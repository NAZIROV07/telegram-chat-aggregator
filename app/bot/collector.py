import logging

from aiogram import Bot, F, Router
from aiogram.types import Message

from app.config import ALLOWED_CHAT_IDS
from app.db.db import SessionLocal

from app.db.crud import (
    save_user,
    save_chat,
    save_message,
    save_attachment
)

from app.services.media import (
    extract_media,
    download_media
)


router = Router(name="collector")

logger = logging.getLogger(__name__)


def is_allowed_chat(chat):
    return (
        chat.type in ("group", "supergroup")
        and chat.id in ALLOWED_CHAT_IDS
    )


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def collect_message(message: Message, bot: Bot):

    if not is_allowed_chat(message.chat):
        return

    if message.has_protected_content:
        return

    user = message.from_user

    user_id = None

    sender_chat_id = (
        message.sender_chat.id
        if message.sender_chat
        else None
    )

    text = message.text or message.caption

    media_data = extract_media(message)

    file_path = None

    if media_data:
        media_type, media = media_data

        file_path = await download_media(
            bot,
            message,
            media_type,
            media
        )

    with SessionLocal.begin() as db:

        if user and not message.sender_chat:
            user_id = save_user(
                db,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_bot=user.is_bot
            )

        chat_id = save_chat(
            db,
            chat_id=message.chat.id,
            title=message.chat.title or "Unknown chat",
            chat_type=message.chat.type
        )

        message_id = save_message(
            db,
            telegram_message_id=message.message_id,
            chat_id=chat_id,
            user_id=user_id,
            sender_chat_id=sender_chat_id,
            text=text,
            message_type=str(message.content_type),
            sent_at=message.date,
            edited_at=message.edit_date,
            reply_to_message_id=(
                message.reply_to_message.message_id
                if message.reply_to_message
                else None
            )
        )

        if media_data:
            media_type, media = media_data

            save_attachment(
                db,
                message_id=message_id,
                file_id=media.file_id,
                file_unique_id=media.file_unique_id,
                file_type=media_type,
                file_name=getattr(media, "file_name", None),
                file_path=file_path,
                mime_type=getattr(media, "mime_type", None),
                file_size=getattr(media, "file_size", None)
            )

    logger.info(
        "Message saved: chat=%s message=%s",
        message.chat.id,
        message.message_id
    )

from aiogram.types import (
    MessageReactionUpdated,
    MessageReactionCountUpdated
)

from app.db.crud import get_message, replace_reactions


def reaction_key(reaction):
    if reaction.type == "emoji":
        return reaction.emoji

    if reaction.type == "custom_emoji":
        return f"custom:{reaction.custom_emoji_id}"

    if reaction.type == "paid":
        return "paid"

    return str(reaction.type)


#Индивидуальные реакции пользователей

@router.message_reaction()
async def collect_reaction(event: MessageReactionUpdated):

    if not is_allowed_chat(event.chat):
        return

    with SessionLocal.begin() as db:

        message = get_message(
            db,
            event.chat.id,
            event.message_id
        )

        if message is None:
            return

        user_id = None

        if event.user:
            user_id = save_user(
                db,
                user_id=event.user.id,
                username=event.user.username,
                first_name=event.user.first_name,
                last_name=event.user.last_name,
                is_bot=event.user.is_bot
            )

            actor_key = f"user:{user_id}"

        elif event.actor_chat:
            actor_key = f"chat:{event.actor_chat.id}"

        else:
            return

        reactions = {
            reaction_key(reaction): 1
            for reaction in event.new_reaction
        }

        replace_reactions(
            db,
            message_id=message.id,
            actor_key=actor_key,
            reactions=reactions,
            user_id=user_id
        )

    logger.info(
        "Reaction updated: chat=%s message=%s",
        event.chat.id,
        event.message_id
    )


#Анонимные реакции

@router.message_reaction_count()
async def collect_reaction_count(
    event: MessageReactionCountUpdated
):

    if not is_allowed_chat(event.chat):
        return

    with SessionLocal.begin() as db:

        message = get_message(
            db,
            event.chat.id,
            event.message_id
        )

        if message is None:
            return

        reactions = {
            reaction_key(item.type): item.total_count
            for item in event.reactions
        }

        replace_reactions(
            db,
            message_id=message.id,
            actor_key="anonymous:total",
            reactions=reactions
        )

    logger.info(
        "Reaction counts updated: chat=%s message=%s",
        event.chat.id,
        event.message_id
    )

#Обработка отредактированных сообщений

@router.edited_message()
async def collect_edited_message(message: Message, bot: Bot):

    if not is_allowed_chat(message.chat):
        return

    if message.has_protected_content:
        return

    logger.info(
        "Edited message received: chat=%s message=%s",
        message.chat.id,
        message.message_id
    )

    await collect_message(message, bot)

    logger.info(
        "Edited message saved: chat=%s message=%s",
        message.chat.id,
        message.message_id
    )