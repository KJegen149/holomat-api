"""
MakerWorld paste-URL inlet — Phase 11 item 5.

MakerWorld has no official public API; this module uses the
reverse-engineered `api.bambulab.com/v1/design-service/*` endpoints
documented at https://github.com/Doridian/OpenBambuAPI. They could change
without notice.

Authentication reuses the same Bambu Cloud credentials that the printer
flow already needs (`BAMBU_EMAIL` / `BAMBU_PASSWORD`); the `bambulab`
library caches the access token at `BAMBU_TOKEN_FILE`.

Public surface:
- `parse_design_id(url)` → int | None
- `get_design(design_id)` → metadata dict
- `download_3mf(design_id) -> (bytes, suggested_filename, metadata)`
"""
import os
import re
from pathlib import Path
from typing import Optional

import httpx

from core.logger import get_logger

log = get_logger(__name__)

_BASE = "https://api.bambulab.com"

# MakerWorld URLs look like:
#   https://makerworld.com/en/models/12345
#   https://makerworld.com/models/12345-some-slug
#   https://makerworld.com/en/models/12345#profileId=67890
_URL_RE = re.compile(r"makerworld\.com/(?:[a-z]{2}/)?models/(\d+)", re.IGNORECASE)


def parse_design_id(url: str) -> Optional[int]:
    """Extract the numeric design ID from a MakerWorld URL."""
    if not url:
        return None
    m = _URL_RE.search(url)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _bambu_token() -> str:
    """Get a Bambu Cloud access token using the same auth path the printer uses."""
    email = os.getenv("BAMBU_EMAIL", "")
    password = os.getenv("BAMBU_PASSWORD", "")
    region = os.getenv("BAMBU_REGION", "global")
    token_file = os.getenv("BAMBU_TOKEN_FILE", "scan_data/.bambu_token")
    if not email or not password:
        raise RuntimeError("BAMBU_EMAIL / BAMBU_PASSWORD not set — needed for MakerWorld auth")
    from bambulab import BambuAuthenticator  # type: ignore
    Path(token_file).parent.mkdir(parents=True, exist_ok=True)
    auth = BambuAuthenticator(region=region, token_file=token_file)
    return auth.get_or_create_token(username=email, password=password)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_bambu_token()}",
        "Accept": "application/json",
        "User-Agent": "Holomat/1.0",
    }


async def get_design(design_id: int) -> dict:
    """Fetch design metadata. Returns the raw payload from design-service."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get(f"{_BASE}/v1/design-service/design/{design_id}", headers=_headers())
        r.raise_for_status()
        return r.json()


def _normalize_design(payload: dict, design_id: int) -> dict:
    """Pull a stable subset of fields out of the design-service envelope."""
    # The design-service response shape isn't formally documented. Common
    # field paths observed: `name`/`title`, `cover` (thumbnail), `nickName`
    # (creator), `instances` (variants with download URLs). Try multiple
    # spellings and fall back gracefully.
    data = payload.get("data") if isinstance(payload, dict) else None
    src = data if isinstance(data, dict) else (payload if isinstance(payload, dict) else {})

    return {
        "design_id": design_id,
        "name": src.get("title") or src.get("name") or f"Design {design_id}",
        "creator": (
            src.get("designCreator", {}).get("nickName")
            or src.get("nickName")
            or src.get("creator", {}).get("name")
            or "unknown"
        ),
        "thumbnail_url": src.get("cover") or src.get("coverUrl") or src.get("thumbnail_url"),
        "public_url": f"https://makerworld.com/en/models/{design_id}",
        "instances": src.get("instances") or src.get("designInstances") or [],
    }


def _extract_download_url(design_payload: dict) -> Optional[str]:
    """Walk the design payload for the first plausible 3MF download URL."""
    # Best-effort traversal — MakerWorld returns a tree with nested
    # `context` arrays that each carry `url` + `md5`. Pick the first URL
    # that looks like a .3mf or a presigned CDN download.
    def _walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                if key in ("url", "downloadUrl", "download_url") and isinstance(val, str):
                    if ".3mf" in val.lower() or "x-amz" in val.lower() or "Signature=" in val:
                        return val
                hit = _walk(val)
                if hit:
                    return hit
        elif isinstance(node, list):
            for item in node:
                hit = _walk(item)
                if hit:
                    return hit
        return None
    return _walk(design_payload)


async def download_3mf(design_id: int) -> "tuple[bytes, str, dict]":
    """
    Download the 3MF for a MakerWorld design.
    Returns (file_bytes, suggested_filename, normalized_metadata).
    """
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        # 1. Fetch design metadata
        meta_resp = await client.get(
            f"{_BASE}/v1/design-service/design/{design_id}",
            headers=_headers(),
        )
        meta_resp.raise_for_status()
        meta_payload = meta_resp.json()

        normalized = _normalize_design(meta_payload, design_id)

        # 2. Find a download URL in the design payload
        url = _extract_download_url(meta_payload)

        # 3. If not in the design metadata directly, walk the first instance
        # via /v1/design-service/instance/{id} which is more likely to carry
        # the file context with download URLs.
        if not url:
            instances = normalized.get("instances") or []
            for inst in instances:
                inst_id = inst.get("id") if isinstance(inst, dict) else None
                if not inst_id:
                    continue
                try:
                    inst_resp = await client.get(
                        f"{_BASE}/v1/design-service/instance/{inst_id}",
                        headers=_headers(),
                    )
                    inst_resp.raise_for_status()
                    url = _extract_download_url(inst_resp.json())
                    if url:
                        break
                except httpx.HTTPError as e:
                    log.debug("MakerWorld instance %s lookup failed: %s", inst_id, e)
                    continue

        if not url:
            raise RuntimeError(
                "Could not locate a download URL in the MakerWorld design payload. "
                "The reverse-engineered API path may have changed — fall back to "
                "downloading manually and dropping into the HolomatSTL share."
            )

        # 4. Download the 3MF (presigned CDN — no auth header needed)
        file_resp = await client.get(url)
        file_resp.raise_for_status()

        # Suggested filename: prefer Content-Disposition, then design name
        suggested = None
        disp = file_resp.headers.get("content-disposition", "")
        if "filename=" in disp:
            suggested = disp.split("filename=", 1)[1].strip().strip('"').strip("'")
        if not suggested:
            stem = re.sub(r"[^A-Za-z0-9_-]", "_", normalized["name"])[:40] or f"makerworld_{design_id}"
            suggested = f"{stem}.3mf"

        return file_resp.content, suggested, normalized
