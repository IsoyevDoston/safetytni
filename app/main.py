"""FastAPI application main module."""
import json
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse
from app.config import settings
from app.models import SpeedingEvent
from app.security import verify_webhook_signature
from app.telegram_bot import send_speeding_alert, init_bot, close_bot


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


@app.post("/webhook/motive")
async def motive_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Receive and process Motive webhook events.
    
    Security: Verifies HMAC-SHA1 signature before processing.
    Performance: Returns 200 OK immediately, processes Telegram in background.
    Filtering: Only processes 'speeding_event_created' events.
    """
    try:
        # Step 1: Read the request body (can only be read once)
        body_bytes = await request.body()
        
        # Step 2: Verify webhook signature (SECURITY FIRST)
        signature = request.headers.get("X-KT-Webhook-Signature", "")
        verify_webhook_signature(body_bytes, signature, settings.webhook_secret)
        
        # Step 3: Parse the request body
        payload_dict = json.loads(body_bytes)
        
        # Step 4: Check action type (EFFICIENCY - filter early)
        action = payload_dict.get("action")
        if action != "speeding_event_created":
            # Return 200 OK but don't process
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "ignored", "reason": f"Action '{action}' not processed"}
            )
        
        # Step 5: Validate the payload structure (TYPING - use Pydantic)
        try:
            event = SpeedingEvent.model_validate(payload_dict)
        except Exception as e:
            # Invalid payload structure
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payload structure: {str(e)}"
            )
        
        # Step 6: Schedule Telegram notification in background (ASYNC/NON-BLOCKING)
        background_tasks.add_task(send_speeding_alert, payload_dict)
        
        # Step 7: Return 200 OK immediately (within 2 seconds constraint)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "accepted",
                "event_id": event.id,
                "message": "Event queued for processing"
            }
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
        # Log unexpected errors (in production, use proper logging)
        print(f"Unexpected error processing webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
