import re
import time
from collections import defaultdict, deque

from aiogram import F, Router
from aiogram.types import Message

from ..ai.client import ai_client
from ..ai.language import detect
from ..ai.persona import system_prompt
from ..config import settings

router = Router(name="chat")

HISTORY: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))
LAST_AI: dict[int, float] = {}
COOLDOWN_DM = 2.0
COOLDOWN_GROUP = 4.0


def _strip_mention(text: str, username: str) -> str:
    return re.sub(rf"@{re.escape(username)}\b", "", text, flags=re.IGNORECASE).strip()


@router.message(F.text)
async def ai_chat(message: Message) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    # let active group games grab answers first
    from .games import try_game_answer

    if await try_game_answer(message):
        return

    chat = message.chat
    user = message.from_user
    if user is None:
        return

    bot_user = await message.bot.get_me()

    if chat.type != "private":
        reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == bot_user.id
        )
        mentioned = f"@{bot_user.username.lower()}" in text.lower()
        if not (reply_to_bot or mentioned):
            return
        text = _strip_mention(text, bot_user.username)

    if not text:
        text = "hi"

    now = time.monotonic()
    cooldown = COOLDOWN_DM if chat.type == "private" else COOLDOWN_GROUP
    key = user.id if chat.type == "private" else chat.id
    if now - LAST_AI.get(key, 0) < cooldown:
        return
    LAST_AI[key] = now

    lang = detect(text)
    history = HISTORY[chat.id]
    history.append({"role": "user", "content": text})

    await message.bot.send_chat_action(chat.id, "typing")

    from .persona_cmd import persona_chat

    try:
        reply = await persona_chat(message, text, list(history))
        if reply is None:
            reply = await ai_client.chat(
                messages=list(history),
                system=system_prompt(settings.bot_name, lang),
            )
    except Exception:
        reply = "AI busy hai abhi 😅 thodi der baad try karo bestie!"

    history.append({"role": "assistant", "content": reply})
    await message.reply(reply)
