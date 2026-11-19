import time

from aiogram import BaseMiddleware, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import settings

router = Router(name="forcejoin")

_member_cache: dict[int, tuple[bool, float]] = {}
_prompt_ts: dict[int, float] = {}
CACHE_TTL = 300.0
PROMPT_COOLDOWN = 30.0


def join_url() -> str:
    ch = settings.force_channel.lstrip("@")
    return f"https://t.me/{ch}"


async def is_member(bot, user_id: int, force: bool = False) -> bool:
    now = time.time()
    if not force:
        cached = _member_cache.get(user_id)
        if cached and now - cached[1] < CACHE_TTL:
            return cached[0]

    ok = False
    try:
        m = await bot.get_chat_member(settings.force_channel, user_id)
        ok = m.status in ("member", "administrator", "creator", "restricted")
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "not participant" in msg or "user not found" in msg or "left" in msg:
            ok = False
        else:
            # bot likely can't access channel yet (not admin) — don't brick the bot
            ok = True
            import logging

            logging.getLogger("kayra.forcejoin").warning(
                "membership check failed (add bot as channel admin?): %s", e
            )

    _member_cache[user_id] = (ok, now)
    return ok


def _prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join Channel", url=join_url())],
            [InlineKeyboardButton(text="✅ I Joined — Check", callback_data="fj:check")],
        ]
    )


class ForceJoinMiddleware(BaseMiddleware):
    """Block anyone who hasn't joined the channel."""

    async def __call__(self, handler, event, data):
        if not settings.force_channel:
            return await handler(event, data)

        # allow our own verify callback through
        if isinstance(event, CallbackQuery) and (event.data or "").startswith("fj:"):
            return await handler(event, data)

        user = None
        chat_id = None
        if isinstance(event, Message):
            if event.new_chat_members or event.left_chat_member:
                return await handler(event, data)
            user = event.from_user
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            chat_id = event.message.chat.id if event.message else 0
        else:
            return await handler(event, data)

        if user is None or user.is_bot:
            return await handler(event, data)

        if await is_member(event.bot, user.id):
            return await handler(event, data)

        # not a member — block
        if isinstance(event, CallbackQuery):
            await event.answer(
                "❌ Pehle channel join karo, phir check karo!", show_alert=True
            )
            return None

        now = time.time()
        if now - _prompt_ts.get(chat_id, 0) < PROMPT_COOLDOWN:
            return None
        _prompt_ts[chat_id] = now
        try:
            await event.answer(
                "🔒 <b>Force Join Required!</b>\n\n"
                f"Sirf <b>{settings.force_channel}</b> members hi "
                f"{settings.bot_name} ko use kar sakte hain.\n\n"
                "1️⃣ Channel join karo\n"
                "2️⃣ Phir <b>I Joined</b> dabao",
                reply_markup=_prompt_kb(),
            )
        except Exception:
            pass
        return None


@router.callback_query(lambda c: c.data == "fj:check")
async def cb_joined(cb: CallbackQuery) -> None:
    if not settings.force_channel:
        await cb.answer()
        return
    if await is_member(cb.bot, cb.from_user.id, force=True):
        try:
            await cb.message.edit_text(
                "✅ <b>Verified!</b> Welcome aboard 🌸 Ab sab commands use karo — /start se shuru karo!"
            )
        except Exception:
            pass
        await cb.answer("Verified! 🎉")
    else:
        await cb.answer(
            "❌ Abhi tak member nahi dikhe — pehle join karo!", show_alert=True
        )
