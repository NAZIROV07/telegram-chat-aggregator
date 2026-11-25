from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from app.bot import admin
from app.config import ADMIN_IDS, ALLOWED_CHAT_IDS, TIMEZONE
from app.db.db import SessionLocal
from app.db.crud import get_chats


router = Router(name="export_ui")


class ExportFlow(StatesGroup):
    chat = State()
    period = State()
    start_date = State()
    end_date = State()
    confirm = State()


def button(text, value):
    return InlineKeyboardButton(
        text=text,
        callback_data=f"exp:{value}"
    )


def keyboard(*rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[list(row) for row in rows]
    )


def cancel_keyboard():
    return keyboard(
        [button("❌ Отмена", "cancel")]
    )


async def show(message, state, text, markup):
    sent = await message.answer(
        text,
        reply_markup=markup
    )

    await state.update_data(
        ui_message_id=sent.message_id
    )


#Главное меню

@router.message(
    F.chat.type == "private",
    F.text.in_({
        "📂 Мои чаты",
        "📊 Статистика",
        "🟢 Состояние системы",
        "ℹ️ Помощь"
    })
)
async def menu_handler(message: Message, state: FSMContext):

    if not await admin.require_admin(message):
        return

    await state.clear()

    handlers = {
        "📂 Мои чаты": admin.chats_command,
        "📊 Статистика": admin.stats_command,
        "🟢 Состояние системы": admin.status_command,
        "ℹ️ Помощь": admin.help_command
    }

    await handlers[message.text](message)


#Начало выгрузки

@router.message(
    F.chat.type == "private",
    F.text == "📥 Выгрузить переписку"
)
async def begin_export(message: Message, state: FSMContext):

    if not await admin.require_admin(message):
        return

    await state.clear()

    with SessionLocal() as db:
        chats = {
            str(chat.id): chat.title
            for chat in get_chats(db, ALLOWED_CHAT_IDS)
        }

    if not chats:
        await message.answer(
            "📭 Нет доступных чатов.\n"
            "Сначала отправьте сообщение "
            "в подключённую группу."
        )
        return

    rows = [
        [button(f"💬 {title[:50]}", f"chat:{chat_id}")]
        for chat_id, title in chats.items()
    ]

    rows.append([button("❌ Отмена", "cancel")])

    await state.set_state(ExportFlow.chat)
    await state.update_data(chats=chats)

    await show(
        message,
        state,
        "📥 Выгрузка переписки\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Шаг 1 из 3\n"
        "Выберите чат:",
        keyboard(*rows)
    )


#Подтверждение выгрузки

async def confirm_export(message, state, start, end):

    await state.update_data(
        date_from=start.isoformat(),
        date_to=end.isoformat()
    )

    data = await state.get_data()

    await state.set_state(ExportFlow.confirm)

    await show(
        message,
        state,
        "📋 Подтверждение выгрузки\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 Чат: {data['chat_title']}\n"
        f"📅 Начало: {start:%d.%m.%Y}\n"
        f"📅 Конец: {end:%d.%m.%Y}\n"
        f"🌐 Часовой пояс: {TIMEZONE}\n"
        "📦 Формат: ZIP (JSON, CSV, медиа)\n\n"
        "Шаг 3 из 3\n"
        "Подтвердите создание архива.",
        keyboard(
            [button("✅ Создать архив", "confirm")],
            [button("❌ Отмена", "cancel")]
        )
    )


#Обработка кнопок

