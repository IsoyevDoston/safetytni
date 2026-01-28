"""Telegram bot integration using Aiogram 3.x."""
from aiogram import Bot
from aiogram.types import Message
from typing import Optional
from app.config import settings
from app.cache import driver_cache


# Global bot instance (will be initialized in main)
bot: Optional[Bot] = None


async def init_bot() -> Bot:
    """Initialize the Telegram bot."""
    global bot
    if bot is None:
        bot = Bot(token=settings.telegram_bot_token)
    return bot


async def close_bot() -> None:
    """Close the Telegram bot connection."""
    global bot
    if bot is not None:
        await bot.session.close()
        bot = None


async def get_driver_name(driver_id: int) -> str:
    """
    Get driver name from cache or fetch from API.
    
    For MVP, we'll return a placeholder if not in cache.
    In production, you would fetch from Motive API here.
    """
    cached_name = await driver_cache.get(driver_id)
    if cached_name:
        return cached_name
    
    # TODO: In production, fetch from Motive API
    # For MVP, use a placeholder
    driver_name = f"Driver #{driver_id}"
    
    # Cache the result
    await driver_cache.set(driver_id, driver_name)
    
    return driver_name


async def send_speeding_alert(event_data: dict) -> None:
    """
    Send a speeding alert notification to Telegram.
    
    Args:
        event_data: The speeding event data dictionary
    """
    try:
        # Initialize bot if not already done
        if bot is None:
            await init_bot()
        
        # Parse the event
        from app.models import SpeedingEvent
        event = SpeedingEvent.model_validate(event_data)
        
        # Get driver name (from cache or API)
        driver_name = await get_driver_name(event.driver_id)
        
        # Format the alert message
        message = (
            "🚨 **SPEEDING ALERT** 🚨\n\n"
            f"**Driver:** {driver_name}\n"
            f"**Vehicle ID:** {event.vehicle_id}\n"
            f"**Event ID:** {event.id}\n\n"
            f"**Speed Details:**\n"
            f"• Posted Limit: {event.max_posted_speed_limit_in_kph:.1f} km/h\n"
            f"• Vehicle Speed: {event.max_vehicle_speed:.1f} km/h\n"
            f"• Over Limit: {event.max_over_speed_in_kph:.1f} km/h\n\n"
            f"**Status:** {event.status}"
        )
        
        # Send the message
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=message,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        # Log the error (in production, use proper logging)
        print(f"Error sending Telegram alert: {e}")
        raise
