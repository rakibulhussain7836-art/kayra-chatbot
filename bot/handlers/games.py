import html
import random
import re
import time
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings
from ..db import database as db

router = Router(name="games")

# ---------------- state ----------------

active: dict[int, dict] = {}
pending_duels: dict[int, dict] = {}
clowns: dict[int, tuple[int, str]] = {}  # chat_id -> (user_id, old_title)

ANSWER_GAMES = {"math", "trivia", "oddone", "reverse", "scramble", "riddle", "guesscountry", "memory"}


def _name(user) -> str:
    return html.escape(user.first_name or user.username or "Someone")


async def _reward(message: Message, coins: int, xp: int, win_text: str) -> None:
    u = message.from_user
    await db.add_coins(u.id, coins)
    level, up = await db.add_xp(u.id, xp, message.chat.id)
    extra = f"\n⬆️ Level up! Now level <b>{level}</b>!" if up else ""
    await message.answer(f"{win_text}\n💰 +{coins} coins · +{xp} XP{extra}")


# ---------------- static content ----------------

TRIVIA = [
    ("What is the capital of France?", ["paris"]),
    ("Bharat ki rajdhani kaun si hai?", ["new delhi", "delhi"]),
    ("Which planet is known as the Red Planet?", ["mars"]),
    ("Kon sa planet sabse bada hai?", ["jupiter"]),
    ("What is 9 x 7?", ["63"]),
    ("Hindi mein 'water' ko kya kehte hain?", ["paani", "pani"]),
    ("Which gas do plants absorb?", ["co2", "carbon dioxide"]),
    ("Cricket World Cup 2011 ka winner kaun tha?", ["india", "indian"]),
    ("What is the largest ocean?", ["pacific", "pacific ocean"]),
    ("Ramayan ke hero kaun the?", ["ram", "rama", "shri ram"]),
    ("How many continents are there?", ["7", "seven"]),
    ("Taj kahan sthit hai?", ["agra", "agra, india"]),
]

RIDDLES = [
    ("I speak without a mouth and hear without ears. What am I?", ["an echo", "echo"]),
    ("Aaj mere paas 3 aaye, kal 9 aaye, parso 0. Main kaun hoon?", ["months", "mahine", "month"]),
    ("Meri ek taang nahi hoti par main chalta hoon. Main kya hoon?", ["table", "table ka", "chair"]),
    ("What has keys but can't open locks?", ["piano", "a piano"]),
    ("Sabse zyada bolta kaun hai par kuch sunta nahi?", ["telephone", "phone", "mobile"]),
    ("What comes once in a minute, twice in a moment, never in a thousand years?", ["the letter m", "m"]),
]

ODD_ONES = [
    (["Apple", "Mango", "Banana", "Potato"], "potato"),
    (["Cat", "Dog", "Elephant", "Table"], "table"),
    (["January", "March", "Sunday", "May"], "sunday"),
    (["Circle", "Square", "Triangle", "Blue"], "blue"),
    (["Delhi", "Mumbai", "Paris", "Kolkata"], "paris"),
]

EASY_WORDS = ["cat", "dog", "sun", "hat", "pen", "cup", "red", "toy", "box", "key", "tea", "ball", "fish", "bird"]
MED_WORDS = ["python", "tiger", "garden", "market", "orange", "planet", "guitar", "school", "flower", "rabbit"]
HARD_WORDS = ["elephant", "mountain", "computer", "beautiful", "knowledge", "whisper", "galaxy", "adventure", "mystery"]

MEMORY_POOL = ["🍕", "🐱", "🚀", "🌈", "⭐", "🔥", "🎁", "💎", "🦋", "🍀", "🎧", "🌺", "⚡", "🍭", "🦩"]

GUESSES_COUNTRY = [
    ("This country has Taj Mahal, Bollywood &amp; the Ganges.", ["india", "bharat"]),
    ("Land of the Rising Sun 🌅", ["japan"]),
    ("Known for Eiffel Tower &amp; croissants", ["france"]),
    ("Home of kangaroos &amp; the Great Barrier Reef", ["australia"]),
    ("Pizza, pasta, and the Colosseum live here", ["italy"]),
    ("The largest country in the world by area", ["russia"]),
    ("Maple leaves, hockey, and Niagara Falls", ["canada"]),
    ("Home of the pyramids and the Nile", ["egypt"]),
]

