"""Service layer for external API integrations."""
import httpx
import logging
from app.config import settings
from app.cache import vehicle_cache

logger = logging.getLogger(__name__)


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
        headers = {
            # Motive API uses x-api-key for this integration, not Bearer auth
            "x-api-key": settings.motive_api_token,
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
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
