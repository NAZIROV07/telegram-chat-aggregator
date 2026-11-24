import csv
import io
import json
from datetime import datetime, timezone
from zipfile import ZipFile, ZIP_DEFLATED
from uuid import uuid4

from app.config import (
    STORAGE_DIR,
    EXPORT_DIR,
    ADMIN_IDS,
    ALLOWED_CHAT_IDS
)

from app.db.models import User, Chat

from app.db.crud import (
    get_messages,
    get_attachments,
    get_reactions
)


def safe_csv(value):
    if isinstance(value, str):
        if value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value

    return value


def create_export(db, admin_id, chat_id, date_from, date_to):

    #Проверяем права доступа

    if admin_id not in ADMIN_IDS:
        raise PermissionError("Access denied")

    if chat_id not in ALLOWED_CHAT_IDS:
        raise PermissionError("Chat is not allowed")

    if date_from.utcoffset() is None or date_to.utcoffset() is None:
        raise ValueError("Timezone is required")

    if date_from >= date_to:
        raise ValueError("Invalid date range")

    chat = db.get(Chat, chat_id)

    if chat is None:
        raise ValueError("Chat not found")

    messages = get_messages(
        db,
        chat_id,
        date_from,
        date_to
    )

    result = []

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )

    archive_path = EXPORT_DIR / (
        f"export_{timestamp}_{uuid4().hex[:8]}.zip"
    )

    storage_root = STORAGE_DIR.resolve()

    try:
        with ZipFile(
            archive_path,
            mode="x",
            compression=ZIP_DEFLATED
        ) as archive:

            for message in messages:

                user = (
                    db.get(User, message.user_id)
                    if message.user_id is not None
                    else None
                )

                attachments = []

                for attachment in get_attachments(db, message.id):

                    archive_file = None

                    if attachment.file_path:

                        source = (
                            storage_root / attachment.file_path
                        ).resolve()

                        expected_directory = (
                            storage_root
                            / str(chat_id)
                            / str(message.telegram_message_id)
                        )

                        if (
                            source.is_relative_to(expected_directory)
                            and source.is_file()
                        ):
                            archive_file = (
                                f"media/{message.telegram_message_id}/"
                                f"{attachment.id}{source.suffix}"
                            )

                            archive.write(
                                source,
                                arcname=archive_file
                            )

                    attachments.append({
                        "type": attachment.file_type,
                        "name": attachment.file_name,
                        "size": attachment.file_size,
                        "mime_type": attachment.mime_type,
                        "path": archive_file,
                        "downloaded": archive_file is not None
                    })

                reactions = [
                    {
                        "actor": reaction.actor_key,
                        "user_id": reaction.user_id,
                        "reaction": reaction.reaction_type,
                        "count": reaction.count
                    }
                    for reaction in get_reactions(db, message.id)
                ]

                result.append({
                    "message_id": message.telegram_message_id,
                    "chat_id": message.chat_id,
                    "user_id": message.user_id,
                    "sender_chat_id": message.sender_chat_id,
                    "username": user.username if user else None,
                    "first_name": user.first_name if user else None,
                    "last_name": user.last_name if user else None,
                    "text": message.text,
                    "type": message.message_type,
                    "sent_at": message.sent_at.isoformat(),
                    "edited_at": (
                        message.edited_at.isoformat()
                        if message.edited_at else None
                    ),
                    "reply_to_message_id": message.reply_to_message_id,
                    "attachments": attachments,
                    "reactions": reactions
                })

            #Информация о выгрузке

            metadata = {
                "chat_id": chat_id,
                "chat_title": chat.title,
                "date_from": date_from.isoformat(),
                "date_to_exclusive": date_to.isoformat(),
                "message_count": len(result),
                "exported_at": datetime.now(
                    timezone.utc
                ).isoformat()
            }

            archive.writestr(
                "metadata.json",
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    indent=4
                )
            )

            #JSON

            archive.writestr(
                "messages.json",
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=4
                )
            )

            #SV для Excel

            buffer = io.StringIO()

            columns = [
                "message_id",
                "chat_id",
                "user_id",
                "sender_chat_id",
                "username",
                "first_name",
                "last_name",
                "text",
                "type",
                "sent_at",
                "edited_at",
                "reply_to_message_id",
                "attachments",
                "reactions"
            ]

            writer = csv.DictWriter(
                buffer,
                fieldnames=columns,
                delimiter=";"
            )

            writer.writeheader()

            for item in result:

                row = item.copy()

                row["attachments"] = json.dumps(
                    item["attachments"],
                    ensure_ascii=False
                )

                row["reactions"] = json.dumps(
                    item["reactions"],
                    ensure_ascii=False
                )

                writer.writerow({
                    key: safe_csv(value)
                    for key, value in row.items()
                })

            archive.writestr(
                "messages.csv",
                buffer.getvalue().encode("utf-8-sig")
            )

    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    return archive_path, len(result)