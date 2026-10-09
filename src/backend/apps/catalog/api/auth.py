#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from typing import Annotated, Optional

# THIRD PARTY MODULE IMPORTS --------------------------------------------------
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import bcrypt

# LOCAL MODULE IMPORTS --------------------------------------------------------
from apps.catalog.models import Token, User, UserInDB, UserPublic, RegisterPayload, ChangePasswordPayload # NOQA
from apps.catalog.models import PasswordResetConfirm, PasswordResetRequest
from apps.catalog.models import BCRYPT_MAX_PASSWORD_BYTES
from apps.catalog.models import normalize_username
from services import email_service
from services.email_service import (
    generate_verification_token,
    get_token_expiry,
    load_email_config
)
from limiter import limiter

# INIT ROUTER -----------------------------------------------------------------

# create router instance
router = APIRouter()

# OAuth2 uses this tokenUrl - keep in sync with the route below
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/token')
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl='/auth/token',
    auto_error=False,
)


def open_registration_domains() -> list:
    """CSC_OPEN_REGISTRATION_DOMAINS (comma-separated, default
    tu-darmstadt.de): self-registration without invitation (8.14)."""
    raw = os.getenv('CSC_OPEN_REGISTRATION_DOMAINS', 'tu-darmstadt.de')
    return [d.strip().lower().lstrip('.') for d in raw.split(',')
            if d.strip()]


def is_open_domain(email: str) -> bool:
    """The address's domain is an open domain or one of its subdomains."""
    domain = email.rsplit('@', 1)[-1].lower()
    return any(domain == d or domain.endswith('.' + d)
               for d in open_registration_domains())


