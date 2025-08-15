#!/usr/bin/env python3.9
from datetime import datetime, timedelta, timezone
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

from apps.catalogue.models import Token, TokenData, User, UserInDB # NOQA

router = APIRouter()

# OAuth2 uses this tokenUrl — keep in sync with the route below
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Only allow @*.tu-darmstadt.de emails (at registration; optional at login)
TU_REGEX = re.compile(r"^[^@]+@([^.]+\.)*tu-darmstadt\.de$", re.IGNORECASE)


# ---------- helpers ----------
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _jwt_now():
    return datetime.now(timezone.utc)


def create_access_token(
    secret: str,
    algorithm: str,
    sub: str,
    role: str,
    minutes: int
) -> str:
    now = _jwt_now()
    exp = now + timedelta(minutes=minutes)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp())
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


# ---------- deps ----------
async def users_coll(request: Request):
    return request.app.mongodb_users


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,
            algorithms=[request.app.state.jwt_algorithm],
        )
        sub = payload.get("sub")
        if sub is None:
            raise cred_exc
    except JWTError:
        raise cred_exc

    doc = await request.app.mongodb_users.find_one({"_id": sub})
    if not doc or doc.get("disabled"):
        raise cred_exc

    try:
        return User(**doc)  # maps Mongo {_id: "...", ...} to User(id=..., ...)
    except ValidationError:
        # If the stored document is malformed, treat as invalid credentials
        raise cred_exc


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.disabled is True:
        raise HTTPException(
            status_code=400,
            detail="Inactive user"
        )
    return current_user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    return current_user


# ---------- routes ----------
@router.post(
    "/token",
    response_model=Token,
    summary="Login (email or username) → JWT"
)
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    users=Depends(users_coll),
):
    # OAuth2 form uses `.username` as the identifier field
    identifier = form_data.username.strip()
    user = await users.find_one({
        "$or": [{"email": identifier.lower()}, {"username": identifier}],
        "disabled": {"$ne": True},
    })
    if (
        not user or
        not verify_password(form_data.password, user["hashed_password"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        secret=request.app.state.jwt_secret,
        algorithm=request.app.state.jwt_algorithm,
        sub=user["_id"],                      # subject = GUID _id
        role=user.get("role", "user"),
        minutes=request.app.state.jwt_access_minutes,
    )
    return Token(access_token=token)


# Optional: registration endpoint (enforce TU domain)
@router.post("/register",
             response_model=User,
             status_code=201,
             summary="Register new user (@*.tu-darmstadt.de)")
async def register_user(
    request: Request,
    payload: dict,             # { username, full_name, email, password }
    users=Depends(users_coll),
):
    username = (payload.get("username") or "").strip()
    full_name = (payload.get("full_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not username or not email or not password:
        raise HTTPException(400, "username, email, password are required")
    if not TU_REGEX.match(email):
        raise HTTPException(400, "Email must be @*.tu-darmstadt.de")

    # prevent duplicates
    if await users.find_one({"$or": [{"email": email},
                                     {"username": username}]}):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "User with this email or username already exists")

    new_id = str(__import__("uuid").uuid4())
    doc = {
        "_id": new_id,
        "username": username,
        "full_name": full_name,
        "email": email,
        "hashed_password": get_password_hash(password),
        "disabled": False,
        "role": "user",
    }
    await users.insert_one(doc)
    return User(**doc)  # maps _id->id
