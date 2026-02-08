"""Pydantic models and SQLAlchemy ORM models."""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SpeedingEvent(BaseModel):
    """Model for Motive speeding event webhook payload."""
    
    action: str = Field(..., description="Event action type")
    id: int = Field(..., description="Event ID")
    max_over_speed_in_kph: float = Field(..., alias="max_over_speed_in_kph", description="Maximum speed over limit in KPH")
    max_posted_speed_limit_in_kph: float = Field(..., alias="max_posted_speed_limit_in_kph", description="Maximum posted speed limit in KPH")
    max_vehicle_speed: float = Field(..., alias="max_vehicle_speed", description="Maximum vehicle speed in KPH")
    driver_id: int = Field(..., alias="driver_id", description="Driver ID")
    vehicle_id: int = Field(..., alias="vehicle_id", description="Vehicle ID")
    status: Optional[str] = Field(default=None, description="Event status")
    
    model_config = {
        "populate_by_name": True,
    }


class SafetyEvent(BaseModel):
    """Model for Motive safety_event_created payload (hard braking, acceleration, cornering)."""
    
    action: str = Field(..., description="Event action type")
    vehicle_id: int = Field(..., alias="vehicle_id", description="Vehicle ID")
    id: Optional[int] = Field(default=None, description="Event ID")
    driver_id: Optional[int] = Field(default=None, alias="driver_id", description="Driver ID")
    
    model_config = {
        "populate_by_name": True,
        "extra": "allow",
    }


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class Event(Base):
    """Database model for stored events (for reporting)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_unit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maps_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

