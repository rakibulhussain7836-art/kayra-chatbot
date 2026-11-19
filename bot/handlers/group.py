import datetime as dt
import html
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import settings
from ..db import database as db
from .moderation import is_admin

router = Router(name="group")

TOGGLE_KEYS = [
    ("antilink", "Anti-link"),
    ("antiflood", "Anti-flood"),
    ("antinsfw", "Anti-NSFW (18+)"),
    ("antisticker", "Anti-sticker/media"),
    ("anticaps", "Anti-caps"),
    ("antibot", "Anti-bot"),
    ("welcome_on", "Welcome message"),
    ("goodbye_on", "Goodbye message"),
    ("lockdown", "Lockdown (admins only)"),
]

DEFAULT_WELCOME = (
    "🌸 <b>Welcome {name}!</b>\n"
    "You just met the smartest bestie in the group — that's me, {bot}! ✨\n"
    "Talk to me in Hindi or English, play games, earn coins 💰\n"
    "Type /help to see everything I can do!"
)

DEFAULT_GOODBYE = "👋 <b>{name}</b> left the group. Stay safe!"

DEFAULT_RULES = (
    "📜 <b>Group Rules</b>\n\n"
    "1️⃣ No 18+ / NSFW content\n"
    "2️⃣ No spam, flooding or bulk stickers\n"
    "3️⃣ No random links or promos\n"
    "4️⃣ Be respectful — no abuse\n"
    "5️⃣ English + Hindi both fine\n"
    "6️⃣ Listen to admins 🛡️"
)


def _name(user) -> str:
    return html.escape(user.first_name or user.username or "Someone")


def parse_duration(arg: str) -> int | None:
    """Return minutes, or None if invalid."""
    arg = (arg or "").strip().lower()
    if not arg:
        return None
    m = re.fullmatch(r"(\d+)([smhd])?", arg)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2) or "m"
    mult = {"s": 1 / 60, "m": 1, "h": 60, "d": 1440}[unit]
    mins = int(n * mult)
    return max(1, mins)


def settings_kb(row) -> InlineKeyboardMarkup:
    def mark(v: int) -> str:
        return "✅" if v else "❌"

    buttons = []
    for key, label in TOGGLE_KEYS:
        buttons.append(
            InlineKeyboardButton(
                text=f"{mark(row[key])} {label}",
                callback_data=f"gset:{key}",
            )
        )
    kb_rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    kb_rows.append(
        [InlineKeyboardButton(text="📜 Rules", callback_data="gset:show_rules")]
    )
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def _fill(template: str, user, chat_title: str, member_count: int) -> str:
    bot_name = settings.bot_name
    return (
        template.replace("{name}", _name(user))
        .replace("{id}", str(user.id))
        .replace("{username}", "@" + user.username if user.username else "—")
        .replace("{bot}", bot_name)
        .replace("{title}", html.escape(chat_title or "this group"))
        .replace("{count}", str(member_count))
    )


# ---------------- settings panel ----------------

