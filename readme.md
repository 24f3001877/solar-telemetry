# ☀️ SolarWatch — Solar IoT Telemetry Simulator

A cloud-native full-stack application that ingests, stores, and visualizes real-time telemetry from simulated solar panel IoT devices. Built to demonstrate backend API design, relational database ORM patterns, multi-device fleet monitoring, and live frontend data visualization.

**[Live Demo →]
https://github.com/user-attachments/assets/8b26dfba-de62-4081-8d40-9286aa6b2788
** 

![Dashboard Screenshot](screenshot.png)

---

## Tech Stack

| Layer          | Technology                                      |
|----------------|-------------------------------------------------|
| Backend API    | Python · Flask · Flask-CORS                     |
| ORM & Database | SQLAlchemy · SQLite (dev) · PostgreSQL (prod)   |
| Frontend       | Bootstrap 5 · Chart.js · Vanilla JS             |
| IoT Simulator  | Python · requests · random                      |
| Deployment     | Railway · Gunicorn                              |

---

## Features

- **Live telemetry dashboard** — KPI cards and Chart.js line chart auto-refresh every 5 seconds without page reload
- **Multi-device fleet support** — run multiple simulators simultaneously; switch between panels via the device dropdown
- **Connection / disconnection detection** — dashboard detects when a device goes offline within 15 seconds and shows a live signal-lost banner; auto-recovers when reconnected
- **Temperature alert system** — banner fires when panel exceeds 70°C thermal derating threshold
- **Validated REST API** — type checks, physical plausibility bounds, and JSON error responses on every ingestion route
- **PostgreSQL-ready** — one environment variable swap from SQLite to PostgreSQL; no code changes required

---

## Project Structure

```
solar-telemetry/
├── app.py              # Flask REST API — central backend server
├── iot_device.py       # IoT simulator — pretends to be a solar panel
├── requirements.txt    # Python dependencies
├── Procfile            # Gunicorn start command for Railway / Render
├── railway.json        # Railway deployment configuration
├── README.md
└── templates/
    └── dashboard.html  # Live monitoring dashboard (served by Flask)
```

---

## Local Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/solar-telemetry.git
cd solar-telemetry

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start the Flask API

```bash
python app.py
```

Server starts at `http://127.0.0.1:5000`

### 3. Open the dashboard

Visit `http://127.0.0.1:5000` in your browser.

### 4. Start the IoT simulator (new terminal)

```bash
python iot_device.py
```

Data flows every 5 seconds. To simulate a second panel in a third terminal:

```bash
python iot_device.py --device PANEL-TX-002 --interval 3
```

### 5. Test the disconnect feature

Stop either simulator with `Ctrl+C` — the dashboard shows a red **OFFLINE** banner within 15 seconds. Restart it and it recovers automatically.

---

## API Reference

| Method | Endpoint                  | Description                                        |
|--------|---------------------------|----------------------------------------------------|
| `POST` | `/api/telemetry`          | Ingest a telemetry reading from an IoT device      |
| `GET`  | `/api/telemetry/latest`   | Fetch the last 20 readings for a device (JSON)     |
| `GET`  | `/api/devices`            | List all registered device IDs                     |
| `GET`  | `/api/devices/status`     | Per-device online/offline status with last-seen    |
| `GET`  | `/api/health`             | Liveness probe (Kubernetes / Railway compatible)   |

### POST /api/telemetry — Payload

```json
{
  "device_id":      "PANEL-TX-001",
  "voltage":        228.4,
  "temperature_c":  51.2,
  "power_output_w": 483.7,
  "irradiance_wm2": 812.0
}
```

### GET /api/devices/status — Response

```json
{
  "devices": [
    {
      "device_id":      "PANEL-TX-001",
      "last_seen":      "2024-06-19T10:50:05Z",
      "seconds_ago":    3.1,
      "online":         true,
      "total_readings": 142
    },
    {
      "device_id":      "PANEL-TX-002",
      "last_seen":      "2024-06-19T10:48:22Z",
      "seconds_ago":    103.4,
      "online":         false,
      "total_readings": 38
    }
  ],
  "threshold_seconds": 15
}
```

---

## Switching to PostgreSQL

The ORM layer is fully database-agnostic. Zero code changes required — only the connection string changes.

```bash
pip install psycopg2-binary
export DATABASE_URL="postgresql://user:password@localhost:5432/solar_db"
python app.py
```

On Railway, this environment variable is set automatically when you provision a PostgreSQL plugin.

---

## Simulator CLI Options

```bash
python iot_device.py --help

Options:
  --device    Device ID string   (default: PANEL-TX-001)
  --interval  Seconds between readings  (default: 5)
  --url       Flask API endpoint  (default: http://127.0.0.1:5000/api/telemetry)

# Examples
python iot_device.py --device PANEL-CA-002 --interval 2
python iot_device.py --url https://your-app.railway.app/api/telemetry --device PANEL-TX-001
```

---

## Architecture

```
┌─────────────────────┐     HTTP POST /api/telemetry      ┌────────────────────────────┐
│   iot_device.py     │  ──────────────────────────────►  │   Flask API  (app.py)      │
│                     │                                    │                            │
│  Simulates:         │  {"status": "ok", "id": 42}       │  • Validates JSON payload  │
│  · Irradiance       │  ◄──────────────────────────────  │  • Checks physical bounds  │
│  · Temperature      │                                    │  • Persists via SQLAlchemy │
│  · Voltage          │                                    │                            │
│  · Power output     │                                    │  SQLite (dev)              │
└─────────────────────┘                                    │  PostgreSQL (prod)         │
                                                           └──────────────┬─────────────┘
                                                                          │
                                                     GET /api/telemetry/latest
                                                     GET /api/devices/status
                                                                          │ (every 5s)
                                                                          ▼
                                                           ┌────────────────────────────┐
                                                           │   dashboard.html           │
                                                           │                            │
                                                           │  · Device selector         │
                                                           │  · KPI Cards (4 metrics)   │
                                                           │  · Chart.js live chart     │
                                                           │  · Disconnect detection    │
                                                           │  · Fleet status panel      │
                                                           └────────────────────────────┘
```

---

## License

MIT
