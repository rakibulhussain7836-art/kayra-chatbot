from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import settings
from ..db import database as db

router = Router(name="start")


def main_keyboard(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Karya to Your Group",
                    url=f"https://t.me/{username}?startgroup=true",
                )
            ],
            [
                InlineKeyboardButton(text="📚 View Commands", callback_data="help:main"),
                InlineKeyboardButton(text="💬 How to Chat", callback_data="help:chat"),
            ],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    await db.ensure_user(user.id, user.username or "", user.first_name or "")
    bot_user = await message.bot.get_me()
    name = user.first_name or "bestie"

    text = (
        f"🌸 <b>WELCOME TO {settings.bot_name.upper()}!</b>\n"
        f"Hi {name}! I'm your personal AI bestie, game host &amp; group protector ✨\n\n"
        f"🗣️ <b>Chat with me in Hindi or English</b> — main dono mein baat karta hoon, "
        f"bina lag ke!\n"
        f" Just send me a message (DM me, or add me to a group and mention me).\n\n"
        f"🎮 <b>Play &amp; Earn Coins</b>\n"
        f"Fast mini-games like <code>/math</code>, <code>/trivia</code>, "
        f"<code>/scramble</code> &amp; lucky coin drops!\n\n"
        f"💰 <b>Economy</b>\n"
        f"Daily coins, levels, shop &amp; leaderboards — <code>/profile</code>, "
        f"<code>/daily</code>, <code>/shop</code>\n\n"
        f"🛡️ <b>Group Protection</b>\n"
        f"Anti-spam locks keep your group clean 24/7.\n\n"
        f"<i>Tap a button below to explore or invite me to your group!</i>"
    )
    await message.answer(text, reply_markup=main_keyboard(bot_user.username))


@router.callback_query(F.data == "help:chat")
async def cb_chat_guide(cb: CallbackQuery) -> None:
    text = (
        f"💬 <b>How to chat with {settings.bot_name}</b>\n\n"
        f"• <b>Private chat:</b> just type anything — I reply instantly in the "
        f"same language (Hindi 🇮🇳 or English 🇬🇧)\n"
        f"• <b>In a group:</b> reply to my message OR type "
        f"<code>@{settings.bot_name.lower()}_bot your message</code>\n"
        f"• Commands like <code>/math</code>, <code>/daily</code> work anywhere "
        f"without mentioning\n\n"
        f"Examples:\n"
        f"→ <i>kaise ho Karya?</i> → Hindi mein reply\n"
        f"→ <i>tell me a joke</i> → English mein reply"
    )
    await cb.message.edit_text(text, reply_markup=main_keyboard((await cb.bot.get_me()).username))
    await cb.answer()
