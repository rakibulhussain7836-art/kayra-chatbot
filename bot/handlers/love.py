import html
import random

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..db import database as db

router = Router(name="love")

COMPLIMENTS = [
    "You have the warmest smile in this group 🌸",
    "Your vibe is literally a daily mood booster ☀️",
    "Talking to you feels like a hug from a bestie 🤗",
    "You're the main character and everyone knows it 🎬",
    "Tumhara sense of style top class hai! 🔥",
    "Aapki energy sabse alag hai — hamesha positive! ✨",
    "Your brain + your heart = dangerous combo 💯",
    "Log tumhare aane se pehle hi khush ho jaate hain 😄",
]

ROASTS = [
    "Your WiFi signal is stronger than your game skills 📶",
    "You type 'lol' but your face shows zero emotion 😐",
    "Tumhara wardrobe aur tumhari life — dono mein confusion hai 👔",
    "You're not the clown, you're the whole circus 🤡",
    "Even your horoscope ignores you 🔮",
    "Aapki personality WhatsApp forward jaise purani hai 📵",
    "You bring everyone joy — when you leave the chat 👋",
    "Your last braincell is on a tea break ☕",
]


def _pair_users(message: Message, command_text: str) -> tuple | None:
    parts = command_text.split()
    users = []
    if message.reply_to_message and message.reply_to_message.from_user:
        users.append(message.reply_to_message.from_user)
    for ent in (message.entities or []):
        if ent.type == "text_mention" and ent.user:
            users.append(ent.user)
    # @username args (resolve via chat members is limited; fallback: use reply only)
    if len(users) >= 2:
        return users[0], users[1]
    if len(users) == 1:
        return message.from_user, users[0]
    return None


@router.message(Command("ship"))
async def cmd_ship(message: Message) -> None:
    pair = _pair_users(message, message.text or "")
    if not pair:
        await message.answer(
            "💘 Ship karo! Reply to someone with <code>/ship</code> — "
            "ya do @usernames do: <code>/ship @a @b</code> (reply method best hai)"
        )
        return
    u1, u2 = pair
    if u1.id == u2.id:
        await message.answer("Khud se ship? Self-love level: 100% 💅")
        return
    key = tuple(sorted((u1.id, u2.id)))
    score = (u1.id * u2.id + len(u1.first_name or "") * 7) % 101
    await db.run(
        "INSERT INTO ships (chat_id, user1, user2, score) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(chat_id, user1, user2) DO UPDATE SET score = MAX(score, excluded.score)",
        (message.chat.id, key[0], key[1], score),
    )
    hearts = "💖" * max(1, score // 20)
    if score >= 80:
        verdict = "Soulmates! Shaadi ki dates pack karo 💒"
    elif score >= 50:
        verdict = "Cute match — date pe jao! 🥰"
    elif score >= 25:
        verdict = "Thoda effort daalo, ho jaayega 👀"
    else:
        verdict = "Uh oh… friendzone danger zone 💀"
    n1 = html.escape(u1.first_name or u1.username or "?")
    n2 = html.escape(u2.first_name or u2.username or "?")
    await message.answer(
        f"💘 <b>{n1} × {n2}</b>\n{hearts}\n"
        f"Compatibility: <b>{score}%</b>\n<i>{verdict}</i>"
    )


@router.message(Command("compliment"))
async def cmd_compliment(message: Message) -> None:
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    n = html.escape(target.first_name or target.username or "you")
    await message.answer(f"🌸 <b>{n}</b>, {random.choice(COMPLIMENTS)}")


@router.message(Command("roast"))
async def cmd_roast(message: Message) -> None:
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    n = html.escape(target.first_name or target.username or "you")
    await message.answer(f"🔥 <b>{n}</b>, {random.choice(ROASTS)}\n\n(Playful only! ❤️)")


@router.message(Command("loveboard"))
async def cmd_loveboard(message: Message) -> None:
    rows = await db.many(
        "SELECT s.score, u1.first_name AS n1, u2.first_name AS n2 FROM ships s "
        "JOIN users u1 ON u1.user_id = s.user1 JOIN users u2 ON u2.user_id = s.user2 "
        "WHERE s.chat_id = ? ORDER BY s.score DESC LIMIT 10",
        (message.chat.id,),
    )
    if not rows:
        await message.answer("Abhi tak koi ship nahi hui — /ship se start karo! 💘")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        f"{medals[i] if i < 3 else f'{i+1}.'} {html.escape(r['n1'] or '?')} × "
        f"{html.escape(r['n2'] or '?')} — {r['score']}%"
        for i, r in enumerate(rows)
    ]
    await message.answer("💘 <b>Love Board</b>\n\n" + "\n".join(lines))