# HELPERS ---------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Stored hashes were written by passlib on bcrypt < 5, which silently
    # truncated to 72 bytes; truncate the same way so old passwords verify.
    secret = plain_password.encode('utf-8')[:BCRYPT_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(secret, hashed_password.encode('utf-8'))
    except ValueError:  # malformed stored hash
        return False


def get_password_hash(password: str) -> str:
    # Payload validators cap passwords at 72 bytes, so bcrypt never truncates.
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode()


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

def token_predates_password(payload: dict, doc: dict) -> bool:
    """A token issued (``iat``, whole seconds) before the last password
    change is refused: a change or a reset signs out every other device and
    the Grasshopper session (8.124 a). The comparison is on whole seconds:
    a token issued in the second of the change is still good (the sign-in
    that follows a reset at once must work); the window it leaves is under a
    second."""
    changed = doc.get('password_changed_at')
    if not changed:
        return False
    if isinstance(changed, str):
        changed = datetime.fromisoformat(changed.replace('Z', '+00:00'))
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    issued = payload.get('iat')
    return not isinstance(issued, (int, float)) \
        or issued < int(changed.timestamp())


async def lookup_user_from_token(
    request: Request,
    token: str,
) -> Optional[UserInDB]:
    try:
        payload = jwt.decode(
            token,
            request.app.state.jwt_secret,
            algorithms=[request.app.state.jwt_algorithm],
            options={'verify_aud': False},
        )
    except JWTError as e:
        print(f'{ts()} [AUTH] JWT decode error:', str(e))
        return None

    sub = payload.get('sub')
    uname = payload.get('username')
    email = payload.get('email')

    if not sub and not uname and not email:
        return None

    users = request.app.mongodb_users
    doc = None

    if sub:
        doc = await users.find_one({'_id': sub})

    if not doc and uname:
        doc = await users.find_one({'username': normalize_username(uname)})

    if not doc and email:
        doc = await users.find_one({'email': email})

    if not doc or doc.get('disabled'):
        return None

    if token_predates_password(payload, doc):
        return None

    try:
        return UserInDB(**doc)
    except Exception as e:
        print(f'{ts()} [AUTH] Failed to parse user doc into UserInDB:', e, doc)
        return None


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> UserInDB:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    user = await lookup_user_from_token(request, token)
    if user is None:
        raise cred_exc
    return user


async def get_optional_current_user(
    request: Request,
    token: Annotated[Optional[str], Depends(oauth2_scheme_optional)],
) -> Optional[UserInDB]:
    if not token:
        return None
    return await lookup_user_from_token(request, token)


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
    # any case is accepted: emails and usernames are stored lowercase (8.28)
    identifier = form_data.username.strip().lower()
    user = await users.find_one({
        '$or': [{'email': identifier}, {'username': identifier}],
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
             response_model=UserPublic,
             status_code=201,
             summary='Register (open domains, or with an invitation code)')
@limiter.limit('5/minute')
async def register_user(
    request: Request,
    payload: RegisterPayload,
    users=Depends(users_coll),
):
    username = normalize_username(payload.username)
    full_name = payload.full_name.strip()
    email = payload.email.strip().lower()
    password = payload.password

    # late import: invitations depends on this module's auth dependencies
    from apps.catalog.api.invitations import grant_invitation, redeem

    invitation = None
    if payload.code:
        # the code proves the address received it: verified at once (8.14)
        invitation = await redeem(request, payload.code, email)
    elif not is_open_domain(email):
        raise HTTPException(
            400, 'Registration with this address needs an invitation; '
                 'ask a dataset moderator to invite you.')

    # prevent duplicates
    if await users.find_one({'$or': [{'email': email},
                                     {'username': username}]}):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            'User with this email or username already exists')

    if invitation is not None:
        new_id = str(__import__('uuid').uuid4())
        doc = {
            '_id': new_id, 'username': username, 'full_name': full_name,
            'email': email, 'hashed_password': get_password_hash(password),
            'disabled': False, 'role': 'user', 'email_verified': True,
            'verification_token': None, 'verification_token_expires': None,
            'invitation_id': invitation['_id'],
        }
        await users.insert_one(doc)
        await grant_invitation(request, invitation, new_id)
        return User(**doc)

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

    # Send verification email (off the event loop); a failure is logged, the
    # user is created and can ask for it again
    try:
        email_config = load_email_config()
        failure = await run_in_threadpool(
            email_service.send_mail, email_config,
            email_service.verification_mail(
                email_config, email, full_name, verification_token))
        if failure:
            print(f'{ts()} [AUTH] Verification email failed: {failure}')
    except Exception as e:
        print(f'{ts()} [AUTH] Failed to send verification email: {str(e)}')

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


@router.post('/change-password',
             status_code=200,
             summary='Change password for the authenticated user')
@limiter.limit('5/minute')
async def change_password(
    request: Request,
    payload: ChangePasswordPayload,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    users=Depends(users_coll),
):
    """
    Allows an authenticated user to change their own password.
    Requires the correct current password and a new password (min 8 chars).
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Current password is incorrect',
        )

    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='New password must differ from the current password',
        )

    new_hashed = get_password_hash(payload.new_password)
    # every other device and the Grasshopper session are signed out (8.124);
    # an open reset link is void too
    await users.update_one(
        {'_id': current_user.id},
        {'$set': {'hashed_password': new_hashed,
                  'password_changed_at': datetime.now(timezone.utc)},
         '$unset': {'password_reset_sha256': '',
                    'password_reset_expires': ''}},
    )

    print(f'{ts()} [AUTH] Password changed for user: {current_user.email}')
    return {'message': 'Password changed successfully. Sign in again.'}


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

    # Check if already verified - return the same neutral response as "user not
    # found" to avoid leaking whether a verified account exists for this email.
    if user.get('email_verified', False):
        return {
            'message': (
                'If an unverified account exists with this email, '
                'a verification email has been sent.'
            ),
        }

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

    # Send verification email (off the event loop). A failure goes to the
    # log: the answer must not tell whether the account exists.
    try:
        email_config = load_email_config()
        failure = await run_in_threadpool(
            email_service.send_mail, email_config,
            email_service.verification_mail(
                email_config, email, user.get('full_name', 'User'),
                verification_token))
        if failure:
            print(f'{ts()} [AUTH] Verification email failed: {failure}')
        else:
            print(f'{ts()} [AUTH] Verification email resent to: {email}')
    except Exception as e:
        print(f'{ts()} [AUTH] Failed to resend verification email: {str(e)}')

    return {
        'message': (
            'If an unverified account exists with this email, '
            'a verification email has been sent.'
        ),
    }


# PASSWORD RESET (decision 8.124 a) -------------------------------------------
RESET_TOKEN_HOURS = 1
RESET_MAILS_PER_HOUR = 3                   # per address (the limiter counts per IP)
RESET_ANSWER = {
    'message': ('If an account exists for this address, an email with a '
                'link to choose a new password has been sent.'),
}


def reset_token_sha256(token: str) -> str:
    """Only this hash is stored: a leaked database holds no usable link."""
    return hashlib.sha256(token.strip().encode('utf-8')).hexdigest()


def _send_reset_mail(email: str, full_name: str, token: str) -> None:
    """Blocking, run as a background task after the answer is out, so the
    answer takes the same time for a known and an unknown address. A failure
    goes to the log only: the answer must not tell whether the address has
    an account."""
    try:
        config = load_email_config()
        failure = email_service.send_mail(
            config, email_service.reset_mail(config, email, full_name, token))
        if failure:
            print(f'{ts()} [AUTH] Password reset mail failed: {failure}')
    except Exception as exc:
        print(f'{ts()} [AUTH] Password reset mail failed: {exc}')


@router.post('/password-reset', status_code=202,
             summary='Ask for a password reset mail (always 202)')
@limiter.limit('20/hour')
async def request_password_reset(
    request: Request,
    payload: PasswordResetRequest,
    background: BackgroundTasks,
    users=Depends(users_coll),
):
    """Always 202 with the same text: no account is revealed. For an enabled
    account a single-use token is stored (as a hash, one hour) and mailed;
    at most ``RESET_MAILS_PER_HOUR`` mails go to one address in an hour (the
    limiter counts the requests per client address)."""
    email = payload.email.strip().lower()
    user = await users.find_one({'email': email,
                                 'disabled': {'$ne': True}})
    token = secrets.token_urlsafe(32)
    digest = reset_token_sha256(token)
    if user is not None:
        now = datetime.now(timezone.utc)
        horizon = now.timestamp() - 3600
        recent = [t for t in user.get('password_reset_requests') or []
                  if isinstance(t, (int, float)) and t > horizon]
        if len(recent) < RESET_MAILS_PER_HOUR:
            await users.update_one(
                {'_id': user['_id']},
                {'$set': {
                    'password_reset_sha256': digest,
                    'password_reset_expires':
                        now + timedelta(hours=RESET_TOKEN_HOURS),
                    'password_reset_requests': [*recent, now.timestamp()]}})
            background.add_task(_send_reset_mail, email,
                                user.get('full_name') or user.get(
                                    'username') or '', token)
    return RESET_ANSWER


@router.post('/password-reset/confirm', status_code=200,
             summary='Choose a new password with the mailed token')
@limiter.limit('10/hour')
async def confirm_password_reset(
    request: Request,
    payload: PasswordResetConfirm,
    users=Depends(users_coll),
):
    """The token works once and for an hour. It sets the password, signs out
    every token issued before (``password_changed_at``) and, because the mail
    reached the mailbox, counts as the verification of the address."""
    digest = reset_token_sha256(payload.token)
    now = datetime.now(timezone.utc)
    match = {'password_reset_sha256': digest,
             'password_reset_expires': {'$gt': now},
             'disabled': {'$ne': True}}
    if await users.find_one(match, {'_id': 1}) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='This reset link is invalid or has expired. Ask for a '
                   'new one.')
    new_hashed = get_password_hash(payload.new_password)
    user = await users.find_one_and_update(
        match,
        {'$set': {'hashed_password': new_hashed, 'password_changed_at': now,
                  'email_verified': True},
         '$unset': {'password_reset_sha256': '',
                    'password_reset_expires': '',
                    'verification_token': '',
                    'verification_token_expires': ''}})
    if user is None:                # used by a second request meanwhile
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='This reset link is invalid or has expired. Ask for a '
                   'new one.')
    print(f'{ts()} [AUTH] Password reset for user: {user.get("email")}')
    return {'message': 'Password changed. You can now sign in.'}
