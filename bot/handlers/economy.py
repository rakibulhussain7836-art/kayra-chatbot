import html
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings
from ..db import database as db

router = Router(name="economy")

DAILY_BASE = 100
STREAK_BONUS_CAP = 100
AUCTION_SECONDS = 600

AUCTION_ITEMS = [
    "👑 Golden Crown", "🌹 Rose Badge", "💎 Diamond Tag", "🔥 Fire Title",
    "⭐ Star Charm", "🎨 Color Splash", "🏆 Trophy Pin", "🎭 Mask Badge",
]


def _name(user) -> str:
    return html.escape(user.first_name or user.username or "Someone")


def _bar(xp: int) -> str:
    pct = xp % 100
    filled = pct // 10
    return "🟩" * filled + "⬜" * (10 - filled)


@router.message(Command("profile", "me"))
async def cmd_profile(message: Message) -> None:
    u = message.from_user
    row = await db.ensure_user(u.id, u.username or "", u.first_name or "")
    rank = await db.get_rank(u.id)
    tag_row = await db.one("SELECT tag FROM tags WHERE chat_id = ? AND user_id = ?", (message.chat.id, u.id))
    tag = f"\n🏷 Tag: {tag_row['tag']}" if tag_row and tag_row["tag"] else ""
    title = f"\n🎩 Title: {row['title']}" if row["title"] else ""

    await message.answer(
        f"👤 <b>{_name(u)}'s Profile</b>\n"
        f"{title}{tag}\n"
        f"💰 Coins: <b>{row['coins']}</b>\n"
        f"🛒 Spent: {row['spent']}\n"
        f"📈 Level: <b>{row['level']}</b> ({row['xp']} XP)\n"
        f"{_bar(row['xp'])} {row['xp'] % 100}%\n"
        f"🔥 Streak: {row['streak']} day(s)\n"
        f"🌍 Global Rank: <b>#{rank}</b>\n"
        f"⚠️ Warnings: {row['warnings']}"
    )


@router.message(Command("wallet"))
async def cmd_wallet(message: Message) -> None:
    u = message.from_user
    row = await db.ensure_user(u.id, u.username or "", u.first_name or "")
    await message.answer(
        f"👛 <b>Wallet</b>\n💰 Balance: <b>{row['coins']}</b> coins\n"
        f"🔥 Daily streak: {row['streak']}\n"
        f"💡 Use /daily for free coins!"
    )


@router.message(Command("daily"))
async def cmd_daily(message: Message) -> None:
    u = message.from_user
    row = await db.ensure_user(u.id, u.username or "", u.first_name or "")
    t = db.today()
    if row["last_daily"] == t:
        await message.answer("⏳ Aaj ka daily already le liya! Kal wapas aana 💤")
        return
    import datetime as dt

    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    streak = row["streak"] + 1 if row["last_daily"] == yesterday else 1
    bonus = min((streak - 1) * 10, STREAK_BONUS_CAP)
    amount = DAILY_BASE + bonus
    await db.run(
        "UPDATE users SET coins = coins + ?, last_daily = ?, streak = ? WHERE user_id = ?",
        (amount, t, streak, u.id),
    )
    await db.add_xp(u.id, 20, message.chat.id)
    await message.answer(
        f"🎁 <b>Daily claimed!</b>\n+{amount} coins "
        f"(base {DAILY_BASE} + streak bonus {bonus})\n"
        f"🔥 Streak: {streak} day(s) — come back tomorrow for more!"
    )


@router.message(Command("rank"))
async def cmd_rank(message: Message) -> None:
    u = message.from_user
    row = await db.ensure_user(u.id, u.username or "", u.first_name or "")
    rank = await db.get_rank(u.id)
    await message.answer(
        f"📊 <b>{_name(u)}</b>\nLevel <b>{row['level']}</b> · {row['xp']} XP\n"
        f"{_bar(row['xp'])} {row['xp'] % 100}% to next level\n"
        f"🌍 Global rank: <b>#{rank}</b>\nEarn XP by chatting &amp; playing games!"
    )