@router.message(Command("mylove"))
async def cmd_mylove(message: Message) -> None:
    row = await db.one("SELECT love FROM love_stats WHERE user_id = ?", (message.from_user.id,))
    ships = await db.many(
        "SELECT COUNT(*) AS c FROM ships WHERE user1 = ? OR user2 = ?",
        (message.from_user.id, message.from_user.id),
    )
    love = row["love"] if row else 0
    await message.answer(
        f"💕 <b>{html.escape(message.from_user.first_name or 'You')} Love Stats</b>\n"
        f"💘 Times shipped: {ships[0]['c'] if ships else 0}\n"
        f"❤️ Love points: {love}\n"
        f"Keep vibing bestie! 🌹"
    )


@router.message(Command("couple"))
async def cmd_couple(message: Message) -> None:
    row = await db.one("SELECT * FROM couples WHERE chat_id = ?", (message.chat.id,))
    if row is None:
        await message.answer(
            "No Couple of the Day yet!\nSet one: reply to your partner with <code>/setcouple</code> (200 coins)"
        )
        return
    n1 = html.escape(row["user1"])
    await message.answer(
        f"💍 <b>Couple of the Day</b>\n"
        f"<a href='tg://user?id={row['user1']}'>Partner 1</a> × "
        f"<a href='tg://user?id={row['user2']}'>Partner 2</a>\n"
        f"Score: {row['score']} · since {row['since'][:10]}\n"
        f"Break them up? /breakup (admin or either partner)"
    )


@router.message(Command("setcouple"))
async def cmd_setcouple(message: Message) -> None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Reply to your partner with <code>/setcouple</code>")
        return
    if not await db.spend_coins(message.from_user.id, 200):
        await message.answer("Setting couple costs 200 coins 💸")
        return
    a, b = message.from_user.id, message.reply_to_message.from_user.id
    await db.run(
        "INSERT INTO couples (chat_id, user1, user2, score) VALUES (?, ?, ?, 100) "
        "ON CONFLICT(chat_id) DO UPDATE SET user1 = excluded.user1, user2 = excluded.user2, "
        "score = MAX(couples.score, 100)",
        (message.chat.id, a, b),
    )
    await db.add_xp(message.from_user.id, 20, message.chat.id)
    await message.answer("💍 Couple set! Congrats you two 🎉 (-200 coins)")


@router.message(Command("breakup"))
async def cmd_breakup(message: Message) -> None:
    row = await db.one("SELECT * FROM couples WHERE chat_id = ?", (message.chat.id,))
    if row is None:
        await message.answer("Yahan koi couple nahi hai to todna kya hai? 😅")
        return
    uid = message.from_user.id
    is_admin = False
    try:
        member = await message.bot.get_chat_member(message.chat.id, uid)
        is_admin = member.status in ("creator", "administrator")
    except Exception:
        pass
    if not (is_admin or uid in (row["user1"], row["user2"])):
        await message.answer("Sirf admins ya us couple ke members hi breakup kar sakte hain")
        return
    await db.run("DELETE FROM couples WHERE chat_id = ?", (message.chat.id,))
    await message.answer("💔 It's over… couple reset ho gaya. /setcouple se dobara set karo.")
