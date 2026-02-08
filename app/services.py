"""Service layer for external API integrations."""
import logging
from typing import Any, Dict, Optional

import httpx

from app.cache import vehicle_cache
from app.config import settings

logger = logging.getLogger(__name__)

MOTIVE_HEADERS = {
    "x-api-key": settings.motive_api_token,
    "Accept": "application/json",
}


async def fetch_speeding_details(event_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch speeding event details from Motive API (API-first source of truth for location).
    GET https://api.gomotive.com/v1/speeding_events/{event_id}
    Returns dict with lat, lon, speed, limit, vehicle_id (or None on error).
    """
    url = f"https://api.gomotive.com/v1/speeding_events/{event_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=MOTIVE_HEADERS)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        logger.warning(f"Speeding details API error for event_id={event_id}: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.warning(f"Speeding details request error for event_id={event_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Speeding details error for event_id={event_id}: {e}")
        return None

    # Normalize: API may return { "speeding_event": { ... } } or top-level keys
    event = data.get("speeding_event") if isinstance(data.get("speeding_event"), dict) else data
    if not isinstance(event, dict):
        logger.debug(f"Motive speeding_events response missing event object: {data}")
        return None

    lat: Optional[float] = None
    lon: Optional[float] = None
    loc = event.get("start_location") or event.get("location") or {}
    if isinstance(loc, dict):
        lat = loc.get("lat") or loc.get("latitude")
        lon = loc.get("lon") or loc.get("longitude")
    if lat is None:
        lat = event.get("lat") or event.get("latitude")
    if lon is None:
        lon = event.get("lon") or event.get("longitude")
    try:
        lat = float(lat) if lat is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lon = None

    speed = event.get("max_vehicle_speed") or event.get("speed")
    limit = event.get("max_posted_speed_limit_in_kph") or event.get("posted_speed_limit_in_kph") or event.get("limit")
    vehicle_id = event.get("vehicle_id")
    try:
        speed = float(speed) if speed is not None else None
    except (TypeError, ValueError):
        speed = None
    try:
        limit = float(limit) if limit is not None else None
    except (TypeError, ValueError):
        limit = None
    try:
        vehicle_id = int(vehicle_id) if vehicle_id is not None else None
    except (TypeError, ValueError):
        vehicle_id = None

    return {
        "lat": lat,
        "lon": lon,
        "speed": speed,
        "limit": limit,
        "vehicle_id": vehicle_id,
    }


async def get_vehicle_unit(vehicle_id: int) -> str:
    """
    Get vehicle unit number from cache or fetch from Motive API.
    
    Args:
        vehicle_id: The vehicle ID from Motive
        
    Returns:
        The vehicle unit number (from the 'number' field), or "Unit Unknown" on error
    """
    # Check cache first
    cached_unit = await vehicle_cache.get(vehicle_id)
    if cached_unit:
        logger.info(f"Cache hit for vehicle_id={vehicle_id}, unit={cached_unit}")
        return cached_unit
    
    logger.info(f"Cache miss for vehicle_id={vehicle_id}, fetching from API")
    
    # Fetch from Motive API
    try:
        url = f"https://api.gomotive.com/v1/vehicles/{vehicle_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=MOTIVE_HEADERS)
            response.raise_for_status()
            
            # Motive wraps the vehicle in a 'vehicle' key; extract nested number.
            vehicle_data = response.json()
            unit_number = vehicle_data.get("vehicle", {}).get("number")

            if not unit_number:
                # Log full payload at debug level to inspect structure in Railway logs.
                logger.debug(f"Motive Response: {vehicle_data}")
                unit_number = "Unit Unknown"
            
            # Cache the result (keyed by vehicle_id, so repeated lookups are avoided)
            await vehicle_cache.set(vehicle_id, unit_number)
            logger.info(f"Fetched and cached vehicle_id={vehicle_id}, unit={unit_number}")
            
            return unit_number
            
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code in (401, 403):
            logger.error(f"Auth error fetching vehicle {vehicle_id}: {status_code} {e}")
            # Do not raise — return safe fallback
            return "Unit Unknown"
        if status_code == 404:
            logger.warning(f"Vehicle not found: vehicle_id={vehicle_id}")
            unit_number = "Unit Unknown"
            # Cache the "not found" result to avoid repeated API calls
            await vehicle_cache.set(vehicle_id, unit_number)
            return unit_number
        logger.error(f"HTTP error fetching vehicle {vehicle_id}: {e}")
        return "Unit Unknown"
            
    except httpx.RequestError as e:
        logger.error(f"Request error fetching vehicle {vehicle_id}: {e}")
        return "Unit Unknown"
        
    except Exception as e:
        logger.error(f"Unexpected error fetching vehicle {vehicle_id}: {e}")
        return "Unit Unknown"
