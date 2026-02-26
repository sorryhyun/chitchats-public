"""WebSocket bridge for Codex realtime voice mode.

Bridges browser audio ←→ Codex app-server realtime API.
Browser sends/receives JSON messages over WebSocket; this endpoint
translates them to/from JSON-RPC calls on the Codex app-server instance.

Protocol (browser ↔ this endpoint):
  → {type: "audio", data: "<base64>", sampleRate: 24000, numChannels: 1}
  → {type: "text", text: "..."}
  → {type: "stop"}
  ← {type: "audio", data: "<base64>", sampleRate: 24000, numChannels: 1}
  ← {type: "transcript", item: {...}}
  ← {type: "error", message: "..."}
  ← {type: "closed", reason: "..."}
"""

import asyncio
import logging

from core.auth import validate_jwt_token
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from providers.codex.app_server_pool import CodexAppServerPool
from providers.codex.constants import RealtimeNotification
from providers.configs import CodexStartupConfig, CodexTurnConfig

import crud
from infrastructure.database import get_db

router = APIRouter()
logger = logging.getLogger("VoiceRealtime")


@router.websocket("/rooms/{room_id}/voice/realtime")
async def voice_realtime_ws(websocket: WebSocket, room_id: int, token: str = ""):
    """WebSocket endpoint for realtime voice mode in Codex rooms.

    Query params:
        token: JWT auth token (required, since WS can't send custom headers)
    """
    # --- Auth ---
    payload = validate_jwt_token(token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_role = payload.get("role", "admin")
    user_id = payload.get("sub", user_role)

    # --- Room validation ---
    async for db in get_db():
        room = await crud.get_room(db, room_id)
        break
    else:
        await websocket.close(code=4004, reason="Database error")
        return

    if room is None:
        await websocket.close(code=4004, reason="Room not found")
        return

    if user_role != "admin" and room.owner_id != user_id:
        await websocket.close(code=4003, reason="Access denied")
        return

    if room.default_provider != "codex":
        await websocket.close(code=4000, reason="Voice mode requires a Codex room")
        return

    await websocket.accept()

    # --- Get Codex instance & thread ---
    try:
        pool = await CodexAppServerPool.get_instance()
    except Exception as e:
        logger.error(f"Failed to get Codex pool: {e}")
        await websocket.send_json({"type": "error", "message": "Codex pool unavailable"})
        await websocket.close(code=1011)
        return

    # Use a room-level agent key for voice (shared across all agents in the room)
    agent_key = f"voice_room_{room_id}"
    startup_config = CodexStartupConfig()

    try:
        instance = await pool.get_or_create_instance(agent_key, startup_config)
    except Exception as e:
        logger.error(f"Failed to create Codex instance for voice: {e}")
        await websocket.send_json({"type": "error", "message": f"Failed to start Codex: {e}"})
        await websocket.close(code=1011)
        return

    # Create a thread for this voice session
    turn_config = CodexTurnConfig(
        developer_instructions="You are a helpful voice assistant.",
        cwd=None,
    )

    try:
        thread_id = await instance.create_thread(turn_config)
    except Exception as e:
        logger.error(f"Failed to create thread for voice: {e}")
        await websocket.send_json({"type": "error", "message": f"Failed to create thread: {e}"})
        await websocket.close(code=1011)
        return

    # Start realtime session
    try:
        await instance.start_realtime(thread_id, prompt=turn_config.developer_instructions)
    except Exception as e:
        logger.error(f"Failed to start realtime: {e}")
        await websocket.send_json({"type": "error", "message": f"Failed to start realtime: {e}"})
        await websocket.close(code=1011)
        return

    logger.info(f"Voice realtime session started: room={room_id}, thread={thread_id}")

    # --- Bidirectional bridge ---
    session_active = True
    realtime_stopped = False

    async def write_loop():
        """Forward realtime notifications from Codex → browser."""
        nonlocal session_active
        notification_count = 0
        try:
            while session_active:
                notification = await instance.drain_realtime_notifications(timeout=0.05)
                if notification is None:
                    continue

                notification_count += 1
                method = notification.get("method", "")
                params = notification.get("params", {})
                logger.info(f"Realtime notification #{notification_count}: method={method}")

                if method == RealtimeNotification.OUTPUT_AUDIO_DELTA:
                    audio = params.get("audio", {})
                    await websocket.send_json({
                        "type": "audio",
                        "data": audio.get("data", ""),
                        "sampleRate": audio.get("sampleRate", 24000),
                        "numChannels": audio.get("numChannels", 1),
                    })
                elif method == RealtimeNotification.ITEM_ADDED:
                    await websocket.send_json({
                        "type": "transcript",
                        "item": params.get("item", {}),
                    })
                elif method == RealtimeNotification.ERROR:
                    await websocket.send_json({
                        "type": "error",
                        "message": params.get("message", "Unknown error"),
                    })
                elif method in ("error", "codex/event/error"):
                    # Generic Codex errors routed during realtime session
                    error_msg = params.get("error", {}).get("message", "") or \
                                params.get("msg", {}).get("message", "Unknown error")
                    logger.warning(f"Codex error during voice session: {error_msg}")
                    await websocket.send_json({
                        "type": "error",
                        "message": error_msg,
                    })
                elif method == RealtimeNotification.CLOSED:
                    await websocket.send_json({
                        "type": "closed",
                        "reason": params.get("reason", "unknown"),
                    })
                    session_active = False
                    break
                elif method == RealtimeNotification.STARTED:
                    await websocket.send_json({
                        "type": "started",
                        "sessionId": params.get("sessionId"),
                    })
        except WebSocketDisconnect:
            session_active = False
        except Exception as e:
            logger.debug(f"Write loop error: {e}")
            session_active = False

    write_task = asyncio.create_task(write_loop())

    try:
        # Read loop: browser → Codex
        while session_active:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            msg_type = msg.get("type", "")

            if msg_type == "audio":
                await instance.append_audio(thread_id, {
                    "data": msg.get("data", ""),
                    "sampleRate": msg.get("sampleRate", 24000),
                    "numChannels": msg.get("numChannels", 1),
                    "samplesPerChannel": msg.get("samplesPerChannel"),
                })
            elif msg_type == "text":
                text = msg.get("text", "")
                if text:
                    await instance.append_text(thread_id, text)
            elif msg_type == "stop":
                await instance.stop_realtime(thread_id)
                realtime_stopped = True
                session_active = False
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Voice realtime read loop error: {e}")
    finally:
        session_active = False
        write_task.cancel()
        try:
            await write_task
        except asyncio.CancelledError:
            pass

        # Ensure realtime session is stopped (skip if already stopped by "stop" msg)
        if not realtime_stopped:
            try:
                await instance.stop_realtime(thread_id)
            except Exception:
                pass

        logger.info(f"Voice realtime session ended: room={room_id}, thread={thread_id}")
