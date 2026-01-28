# Safety Alert Bot - Motive Webhook to Telegram

A critical safety alert bot for logistics fleet management that receives webhooks from Motive (formerly KeepTruckin), verifies their security, and dispatches Telegram notifications for speeding events.

## Architecture

- **FastAPI**: High-performance web server for webhook endpoints
- **Aiogram 3.x**: Modern async Telegram bot framework
- **Pydantic V2**: Type-safe data validation
- **Railway**: Deployment platform

## Features

✅ **Security First**: HMAC-SHA1 signature verification for all webhooks  
✅ **Async/Non-blocking**: Returns 200 OK within 2 seconds, processes Telegram in background  
✅ **Type Safety**: Full Pydantic models, no raw dicts  
✅ **Efficient Caching**: In-memory LRU cache (max 100) for driver ID → name mapping  
✅ **Event Filtering**: Only processes `speeding_event_created` events  

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required variables:
- `WEBHOOK_SECRET`: Your Motive webhook secret (for HMAC verification)
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather
- `TELEGRAM_CHAT_ID`: The chat ID where alerts should be sent

### 3. Run the Server

```bash
python main.py
```

Or using uvicorn directly:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The server will be available at `http://localhost:8000`

## API Endpoints

### `POST /webhook/motive`

Receives Motive webhook events. Only processes `speeding_event_created` events.

**Security**: Requires `X-KT-Webhook-Signature` header with valid HMAC-SHA1 signature.

**Response**: Returns 200 OK immediately, processes Telegram notification in background.

### `GET /health`

Health check endpoint for monitoring.

### `GET /`

Root endpoint with service status.

## Webhook Payload Format

The bot expects Motive speeding events in this format:

```json
{
  "action": "speeding_event_created",
  "id": 435681,
  "max_over_speed_in_kph": 12.5,
  "max_posted_speed_limit_in_kph": 80.0,
  "max_vehicle_speed": 92.5,
  "driver_id": 101,
  "vehicle_id": 25,
  "status": "pending_review"
}
```

## Deployment on Railway

1. Connect your repository to Railway
2. Set environment variables in Railway dashboard:
   - `WEBHOOK_SECRET`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Railway will automatically detect and deploy the FastAPI app

## Security

- All webhooks are verified using HMAC-SHA1 with your `WEBHOOK_SECRET`
- Invalid signatures result in HTTP 403 Forbidden
- Constant-time comparison prevents timing attacks

## Performance

- Webhook endpoint returns within 2 seconds
- Telegram notifications processed asynchronously via FastAPI BackgroundTasks
- Driver name caching reduces API calls (max 100 entries)

## Development

The project structure:

```
safetytni/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application
│   ├── config.py        # Configuration management
│   ├── models.py        # Pydantic models
│   ├── security.py      # HMAC verification
│   ├── telegram_bot.py # Telegram bot integration
│   └── cache.py         # In-memory LRU cache
├── main.py              # Entry point
├── requirements.txt     # Python dependencies
├── pyproject.toml       # Project metadata
└── README.md           # This file
```

## License

Proprietary - Internal use only
