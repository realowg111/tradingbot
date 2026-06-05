"""WebSocket Hub for live broadcasting state, positions and prices."""
import asyncio
import json
import logging
from typing import Set, Any, Dict
from datetime import datetime, timezone

from fastapi import WebSocket
from jose import JWTError

from security import decode_access_token

logger = logging.getLogger("ws_hub")


class WSHub:
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, token: str) -> bool:
        # Validate JWT
        try:
            decode_access_token(token)
        except JWTError:
            await ws.close(code=4401)
            return False
        await ws.accept()
        async with self._lock:
            self.clients.add(ws)
        logger.info("WS client connected (total=%d)", len(self.clients))
        return True

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self.clients.discard(ws)
        logger.info("WS client disconnected (total=%d)", len(self.clients))

    async def broadcast(self, msg_type: str, data: Dict[str, Any]):
        if not self.clients:
            return
        payload = json.dumps({
            "type": msg_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }, default=str)
        dead = []
        async with self._lock:
            clients = list(self.clients)
        for c in clients:
            try:
                await c.send_text(payload)
            except Exception:
                dead.append(c)
        if dead:
            async with self._lock:
                for c in dead:
                    self.clients.discard(c)


ws_hub = WSHub()
