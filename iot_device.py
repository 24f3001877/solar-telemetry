"""
Solar IoT Telemetry Simulator — Device Script
iot_device.py

Simulates a solar panel (PANEL-TX-001) located in Austin, Texas.
Generates physically realistic readings and posts them to the Flask API
every 5 seconds, mimicking a real MQTT/HTTP IoT edge device.

Usage:
    python iot_device.py
    python iot_device.py --interval 2 --device PANEL-TX-002
"""

import argparse
import random
import sys
import time
from datetime import datetime

import requests

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
DEFAULT_API_URL  = "http://127.0.0.1:5000/api/telemetry"
DEFAULT_DEVICE   = "PANEL-TX-001"
DEFAULT_INTERVAL = 5   # seconds between readings


# ─────────────────────────────────────────────
# Realistic Solar Data Generation
# ─────────────────────────────────────────────
# Panel specs modelled after a 600W monocrystalline residential panel
PANEL_RATED_POWER_W   = 600.0
PANEL_RATED_VOLTAGE_V = 240.0

# Simulate gradual drift so readings don't look random — they follow
# a slow sinusoidal "time of day" curve perturbed by noise.
_step = 0  # increments each reading


def get_irradiance() -> float:
    """
    Simulate solar irradiance (W/m²).
    - Peak irradiance: ~1000 W/m² at solar noon
    - We model a gentle sine wave + gaussian noise to mimic cloud cover
    """
    global _step
    base = 700 + 250 * abs((((_step * 5) % 3600) / 3600) - 0.5)   # 0-1000 range
    noise = random.gauss(0, 40)
    return round(max(0, min(1050, base + noise)), 2)


def generate_reading(device_id: str) -> dict:
    """
    Generate one telemetry payload from simulated sensor readings.
    Values are physically coupled:
      - Higher irradiance → higher power output
      - Higher irradiance → higher panel temperature
      - Higher temperature → slight voltage drop (silicon physics)
    """
    global _step
    _step += 1

    irradiance = get_irradiance()

    # Temperature: ambient (Austin, TX ~32°C) + panel heating from irradiance
    ambient_temp   = 32.0 + random.uniform(-3, 3)
    panel_temp     = ambient_temp + (irradiance / 1000) * 35 + random.gauss(0, 1.5)
    temperature_c  = round(max(15.0, min(90.0, panel_temp)), 2)

    # Voltage drops ~0.35%/°C above 25°C STC (standard test conditions)
    temp_delta     = temperature_c - 25.0
    voltage_drop   = PANEL_RATED_VOLTAGE_V * 0.0035 * temp_delta
    voltage        = round(max(0, PANEL_RATED_VOLTAGE_V - voltage_drop + random.gauss(0, 2)), 2)

    # Power output: efficiency proportional to irradiance, derated by temp
    efficiency     = irradiance / 1000.0
    temp_derating  = max(0, 1 - 0.004 * max(0, temperature_c - 25))  # -0.4%/°C above 25°C
    power_output_w = round(PANEL_RATED_POWER_W * efficiency * temp_derating + random.gauss(0, 8), 2)
    power_output_w = max(0, power_output_w)

    return {
        "device_id":      device_id,
        "voltage":        voltage,
        "temperature_c":  temperature_c,
        "power_output_w": power_output_w,
        "irradiance_wm2": irradiance,
    }


# ─────────────────────────────────────────────
# Transmission Loop
# ─────────────────────────────────────────────
def run(api_url: str, device_id: str, interval: int):
    print("─" * 55)
    print(f"  ☀  Solar IoT Simulator — {device_id}")
    print(f"  📡  Target: {api_url}")
    print(f"  ⏱   Interval: {interval}s  |  Press Ctrl+C to stop")
    print("─" * 55)

    session = requests.Session()   # reuse TCP connection for efficiency

    while True:
        payload = generate_reading(device_id)
        ts = datetime.now().strftime("%H:%M:%S")

        try:
            resp = session.post(api_url, json=payload, timeout=5)
            resp.raise_for_status()
            print(
                f"[{ts}] ✅  Sent  |  "
                f"V={payload['voltage']:>6.1f}V  "
                f"T={payload['temperature_c']:>5.1f}°C  "
                f"P={payload['power_output_w']:>6.1f}W  "
                f"☀={payload['irradiance_wm2']:>6.1f} W/m²  "
                f"→ HTTP {resp.status_code}"
            )
        except requests.exceptions.ConnectionError:
            print(f"[{ts}] ❌  Connection refused — is the Flask server running?")
        except requests.exceptions.Timeout:
            print(f"[{ts}] ⚠️   Request timed out — server slow or overloaded.")
        except requests.exceptions.HTTPError as e:
            print(f"[{ts}] ⚠️   Server error: {e.response.status_code} — {e.response.text[:80]}")
        except Exception as e:
            print(f"[{ts}] ⚠️   Unexpected error: {e}")

        time.sleep(interval)


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Solar Panel IoT Simulator")
    parser.add_argument("--url",      default=DEFAULT_API_URL,  help="Flask API endpoint")
    parser.add_argument("--device",   default=DEFAULT_DEVICE,   help="Device ID string")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, type=int, help="Seconds between readings")
    args = parser.parse_args()

    try:
        run(args.url, args.device, args.interval)
    except KeyboardInterrupt:
        print("\n\n  Simulator stopped. 👋")
        sys.exit(0)
