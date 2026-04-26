"""
FastAPI backend for Real-Air quality forecasting.

Run: uvicorn backend.main:app --reload --port 8000
"""

import asyncio
import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data.database import init_db, SessionLocal, AQIReading
from .data.pipeline import (
    CITIES, refresh_all_cities, refresh_city,
    get_city_dataframe, fetch_weather_forecast, pm25_to_aqi,
)
from .data.scheduler import start_scheduler, stop_scheduler
from .models.forecast import LSTMTrainer, ProphetTrainer, has_model, PRED_LEN
from .health.risk import UserProfile, assess_risk, pm25_to_aqi_india

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(refresh_all_cities(hours=72))
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Real-Air API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _safe(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), 2)


def _aqi_category(aqi: float | None) -> str:
    if aqi is None:
        return "Unknown"
    if aqi <= 50:   return "Good"
    if aqi <= 100:  return "Satisfactory"
    if aqi <= 200:  return "Moderate"
    if aqi <= 300:  return "Poor"
    if aqi <= 400:  return "Very Poor"
    return "Severe"


def _aqi_color(aqi: float | None) -> str:
    if aqi is None: return "#9E9E9E"
    if aqi <= 50:   return "#4CAF50"
    if aqi <= 100:  return "#CDDC39"
    if aqi <= 200:  return "#FFC107"
    if aqi <= 300:  return "#FF5722"
    if aqi <= 400:  return "#9C27B0"
    return "#B71C1C"


# ─── schemas ──────────────────────────────────────────────────────────────────

class HealthRequest(BaseModel):
    city: str
    age_group: Literal["child", "adult", "elderly"] = "adult"
    condition: Literal["none", "asthma", "heart_disease", "diabetes"] = "none"


class RefreshRequest(BaseModel):
    city: Optional[str] = None


# ─── routes ───────────────────────────────────────────────────────────────────

@app.get("/api/cities")
def list_cities():
    db = SessionLocal()
    try:
        result = []
        for city, coords in CITIES.items():
            row = (
                db.query(AQIReading)
                .filter(AQIReading.city == city)
                .order_by(AQIReading.timestamp.desc())
                .first()
            )
            aqi = _safe(row.aqi) if row else None
            result.append({
                "city": city,
                "lat": coords["lat"],
                "lon": coords["lon"],
                "aqi": aqi,
                "category": _aqi_category(aqi),
                "color": _aqi_color(aqi),
                "updated_at": row.timestamp.isoformat() if row and row.timestamp else None,
            })
        return result
    finally:
        db.close()


@app.get("/api/cities/{city}/current")
def city_current(city: str):
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not found")
    db = SessionLocal()
    try:
        row = (
            db.query(AQIReading)
            .filter(AQIReading.city == city)
            .order_by(AQIReading.timestamp.desc())
            .first()
        )
        if not row:
            raise HTTPException(404, "No data yet for this city")
        return {
            "city": city,
            "timestamp": row.timestamp.isoformat(),
            "pm25": _safe(row.pm25),
            "pm10": _safe(row.pm10),
            "no2": _safe(row.no2),
            "o3": _safe(row.o3),
            "co": _safe(row.co),
            "so2": _safe(row.so2),
            "aqi": _safe(row.aqi),
            "category": _aqi_category(row.aqi),
            "color": _aqi_color(row.aqi),
            "temperature": _safe(row.temperature),
            "humidity": _safe(row.humidity),
            "wind_speed": _safe(row.wind_speed),
        }
    finally:
        db.close()


@app.get("/api/cities/{city}/hourly")
def city_hourly(city: str, hours: int = Query(default=72, ge=1, le=720)):
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not found")
    db = SessionLocal()
    try:
        df = get_city_dataframe(db, city, hours=hours)
    finally:
        db.close()

    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        records.append({
            "timestamp": row["timestamp"].isoformat() if pd.notna(row["timestamp"]) else None,
            "pm25": _safe(row.get("pm25")),
            "pm10": _safe(row.get("pm10")),
            "no2": _safe(row.get("no2")),
            "aqi": _safe(row.get("aqi")),
            "temperature": _safe(row.get("temperature")),
            "humidity": _safe(row.get("humidity")),
            "wind_speed": _safe(row.get("wind_speed")),
        })
    return records