async def _leaderboard(message: Message, mode: str) -> None:
    if mode == "top":
        rows = await db.many(
            "SELECT c.xp, u.first_name, u.username FROM chat_xp c "
            "JOIN users u ON u.user_id = c.user_id WHERE c.chat_id = ? "
            "ORDER BY c.xp DESC LIMIT 10",
            (message.chat.id,),
        )
        title = "🏆 Group XP Leaderboard"
    elif mode == "gtop":
        rows = await db.many("SELECT xp, first_name, username FROM users ORDER BY xp DESC LIMIT 10")
        title = "🌍 Global XP Leaderboard"
    elif mode == "rich":
        rows = await db.many(
            "SELECT coins, first_name, username FROM users u "
            "WHERE EXISTS (SELECT 1 FROM chat_xp c WHERE c.user_id = u.user_id AND c.chat_id = ?) "
            "ORDER BY coins DESC LIMIT 10",
            (message.chat.id,),
        )
        title = "💰 Richest Group Members"
    elif mode == "grich":
        rows = await db.many("SELECT coins, first_name, username FROM users ORDER BY coins DESC LIMIT 10")
        title = "🌍 Global Wealth Leaderboard"
    elif mode == "spenders":
        rows = await db.many(
            "SELECT spent AS coins, first_name, username FROM users u "
            "WHERE EXISTS (SELECT 1 FROM chat_xp c WHERE c.user_id = u.user_id AND c.chat_id = ?) "
            "ORDER BY spent DESC LIMIT 10",
            (message.chat.id,),
        )
        title = "🛒 Group Spenders Leaderboard"
    else:  # halloffame
        rows = await db.many("SELECT spent AS coins, first_name, username FROM users ORDER BY spent DESC LIMIT 10")
        title = "🏛 Hall of Fame — Top Spenders"

    if not rows:
        await message.answer(f"{title}\n\nKoi data nahi abhi — pehle khelo aur kamao! 🎮")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, r in enumerate(rows):
        val = r["coins"]
        unit = "XP" if mode in ("top", "gtop") else "🪙"
        who = html.escape(r["first_name"] or r["username"] or "anon")
        lines.append(f"{medals[i] if i < 3 else f'{i+1}.'} {who} — {val} {unit}")
    await message.answer(f"<b>{title}</b>\n\n" + "\n".join(lines))


@router.message(Command("top"))
async def cmd_top(m: Message) -> None:
    await _leaderboard(m, "top")


@router.message(Command("gtop"))
async def cmd_gtop(m: Message) -> None:
    await _leaderboard(m, "gtop")


@router.message(Command("rich"))
async def cmd_rich(m: Message) -> None:
    await _leaderboard(m, "rich")


@router.message(Command("grich"))
async def cmd_grich(m: Message) -> None:
    await _leaderboard(m, "grich")


@router.message(Command("spenders"))
async def cmd_spenders(m: Message) -> None:
    await _leaderboard(m, "spenders")


@router.message(Command("halloffame"))
async def cmd_hof(m: Message) -> None:
    await _leaderboard(m, "halloffame")


@router.message(Command("earncoins"))
async def cmd_earncoins(m: Message) -> None:
    await m.answer(
        "💸 <b>Ways to earn coins:</b>\n"
        "• /daily — free coins every day (+streak bonus)\n"
        "• Chat &amp; play — XP from messages &amp; games\n"
        "• /math /trivia /scramble — win game rewards\n"
        "• /gamble /dice /slots — risk it for the biscuit 🎰\n"
        "• /lottery — daily jackpot\n"
        "• /coinrain — generous sponsors drop coins 🚀\n"
        "• /give — friends can gift you coins"
    )


# ---------------- SHOP ----------------

SHOP_ITEMS = {
    "title": {"label": "🎩 Custom Title (500)", "cost": 500},
    "rename": {"label": "✨ Name Glow (250)", "cost": 250},
    "xpboost": {"label": "🚀 XP Boost +100 (300)", "cost": 300},
}


def _shop_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=v["label"], callback_data=f"shop:buy:{k}")]
            for k, v in SHOP_ITEMS.items()
        ]
        + [[InlineKeyboardButton(text="❌ Close", callback_data="shop:close")]]
    )


@router.message(Command("shop"))
async def cmd_shop(message: Message) -> None:
    u = message.from_user
    row = await db.ensure_user(u.id, u.username or "", u.first_name or "")
    await message.answer(
        f"🛒 <b>{settings.bot_name} Shop</b>\nYour balance: <b>{row['coins']}</b> coins\n\n"
        "Pick an item below 👇",
        reply_markup=_shop_kb(),
    )


@router.callback_query(F.data.startswith("shop:"))
async def cb_shop(cb: CallbackQuery) -> None:
    _, action, item = (cb.data.split(":") + ["", ""])[:3]
    if action == "close":
        await cb.message.edit_text("Shop band. /shop se wapas aa jana 🛒")
        await cb.answer()
        return
    if item not in SHOP_ITEMS:
        await cb.answer("Invalid item", show_alert=True)
        return
    u = cb.from_user
    cost = SHOP_ITEMS[item]["cost"]
    if not await db.spend_coins(u.id, cost):
        await cb.answer(f"Coins kam hain! {cost} chahiye 💸", show_alert=True)
        return
    if item == "title":
        await db.run("UPDATE users SET title = ? WHERE user_id = ?", ("⭐ Shop Star", u.id))
        out = "🎩 Title mil gaya! Ab /profile se dikhega. (Abhi '⭐ Shop Star' set hai)"
    elif item == "rename":
        await db.run("UPDATE users SET title = ? WHERE user_id = ?", ("✨ Glowing", u.id))
        out = "✨ Name glow mil gaya! Profile pe lag gaya ✨"
    else:
        await db.add_xp(u.id, 100, cb.message.chat.id)
        out = "🚀 XP Boost! +100 XP lag gaya!"
    await cb.answer(f"-{cost} coins ✅")
    await cb.message.edit_text(f"✅ <b>Purchase done!</b>\n{out}\nBal: {await _coins(u.id)}")


