"""
Gallery routes — SMB share image browser and 3D/SVG conversion pipeline.

GET    /api/gallery                    — list gallery items (paginated)
GET    /api/gallery/{id}               — single gallery item metadata
GET    /api/gallery/{id}/image         — proxy raw image from R2
DELETE /api/gallery/{id}               — remove from gallery + R2
POST   /api/gallery/{id}/generate-3d   — submit to Meshy image-to-3D
POST   /api/gallery/{id}/generate-svg  — recreate as SVG via Gemini Vision
"""
import io
import os
import re

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from core.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


def _api_url() -> str:
    return os.getenv("CF_API_URL", "").rstrip("/")


def _cf_headers() -> dict:
    return {"X-API-Key": os.getenv("CF_API_KEY", "")}


def _no_cf() -> JSONResponse:
    return JSONResponse(
        {"error": "cf_not_configured", "detail": "CF_API_URL / CF_API_KEY not set"},
        status_code=503,
    )


def _configured() -> bool:
    return bool(_api_url() and os.getenv("CF_API_KEY", ""))


# ── List ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_gallery(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    if not _configured():
        return _no_cf()
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{_api_url()}/api/gallery",
            headers=_cf_headers(),
            params={"limit": limit, "offset": offset},
        )
        r.raise_for_status()
        return JSONResponse(r.json())


# ── Image proxy ─────────────────────────────────────────────────────────────

@router.get("/{item_id}/image")
async def get_gallery_image(item_id: str):
    if not _configured():
        return _no_cf()
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{_api_url()}/api/gallery/{item_id}/image",
            headers=_cf_headers(),
        )
        if r.status_code == 404:
            return JSONResponse({"error": "not_found"}, status_code=404)
        r.raise_for_status()
        return StreamingResponse(
            iter([r.content]),
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600"},
        )


# ── Single item ─────────────────────────────────────────────────────────────

@router.get("/{item_id}")
async def get_gallery_item(item_id: str) -> JSONResponse:
    if not _configured():
        return _no_cf()
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{_api_url()}/api/gallery/{item_id}",
            headers=_cf_headers(),
        )
        if r.status_code == 404:
            return JSONResponse({"error": "not_found"}, status_code=404)
        r.raise_for_status()
        return JSONResponse(r.json())


# ── Delete ──────────────────────────────────────────────────────────────────

@router.delete("/{item_id}")
async def delete_gallery_item(item_id: str) -> JSONResponse:
    if not _configured():
        return _no_cf()
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.delete(
            f"{_api_url()}/api/gallery/{item_id}",
            headers=_cf_headers(),
        )
        if r.status_code == 404:
            return JSONResponse({"error": "not_found"}, status_code=404)
        r.raise_for_status()
        return JSONResponse(r.json())


# ── Generate 3D (Meshy image-to-3D) ─────────────────────────────────────────

@router.post("/{item_id}/generate-3d")
async def gallery_to_3d(item_id: str) -> JSONResponse:
    if not _configured():
        return _no_cf()
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Fetch gallery item metadata
        meta_r = await client.get(
            f"{_api_url()}/api/gallery/{item_id}",
            headers=_cf_headers(),
        )
        if meta_r.status_code == 404:
            return JSONResponse({"error": "not_found"}, status_code=404)
        meta_r.raise_for_status()
        item = meta_r.json()

        # Download image bytes from R2 via our proxy
        img_r = await client.get(
            f"{_api_url()}/api/gallery/{item_id}/image",
            headers=_cf_headers(),
        )
        img_r.raise_for_status()

        # Upload to jarvis-api temp store → get public URL for Meshy
        upload_r = await client.post(
            f"{_api_url()}/api/meshy/upload-image",
            content=img_r.content,
            headers={
                "X-API-Key": os.getenv("CF_API_KEY", ""),
                "Content-Type": img_r.headers.get("content-type", "image/jpeg"),
            },
        )
        upload_r.raise_for_status()
        public_url = upload_r.json()["url"]

        # Submit image-to-3D job to Meshy
        meshy_r = await client.post(
            f"{_api_url()}/api/meshy/generate",
            json={"image_url": public_url},
            headers=_cf_headers(),
        )
        meshy_r.raise_for_status()
        meshy = meshy_r.json()

        # Create a project to track the 3D job
        proj_name = f"Gallery 3D: {item.get('filename', item_id)}"[:60]
        proj_r = await client.post(
            f"{_api_url()}/api/projects",
            json={"name": proj_name, "type": "3d_model"},
            headers=_cf_headers(),
        )
        proj_r.raise_for_status()
        project = proj_r.json()

    log.info("Meshy image-to-3D submitted: task=%s project=%s", meshy.get("task_id"), project.get("id"))
    return JSONResponse(
        {
            "task_id": meshy["task_id"],
            "mode": "image",
            "project_id": project["id"],
            "gallery_item_id": item_id,
        },
        status_code=202,
    )


# ── Generate SVG (Gemini Vision) ─────────────────────────────────────────────

_SVG_PROMPT = (
    "Analyze this image and recreate it as a clean SVG vector graphic suitable for "
    "a Cricut Explore 4 vinyl cutter. Return ONLY the complete SVG code, starting "
    "with <svg and ending with </svg>. No markdown fences, no explanation. "
    "Rules: use stroke='black' fill='none' stroke-width='1' for cut lines; "
    "viewBox must match the actual content proportions; minimum 200 units wide."
)


@router.post("/{item_id}/generate-svg")
async def gallery_to_svg(item_id: str) -> JSONResponse:
    if not _configured():
        return _no_cf()

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        return JSONResponse({"error": "gemini_not_configured"}, status_code=503)

    # Download image from R2
    async with httpx.AsyncClient(timeout=20.0) as client:
        img_r = await client.get(
            f"{_api_url()}/api/gallery/{item_id}/image",
            headers=_cf_headers(),
        )
        if img_r.status_code == 404:
            return JSONResponse({"error": "not_found"}, status_code=404)
        img_r.raise_for_status()
        img_bytes = img_r.content
        content_type = img_r.headers.get("content-type", "image/jpeg")

    # Normalize to JPEG for Gemini (it handles PNG fine too, but JPEG is safer)
    if "png" in content_type or "webp" in content_type or "gif" in content_type:
        import PIL.Image
        buf = io.BytesIO()
        PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB").save(buf, format="JPEG", quality=92)
        img_bytes = buf.getvalue()
        content_type = "image/jpeg"

    import asyncio
    import PIL.Image
    import google.generativeai as genai

    genai.configure(api_key=gemini_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    model = genai.GenerativeModel(model_name)
    image = PIL.Image.open(io.BytesIO(img_bytes))

    loop = asyncio.get_running_loop()
    response = await model.generate_content_async([_SVG_PROMPT, image])
    raw = response.text.strip()

    # Strip markdown fences if model adds them
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
        ).strip()

    m = re.search(r"<svg[\s\S]*?</svg>", raw, re.IGNORECASE)
    if not m:
        log.warning("Gemini SVG response had no <svg> tag: %s", raw[:200])
        return JSONResponse({"error": "no_svg_in_response", "raw": raw[:500]}, status_code=502)

    log.info("Gallery SVG generated for item %s", item_id)
    return JSONResponse({"svg": m.group(0), "gallery_item_id": item_id})
