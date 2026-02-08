"""FastAPI application main module."""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple, Union

from fastapi import FastAPI, Request, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from sqlalchemy import desc, select

from app.config import settings
from app.database import async_session_maker
from app.models import Event, SafetyEvent, SpeedingEvent
from app.security import verify_webhook_signature
from app.services import fetch_speeding_details, get_vehicle_unit
from app.telegram_bot import init_bot, process_alert, process_safety_alert, close_bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _extract_location(raw: dict) -> Tuple[Optional[float], Optional[float]]:
    """Best-effort extraction of lat/lon from Motive payload."""
    lat: Optional[float] = None
    lon: Optional[float] = None

    # Prefer nested start_location if present
    start_loc = raw.get("start_location") or raw.get("location")
    if isinstance(start_loc, dict):
        lat = start_loc.get("lat") or start_loc.get("latitude")
        lon = start_loc.get("lon") or start_loc.get("longitude")

    # Fallback to top-level fields
    if lat is None:
        lat = raw.get("lat") or raw.get("latitude")
    if lon is None:
        lon = raw.get("lon") or raw.get("longitude")

    try:
        lat = float(lat) if lat is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lon = None

    return lat, lon


def _build_map_link(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    """Build a Google Maps link if coordinates are available."""
    if lat is None or lon is None:
        return None
    return f"https://www.google.com/maps?q={lat},{lon}"


def _extract_timestamp(raw: dict) -> Optional[datetime]:
    """Best-effort extraction of an event timestamp from payload."""
    ts = raw.get("timestamp") or raw.get("occurred_at") or raw.get("created_at")
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        # Handle ISO 8601 strings
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _normalize_safety_event_type(raw: dict) -> str:
    """Normalize safety event subtype to event_type (hard_brake, acceleration, cornering)."""
    raw_type = (
        raw.get("safety_event_type")
        or raw.get("event_type")
        or raw.get("type")
        or raw.get("subtype")
        or ""
    )
    s = str(raw_type).lower().replace(" ", "_").replace("-", "_")
    if "brake" in s or "braking" in s:
        return "hard_brake"
    if "accel" in s:
        return "acceleration"
    if "corner" in s:
        return "cornering"
    return "safety" if s else "safety"


def _verify_dashboard_auth(credentials: HTTPBasicCredentials = Depends(HTTPBasic())) -> None:
    """Require admin/tnisafety for dashboard and /api/events."""
    if credentials.username != "admin" or credentials.password != "tnisafety":
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})


app = FastAPI(
    title="Safety Alert Bot",
    description="Webhook receiver for Motive speeding events with Telegram notifications",
    version="0.1.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    await init_bot()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup services on application shutdown."""
    await close_bot()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "safety-alert-bot"}


@app.get("/health")
async def health():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


@app.get("/dashboard", dependencies=[Depends(_verify_dashboard_auth)])
async def dashboard():
    """Serve the secure dashboard (HTTPBasic: admin / tnisafety)."""
    path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(path, media_type="text/html")


