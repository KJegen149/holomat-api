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

# ── Extracted Bambu Connect credentials ──────────────────────────────────────
# Source: publicly published by community reverse-engineering of Bambu Connect
# v1.1.3 (schwarztim/bambu-mcp, Consumer Rights Wiki, Hackaday Jan 2025).
# CN from the X.509 Subject field (openssl x509 -noout -subject):
_DEFAULT_CERT_ID = "GLOF3813734089-524a37c80000"

_DEFAULT_PRIVATE_KEY_PEM = """\
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDQNp2NfkajwcWH
PIqosa08P1ZwETPr1veZCMqieQxWtYw97wp+JCxX4yBrBcAwid7o7PHI9KQVzPRM
f0uXspaDUdSljrfJ/YwGEz7+GJz4+ml1UbWXBePyzXW1+N2hIGGn7BcNuA0v8rMY
uvVgiIIQNjLErgGcCWmMHLwsMMQ7LNprUZZKsSNB4HaQDH7cQZmYBN/O45np6l+K
VuLdzXdDpZcOM7bNO6smev822WPGDuKBo1iVfQbUe10X4dCNwkBR3QGpScVvg8gg
tRYZDYue/qc4Xaj806RZPttknWfxdvfZgoOmAiwnyQ5K3+mzNYHgQZAOC2ydkK4J
s+ZizK3lAgMBAAECggEAKwEcyXyrWmdLRQNcIDuSbD8ouzzSXIOp4BHQyH337nDQ
5nnY0PTns79VksU9TMktIS7PQZJF0brjOmmQU2SvcbAVG5y+mRmlMhwHhrPOuB4A
ahrWRrsQubV1+n/MRttJUEWS/WJmVuDp3NHAnI+VTYPkOHs4GeJXynik5PutjAr3
tYmr3kaw0Wo/hYAXTKsI/R5aenC7jH8ZSyVcZ/j+bOSH5sT5/JY122AYmkQOFE7s
JA0EfYJaJEwiuBWKOfRLQVEHhOFodUBZdGQcWeW3uFb88aYKN8QcKTO8/f6e4r8w
QojgK3QMj1zmfS7xid6XCOVa17ary2hZHAEPnjcigQKBgQDQnm4TlbVTsM+CbFUS
1rOIJRzPdnH3Y7x3IcmVKZt81eNktsdu56A4U6NEkFQqk4tVTT4TYja/hwgXmm6w
J+w0WwZd445Bxj8PmaEr6Z/NSMYbCsi8pRelKWmlIMwD2YhtY/1xXD37zpOgN8oQ
ryTKZR2gljbPxdfhKS7YerLp2wKBgQD/gJt3Ds69j1gMDLnnPctjmhsPRXh7PQ0e
E9lqgFkx/vNuCuyRs6ymic2rBZmkdlpjsTJFmz1bwOzIvSRoH6kp0Mfyo6why5kr
upDf7zz+hlvaFewme8aDeV3ex9Wvt73D66nwAy5ABOgn+66vZJeo0Iq/tnCwK3a/
evTL9BOzPwKBgEUi7AnziEc3Bl4Lttnqa08INZcPgs9grzmv6dVUF6J0Y8qhxFAd
1Pw1w5raVfpSMU/QrGzSFKC+iFECLgKVCHOFYwPEgQWNRKLP4BjkcMAgiP63QTU7
ZS2oHsnJp7Ly6YKPK5Pg5O3JVSU4t+91i7TDc+EfRwTuZQ/KjSrS5u4XAoGBAP06
v9reSDVELuWyb0Yqzrxm7k7ScbjjJ28aCTAvCTguEaKNHS7DP2jHx5mrMT35N1j7
NHIcjFG2AnhqTf0M9CJHlQR9B4tvON5ISHJJsNAq5jpd4/G4V2XTEiBNOxKvL1tQ
5NrGrD4zHs0R+25GarGcDwg3j7RrP4REHv9NZ4ENAoGAY7Nuz6xKu2XUwuZtJP7O
kjsoDS7bjP95ddrtsRq5vcVjJ04avnjsr+Se9WDA//t7+eSeHjm5eXD7u0NtdqZo
WtSm8pmWySOPXMn9QQmdzKHg1NOxer//f1KySVunX1vftTStjsZH7dRCtBEePcqg
z5Av6MmEFDojtwTqvEZuhBM=
-----END PRIVATE KEY-----"""

# Allow runtime override if Bambu rotates credentials
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
