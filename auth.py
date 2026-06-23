from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from passlib.context import CryptContext
from jose import JWTError, jwt
from database import get_db, AsyncSession
from models import User
from config import settings

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
router = APIRouter(prefix="/auth", tags=["Authentication"])

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    model_config = {"from_attributes": True}

def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)
def get_password_hash(password): return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id: raise HTTPException(401, "Invalid token")
    except JWTError: raise HTTPException(401, "Invalid token")
    user = await db.get(User, int(user_id))
    if not user or not user.is_active: raise HTTPException(401, "User not found")
    return user

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(select(User).where((User.username == payload.username) | (User.email == payload.email)))
    if exists.scalar_one_or_none(): raise HTTPException(400, "Username or email already exists")
    user = User(username=payload.username, email=payload.email, hashed_password=get_password_hash(payload.password))
    db.add(user); await db.commit(); await db.refresh(user)
    return user

@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.username == form_data.username))).scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    if not user.is_active: raise HTTPException(403, "Account disabled")
    token = create_access_token({"sub": user.username, "user_id": user.id})
    return TokenResponse(access_token=token, token_type="bearer")

@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)): return current_user7
