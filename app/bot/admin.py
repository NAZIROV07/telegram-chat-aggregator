import asyncio
import logging

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message,
    FSInputFile,
    KeyboardButton,
    ReplyKeyboardMarkup
)

from sqlalchemy import select, func, text

from app.config import (
    ADMIN_IDS,
    ALLOWED_CHAT_IDS,
    TIMEZONE
)

from app.db.db import SessionLocal
from app.db.models import Message as DBMessage

from app.db.crud import (
    save_user,
    get_chats,
    create_export_log,
    finish_export_log
)

from app.services.export import create_export


router = Router(name="admin")

logger = logging.getLogger(__name__)

MAX_EXPORT_SIZE = 50 * 1024 * 1024


#Проверка прав администратора

def is_admin(message):
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and message.from_user.id in ADMIN_IDS
    )


async def require_admin(message):
    if not is_admin(message):
        await message.answer("Доступ запрещён.")
        return False

    return True


#Главное меню

menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="/chats"),
            KeyboardButton(text="/stats")
        ],
        [
            KeyboardButton(text="/export"),
            KeyboardButton(text="/status")
        ],
        [
            KeyboardButton(text="/help"),
            KeyboardButton(text="/myid")
        ]
    ],
    resize_keyboard=True
)


@router.message(Command("start"), F.chat.type == "private")
async def start_command(message: Message):

    if not await require_admin(message):
        return

    await message.answer(
        "Добро пожаловать в Corporate Chat Aggregator!\n\n"
        "Система сбора корпоративных переписок.\n"
        "Выберите необходимое действие.",
        reply_markup=menu
    )


@router.message(Command("help"), F.chat.type == "private")
async def help_command(message: Message):

    if not await require_admin(message):
        return

    await message.answer(
        "Доступные команды:\n\n"
        "/chats — список чатов\n"
        "/stats — статистика сообщений\n"
        "/export — выгрузка переписки\n"
        "/status — состояние системы\n"
        "/myid — ваш Telegram ID\n\n"
        "Формат выгрузки:\n"
        "/export CHAT_ID YYYY-MM-DD YYYY-MM-DD\n\n"
        "Обе даты включаются в период."
    )


#Получение собственного Telegram ID

@router.message(Command("myid"), F.chat.type == "private")
async def myid_command(message: Message):

    if message.from_user:
        await message.answer(
            f"Ваш Telegram ID: {message.from_user.id}"
        )


#Получение ID группы

@router.message(
    Command("chatid"),
    F.chat.type.in_({"group", "supergroup"})
)
async def chatid_command(message: Message):

    if (
        message.from_user
        and message.from_user.id in ADMIN_IDS
    ):
        await message.answer(
            f"Название: {message.chat.title}\n"
            f"Chat ID: {message.chat.id}"
        )


#Список разрешённых чатов

@router.message(Command("chats"), F.chat.type == "private")
async def chats_command(message: Message):

    if not await require_admin(message):
        return

    with SessionLocal() as db:
        chats = get_chats(db, ALLOWED_CHAT_IDS)

        if not chats:
            await message.answer(
                "Нет зарегистрированных чатов."
            )
            return

        lines = ["Доступные чаты:\n"]

        for chat in chats:
            lines.append(
                f"{chat.title}\nID: {chat.id}\n"
            )

    for line in lines:
        await message.answer(line)


#Статистика

@router.message(Command("stats"), F.chat.type == "private")
async def stats_command(message: Message):

    if not await require_admin(message):
        return

    with SessionLocal() as db:
        chats = get_chats(db, ALLOWED_CHAT_IDS)

        count = db.scalar(
            select(func.count(DBMessage.id))
            .where(
                DBMessage.chat_id.in_(ALLOWED_CHAT_IDS)
            )
        )

    await message.answer(
        "Статистика системы\n\n"
        f"Зарегистрировано чатов: {len(chats)}\n"
        f"Сохранено сообщений: {count}"
    )


#Состояние системы

