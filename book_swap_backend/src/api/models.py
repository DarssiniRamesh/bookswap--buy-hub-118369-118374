"""
SQLAlchemy ORM models for the Book Swap Marketplace backend.

Defines User, Book, Transaction, and SwapRequest models, and centralizes the database connection setup
with strong adherence to security via environment variables (.env-backed).
"""

import os
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, ForeignKey, Enum, Boolean, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import enum

# Load environment variables from .env file
load_dotenv()

# Database connection configuration using env variables
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_HOST = os.getenv('POSTGRES_URL')  # Host, possibly includes port, e.g., "localhost"
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')

DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

Base = declarative_base()

# Async SQLAlchemy engine and session
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# Enum type for user roles (optional)
class UserRole(enum.Enum):
    REGULAR = "regular"
    ADMIN = "admin"

# Enum type for transaction status
class TransactionStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

# Enum type for swap request status
class SwapRequestStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

# PUBLIC_INTERFACE
class User(Base):
    """
    A registered user of the Book Swap platform.
    """
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    full_name = Column(String(120), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.REGULAR, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")

    # Relationships
    books = relationship("Book", back_populates="owner", cascade="all, delete", passive_deletes=True)
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete", passive_deletes=True)
    swap_requests_sent = relationship(
        "SwapRequest", back_populates="sender", foreign_keys='SwapRequest.sender_id',
        cascade="all, delete", passive_deletes=True,
    )
    swap_requests_received = relationship(
        "SwapRequest", back_populates="receiver", foreign_keys='SwapRequest.receiver_id',
        cascade="all, delete", passive_deletes=True,
    )

# PUBLIC_INTERFACE
class Book(Base):
    """
    Book listed for sale or swap in the marketplace.
    """
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False, index=True)
    author = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    genre = Column(String(80), nullable=True)
    price = Column(Float, nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")

    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("User", back_populates="books")

    transactions = relationship("Transaction", back_populates="book", cascade="all, delete", passive_deletes=True)
    swap_requests = relationship("SwapRequest", back_populates="book", cascade="all, delete", passive_deletes=True)

# PUBLIC_INTERFACE
class Transaction(Base):
    """
    A record of a purchase transaction (e.g., user buys a book).
    """
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")

    user = relationship("User", back_populates="transactions")
    book = relationship("Book", back_populates="transactions")

# PUBLIC_INTERFACE
class SwapRequest(Base):
    """
    Represents a swap request between two users involving a book.
    """
    __tablename__ = "swap_requests"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(SwapRequestStatus), default=SwapRequestStatus.PENDING, nullable=False)
    requested_at = Column(DateTime, nullable=False, server_default="now()")
    message = Column(Text, nullable=True)

    sender = relationship("User", back_populates="swap_requests_sent", foreign_keys=[sender_id])
    receiver = relationship("User", back_populates="swap_requests_received", foreign_keys=[receiver_id])
    book = relationship("Book", back_populates="swap_requests")

    __table_args__ = (
        UniqueConstraint('sender_id', 'receiver_id', 'book_id', name='_unique_swap_participants_book'),
    )

# PUBLIC_INTERFACE
async def init_db():
    """Initializes all database tables. Call this at app startup for dev/prototyping ONLY."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
