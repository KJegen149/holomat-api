"""
Meshy retrieval tracker — Phase 11 item 3.

When the Gallery's "3D" button submits an image-to-3D job to Meshy, we record
the Meshy `task_id` here. A background worker polls each task via the
Cloudflare worker (`/api/meshy/status/{task_id}`) and — on `SUCCEEDED` —
downloads `model_urls.stl` into `scan_data/stls/`, writing a sidecar
`.meta.json` so the Model Sources tab labels the file as Meshy-sourced.

Job lifecycle: pending → polling → downloading → done | failed | cancelled
Persistence: scan_data/meshy_jobs.json (mid-flight states reset to `pending`
on restart so the worker resumes after a process restart).
"""
import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from core.logger import get_logger

log = get_logger(__name__)

JOBS_FILE = Path("scan_data/meshy_jobs.json")
STL_DIR = Path("scan_data/stls")

_ACTIVE_STATES = {"pending", "polling", "downloading"}
_TERMINAL_STATES = {"done", "failed", "cancelled"}

# How often to poll a single Meshy task while the worker is running.
_POLL_INTERVAL_S = 10
# Hard ceiling on how long any single task can run before we abandon it.
_MAX_TASK_AGE_S = 60 * 60  # 1 hour — Meshy image-to-3D normally completes in 2-5 min


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)[:40] or "meshy"