HANGMAN_WORDS = [
    "PYTHON", "TELEGRAM", "CHOCOLATE", "ELEPHANT", "GUITAR", "MOUNTAIN",
    "SHREYA", "KARYA", "BUTTERFLY", "ADVENTURE", "GALAXY", "MARVEL",
]

CASINO_EMOJI = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]


# ---------------- answer checking (used by chat handler) ----------------

async def try_game_answer(message: Message) -> bool:
    chat_id = message.chat.id
    st = active.get(chat_id)
    if not st:
        return False

    now = time.time()
    if now > st.get("expires", 0):
        await _expire(chat_id, st, bot=message.bot, announce=True)
        st = active.get(chat_id)
        if not st:
            return False

    text = (message.text or "").strip()
    if not text:
        return False

    gtype = st["type"]

    if gtype == "hangman":
        return await _hangman_guess(message, st)

    if gtype == "number":
        return await _number_guess(message, st)

    if gtype == "mines":
        return await _mines_pick(message, st)

    if gtype not in ANSWER_GAMES:
        return False

    guess = text.lower().strip("?!., ")
    answers = [a.lower().strip("?!., ") for a in st["answers"]]
    if guess in answers or text.lower() in [a.lower() for a in st.get("display_answers", [])]:
        active.pop(chat_id, None)
        await _reward(message, st["reward"], st["xp"], st["win"])
        return True
    return False


async def _expire(chat_id: int, st: dict, bot=None, announce: bool = False) -> None:
    active.pop(chat_id, None)
    if announce and st.get("display") and bot:
        try:
            await bot.send_message(chat_id, f"⏰ Time's up! Answer: <b>{st['display']}</b>")
        except Exception:
            pass


# ---------------- game starters ----------------

def _start_game(message: Message, st: dict) -> None:
    st["expires"] = time.time() + st.pop("seconds", 45)
    active[message.chat.id] = st


@router.message(Command("math"))
async def g_math(message: Message) -> None:
    a, b = random.randint(2, 99), random.randint(2, 99)
    op = random.choice("+-*")
    ans = {"+": a + b, "-": a - b, "*": a * b}[op]
    _start_game(message, {
        "type": "math", "answers": [str(ans)], "display": str(ans),
        "reward": 50, "xp": 25, "seconds": 30,
        "win": f"🧮 Correct! {_name(message.from_user)} solved {a} {op} {b}!",
    })
    await message.answer(
        f"🧮 <b>Mental Math!</b> (30s)\nWhat is <code>{a} {op} {b}</code>?\n"
        f"First correct answer wins 50 coins!"
    )


@router.message(Command("trivia"))
async def g_trivia(message: Message) -> None:
    q, answers = random.choice(TRIVIA)
    _start_game(message, {
        "type": "trivia", "answers": answers, "display": answers[0].title(),
        "reward": 60, "xp": 30, "seconds": 40,
        "win": f"🧠 Trivia king/queen! {_name(message.from_user)} got it!",
    })
    await message.answer(f"🧠 <b>Trivia!</b> (40s)\n\n{q}\n\nFirst correct answer: +60 coins")


@router.message(Command("oddone"))
async def g_oddone(message: Message) -> None:
    items, odd = random.choice(ODD_ONES)
    random.shuffle(items)
    _start_game(message, {
        "type": "oddone", "answers": [odd], "display": odd.title(),
        "reward": 40, "xp": 20, "seconds": 30,
        "win": f"🔍 {_name(message.from_user)} spotted the odd one!",
    })
    await message.answer(
        "🔍 <b>Spot the Odd One Out!</b> (30s)\n" + " · ".join(items) +
        "\n\nWhich one doesn't belong? +40 coins"
    )


@router.message(Command("reverse"))
async def g_reverse(message: Message) -> None:
    word = random.choice(EASY_WORDS + MED_WORDS)
    _start_game(message, {
        "type": "reverse", "answers": [word], "display": word,
        "reward": 40, "xp": 20, "seconds": 30,
        "win": f"↩️ {_name(message.from_user)} reversed it like a pro!",
    })
    await message.answer(
        f"↩️ <b>Reverse Sprint!</b> (30s)\nType the original word:\n"
        f"<code>{word[::-1]}</code>\n\n+40 coins"
    )


def _scramble_word(words: list[str]) -> str:
    w = random.choice(words)
    s = w
    while s == w and len(w) > 3:
        s = "".join(random.sample(w, len(w)))
    return w, s


@router.message(Command("scramble", "smed", "shard"))
async def g_scramble(message: Message) -> None:
    cmd = (message.text or "").split()[0].lstrip("/").lower()
    words, reward = {
        "scramble": (EASY_WORDS, 30),
        "smed": (MED_WORDS, 50),
        "shard": (HARD_WORDS, 80),
    }[cmd]
    word, scrambled = _scramble_word(words)
    _start_game(message, {
        "type": "scramble", "answers": [word], "display": word,
        "reward": reward, "xp": 25, "seconds": 40,
        "win": f"🔤 {_name(message.from_user)} unscrambled <b>{word}</b>!",
    })
    await message.answer(
        f"🔤 <b>Word Scramble</b> (40s)\n<code>{scrambled}</code>\n\nUnscramble it! +{reward} coins"
    )


@router.message(Command("riddle"))
async def g_riddle(message: Message) -> None:
    q, answers = random.choice(RIDDLES)
    _start_game(message, {
        "type": "riddle", "answers": answers, "display": answers[0].title(),
        "reward": 70, "xp": 35, "seconds": 60,
        "win": f" Sphinx is impressed! 🦁 {_name(message.from_user)} solved the riddle!",
    })
    await message.answer(f"🦁 <b>Sphinx Riddle</b> (60s)\n\n<i>{q}</i>\n\n+70 coins to the first correct answer")


@router.message(Command("memory"))
async def g_memory(message: Message) -> None:
    seq = [random.choice(MEMORY_POOL) for _ in range(random.randint(5, 7))]
    await message.answer(
        f"🧠 <b>Memory Challenge!</b>\nMemorize in <b>5 seconds</b>…\n\n{' '.join(seq)}"
    )
    await _delay_then_ask(message, seq)


async def _delay_then_ask(message: Message, seq: list[str]) -> None:
    import asyncio

    await asyncio.sleep(5)
    try:
        _start_game(message, {
            "type": "memory", "answers": ["".join(seq), " ".join(seq)],
            "display": " ".join(seq),
            "reward": 60, "xp": 30, "seconds": 30,
            "win": f"🧠 Perfect memory! {_name(message.from_user)} nailed the sequence!",
        })
        await message.answer("NOW type the exact emoji sequence you saw! (30s) +60 coins")
    except Exception:
        pass


@router.message(Command("guesscountry"))
async def g_country(message: Message) -> None:
    clue, answers = random.choice(GUESSES_COUNTRY)
    _start_game(message, {
        "type": "guesscountry", "answers": answers, "display": answers[0].title(),
        "reward": 80, "xp": 40, "seconds": 45,
        "win": f"🗺 {_name(message.from_user)} knows their geography!",
    })
    await message.answer(f"🗺 <b>Guess the Country!</b> (45s)\n\n{clue}\n\n+80 coins")


# ---------------- hangman ----------------

@router.message(Command("hangman"))
async def g_hangman(message: Message) -> None:
    word = random.choice(HANGMAN_WORDS)
    active[message.chat.id] = {
        "type": "hangman", "word": word, "guessed": set(), "lives": 6,
        "expires": time.time() + 180,
    }
    await message.answer(
        f"🪢 <b>Hangman!</b> (3 min)\nWord: <code>{_hang_display(word, set())}</code>\n"
        f"Lives: ❤️❤️❤️❤️❤️❤️\nSend letters (or the full word). +100 coins!"
    )


def _hang_display(word: str, guessed: set) -> str:
    return " ".join(ch if ch in guessed or ch == " " else "＿" for ch in word)


