"""Telegram listener using Telethon.

Listens to NEW messages from configured channels and forwards them to a parser.
Session is persisted on disk so the SMS flow runs only once.

Designed to run alongside FastAPI on Windows VPS.
"""
import os
import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional, List

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

logger = logging.getLogger("telegram_listener")

ParseCallback = Callable[[str, dict], Awaitable[None]]


class TelegramListener:
    """Singleton-ish manager for the Telethon client + login flow."""

    def __init__(self) -> None:
        # Lazy init in connect_and_maybe_start (env may not be loaded at import time)
        self.api_id: Optional[int] = None
        self.api_hash: Optional[str] = None
        self.phone_number: Optional[str] = None
        self.session_path: Optional[Path] = None
        self.channels: List[str] = []
        self.parse_callback: Optional[ParseCallback] = None

        self.client: Optional[TelegramClient] = None
        self._login_lock = asyncio.Lock()
        self._login_in_progress: bool = False
        self._phone_code_hash: Optional[str] = None
        self._authorized: bool = False
        self._runner_task: Optional[asyncio.Task] = None
        self._channel_entities: dict = {}
        self._last_error: Optional[str] = None

    def configure(
        self,
        api_id: int,
        api_hash: str,
        phone_number: str,
        session_path: Path,
        channels: List[str],
        parse_callback: ParseCallback,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.session_path = session_path
        self.channels = channels or []
        self.parse_callback = parse_callback

        # Make sure session dir exists
        if session_path:
            session_path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_client(self) -> bool:
        if self.client is not None:
            return True
        if not (self.api_id and self.api_hash and self.session_path):
            self._last_error = "Telethon non configuré (TELEGRAM_API_ID/HASH manquants)"
            return False
        try:
            self.client = TelegramClient(
                str(self.session_path),
                self.api_id,
                self.api_hash,
                auto_reconnect=True,
                connection_retries=5,
            )
            return True
        except Exception as e:
            self._last_error = f"Telethon init error: {e}"
            logger.exception("Telethon init failed: %s", e)
            return False

    # ---------- public API ----------

    async def connect_and_maybe_start(self) -> None:
        """Connect Telethon. If session authorized, register handlers. Else wait for SMS flow."""
        if not self._ensure_client():
            logger.warning("Telegram listener disabled: %s", self._last_error)
            return
        try:
            if not self.client.is_connected():
                await self.client.connect()
            self._authorized = await self.client.is_user_authorized()
            if self._authorized:
                logger.info("Telegram session authorized -> registering handlers")
                await self._register_handlers()
            else:
                logger.warning("Telegram session NOT authorized. Use POST /api/telegram/start-login")

            if self._runner_task is None or self._runner_task.done():
                self._runner_task = asyncio.create_task(self._run_until_disconnected())
        except Exception as e:
            self._last_error = str(e)
            logger.exception("connect_and_maybe_start error")

    async def _run_until_disconnected(self) -> None:
        try:
            await self.client.run_until_disconnected()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("Telethon disconnected with error: %s", e)
            self._last_error = str(e)

    async def start_login(self) -> dict:
        """Send SMS code to phone. Caller must then submit code."""
        if not self._ensure_client():
            raise RuntimeError(self._last_error or "Telethon non configuré")
        async with self._login_lock:
            if not self.client.is_connected():
                await self.client.connect()
            if await self.client.is_user_authorized():
                self._authorized = True
                return {"status": "already_authorized"}
            logger.info("Requesting Telegram code for %s", self.phone_number)
            sent = await self.client.send_code_request(self.phone_number)
            self._phone_code_hash = sent.phone_code_hash
            self._login_in_progress = True
            return {"status": "code_sent"}

    async def finish_login_with_code(self, code: str) -> dict:
        if not self._ensure_client():
            raise RuntimeError(self._last_error or "Telethon non configuré")
        async with self._login_lock:
            if not self._login_in_progress or not self._phone_code_hash:
                raise RuntimeError("Aucun login en cours. Appelez start_login d'abord.")
            if not self.client.is_connected():
                await self.client.connect()
            try:
                await self.client.sign_in(
                    phone=self.phone_number,
                    code=str(code).strip(),
                    phone_code_hash=self._phone_code_hash,
                )
            except SessionPasswordNeededError:
                raise  # caller handles -> 2FA password needed
            except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
                raise RuntimeError(f"Code invalide ou expiré: {type(e).__name__}")
            self._authorized = True
            self._login_in_progress = False
            self._phone_code_hash = None
            await self._register_handlers()
            logger.info("Telegram login OK -> handlers registered")
            return {"status": "authorized"}

    async def finish_login_with_password(self, password: str) -> dict:
        if not self._ensure_client():
            raise RuntimeError(self._last_error or "Telethon non configuré")
        async with self._login_lock:
            if not self.client.is_connected():
                await self.client.connect()
            await self.client.sign_in(password=password)
            self._authorized = True
            self._login_in_progress = False
            await self._register_handlers()
            return {"status": "authorized"}

    async def _register_handlers(self) -> None:
        """Attach NewMessage handler restricted to configured channels."""
        if not self.client or not self.channels or not self.parse_callback:
            return
        # Resolve entities once (helps Telegram push passive updates)
        try:
            await self.client.get_dialogs()
        except Exception as e:
            logger.debug("get_dialogs warn: %s", e)

        resolved = []
        for ch in self.channels:
            try:
                entity = await self.client.get_entity(ch)
                self._channel_entities[ch] = entity
                resolved.append(entity)
            except Exception as e:
                logger.warning("Cannot resolve channel '%s': %s", ch, e)

        if not resolved:
            logger.warning("No telegram channels resolved.")
            return

        # Remove old handlers first (idempotency on reconnect)
        for h, _ in list(self.client.list_event_handlers()):
            self.client.remove_event_handler(h)

        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=resolved),
        )
        names = [getattr(e, "title", getattr(e, "username", str(e))) for e in resolved]
        logger.info("Listening to %d channel(s): %s", len(resolved), names)

    async def _on_new_message(self, event) -> None:
        try:
            text = event.raw_text or ""
            if not text.strip():
                return
            chat = await event.get_chat()
            meta = {
                "message_id": event.message.id,
                "chat_id": event.chat_id,
                "chat_title": getattr(chat, "title", None) or getattr(chat, "username", None) or str(event.chat_id),
                "date": event.message.date.isoformat() if event.message.date else None,
                "sender_id": event.sender_id,
            }
            if self.parse_callback:
                await self.parse_callback(text, meta)
        except Exception:
            logger.exception("on_new_message error")

    async def reload_channels(self, channels: List[str]) -> None:
        self.channels = channels
        if self._authorized:
            await self._register_handlers()

    async def disconnect(self) -> None:
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
        if self.client and self.client.is_connected():
            await self.client.disconnect()

    def status(self) -> dict:
        return {
            "configured": bool(self.api_id and self.api_hash and self.phone_number),
            "authorized": self._authorized,
            "login_in_progress": self._login_in_progress,
            "connected": bool(self.client and self.client.is_connected()),
            "channels": self.channels,
            "phone": self.phone_number,
            "last_error": self._last_error,
        }


telegram_listener = TelegramListener()
