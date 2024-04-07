#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from datetime import datetime, timedelta, timezone
from typing import Annotated, Union
import os
import json
import pathlib


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorClient


# LOCAL MODULE IMPORTS --------------------------------------------------------
from .models import (Token, # NOQA
                     TokenData,
                     User,
                     UserInDB)
from utility import sanitize_path


# ENVIRONMENT -----------------------------------------------------------------
_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(
                    pathlib.Path(_HERE).parent.parent.absolute(), "config"))

_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, "dbconfig.json"))
"""str: Default configuration file."""


def __get_db_connectionstring():
    """
    Read MongoDB connection string from config file.
    """
    with open(_CONFIGFILE, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        server = dbconfig['server']
        user = dbconfig['user']
        pwd = dbconfig['pwd']
    # compose mongodb connection string
    cstr = f'mongodb+srv://{user}:{pwd}@{server}'
    return cstr


def __get_auth_config():
    """
    Read auth config from config file.
    """
    with open(_CONFIGFILE, 'r') as configfile:
        config = json.load(configfile)
        secret = config['secret']
        algorithm = config['algorithm']
        expire = config['access_token_expire_minutes']
    return (secret, algorithm, expire)


(SECRET_KEY,
 ALGORITHM,
 ACCESS_TOKEN_EXPIRE_MINUTES) = __get_auth_config()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def get_user(username: str):
    mongodb_client = AsyncIOMotorClient(__get_db_connectionstring())
    mongodb = mongodb_client['csc']
    userdb = mongodb['users']

    user_doc = await userdb.find_one({'username': username})
    if user_doc:
        mongodb_client.close()
        return UserInDB(**user_doc)


async def authenticate_user(username: str, password: str):
    user = await get_user(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict,
                        expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = await get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
