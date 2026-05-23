"""
Print queue manager — Phase 7.

Job lifecycle: queued → slicing → uploading → printing → done | failed | cancelled
Persistence: scan_data/print_queue.json, scan_data/print_profiles.json
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)

QUEUE_FILE    = Path("scan_data/print_queue.json")
PROFILES_FILE = Path("scan_data/print_profiles.json")
THREE_MF_DIR  = Path("scan_data/3mfs")

BUILTIN_PROFILES: list[dict] = [
    {"id": "draft",    "name": "Draft",    "layer_height": 0.28, "infill_percent": 15, "supports": "none", "is_builtin": True},
    {"id": "standard", "name": "Standard", "layer_height": 0.20, "infill_percent": 15, "supports": "none", "is_builtin": True},
    {"id": "fine",     "name": "Fine",     "layer_height": 0.10, "infill_percent": 20, "supports": "none", "is_builtin": True},
]

_ACTIVE_STATES  = {"slicing", "uploading", "printing"}
_TERMINAL_STATES = {"done", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PrintQueue:
    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._jobs: list[dict] = []
        self._profiles: list[dict] = []
        self._worker_task: Optional[asyncio.Task] = None
        self._broadcast = None
        THREE_MF_DIR.mkdir(parents=True, exist_ok=True)

    def set_broadcast(self, fn) -> None:
        self._broadcast = fn

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if QUEUE_FILE.exists():
            try:
                self._jobs = json.loads(QUEUE_FILE.read_text())
            except Exception:
                self._jobs = []
        # Reset mid-flight states on restart so they re-queue
        for job in self._jobs:
            if job.get("state") in _ACTIVE_STATES:
                job["state"] = "queued"
                job["started_at"] = None

        if PROFILES_FILE.exists():
            try:
                self._profiles = json.loads(PROFILES_FILE.read_text())
            except Exception:
                self._profiles = []

    def _save_jobs(self) -> None:
        QUEUE_FILE.write_text(json.dumps(self._jobs, indent=2))

    def _save_profiles(self) -> None:
        PROFILES_FILE.write_text(json.dumps(self._profiles, indent=2))

    # ── Profile management ──────────────────────────────────────────────────

    def get_all_profiles(self) -> list[dict]:
        return BUILTIN_PROFILES + self._profiles

    def get_profile(self, profile_id: str) -> Optional[dict]:
        for p in self.get_all_profiles():
            if p["id"] == profile_id:
                return p
        return None

    def add_profile(
        self,
        name: str,
        layer_height: float,
        infill_percent: int,
        supports: str,
    ) -> dict:
        profile = {
            "id": str(uuid.uuid4()),
            "name": name,
            "layer_height": layer_height,
            "infill_percent": infill_percent,
            "supports": supports,
            "is_builtin": False,
        }
        self._profiles.append(profile)
        self._save_profiles()
        return profile

    def delete_profile(self, profile_id: str) -> bool:
        before = len(self._profiles)
        self._profiles = [p for p in self._profiles if p["id"] != profile_id]
        if len(self._profiles) < before:
            self._save_profiles()
            return True
        return False

    # ── Job management ──────────────────────────────────────────────────────

    async def add_job(
        self,
        name: str,
        stl_path: str,
        profile_id: str,
        ams_slot: Optional[int] = None,
    ) -> dict:
        async with self._lock:
            job: dict = {
                "id": str(uuid.uuid4()),
                "name": name,
                "stl_path": stl_path,
                "profile_id": profile_id,
                "ams_slot": ams_slot,  # None = use BAMBU_AMS_SLOT env default at print time
                "state": "queued",
                "created_at": _now(),
                "started_at": None,
                "completed_at": None,
                "error": None,
                "three_mf_path": None,
                "progress": 0,
            }
            self._jobs.append(job)
            self._save_jobs()
            log.info("Print job queued: %s (%s, ams_slot=%s)",
                     name, job["id"], ams_slot if ams_slot is not None else "default")
            return job

    def get_jobs(self) -> list[dict]:
        return list(self._jobs)

    async def cancel_job(self, job_id: str) -> bool:
        async with self._lock:
            for job in self._jobs:
                if job["id"] == job_id and job["state"] == "queued":
                    job["state"] = "cancelled"
                    job["completed_at"] = _now()
                    self._save_jobs()
                    log.info("Print job cancelled: %s", job_id)
                    return True
        return False

    # ── Internal worker helpers ─────────────────────────────────────────────

    async def _set(self, job_id: str, **kwargs) -> None:
        """Update job fields and persist; broadcast change over WebSocket."""
        async with self._lock:
            for job in self._jobs:
                if job["id"] == job_id:
                    job.update(kwargs)
                    self._save_jobs()
                    break

        if self._broadcast:
            try:
                await self._broadcast(json.dumps({
                    "type": "print_queue_update",
                    "job_id": job_id,
                    **kwargs,
                }))
            except Exception:
                pass

    async def _process_job(self, job: dict) -> None:
        job_id  = job["id"]
        profile = self.get_profile(job["profile_id"]) or self.get_profile("standard")
        assert profile is not None

        # Resolve AMS slot: per-job override → env default → 0
        import os as _os
        if job.get("ams_slot") is not None:
            ams_slot = int(job["ams_slot"])
        else:
            ams_slot = int(_os.getenv("BAMBU_AMS_SLOT", "0"))

        # ── 1. Slice STL → 3MF ────────────────────────────────────────────
        await self._set(job_id, state="slicing", started_at=_now())
        log.info("Slicing: %s (ams_slot=%d)", job["stl_path"], ams_slot)
        try:
            from core.slicer import slice_model, orca_available
            if not orca_available():
                raise RuntimeError(
                    f"OrcaSlicer not found at {_os.getenv('ORCA_CLI', '/usr/bin/orca-slicer')!r} — "
                    "install OrcaSlicer and set ORCA_CLI env var"
                )
            three_mf_path = await slice_model(
                input_path=job["stl_path"],
                quality=job["profile_id"] if profile.get("is_builtin") else "standard",
                infill=profile["infill_percent"],
                supports=profile["supports"],
                output_dir=str(THREE_MF_DIR),
                ams_slot=ams_slot,
            )
        except Exception as e:
            log.error("Slice failed: %s", e)
            await self._set(job_id, state="failed", error=str(e), completed_at=_now())
            return

        await self._set(job_id, three_mf_path=three_mf_path)

        # ── 2. FTP upload + MQTT print trigger ────────────────────────────
        await self._set(job_id, state="uploading")
        log.info("Uploading: %s", three_mf_path)
        try:
            from core.printer import send_and_print, is_configured
            if not is_configured():
                raise RuntimeError(
                    "Bambu printer not configured — set BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL"
                )
            await send_and_print(three_mf_path, ams_slot=ams_slot)
        except Exception as e:
            log.error("Upload/print trigger failed: %s", e)
            await self._set(job_id, state="failed", error=str(e), completed_at=_now())
            return

        await self._set(job_id, state="printing")

        # ── 3. Poll printer until done (up to 8 h) ────────────────────────
        # State machine for a fresh job: IDLE → PREPARE → RUNNING → FINISH → IDLE.
        # We MUST see RUNNING at least once before treating IDLE/FINISH as
        # completion — otherwise the first poll after dispatch (still IDLE
        # because the printer is heating) flips the job to done in ~10 s.
        # If we never see RUNNING within the startup grace window the printer
        # almost certainly silently aborted (the classic "ack but no print"
        # mode) and we mark the job failed with a real reason.
        from core.printer import get_status
        seen_running   = False
        startup_grace  = 30  # number of poll cycles (~5 min @ 10 s) to see RUNNING
        polls_so_far   = 0

        for _ in range(2880):  # 8 h at 10 s intervals
            await asyncio.sleep(10)
            polls_so_far += 1
            try:
                status = await get_status()
                if "error" in status:
                    continue  # connectivity blip — keep polling
                progress = status.get("progress", 0) or 0
                state_str = str(status.get("state", "")).upper()
                if "." in state_str:          # strip enum prefix e.g. GcodeState.IDLE
                    state_str = state_str.split(".")[-1]
                await self._set(job_id, progress=progress)

                if state_str in ("RUNNING", "PRINTING"):
                    seen_running = True
                    continue

                if state_str in ("FAILED", "STOP"):
                    await self._set(
                        job_id, state="failed",
                        error=f"Printer reported: {state_str}", completed_at=_now(),
                    )
                    return

                if state_str in ("IDLE", "FINISH", "FINISHED"):
                    if seen_running:
                        break  # genuine completion
                    if polls_so_far >= startup_grace:
                        await self._set(
                            job_id, state="failed",
                            error=(
                                "Printer never entered RUNNING state — most likely "
                                "the job was silently aborted (missing user_id, "
                                "AMS error, or rejected file). Check the printer "
                                "touchscreen for the actual reason."
                            ),
                            completed_at=_now(),
                        )
                        return
                    # still in startup grace — keep waiting for RUNNING
            except Exception:
                pass  # transient error — keep polling

        await self._set(job_id, state="done", progress=100, completed_at=_now())
        log.info("Print job done: %s", job_id)

    async def _worker(self) -> None:
        log.info("Print queue worker started")
        while True:
            await asyncio.sleep(5)
            queued = [j for j in self._jobs if j["state"] == "queued"]
            if not queued:
                continue
            job = queued[0]
            try:
                await self._process_job(job)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("Worker unhandled error: %s", e)
                try:
                    await self._set(job["id"], state="failed", error=str(e), completed_at=_now())
                except Exception:
                    pass

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> None:
        self._load()
        self._worker_task = asyncio.get_running_loop().create_task(self._worker())
        log.info("Print queue ready (%d jobs loaded)", len(self._jobs))

    def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()


print_queue = PrintQueue()