class MeshyJobs:
    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._jobs: list[dict] = []
        self._worker_task: Optional[asyncio.Task] = None
        self._broadcast = None
        self._loaded = False

    def set_broadcast(self, fn) -> None:
        self._broadcast = fn

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if JOBS_FILE.exists():
            try:
                self._jobs = json.loads(JOBS_FILE.read_text())
            except Exception:
                self._jobs = []
        # Reset mid-flight states on restart so the worker resumes
        for job in self._jobs:
            if job.get("state") in _ACTIVE_STATES:
                job["state"] = "pending"
        self._loaded = True

    def _save(self) -> None:
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        JOBS_FILE.write_text(json.dumps(self._jobs, indent=2))

    # ── Public API ──────────────────────────────────────────────────────────

    def get_jobs(self) -> list[dict]:
        return list(self._jobs)

    async def add_job(
        self,
        task_id: str,
        source_filename: str,
        gallery_item_id: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
    ) -> dict:
        """Register a freshly-submitted Meshy task for tracking."""
        if not self._loaded:
            self._load()
        async with self._lock:
            job = {
                "id": str(uuid.uuid4()),
                "task_id": task_id,
                "source": "image",
                "source_filename": source_filename,
                "gallery_item_id": gallery_item_id,
                "thumbnail_url": thumbnail_url,
                "state": "pending",
                "created_at": _now(),
                "completed_at": None,
                "error": None,
                "progress": 0,
                "stl_filename": None,
            }
            self._jobs.append(job)
            self._save()
        log.info("Meshy job tracked: task=%s file=%s", task_id, source_filename)
        await self._broadcast_update(job["id"], state="pending")
        return job

    async def cancel_job(self, job_id: str) -> bool:
        async with self._lock:
            for job in self._jobs:
                if job["id"] == job_id and job["state"] in _ACTIVE_STATES:
                    job["state"] = "cancelled"
                    job["completed_at"] = _now()
                    self._save()
                    log.info("Meshy job cancelled: %s", job_id)
                    await self._broadcast_update(job_id, state="cancelled")
                    return True
        return False

    # ── Worker ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        if not self._loaded:
            self._load()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.warning("Meshy worker can't start outside an event loop")
            return
        self._worker_task = loop.create_task(self._worker())
        log.info("Meshy retrieval worker started")

    def stop(self) -> None:
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()

    async def _worker(self) -> None:
        try:
            while True:
                try:
                    await self._tick()
                except Exception:
                    log.exception("Meshy worker tick failed")
                await asyncio.sleep(_POLL_INTERVAL_S)
        except asyncio.CancelledError:
            return

    async def _tick(self) -> None:
        pending = [j for j in self._jobs if j["state"] in _ACTIVE_STATES]
        if not pending:
            return
        cf_url = os.getenv("CF_API_URL", "").rstrip("/")
        cf_key = os.getenv("CF_API_KEY", "")
        if not cf_url:
            return  # nothing to do without CF
        headers: dict[str, str] = {"X-API-Key": cf_key} if cf_key else {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for job in pending:
                await self._poll_one(job, client, cf_url, headers)

    async def _poll_one(
        self,
        job: dict,
        client: httpx.AsyncClient,
        cf_url: str,
        headers: dict,
    ) -> None:
        # Abandon ancient jobs that never completed
        created = datetime.fromisoformat(job["created_at"])
        age_s = (datetime.now(timezone.utc) - created).total_seconds()
        if age_s > _MAX_TASK_AGE_S:
            await self._set(
                job["id"],
                state="failed",
                error=f"Timed out after {int(age_s)}s",
                completed_at=_now(),
            )
            return

        try:
            r = await client.get(f"{cf_url}/api/meshy/status/{job['task_id']}", headers=headers)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            log.warning("Meshy poll failed for %s: %s", job["task_id"], e)
            return  # transient — try again next tick

        status = str(data.get("status", "")).upper()
        progress = int(data.get("progress", 0) or 0)
        if job["state"] == "pending":
            await self._set(job["id"], state="polling", progress=progress)
        elif progress != job.get("progress"):
            await self._set(job["id"], progress=progress)

        if status in ("FAILED", "CANCELED", "EXPIRED"):
            err = data.get("task_error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            await self._set(
                job["id"],
                state="failed",
                error=msg or f"Meshy reported: {status}",
                completed_at=_now(),
            )
            return

        if status == "SUCCEEDED":
            await self._download_stl(job, data, client, headers)
            return
        # PENDING / IN_PROGRESS → keep polling

    async def _download_stl(
        self,
        job: dict,
        task: dict,
        client: httpx.AsyncClient,
        headers: dict,
    ) -> None:
        urls = task.get("model_urls") or {}
        stl_url = urls.get("stl")
        if not stl_url:
            await self._set(
                job["id"],
                state="failed",
                error="Meshy task succeeded but did not return an STL URL",
                completed_at=_now(),
            )
            return

        await self._set(job["id"], state="downloading", progress=100)

        STL_DIR.mkdir(parents=True, exist_ok=True)
        stem = _safe_stem(Path(job["source_filename"]).stem)
        filename = f"{stem}_{job['task_id'][:8]}.stl"
        stl_path = STL_DIR / filename

        try:
            # Meshy URLs are presigned — no auth headers needed.
            async with client.stream("GET", stl_url, timeout=120.0) as resp:
                resp.raise_for_status()
                with open(stl_path, "wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        fh.write(chunk)
        except httpx.HTTPError as e:
            log.error("Meshy STL download failed for %s: %s", job["task_id"], e)
            await self._set(
                job["id"],
                state="failed",
                error=f"STL download failed: {e}",
                completed_at=_now(),
            )
            return

        # Sidecar — labels this STL in the Model Sources grid
        sidecar = stl_path.with_suffix(stl_path.suffix + ".meta.json")
        # Meshy task URLs aren't part of the public API and the user-facing
        # workspace URL needs the workspace id we don't have here, so leave
        # external_url unset — the MESHY source badge is enough labelling.
        sidecar.write_text(json.dumps({
            "source": "meshy",
            "thumbnail_url": task.get("thumbnail_url") or job.get("thumbnail_url"),
            "gallery_item_id": job.get("gallery_item_id"),
            "task_id": job["task_id"],
            "source_filename": job["source_filename"],
        }, indent=2))

        await self._set(
            job["id"],
            state="done",
            stl_filename=filename,
            completed_at=_now(),
            progress=100,
        )
        log.info("Meshy STL retrieved: %s → %s", job["task_id"], filename)

    # ── Internals ───────────────────────────────────────────────────────────

    async def _set(self, job_id: str, **kwargs) -> None:
        async with self._lock:
            for job in self._jobs:
                if job["id"] == job_id:
                    job.update(kwargs)
                    self._save()
                    break
        await self._broadcast_update(job_id, **kwargs)

    async def _broadcast_update(self, job_id: str, **kwargs) -> None:
        if not self._broadcast:
            return
        try:
            await self._broadcast(json.dumps({
                "type": "meshy_job_update",
                "job_id": job_id,
                **kwargs,
            }))
        except Exception:
            pass


meshy_jobs = MeshyJobs()
