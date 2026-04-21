#!/usr/bin/env python3
"""
Quick standalone Bambu P1S connection test.
Run this FIRST on KJLC-AI-01 before starting the API server.

Usage:
    python3 test_bambu.py
"""
import asyncio
import sys
import time

PRINTER_IP  = "10.11.12.91"
ACCESS_CODE = "14620600"
SERIAL      = "01p00c5c0701414"

def test_import():
    print("1. Checking bambulabs-api install...")
    try:
        import bambulabs_api as bl
        print(f"   ✅ bambulabs_api imported OK (version: {getattr(bl, '__version__', 'unknown')})")
        return bl
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        print("      Fix: pip install bambulabs-api")
        sys.exit(1)

def test_connect(bl):
    print(f"\n2. Connecting to P1S at {PRINTER_IP}...")
    try:
        printer = bl.Printer(
            ip_address=PRINTER_IP,
            access_code=ACCESS_CODE,
            serial=SERIAL,
        )
        printer.connect()
        print("   ✅ printer.connect() OK — waiting up to 8s for MQTT ready...")

        for i in range(16):
            time.sleep(0.5)
            if printer.mqtt_client_ready:
                print(f"   ✅ MQTT ready after {(i+1)*0.5:.1f}s")
                break
            print(f"   ... {(i+1)*0.5:.1f}s", end="\r")
        else:
            print(f"\n   ⚠️  MQTT connected but not ready after 8s — may still work")

        # Read status fields
        try:
            state    = printer.get_current_state()
            nozzle   = printer.get_nozzle_temperature()
            bed      = printer.get_bed_temperature()
            progress = printer.get_percentage()
            print(f"   State:    {state}")
            print(f"   Nozzle:   {nozzle}°C")
            print(f"   Bed:      {bed}°C")
            print(f"   Progress: {progress}%")
        except Exception as e:
            print(f"   ⚠️  Status read error (connection still OK): {e}")

        printer.disconnect()
        return True

    except Exception as e:
        print(f"\n   ❌ Connection failed: {e}")
        print("\n   Troubleshooting:")
        print(f"   - Can you ping the printer?  ping {PRINTER_IP}")
        print("   - Is Developer Mode ON? (Settings → Network → Developer Mode)")
        print("   - Is access code correct?    Should be 8 chars from printer screen")
        return False

def test_cert():
    import os
    from pathlib import Path
    cert = Path(__file__).parent / "certs" / "printer.pem"
    print(f"\n3. Checking cert at {cert}...")
    if cert.exists():
        print(f"   ✅ printer.pem exists ({cert.stat().st_size} bytes)")
    else:
        print(f"   ⚠️  printer.pem not found (not always required, but good to have)")

if __name__ == "__main__":
    print("=" * 55)
    print("  HoloMat — Bambu P1S connection test")
    print("=" * 55)
    bl = test_import()
    test_cert()
    ok = test_connect(bl)
    print()
    print("=" * 55)
    if ok:
        print("  ✅  Bambu connectivity verified. Ready for API server.")
    else:
        print("  ❌  Connection failed — fix issues above before continuing.")
    print("=" * 55)
