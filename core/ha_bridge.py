"""
Home Assistant MQTT discovery bridge.
Publishes Holomat device state to HA via MQTT discovery protocol,
enabling all Holomat sensors to appear as native HA entities.

Configure via environment variables:
  HA_MQTT_HOST  — Mosquitto broker IP/hostname (required to enable)
  HA_MQTT_PORT  — broker port (default: 1883)
  HA_MQTT_USER  — broker username (optional)
  HA_MQTT_PASS  — broker password (optional)
"""
import json
import os
import threading
from typing import Any

from core.logger import get_logger
from core.version import VERSION

log = get_logger(__name__)

HA_MQTT_HOST = os.getenv("HA_MQTT_HOST", "")
HA_MQTT_PORT = int(os.getenv("HA_MQTT_PORT") or "1883")
HA_MQTT_USER = os.getenv("HA_MQTT_USER", "")
HA_MQTT_PASS = os.getenv("HA_MQTT_PASS", "")

DISCOVERY_PREFIX = "homeassistant"
STATE_PREFIX     = "holomat"
AVAIL_TOPIC      = f"{STATE_PREFIX}/availability"

DEVICE_INFO: dict[str, Any] = {
    "identifiers":  ["holomat"],
    "name":         "Holomat",
    "model":        "Smart Fabrication Surface",
    "manufacturer": "JARVIS",
    "sw_version":   VERSION,
}

# Each entry: component, object_id, extra HA config keys
_ENTITIES: list[dict[str, Any]] = [
    {
        "component": "binary_sensor",
        "object_id": "calibration_valid",
        "name":      "Calibration Valid",
        "device_class": "connectivity",
        "icon":      "mdi:grid-large",
    },
    {
        "component":            "sensor",
        "object_id":            "calibration_rmse",
        "name":                 "Calibration RMSE",
        "unit_of_measurement":  "px",
        "icon":                 "mdi:target-variant",
        "suggested_display_precision": 3,
    },
    {
        "component":           "sensor",
        "object_id":           "calibration_points",
        "name":                "Calibration Points",
        "unit_of_measurement": "pts",
        "icon":                "mdi:dots-grid",
    },
    {
        "component":    "binary_sensor",
        "object_id":    "camera_online",
        "name":         "Camera Online",
        "device_class": "connectivity",
        "icon":         "mdi:camera",
    },
    {
        "component": "binary_sensor",
        "object_id": "printer_configured",
        "name":      "Printer Configured",
        "icon":      "mdi:printer-3d",
    },
    {
        "component":           "sensor",
        "object_id":           "ws_clients",
        "name":                "Active Clients",
        "unit_of_measurement": "clients",
        "icon":                "mdi:monitor-multiple",
    },
]


def _state_topic(entity: dict[str, Any]) -> str:
    return f"{STATE_PREFIX}/{entity['component']}/{entity['object_id']}/state"


def _discovery_topic(entity: dict[str, Any]) -> str:
    return f"{DISCOVERY_PREFIX}/{entity['component']}/{entity['object_id']}/config"


def _discovery_payload(entity: dict[str, Any]) -> str:
    obj_id = entity["object_id"]
    config: dict[str, Any] = {
        "name":                entity["name"],
        "unique_id":           f"holomat_{obj_id}",
        "state_topic":         _state_topic(entity),
        "availability_topic":  AVAIL_TOPIC,
        "payload_available":   "online",
        "payload_not_available": "offline",
        "device":              DEVICE_INFO,
    }
    # binary_sensor on/off payloads
    if entity["component"] == "binary_sensor":
        config["payload_on"]  = "ON"
        config["payload_off"] = "OFF"
    # pass through any extra HA config keys
    for key in ("device_class", "icon", "unit_of_measurement", "suggested_display_precision"):
        if key in entity:
            config[key] = entity[key]
    return json.dumps(config)


class _HABridge:
    def __init__(self) -> None:
        self._client:     Any = None
        self._thread:     threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self._connected:  bool = False
        self.running:     bool = False

    # ── public API ──────────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        return bool(HA_MQTT_HOST)

    def start(self) -> None:
        if not self.is_configured():
            raise NotImplementedError("HA bridge requires HA_MQTT_HOST")

        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except ImportError:
            log.warning("paho-mqtt not installed — HA bridge skipped")
            return

        self._stop_event.clear()

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="holomat-bridge",
        )
        if HA_MQTT_USER:
            client.username_pw_set(HA_MQTT_USER, HA_MQTT_PASS)

        # Last-will marks all entities unavailable when Holomat goes offline
        client.will_set(AVAIL_TOPIC, "offline", retain=True)

        client.on_connect    = self._on_connect
        client.on_disconnect = self._on_disconnect

        try:
            client.connect(HA_MQTT_HOST, HA_MQTT_PORT, keepalive=60)
        except Exception as exc:
            log.warning("HA MQTT broker unreachable (%s:%d): %s", HA_MQTT_HOST, HA_MQTT_PORT, exc)
            return

        client.loop_start()
        self._client = client

        self._thread = threading.Thread(
            target=self._publish_loop, daemon=True, name="ha-bridge"
        )
        self._thread.start()
        self.running = True
        log.info("HA bridge started → %s:%d", HA_MQTT_HOST, HA_MQTT_PORT)

    def stop(self) -> None:
        self._stop_event.set()
        if self._client:
            try:
                self._client.publish(AVAIL_TOPIC, "offline", retain=True)
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        self.running    = False
        self._connected = False

    def push(self) -> None:
        """Trigger an immediate state push (e.g., called after calibration update)."""
        if self._connected:
            self._push_state()

    # ── MQTT callbacks ──────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("HA MQTT connection refused: %s", reason_code)
            return
        self._connected = True
        log.info("HA MQTT connected — publishing discovery + availability")
        for entity in _ENTITIES:
            client.publish(_discovery_topic(entity), _discovery_payload(entity), retain=True)
        client.publish(AVAIL_TOPIC, "online", retain=True)
        log.info("HA discovery published (%d entities)", len(_ENTITIES))
        self._push_state()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self._connected = False
        if reason_code.is_failure:
            log.warning("HA MQTT disconnected unexpectedly: %s", reason_code)

    # ── state publishing ────────────────────────────────────────────────────

    def _publish_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(30)
            if not self._stop_event.is_set() and self._connected:
                self._push_state()

    def _push_state(self) -> None:
        try:
            from core import calibration as cal
            from core.camera import camera
            from core.printer import is_configured as printer_is_configured
            from api.websocket import manager as ws_manager

            calib = cal.load()
            state_map: dict[str, str] = {
                "calibration_valid":  "ON"  if calib else "OFF",
                "calibration_rmse":   f"{calib['rmse']:.3f}" if calib and calib.get("rmse") else "unknown",
                "calibration_points": str(calib.get("point_count", 0)) if calib else "0",
                "camera_online":      "ON" if camera.is_available() else "OFF",
                "printer_configured": "ON" if printer_is_configured() else "OFF",
                "ws_clients":         str(ws_manager.connection_count),
            }
            for entity in _ENTITIES:
                obj_id = entity["object_id"]
                value  = state_map.get(obj_id, "unknown")
                self._client.publish(_state_topic(entity), value)
        except Exception as exc:
            log.warning("HA state push failed: %s", exc)


ha_bridge = _HABridge()
