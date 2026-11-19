import re
import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import ChatPermissions, Message

from ..db import database as db
from ..handlers.moderation import is_admin

flood_log: dict[tuple[int, int], deque] = defaultdict(deque)
link_log: dict[int, float] = {}
media_log: dict[tuple[int, int], deque] = defaultdict(deque)

LINK_RE = re.compile(r"(https?://|t\.me/|www\.)\S+", re.IGNORECASE)

NSFW_WORDS = [
    "nsfw", "porn", "porno", "xxx", "xvideos", "xnxx", "onlyfans",
    "nude", "nudes", "naked", "boobs", "boob", "tits", "titties",
    "dick", "cock", "pussy", "fuck", "fucking", "fucker", "fucked",
    "bitch", "slut", "whore", "cum", "cumming", "orgasm",
    "masturbate", "masturbation", "hentai", "rule34", "erotic",
    "sexy", "horny", "lingerie", "anal", "blowjob", "handjob",
    "doggy", "creampie", "bukkake", "gangbang", "incest",
    "milf", "stepsister", "stepmom", "fetish", "bondage", "bdsm",
    "dildo", "vibrator", "penis", "vagina", "nipple", "semen",
    "sperm", "escort", "hooker", "stripper", "camgirl",
    "chut", "chuchi", "lund", "lauda", "gand", "gaand",
    "randi", "rundi", "kutti", "chudai", "bhosda", "bhosdi",
    "madarchod", "bhenchod", "banchod", "bakchod", "gandu",
    "chinal", "randibaaz", "gandi", "nangi", "nange",
]

SCAM_WORDS = [
    "free crypto", "click here now", "guaranteed profit",
    "betting fix", "hacked account", "clickbait",
]

NSFW_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in NSFW_WORDS) + r")\b",
    re.IGNORECASE,
)

MEDIA_TYPES = ("sticker", "animation", "video", "video_note", "photo", "audio", "document")


def parse_bool(v) -> bool:
    return bool(v)


class GuardMiddleware(BaseMiddleware):
    """Group protection: lockdown, NSFW, stickers, flood, links, caps, bots."""

    async def __call__(self, handler, event: Message, data: dict):
        if event.chat.type == "private":
            return await handler(event, data)

        user = event.from_user
        if user is None or user.is_bot:
            return await handler(event, data)

        settings = await db.get_chat_settings(event.chat.id)
        admin = await is_admin(event.bot, event.chat.id, user.id)

        # service messages (join/leave) never lockdown-blocked
        is_service = bool(event.new_chat_members or event.left_chat_member)

        # lockdown: only admins may send
        if settings["lockdown"] and not admin and not is_service:
            await self._try_delete(event)
            return None

        # join: anti-bot kick, then let welcome handler run
        if event.new_chat_members:
            if settings["antibot"] and not admin:
                me = await event.bot.get_me()
                for member in event.new_chat_members:
                    if member.is_bot and member.id != me.id:
                        try:
                            await event.bot.ban_chat_member(event.chat.id, member.id)
                            await event.bot.unban_chat_member(event.chat.id, member.id)
                        except Exception:
                            pass
                        try:
                            await event.answer(
                                f"🤖 Bot <b>{member.first_name}</b> removed (anti-bot ON)"
                            )
                        except Exception:
                            pass
            return await handler(event, data)

        if event.left_chat_member:
            return await handler(event, data)

        if admin:
            return await handler(event, data)

        now = time.time()
        key = (event.chat.id, user.id)

        # anti-flood
        if settings["antiflood"]:
            dq = flood_log[key]
            dq.append(now)
            while dq and now - dq[0] > 8:
                dq.popleft()
            if len(dq) > 6:
                await self._punish(event, user, "🚫 Flooding (message spam)", mute=True)
                return None

        # anti-sticker / media spam
        has_media = getattr(event, "sticker", None) or getattr(event, "animation", None) \
            or getattr(event, "video_note", None) or getattr(event, "video", None)

        if has_media and settings["antisticker"]:
            mdq = media_log[key]
            mdq.append(now)
            while mdq and now - mdq[0] > 10:
                mdq.popleft()
            if len(mdq) > 4:
                await self._punish(event, user, "🎬 Media flood", mute=True)
                return None
            await self._try_delete(event)
            try:
                await event.answer(
                    f"⛔ Stickers/media not allowed here, {user.first_name}!"
                )
            except Exception:
                pass
            return None

        text = (event.text or event.caption or "").strip()
        if not text or text.startswith("/"):
            return await handler(event, data)

        # anti-link
        if settings["antilink"] and LINK_RE.search(text):
            if now - link_log.get(event.chat.id, 0) > 2:
                link_log[event.chat.id] = now
                await self._punish(event, user, "🔗 Links are not allowed")
            return None

        # caps lock
        if settings["anticaps"]:
            letters = [c for c in text if c.isalpha()]
            if len(text) > 20 and letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
                await self._punish(event, user, "🔇 Stop SHOUTING (caps lock)")
                return None

        # NSFW / 18+ / scam
        if settings["antinsfw"]:
            if NSFW_RE.search(text) or any(w in text.lower() for w in SCAM_WORDS):
                await self._punish(event, user, "🔞 18+ / banned content")
                return None

        # per-chat word filters
        filters = await db.get_word_filters(event.chat.id)
        if filters:
            low = text.lower()
            hit = next((w for w in filters if w in low), None)
            if hit:
                await self._punish(event, user, f"⛔ Banned word: <code>{hit}</code>")
                return None

        return await handler(event, data)

    async def _try_delete(self, event: Message) -> None:
        try:
            await event.delete()
        except Exception:
            pass

    async def _punish(self, event: Message, user, reason: str, mute: bool = False) -> None:
        await self._try_delete(event)
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
                await event.answer(f"🔇 {name} muted 10m — {reason} ({warns}/3)")
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
