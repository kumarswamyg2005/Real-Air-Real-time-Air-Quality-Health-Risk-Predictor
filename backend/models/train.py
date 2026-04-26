"""
CLI training script.

Usage:
    python -m backend.models.train [--city Delhi] [--all] [--hours 720]

Trains LSTM + Prophet for each city using data already in the SQLite database.
Prints a comparison table of MAE / RMSE / MAPE.
"""

import argparse
import asyncio
import logging
from tabulate import tabulate  # type: ignore  (pip install tabulate)

from ..data.database import init_db, SessionLocal
from ..data.pipeline import CITIES, refresh_all_cities, get_city_dataframe
from .forecast import LSTMTrainer, ProphetTrainer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def train_city(city: str, hours: int) -> dict:
    db = SessionLocal()
    try:
        df = get_city_dataframe(db, city, hours=hours)
    finally:
        db.close()

    if df.empty:
        logger.warning(f"No data for {city}, skipping")
        return {"city": city, "lstm_mae": "—", "lstm_rmse": "—", "lstm_mape": "—",
                "prophet_mae": "—", "prophet_rmse": "—", "prophet_mape": "—"}

    result = {"city": city}
    try:
        lstm_metrics = LSTMTrainer(city).train(df)
        result.update({
            "lstm_mae": lstm_metrics["MAE"],
            "lstm_rmse": lstm_metrics["RMSE"],
            "lstm_mape": f"{lstm_metrics['MAPE']}%",
        })
    except Exception as e:
        logger.error(f"LSTM training failed for {city}: {e}")
        result.update({"lstm_mae": "err", "lstm_rmse": "err", "lstm_mape": "err"})

    try:
        prophet_metrics = ProphetTrainer(city).train(df)
        result.update({
            "prophet_mae": prophet_metrics["MAE"],
            "prophet_rmse": prophet_metrics["RMSE"],
            "prophet_mape": f"{prophet_metrics['MAPE']}%",
        })
    except Exception as e:
        logger.error(f"Prophet training failed for {city}: {e}")
        result.update({"prophet_mae": "err", "prophet_rmse": "err", "prophet_mape": "err"})

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", type=str, default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--hours", type=int, default=720, help="History hours to use for training")
    parser.add_argument("--fetch", action="store_true", help="Fetch fresh data before training")
    args = parser.parse_args()

    init_db()

    if args.fetch:
        logger.info("Fetching data from APIs...")
        asyncio.run(refresh_all_cities(hours=args.hours))

    cities = list(CITIES.keys()) if (args.all or not args.city) else [args.city]
    rows = [train_city(c, args.hours) for c in cities]

    headers = ["City", "LSTM MAE", "LSTM RMSE", "LSTM MAPE", "Prophet MAE", "Prophet RMSE", "Prophet MAPE"]
    table = [[r["city"], r.get("lstm_mae"), r.get("lstm_rmse"), r.get("lstm_mape"),
              r.get("prophet_mae"), r.get("prophet_rmse"), r.get("prophet_mape")] for r in rows]
    print("\n" + tabulate(table, headers=headers, tablefmt="rounded_outline"))


if __name__ == "__main__":
    main()
