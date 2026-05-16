#!/usr/bin/env python3
"""
Deep probe of the Panda Touch web server.
All endpoints return 500 (not 404) — server has live handlers, just needs
correct request format. This script extracts the JS source to find the API.

Usage:
  PANDA_TOUCH_IP=10.11.12.197 python3 scripts/probe_panda_touch.py
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE = f"http://{os.getenv('PANDA_TOUCH_IP', '10.11.12.197')}"

def get(path, label=""):
    url = BASE + path
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            body = r.read()
            print(f"GET {path:40} → {r.status}  {len(body)} bytes")
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f"GET {path:40} → {e.code}  {len(body)} bytes")
        return e.code, body
    except Exception as ex:
        print(f"GET {path:40} → ERR {ex}")
        return 0, b""

def post(path, data=None, content_type="application/json"):
    url = BASE + path
    payload = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=payload,
          headers={"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read()
            print(f"POST {path:39} → {r.status}  {len(body)} bytes  body={body[:120]!r}")
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f"POST {path:39} → {e.code}  body={body[:120]!r}")
        return e.code, body
    except Exception as ex:
        print(f"POST {path:39} → ERR {ex}")
        return 0, b""

def section(title):
    print(f"\n{'─'*65}")
    print(f"  {title}")
    print('─'*65)

# ─────────────────────────────────────────────────────────────────────────────

section("1. Fetch root HTML — extract JS file references")
_, html = get("/")
html_str = html.decode(errors="replace")
print("\n--- Root HTML (first 2000 chars) ---")
print(html_str[:2000])

# Find JS/CSS src references
js_files = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html_str)
css_files = re.findall(r'href=["\']([^"\']+\.css[^"\']*)["\']', html_str)
api_refs = re.findall(r'["\'](/api/[^"\']+)["\']', html_str)
fetch_refs = re.findall(r'fetch\(["\']([^"\']+)["\']', html_str)

print(f"\nJS files found: {js_files}")
print(f"CSS files found: {css_files}")
print(f"API refs in HTML: {api_refs}")
print(f"fetch() calls: {fetch_refs}")

section("2. Fetch all linked JS files — look for API calls")
all_js_content = ""
for js in js_files:
    path = js if js.startswith("/") else "/" + js
    code, body = get(path)
    if code == 200:
        content = body.decode(errors="replace")
        all_js_content += content
        print(f"\n--- {js} (first 3000 chars) ---")
        print(content[:3000])

# Extract API endpoint patterns from JS
section("3. API patterns extracted from JS")
api_patterns = re.findall(r'["\`](/[a-zA-Z0-9_/\-]+)["\`]', all_js_content)
fetch_calls   = re.findall(r'fetch\(["\`]([^"\`]+)["\`]', all_js_content)
axios_calls   = re.findall(r'axios\.[a-z]+\(["\`]([^"\`]+)["\`]', all_js_content)
url_patterns  = re.findall(r'url\s*[:=]\s*["\`]([^"\`]+)["\`]', all_js_content, re.IGNORECASE)
post_patterns = re.findall(r'method\s*[:=]\s*["\`]POST["\`].*?url\s*[:=]\s*["\`]([^"\`]+)["\`]',
                            all_js_content, re.DOTALL | re.IGNORECASE)

paths_found = sorted(set(
    p for p in api_patterns + fetch_calls + axios_calls + url_patterns
    if p.startswith("/") and len(p) > 1
))
print("Paths referenced in JS:")
for p in paths_found:
    print(f"  {p}")
print(f"\nPOST targets: {post_patterns}")

section("4. Try every path found in JS")
for p in paths_found:
    get(p)

section("5. Common Bambu / embedded-device API patterns")
# Try with various JSON bodies that a printer control API might need
endpoints_to_try = [
    ("/api/print/start",   {"filename": "test.3mf"}),
    ("/api/print/confirm", {}),
    ("/api/print/stop",    {}),
    ("/api/printer/info",  {}),
    ("/printer/status",    {}),
    ("/api/v1/print",      {"file": "test.3mf"}),
    ("/control/print",     {"action": "start"}),
    ("/command",           {"cmd": "print_confirm"}),
    ("/api/confirm",       {"confirm": True}),
    ("/action",            {"action": "confirm"}),
]
for path, body in endpoints_to_try:
    post(path, body)

section("6. Try with form-encoded body (not JSON)")
import urllib.parse
for path in ["/api/print", "/api/confirm", "/control"]:
    url = BASE + path
    data = urllib.parse.urlencode({"action": "confirm"}).encode()
    req = urllib.request.Request(url, data=data,
          headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            print(f"FORM POST {path} → {r.status}  {r.read(100)!r}")
    except urllib.error.HTTPError as e:
        print(f"FORM POST {path} → {e.code}  {e.read(100)!r}")
    except Exception as ex:
        print(f"FORM POST {path} → ERR {ex}")

section("7. Check for WebSocket upgrade")
try:
    import socket
    s = socket.create_connection((os.getenv('PANDA_TOUCH_IP', '10.11.12.197'), 80), timeout=3)
    ws_key = "dGhlIHNhbXBsZSBub25jZQ=="
    s.sendall((
        "GET /ws HTTP/1.1\r\n"
        f"Host: {os.getenv('PANDA_TOUCH_IP', '10.11.12.197')}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode())
    resp = s.recv(512).decode(errors="replace")
    print(f"WebSocket /ws: {resp[:200]}")
    s.close()
except Exception as e:
    print(f"WebSocket probe: {e}")

print("\n" + "="*65)
print("  Probe complete — paste full output for analysis")
print("="*65)