@router.message(Command("status"), F.chat.type == "private")
async def status_command(message: Message):

    if not await require_admin(message):
        return

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))

        database_status = "Работает"

    except Exception:
        database_status = "Ошибка подключения"

    await message.answer(
        "Состояние системы\n\n"
        "Telegram-бот: Работает\n"
        f"PostgreSQL: {database_status}\n"
        f"Разрешённых чатов: {len(ALLOWED_CHAT_IDS)}\n"
        f"Администраторов: {len(ADMIN_IDS)}"
    )


#Обработка периода выгрузки

def parse_export_args(args):

    parts = (args or "").split()

    if len(parts) != 3:
        raise ValueError("Invalid arguments")

    chat_id = int(parts[0])

    tz = ZoneInfo(TIMEZONE)

    date_from = datetime.strptime(
        parts[1], "%Y-%m-%d"
    ).replace(tzinfo=tz)

    date_to = (
        datetime.strptime(parts[2], "%Y-%m-%d")
        + timedelta(days=1)
    ).replace(tzinfo=tz)

    if date_from >= date_to:
        raise ValueError("Invalid period")

    return chat_id, date_from, date_to


#Создание архива в отдельном потоке

def prepare_export(user, chat_id, date_from, date_to):

    if user.id not in ADMIN_IDS:
        raise PermissionError("Access denied")

    if chat_id not in ALLOWED_CHAT_IDS:
        raise PermissionError("Chat is not allowed")

    with SessionLocal.begin() as db:

        save_user(
            db,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            is_bot=user.is_bot
        )

        path, count = create_export(
            db,
            admin_id=user.id,
            chat_id=chat_id,
            date_from=date_from,
            date_to=date_to
        )

        try:
            log_id = create_export_log(
                db,
                admin_id=user.id,
                chat_id=chat_id,
                date_from=date_from,
                date_to=date_to
            )

        except Exception:
            path.unlink(missing_ok=True)
            raise

    return path, count, log_id


def update_export_status(log_id, status, count):

    with SessionLocal.begin() as db:
        finish_export_log(
            db,
            log_id=log_id,
            status=status,
            message_count=count
        )


#Выгрузка переписки

@router.message(Command("export"), F.chat.type == "private")
async def export_command(
    message: Message,
    command: CommandObject
):

    if not await require_admin(message):
        return

    if not command.args:
        await message.answer(
            "Для выгрузки сначала используй /chats.\n\n"
            "Затем отправь команду:\n"
            "/export CHAT_ID YYYY-MM-DD YYYY-MM-DD\n\n"
            "Пример:\n"
            "/export -1001234567890 2026-11-01 2026-11-24"
        )
        return

    try:
        chat_id, date_from, date_to = parse_export_args(
            command.args
        )

    except ValueError:
        await message.answer(
            "Неверный формат команды или периода."
        )
        return

    if chat_id not in ALLOWED_CHAT_IDS:
        await message.answer("Этот чат недоступен.")
        return

    await message.answer("Подготавливаю архив...")

    path = None
    log_id = None
    count = 0
    status = "failed"

    try:
        path, count, log_id = await asyncio.to_thread(
            prepare_export,
            message.from_user,
            chat_id,
            date_from,
            date_to
        )

        if path.stat().st_size > MAX_EXPORT_SIZE:
            await message.answer(
                "Архив слишком большой. "
                "Выбери более короткий период."
            )
            return

        await message.answer_document(
            document=FSInputFile(path),
            caption=(
                "Выгрузка успешно создана.\n"
                f"Количество сообщений: {count}\n"
                "Форматы: JSON, CSV, ZIP"
            )
        )

        status = "completed"

    except Exception as error:
        logger.error(
            "Export failed: %s",
            type(error).__name__
        )

        await message.answer(
            "Не удалось создать или отправить выгрузку."
        )

    finally:
        if path is not None:
            path.unlink(missing_ok=True)

        if log_id is not None:
            await asyncio.to_thread(
                update_export_status,
                log_id,
                status,
                count
            )