@router.message(Command("settings", "gsettings", "groupsettings"))
async def cmd_settings(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Ye command sirf groups mein chalta hai 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    row = await db.get_chat_settings(message.chat.id)
    title = message.chat.title or "Group"
    await message.answer(
        f"🛡️ <b>Group Settings — {html.escape(title)}</b>\n\n"
        f"Tap any row to toggle it.",
        reply_markup=settings_kb(row),
    )


@router.callback_query(F.data.startswith("gset:"))
async def cb_gset(cb: CallbackQuery) -> None:
    key = cb.data.split(":", 1)[1]
    chat_id = cb.message.chat.id
    if not await is_admin(cb.bot, chat_id, cb.from_user.id):
        await cb.answer("Admins only 🛡️", show_alert=True)
        return

    if key == "show_rules":
        row = await db.get_chat_settings(chat_id)
        text = row["rules"] or DEFAULT_RULES
        await cb.answer()
        try:
            await cb.message.answer(text)
        except Exception:
            pass
        return

    if key not in dict(TOGGLE_KEYS):
        await cb.answer()
        return

    row = await db.get_chat_settings(chat_id)
    new_val = 0 if row[key] else 1
    await db.set_chat_setting(chat_id, key, new_val)
    row = await db.get_chat_settings(chat_id)
    label = dict(TOGGLE_KEYS)[key]
    state = "ON ✅" if new_val else "OFF ❌"
    try:
        await cb.message.edit_reply_markup(reply_markup=settings_kb(row))
    except Exception:
        pass
    await cb.answer(f"{label}: {state}")


# ---------------- welcome / goodbye / rules ----------------

@router.message(Command("setwelcome"))
async def cmd_setwelcome(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 and not message.reply_to_message:
        await message.answer(
            "Usage: <code>/setwelcome Welcome {name}!</code>\n"
            "Or reply to a message with <code>/setwelcome</code>\n"
            "Placeholders: {name} {id} {username} {bot} {count} {title}"
        )
        return
    if message.reply_to_message:
        content = message.reply_to_message.text or message.reply_to_message.caption or ""
    else:
        content = parts[1]
    await db.set_chat_setting(message.chat.id, "welcome_text", content)
    await db.set_chat_setting(message.chat.id, "welcome_on", 1)
    await message.answer("✅ Custom welcome saved & turned ON")


@router.message(Command("setgoodbye"))
async def cmd_setgoodbye(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 and not message.reply_to_message:
        await message.answer(
            "Usage: <code>/setgoodbye Bye {name}!</code>\n"
            "Or reply to a message with <code>/setgoodbye</code>"
        )
        return
    if message.reply_to_message:
        content = message.reply_to_message.text or message.reply_to_message.caption or ""
    else:
        content = parts[1]
    await db.set_chat_setting(message.chat.id, "goodbye_text", content)
    await db.set_chat_setting(message.chat.id, "goodbye_on", 1)
    await message.answer("✅ Custom goodbye saved & turned ON")


@router.message(Command("setrules"))
async def cmd_setrules(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 and not message.reply_to_message:
        await message.answer(
            "Usage: <code>/setrules No spam, be nice...</code>\n"
            "Or reply to a message with <code>/setrules</code>"
        )
        return
    if message.reply_to_message:
        content = message.reply_to_message.text or message.reply_to_message.caption or ""
    else:
        content = parts[1]
    await db.set_chat_setting(message.chat.id, "rules", content)
    await message.answer("✅ Group rules saved")


@router.message(Command("rules"))
async def cmd_rules(message: Message) -> None:
    row = await db.get_chat_settings(message.chat.id)
    await message.answer(row["rules"] or DEFAULT_RULES)


@router.message(F.new_chat_members)
async def on_join(message: Message) -> None:
    row = await db.get_chat_settings(message.chat.id)
    if not row["welcome_on"]:
        return
    me = await message.bot.get_me()
    template = row["welcome_text"] or DEFAULT_WELCOME
    try:
        count = await message.bot.get_chat_member_count(message.chat.id)
    except Exception:
        count = 0
    for user in message.new_chat_members:
        if user.id == me.id or user.is_bot:
            continue
        try:
            await message.answer(
                _fill(template, user, message.chat.title or "", count)
            )
        except Exception:
            pass


@router.message(F.left_chat_member)
async def on_leave(message: Message) -> None:
    row = await db.get_chat_settings(message.chat.id)
    if not row["goodbye_on"]:
        return
    user = message.left_chat_member
    if user is None or user.is_bot:
        return
    template = row["goodbye_text"] or DEFAULT_GOODBYE
    try:
        await message.answer(_fill(template, user, message.chat.title or "", 0))
    except Exception:
        pass


# ---------------- lockdown / slowmode ----------------

@router.message(Command("lockdown", "lock"))
async def cmd_lockdown(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    arg = (message.text or "").split(maxsplit=1)
    arg = arg[1].strip().lower() if len(arg) > 1 else ""
    row = await db.get_chat_settings(message.chat.id)
    if arg in ("off", "0", "disable", "unlock"):
        await db.set_chat_setting(message.chat.id, "lockdown", 0)
        await message.answer("🔓 <b>Lockdown OFF</b> — everyone can talk again")
    elif arg in ("on", "1", "enable", "lock"):
        await db.set_chat_setting(message.chat.id, "lockdown", 1)
        await message.answer("🔒 <b>Lockdown ON</b> — only admins can send")
    else:
        new_val = 0 if row["lockdown"] else 1
        await db.set_chat_setting(message.chat.id, "lockdown", new_val)
        state = "ON 🔒" if new_val else "OFF 🔓"
        await message.answer(f"Lockdown <b>{state}</b>")


@router.message(Command("slowmode"))
async def cmd_slowmode(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "Usage: <code>/slowmode 5</code> (seconds, 0 = off)"
        )
        return
    secs = min(int(parts[1]), 86400)
    try:
        await message.bot.set_chat_slow_mode(message.chat.id, slow_mode_delay=secs)
    except Exception:
        await message.answer("Slowmode fail — bot ko admin banao 🛡️")
        return
    if secs == 0:
        await message.answer("⚡ Slowmode OFF")
    else:
        await message.answer(f"🐢 Slowmode set: <b>{secs}s</b>")


# ---------------- message tools ----------------

@router.message(Command("purge"))
async def cmd_purge(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    parts = (message.text or "").split(maxsplit=1)
    count = 20
    if len(parts) > 1 and parts[1].strip().isdigit():
        count = max(1, min(int(parts[1]), 100))

    start_id = message.message_id - count
    if message.reply_to_message:
        start_id = message.reply_to_message.message_id
    start_id = max(1, start_id)
    end_id = message.message_id

    ids = list(range(start_id, end_id + 1))
    deleted = 0
    try:
        msgs = await message.bot.get_messages(message.chat.id, message_ids=ids)
        for m in msgs:
            if m is None:
                continue
            try:
                await m.delete()
                deleted += 1
            except Exception:
                pass
    except Exception:
        await message.answer("Purge fail — bot ko <b>delete messages</b> permission do 🛡️")
        return

    try:
        confirm = await message.answer(f"🧹 Purged <b>{deleted}</b> messages")
        await confirm.delete()
    except Exception:
        pass


@router.message(Command("del", "delete"))
async def cmd_del(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    target = message.reply_to_message
    if not target:
        await message.answer("Reply to a message with <code>/del</code>")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        if target.from_user and target.from_user.id != message.from_user.id:
            await message.answer("Admins only (ya apna message khud delete karo)")
            return
    try:
        await target.delete()
        await message.delete()
    except Exception:
        await message.answer("Delete fail — bot ko permission do 🛡️")


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    target = message.reply_to_message
    if not target or not target.from_user:
        await message.answer("Reply to a bad message with <code>/report</code>")
        return
    reporter = message.from_user
    reported = target.from_user
    if reported.id == reporter.id:
        await message.answer("Apni message report nahi kar sakte 😅")
        return
    text = (
        "🚨 <b>New Report</b>\n"
        f"Group: {html.escape(message.chat.title or '—')}\n"
        f"By: {_name(reporter)} (<code>{reporter.id}</code>)\n"
        f"User: {_name(reported)} (<code>{reported.id}</code>)\n"
        f"Reason: <i>{html.escape((target.text or target.caption or '[media]')[:200])}</i>\n\n"
        "Admins — take action with /warn /mute /ban"
    )
    # notify admins in the chat
    notified = 0
    try:
        admins = await message.bot.get_chat_administrators(message.chat.id)
        for a in admins:
            if a.user.is_bot:
                continue
            try:
                await message.bot.send_message(a.user.id, text)
                notified += 1
            except Exception:
                pass
    except Exception:
        pass
    if notified:
        await message.answer(f"✅ Reported — {notified} admin(s) notified")
    else:
        await message.answer(
            "⚠️ Couldn't DM admins (they must <b>start</b> the bot first). "
            "Report logged here for group admins."
        )
        await message.answer(text)


# ---------------- word filters ----------------

@router.message(Command("filter"))
async def cmd_filter(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: <code>/filter badword</code>")
        return
    ok = await db.add_word_filter(message.chat.id, parts[1])
    if ok:
        await message.answer(f"✅ Filter added: <code>{html.escape(parts[1].strip().lower())}</code>")
    else:
        await message.answer("Already filtered ya invalid")


@router.message(Command("unfilter"))
async def cmd_unfilter(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: <code>/unfilter badword</code>")
        return
    ok = await db.remove_word_filter(message.chat.id, parts[1])
    if ok:
        await message.answer(f"🗑️ Filter removed: <code>{html.escape(parts[1].strip().lower())}</code>")
    else:
        await message.answer("Not found")


@router.message(Command("filters"))
async def cmd_filters(message: Message) -> None:
    words = await db.get_word_filters(message.chat.id)
    if not words:
        await message.answer("No custom word filters. Add with <code>/filter word</code>")
        return
    listed = "\n".join(f"• <code>{html.escape(w)}</code>" for w in words[:50])
    more = f"\n… +{len(words) - 50} more" if len(words) > 50 else ""
    await message.answer(f"🚫 <b>Word filters ({len(words)})</b>\n{listed}{more}")


# ---------------- info ----------------

@router.message(Command("id", "whois"))
async def cmd_id(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    if len(parts) > 1 and parts[1].strip().isdigit():
        uid = int(parts[1])
        try:
            member = await message.bot.get_chat_member(message.chat.id, uid)
            target = member.user
        except Exception:
            await message.answer(f"User <code>{uid}</code> not found in this chat")
            return
    lines = [
        f"👤 <b>{_name(target)}</b>",
        f"ID: <code>{target.id}</code>",
        f"Username: {('@' + target.username) if target.username else '—'}",
        f"Chat ID: <code>{message.chat.id}</code>",
    ]
    if message.chat.type != "private":
        try:
            member = await message.bot.get_chat_member(message.chat.id, target.id)
            lines.append(f"Status: <b>{member.status}</b>")
        except Exception:
            pass
    await message.answer("\n".join(lines))


@router.message(Command("adminlist", "admins"))
async def cmd_adminlist(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    try:
        admins = await message.bot.get_chat_administrators(message.chat.id)
    except Exception:
        await message.answer("Fail — bot admin hai na?")
        return
    lines = ["🛡️ <b>Admins</b>"]
    for a in admins:
        u = a.user
        if u.is_bot:
            continue
        role = "👑 Creator" if a.status == "creator" else "⚙️ Admin"
        uname = f" (@{u.username})" if u.username else ""
        lines.append(f"• {_name(u)}{uname} — {role}")
    await message.answer("\n".join(lines))


@router.message(Command("tagall", "mention", "all"))
async def cmd_tagall(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    text = (message.text or "").split(maxsplit=1)
    reason = text[1] if len(text) > 1 else "📢 Attention!"
    rows = await db.many(
        "SELECT user_id FROM chat_xp WHERE chat_id = ? ORDER BY xp DESC LIMIT 50",
        (message.chat.id,),
    )
    if not rows:
        await message.answer("No active members to tag yet.")
        return
    mentions = " ".join(
        f'<a href="tg://user?id={r["user_id"]}">•</a>' for r in rows
    )
    await message.answer(
        f"{html.escape(reason)}\n{mentions}",
        disable_web_page_preview=True,
    )


# ---------------- mute with duration ----------------

@router.message(Command("mute"))
async def cmd_mute_dur(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    if not message.reply_to_message:
        await message.answer(
            "Reply to a user: <code>/mute</code> or <code>/mute 15m</code>\n"
            "Units: s / m / h / d (default 30m)"
        )
        return
    parts = (message.text or "").split(maxsplit=1)
    minutes = 30
    if len(parts) > 1:
        parsed = parse_duration(parts[1])
        if parsed is None:
            await message.answer("Invalid duration. Example: <code>/mute 15m</code>")
            return
        minutes = parsed
    target = message.reply_to_message.from_user
    if await is_admin(message.bot, message.chat.id, target.id):
        await message.answer("Admin ko mute nahi kar sakte")
        return
    until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    try:
        await message.bot.restrict_chat_member(
            message.chat.id, target.id,
            permissions=ChatPermissions(),
            until_date=until,
        )
    except Exception:
        await message.answer("Mute fail — bot ko admin banao 🛡️")
        return
    human = (
        f"{minutes}m" if minutes < 60
        else f"{minutes // 60}h" if minutes < 1440
        else f"{minutes // 1440}d"
    )
    await message.answer(f"🔇 {_name(target)} muted for <b>{human}</b>")


@router.message(Command("unban"))
async def cmd_unban(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("Groups only 🛡️")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("Admins only 🛡️")
        return
    parts = (message.text or "").split(maxsplit=1)
    uid = None
    if len(parts) > 1 and parts[1].strip().isdigit():
        uid = int(parts[1])
    elif message.reply_to_message and message.reply_to_message.from_user:
        uid = message.reply_to_message.from_user.id
    if uid is None:
        await message.answer("Usage: reply to user or <code>/unban user_id</code>")
        return
    try:
        await message.bot.unban_chat_member(message.chat.id, uid)
    except Exception:
        await message.answer("Unban fail — bot admin hai na?")
        return
    await message.answer(f"✅ Unbanned <code>{uid}</code>")
