import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    TelegramRetryAfter,
    TelegramNetworkError,
    TelegramUnauthorizedError
)

from sqlalchemy import text

from app.config import (
    BOT_TOKEN,
    ADMIN_IDS,
    ALLOWED_CHAT_IDS
)

from app.db.db import Base, engine
from app.db import models

from app.bot import admin, collector


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)


def create_dispatcher():
    dp = Dispatcher()

    dp.include_router(admin.router)
    dp.include_router(collector.router)

    return dp


def init_database():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    Base.metadata.create_all(bind=engine)

    logger.info("PostgreSQL connected successfully")


async def main():

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing in .env")

    init_database()

    dp = create_dispatcher()

    logger.info("Configured administrators: %s", len(ADMIN_IDS))
    logger.info("Allowed chats: %s", len(ALLOWED_CHAT_IDS))

    if not ALLOWED_CHAT_IDS:
        logger.warning("Message collection is disabled")

    session = AiohttpSession(timeout=90)

    try:
        async with Bot(
            token=BOT_TOKEN,
            session=session
        ) as bot:

            info = await bot.me()

            logger.info("Telegram API connected")
            logger.info("Bot username: @%s", info.username)

            allowed_updates = dp.resolve_used_update_types()

            logger.info("Allowed updates: %s", allowed_updates)

            await dp.start_polling(
                bot,
                allowed_updates=allowed_updates,
                handle_as_tasks=False,
                close_bot_session=False
            )

    except TelegramRetryAfter as error:
        logger.error(
            "Telegram rate limit. Retry after %s seconds",
            error.retry_after
        )

    except TelegramNetworkError:
        logger.error("Telegram network connection failed")

    except TelegramUnauthorizedError:
        logger.error("Invalid Telegram bot token")

    finally:
        engine.dispose()
        logger.info("Application stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass