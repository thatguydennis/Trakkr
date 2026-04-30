"""
Trakkr — TrakkRecord™ Prediction API
Read-only API serving forecast snapshots and live station lookups.

Run:
  uvicorn api.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

from google.transit import gtfs_realtime_pb2

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

# Rate limiting — optional. If slowapi isn't installed (e.g. local dev without
# the full requirements-api.txt), the app still runs without any limits.
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    _RATE_LIMIT_AVAILABLE = True
except ImportError:
    _RATE_LIMIT_AVAILABLE = False

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_LATEST = os.path.join(BASE, "data", "artifacts", "latest", "forecast.json")
ELEV_CLEAN       = os.path.join(BASE, "data", "clean", "elevator_clean.csv")
STATION_COORDS   = os.path.join(BASE, "data", "raw", "station_coords.json")

# Mapbox public token for geocoding. Read from MAPBOX_TOKEN env var first; fall back
# to the project default (a `pk.` token is safe to commit — Mapbox treats it as public).
MAPBOX_TOKEN = os.environ.get(
    "MAPBOX_TOKEN",
    "pk.eyJ1Ijoid29ya3NieWRlbm5pcyIsImEiOiJjbW9sbGpiamEwbjNsMzFva2k5bThnNGZzIn0.5R7qckf7x-puhqGa7xlgVw",
)

# Load .env if present — no external dependency required
_env_path = os.path.join(BASE, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

MTA_API_KEY = os.environ.get("MTA_API_KEY", "")

# CORS — read allowed origins from CORS_ORIGINS env var (comma-separated).
# Defaults to local-development hosts only. Production deploys must set this
# to the live frontend origin(s), e.g. "https://www.trakkr.app".
_default_origins = "http://localhost:8765,http://127.0.0.1:8765,http://localhost:5173"
_cors_raw = os.environ.get("CORS_ORIGINS", _default_origins).strip()
if _cors_raw == "*":
    CORS_ORIGINS = ["*"]
else:
    CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app = FastAPI(title="Trakkr — TrakkRecord™ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Rate limiter. The expensive endpoint is /v1/lookup (calls paid Mapbox API);
# everything else just reads pre-published CSVs or cached MTA feeds.
if _RATE_LIMIT_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
else:
    limiter = None


def _rate_limit(rate: str):
    """Apply slowapi rate limit if installed; otherwise a no-op decorator.
    Lets the API run without slowapi in dev while still enforcing limits in prod.
    """
    def decorator(func):
        if limiter is None:
            return func
        return limiter.limit(rate)(func)
    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_latest_forecast_pointer() -> Dict[str, Any]:
    if not os.path.exists(ARTIFACTS_LATEST):
        raise HTTPException(status_code=404, detail="No forecast snapshot published yet.")
    with open(ARTIFACTS_LATEST, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_forecast_files() -> Dict[str, str]:
    """Resolve the latest run's forecast CSVs.

    The pointer's `latest_run_dir` may have been written on a different machine
    (the path is absolute). We try the recorded path first, fall back to
    rebuilding it from `latest_run_id` under this project's `data/artifacts/`.
    Either way the returned paths are absolute and verified to exist.
    """
    pointer = _read_latest_forecast_pointer()
    run_dir = pointer.get("latest_run_dir") or ""
    run_id  = pointer.get("latest_run_id")  or ""

    candidates = []
    if run_dir:
        candidates.append(run_dir)
    if run_id:
        # Rebuild against this deployment's BASE so cross-machine pointers still work
        candidates.append(os.path.join(BASE, "data", "artifacts", run_id))

    resolved_dir = next((p for p in candidates if p and os.path.isdir(p)), None)
    if not resolved_dir:
        raise HTTPException(status_code=500, detail="Forecast pointer is invalid.")

    m1 = os.path.join(resolved_dir, "forecast_model1_2027_2029.csv")
    m2 = os.path.join(resolved_dir, "forecast_model2_2027_2029.csv")
    if not os.path.exists(m1) or not os.path.exists(m2):
        raise HTTPException(status_code=500, detail="Forecast artifacts missing from latest run.")
    return {"run_dir": resolved_dir, "model1_csv": m1, "model2_csv": m2}


def _elev_norm_key(s: str) -> str:
    """Normalize an elevator station name to its base segment for fuzzy matching.
    e.g. '14ST-UNIONSQ-BWY-N/R/Q' → '14ST'
    """
    s = re.sub(r"[\s\.\-]+", "", s.upper())
    return s.split("/")[0][:12]


def _crime_norm_key(s: str) -> str:
    """Normalize a crime dataset station name the same way.
    e.g. '14 ST.-UNION SQUARE' → '14ST'
    """
    s = re.sub(r"[\s\.\-]+", "", s.upper())
    return s.split("/")[0][:12]


@lru_cache(maxsize=1)
def _load_equipment_map() -> pd.DataFrame:
    """Return deduplicated DataFrame: equipment_code, station_name, equipment_type."""
    df = pd.read_csv(ELEV_CLEAN, low_memory=False, usecols=["equipment_code", "station_name", "equipment_type"])
    df = df.dropna(subset=["equipment_code", "station_name"]).drop_duplicates(subset=["equipment_code"])
    df["station_name"] = df["station_name"].astype(str).str.strip().str.upper()
    df["norm_key"] = df["station_name"].apply(_elev_norm_key)
    return df.reset_index(drop=True)


@lru_cache(maxsize=1)
def _load_station_coords() -> List[Dict]:
    if not os.path.exists(STATION_COORDS):
        return []
    with open(STATION_COORDS, encoding="utf-8") as f:
        return json.load(f)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000  # metres
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) *
         math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _nearest_station(lat: float, lon: float) -> Dict:
    stations = _load_station_coords()
    if not stations:
        raise HTTPException(status_code=500, detail="Station coordinates not available.")
    best = min(stations, key=lambda s: _haversine(lat, lon, s["lat"], s["lon"]))
    best["distance_m"] = round(_haversine(lat, lon, best["lat"], best["lon"]))
    return best


def _geocode_address(address: str) -> Dict[str, float]:
    """Geocode a free-text address via Mapbox Geocoding API v6.

    Biased toward NYC via the proximity parameter and constrained to US results
    so partial queries don't get matched against international false positives.
    Returns {lat, lon, display_name}.
    """
    params = urllib.parse.urlencode({
        "q": address,
        "access_token": MAPBOX_TOKEN,
        "limit": "1",
        "proximity": "-74.0060,40.7128",  # Empire State Bldg — biases ranking toward NYC
        "bbox": "-74.2591,40.4774,-73.7004,40.9176",  # NYC five-borough bounding box
        "country": "us",
        "language": "en",
    })
    url = f"https://api.mapbox.com/search/geocode/v6/forward?{params}"
    # Mapbox URL-restricted tokens require a Referer that matches an allowlisted
    # origin. We send one so the backend works under the same restricted token
    # the frontend uses. Override per environment via MAPBOX_REFERER (e.g. set
    # to "https://www.trakkr.app/" in production).
    referer = os.environ.get("MAPBOX_REFERER", "http://localhost:8765/")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Trakkr/1.0 (transit safety tool)",
        "Referer":    referer,
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read())
    except Exception:
        # Don't surface upstream URLs or our access token to the client.
        raise HTTPException(status_code=502, detail="Address lookup is temporarily unavailable.")

    features = payload.get("features") or []
    if not features:
        raise HTTPException(status_code=404, detail=f"Address not found: '{address}'. Try adding a street number or neighborhood.")

    f = features[0]
    coords = (f.get("geometry") or {}).get("coordinates") or []
    if len(coords) < 2:
        raise HTTPException(status_code=502, detail="Geocoder returned malformed response.")
    lon, lat = coords[0], coords[1]
    props = f.get("properties") or {}
    display = props.get("full_address") or props.get("place_formatted") or props.get("name") or address
    return {"lat": float(lat), "lon": float(lon), "display_name": str(display)}


def _status_label(prob: float) -> Dict[str, str]:
    if prob >= 0.5:
        return {"status": "FLAG", "emoji": "🔴", "text": "TrakkRecord™ indicates elevated risk."}
    if prob >= 0.2:
        return {"status": "WATCH", "emoji": "🟡", "text": "Something's off — worth knowing."}
    return {"status": "CLEAR", "emoji": "🟢", "text": "TrakkRecord™ says you're good."}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness + readiness check.

    Liveness: the process is up.
    Readiness: forecast artifacts are resolvable.
    Returns 200 if the service can serve traffic; the body's `forecast.ready`
    flag plus `latest_run_id` give you signal for monitoring/alerting.
    """
    info: Dict[str, Any] = {
        "status":  "ok",
        "service": "trakkr-api",
        "version": app.version,
    }
    try:
        pointer = _read_latest_forecast_pointer()
        files   = _resolve_forecast_files()
        info["forecast"] = {
            "ready":       True,
            "run_id":      pointer.get("latest_run_id", ""),
            "updated_at":  pointer.get("updated_at", ""),
            "run_dir":     files["run_dir"],
        }
    except HTTPException as e:
        info["forecast"] = {"ready": False, "reason": e.detail}
    return info


