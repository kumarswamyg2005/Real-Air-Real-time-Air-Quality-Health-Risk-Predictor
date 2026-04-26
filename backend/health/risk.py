"""
Health risk engine: combines predicted AQI + user profile → 4-level alert.
"""

from dataclasses import dataclass
from typing import Literal
from enum import IntEnum
import math


AgeGroup = Literal["child", "adult", "elderly"]
Condition = Literal["none", "asthma", "heart_disease", "diabetes"]
RiskLevel = Literal["Safe", "Moderate", "Unhealthy", "Hazardous"]


class AQI(IntEnum):
    GOOD = 50
    MODERATE = 100
    POOR = 200
    VERY_POOR = 300
    SEVERE = 400


# Multipliers bump the effective AQI for vulnerable groups
_AGE_MULT = {"child": 1.25, "adult": 1.0, "elderly": 1.20}
_COND_MULT = {"none": 1.0, "asthma": 1.35, "heart_disease": 1.30, "diabetes": 1.15}


@dataclass
class UserProfile:
    age_group: AgeGroup = "adult"
    condition: Condition = "none"


@dataclass
class RiskAssessment:
    aqi: float
    effective_aqi: float
    level: RiskLevel
    color: str
    headline: str
    recommendations: list[str]
    next_24h_level: RiskLevel | None = None


_RECS: dict[RiskLevel, dict[str, list[str]]] = {
    "Safe": {
        "none":         ["Air quality is good. Enjoy outdoor activities."],
        "asthma":       ["Air quality is acceptable. Carry your inhaler as a precaution."],
        "heart_disease":["Safe conditions. Light outdoor exercise is fine."],
        "diabetes":     ["Good conditions. Stay hydrated during outdoor activity."],
    },
    "Moderate": {
        "none":         ["Sensitive individuals may experience minor irritation.", "Limit prolonged outdoor exertion."],
        "asthma":       ["Avoid outdoor exercise.", "Keep rescue inhaler accessible.", "Monitor for symptoms."],
        "heart_disease":["Reduce moderate physical exertion.", "Take prescribed medications on schedule."],
        "diabetes":     ["Monitor blood sugar more frequently.", "Limit vigorous outdoor activity."],
    },
    "Unhealthy": {
        "none":         ["Reduce time spent outdoors.", "Avoid strenuous exercise outside.", "Consider wearing a mask."],
        "asthma":       ["Stay indoors with windows closed.", "Use air purifier if available.", "Have nebulizer ready."],
        "heart_disease":["Stay indoors.", "Avoid all strenuous activity.", "Seek immediate help if chest pain occurs."],
        "diabetes":     ["Stay indoors.", "High pollution can raise blood sugar — check levels hourly.", "Stay hydrated."],
    },
    "Hazardous": {
        "none":         ["Avoid all outdoor activity.", "Wear N95 mask if you must go out.", "Seal windows and doors."],
        "asthma":       ["STAY INDOORS. Hazardous air can trigger severe attacks.", "Call your doctor proactively.",
                         "Run air purifier on maximum. Wear N95 if emergency exit required."],
        "heart_disease":["STAY INDOORS. Risk of cardiac events is significantly elevated.",
                         "Contact your cardiologist.", "Do not exert yourself at all."],
        "diabetes":     ["STAY INDOORS.", "Pollution stress can cause blood-sugar spikes.",
                         "Check levels every 30 minutes.", "Wear N95 if emergency exit required."],
    },
}

_CHILD_EXTRA = {
    "Moderate": "Children are more sensitive — keep outdoor play brief.",
    "Unhealthy": "Keep children indoors and away from windows.",
    "Hazardous": "Children must remain indoors. Cancel all outdoor school activities.",
}

_ELDERLY_EXTRA = {
    "Moderate": "Elderly individuals should avoid prolonged outdoor exposure.",
    "Unhealthy": "Elderly should stay indoors; arrange medication delivery if possible.",
    "Hazardous": "Elderly at high risk — stay indoors and call for check-ins.",
}


def _level_from_aqi(effective_aqi: float) -> tuple[RiskLevel, str]:
    if effective_aqi <= 100:
        return "Safe", "#4CAF50"
    elif effective_aqi <= 200:
        return "Moderate", "#FFC107"
    elif effective_aqi <= 300:
        return "Unhealthy", "#FF5722"
    else:
        return "Hazardous", "#B71C1C"


def _headline(level: RiskLevel, aqi: float) -> str:
    return {
        "Safe":      f"Air Quality Good (AQI {aqi:.0f})",
        "Moderate":  f"Air Quality Moderate (AQI {aqi:.0f}) — Some Risk",
        "Unhealthy": f"Air Quality Unhealthy (AQI {aqi:.0f}) — Caution Required",
        "Hazardous": f"Air Quality Hazardous (AQI {aqi:.0f}) — STAY INDOORS",
    }[level]


def assess_risk(aqi: float, profile: UserProfile, next_24h_aqi: float | None = None) -> RiskAssessment:
    if math.isnan(aqi) or aqi < 0:
        aqi = 0.0

    eff = aqi * _AGE_MULT[profile.age_group] * _COND_MULT[profile.condition]
    level, color = _level_from_aqi(eff)

    recs = list(_RECS[level][profile.condition])
    if profile.age_group == "child" and level in _CHILD_EXTRA:
        recs.append(_CHILD_EXTRA[level])
    if profile.age_group == "elderly" and level in _ELDERLY_EXTRA:
        recs.append(_ELDERLY_EXTRA[level])

    next_level = None
    if next_24h_aqi is not None and not math.isnan(next_24h_aqi):
        eff_next = next_24h_aqi * _AGE_MULT[profile.age_group] * _COND_MULT[profile.condition]
        next_level, _ = _level_from_aqi(eff_next)

    return RiskAssessment(
        aqi=round(aqi, 1),
        effective_aqi=round(eff, 1),
        level=level,
        color=color,
        headline=_headline(level, aqi),
        recommendations=recs,
        next_24h_level=next_level,
    )


def pm25_to_aqi_india(pm25: float) -> float:
    """India NAAQS AQI from PM2.5 (µg/m³)."""
    breakpoints = [
        (0, 30, 0, 50), (30, 60, 51, 100), (60, 90, 101, 200),
        (90, 120, 201, 300), (120, 250, 301, 400), (250, 500, 401, 500),
    ]
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if c_lo <= pm25 <= c_hi:
            return ((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo
    return 500.0