async def _hangman_guess(message: Message, st: dict) -> bool:
    text = (message.text or "").strip().upper()
    if not text or len(text) > 20:
        return False
    if not re.fullmatch(r"[A-Z ]+", text):
        return False

    if " " in text or len(text) > 1:
        if text == st["word"]:
            active.pop(message.chat.id, None)
            await _reward(message, 100, 50, f"🎉 {_name(message.from_user)} guessed the word: <b>{st['word']}</b>!")
            return True
        await message.answer("❌ Not the word! Keep guessing letters…")
        return True

    letter = text
    if letter in st["guessed"]:
        return True
    st["guessed"].add(letter)

    if letter in st["word"]:
        display = _hang_display(st["word"], st["guessed"])
        if "＿" not in display:
            active.pop(message.chat.id, None)
            await _reward(message, 100, 50, f"🎉 Word completed: <b>{st['word']}</b>! {_name(message.from_user)} wins!")
            return True
        await message.answer(f"✅ Nice! <code>{display}</code> · Lives: {'❤️' * st['lives']}")
    else:
        st["lives"] -= 1
        if st["lives"] <= 0:
            active.pop(message.chat.id, None)
            await message.answer(f"💀 Game over! The word was <b>{st['word']}</b>")
            return True
        await message.answer(f"❌ Nope! <code>{_hang_display(st['word'], st['guessed'])}</code> · Lives: {'❤️' * st['lives']}")
    return True


# ---------------- number bounty ----------------

@router.message(Command("number"))
async def g_number(message: Message) -> None:
    active[message.chat.id] = {
        "type": "number", "answer": random.randint(1, 100), "tries": 0,
        "expires": time.time() + 120,
    }
    await message.answer(
        "🔢 <b>Secret Number Bounty!</b>\nI picked 1–100. Find it in ≤7 tries! (2 min)\n"
        "Each wrong guess gets a hint. +120 coins!"
    )


async def _number_guess(message: Message, st: dict) -> bool:
    text = (message.text or "").strip()
    if not text.isdigit():
        return False
    guess = int(text)
    st["tries"] += 1
    ans = st["answer"]

    if guess == ans:
        active.pop(message.chat.id, None)
        bonus = max(40, 120 - st["tries"] * 10)
        await _reward(message, bonus, 40, f"🎯 Found it in {st['tries']} tries! Number was {ans}!")
        return True

    if st["tries"] >= 7:
        active.pop(message.chat.id, None)
        await message.answer(f"💥 Out of tries! The number was <b>{ans}</b>")
        return True

    hint = "⬆️ Higher!" if guess < ans else "⬇️ Lower!"
    await message.answer(f"{hint} ({7 - st['tries']} tries left)")
    return True


# ---------------- mines ----------------

@router.message(Command("mines"))
async def g_mines(message: Message) -> None:
    parts = (message.text or "").split()
    bet = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
    if not await db.spend_coins(message.from_user.id, bet):
        await message.answer(f"{bet} coins chahiye pehle 💸")
        return
    mines = sorted(random.sample(range(1, 10), 2))
    active[message.chat.id] = {
        "type": "mines", "bet": bet, "mines": mines, "revealed": [],
        "mult": 1.0, "player": message.from_user.id, "expires": time.time() + 90,
    }
    await message.answer(
        f"💣 <b>Mines!</b> Bet: {bet} coins · 9 tiles, 2 mines 💣\n"
        f"Send tile number <b>1–9</b> to reveal. Say <code>cashout</code> to take winnings.\n"
        f"Current multiplier: <b>x1.0</b> (90s)"
    )


