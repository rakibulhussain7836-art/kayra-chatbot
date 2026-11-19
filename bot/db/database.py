import asyncio
import datetime
import os
from typing import Any, Optional

import aiosqlite

from ..config import settings

_db: Optional[aiosqlite.Connection] = None
_lock = asyncio.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT DEFAULT '',
    first_name TEXT DEFAULT '',
    coins INTEGER DEFAULT 100,
    spent INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    streak INTEGER DEFAULT 0,
    last_daily TEXT DEFAULT '',
    title TEXT DEFAULT '',
    warnings INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_xp (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    xp INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS tags (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    tag TEXT DEFAULT '',
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS couples (
    chat_id INTEGER PRIMARY KEY,
    user1 INTEGER NOT NULL,
    user2 INTEGER NOT NULL,
    score INTEGER DEFAULT 0,
    since TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ships (
    chat_id INTEGER NOT NULL,
    user1 INTEGER NOT NULL,
    user2 INTEGER NOT NULL,
    score INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user1, user2)
);

CREATE TABLE IF NOT EXISTS love_stats (
    user_id INTEGER PRIMARY KEY,
    love INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    due_at TEXT NOT NULL,
    text TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS stash (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auctions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    item TEXT DEFAULT '',
    bid INTEGER DEFAULT 0,
    leader INTEGER DEFAULT 0,
    ends_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS lotteries (
    chat_id INTEGER PRIMARY KEY,
    pot INTEGER DEFAULT 0,
    ends_at TEXT NOT NULL,
    participants TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id INTEGER PRIMARY KEY,
    antilink INTEGER DEFAULT 1,
    antiflood INTEGER DEFAULT 1,
    antinsfw INTEGER DEFAULT 1,
    antisticker INTEGER DEFAULT 1,
    anticaps INTEGER DEFAULT 1,
    welcome_on INTEGER DEFAULT 1,
    goodbye_on INTEGER DEFAULT 0,
    lockdown INTEGER DEFAULT 0,
    antibot INTEGER DEFAULT 1,
    welcome_text TEXT DEFAULT '',
    goodbye_text TEXT DEFAULT '',
    rules TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS word_filters (
    chat_id INTEGER NOT NULL,
    word TEXT NOT NULL,
    PRIMARY KEY (chat_id, word)
);
"""


async def init() -> None:
    global _db
    os.makedirs(settings.data_dir, exist_ok=True)
    path = os.path.join(settings.data_dir, "bot.db")
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(SCHEMA)
    await _db.commit()


async def close() -> None:
    if _db:
        await _db.close()


async def run(sql: str, params: tuple = ()) -> None:
    async with _lock:
        await _db.execute(sql, params)
        await _db.commit()


async def one(sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
    cur = await _db.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return row


async def many(sql: str, params: tuple = ()) -> list:
    cur = await _db.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()
    return rows


async def ensure_user(user_id: int, username: str = "", first_name: str = "") -> aiosqlite.Row:
    row = await one("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if row is None:
        await run(
            "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username or "", first_name or ""),
        )
        row = await one("SELECT * FROM users WHERE user_id = ?", (user_id,))
    else:
        if username and row["username"] != username:
            await run("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        if first_name and row["first_name"] != first_name:
            await run("UPDATE users SET first_name = ? WHERE user_id = ?", (first_name, user_id))
    return row


async def add_coins(user_id: int, amount: int) -> int:
    await ensure_user(user_id)
    await run("UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id = ?", (amount, user_id))
    row = await one("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    return row["coins"] if row else 0


async def spend_coins(user_id: int, amount: int) -> bool:
    await ensure_user(user_id)
    row = await one("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    if not row or row["coins"] < amount:
        return False
    async with _lock:
        await _db.execute(
            "UPDATE users SET coins = coins - ?, spent = spent + ? WHERE user_id = ?",
            (amount, amount, user_id),
        )
        await _db.commit()
    return True


async def add_xp(user_id: int, amount: int, chat_id: int = 0) -> tuple[int, bool]:
    """Add XP. Returns (level, levelled_up)."""
    await ensure_user(user_id)
    row = await one("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
    xp = row["xp"] + amount
    level = xp // 100 + 1
    levelled = level > row["level"]
    await run("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (xp, level, user_id))
    if chat_id:
        await run(
            "INSERT INTO chat_xp (chat_id, user_id, xp) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET xp = xp + excluded.xp",
            (chat_id, user_id, amount),
        )
    return level, levelled


async def get_rank(user_id: int) -> int:
    row = await one("SELECT COUNT(*) AS c FROM users WHERE xp > (SELECT xp FROM users WHERE user_id = ?)", (user_id,))
    return (row["c"] + 1) if row else 1


def today() -> str:
    return datetime.date.today().isoformat()


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def now_dt() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def parse_iso(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s)


async def get_chat_settings(chat_id: int) -> aiosqlite.Row:
    row = await one("SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,))
    if row is None:
        await run("INSERT OR IGNORE INTO chat_settings (chat_id) VALUES (?)", (chat_id,))
        row = await one("SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,))
    return row


async def set_chat_setting(chat_id: int, key: str, value) -> None:
    allowed = {
        "antilink", "antiflood", "antinsfw", "antisticker", "anticaps",
        "welcome_on", "goodbye_on", "lockdown", "antibot",
        "welcome_text", "goodbye_text", "rules",
    }
    if key not in allowed:
        return
    await run(
        f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?",
        (value, chat_id),
    )


async def get_word_filters(chat_id: int) -> list[str]:
    rows = await many("SELECT word FROM word_filters WHERE chat_id = ?", (chat_id,))
    return [r["word"] for r in rows]


async def add_word_filter(chat_id: int, word: str) -> bool:
    word = word.strip().lower()
    if not word:
        return False
    existing = await one(
        "SELECT 1 FROM word_filters WHERE chat_id = ? AND word = ?",
        (chat_id, word),
    )
    if existing:
        return False
    await run("INSERT INTO word_filters (chat_id, word) VALUES (?, ?)", (chat_id, word))
    return True


async def remove_word_filter(chat_id: int, word: str) -> bool:
    word = word.strip().lower()
    row = await one(
        "SELECT 1 FROM word_filters WHERE chat_id = ? AND word = ?",
        (chat_id, word),
    )
    if not row:
        return False
    await run("DELETE FROM word_filters WHERE chat_id = ? AND word = ?", (chat_id, word))
    return True
