"""Pydantic models for Motive webhook payloads."""
from pydantic import BaseModel, Field


class SpeedingEvent(BaseModel):
    """Model for Motive speeding event webhook payload."""
    
    action: str = Field(..., description="Event action type")
    id: int = Field(..., description="Event ID")
    max_over_speed_in_kph: float = Field(..., alias="max_over_speed_in_kph", description="Maximum speed over limit in KPH")
    max_posted_speed_limit_in_kph: float = Field(..., alias="max_posted_speed_limit_in_kph", description="Maximum posted speed limit in KPH")
    max_vehicle_speed: float = Field(..., alias="max_vehicle_speed", description="Maximum vehicle speed in KPH")
    driver_id: int = Field(..., alias="driver_id", description="Driver ID")
    vehicle_id: int = Field(..., alias="vehicle_id", description="Vehicle ID")
    status: str = Field(..., description="Event status")
    
    model_config = {
        "populate_by_name": True,
    }