@app.get("/api/events", dependencies=[Depends(_verify_dashboard_auth)])
async def api_events():
    """Return the last 50 events from the DB as JSON."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Event).order_by(desc(Event.timestamp)).limit(50)
        )
        rows = result.scalars().all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "event_type": r.event_type,
                "vehicle_unit": r.vehicle_unit,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "lat": r.lat,
                "lon": r.lon,
                "speed": r.speed,
                "limit": r.limit,
                "maps_link": r.maps_link,
            })
        return out


@app.post("/webhook/motive")
async def motive_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Receive and process Motive webhook events.
    
    Security: For the Motive HMAC signature check, uses await request.body() (raw body).
    Performance: Returns 200 OK immediately, processes Telegram in background.
    Events: speeding_event_created, safety_event_created (hard brake, acceleration, cornering).
    """
    try:
        # Step 1: Read raw body for HMAC verification (must use exact bytes Motive sent)
        body_bytes = await request.body()
        
        # Step 2: Verify webhook signature (SECURITY FIRST)
        signature = request.headers.get("X-KT-Webhook-Signature", "")
        verify_webhook_signature(body_bytes, signature, settings.webhook_secret)
        
        # Step 3: Parse the request body
        try:
            payload: Union[List[Any], Any] = json.loads(body_bytes)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )

        # Normalize to a list of event dicts
        if isinstance(payload, list):
            events_raw: List[Any] = payload
            logger.info(f"Webhook batch received with {len(events_raw)} events")
        else:
            events_raw = [payload]
            logger.info(
                "Webhook event received: action=%s, id=%s",
                payload.get("action") if isinstance(payload, dict) else None,
                payload.get("id") if isinstance(payload, dict) else None,
            )

        accepted_events: List[int] = []

        # Open a DB session for this batch
        async with async_session_maker() as session:
            # Process each event in the batch
            for raw in events_raw:
                if not isinstance(raw, dict):
                    logger.error(f"Skipping non-object event payload: {raw!r}")
                    continue

                action = raw.get("action")

                if action == "speeding_event_created":
                    # --- Speeding: API-first — fetch_speeding_details(id) is source of truth ---
                    try:
                        event = SpeedingEvent.model_validate(raw)
                    except Exception as e:
                        logger.error(f"Invalid payload structure for event: {e}")
                        continue

                    event_id = event.id
                    details = await fetch_speeding_details(event_id)
                    if details:
                        lat, lon = details.get("lat"), details.get("lon")
                        speed, limit = details.get("speed"), details.get("limit")
                        vid = details.get("vehicle_id")
                    else:
                        lat, lon = _extract_location(raw)
                        speed = event.max_vehicle_speed
                        limit = event.max_posted_speed_limit_in_kph
                        vid = event.vehicle_id

                    map_link = _build_map_link(lat, lon)
                    vehicle_id_for_unit = vid if vid is not None else event.vehicle_id
                    vehicle_unit = await get_vehicle_unit(vehicle_id_for_unit)
                    event_ts = _extract_timestamp(raw) or datetime.now(timezone.utc)

                    try:
                        db_event = Event(
                            event_type="speeding",
                            vehicle_unit=vehicle_unit,
                            timestamp=event_ts,
                            lat=lat,
                            lon=lon,
                            speed=speed,
                            limit=limit,
                            maps_link=map_link,
                        )
                        session.add(db_event)
                        await session.flush()
                    except Exception as e:
                        logger.error(f"Failed to persist event {event_id} to DB: {e}", exc_info=True)
                        continue

                    raw["vehicle_unit"] = vehicle_unit
                    raw["map_link"] = map_link
                    raw["lat"] = lat
                    raw["lon"] = lon
                    if speed is not None:
                        raw["max_vehicle_speed"] = speed
                    if limit is not None:
                        raw["max_posted_speed_limit_in_kph"] = limit
                    background_tasks.add_task(process_alert, raw)
                    accepted_events.append(event_id)

                elif action == "safety_event_created":
                    # --- Safety (hard brake, acceleration, cornering): save Event, then Telegram ---
                    try:
                        safety = SafetyEvent.model_validate(raw)
                    except Exception as e:
                        logger.error(f"Invalid safety event payload: {e}")
                        continue

                    lat, lon = _extract_location(raw)  # start_location
                    map_link = _build_map_link(lat, lon)
                    vehicle_unit = await get_vehicle_unit(safety.vehicle_id)
                    event_ts = _extract_timestamp(raw) or datetime.now(timezone.utc)
                    event_type = _normalize_safety_event_type(raw)

                    try:
                        db_event = Event(
                            event_type=event_type,
                            vehicle_unit=vehicle_unit,
                            timestamp=event_ts,
                            lat=lat,
                            lon=lon,
                            speed=None,
                            limit=None,
                            maps_link=map_link,
                        )
                        session.add(db_event)
                        await session.flush()
                    except Exception as e:
                        logger.error(f"Failed to persist safety event to DB: {e}", exc_info=True)
                        continue

                    raw["vehicle_unit"] = vehicle_unit
                    raw["map_link"] = map_link
                    raw["event_type"] = event_type
                    raw["lat"] = lat
                    raw["lon"] = lon
                    background_tasks.add_task(process_safety_alert, raw)
                    accepted_events.append(safety.id or 0)

                else:
                    logger.info(f"Event ignored: action '{action}' not processed")
                    continue

            # Commit all persisted events
            await session.commit()

        # Step 4: Return 200 OK immediately (within 2 seconds constraint)
        if not accepted_events:
            # No events were accepted, but we still return 200 to Motive
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "ignored",
                    "reason": "No qualifying events (speeding_event_created / safety_event_created) in payload",
                },
            )

        logger.info(f"Events queued for processing: {accepted_events}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "accepted",
                "event_ids": accepted_events,
                "message": f"{len(accepted_events)} event(s) queued for processing",
            },
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 from signature verification)
        raise
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
