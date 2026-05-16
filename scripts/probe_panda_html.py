#!/usr/bin/env python3
"""Print full Panda Touch HTML and extract all inline JS + form actions."""
import os, re, urllib.request

BASE = f"http://{os.getenv('PANDA_TOUCH_IP','10.11.12.197')}"

with urllib.request.urlopen(BASE + "/", timeout=5) as r:
    html = r.read().decode(errors="replace")

print(f"=== Full HTML ({len(html)} bytes) ===\n")
print(html)

print("\n\n=== Inline <script> blocks ===")
for i, block in enumerate(re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)):
    print(f"\n--- Script block {i+1} ---")
    print(block.strip())

print("\n\n=== Form actions ===")
for m in re.findall(r'<form[^>]+>', html):
    print(m)

print("\n\n=== All string literals that look like paths ===")
paths = sorted(set(re.findall(r'["\']/([\w/\-\.]+)["\']', html)))
for p in paths:
    print(f"  /{p}")
