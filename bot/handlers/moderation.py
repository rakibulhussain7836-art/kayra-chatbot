import html
import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import ChatPermissions, Message

from ..db import database as db

router = Router(name="moderation")

admin_cache: dict[tuple[int, int], tuple[bool, float]] = {}
ADMIN_TTL = 60.0

BANNED_WORDS = [
    "nsfw", "porn", "xxx", "onlyfans", "free crypto", "click here now",
    "guaranteed profit", "betting fix", "hacked account",
]

WELCOME = (
    "🌸 <b>Welcome {name}!</b>\n"
    "You just met the smartest bestie in the group — that's me, {bot}! ✨\n"
    "Talk to me in Hindi or English, play games, earn coins 💰\n"
    "Type /help to see everything I can do!"
)


async def is_admin(bot, chat_id: int, user_id: int) -> bool:
    key = (chat_id, user_id)
    cached = admin_cache.get(key)
    if cached and time.time() - cached[1] < ADMIN_TTL:
        return cached[0]
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        ok = member.status in ("creator", "administrator")
    except Exception:
        ok = False
    admin_cache[key] = (ok, time.time())
    return ok


async def _warns_inc(user_id: int) -> int:
    await db.ensure_user(user_id)
    row = await db.one("SELECT warnings FROM users WHERE user_id = ?", (user_id,))
    w = row["warnings"] + 1
    await db.run("UPDATE users SET warnings = ? WHERE user_id = ?", (w, user_id))
    return w


@router.message(Command("warn"))
async def cmd_warn(message: Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    if not message.reply_to_message:
        await message.answer("Reply to a user: <code>/warn reason</code>")
        return
    target = message.reply_to_message.from_user
    if await is_admin(message.bot, message.chat.id, target.id):
        await message.answer("Admin ko warn nahi kar sakte 😅")
        return
    w = await _warns_inc(target.id)
    reason = (message.text or "").split(maxsplit=1)
    reason = reason[1] if len(reason) > 1 else "No reason"
    if w >= 3:
        await db.run("UPDATE users SET warnings = 0 WHERE user_id = ?", (target.id,))
        try:
            await message.bot.ban_chat_member(message.chat.id, target.id)
            await message.bot.unban_chat_member(message.chat.id, target.id)
        except Exception:
            await message.answer("Kick fail (bot admin hai na?)")
            return
        await message.answer(
            f"🚨 {_name(target)} got 3 warnings — <b>KICKED</b>! "
            f"Reason: {html.escape(reason)}"
        )
    else:
        await message.answer(
            f"⚠️ {_name(target)} warned ({w}/3). Reason: {html.escape(reason)}"
        )


@router.message(Command("warns"))
async def cmd_warns(message: Message) -> None:
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    row = await db.ensure_user(target.id, target.username or "", target.first_name or "")
    await message.answer(f"⚠️ {_name(target)} has <b>{row['warnings']}</b> warning(s)")


@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    if not message.reply_to_message:
        await message.answer("Reply to a user: <code>/unwarn</code>")
        return
    target = message.reply_to_message.from_user
    await db.run("UPDATE users SET warnings = MAX(0, warnings - 1) WHERE user_id = ?", (target.id,))
    await message.answer(f"✅ Warning reduced for {_name(target)}")


@router.message(Command("mute"))
async def cmd_mute(message: Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    if not message.reply_to_message:
        await message.answer("Reply to a user: <code>/mute</code> (30 min)")
        return
    target = message.reply_to_message.from_user
    if await is_admin(message.bot, message.chat.id, target.id):
        await message.answer("Admin ko mute nahi kar sakte")
        return
    import datetime as dt

    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30)
    try:
        await message.bot.restrict_chat_member(
            message.chat.id, target.id,
            permissions=ChatPermissions(),
            until_date=until,
        )
    except Exception:
        await message.answer("Mute fail — bot ko admin banao 🛡️")
        return
    await message.answer(f"🔇 {_name(target)} muted for 30 minutes")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    if not message.reply_to_message:
        await message.answer("Reply to a user: <code>/unmute</code>")
        return
    target = message.reply_to_message.from_user
    try:
        await message.bot.restrict_chat_member(
            message.chat.id, target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_audio=True,
                can_send_documents=True,
                can_send_stickers=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_add_web_page_previews=True,
                can_invite_users=True,
                can_pin_messages=True,
                can_change_info=True,
            ),
        )
    except Exception:
        await message.answer("Unmute fail — bot admin hai na?")
        return
    await message.answer(f"🔊 {_name(target)} unmuted")


@router.message(Command("kick"))
async def cmd_kick(message: Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    if not message.reply_to_message:
        await message.answer("Reply to a user: <code>/kick</code>")
        return
    target = message.reply_to_message.from_user
    if await is_admin(message.bot, message.chat.id, target.id):
        await message.answer("Admin ko nahi kar sakte 😅")
        return
    try:
        await message.bot.ban_chat_member(message.chat.id, target.id)
        await message.bot.unban_chat_member(message.chat.id, target.id)
    except Exception:
        await message.answer("Kick fail — bot ko admin banao 🛡️")
        return
    await message.answer(f"👢 {_name(target)} kicked")


@router.message(Command("ban"))
async def cmd_ban(message: Message) -> None:
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    if not message.reply_to_message:
        await message.answer("Reply to a user: <code>/ban</code>")
        return
    target = message.reply_to_message.from_user
    if await is_admin(message.bot, message.chat.id, target.id):
        await message.answer("Admin ko nahi kar sakte 😅")
        return
    try:
        await message.bot.ban_chat_member(message.chat.id, target.id)
    except Exception:
        await message.answer("Ban fail — bot ko admin banao 🛡️")
        return
    await message.answer(f"🔨 {_name(target)} banned")


# ---------------- joins & welcome ----------------

@router.message(F.new_chat_members)
async def on_join(message: Message) -> None:
    me = await message.bot.get_me()
    for user in message.new_chat_members:
        if user.id == me.id:
            await message.answer(
                WELCOME.format(name="everyone", bot=me.first_name)
                + "\n\nI can also manage groups — make me <b>admin</b> for full protection 🛡️"
            )
            continue
        if user.is_bot:
            continue
        blob = f"{user.first_name or ''} {user.username or ''}".lower()
        hit = next((w for w in BANNED_WORDS if w in blob), None)
        if hit:
            try:
                await message.bot.ban_chat_member(message.chat.id, user.id)
                await message.bot.unban_chat_member(message.chat.id, user.id)
            except Exception:
                pass
            await message.answer(
                f"🛡️ Bio scanner: {_name(user)} blocked (suspicious name) ⛔"
            )
        else:
            await message.answer(
                WELCOME.format(name=_name(user), bot=me.first_name)
            )


@router.my_chat_member()
async def on_my_chat_member(event) -> None:
    status = event.new_chat_member.status
    if status in ("member", "administrator"):
        me = event.bot
        try:
            await event.message.answer(
                WELCOME.format(name="everyone", bot=event.new_chat_member.user.first_name)
                + "\n\nMake me <b>admin</b> for anti-spamp &amp; protection 🛡️"
            )
        except Exception:
            pass


def _name(user) -> str:
    return html.escape(user.first_name or user.username or "Someone")
