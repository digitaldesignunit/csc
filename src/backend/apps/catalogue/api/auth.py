#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from datetime import datetime, timedelta, timezone
import re
from typing import Annotated

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalogue.models import Token, User, UserInDB # NOQA

# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()

# OAuth2 uses this tokenUrl — keep in sync with the route below
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/token')
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# Only allow @*.tu-darmstadt.de emails (at registration; optional at login)
TU_REGEX = re.compile(r'^[^@]+@([^.]+\.)*tu-darmstadt\.de$', re.IGNORECASE)


# HELPERS ---------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _jwt_now():
    return datetime.now(timezone.utc)


def ts():
    """
    Creates a timestamp in YY:MM:DD-HH:MM:SS format.
    """
    timestamp = datetime.now().strftime('%y:%m:%d-%H:%M:%S')
    return timestamp


# FASTAPI DEPENDENCIES --------------------------------------------------------

async def users_coll(request: Request):
    return request.app.mongodb_users


# TOKEN ROUTE -----------------------------------------------------------------

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
        'sub': sub,
        'role': role,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp())
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


# AUTHENTICATION DEPENDENCIES -------------------------------------------------

async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> UserInDB:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    # 1) Decode the JWT (signed JWS). Auto-detect alg from header.
    try:
        header = jwt.get_unverified_header(token)
        alg = (header.get('alg') or
               getattr(request.app.state, 'jwt_algorithm', 'HS256'))
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,  # must equal NEXTAUTH_SECRET
            algorithms=[alg],
            options={'verify_aud': False},
        )
    except JWTError as e:
        print(f'{ts()} [AUTH] JWT decode error:', str(e))
        raise cred_exc

    # 2) Extract identity claims
    sub = payload.get('sub')
    uname = payload.get('username')
    email = payload.get('email')

    if not sub and not uname and not email:
        print(f'{ts()} [AUTH] No usable identity in token payload:', payload)
        raise cred_exc

    # 3) Look up the user: by _id (GUID), then username, then email
    users = request.app.mongodb_users
    doc = None

    if sub:
        doc = await users.find_one({'_id': sub})
        if doc:
            print(f'{ts()} [AUTH] Matched user by _id (sub):', sub)

    if not doc and uname:
        doc = await users.find_one({'username': uname})
        if doc:
            print(f'{ts()} [AUTH] Matched user by username:', uname)

    if not doc and email:
        doc = await users.find_one({'email': email})
        if doc:
            print(f'{ts()} [AUTH] Matched user by email:', email)

    if not doc:
        print(f'{ts()} [AUTH] No user found for sub/username/email:',
              sub,
              uname,
              email)
        raise cred_exc

    if doc.get('disabled'):
        print(f'{ts()} [AUTH] User is disabled:',
              doc.get('_id') or doc.get('username') or doc.get('email'))
        raise cred_exc

    # 4) Return your Pydantic user model
    try:
        return UserInDB(**doc)
    except Exception as e:
        print(f'{ts()} [AUTH] Failed to parse user doc into UserInDB:', e, doc)
        raise cred_exc


async def get_current_active_user(
    current_user: Annotated[UserInDB, Depends(get_current_user)]
):
    if current_user.disabled:
        print('[AUTH] Inactive user:', current_user.username)
        raise HTTPException(status_code=400, detail='Inactive user')
    return current_user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Admin role required'
        )
    return current_user


# ---------- routes ----------
@router.post(
    '/token',
    response_model=Token,
    summary='Login (email or username) → JWT'
)
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    users=Depends(users_coll),
):
    # OAuth2 form uses `.username` as the identifier field
    identifier = form_data.username.strip()
    user = await users.find_one({
        '$or': [{'email': identifier.lower()}, {'username': identifier}],
        'disabled': {'$ne': True},
    })
    if (
        not user or
        not verify_password(form_data.password, user['hashed_password'])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect username/email or password',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    token = create_access_token(
        secret=request.app.state.jwt_secret,
        algorithm=request.app.state.jwt_algorithm,
        sub=user['_id'],                      # subject = GUID _id
        role=user.get('role', 'user'),
        minutes=request.app.state.jwt_access_minutes,
    )
    return Token(access_token=token)


# Optional: registration endpoint (enforce TU domain)
@router.post('/register',
             response_model=User,
             status_code=201,
             summary='Register new user (@*.tu-darmstadt.de)')
async def register_user(
    request: Request,
    payload: dict,             # { username, full_name, email, password }
    users=Depends(users_coll),
):
    username = (payload.get('username') or '').strip()
    full_name = (payload.get('full_name') or '').strip()
    email = (payload.get('email') or '').strip().lower()
    password = payload.get('password') or ''

    if not username or not email or not password:
        raise HTTPException(400, 'username, email, password are required')
    if not TU_REGEX.match(email):
        raise HTTPException(400, 'Email must be @*.tu-darmstadt.de')

    # prevent duplicates
    if await users.find_one({'$or': [{'email': email},
                                     {'username': username}]}):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            'User with this email or username already exists')

    new_id = str(__import__('uuid').uuid4())
    doc = {
        '_id': new_id,
        'username': username,
        'full_name': full_name,
        'email': email,
        'hashed_password': get_password_hash(password),
        'disabled': False,
        'role': 'user',
    }
    await users.insert_one(doc)
    return User(**doc)  # maps _id->id
