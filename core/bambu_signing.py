"""
Bambu Lab ACS (Authorization Control System) MQTT command signing.

The P1S firmware (post-Jan 2025) requires project_file and other print commands
to carry an RSA-SHA256 signature in a 'header' block.  The signing key is the
Bambu Connect X.509 certificate/private-key pair that was publicly extracted by
the community in January 2025 (Hackaday, Consumer Rights Wiki, schwarztim/bambu-mcp).

The certificate expired December 2025; the printer may or may not check expiry.
Override via env vars BAMBU_APP_PRIVATE_KEY and BAMBU_APP_CERT_ID if Bambu
rotates credentials and a newer key is available.
"""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from core.bambu_acs_key import CERT_ID as _DEFAULT_CERT_ID, KEY_B64 as _DEFAULT_KEY_B64

# ── Bambu Connect ACS credentials ────────────────────────────────────────────
# Publicly-extracted community key — full provenance and the base64-encoded key
# material live in core/bambu_acs_key.py (kept out of this file so a raw PEM
# block does not sit in source). Override at runtime via the env vars named in
# the module docstring above.
_DEFAULT_PRIVATE_KEY_PEM = base64.b64decode(_DEFAULT_KEY_B64).decode()

_CERT_ID      = os.getenv("BAMBU_APP_CERT_ID",      _DEFAULT_CERT_ID)
_PRIVATE_KEY  = os.getenv("BAMBU_APP_PRIVATE_KEY",  _DEFAULT_PRIVATE_KEY_PEM)

# Load key once at module import
_rsa_key = serialization.load_pem_private_key(_PRIVATE_KEY.encode(), password=None)


def sign_mqtt_payload(print_payload: dict, user_id: str) -> dict:
    """
    Wrap a Bambu MQTT print-command dict in an ACS-signed envelope.

    Input:  {"print": {"command": "project_file", ...}}
    Output: {"print": {..., "user_id": "..."}, "header": {sign_ver, sign_alg,
             sign_string, cert_id, payload_len}}

    The signature covers the entire JSON of the inner dict (print object +
    user_id) serialised with no extra whitespace, as per the schwarztim/bambu-mcp
    TypeScript reference implementation.
    """
    inner = {**print_payload, "user_id": user_id}
    payload_str   = json.dumps(inner, separators=(",", ":"), ensure_ascii=False)
    payload_bytes = payload_str.encode("utf-8")

    signature = _rsa_key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())

    return {
        **inner,
        "header": {
            "sign_ver":    "v1.0",
            "sign_alg":    "RSA_SHA256",
            "sign_string": base64.b64encode(signature).decode("utf-8"),
            "cert_id":     _CERT_ID,
            "payload_len": len(payload_bytes),
        },
    }
