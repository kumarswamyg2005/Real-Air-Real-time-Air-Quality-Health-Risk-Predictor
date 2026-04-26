import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .pipeline import refresh_all_cities

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_refresh,
        "interval",
        hours=1,
        id="refresh_aqi",
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler started — hourly AQI refresh active")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


async def _run_refresh():
    logger.info("Scheduled: refreshing all cities")
    try:
        await refresh_all_cities(hours=72)
    except Exception as e:
        logger.error(f"Scheduled refresh failed: {e}")
