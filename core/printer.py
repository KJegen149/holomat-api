"""
Bambu Lab P1S wrapper — MQTT status polling and print job submission.
Wraps bambulabs-api with async helpers and structured logging.

Migrated from original main.py Phase 2A. Full queue and monitoring
UI implemented in Phase 5.
"""
import os
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)

BAMBU_IP = os.getenv("BAMBU_IP", "")
BAMBU_ACCESS_CODE = os.getenv("BAMBU_ACCESS_CODE", "")
BAMBU_SERIAL = os.getenv("BAMBU_SERIAL", "")
BAMBU_CERT = os.getenv("BAMBU_CERT", "certs/printer.pem")


async def get_status() -> dict:
    """
    Connect to printer via MQTT, wait for status, return state dict.
    Returns {state, nozzle_temp, bed_temp, progress, current_file}.
    """
    try:
        import bambulabs_api as bl  # type: ignore
    except ImportError:
        return {"error": "bambulabs-api not installed"}

    if not all([BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL]):
        return {"error": "Bambu credentials not configured"}

    printer = bl.Printer(BAMBU_IP, BAMBU_ACCESS_CODE, BAMBU_SERIAL)
    try:
        printer.start()
        import asyncio
        for _ in range(16):
            if printer.mqtt_client_connected():
                break
            await asyncio.sleep(0.5)

        return {
            "state": str(printer.get_state()),
            "nozzle_temp": printer.get_nozzle_temper(),
            "bed_temp": printer.get_bed_temper(),
            "progress": printer.get_print_percent(),
            "current_file": printer.get_gcode_file(),
        }
    finally:
        printer.stop()


async def send_and_print(path_3mf: str) -> dict:
    """
    FTP upload .3mf to printer then trigger print via MQTT.
    Full implementation in Phase 5.
    """
    raise NotImplementedError("Phase 5")


def is_configured() -> bool:
    return bool(BAMBU_IP and BAMBU_ACCESS_CODE and BAMBU_SERIAL)