async def _mines_pick(message: Message, st: dict) -> bool:
    text = (message.text or "").strip().lower()
    if message.from_user.id != st["player"]:
        return False

    if text in ("cashout", "/cashout"):
        winnings = int(st["bet"] * st["mult"])
        active.pop(message.chat.id, None)
        await db.add_coins(message.from_user.id, winnings)
        await message.answer(f"💰 Cashed out! <b>{winnings}</b> coins (x{st['mult']})")
        return True

    if not text.isdigit() or not (1 <= int(text) <= 9):
        return False

    tile = int(text)
    if tile in st["revealed"]:
        return True

    if tile in st["mines"]:
        active.pop(message.chat.id, None)
        await message.answer(f"💥 BOOM! 💣 Tile {tile} was a mine. {st['bet']} coins lost!")
        return True

    st["revealed"].append(tile)
    st["mult"] = round(1.0 + 0.4 * len(st["revealed"]), 1)
    safe_left = 7 - len(st["revealed"])
    if safe_left <= 0:
        winnings = int(st["bet"] * st["mult"])
        active.pop(message.chat.id, None)
        await db.add_coins(message.from_user.id, winnings)
        await message.answer(f"🏆 Cleared the whole board! <b>{winnings}</b> coins (x{st['mult']})")
        return True

    await message.answer(
        f"✅ Safe! x{st['mult']} · revealed {sorted(st['revealed'])} · "
        f"next pick (or cashout): {safe_left} safe tiles left"
    )
    return True


# ---------------- pot / duel / coinrain / lottery / clown ----------------

@router.message(Command("pot"))
async def g_pot(message: Message) -> None:
    parts = (message.text or "").split()
    stake = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
    if stake < 10:
        await message.answer("Minimum stake 10 coins")
        return
    u = message.from_user
    st = active.get(message.chat.id)
    if not (st and st["type"] == "pot" and st["expires"] > time.time()):
        if not await db.spend_coins(u.id, stake):
            await message.answer("Coins kam hain 💸")
            return
        active[message.chat.id] = {
            "type": "pot", "stake": stake, "players": [u.id], "names": {_name(u)},
            "expires": time.time() + 60,
        }
        await message.answer(
            f"🫕 <b>Winner-Takes-All Pot!</b>\nStake: {stake} coins · 60 seconds\n"
            f"{_name(u)} joined! Anyone: <code>/pot {stake}</code> to join"
        )
        return
    if u.id in st["players"]:
        await message.answer("Tum already ho pot mein!")
        return
    if st["stake"] != stake:
        await message.answer(f"Pot stake {st['stake']} coins hai — same daalo")
        return
    if not await db.spend_coins(u.id, stake):
        await message.answer("Coins kam hain 💸")
        return
    st["players"].append(u.id)
    st["names"].add(_name(u))
    left = int(st["expires"] - time.time())
    await message.answer(f"🫕 {_name(u)} joined! ({len(st['players'])} players · {left}s left)")


async def _settle_pot(bot) -> None:
    for chat_id, st in list(active.items()):
        if st["type"] == "pot" and time.time() > st["expires"]:
            active.pop(chat_id, None)
            winner = random.choice(st["players"])
            pot = st["stake"] * len(st["players"])
            await db.add_coins(winner, pot)
            try:
                await bot.send_message(
                    chat_id,
                    f"🫕 <b>Pot settled!</b>\n🏆 Winner takes <b>{pot}</b> coins! "
                    f"(from {len(st['players'])} players)",
                )
            except Exception:
                pass


