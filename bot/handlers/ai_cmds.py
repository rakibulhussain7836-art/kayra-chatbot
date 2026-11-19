import datetime as dt
import html
import random

import aiohttp
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..ai.client import ai_client
from ..ai.language import detect
from ..ai.persona import system_prompt
from ..config import settings
from ..db import database as db

router = Router(name="ai_cmds")

TIMEOUT = aiohttp.ClientTimeout(total=15)


def _parse_duration(s: str) -> int | None:
    s = s.strip().lower()
    try:
        if s.endswith("s"):
            return int(s[:-1])
        if s.endswith("m"):
            return int(s[:-1]) * 60
        if s.endswith("h"):
            return int(s[:-1]) * 3600
        if s.endswith("d"):
            return int(s[:-1]) * 86400
        return int(s) * 60
    except ValueError:
        return None


@router.message(Command("translate"))
async def cmd_translate(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "🌐 Usage: <code>/translate hindi Hello how are you</code>\n"
            "Also works: <code>/translate English namaste dosto</code>"
        )
        return
    target, text = parts[1], parts[2]
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        out = await ai_client.chat(
            [{"role": "user", "content": f"Translate this to {target} and reply ONLY with the translation:\n\n{text}"}],
            system="You are a precise translator. No explanations.",
            max_tokens=600,
        )
        await message.answer(f"🌐 <b>{html.escape(target)}</b>\n\n{html.escape(out)}")
    except Exception:
        await message.answer("Translation fail ho gayi 😅 dobara try karo")


@router.message(Command("shayari"))
async def cmd_shayari(message: Message) -> None:
    topic = (message.text or "").split(maxsplit=1)
    topic = topic[1] if len(topic) > 1 else random.choice(["pyaar", "dost", "zindagi", "baarish", "umeed"])
    await message.bot.send_chat_action(message.chat.id, "typing")
    lang = "hi"
    try:
        out = await ai_client.chat(
            [{"role": "user", "content": f"Ek beautiful Hindi shayari likho, topic: {topic}. Sirf shayari, 2-4 lines, koi heading nahi."}],
            system=system_prompt(settings.bot_name, lang),
            max_tokens=300,
        )
        await message.answer(f"🌹 <b>Shayari — {html.escape(topic)}</b>\n\n<i>{out}</i>")
    except Exception:
        await message.answer("Dil toota shayari likhne mein 😢 dobara try")


@router.message(Command("horoscope"))
async def cmd_horoscope(message: Message) -> None:
    sign = (message.text or "").split(maxsplit=1)
    sign = sign[1].strip() if len(sign) > 1 else random.choice(
        ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
    )
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        out = await ai_client.chat(
            [{"role": "user", "content": f"Aaj ka sassy, fun horoscope for {sign} — 2-3 lines, mix Hindi-English, with emojis. Mention love, work, money briefly."}],
            system=system_prompt(settings.bot_name, "hi"),
            max_tokens=250,
        )
        await message.answer(f"🔮 <b>Horoscope — {html.escape(sign)}</b>\n\n{out}")
    except Exception:
        await message.answer("Stars busy hain abhi 🔮 dobara try karo")


@router.message(Command("whatif"))
async def cmd_whatif(message: Message) -> None:
    scenario = (message.text or "").split(maxsplit=1)
    if len(scenario) < 2:
        await message.answer("Usage: <code>/whatif gravity became zero tomorrow</code>")
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        out = await ai_client.chat(
            [{"role": "user", "content": f"Creative, funny 'what if' scenario answer (3-4 lines, Hinglish ok, with emojis): {scenario[1]}"}],
            system=system_prompt(settings.bot_name, "en"),
            max_tokens=400,
        )
        await message.answer(f"🌀 <b>What If…</b>\n\n{out}")
    except Exception:
        await message.answer("Imagination crash ho gaya 😅 try again")


@router.message(Command("meme"))
async def cmd_meme(message: Message) -> None:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            async with session.get("https://meme-api.com/gimme") as resp:
                data = await resp.json()
        except Exception:
            await message.answer("Meme API down hai abhi 😅")
            return
    cap = html.escape(data.get("title", "meme"))
    url = data.get("url")
    if not url:
        await message.answer("Aaj ka meme miss ho gaya 😅")
        return
    await message.answer_photo(url, caption=f"😂 <b>{cap}</b>\n| r/{data.get('subreddit', 'memes')}")


@router.message(Command("lyrics"))
async def cmd_lyrics(message: Message) -> None:
    query = (message.text or "").split(maxsplit=1)
    if len(query) < 2:
        await message.answer("Usage: <code>/lyrics shape of you ed sheeran</code>")
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    headers = {"User-Agent": "KayraChatbot/1.0"}
    async with aiohttp.ClientSession(timeout=TIMEOUT, headers=headers) as session:
        try:
            async with session.get("https://lrclib.net/api/search", params={"q": query[1]}) as resp:
                data = await resp.json()
        except Exception:
            await message.answer("Lyrics service down hai 😅")
            return
    if not data:
        await message.answer("Koi lyrics nahi mili 🎵 Try: /lyrics <b>song name artist</b>")
        return
    item = data[0]
    plain = item.get("plainLyrics") or ""
    if not plain:
        await message.answer("Lyrics nahi mile is gaane ke 😅")
        return
    if len(plain) > 3500:
        plain = plain[:3500] + "\n… (truncated)"
    await message.answer(
        f"🎵 <b>{html.escape(item.get('trackName', 'Unknown'))}</b> — "
        f"{html.escape(item.get('artistName', ''))}\n\n<code>{html.escape(plain)}</code>"
    )


