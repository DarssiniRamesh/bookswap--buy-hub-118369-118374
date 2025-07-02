"""REST endpoints for Book Swap Marketplace:
- Authentication: registration, login (JWT), profile CRUD
- Book: grid, detail, add/edit/delete, user's books
- Transactions: buy, swap, history
"""

from fastapi import APIRouter, HTTPException, Depends, status, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from passlib.context import CryptContext
import jwt
import os
from datetime import datetime, timedelta

from .models import (
    User, Book, Transaction, SwapRequest,
    AsyncSessionLocal, UserRole, TransactionStatus, SwapRequestStatus,
)

SECRET_KEY = os.getenv("JWT_SECRET", "supersecret")
JWT_ALGORITHM = os.getenv("JWT_ALGO", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES") or 60)

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

#############
# Pydantic Schemas
#############
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserRead(UserBase):
    id: int
    role: str
    created_at: datetime

    class Config:
        orm_mode = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)

class Token(BaseModel):
    access_token: str
    token_type: str

class BookBase(BaseModel):
    title: str
    author: str
    description: Optional[str] = None
    genre: Optional[str] = None
    price: float

class BookCreate(BookBase):
    pass

class BookRead(BookBase):
    id: int
    owner_id: int
    is_available: bool
    created_at: datetime

    class Config:
        orm_mode = True

class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    price: Optional[float] = None
    is_available: Optional[bool] = None

class TransactionRead(BaseModel):
    id: int
    user_id: Optional[int]
    book_id: Optional[int]
    amount: float
    status: str
    created_at: datetime

    class Config:
        orm_mode = True

class SwapRequestCreate(BaseModel):
    receiver_id: int
    book_id: int
    message: Optional[str] = None