@app.get("/api/cities/{city}/forecast")
async def city_forecast(city: str):
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not found")

    db = SessionLocal()
    try:
        df = get_city_dataframe(db, city, hours=72)
    finally:
        db.close()

    coords = CITIES[city]
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    future_times = [now + timedelta(hours=i + 1) for i in range(PRED_LEN)]

    lstm_preds, prophet_preds = None, None

    if not df.empty and has_model(city):
        try:
            lstm_preds = LSTMTrainer(city).predict(df)
        except Exception as e:
            logger.warning(f"LSTM predict failed for {city}: {e}")
        try:
            prophet_preds = ProphetTrainer(city).predict(df)
        except Exception as e:
            logger.warning(f"Prophet predict failed for {city}: {e}")

    # Fall back to a simple seasonal simulation if no model is trained yet
    if lstm_preds is None and not df.empty and "pm25" in df.columns:
        last_pm25 = df["pm25"].dropna().iloc[-1] if df["pm25"].notna().any() else 60.0
        lstm_preds = _simulate_forecast(last_pm25, PRED_LEN)
        prophet_preds = _simulate_forecast(last_pm25 * 0.95, PRED_LEN)
    elif lstm_preds is None:
        base = 80.0
        lstm_preds = _simulate_forecast(base, PRED_LEN)
        prophet_preds = _simulate_forecast(base * 0.9, PRED_LEN)

    if prophet_preds is None:
        prophet_preds = lstm_preds * np.random.uniform(0.9, 1.1, size=len(lstm_preds))

    result = []
    for i, ts in enumerate(future_times):
        pm25_l = float(lstm_preds[i]) if i < len(lstm_preds) else None
        pm25_p = float(prophet_preds[i]) if i < len(prophet_preds) else None
        result.append({
            "timestamp": ts.isoformat(),
            "hour": i + 1,
            "pm25_lstm": _safe(pm25_l),
            "pm25_prophet": _safe(pm25_p),
            "aqi_lstm": _safe(pm25_to_aqi(pm25_l) if pm25_l is not None else None),
            "aqi_prophet": _safe(pm25_to_aqi(pm25_p) if pm25_p is not None else None),
        })
    return result


def _simulate_forecast(base_pm25: float, n: int) -> np.ndarray:
    """Diurnal + noise simulation for demo when model not trained."""
    hours = np.arange(n)
    diurnal = 15 * np.sin(2 * np.pi * (hours - 6) / 24)
    noise = np.random.normal(0, 5, n)
    return np.clip(base_pm25 + diurnal + noise, 5, 500)


@app.get("/api/cities/{city}/historical")
def city_historical(
    city: str,
    year: int = Query(default=None),
    month: int = Query(default=None, ge=1, le=12),
):
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not found")

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        target_year = year or now.year
        target_month = month or now.month

        prev_year = target_year - 1
        # Current month window
        start_curr = datetime(target_year, target_month, 1)
        if target_month == 12:
            end_curr = datetime(target_year + 1, 1, 1)
        else:
            end_curr = datetime(target_year, target_month + 1, 1)

        # Same month last year
        start_prev = datetime(prev_year, target_month, 1)
        if target_month == 12:
            end_prev = datetime(prev_year + 1, 1, 1)
        else:
            end_prev = datetime(prev_year, target_month + 1, 1)

        def query_range(s, e):
            rows = (
                db.query(AQIReading)
                .filter(AQIReading.city == city, AQIReading.timestamp >= s, AQIReading.timestamp < e)
                .order_by(AQIReading.timestamp)
                .all()
            )
            return [{"timestamp": r.timestamp.isoformat(), "aqi": _safe(r.aqi), "pm25": _safe(r.pm25)} for r in rows]

        return {
            "city": city,
            "current_month": {"year": target_year, "month": target_month, "data": query_range(start_curr, end_curr)},
            "previous_year": {"year": prev_year, "month": target_month, "data": query_range(start_prev, end_prev)},
        }
    finally:
        db.close()


@app.post("/api/health/risk")
def health_risk(req: HealthRequest):
    if req.city not in CITIES:
        raise HTTPException(404, f"City '{req.city}' not found")

    db = SessionLocal()
    try:
        row = (
            db.query(AQIReading)
            .filter(AQIReading.city == req.city)
            .order_by(AQIReading.timestamp.desc())
            .first()
        )
    finally:
        db.close()

    current_aqi = float(row.aqi) if row and row.aqi else 150.0
    profile = UserProfile(age_group=req.age_group, condition=req.condition)

    # Get next 24h avg from forecast if available (non-blocking best-effort)
    next_24h_aqi = None
    try:
        db = SessionLocal()
        df = get_city_dataframe(db, req.city, hours=72)
        db.close()
        if not df.empty and has_model(req.city):
            lstm_preds = LSTMTrainer(req.city).predict(df)
            next_24h_aqi = float(np.mean([pm25_to_aqi(p) for p in lstm_preds[:24]]))
    except Exception:
        pass

    assessment = assess_risk(current_aqi, profile, next_24h_aqi)
    return {
        "city": req.city,
        "current_aqi": assessment.aqi,
        "effective_aqi": assessment.effective_aqi,
        "level": assessment.level,
        "color": assessment.color,
        "headline": assessment.headline,
        "recommendations": assessment.recommendations,
        "next_24h_level": assessment.next_24h_level,
        "profile": {"age_group": req.age_group, "condition": req.condition},
    }


@app.post("/api/refresh")
async def trigger_refresh(req: RefreshRequest):
    if req.city:
        if req.city not in CITIES:
            raise HTTPException(404, f"City '{req.city}' not found")
        asyncio.create_task(refresh_city(req.city, CITIES[req.city], hours=72))
        return {"message": f"Refresh triggered for {req.city}"}
    asyncio.create_task(refresh_all_cities(hours=72))
    return {"message": "Refresh triggered for all cities"}


@app.get("/api/stats")
def stats():
    db = SessionLocal()
    try:
        total = db.query(AQIReading).count()
        cities_with_data = [
            city for city in CITIES
            if db.query(AQIReading).filter(AQIReading.city == city).count() > 0
        ]
        return {
            "total_readings": total,
            "cities_with_data": cities_with_data,
            "cities_total": len(CITIES),
            "model_ready": [c for c in CITIES if has_model(c)],
        }
    finally:
        db.close()
