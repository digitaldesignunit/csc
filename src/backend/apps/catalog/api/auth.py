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
from apps.catalog.models import Token, User, UserInDB # NOQA
from services.email_service import (
    generate_verification_token,
    get_token_expiry,
    send_verification_email,
    send_verification_resent_email,
    load_email_config
)
from limiter import limiter

# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()

# OAuth2 uses this tokenUrl - keep in sync with the route below
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

    # 1) Decode the JWT.
    # Algorithm is always taken from server config,
    # never from the token header.
    try:
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,
            algorithms=[request.app.state.jwt_algorithm],
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
            # print(f'{ts()} [AUTH] Matched user by _id (sub):', sub)
            pass

    if not doc and uname:
        doc = await users.find_one({'username': uname})
        if doc:
            # print(f'{ts()} [AUTH] Matched user by username:', uname)
            pass

    if not doc and email:
        doc = await users.find_one({'email': email})
        if doc:
            # print(f'{ts()} [AUTH] Matched user by email:', email)
            pass

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
    summary='Login (email or username) -> JWT'
)
@limiter.limit('10/minute')
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

    # Check if email is verified
    if not user.get('email_verified', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                'Email not verified. Please check your email '
                'for verification link.'
            ),
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
@limiter.limit('5/minute')
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

    # Generate verification token
    verification_token = generate_verification_token()
    verification_token_expires = get_token_expiry(hours=24)

    new_id = str(__import__('uuid').uuid4())
    doc = {
        '_id': new_id,
        'username': username,
        'full_name': full_name,
        'email': email,
        'hashed_password': get_password_hash(password),
        'disabled': False,
        'role': 'user',
        'email_verified': False,
        'verification_token': verification_token,
        'verification_token_expires': verification_token_expires,
    }
    await users.insert_one(doc)

    # Send verification email
    try:
        email_config = load_email_config()
        dev_mode = email_config.get('dev_mode', False)

        send_verification_email(
            email_config,
            email,
            full_name,
            verification_token,
            dev_mode=dev_mode
        )
    except Exception as e:
        print(f'{ts()} [AUTH] Failed to send verification email: {str(e)}')
        # Continue anyway - user is created, they can request resend

    return User(**doc)  # maps _id->id


@router.get('/verify-email',
            summary='Verify email address with token')
async def verify_email(
    token: str,
    users=Depends(users_coll),
):
    """
    Verify user's email address using the token sent via email.
    """
    if not token:
        raise HTTPException(400, 'Verification token is required')

    # Find user with this token
    user = await users.find_one({
        'verification_token': token,
    })

    if not user:
        raise HTTPException(400, 'Invalid or expired verification token')

    # Check if token is expired
    if user.get('verification_token_expires'):
        expires = user['verification_token_expires']
        # Handle both datetime objects and strings
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires.replace('Z', '+00:00'))
        elif isinstance(expires, datetime):
            # Make timezone-aware if it isn't already
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) > expires:
            raise HTTPException(
                400,
                'Verification token has expired. Please request a new one.'
            )

    # Update user: mark as verified, clear token
    await users.update_one(
        {'_id': user['_id']},
        {
            '$set': {'email_verified': True},
            '$unset': {
                'verification_token': '',
                'verification_token_expires': ''
            }
        }
    )

    print(f'{ts()} [AUTH] Email verified for user: {user.get("email")}')

    return {
        'message': 'Email verified successfully. You can now sign in.',
        'email': user.get('email')
    }


@router.post('/resend-verification',
             summary='Resend verification email')
@limiter.limit('3/minute')
async def resend_verification(
    request: Request,
    payload: dict,  # { email }
    users=Depends(users_coll),
):
    """
    Resend verification email to user.
    """
    email = (payload.get('email') or '').strip().lower()

    if not email:
        raise HTTPException(400, 'Email is required')

    # Find user
    user = await users.find_one({'email': email})

    if not user:
        # Don't reveal if user exists or not (security)
        return {
            'message': (
                'If an unverified account exists with this email, '
                'a verification email has been sent.'
            ),
        }

    # Check if already verified
    if user.get('email_verified', False):
        raise HTTPException(
            400,
            'Email is already verified. You can sign in.'
        )

    # Generate new verification token
    verification_token = generate_verification_token()
    verification_token_expires = get_token_expiry(hours=24)

    # Update user with new token
    await users.update_one(
        {'_id': user['_id']},
        {
            '$set': {
                'verification_token': verification_token,
                'verification_token_expires': verification_token_expires,
            }
        }
    )

    # Send verification email
    try:
        email_config = load_email_config()
        dev_mode = email_config.get('dev_mode', False)

        send_verification_resent_email(
            email_config,
            email,
            user.get('full_name', 'User'),
            verification_token,
            dev_mode=dev_mode
        )

        print(f'{ts()} [AUTH] Verification email resent to: {email}')
    except Exception as e:
        print(f'{ts()} [AUTH] Failed to resend verification email: {str(e)}')
        raise HTTPException(
            500,
            'Failed to send verification email. Please try again later.'
        )

    return {
        'message': (
            'If an unverified account exists with this email, '
            'a verification email has been sent.'
        ),
    }
