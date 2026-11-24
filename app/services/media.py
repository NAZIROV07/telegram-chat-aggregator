import hashlib
import logging
import re
from pathlib import Path
from uuid import uuid4

from aiogram.exceptions import TelegramAPIError

from app.config import STORAGE_DIR


logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024


def extract_media(message):
    if message.photo:
        return "photo", message.photo[-1]

    for media_type in (
        "document",
        "video",
        "audio",
        "voice",
        "animation",
        "video_note",
        "sticker"
    ):
        media = getattr(message, media_type, None)

        if media is not None:
            return media_type, media

    return None


async def download_media(bot, message, media_type, media):
    if message.has_protected_content:
        return None

    file_size = getattr(media, "file_size", None)

    if file_size and file_size > MAX_FILE_SIZE:
        logger.warning("File exceeds download limit")
        return None

    directory = (
        STORAGE_DIR
        / str(message.chat.id)
        / str(message.message_id)
    )

    directory.mkdir(parents=True, exist_ok=True)

    original_name = getattr(media, "file_name", None)

    extensions = {
        "photo": ".jpg",
        "video": ".mp4",
        "audio": ".mp3",
        "voice": ".ogg",
        "animation": ".mp4",
        "video_note": ".mp4",
        "sticker": ".webp"
    }

    suffix = Path(original_name).suffix if original_name else ""

    if not re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", suffix):
        suffix = extensions.get(media_type, ".bin")

    safe_name = hashlib.sha256(
        media.file_unique_id.encode()
    ).hexdigest()

    destination = directory / f"{safe_name}{suffix}"

    if destination.is_file():
        return destination.relative_to(STORAGE_DIR).as_posix()

    temporary = directory / f"{uuid4().hex}.part"

    try:
        await bot.download(
            media.file_id,
            destination=temporary,
            timeout=60
        )

        temporary.replace(destination)

        return destination.relative_to(STORAGE_DIR).as_posix()

    except (TelegramAPIError, OSError, TimeoutError) as error:
        logger.warning(
            "Media download failed: %s",
            type(error).__name__
        )
        return None

    finally:
        temporary.unlink(missing_ok=True)