class SwapRequestRead(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    book_id: int
    status: str
    requested_at: datetime
    message: Optional[str] = None

    class Config:
        orm_mode = True

#############
# Utility functions
#############
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub", None)
        if not username:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    # Find user
    q = await db.execute(select(User).where(User.username == username))
    user = q.scalar_one_or_none()
    if not user:
        raise credentials_exception
    return user

#############
# AUTHENTICATION ROUTES
#############

# PUBLIC_INTERFACE
@router.post("/auth/register", response_model=UserRead, summary="Register a new user", tags=["Authentication"])
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check uniqueness (username/email)
    q = await db.execute(select(User).where((User.username == user.username) | (User.email == user.email)))
    if q.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username or email already exists")
    new_user = User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        hashed_password=get_password_hash(user.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

# PUBLIC_INTERFACE
@router.post("/auth/login", response_model=Token, summary="Login with username & password", tags=["Authentication"])
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(User).where(User.username == form.username))
    user: User = q.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return Token(access_token=access_token, token_type="bearer")

# PUBLIC_INTERFACE
@router.get("/auth/me", response_model=UserRead, summary="Current user's profile", tags=["Authentication"])
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user

# PUBLIC_INTERFACE
@router.put("/auth/me", response_model=UserRead, summary="Update own profile", tags=["Authentication"])
async def update_my_profile(
    user_update: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    if user_update.full_name:
        current_user.full_name = user_update.full_name
    if user_update.password:
        current_user.hashed_password = get_password_hash(user_update.password)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user

# PUBLIC_INTERFACE
@router.delete("/auth/me", status_code=204, summary="Delete own profile", tags=["Authentication"])
async def delete_profile(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await db.delete(current_user)
    await db.commit()
    return

#############
# BOOK ROUTES
#############
# PUBLIC_INTERFACE
@router.post("/books/", response_model=BookRead, summary="Add a book", tags=["Books"])
async def add_book(book: BookCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_book = Book(**book.dict(), owner_id=current_user.id)
    db.add(new_book)
    await db.commit()
    await db.refresh(new_book)
    return new_book

# PUBLIC_INTERFACE
@router.get("/books/", response_model=List[BookRead], summary="List all books (grid)", tags=["Books"])
async def list_books(db: AsyncSession = Depends(get_db), skip: int = 0, limit: int = 20):
    q = await db.execute(select(Book).filter(Book.is_available).order_by(Book.created_at.desc()).offset(skip).limit(limit))
    return q.scalars().all()

# PUBLIC_INTERFACE
@router.get("/books/{book_id}", response_model=BookRead, summary="Get book details", tags=["Books"])
async def get_book(book_id: int, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(Book).where(Book.id == book_id))
    book = q.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book

# PUBLIC_INTERFACE
@router.put("/books/{book_id}", response_model=BookRead, summary="Edit a book", tags=["Books"])
async def edit_book(book_id: int, book: BookUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = await db.execute(select(Book).where(Book.id == book_id))
    db_book: Book = q.scalar_one_or_none()
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    if db_book.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Permission denied")
    for k, v in book.dict(exclude_unset=True).items():
        setattr(db_book, k, v)
    db.add(db_book)
    await db.commit()
    await db.refresh(db_book)
    return db_book

# PUBLIC_INTERFACE
@router.delete("/books/{book_id}", status_code=204, summary="Delete a book", tags=["Books"])
async def delete_book(book_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = await db.execute(select(Book).where(Book.id == book_id))
    db_book: Book = q.scalar_one_or_none()
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    if db_book.owner_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Permission denied")
    await db.delete(db_book)
    await db.commit()
    return

# PUBLIC_INTERFACE
@router.get("/my/books/", response_model=List[BookRead], summary="List my books", tags=["Books"])
async def list_my_books(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = await db.execute(select(Book).where(Book.owner_id == current_user.id))
    return q.scalars().all()

#############
# TRANSACTION ROUTES
#############

# PUBLIC_INTERFACE
@router.post("/transactions/buy/", response_model=TransactionRead, summary="Buy a book", tags=["Transactions"])
async def buy_book(book_id: int = Body(...), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = await db.execute(select(Book).where(Book.id == book_id))
    book: Book = q.scalar_one_or_none()
    if not book or not book.is_available:
        raise HTTPException(status_code=404, detail="Book not available")
    if book.owner_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own book")
    # Faux payment & book transfer; in prod integrate payments!
    transaction = Transaction(
        user_id=current_user.id,
        book_id=book.id,
        amount=book.price,
        status=TransactionStatus.COMPLETED
    )
    book.is_available = False
    db.add_all([transaction, book])
    await db.commit()
    await db.refresh(transaction)
    return transaction

# PUBLIC_INTERFACE
@router.post("/transactions/swap/", response_model=SwapRequestRead, summary="Request a book swap", tags=["Transactions"])
async def request_swap(swap: SwapRequestCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Cannot send to self
    if swap.receiver_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot swap with yourself")
    q = await db.execute(select(Book).where(Book.id == swap.book_id))
    book: Book = q.scalar_one_or_none()
    if not book or not book.is_available:
        raise HTTPException(status_code=404, detail="Book not available")
    if book.owner_id != swap.receiver_id:
        raise HTTPException(status_code=400, detail="Receiver does not own the book")
    # Only one pending swap per user, book, and target
    q2 = await db.execute(
        select(SwapRequest).where((SwapRequest.sender_id == current_user.id) & (SwapRequest.receiver_id == swap.receiver_id) & (SwapRequest.book_id == swap.book_id) & (SwapRequest.status == SwapRequestStatus.PENDING))
    )
    if q2.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Swap already requested and pending")
    swap_obj = SwapRequest(
        sender_id=current_user.id,
        receiver_id=swap.receiver_id,
        book_id=swap.book_id,
        message=swap.message
    )
    db.add(swap_obj)
    await db.commit()
    await db.refresh(swap_obj)
    return swap_obj

# PUBLIC_INTERFACE
@router.get("/transactions/history/", response_model=List[TransactionRead], summary="View my transaction history", tags=["Transactions"])
async def my_transaction_history(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = await db.execute(select(Transaction).where(Transaction.user_id == current_user.id))
    return q.scalars().all()

# PUBLIC_INTERFACE
@router.get("/transactions/swap-requests/", response_model=List[SwapRequestRead], summary="Swap requests involving me", tags=["Transactions"])
async def swap_requests_me(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = await db.execute(select(SwapRequest).where((SwapRequest.sender_id == current_user.id) | (SwapRequest.receiver_id == current_user.id)))
    return q.scalars().all()

# PUBLIC_INTERFACE
@router.post("/transactions/swap/{swap_id}/respond", response_model=SwapRequestRead, summary="Respond to a swap request", tags=["Transactions"])
async def respond_swap(
    swap_id: int,
    accept: bool = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = await db.execute(select(SwapRequest).where(SwapRequest.id == swap_id))
    swap: SwapRequest = q.scalar_one_or_none()
    if not swap:
        raise HTTPException(status_code=404, detail="Swap not found")
    if swap.receiver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    # Only update if pending
    if swap.status != SwapRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Already processed")
    swap.status = SwapRequestStatus.ACCEPTED if accept else SwapRequestStatus.REJECTED
    # If accepted, mark book as unavailable
    if accept:
        q_book = await db.execute(select(Book).where(Book.id == swap.book_id))
        book = q_book.scalar_one_or_none()
        if book:
            book.is_available = False
            db.add(book)
    db.add(swap)
    await db.commit()
    await db.refresh(swap)
    return swap

