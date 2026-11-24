from sqlalchemy import select, delete, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import (
    User,
    Chat,
    Message,
    Attachment,
    Reaction,
    ExportLog
)


#Универсальное сохранение без дублирования

def upsert(db, model, values, conflict_columns):
    stmt = insert(model).values(**values)

    update_values = {
        key: stmt.excluded[key]
        for key in values
        if key not in conflict_columns
    }

    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_columns,
        set_=update_values
    )

    stmt = stmt.returning(model.id)

    return db.execute(stmt).scalar_one()


#Пользователи

def save_user(
    db,
    user_id,
    username=None,
    first_name=None,
    last_name=None,
    is_bot=False
):
    return upsert(
        db,
        User,
        {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "is_bot": is_bot
        },
        ["id"]
    )


#Чаты

def save_chat(db, chat_id, title, chat_type):
    return upsert(
        db,
        Chat,
        {
            "id": chat_id,
            "title": title,
            "chat_type": chat_type
        },
        ["id"]
    )


def get_chats(db, allowed_chat_ids):
    return db.scalars(
        select(Chat)
        .where(Chat.id.in_(allowed_chat_ids))
        .order_by(Chat.title)
    ).all()


#Сообщения

def save_message(
    db,
    telegram_message_id,
    chat_id,
    sent_at,
    message_type,
    user_id=None,
    sender_chat_id=None,
    text=None,
    reply_to_message_id=None,
    edited_at=None
):
    return upsert(
        db,
        Message,
        {
            "telegram_message_id": telegram_message_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "sender_chat_id": sender_chat_id,
            "text": text,
            "message_type": message_type,
            "reply_to_message_id": reply_to_message_id,
            "sent_at": sent_at,
            "edited_at": edited_at
        },
        ["chat_id", "telegram_message_id"]
    )


def get_message(db, chat_id, telegram_message_id):
    return db.scalar(
        select(Message).where(
            Message.chat_id == chat_id,
            Message.telegram_message_id == telegram_message_id
        )
    )


def get_messages(db, chat_id, date_from, date_to):
    return db.scalars(
        select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.sent_at >= date_from,
            Message.sent_at < date_to
        )
        .order_by(Message.sent_at, Message.id)
    ).all()


#Вложения

def save_attachment(
    db,
    message_id,
    file_id,
    file_unique_id,
    file_type,
    file_name=None,
    file_path=None,
    mime_type=None,
    file_size=None
):
    return upsert(
        db,
        Attachment,
        {
            "message_id": message_id,
            "file_id": file_id,
            "file_unique_id": file_unique_id,
            "file_type": file_type,
            "file_name": file_name,
            "file_path": file_path,
            "mime_type": mime_type,
            "file_size": file_size
        },
        ["message_id", "file_unique_id"]
    )


def get_attachments(db, message_id):
    return db.scalars(
        select(Attachment).where(
            Attachment.message_id == message_id
        )
    ).all()


#Реакции

def replace_reactions(
    db,
    message_id,
    actor_key,
    reactions,
    user_id=None
):
    db.execute(
        delete(Reaction).where(
            Reaction.message_id == message_id,
            Reaction.actor_key == actor_key
        )
    )

    for reaction_type, count in reactions.items():
        if count > 0:
            db.add(
                Reaction(
                    message_id=message_id,
                    user_id=user_id,
                    actor_key=actor_key,
                    reaction_type=reaction_type,
                    count=count
                )
            )

    db.flush()


def get_reactions(db, message_id):
    return db.scalars(
        select(Reaction).where(
            Reaction.message_id == message_id
        )
    ).all()


#История выгрузок

def create_export_log(
    db,
    admin_id,
    chat_id,
    date_from,
    date_to
):
    log = ExportLog(
        admin_id=admin_id,
        chat_id=chat_id,
        date_from=date_from,
        date_to=date_to,
        status="pending",
        message_count=0
    )

    db.add(log)
    db.flush()

    return log.id


def finish_export_log(
    db,
    log_id,
    status,
    message_count=0,
    file_path=None
):
    db.execute(
        update(ExportLog)
        .where(ExportLog.id == log_id)
        .values(
            status=status,
            message_count=message_count,
            file_path=file_path
        )
    )