@app.get("/v1/snapshots/latest")
def latest_snapshot() -> Dict[str, Any]:
    pointer = _read_latest_forecast_pointer()
    files = _resolve_forecast_files()
    return {
        "pipeline_name": pointer.get("pipeline_name", "forecast"),
        "latest_run_id": pointer.get("latest_run_id", ""),
        "latest_run_dir": files["run_dir"],
        "updated_at":     pointer.get("updated_at", ""),
    }


@app.get("/v1/stations")
def list_stations(q: Optional[str] = Query(default=None)) -> List[str]:
    """Return all station names from the crime forecast, optionally filtered by prefix."""
    files = _resolve_forecast_files()
    m2 = pd.read_csv(files["model2_csv"], usecols=["station_name"])
    names = sorted(m2["station_name"].dropna().unique().tolist())
    if q:
        q_up = q.strip().upper()
        names = [n for n in names if q_up in n]
    return names


@app.get("/v1/lookup")
@_rate_limit("30/minute")
def address_lookup(
    request: Request,
    address: str = Query(..., min_length=3, max_length=200),
) -> Dict[str, Any]:
    """Geocode an address, find the nearest subway station, return full TrakkRecord™ predictions."""
    geo = _geocode_address(address)
    nearest = _nearest_station(geo["lat"], geo["lon"])
    result = station_lookup(nearest["station_name"])
    result["address"] = {
        "query": address,
        "display_name": geo["display_name"],
        "lat": geo["lat"],
        "lon": geo["lon"],
    }
    result["nearest_station_distance_m"] = nearest["distance_m"]
    result["nearest_station_lat"] = nearest["lat"]
    result["nearest_station_lon"] = nearest["lon"]
    result["nearest_station_gtfs"] = nearest.get("gtfs_name", "")

    # Nearest 8 stations for interactive map pins
    all_coords = _load_station_coords()
    nearby_sorted = sorted(
        all_coords,
        key=lambda s: _haversine(geo["lat"], geo["lon"], s["lat"], s["lon"])
    )[:8]
    result["nearby_stations"] = [
        {
            "station_name": s["station_name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "distance_m": round(_haversine(geo["lat"], geo["lon"], s["lat"], s["lon"])),
        }
        for s in nearby_sorted
    ]
    return result


@app.get("/v1/station")
def station_lookup(name: str = Query(..., min_length=1)) -> Dict[str, Any]:
    """Return TrakkRecord™ predictions for a station — next 3 forecast months."""
    name_upper = name.strip().upper()
    # Normalize punctuation so "34 ST-PENN" matches "34 ST.-PENN STATION"
    name_norm = re.sub(r"[.\-]+", " ", name_upper).strip()
    files = _resolve_forecast_files()

    # --- Model 2: crime hotspot ---
    m2 = pd.read_csv(files["model2_csv"])
    m2["_s_norm"] = m2["station_name"].str.upper().apply(lambda s: re.sub(r"[.\-]+", " ", s).strip())
    # Word-boundary match so "42 ST" doesn't hit "242 ST"
    pattern = r"(?<!\w)" + re.escape(name_norm)
    m2_match = m2[m2["_s_norm"].str.contains(pattern, regex=True)]
    if m2_match.empty:
        # Fallback: starts-with first token
        first_token = re.escape(name_norm.split()[0])
        m2_match = m2[m2["_s_norm"].str.contains(r"(?<!\w)" + first_token, regex=True)]

    if m2_match.empty:
        raise HTTPException(status_code=404, detail=f"Station '{name}' not found in forecast data.")

    matched_name = m2_match["station_name"].iloc[0]
    borough = m2_match["borough"].iloc[0] if "borough" in m2_match.columns else "N/A"

    m2_months = (
        m2_match.sort_values("month")
        .head(3)[["month", "predicted_hotspot_prob", "predicted_hotspot_label", "confidence_bucket"]]
        .to_dict(orient="records")
    )
    avg_hotspot_prob = float(m2_match["predicted_hotspot_prob"].mean())
    safety_status = _status_label(avg_hotspot_prob)

    # --- Model 1: elevator/escalator ---
    m1 = pd.read_csv(files["model1_csv"])
    eq_map = _load_equipment_map()

    crime_key = _crime_norm_key(matched_name)
    # Use 4-char prefix — "14 STREET"→"14ST", "125 STREET"→"125S", covers abbreviation differences
    prefix = crime_key[:4]
    matched_eq = eq_map[eq_map["norm_key"].str.startswith(prefix)]

    if matched_eq.empty:
        # Fallback: raw contains on first word of the station name
        first_word = re.sub(r"[\s\-\.]+", "", name_upper.split()[0]) if name_upper.split() else name_upper
        matched_eq = eq_map[eq_map["norm_key"].str.contains(first_word[:4], regex=False)]

    equipment_out = []
    if not matched_eq.empty:
        codes = matched_eq["equipment_code"].unique()
        m1_match = m1[m1["equipment_code"].isin(codes)].sort_values("month")
        for code, grp in m1_match.groupby("equipment_code"):
            eq_row = matched_eq[matched_eq["equipment_code"] == code].iloc[0]
            first = grp.iloc[0]
            equipment_out.append({
                "equipment_code": code,
                "equipment_type": eq_row["equipment_type"],
                "severity": first.get("severity", "UNKNOWN"),
                "service_probability": round(float(first["predicted_service_prob"]), 3),
                "label": int(first["predicted_service_label"]),
                "confidence": first.get("confidence_bucket", ""),
                "forecast_months": grp.head(3)[["month", "predicted_service_prob", "severity"]].to_dict(orient="records"),
            })

    # Look up station coordinates for direct-station map view
    station_lat, station_lon = None, None
    coords_list = _load_station_coords()
    if coords_list:
        _norm = lambda s: re.sub(r"[\s\.\-]+", "", s.upper())
        target = _norm(matched_name)
        for c in coords_list:
            ckey = _norm(c["station_name"])
            if ckey == target or target[:8] in ckey or ckey[:8] in target:
                station_lat = c["lat"]
                station_lon = c["lon"]
                break

    # Nearby stations centred on this station so map pins persist on station-direct pages
    nearby_stations: List[Dict] = []
    if station_lat and station_lon and coords_list:
        nearby_sorted = sorted(
            coords_list,
            key=lambda s: _haversine(station_lat, station_lon, s["lat"], s["lon"])
        )[:8]
        nearby_stations = [
            {
                "station_name": s["station_name"],
                "lat": s["lat"],
                "lon": s["lon"],
                "distance_m": round(_haversine(station_lat, station_lon, s["lat"], s["lon"])),
            }
            for s in nearby_sorted
        ]

    return {
        "query": name,
        "matched_station": matched_name,
        "borough": borough,
        "station_lat": station_lat,
        "station_lon": station_lon,
        "lines": _station_lines(matched_name),
        "nearby_stations": nearby_stations,
        "safety": {
            **safety_status,
            "avg_hotspot_probability": round(avg_hotspot_prob, 3),
            "forecast_months": m2_months,
        },
        "equipment": equipment_out,
        "powered_by": "TrakkRecord™",
        "disclaimer": "Predictions based on historical patterns. Always use your own judgment.",
    }


@app.get("/v1/forecast/model1")
def forecast_model1(
    limit: int = Query(default=200, ge=1, le=5000),
    min_probability: float = Query(default=0.0, ge=0.0, le=1.0),
) -> List[Dict[str, Any]]:
    files = _resolve_forecast_files()
    df = pd.read_csv(files["model1_csv"])
    df = df[df["predicted_service_prob"] >= min_probability]
    return df.sort_values("predicted_service_prob", ascending=False).head(limit).to_dict(orient="records")


@app.get("/v1/forecast/model2")
def forecast_model2(
    limit: int = Query(default=200, ge=1, le=5000),
    min_probability: float = Query(default=0.0, ge=0.0, le=1.0),
) -> List[Dict[str, Any]]:
    files = _resolve_forecast_files()
    df = pd.read_csv(files["model2_csv"])
    df = df[df["predicted_hotspot_prob"] >= min_probability]
    return df.sort_values("predicted_hotspot_prob", ascending=False).head(limit).to_dict(orient="records")


@app.get("/v1/forecast/summary")
def forecast_summary() -> Dict[str, Any]:
    files = _resolve_forecast_files()
    m1 = pd.read_csv(files["model1_csv"])
    m2 = pd.read_csv(files["model2_csv"])
    return {
        "model1": {
            "rows": int(len(m1)),
            "positive_predictions": int(m1["predicted_service_label"].sum()),
            "mean_probability": round(float(m1["predicted_service_prob"].mean()), 4),
        },
        "model2": {
            "rows": int(len(m2)),
            "positive_predictions": int(m2["predicted_hotspot_label"].sum()),
            "mean_probability": round(float(m2["predicted_hotspot_prob"].mean()), 4),
        },
    }


_SKIP_LINES = {"LIRR", "METRO-NORTH", "PATH", "SIR"}   # non-subway operators


def _station_lines(station_name: str) -> List[str]:
    """Return subway lines serving a station, derived from the equipment feed."""
    try:
        root = _fetch_xml(_ENE_EQUIP_URL, _EQUIP_CACHE)
    except Exception:
        return []
    lines: set = set()
    for e in root.findall("equipment"):
        if _ene_station_match(e.findtext("station", ""), station_name):
            for tok in re.split(r"[/,\s]+", e.findtext("linesservedbyelevator", "")):
                tok = tok.strip().upper()
                if tok and tok not in _SKIP_LINES:
                    lines.add(tok)
    return sorted(lines)


_ENE_EQUIP_URL    = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fnyct_ene_equipments.xml"
_ENE_OUTAGE_URL   = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fnyct_ene.xml"
_ENE_UPCOMING_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fnyct_ene_upcoming.xml"
_ENE_TTL = 120  # seconds
_EQUIP_CACHE:    Dict[str, Any] = {}
_OUTAGE_CACHE:   Dict[str, Any] = {}
_UPCOMING_CACHE: Dict[str, Any] = {}


def _fetch_xml(url: str, cache: Dict[str, Any]) -> ET.Element:
    """Fetch, parse, and cache an XML feed for _ENE_TTL seconds."""
    now = time.time()
    if cache.get("ts", 0) + _ENE_TTL > now:
        return cache["root"]
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            root = ET.parse(resp).getroot()
    except Exception:
        # Don't expose internal MTA URLs in error messages
        raise HTTPException(status_code=502, detail="MTA equipment feed is temporarily unavailable.")
    cache["ts"] = now
    cache["root"] = root
    return root


def _ene_station_match(station_field: str, query: str) -> bool:
    """True if the first meaningful token (>=3 chars) of query appears as a whole word in station_field."""
    def tok(s: str) -> List[str]:
        return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()
    u_toks = tok(station_field)
    q_toks = tok(query)
    meaningful = [t for t in q_toks if len(t) >= 3]
    return bool(meaningful) and meaningful[0] in u_toks


def _parse_mta_dt(s: str, time_only: bool = False) -> Optional[str]:
    """Parse MTA datetime MM/DD/YYYY HH:MM:SS AM/PM.
    Returns ISO datetime string; if time_only=True returns just 'h:mm AM/PM'."""
    if not s:
        return None
    try:
        dt = datetime.strptime(s.strip(), "%m/%d/%Y %I:%M:%S %p")
        if time_only:
            return dt.strftime("%-I:%M %p")
        return dt.isoformat()          # e.g. 2026-05-04T22:00:00
    except Exception:
        return s.strip()


@app.get("/v1/mta/elevator-status")
def mta_elevator_status(station: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    """Live MTA elevator/escalator status — three public feeds, no API key required."""
    equip_root    = _fetch_xml(_ENE_EQUIP_URL,    _EQUIP_CACHE)
    outage_root   = _fetch_xml(_ENE_OUTAGE_URL,   _OUTAGE_CACHE)
    upcoming_root = _fetch_xml(_ENE_UPCOMING_URL, _UPCOMING_CACHE)

    # Equipment inventory for this station
    all_equip = equip_root.findall("equipment")
    if station:
        all_equip = [e for e in all_equip if _ene_station_match(e.findtext("station", ""), station)]

    total      = len(all_equip)
    elevators  = sum(1 for e in all_equip if e.findtext("equipmenttype", "") == "EL")
    escalators = sum(1 for e in all_equip if e.findtext("equipmenttype", "") == "ES")
    equip_nos  = {e.findtext("equipmentno", "") for e in all_equip}

    # Alt-route lookup: equipmentno → altroute text
    altroute_map = {
        e.findtext("equipmentno", ""): e.findtext("alternativeroute", "").strip()
        for e in equip_root.findall("equipment")
    }

    def outage_dict(o: ET.Element, is_upcoming: bool = False) -> Dict:
        eq_no    = o.findtext("equipment", "")
        start_dt = _parse_mta_dt(o.findtext("outagedate", ""))
        end_dt   = _parse_mta_dt(o.findtext("estimatedreturntoservice", ""))
        # Compute duration in hours for upcoming windows
        duration_h = None
        if is_upcoming and start_dt and end_dt:
            try:
                s = datetime.fromisoformat(start_dt)
                e = datetime.fromisoformat(end_dt)
                duration_h = round((e - s).total_seconds() / 3600, 1)
            except Exception:
                pass
        return {
            "equipmentno":    eq_no,
            "equipmenttype":  o.findtext("equipmenttype", ""),
            "station":        o.findtext("station", ""),
            "serving":        o.findtext("serving", "").strip(),
            "lines":          o.findtext("trainno", ""),
            "ADA":            o.findtext("ADA", "N") == "Y",
            "reason":         o.findtext("reason", ""),
            "outage_start":   start_dt,
            "outage_end":     end_dt,
            "duration_h":     duration_h,
            "is_maintenance": o.findtext("ismaintenanceoutage", "N") == "Y",
            "altroute":       altroute_map.get(eq_no, ""),
        }

    # Current outages: from nyct_ene.xml (isupcomingoutage=N)
    current_outages = [
        o for o in outage_root.findall("outage")
        if o.findtext("isupcomingoutage", "N") == "N"
    ]
    # Upcoming outages: from dedicated nyct_ene_upcoming.xml
    upcoming_outages = upcoming_root.findall("outage")

    if station:
        station_outages  = [outage_dict(o, False) for o in current_outages  if o.findtext("equipment", "") in equip_nos]
        station_upcoming = [outage_dict(o, True)  for o in upcoming_outages if o.findtext("equipment", "") in equip_nos]
    else:
        station_outages  = [outage_dict(o, False) for o in current_outages]
        station_upcoming = [outage_dict(o, True)  for o in upcoming_outages]

    # Sort upcoming by start time
    station_upcoming.sort(key=lambda x: x.get("outage_start") or "")

    down  = len(station_outages)
    active = max(total - down, 0)

    ada_outages = [o for o in station_outages if o["ADA"]]
    ada_ok = total > 0 and len(ada_outages) == 0

    return {
        "configured":     True,
        "station_query":  station,
        "total_units":    total,
        "active":         active,
        "down":           down,
        "elevators":      elevators,
        "escalators":     escalators,
        "ada_accessible": ada_ok,
        "outages":        station_outages,
        "upcoming":       station_upcoming,
    }


_SUBWAY_ALERTS_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts"
_ALERTS_CACHE: Dict[str, Any] = {}
_ALERTS_TTL = 60  # seconds — alerts change frequently

# All canonical NYC subway lines in display order
_ALL_LINES = ["1","2","3","4","5","6","7","A","C","E","B","D","F","M","G","J","Z","L","N","Q","R","W","SI","GS","H"]
_LINE_COLOR = {
    "1":"#EE352E","2":"#EE352E","3":"#EE352E",
    "4":"#00933C","5":"#00933C","6":"#00933C",
    "7":"#B933AD",
    "A":"#0039A6","C":"#0039A6","E":"#0039A6",
    "B":"#FF6319","D":"#FF6319","F":"#FF6319","M":"#FF6319",
    "G":"#6CBE45",
    "J":"#996633","Z":"#996633",
    "L":"#A7A9AC",
    "N":"#FCCC0A","Q":"#FCCC0A","R":"#FCCC0A","W":"#FCCC0A",
    "SI":"#0039A6","GS":"#808183","H":"#808183",
}


def _classify_alert(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["suspended", "no service", "no train", "not running", "not stopping"]):
        return "NO_SERVICE"
    if any(w in t for w in ["delay", "delayed", "running with delay"]):
        return "DELAYS"
    if any(w in t for w in ["skip", "bypass", "reroute", "different route", "express", "local stop",
                             "alternate", "modified", "change", "replaced", "shuttle"]):
        return "SERVICE_CHANGE"
    if any(w in t for w in ["resumed", "restored", "back on", "returning"]):
        return "GOOD_SERVICE"
    return "PLANNED_WORK"


_STATUS_PRIORITY = {"NO_SERVICE": 5, "DELAYS": 4, "SERVICE_CHANGE": 3, "PLANNED_WORK": 2, "GOOD_SERVICE": 1}


def _fetch_subway_alerts() -> gtfs_realtime_pb2.FeedMessage:
    now = time.time()
    if _ALERTS_CACHE.get("ts", 0) + _ALERTS_TTL > now:
        return _ALERTS_CACHE["feed"]
    try:
        with urllib.request.urlopen(_SUBWAY_ALERTS_URL, timeout=10) as resp:
            data = resp.read()
    except Exception:
        raise HTTPException(status_code=502, detail="MTA alerts feed is temporarily unavailable.")
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    _ALERTS_CACHE["ts"] = now
    _ALERTS_CACHE["feed"] = feed
    return feed


@app.get("/v1/mta/line-status")
def mta_line_status(lines: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    """Live NYC subway line status — all lines or filtered by comma-separated list."""
    feed = _fetch_subway_alerts()
    filter_lines = {l.strip().upper() for l in lines.split(",")} if lines else set()

    # Aggregate alerts per route
    route_alerts: Dict[str, List[Dict]] = {}
    for entity in feed.entity:
        a = entity.alert
        header = next((t.text for t in a.header_text.translation if t.language == "en"), "")
        if not header:
            continue
        desc = next((t.text for t in a.description_text.translation if t.language == "en"), "")
        status = _classify_alert(header)
        routes = list({ie.route_id for ie in a.informed_entity if ie.route_id})
        for r in routes:
            if filter_lines and r not in filter_lines:
                continue
            route_alerts.setdefault(r, []).append({
                "status":  status,
                "header":  header,
                "description": desc,
            })

    # Build per-line summary
    target_lines = filter_lines if filter_lines else set(_ALL_LINES)
    line_status = {}
    for line in _ALL_LINES:
        if line not in target_lines:
            continue
        alerts = route_alerts.get(line, [])
        if not alerts:
            worst = "GOOD_SERVICE"
            top   = "Good service"
        else:
            worst_alert = max(alerts, key=lambda x: _STATUS_PRIORITY.get(x["status"], 0))
            worst = worst_alert["status"]
            top   = worst_alert["header"]
        line_status[line] = {
            "line":        line,
            "color":       _LINE_COLOR.get(line, "#808183"),
            "status":      worst,
            "alert_count": len(alerts),
            "top_alert":   top,
            "alerts":      alerts,
        }

    return {
        "timestamp": int(feed.header.timestamp),
        "lines": line_status,
        "summary": {
            "NO_SERVICE":     sum(1 for v in line_status.values() if v["status"] == "NO_SERVICE"),
            "DELAYS":         sum(1 for v in line_status.values() if v["status"] == "DELAYS"),
            "SERVICE_CHANGE": sum(1 for v in line_status.values() if v["status"] == "SERVICE_CHANGE"),
            "PLANNED_WORK":   sum(1 for v in line_status.values() if v["status"] == "PLANNED_WORK"),
            "GOOD_SERVICE":   sum(1 for v in line_status.values() if v["status"] == "GOOD_SERVICE"),
        }
    }


@app.get("/v1/mta/service-alerts")
def mta_service_alerts(line: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    """Live MTA subway service alerts — all or filtered by line."""
    feed = _fetch_subway_alerts()
    filter_line = line.upper() if line else None
    alerts = []
    for entity in feed.entity:
        a = entity.alert
        header = next((t.text for t in a.header_text.translation if t.language == "en"), "")
        desc   = next((t.text for t in a.description_text.translation if t.language == "en"), "")
        routes = list({ie.route_id for ie in a.informed_entity if ie.route_id})
        if not header:
            continue
        if filter_line and filter_line not in routes:
            continue
        alerts.append({"header": header, "description": desc, "routes": routes, "status": _classify_alert(header)})
    return {"configured": True, "total": len(alerts), "alerts": alerts}