async def _coins(uid: int) -> int:
    row = await db.one("SELECT coins FROM users WHERE user_id = ?", (uid,))
    return row["coins"] if row else 0


# ---------------- GIVE / TAGS ----------------

@router.message(Command("give"))
async def cmd_give(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("Kisi ko coin dene ke liye unko <b>reply</b> karo: /give 50")
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: reply karo aur likho <code>/give 50</code>")
        return
    amount = int(parts[1])
    if amount <= 0:
        await message.answer("Amount positive hona chahiye 😅")
        return
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id:
        await message.answer("Khud ko dena band karo 😂")
        return
    if not await db.spend_coins(message.from_user.id, amount):
        await message.answer("Itne coins nahi hain tumhare paas 💸")
        return
    await db.add_coins(target.id, amount)
    await message.answer(
        f"🤝 {_name(message.from_user)} → {_name(target)}: <b>+{amount} coins</b> 🎁"
    )


@router.message(Command("tag"))
async def cmd_tag(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("Reply karo us user ko jisme tag dena hai: <code>/tag cutie</code>")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: <code>/tag cutie</code> (cost 100 coins)")
        return
    tag = parts[1].strip()[:25]
    if not await db.spend_coins(message.from_user.id, 100):
        await message.answer("Tag ke 100 coins chahiye 💸")
        return
    target = message.reply_to_message.from_user
    await db.run(
        "INSERT INTO tags (chat_id, user_id, tag) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET tag = excluded.tag",
        (message.chat.id, target.id, tag),
    )
    await message.answer(f"🏷 {_name(target)} ab hain: <b>{html.escape(tag)}</b> (-100 coins)")


@router.message(Command("untag"))
async def cmd_untag(message: Message) -> None:
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    await db.run("DELETE FROM tags WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id))
    await message.answer(f"🏷 Tag hata diya: {_name(target)}")


# ---------------- AUCTION ----------------

@router.message(Command("auction"))
async def cmd_auction(message: Message) -> None:
    row = await db.one(
        "SELECT * FROM auctions WHERE chat_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
        (message.chat.id,),
    )
    if row is None:
        item = random.choice(AUCTION_ITEMS)
        import datetime as dt

        ends = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=AUCTION_SECONDS)).isoformat()
        await db.run(
            "INSERT INTO auctions (chat_id, item, bid, leader, ends_at) VALUES (?, ?, 0, 0, ?)",
            (message.chat.id, item, ends),
        )
        await message.answer(
            f"🔨 <b>Daily Auction started!</b>\nItem: {item}\n"
            f"Starting bid: 0 coins · 10 minutes\n"
            f"Place bids with <code>/bid 50</code>"
        )
        return
    left = int((db.parse_iso(row["ends_at"]) - db.now_dt()).total_seconds())
    leader_html = f"<a href='tg://user?id={row['leader']}'>leader</a>" if row["leader"] else "nobody"
    await message.answer(
        f"🔨 <b>Auction</b>\nItem: {row['item']}\nHighest bid: <b>{row['bid']}</b> by {leader_html}\n"
        f"⏳ {max(left, 0)}s left\nBid: <code>/bid 100</code>"
    )


@router.message(Command("bid"))
async def cmd_bid(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: <code>/bid 100</code>")
        return
    amount = int(parts[1])
    row = await db.one(
        "SELECT * FROM auctions WHERE chat_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
        (message.chat.id,),
    )
    if row is None:
        await message.answer("Koi auction nahi chal raha. /auction start karo!")
        return
    if amount <= row["bid"]:
        await message.answer(f"Current highest bid {row['bid']} se zyada chahiye 💰")
        return
    u = message.from_user
    if not await db.spend_coins(u.id, amount):
        await message.answer("Itne coins nahi hain 💸")
        return
    if row["leader"]:
        await db.add_coins(row["leader"], row["bid"])  # refund outbid
    await db.run(
        "UPDATE auctions SET bid = ?, leader = ? WHERE id = ?", (amount, u.id, row["id"])
    )
    await message.answer(
        f"🔨 {_name(u)} bid <b>{amount}</b> on {row['item']}! "
        f"(previous leader refunded {row['bid']})"
    )


async def close_expired_auctions(bot) -> None:
    import datetime as dt

    now = dt.datetime.now(dt.timezone.utc)
    rows = await db.many("SELECT * FROM auctions WHERE active = 1 AND ends_at < ?", (now.isoformat(),))
    for row in rows:
        await db.run("UPDATE auctions SET active = 0 WHERE id = ?", (row["id"],))
        try:
            if row["leader"]:
                await bot.send_message(
                    row["chat_id"],
                    f"🔨 <b>Auction ended!</b>\n🏆 <a href='tg://user?id={row['leader']}'>Winner</a> "
                    f"gets <b>{html.escape(row['item'])}</b> for {row['bid']} coins!",
                )
            else:
                await bot.send_message(
                    row["chat_id"],
                    f"🔨 <b>Auction ended!</b> No bids on {row['item']} — better luck next time!",
                )
        except Exception:
            pass
