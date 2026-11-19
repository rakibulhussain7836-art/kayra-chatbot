from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import settings

router = Router(name="help")

CATEGORIES: dict[str, tuple[str, str]] = {
    "main": (
        "📚 <b>All Commands</b>",
        f"✨ <b>Hello! I'm {settings.bot_name}!</b>\n"
        "Your personal AI bestie, moderator &amp; economy bot rolled into one!\n\n"
        "👇 <b>Tap a category below</b> to see detailed explanations for all my features!\n\n"
        "⭐ <b>Most Useful Commands:</b>\n"
        "<code>/start</code> - Start me\n"
        "<code>/help</code> - Show all commands\n"
        "<code>/profile</code> - Check your wallet &amp; stats!\n"
        "<code>/daily</code> - Claim daily free coins!\n"
        "Just <b>talk to me</b> in Hindi or English anytime 💬",
    ),
    "economy": (
        "💰 Economy",
        "<b>💰 ECONOMY COMMANDS</b>\n\n"
        "<code>/profile</code> - Profile, balance, items &amp; stats\n"
        "<code>/wallet</code> - Wallet balance &amp; streak\n"
        "<code>/daily</code> - Claim daily TalkCoins\n"
        "<code>/rank</code> - Your level &amp; XP progress\n"
        "<code>/top</code> - Group XP leaderboard\n"
        "<code>/gtop</code> - Global XP leaderboard\n"
        "<code>/rich</code> - Richest group members\n"
        "<code>/grich</code> - Global wealth leaderboard\n"
        "<code>/earncoins</code> - All ways to earn coins\n"
        "<code>/spenders</code> - Group spending leaderboard\n"
        "<code>/halloffame</code> - All-time top spenders\n"
        "<code>/shop</code> - Open the shop\n"
        "<code>/give</code> - Transfer coins to a friend\n"
        "<code>/tag</code> - Buy a relationship tag\n"
        "<code>/untag</code> - Remove a tag\n"
        "<code>/auction</code> - View daily auction\n"
        "<code>/bid</code> - Bid on the auction",
    ),
    "games": (
        "🎮 Games",
        "<b>🎮 GAMES</b>\n\n"
        "<code>/math</code> - Fast mental arithmetic\n"
        "<code>/trivia</code> - Knowledge contest\n"
        "<code>/oddone</code> - Spot the odd one out\n"
        "<code>/memory</code> - Emoji sequence recall\n"
        "<code>/riddle</code> - Sphinx riddles\n"
        "<code>/reverse</code> - Backwards words sprint\n"
        "<code>/scramble</code> - Easy word scramble\n"
        "<code>/smed</code> - Medium scramble\n"
        "<code>/shard</code> - Hard scramble\n"
        "<code>/guesscountry</code> - Guess the country\n"
        "<code>/hangman</code> - Group hangman\n"
        "<code>/tictactoe</code> - Multiplayer Tic-Tac-Toe\n"
        "<code>/gamble</code> - Bet coins 50/50\n"
        "<code>/duel</code> - 1v1 coin wager\n"
        "<code>/mines</code> - High-stakes mines\n"
        "<code>/pot</code> - 60s winner-takes-all\n"
        "<code>/number</code> - Secret number bounty\n"
        "<code>/coinrain</code> - Sponsor a coin shower\n"
        "<code>/lottery</code> - Global daily lottery\n"
        "<code>/dice</code> - Casino dice\n"
        "<code>/darts</code> - Casino darts\n"
        "<code>/slots</code> - Slot machine\n"
        "<code>/clown</code> - Clown gag a friend",
    ),
    "love": (
        "💕 Love",
        "<b>💕 LOVE COMMANDS</b>\n\n"
        "<code>/ship</code> - Compatibility &amp; romance score\n"
        "<code>/compliment</code> - Send a sweet compliment\n"
        "<code>/roast</code> - Playfully roast a user\n"
        "<code>/loveboard</code> - Top couples leaderboard\n"
        "<code>/mylove</code> - Your personal love stats\n"
        "<code>/couple</code> - View Couple of the Day\n"
        "<code>/breakup</code> - Break up a couple",
    ),
    "ai": (
        "🤖 AI",
        "<b>🤖 AI COMMANDS</b>\n\n"
        "💬 <b>Just message me</b> — Hindi &amp; English, zero lag!\n"
        "<code>/say</code> - Generate an AI voice note\n"
        "<code>/song</code> - Find &amp; preview a song\n"
        "<code>/lyrics</code> - Get song lyrics\n"
        "<code>/ocr</code> - Extract text from an image\n"
        "<code>/translate</code> - Translate to any language\n"
        "<code>/whatif</code> - Creative AI scenarios\n"
        "<code>/horoscope</code> - Sassy daily horoscope\n"
        "<code>/shayari</code> - Poetic Hindi Shayari\n"
        "<code>/meme</code> - Random meme\n"
        "<code>/remindme</code> - Timed reminder\n"
        "<code>/stash</code> - Save a message privately\n\n"
        "<b>Persona:</b>\n"
        "<code>/settitle</code> - Set custom title\n"
        "<code>/bribe</code> - Custom AI personality\n"
        "<code>/revert</code> - Revert to normal",
    ),
    "moderation": (
        "🛡️ Moderation",
        "<b>🛡️ MODERATION</b> (admins only)\n\n"
        "<code>/warn</code> - Warn a user\n"
        "<code>/warns</code> - View warnings\n"
        "<code>/unwarn</code> - Remove a warning\n"
        "<code>/mute</code> - Mute a user (30m)\n"
        "<code>/unmute</code> - Unmute a user\n"
        "<code>/kick</code> - Kick a user\n"
        "<code>/ban</code> - Ban a user\n\n"
        "🛡️ <b>Auto-protection:</b>\n"
        "• Anti-flood (message spam)\n"
        "• Anti-link (non-admins)\n"
        "• Caps lock limiter\n"
        "• Bio scanner on join\n"
        "• 3 warnings = auto-kick",
    ),
}


def cat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Economy", callback_data="help:economy"),
                InlineKeyboardButton(text="🏆 Games", callback_data="help:games"),
            ],
            [
                InlineKeyboardButton(text="💕 Love", callback_data="help:love"),
                InlineKeyboardButton(text="🤖 AI", callback_data="help:ai"),
            ],
            [
                InlineKeyboardButton(text="🛡️ Moderation", callback_data="help:moderation"),
                InlineKeyboardButton(text="🏠 Main Menu", callback_data="help:main"),
            ],
        ]
    )


@router.message(Command("help", "commands"))
async def cmd_help(message: Message) -> None:
    title, body = CATEGORIES["main"]
    await message.answer(f"{title}\n{body}", reply_markup=cat_keyboard())


@router.callback_query(F.data.startswith("help:"))
async def cb_help(cb: CallbackQuery) -> None:
    key = cb.data.split(":", 1)[1]
    if key not in CATEGORIES:
        key = "main"
    title, body = CATEGORIES[key]
    try:
        await cb.message.edit_text(f"{title}\n{body}", reply_markup=cat_keyboard())
    except Exception:
        await cb.message.answer(f"{title}\n{body}", reply_markup=cat_keyboard())
    await cb.answer()
