import httpx
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .database import AQIReading, SessionLocal

logger = logging.getLogger(__name__)

CITIES = {
    "Delhi":      {"lat": 28.6139, "lon": 77.2090},
    "Mumbai":     {"lat": 19.0760, "lon": 72.8777},
    "Hyderabad":  {"lat": 17.3850, "lon": 78.4867},
    "Chennai":    {"lat": 13.0827, "lon": 80.2707},
    "Bangalore":  {"lat": 12.9716, "lon": 77.5946},
    "Kolkata":    {"lat": 22.5726, "lon": 88.3639},
    "Pune":       {"lat": 18.5204, "lon": 73.8567},
    "Ahmedabad":  {"lat": 23.0225, "lon": 72.5714},
    "Jaipur":     {"lat": 26.9124, "lon": 75.7873},
    "Nellore":    {"lat": 14.4426, "lon": 79.9865},
}

OPENAQ_BASE = "https://api.openaq.org/v3"
METEO_BASE = "https://api.open-meteo.com/v1"
AIRQ_BASE = "https://air-quality-api.open-meteo.com/v1"

# India AQI breakpoints for PM2.5 (µg/m³) → AQI
PM25_BREAKPOINTS = [
    (0, 30, 0, 50),
    (30, 60, 51, 100),
    (60, 90, 101, 200),
    (90, 120, 201, 300),
    (120, 250, 301, 400),
    (250, 500, 401, 500),
]


