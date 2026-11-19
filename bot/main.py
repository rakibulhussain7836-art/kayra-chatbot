import asyncio
import datetime as dt
import html
import logging
import traceback

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommand,
    ErrorEvent,
)

from .ai.client import ai_client
from .config import settings
from .db import database as db
from .handlers import (
    ai_cmds,
    chat,
    economy,
    games,
    help as help_mod,
    love,
    moderation,
    persona_cmd,
    start,
)
from .middlewares.spam import SpamMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("karya")

dp = Dispatcher()

COMMANDS = [
    ("start", "Start Karya"),
    ("help", "All commands"),
    ("profile", "Your profile & stats"),
    ("daily", "Claim daily coins"),
    ("wallet", "Check balance"),
    ("rank", "Your level & XP"),
    ("top", "Group leaderboard"),
    ("rich", "Richest members"),
    ("shop", "Open the shop"),
    ("math", "Mental math game"),
    ("trivia", "Trivia contest"),
    ("scramble", "Word scramble"),
    ("riddle", "Sphinx riddle"),
    ("hangman", "Group hangman"),
    ("tictactoe", "Tic-Tac-Toe duel"),
    ("gamble", "Bet coins 50/50"),
    ("slots", "Slot machine"),
    ("dice", "Casino dice"),
    ("mines", "Mines game"),
    ("pot", "Winner-takes-all pot"),
    ("duel", "1v1 coin duel"),
    ("lottery", "Daily lottery"),
    ("ship", "Compatibility check"),
    ("compliment", "Sweet compliment"),
    ("roast", "Playful roast"),
    ("translate", "Translate text"),
    ("shayari", "Hindi shayari"),
    ("horoscope", "Daily horoscope"),
    ("meme", "Random meme"),
    ("lyrics", "Song lyrics"),
    ("say", "AI voice note"),
    ("remindme", "Set a reminder"),
    ("ocr", "Extract text from image"),
    ("bribe", "Custom AI persona"),
    ("warn", "Warn a user (admin)"),
    ("mute", "Mute 30m (admin)"),
    ("kick", "Kick user (admin)"),
]


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in COMMANDS]
    )


async def scheduler(bot: Bot) -> None:
    """Background jobs: game expiry, auctions, reminders."""
    while True:
        try:
            await games.cleanup(bot)
            await economy.close_expired_auctions(bot)
            await check_reminders(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler error")
        await asyncio.sleep(15)


async def check_reminders(bot: Bot) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = await db.many("SELECT * FROM reminders WHERE due_at < ?", (now,))
    for r in rows:
        await db.run("DELETE FROM reminders WHERE id = ?", (r["id"],))
        try:
            await bot.send_message(
                r["chat_id"],
                f"⏰ <b>Reminder!</b> <a href='tg://user?id={r['user_id']}'>You</a> "
                f"asked me to remind you:\n<i>{html.escape(r['text'])}</i>",
            )
        except Exception:
            pass


async def on_error(event: ErrorEvent) -> None:
    log.error("Unhandled error: %s\n%s", event.exception, traceback.format_exc())


def register() -> None:
    # moderation service handlers + admin commands first (specific filters)
    dp.include_router(moderation.router)
    dp.include_router(start.router)
    dp.include_router(help_mod.router)
    dp.include_router(economy.router)
    dp.include_router(games.router)
    dp.include_router(love.router)
    dp.include_router(ai_cmds.router)
    dp.include_router(persona_cmd.router)
    # AI chat LAST — catch-all for plain text
    dp.include_router(chat.router)

    dp.message.outer_middleware(SpamMiddleware())
    dp.errors.register(on_error)


async def start_health_server() -> None:
    """Tiny HTTP server so Render (web type) sees an open port and stays alive."""
    import os

    from aiohttp import web

    app = web.Application()

    async def ok(_request):
        return web.Response(text=f"{settings.bot_name} is running!")

    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("Health server on :%s", port)


async def main() -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN missing — fill .env first!")

    await db.init()
    await ai_client.start()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    register()
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    log.info("Starting %s (@%s)", me.first_name, me.username)

    health = asyncio.create_task(start_health_server())
    sched = asyncio.create_task(scheduler(bot))
    try:
        await dp.start_polling(bot)
    finally:
        sched.cancel()
        health.cancel()
        await ai_client.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
