import asyncio
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
import redis.asyncio as aioredis
import structlog

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.redis import get_redis

logger = structlog.get_logger()
router = APIRouter(tags=["WebSockets & Live Alerts"])


@router.websocket("/ws/connect")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    """Authenticated WebSocket connection for real-time placement and interview alerts."""
    # 1. Pre-handshake JWT validation
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token missing")
        return

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid subject")
        return

    # 2. Accept WebSocket connection
    await websocket.accept()
    logger.info("websocket_connected", user_id=str(user_id))

    # 3. Connect to Redis Pub/Sub
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    channel_name = f"hirekit:user:{user_id}"
    await pubsub.subscribe(channel_name)

    # 4. Background task to listen to Redis and forward to WebSocket
    async def redis_listener():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    await websocket.send_text(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("ws_forward_failed", error=str(e))

    listener_task = asyncio.create_task(redis_listener())

    # 5. Handle incoming client messages (heartbeat pings)
    try:
        while True:
            text = await websocket.receive_text()
            if text == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info("websocket_disconnected", user_id=str(user_id))
    finally:
        listener_task.cancel()
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()
        await redis.close()