@router.message(Command("duel"))
async def g_duel(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("Kisi ko reply karke: <code>/duel 100</code>")
        return
    parts = (message.text or "").split()
    amount = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id or target.is_bot:
        await message.answer("Khud se duel nahi hota 😂")
        return
    pending_duels[target.id] = {
        "from": message.from_user.id, "from_name": _name(message.from_user),
        "amount": amount, "chat_id": message.chat.id, "expires": time.time() + 60,
    }
    await message.answer(
        f"⚔️ <b>{_name(message.from_user)}</b> challenged <b>{_name(target)}</b> "
        f"for <b>{amount}</b> coins!\n{target.first_name or 'They'}: reply with "
        f"<code>/accept</code> in 60s"
    )


@router.message(Command("accept"))
async def g_accept(message: Message) -> None:
    d = pending_duels.get(message.from_user.id)
    if not d or d["expires"] < time.time():
        await message.answer("Koi pending duel nahi hai tumhare liye")
        return
    if message.chat.id != d["chat_id"]:
        return
    pending_duels.pop(message.from_user.id, None)
    challenger, target = d["from"], message.from_user.id
    amount = d["amount"]
    if not (await db.spend_coins(challenger, amount) and await db.spend_coins(target, amount)):
        await db.add_coins(challenger, amount)  # best-effort refund
        await message.answer("Ek player ke coins kam the — duel cancelled 💸")
        return
    if random.choice([True, False]):
        winner, loser = challenger, target
    else:
        winner, loser = target, challenger
    await db.add_coins(winner, amount * 2)
    await message.answer(
        f"⚔️ <b>Duel result!</b>🏆 Winner takes <b>{amount * 2}</b> coins! "
        f"<a href='tg://user?id={winner}'>Winner</a>"
    )


@router.message(Command("coinrain"))
async def g_coinrain(message: Message) -> None:
    parts = (message.text or "").split()
    amount = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 500
    amount = max(50, min(amount, 10000))
    u = message.from_user
    if not await db.spend_coins(u.id, amount):
        await message.answer("Itne coins nahi hain 💸 (sponsor karna mehnga hai!)")
        return
    rows = await db.many(
        "SELECT user_id FROM chat_xp WHERE chat_id = ? AND user_id != ? ORDER BY RANDOM() LIMIT 10",
        (message.chat.id, u.id),
    )
    if not rows:
        await db.add_coins(u.id, amount)
        await message.answer("Koi nahi hai udhaar lene wala — coins wapas 💸")
        return
    share = max(1, amount // len(rows))
    for r in rows:
        await db.add_coins(r["user_id"], share)
    await message.answer(
        f"🌧 <b>COIN RAIN!</b> sponsored by {_name(u)}!\n"
        f"{len(rows)} members got <b>{share}</b> coins each ☔💰"
    )


@router.message(Command("lottery"))
async def g_lottery(message: Message) -> None:
    import datetime as dt

    row = await db.one("SELECT * FROM lotteries WHERE chat_id = ?", (message.chat.id,))
    now = dt.datetime.now(dt.timezone.utc)
    if row is None or db.parse_iso(row["ends_at"]) < now:
        ends = (now + dt.timedelta(minutes=10)).isoformat()
        pot, parts = 0, ""
        if row:
            pot, parts = row["pot"], row["participants"]
        await db.run(
            "INSERT INTO lotteries (chat_id, pot, ends_at, participants) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET pot = ?, ends_at = ?, participants = ?",
            (message.chat.id, pot, ends, parts, pot, ends, parts),
        )
        row = await db.one("SELECT * FROM lotteries WHERE chat_id = ?", (message.chat.id,))

    uid = str(message.from_user.id)
    if uid in (row["participants"] or "").split(","):
        await message.answer("Tum already lottery mein ho! ⏳ Wait for the draw")
        return
    if not await db.spend_coins(message.from_user.id, 50):
        await message.answer("Ticket 50 coins ka hai 💸")
        return
    parts = [p for p in (row["participants"] or "").split(",") if p]
    parts.append(uid)
    await db.run(
        "UPDATE lotteries SET pot = pot + 50, participants = ? WHERE chat_id = ?",
        (",".join(parts), message.chat.id),
    )
    left = int((db.parse_iso(row["ends_at"]) - now).total_seconds())
    await message.answer(
        f"🎟 Lottery ticket bought! Pot: <b>{row['pot'] + 50}</b> coins · "
        f"{len(parts)} players · draw in {max(left, 0)}s"
    )


async def _settle_lottery(bot) -> None:
    import datetime as dt

    rows = await db.many("SELECT * FROM lotteries WHERE ends_at < ?", (dt.datetime.now(dt.timezone.utc).isoformat(),))
    for row in rows:
        parts = [p for p in (row["participants"] or "").split(",") if p]
        await db.run("DELETE FROM lotteries WHERE chat_id = ?", (row["chat_id"],))
        if not parts or row["pot"] <= 0:
            continue
        winner = int(random.choice(parts))
        await db.add_coins(winner, row["pot"])
        try:
            await bot.send_message(
                row["chat_id"],
                f"🎟 <b>Lottery draw!</b> 🏆 <a href='tg://user?id={winner}'>Winner</a> "
                f"takes <b>{row['pot']}</b> coins!",
            )
        except Exception:
            pass


@router.message(Command("clown"))
async def g_clown(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("Reply karo us bewakoof ko: clown ka mask lagane ke liye 🤡")
        return
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id:
        await message.answer("Apne aap ko clown bana liya? 😂 Reply do kisi aur ko")
        return
    if not await db.spend_coins(message.from_user.id, 100):
        await message.answer("Clown mask 100 coins ka hai 🤡")
        return
    row = await db.ensure_user(target.id, target.username or "", target.first_name or "")
    clowns[message.chat.id] = (target.id, row["title"], time.time())
    await db.run("UPDATE users SET title = ? WHERE user_id = ?", ("🤡 Clown of the Day", target.id))
    await message.answer(
        f"🤡 {_name(target)} is now the <b>Clown of the Day</b>! (-100 coins, "
        f"title reverts in 1 hour)"
    )


# ---------------- casino (instant) ----------------

async def _bet(message: Message, default: int) -> Optional[int]:
    parts = (message.text or "").split()
    amount = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else default
    amount = max(10, min(amount, 100000))
    if not await db.spend_coins(message.from_user.id, amount):
        await message.answer(f"{amount} coins nahi hain tumhare paas 💸")
        return None
    return amount


@router.message(Command("gamble"))
async def c_gamble(message: Message) -> None:
    amount = await _bet(message, 100)
    if amount is None:
        return
    if random.random() < 0.5:
        await db.add_coins(message.from_user.id, amount * 2)
        await message.answer(f"🎲 <b>JACKPOT!</b> You doubled {amount} → <b>{amount * 2}</b> coins 🎉")
    else:
        await message.answer(f"🪦 <b>Bust!</b> Lost {amount} coins… better luck next time 😅")


@router.message(Command("dice"))
async def c_dice(message: Message) -> None:
    amount = await _bet(message, 100)
    if amount is None:
        return
    roll = random.randint(1, 6)
    if roll >= 4:
        await db.add_coins(message.from_user.id, amount * 2)
        await message.answer(f"🎲 Rolled <b>{roll}</b> — you WIN <b>{amount * 2}</b> coins! 🎉")
    else:
        await message.answer(f"🎲 Rolled <b>{roll}</b> — lost {amount} coins 💸")


@router.message(Command("slots"))
async def c_slots(message: Message) -> None:
    amount = await _bet(message, 100)
    if amount is None:
        return
    reels = [random.choice(CASINO_EMOJI) for _ in range(3)]
    line = " | ".join(reels)
    if reels[0] == reels[1] == reels[2]:
        win = amount * 5
        await db.add_coins(message.from_user.id, win)
        await message.answer(f"🎰 {line}\n<b>TRIPLE!</b> +{win} coins!! 🤑")
    elif len(set(reels)) == 2:
        win = int(amount * 1.5)
        await db.add_coins(message.from_user.id, win)
        await message.answer(f"🎰 {line}\nPair! +{win} coins ✅")
    else:
        await message.answer(f"🎰 {line}\nNo match — {amount} coins gone 💸")


@router.message(Command("darts"))
async def c_darts(message: Message) -> None:
    amount = await _bet(message, 100)
    if amount is None:
        return
    score = random.randint(1, 20)
    if score in (20, 1):
        win = amount * 4
        msg = "🎯 BULLSEYE!"
    elif score >= 10:
        win = amount * 2
        msg = f"🎯 Nice throw ({score})!"
    else:
        win = 0
        msg = f"🪶 Weak throw ({score})…"
    if win:
        await db.add_coins(message.from_user.id, win)
        await message.answer(f"{msg} +<b>{win}</b> coins 🎉")
    else:
        await message.answer(f"{msg} Lost {amount} coins 💸")


# ---------------- tic-tac-toe ----------------

def _ttt_board(board: list[str]) -> InlineKeyboardMarkup:
    symbols = {"X": "❌", "O": "⭕", "-": "⬜"}
    rows = []
    for i in range(3):
        rows.append(
            [
                InlineKeyboardButton(
                    text=symbols.get(board[i * 3 + j], "⬜"),
                    callback_data=f"ttt:{i * 3 + j}",
                )
                for j in range(3)
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _ttt_winner(board: list[str]) -> Optional[str]:
    lines = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]
    for a, b, c in lines:
        if board[a] != "-" and board[a] == board[b] == board[c]:
            return board[a]
    return None


@router.message(Command("tictactoe", "ttt"))
async def g_ttt(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("Kisi ko reply karke challenge karo: <code>/tictactoe</code>")
        return
    p1, p2 = message.from_user, message.reply_to_message.from_user
    if p1.id == p2.id or p2.is_bot:
        await message.answer("Real opponent chahiye 😅")
        return
    active[message.chat.id] = {
        "type": "ttt",
        "board": ["-"] * 9,
        "players": {"X": p1.id, "O": p2.id},
        "turn": "X",
        "names": {"X": _name(p1), "O": _name(p2)},
        "expires": time.time() + 300,
    }
    await message.answer(
        f"🎮 <b>Tic-Tac-Toe!</b>\n{ _name(p1) } (❌) vs { _name(p2) } (⭕)\n"
        f"{_name(p1)}'s turn — tap the board!",
        reply_markup=_ttt_board(["-"] * 9),
    )


@router.callback_query(F.data.startswith("ttt:"))
async def cb_ttt(cb: CallbackQuery) -> None:
    st = active.get(cb.message.chat.id)
    if not st or st["type"] != "ttt":
        await cb.answer("Game khatam ho gaya!", show_alert=True)
        return
    idx = int(cb.data.split(":")[1])
    uid = cb.from_user.id
    if st["players"][st["turn"]] != uid:
        await cb.answer("Abhi opponent ka turn hai!", show_alert=True)
        return
    if st["board"][idx] != "-":
        await cb.answer("Occupied!", show_alert=True)
        return

    st["board"][idx] = st["turn"]
    winner = _ttt_winner(st["board"])

    if winner:
        wuser = st["players"][winner]
        active.pop(cb.message.chat.id, None)
        await db.add_coins(wuser, 50)
        await db.add_xp(wuser, 30, cb.message.chat.id)
        loser_sym = "O" if winner == "X" else "X"
        await cb.message.edit_text(
            f"🏆 {st['names'][winner]} ({'❌' if winner == 'X' else '⭕'}) WINS! +50 coins 🎉\n"
            f"Better luck {st['names'][loser_sym]}!"
        )
        await cb.answer()
        return

    if "-" not in st["board"]:
        active.pop(cb.message.chat.id, None)
        await cb.message.edit_text("🤝 It's a DRAW! No coins this time.")
        await cb.answer()
        return

    st["turn"] = "O" if st["turn"] == "X" else "X"
    await cb.message.edit_reply_markup(reply_markup=_ttt_board(st["board"]))
    await cb.answer()


# ---------------- expiry cleanup ----------------

async def cleanup(bot) -> None:
    now = time.time()
    for chat_id, st in list(active.items()):
        if st["type"] == "pot":
            continue  # handled in settle
        if now > st.get("expires", 0):
            active.pop(chat_id, None)
            display = st.get("display")
            try:
                if display and st["type"] in ANSWER_GAMES:
                    await bot.send_message(chat_id, f"⏰ Time's up! Answer: <b>{html.escape(display)}</b>")
                elif st["type"] == "hangman":
                    await bot.send_message(chat_id, f"⏰ Hangman over! Word was <b>{st['word']}</b>")
                elif st["type"] in ("mines", "number", "ttt"):
                    await bot.send_message(chat_id, "⏰ Game expired.")
            except Exception:
                pass
    await _settle_pot(bot)
    await _settle_lottery(bot)

    # clown revert (1 hour)
    import datetime as dt

    # clown expiry tracked by index-less dict; revert all older than 1h using timestamp
    for chat_id in list(clowns):
        entry = clowns[chat_id]
        if isinstance(entry, tuple) and len(entry) == 3:
            uid, old, ts = entry
            if now > ts:
                clowns.pop(chat_id, None)
                await db.run("UPDATE users SET title = ? WHERE user_id = ?", (old, uid))