def pm25_to_aqi(pm25: float) -> float:
    if pd.isna(pm25) or pm25 < 0:
        return np.nan
    for c_lo, c_hi, i_lo, i_hi in PM25_BREAKPOINTS:
        if c_lo <= pm25 <= c_hi:
            return round(((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo, 1)
    return 500.0


async def fetch_openaq_locations(city: str, lat: float, lon: float, client: httpx.AsyncClient) -> list[int]:
    """Return sensor location IDs near a city centre (radius 25 km)."""
    try:
        r = await client.get(
            f"{OPENAQ_BASE}/locations",
            params={"coordinates": f"{lat},{lon}", "radius": 25000, "country_id": "IN", "limit": 20},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return [loc["id"] for loc in data.get("results", [])]
    except Exception as e:
        logger.warning(f"OpenAQ location fetch failed for {city}: {e}")
        return []


async def fetch_openaq_measurements(location_ids: list[int], city: str, hours: int, client: httpx.AsyncClient) -> pd.DataFrame:
    """Fetch PM2.5, PM10, NO2, O3, CO, SO2 for the last `hours` hours."""
    if not location_ids:
        return pd.DataFrame()

    date_from = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params_map = {"pm25": "pm25", "pm10": "pm10", "no2": "no2", "o3": "o3", "co": "co", "so2": "so2"}
    records: dict[str, dict] = {}  # keyed by rounded hour

    for loc_id in location_ids[:5]:
        for param_key in params_map:
            try:
                r = await client.get(
                    f"{OPENAQ_BASE}/locations/{loc_id}/measurements",
                    params={"parameter": param_key, "date_from": date_from, "limit": 500},
                    timeout=15,
                )
                if r.status_code != 200:
                    continue
                for m in r.json().get("results", []):
                    ts_str = m.get("period", {}).get("datetimeTo", {}).get("utc") or m.get("date", {}).get("utc", "")
                    if not ts_str:
                        continue
                    ts = pd.to_datetime(ts_str, utc=True).floor("h")
                    key = ts.isoformat()
                    if key not in records:
                        records[key] = {"timestamp": ts, "city": city}
                    val = m.get("value")
                    if val is not None and val >= 0:
                        existing = records[key].get(param_key)
                        records[key][param_key] = val if existing is None else (existing + val) / 2
            except Exception:
                continue

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(list(records.values()))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


async def fetch_weather(city: str, lat: float, lon: float, hours: int, client: httpx.AsyncClient) -> pd.DataFrame:
    """Fetch hourly weather from Open-Meteo (past_days covers historical hours)."""
    past_days = max(1, min(92, (hours // 24) + 1))
    try:
        r = await client.get(
            f"{METEO_BASE}/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                "past_days": past_days,
                "forecast_days": 1,
                "timezone": "UTC",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(hourly.get("time", []), utc=True),
            "temperature": hourly.get("temperature_2m", []),
            "humidity": hourly.get("relative_humidity_2m", []),
            "wind_speed": hourly.get("wind_speed_10m", []),
        })
        df["city"] = city
        return df
    except Exception as e:
        logger.warning(f"Open-Meteo fetch failed for {city}: {e}")
        return pd.DataFrame()


async def fetch_weather_forecast(city: str, lat: float, lon: float, client: httpx.AsyncClient) -> pd.DataFrame:
    """Fetch 48-hour weather forecast from Open-Meteo."""
    try:
        r = await client.get(
            f"{METEO_BASE}/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                "timezone": "UTC",
                "forecast_days": 3,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(hourly.get("time", []), utc=True),
            "temperature": hourly.get("temperature_2m", []),
            "humidity": hourly.get("relative_humidity_2m", []),
            "wind_speed": hourly.get("wind_speed_10m", []),
        })
        return df.iloc[:48].reset_index(drop=True)
    except Exception as e:
        logger.warning(f"Weather forecast fetch failed for {city}: {e}")
        return pd.DataFrame()


def merge_aqi_weather(aqi_df: pd.DataFrame, weather_df: pd.DataFrame) -> pd.DataFrame:
    if aqi_df.empty and weather_df.empty:
        return pd.DataFrame()
    if aqi_df.empty:
        return weather_df
    if weather_df.empty:
        return aqi_df
    merged = pd.merge_asof(
        aqi_df.sort_values("timestamp"),
        weather_df.sort_values("timestamp").drop(columns=["city"], errors="ignore"),
        on="timestamp",
        tolerance=pd.Timedelta("1h"),
        direction="nearest",
    )
    if "pm25" in merged.columns:
        merged["aqi"] = merged["pm25"].apply(pm25_to_aqi)
    return merged


def upsert_readings(db: Session, df: pd.DataFrame):
    if df.empty:
        return
    for _, row in df.iterrows():
        record = {
            "city": row.get("city"),
            "timestamp": row.get("timestamp").replace(tzinfo=None) if pd.notna(row.get("timestamp")) else None,
            "pm25": float(row["pm25"]) if "pm25" in row and pd.notna(row["pm25"]) else None,
            "pm10": float(row["pm10"]) if "pm10" in row and pd.notna(row["pm10"]) else None,
            "no2": float(row["no2"]) if "no2" in row and pd.notna(row["no2"]) else None,
            "o3": float(row["o3"]) if "o3" in row and pd.notna(row["o3"]) else None,
            "co": float(row["co"]) if "co" in row and pd.notna(row["co"]) else None,
            "so2": float(row["so2"]) if "so2" in row and pd.notna(row["so2"]) else None,
            "aqi": float(row["aqi"]) if "aqi" in row and pd.notna(row["aqi"]) else None,
            "temperature": float(row["temperature"]) if "temperature" in row and pd.notna(row["temperature"]) else None,
            "humidity": float(row["humidity"]) if "humidity" in row and pd.notna(row["humidity"]) else None,
            "wind_speed": float(row["wind_speed"]) if "wind_speed" in row and pd.notna(row["wind_speed"]) else None,
        }
        if not record["city"] or record["timestamp"] is None:
            continue
        stmt = sqlite_insert(AQIReading).values(**record)
        stmt = stmt.on_conflict_do_update(
            index_elements=["city", "timestamp"],
            set_={k: stmt.excluded[k] for k in record if k not in ("city", "timestamp")},
        )
        db.execute(stmt)
    db.commit()


async def fetch_open_meteo_air_quality(city: str, lat: float, lon: float, hours: int, client: httpx.AsyncClient) -> pd.DataFrame:
    """Fetch hourly pollutants from Open-Meteo Air Quality (CAMS reanalysis, no key)."""
    past_days = max(1, min(92, (hours // 24) + 1))
    try:
        r = await client.get(
            f"{AIRQ_BASE}/air-quality",
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "pm2_5,pm10,nitrogen_dioxide,ozone,carbon_monoxide,sulphur_dioxide",
                "past_days": past_days,
                "forecast_days": 1,
                "timezone": "UTC",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        h = data.get("hourly", {})
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(h.get("time", []), utc=True),
            "pm25": h.get("pm2_5", []),
            "pm10": h.get("pm10", []),
            "no2":  h.get("nitrogen_dioxide", []),
            "o3":   h.get("ozone", []),
            "co":   h.get("carbon_monoxide", []),
            "so2":  h.get("sulphur_dioxide", []),
        })
        df["city"] = city
        return df
    except Exception as e:
        logger.warning(f"Air-quality fetch failed for {city}: {e}")
        return pd.DataFrame()


async def refresh_city(city: str, coords: dict, hours: int = 72):
    lat, lon = coords["lat"], coords["lon"]
    async with httpx.AsyncClient(follow_redirects=True) as client:
        aqi_df, weather_df = await asyncio.gather(
            fetch_open_meteo_air_quality(city, lat, lon, hours, client),
            fetch_weather(city, lat, lon, hours, client),
        )

    merged = merge_aqi_weather(aqi_df, weather_df)
    if merged.empty:
        merged = weather_df.copy()
        if not merged.empty:
            merged["city"] = city

    db = SessionLocal()
    try:
        upsert_readings(db, merged)
        logger.info(f"Refreshed {city}: {len(merged)} rows (pollutants={not aqi_df.empty}, weather={not weather_df.empty})")
    finally:
        db.close()


async def refresh_all_cities(hours: int = 72):
    tasks = [refresh_city(city, coords, hours) for city, coords in CITIES.items()]
    await asyncio.gather(*tasks, return_exceptions=True)


def get_city_dataframe(db: Session, city: str, hours: int = 72) -> pd.DataFrame:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(AQIReading)
        .filter(AQIReading.city == city, AQIReading.timestamp >= cutoff)
        .order_by(AQIReading.timestamp)
        .all()
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "timestamp": r.timestamp,
        "city": r.city,
        "pm25": r.pm25,
        "pm10": r.pm10,
        "no2": r.no2,
        "o3": r.o3,
        "temperature": r.temperature,
        "humidity": r.humidity,
        "wind_speed": r.wind_speed,
        "aqi": r.aqi,
    } for r in rows])
