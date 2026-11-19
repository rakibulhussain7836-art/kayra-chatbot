import html
import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..ai.client import ai_client
from ..ai.language import detect
from ..config import settings
from ..db import database as db

router = Router(name="persona")

# chat_id -> {"text": str, "expires": float}
custom_personas: dict[int, dict] = {}

BRIBE_COST = 500
BRIBE_SECONDS = 3600


@router.message(Command("settitle"))
async def cmd_settitle(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "🎩 Usage: <code>/settitle Cool Guy</code> (500 coins)\n"
            "Title dikhega tumhare /profile mein"
        )
        return
    title = parts[1].strip()[:30]
    if not await db.spend_coins(message.from_user.id, 500):
        await message.answer("Title 500 coins ka hai 💸")
        return
    await db.run(
        "UPDATE users SET title = ? WHERE user_id = ?", (title, message.from_user.id)
    )
    await message.answer(f"🎩 Title set: <b>{html.escape(title)}</b> (-500 coins)")


@router.message(Command("bribe"))
async def cmd_bribe(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            f"😈 <b>Custom AI Persona</b>\n"
            f"Bribe me {BRIBE_COST} coins for 1 hour of a custom personality "
            f"in this chat!\n\n"
            f"Usage: <code>/bribe you are a pirate captain who loves treasure</code>"
        )
        return
    persona_text = parts[1].strip()[:300]
    if not await db.spend_coins(message.from_user.id, BRIBE_COST):
        await message.answer(f"Bribe costs {BRIBE_COST} coins 💸 — kam pad rahe hain!")
        return
    custom_personas[message.chat.id] = {
        "text": persona_text,
        "expires": time.time() + BRIBE_SECONDS,
        "by": message.from_user.id,
    }
    await message.answer(
        f"😈 <b>Persona accepted!</b> (-{BRIBE_COST} coins)\n"
        f"For the next <b>1 hour</b>, I'll act as:\n"
        f"<i>{html.escape(persona_text)}</i>\n\n"
        f"Normal mode: /revert"
    )


@router.message(Command("revert"))
async def cmd_revert(message: Message) -> None:
    if message.chat.id in custom_personas:
        custom_personas.pop(message.chat.id, None)
        await message.answer(f"😌 Back to normal {settings.bot_name} mode!")
    else:
        await message.answer("Koi custom persona active nahi hai — normal hi hoon 😇")


def active_persona(chat_id: int) -> str | None:
    st = custom_personas.get(chat_id)
    if not st:
        return None
    if time.time() > st["expires"]:
        custom_personas.pop(chat_id, None)
        return None
    return st["text"]


async def persona_chat(message: Message, text: str, history: list) -> str | None:
    """If a custom persona is active, answer with it; else None (use default flow)."""
    persona = active_persona(message.chat.id)
    if not persona:
        return None
    lang = detect(text)
    system = (
        f"You are {settings.bot_name} but currently roleplaying this custom persona "
        f"for this chat (bribe system): '{persona}'.\n"
        f"Stay in character, keep it fun and safe-for-work. "
        f"Reply in {'Hindi/Hinglish' if lang == 'hi' else 'English'}. "
        f"Keep it to 1-3 sentences."
    )
    return await ai_client.chat(history, system)