@router.callback_query(F.data.startswith("exp:"))
async def export_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    message = callback.message

    if (
        not isinstance(message, Message)
        or message.chat.type != "private"
        or callback.from_user.id not in ADMIN_IDS
        or message.chat.id != callback.from_user.id
    ):
        await callback.answer(
            "Доступ запрещён.",
            show_alert=True
        )
        return

    data = await state.get_data()
    current_state = await state.get_state()

    if data.get("ui_message_id") != message.message_id:
        await callback.answer(
            "Эта кнопка устарела.",
            show_alert=True
        )
        return

    action = callback.data.removeprefix("exp:")

    await callback.answer()

    #Отмена

    if action == "cancel":
        await state.clear()

        await message.edit_text(
            "❌ Выгрузка отменена."
        )
        return

    #Выбор группы

    if (
        action.startswith("chat:")
        and current_state == ExportFlow.chat.state
    ):
        chat_id = action.split(":", 1)[1]

        if (
            chat_id not in data["chats"]
            or int(chat_id) not in ALLOWED_CHAT_IDS
        ):
            await state.clear()
            await message.answer("🔒 Чат недоступен.")
            return

        await state.update_data(
            chat_id=int(chat_id),
            chat_title=data["chats"][chat_id]
        )

        await state.set_state(ExportFlow.period)
        await message.edit_reply_markup(reply_markup=None)

        await show(
            message,
            state,
            "📅 Выбор периода\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💬 Чат: {data['chats'][chat_id]}\n\n"
            "Шаг 2 из 3\n"
            "За какой период выгрузить сообщения?",
            keyboard(
                [
                    button("Сегодня", "today"),
                    button("Вчера", "yesterday")
                ],
                [
                    button("Последние 7 дней", "week"),
                    button("Последние 30 дней", "month")
                ],
                [
                    button("📅 Свой период", "custom")
                ],
                [
                    button("❌ Отмена", "cancel")
                ]
            )
        )

        return

    #Выбор периода

    if current_state == ExportFlow.period.state:

        today = datetime.now(
            ZoneInfo(TIMEZONE)
        ).date()

        periods = {
            "today": (today, today),
            "yesterday": (
                today - timedelta(days=1),
                today - timedelta(days=1)
            ),
            "week": (
                today - timedelta(days=6),
                today
            ),
            "month": (
                today - timedelta(days=29),
                today
            )
        }

        if action == "custom":
            await state.set_state(ExportFlow.start_date)

            await message.edit_reply_markup(
                reply_markup=None
            )

            await show(
                message,
                state,
                "📅 Введите начальную дату.\n\n"
                "Формат: ГГГГ-ММ-ДД\n"
                f"Например: {today.isoformat()}",
                cancel_keyboard()
            )

            return

        if action in periods:
            start, end = periods[action]

            await message.edit_reply_markup(
                reply_markup=None
            )

            await confirm_export(
                message, state, start, end
            )

            return

    #Создание архива

    if (
        action == "confirm"
        and current_state == ExportFlow.confirm.state
    ):
        chat_id, start, end = admin.parse_export_args(
            f"{data['chat_id']} "
            f"{data['date_from']} "
            f"{data['date_to']}"
        )

        await state.clear()

        await message.edit_reply_markup(
            reply_markup=None
        )

        await admin.send_export(
            message,
            callback.from_user,
            chat_id,
            start,
            end
        )


#Отмена через команду

@router.message(Command("cancel"), F.chat.type == "private")
async def cancel_command(message: Message, state: FSMContext):

    if not await admin.require_admin(message):
        return

    await state.clear()

    await message.answer(
        "❌ Выгрузка отменена.",
        reply_markup=admin.menu
    )


#Проверка формата даты

def parse_date(value):
    value = value.strip()

    result = datetime.strptime(
        value, "%Y-%m-%d"
    ).date()

    if result.isoformat() != value:
        raise ValueError("Invalid date")

    return result


#Ввод начальной даты

@router.message(
    ExportFlow.start_date,
    F.chat.type == "private",
    F.text
)
async def input_start_date(
    message: Message,
    state: FSMContext
):
    if not await admin.require_admin(message):
        await state.clear()
        return

    try:
        start = parse_date(message.text)

    except ValueError:
        await message.answer(
            "❌ Неверная дата.\n"
            "Используйте формат ГГГГ-ММ-ДД."
        )
        return

    await state.update_data(
        date_from=start.isoformat()
    )

    await state.set_state(ExportFlow.end_date)

    await show(
        message,
        state,
        f"✅ Начальная дата: {start:%d.%m.%Y}\n\n"
        "📅 Теперь введите конечную дату:",
        cancel_keyboard()
    )


#Ввод конечной даты

@router.message(
    ExportFlow.end_date,
    F.chat.type == "private",
    F.text
)
async def input_end_date(
    message: Message,
    state: FSMContext
):
    if not await admin.require_admin(message):
        await state.clear()
        return

    data = await state.get_data()

    start = parse_date(data["date_from"])

    try:
        end = parse_date(message.text)

        if end < start:
            raise ValueError("Invalid period")

    except ValueError:
        await message.answer(
            "❌ Некорректная конечная дата.\n"
            "Она не должна быть раньше начальной."
        )
        return

    await confirm_export(
        message, state, start, end
    )