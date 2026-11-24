from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func
)

from app.db.db import Base


#1. Пользователи Telegram

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_bot = Column(Boolean, default=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


#2. Корпоративные чаты

class Chat(Base):
    __tablename__ = "chats"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    title = Column(String(255), nullable=False)
    chat_type = Column(String(50), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


#3. Сообщения

class Message(Base):
    __tablename__ = "messages"

    id = Column(BigInteger, primary_key=True)
    telegram_message_id = Column(BigInteger, nullable=False)

    chat_id = Column(
        BigInteger,
        ForeignKey("chats.id"),
        nullable=False
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True
    )

    sender_chat_id = Column(BigInteger, nullable=True)

    text = Column(Text, nullable=True)
    message_type = Column(String(50), nullable=False)

    reply_to_message_id = Column(BigInteger, nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=False)
    edited_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "telegram_message_id",
            name="uq_chat_message"
        ),
        Index("ix_messages_chat_date", "chat_id", "sent_at")
    )


#4. Вложения

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(BigInteger, primary_key=True)

    message_id = Column(
        BigInteger,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False
    )

    file_id = Column(Text, nullable=False)
    file_unique_id = Column(String(255), nullable=False)

    file_type = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=True)
    file_path = Column(Text, nullable=True)
    mime_type = Column(String(255), nullable=True)
    file_size = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "file_unique_id",
            name="uq_message_attachment"
        ),
    )


#5. Реакции

class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(BigInteger, primary_key=True)

    message_id = Column(
        BigInteger,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True
    )

    actor_key = Column(String(100), nullable=False)
    reaction_type = Column(String(255), nullable=False)
    count = Column(Integer, default=1, nullable=False)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "actor_key",
            "reaction_type",
            name="uq_message_reaction"
        ),
    )


#6. История выгрузок

class ExportLog(Base):
    __tablename__ = "export_logs"

    id = Column(BigInteger, primary_key=True)

    admin_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False
    )

    chat_id = Column(
        BigInteger,
        ForeignKey("chats.id"),
        nullable=False
    )

    date_from = Column(DateTime(timezone=True), nullable=False)
    date_to = Column(DateTime(timezone=True), nullable=False)

    message_count = Column(Integer, default=0)
    file_path = Column(Text, nullable=True)
    status = Column(String(50), default="pending")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )