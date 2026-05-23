"""
Weather Station Web UI Dashboard
Minimal Flask app for visualizing weather data from SQLite database.
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, render_template, jsonify, request

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "weather.db"
DB_PATH = Path(os.getenv("WEATHER_DB_PATH", str(DEFAULT_DB_PATH)))
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

# Valid time ranges and their durations
VALID_RANGES = {
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
}
# Valid record-count ranges (for "last n values" option)
VALID_LIMITS = {
    "10": 10,
    "50": 50,
    "100": 100,
    "500": 500,
}
# Valid metrics mapped to their exact DB column names
VALID_METRICS = {"temperature", "humidity", "windspeed"}
_METRIC_COLUMN = {
    "temperature": "temperature",
    "humidity": "humidity",
    "windspeed": "windspeed",
}

app = Flask(__name__, template_folder="templates", static_folder="static")


def get_db():
    """Get database connection with optimized settings."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def parse_timestamp(ts):
    """Parse ISO 8601 timestamp to an aware UTC datetime."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (ValueError, TypeError):
            return None


def utc_cutoff(duration):
    """Return an aware UTC cutoff timestamp for a dashboard time window."""
    return datetime.now(timezone.utc) - duration


@app.route("/")
def index():
    """Serve main dashboard."""
    return render_template("index.html")


@app.route("/api/stations", methods=["GET"])
def api_stations():
    """Get list of unique station IDs."""
    try:
        conn = get_db()
        cursor = conn.execute(
            "SELECT DISTINCT station_id FROM readings ORDER BY station_id"
        )
        stations = [row[0] for row in cursor.fetchall()]
        conn.close()
        logger.info(f"Fetched {len(stations)} stations")
        return jsonify({"stations": stations})
    except Exception as e:
        logger.error(f"Error fetching stations: {e}")
        return jsonify({"stations": []})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """
    Get statistics for a given station, metric, and time range.
    Query params:
      - station_id (required)
      - metric (required): temperature, humidity, or windspeed
      - range (optional): 6h, 24h (time-based) or limit param for record-based
      - limit (optional): 10, 50, 100, 500 (for last n values)
    
    Returns:
      {"latest": 23.5, "latest_t": "2025-12-25T12:00:00", "avg": 22.1, "min": 20.0, "max": 25.5}
    """
    station_id = request.args.get("station_id", "").strip()
    metric = request.args.get("metric", "").strip()
    time_range = request.args.get("range", "24h").strip()
    limit = request.args.get("limit", "").strip()

    # Validation
    if not station_id or metric not in VALID_METRICS:
        return (
            jsonify(
                {
                    "error": "Invalid parameters",
                    "latest": None,
                    "latest_t": None,
                    "avg": None,
                    "min": None,
                    "max": None,
                }
            ),
            400,
        )

    # Determine if we're using time-based or record-based filtering
    use_limit = limit and limit in VALID_LIMITS
    if not use_limit and time_range not in VALID_RANGES:
        return (
            jsonify(
                {
                    "error": "Invalid range or limit",
                    "latest": None,
                    "latest_t": None,
                    "avg": None,
                    "min": None,
                    "max": None,
                }
            ),
            400,
        )

    # Calculate time window (if time-based)
    cutoff = utc_cutoff(VALID_RANGES[time_range]) if not use_limit else None

    try:
        conn = get_db()
        db_metric = _METRIC_COLUMN[metric]

        if use_limit:
            cursor = conn.execute(
                "SELECT timestamp, " + db_metric + " AS value "
                "FROM readings WHERE station_id = ? AND " + db_metric + " IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (station_id, VALID_LIMITS[limit]),
            )
        else:
            cursor = conn.execute(
                "SELECT timestamp, " + db_metric + " AS value "
                "FROM readings WHERE station_id = ? AND timestamp >= ? AND " + db_metric + " IS NOT NULL "
                "ORDER BY timestamp DESC",
                (station_id, cutoff.isoformat()),
            )

        rows = cursor.fetchall()
        conn.close()

        # Filter by time range or limit, and ignore nulls
        values = []
        latest = None
        latest_t = None

        for row in rows:
            dt = parse_timestamp(row["timestamp"])
            if not dt or (not use_limit and dt < cutoff):
                continue

            val = row["value"]
            values.append(val)
            if latest is None:
                latest = val
                latest_t = row["timestamp"]

        # Calculate stats
        if values:
            result = {
                "latest": round(latest, 2),
                "latest_t": latest_t,
                "avg": round(sum(values) / len(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
            }
        else:
            result = {
                "latest": None,
                "latest_t": None,
                "avg": None,
                "min": None,
                "max": None,
            }

        range_label = f"limit={limit}" if use_limit else f"range={time_range}"
        logger.info(f"Stats for {station_id}/{metric}/{range_label}: {len(values)} points")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify(
            {
                "latest": None,
                "latest_t": None,
                "avg": None,
                "min": None,
                "max": None,
            }
        )


@app.route("/api/readings", methods=["GET"])
def api_readings():
    """
    Get time series data for a given station, metric, and time range.
    Query params:
      - station_id (required)
      - metric (required): temperature, humidity, or windspeed
      - range (optional): 6h, 24h (time-based) or limit param for record-based
      - limit (optional): 10, 50, 100, 500 (for last n values)
    
    Returns:
      {"points": [{"t": "2025-12-25T10:00:00", "v": 23.1}, ...]}
      (ordered oldest -> newest for Chart.js)
    """
    station_id = request.args.get("station_id", "").strip()
    metric = request.args.get("metric", "").strip()
    time_range = request.args.get("range", "24h").strip()
    limit = request.args.get("limit", "").strip()

    # Validation
    if not station_id or metric not in VALID_METRICS:
        return jsonify({"error": "Invalid parameters", "points": []}), 400

    # Determine if we're using time-based or record-based filtering
    use_limit = limit and limit in VALID_LIMITS
    if not use_limit and time_range not in VALID_RANGES:
        return jsonify({"error": "Invalid range or limit", "points": []}), 400

    # Calculate time window (if time-based)
    cutoff = utc_cutoff(VALID_RANGES[time_range]) if not use_limit else None

    try:
        conn = get_db()
        db_metric = _METRIC_COLUMN[metric]

        if use_limit:
            # Fetch newest N rows DESC, then reverse to display oldest→newest in chart
            cursor = conn.execute(
                "SELECT timestamp, " + db_metric + " FROM readings "
                "WHERE station_id = ? AND " + db_metric + " IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (station_id, VALID_LIMITS[limit]),
            )
            rows = list(reversed(cursor.fetchall()))
            conn.close()
            points = [
                {"t": row["timestamp"], "v": row[db_metric]}
                for row in rows
            ]
        else:
            cursor = conn.execute(
                "SELECT timestamp, " + db_metric + " FROM readings "
                "WHERE station_id = ? AND timestamp >= ? AND " + db_metric + " IS NOT NULL "
                "ORDER BY timestamp ASC",
                (station_id, cutoff.isoformat()),
            )
            rows = cursor.fetchall()
            conn.close()
            points = []
            for row in rows:
                dt = parse_timestamp(row["timestamp"])
                if not dt or dt < cutoff:
                    continue
                val = row[db_metric]
                if val is not None:
                    points.append({"t": row["timestamp"], "v": val})

        range_label = f"limit={limit}" if use_limit else f"range={time_range}"
        logger.info(f"Readings for {station_id}/{metric}/{range_label}: {len(points)} points")
        return jsonify({"points": points})

    except Exception as e:
        logger.error(f"Error fetching readings: {e}")
        return jsonify({"points": []})


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Weather Station Web UI Dashboard")
    logger.info("=" * 60)
    logger.info(f"Database: {DB_PATH}")
    logger.info(f"Database exists: {DB_PATH.exists()}")
    logger.info(f"Server: http://{WEB_HOST}:{WEB_PORT}")
    logger.info("=" * 60)

    if not DB_PATH.exists():
        logger.warning(f"Database not found: {DB_PATH}")
        logger.warning("Dashboard will start but show no data until server populates the DB.")

    app.run(host=WEB_HOST, port=WEB_PORT, debug=False, use_reloader=False)
