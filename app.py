"""
Solar IoT Telemetry Simulator — Flask REST API
app.py

Architecture note: SQLite is used for local dev.
To switch to PostgreSQL, change DATABASE_URL in config and
install psycopg2: `pip install psycopg2-binary`
"""

import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, abort
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text

# ─────────────────────────────────────────────
# App & Config
# ─────────────────────────────────────────────
app = Flask(__name__)
CORS(app)  # Allow the dashboard JS to hit the API from any origin (dev convenience)

# ── Database config ───────────────────────────
# Switch to PostgreSQL by setting DATABASE_URL env var:
#   export DATABASE_URL="postgresql://user:pass@localhost:5432/solar_db"
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///solar_telemetry.db")
# Railway provides postgres:// but SQLAlchemy 2.x only accepts postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ─────────────────────────────────────────────
# Model — maps directly to a DB table
# ─────────────────────────────────────────────
class SolarTelemetry(db.Model):
    """
    One row per telemetry reading from a solar panel device.

    PostgreSQL-ready: all column types (Integer, String, DateTime, Float)
    are supported identically by psycopg2. Only the connection string
    needs to change — the schema and ORM code stay identical.
    """
    __tablename__ = "solar_telemetry"

    id             = db.Column(db.Integer,     primary_key=True)
    device_id      = db.Column(db.String(50),  nullable=False, index=True)  # e.g. 'PANEL-TX-001'
    timestamp      = db.Column(db.DateTime,    nullable=False, default=lambda: datetime.now(timezone.utc))
    voltage        = db.Column(db.Float,       nullable=False)   # Volts
    temperature_c  = db.Column(db.Float,       nullable=False)   # °C
    power_output_w = db.Column(db.Float,       nullable=False)   # Watts
    irradiance_wm2 = db.Column(db.Float,       nullable=True)    # W/m² (optional sensor)

    def to_dict(self):
        """Serialize to JSON-safe dict. Used by API endpoints."""
        return {
            "id":              self.id,
            "device_id":       self.device_id,
            "timestamp":       self.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "voltage":         round(self.voltage, 2),
            "temperature_c":   round(self.temperature_c, 2),
            "power_output_w":  round(self.power_output_w, 2),
            "irradiance_wm2":  round(self.irradiance_wm2, 2) if self.irradiance_wm2 else None,
        }


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Serve the live monitoring dashboard."""
    return render_template("dashboard.html")


@app.post("/api/telemetry")
def ingest_telemetry():
    """
    POST /api/telemetry
    Receives a JSON payload from the IoT simulator and persists it.

    Expected payload:
    {
        "device_id":      "PANEL-TX-001",
        "voltage":        220.5,
        "temperature_c":  46.3,
        "power_output_w": 510.0,
        "irradiance_wm2": 850.0   # optional
    }
    """
    data = request.get_json(silent=True)

    # ── Input validation ─────────────────────
    if not data:
        abort(400, description="Request body must be valid JSON.")

    required_fields = ["device_id", "voltage", "temperature_c", "power_output_w"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        abort(400, description=f"Missing required fields: {', '.join(missing)}")

    # Type checks — reject strings masquerading as numbers
    numeric_fields = ["voltage", "temperature_c", "power_output_w"]
    for field in numeric_fields:
        if not isinstance(data[field], (int, float)):
            abort(422, description=f"Field '{field}' must be a number, got: {type(data[field]).__name__}")

    # Sanity bounds (physical plausibility)
    if not (-40 <= data["temperature_c"] <= 120):
        abort(422, description="temperature_c out of physical range (-40 to 120 °C).")
    if not (0 <= data["voltage"] <= 1500):
        abort(422, description="voltage out of range (0 – 1500 V).")
    if not (0 <= data["power_output_w"] <= 100_000):
        abort(422, description="power_output_w out of range (0 – 100,000 W).")

    # ── Persist ──────────────────────────────
    reading = SolarTelemetry(
        device_id      = str(data["device_id"])[:50],
        voltage        = float(data["voltage"]),
        temperature_c  = float(data["temperature_c"]),
        power_output_w = float(data["power_output_w"]),
        irradiance_wm2 = float(data["irradiance_wm2"]) if "irradiance_wm2" in data else None,
    )
    db.session.add(reading)
    db.session.commit()

    return jsonify({"status": "ok", "id": reading.id}), 201


@app.get("/api/telemetry/latest")
def get_latest():
    """
    GET /api/telemetry/latest?limit=20&device_id=PANEL-TX-001
    Returns the most recent N readings (default 20) for a given device.
    The dashboard JS polls this every 5 seconds to redraw the chart.
    """
    limit     = min(int(request.args.get("limit", 20)), 100)   # cap at 100
    device_id = request.args.get("device_id", "PANEL-TX-001")

    readings = (
        SolarTelemetry.query
        .filter_by(device_id=device_id)
        .order_by(SolarTelemetry.timestamp.desc())
        .limit(limit)
        .all()
    )

    # Reverse so data is chronological (oldest → newest) for Chart.js
    readings.reverse()

    return jsonify({
        "device_id": device_id,
        "count":     len(readings),
        "data":      [r.to_dict() for r in readings],
    })


@app.get("/api/devices")
def list_devices():
    """
    GET /api/devices
    Returns all unique device IDs that have sent telemetry.
    """
    rows = db.session.execute(
        text("SELECT DISTINCT device_id FROM solar_telemetry ORDER BY device_id")
    ).fetchall()
    return jsonify({"devices": [r[0] for r in rows]})


@app.get("/api/devices/status")
def devices_status():
    """
    GET /api/devices/status
    Returns every known device with its last-seen timestamp and online/offline status.

    A device is ONLINE  if it sent data within the last OFFLINE_THRESHOLD_SECONDS.
    A device is OFFLINE if no data has been received within that window.

    The dashboard polls this every 5 seconds to drive the connection indicator.
    Threshold is 15s — that's 3 missed readings at the default 5s interval.
    """
    from sqlalchemy import func

    OFFLINE_THRESHOLD_SECONDS = 15

    # One query: latest timestamp per device
    rows = (
        db.session.query(
            SolarTelemetry.device_id,
            func.max(SolarTelemetry.timestamp).label("last_seen"),
            func.count(SolarTelemetry.id).label("total_readings"),
        )
        .group_by(SolarTelemetry.device_id)
        .all()
    )

    now = datetime.now(timezone.utc)
    result = []

    for row in rows:
        last_seen = row.last_seen
        # SQLite stores naive datetimes — treat them as UTC
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        seconds_ago = (now - last_seen).total_seconds()
        online      = seconds_ago <= OFFLINE_THRESHOLD_SECONDS

        result.append({
            "device_id":      row.device_id,
            "last_seen":      last_seen.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seconds_ago":    round(seconds_ago, 1),
            "online":         online,
            "total_readings": row.total_readings,
        })

    return jsonify({"devices": result, "threshold_seconds": OFFLINE_THRESHOLD_SECONDS})


@app.get("/api/health")
def health_check():
    """GET /api/health — Kubernetes/load-balancer liveness probe."""
    return jsonify({"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()})


# ─────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────
@app.errorhandler(400)
@app.errorhandler(422)
def handle_bad_request(e):
    return jsonify({"error": e.description}), e.code

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found."}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error."}), 500


# ─────────────────────────────────────────────
# Database Initialisation
# Runs on import — works with both `python app.py` AND gunicorn.
# ─────────────────────────────────────────────
with app.app_context():
    db.create_all()

# ─────────────────────────────────────────────
# Entry Point (local dev only)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("✅  Database tables ready.")
    print("🚀  Server starting at http://127.0.0.1:5000")
    app.run(debug=True, port=5000)