@router.message(Command("song"))
async def cmd_song(message: Message) -> None:
    query = (message.text or "").split(maxsplit=1)
    if len(query) < 2:
        await message.answer("Usage: <code>/song attention</code>")
        return
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            async with session.get(
                "https://itunes.apple.com/search",
                params={"term": query[1], "limit": 1, "media": "music"},
            ) as resp:
                data = await resp.json()
        except Exception:
            await message.answer("Search down hai 😅")
            return
    results = data.get("results", [])
    if not results:
        await message.answer("Gaana nahi mila 🎵 Do naam try karo")
        return
    r = results[0]
    preview = r.get("previewUrl", "")
    text = (
        f"🎵 <b>{html.escape(r.get('trackName', ''))}</b>\n"
        f"👤 {html.escape(r.get('artistName', ''))}\n"
        f"💿 {html.escape(r.get('collectionName', ''))}"
    )
    if preview:
        await message.answer_audio(preview, caption=text)
    else:
        await message.answer(text)


@router.message(Command("say"))
async def cmd_say(message: Message) -> None:
    text = (message.text or "").split(maxsplit=1)
    if len(text) < 2:
        await message.answer("Usage: <code>/say hello dosto</code> — main bol ke sunaunga 🎙️")
        return
    text = text[1][:300]
    voice = "hi-IN-SwaraNeural" if detect(text) == "hi" else "en-IN-NeerjaNeural"
    path = f"{settings.data_dir}/say_{message.from_user.id}.mp3"
    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(path)
        with open(path, "rb") as f:
            await message.answer_voice(f, caption=f"🎙️ {settings.bot_name} says: {html.escape(text)}")
    except Exception as e:
        await message.answer(f"Voice fail ho gayi 😅 ({e})")
    finally:
        import os

        try:
            os.remove(path)
        except OSError:
            pass


@router.message(Command("remindme", "remind"))
async def cmd_remind(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "⏰ Usage: <code>/remindme 10m call mom</code>\n"
            "Formats: 30s, 10m, 2h, 1d"
        )
        return
    seconds = _parse_duration(parts[1])
    if seconds is None or seconds < 5 or seconds > 86400 * 7:
        await message.answer("Duration 5s se 7 din ke beech hona chahiye")
        return
    due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
    await db.run(
        "INSERT INTO reminders (user_id, chat_id, due_at, text) VALUES (?, ?, ?, ?)",
        (message.from_user.id, message.chat.id, due.isoformat(), parts[2][:200]),
    )
    await message.answer(f"⏰ Reminder set! {parts[1]} mein yaad dilaunga: <i>{html.escape(parts[2])}</i>")


@router.message(Command("stash"))
async def cmd_stash(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub == "list":
        rows = await db.many(
            "SELECT content, created_at FROM stash WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (message.from_user.id,),
        )
        if not rows:
            await message.answer("Stash khali hai — reply karke /stash se save karo")
            return
        lines = [
            f"{i}. <code>{html.escape(r['content'][:80])}</code> <i>({r['created_at'][:10]})</i>"
            for i, r in enumerate(rows, 1)
        ]
        await message.answer("🔐 <b>Your Stash</b>\n\n" + "\n".join(lines))
        return

    if sub == "clear":
        await db.run("DELETE FROM stash WHERE user_id = ?", (message.from_user.id,))
        await message.answer("🔐 Stash cleared")
        return

    content = None
    if message.reply_to_message:
        content = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or f"[{message.reply_to_message.content_type}]"
        )
    elif len(parts) > 1:
        content = parts[1]
    if not content:
        await message.answer(
            "🔐 Reply to a message with <code>/stash</code>, or <code>/stash text</code>\n"
            "View: <code>/stash list</code> · Clear: <code>/stash clear</code>"
        )
        return
    await db.run(
        "INSERT INTO stash (user_id, content) VALUES (?, ?)",
        (message.from_user.id, content[:500]),
    )
    await message.answer("🔐 Saved to your private stash! (/stash list)")


@router.message(Command("ocr"))
async def cmd_ocr(message: Message) -> None:
    photo = None
    if message.photo:
        photo = message.photo[-1]
    elif message.reply_to_message and message.reply_to_message.photo:
        photo = message.reply_to_message.photo[-1]
    if photo is None:
        await message.answer(
            "🖼 Photo bhejo <code>/ocr</code> caption ke saath, "
            "ya kisi photo ko reply karke /ocr likho"
        )
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    file = await message.bot.download(photo.file_id)
    try:
        out = await ai_client.vision(
            file.read(), "image/jpeg",
            "Extract ALL text from this image exactly as written. "
            "If Hindi, keep Hindi. Reply with only the extracted text.",
        )
        await message.answer(f"📄 <b>Extracted text:</b>\n\n<code>{html.escape(out)}</code>")
    except Exception as e:
        await message.answer(f"OCR fail ho gaya 😅 ({e})")
