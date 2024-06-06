#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import os


# FUNCTION DEFINITIONS --------------------------------------------------------

def sanitize_path(fp: str = '') -> str:
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


def mm_to_inches(mm):
    """Convert millimeters to inches."""
    return mm / 25.4


# CONFIG LOADING --------------------------------------------------------------

def get_db_connectionstring(config_file: str) -> str:
    """
    Read MongoDB connection string from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        server = dbconfig['server']
        user = dbconfig['user']
        pwd = dbconfig['pwd']
    # compose mongodb connection string
    cstr = f'mongodb+srv://{user}:{pwd}@{server}'
    return cstr


def get_cors_origins(config_file: str):
    """
    Read CORS origins from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        origins = dbconfig['origins']
    return origins


def get_preview_directory(config_file: str) -> str:
    """
    Read preview directory from config file.
    """
    with open(config_file, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        preview_dir = sanitize_path(dbconfig['preview_dir'])
    return preview_dir
