from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "air_quality.db")
DATABASE_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class AQIReading(Base):
    __tablename__ = "aqi_readings"
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    pm25 = Column(Float, nullable=True)
    pm10 = Column(Float, nullable=True)
    no2 = Column(Float, nullable=True)
    o3 = Column(Float, nullable=True)
    co = Column(Float, nullable=True)
    so2 = Column(Float, nullable=True)
    aqi = Column(Float, nullable=True)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    wind_speed = Column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("city", "timestamp", name="uq_city_time"),)


class ForecastRecord(Base):
    __tablename__ = "forecast_records"
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    forecast_time = Column(DateTime, index=True)
    pm25_lstm = Column(Float, nullable=True)
    pm25_prophet = Column(Float, nullable=True)
    aqi_lstm = Column(Float, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
