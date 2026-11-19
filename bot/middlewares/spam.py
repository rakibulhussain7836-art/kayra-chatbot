import re
import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import ChatPermissions, Message

from ..db import database as db
from ..handlers.moderation import BANNED_WORDS, is_admin

flood_log: dict[tuple[int, int], deque] = defaultdict(deque)
link_log: dict[int, float] = {}

LINK_RE = re.compile(r"(https?://|t\.me/|www\.)\S+", re.IGNORECASE)


class SpamMiddleware(BaseMiddleware):
    """Anti-flood / anti-link / caps / banned-words for groups."""

    async def __call__(self, handler, event: Message, data: dict):
        if event.chat.type == "private":
            return await handler(event, data)
        user = event.from_user
        if user is None or user.is_bot:
            return await handler(event, data)
        if await is_admin(event.bot, event.chat.id, user.id):
            return await handler(event, data)

        text = (event.text or event.caption or "").strip()
        now = time.time()

        # flood: >6 messages in 8 seconds
        key = (event.chat.id, user.id)
        dq = flood_log[key]
        dq.append(now)
        while dq and now - dq[0] > 8:
            dq.popleft()
        if len(dq) > 6:
            await self._punish(event, user, "🚫 Flooding (message spam)", mute=True)
            return None

        if not text or text.startswith("/"):
            return await handler(event, data)

        # links
        if LINK_RE.search(text):
            if now - link_log.get(event.chat.id, 0) > 2:
                link_log[event.chat.id] = now
                await self._punish(event, user, "🔗 Links are not allowed", mute=False)
            return None

        # caps lock
        letters = [c for c in text if c.isalpha()]
        if len(text) > 20 and letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
            await self._punish(event, user, "🔇 Stop SHOUTING (caps lock)", mute=False)
            return None

        # banned words
        low = text.lower()
        hit = next((w for w in BANNED_WORDS if w in low), None)
        if hit:
            await self._punish(event, user, "⛔ Not allowed content", mute=False)
            return None

        return await handler(event, data)

    async def _punish(self, event: Message, user, reason: str, mute: bool) -> None:
        try:
            await event.delete()
        except Exception:
            pass
        w = await db.ensure_user(user.id, user.username or "", user.first_name or "")
        warns = w["warnings"] + 1
        await db.run("UPDATE users SET warnings = ? WHERE user_id = ?", (warns, user.id))

        name = user.first_name or user.username or "Someone"
        if mute:
            import datetime as dt

            try:
                await event.bot.restrict_chat_member(
                    event.chat.id, user.id,
                    permissions=ChatPermissions(),
                    until_date=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
                )
                await event.answer(
                    f"🔇 {name} muted 10m — {reason} ({warns}/3)"
                )
                return
            except Exception:
                pass

        if warns >= 3:
            try:
                await event.bot.ban_chat_member(event.chat.id, user.id)
                await event.bot.unban_chat_member(event.chat.id, user.id)
                await event.answer(f"🚨 {name} kicked — 3 warnings! {reason}")
            except Exception:
                await event.answer(f"⚠️ {name}: {reason} ({warns}/3)")
        else:
            await event.answer(f"⚠️ {name}: {reason} ({warns}/3)")
