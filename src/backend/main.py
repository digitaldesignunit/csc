#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import json


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from fastapi import FastAPI
import pymongo


# UTILITY ---------------------------------------------------------------------

def sanitize_path(fp: str = '') -> str:
    """Sanitizes a filepath an returns the result."""
    return os.path.abspath(os.path.realpath(os.path.normpath(fp)))


# ENVIRONMENT SETTINGS --------------------------------------------------------

_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIGFILE = sanitize_path(os.path.join(_HERE, "dbconfig.json"))
"""str: Default configuration file."""


# create fastapi instance
api = FastAPI()


def _get_db_connectionstring():
    with open(_CONFIGFILE, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        server = dbconfig['server']
        user = dbconfig['user']
        pwd = dbconfig['pwd']
    # compose mongodb connection string
    cstr = f'mongodb+srv://{user}:{pwd}@{server}'
    return cstr


@api.get('/')
def get_all_components():
    # Replace the placeholder with your Atlas connection string
    client = pymongo.MongoClient(_get_db_connectionstring())
    # get database
    db = client.csc
    # get sheets collection
    db_sheets = db.sheets
    # find all documents and return their ids
    alldocs = []
    for doc in db_sheets.find():
        alldocs.append(doc)
    return alldocs
