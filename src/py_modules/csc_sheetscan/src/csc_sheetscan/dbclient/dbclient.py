# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import glob
import os
import json


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
import pymongo


# LOCAL MODULE IMPORTS --------------------------------------------------------
from csc_sheetscan.sheets import _SHEETS_DIR
from csc_sheetscan.utilities import sanitize_path, load_json_sheet


# ENVIRONMENT SETTINGS --------------------------------------------------------
_HERE = os.path.dirname(sanitize_path(__file__))
"""str: Path to directory of this particular file."""

_CONFIG_DIR = sanitize_path(os.path.join(_HERE, "config"))
"""str: Default directory for configuration files."""

_CONFIGFILE = sanitize_path(os.path.join(_CONFIG_DIR, "dbconfig.json"))
"""str: Default configuration file."""


# UTILITY FUNCTIONS -----------------------------------------------------------

def get_db_connectionstring():
    with open(_CONFIGFILE, 'r') as configfile:
        # Reading from json file
        dbconfig = json.load(configfile)
        server = dbconfig['server']
        user = dbconfig['user']
        pwd = dbconfig['pwd']
    # compose mongodb connection string
    cstr = f'mongodb+srv://{user}:{pwd}@{server}'
    return cstr


# FUNCTION DEFINITIONS --------------------------------------------------------

def add_sheet_files_to_db(input_dir: str = _SHEETS_DIR):
    """
    Adds a bunch of sheet files to the database. If the ID already exists, the
    doc in the database will be replaced completely.
    """
    # connect to mongodb using client
    client = pymongo.MongoClient(get_db_connectionstring())
    # get database
    db = client.csc
    # get sheets collection
    db_components = db.components
    # read from json sheets directory
    sheetfiles = glob.glob(os.path.join(input_dir, '*.json'))
    # read all files
    for i, sheet_file in enumerate(sheetfiles):
        # load json file
        json_obj = load_json_sheet(sheet_file)
        # add to mongodb
        try:
            db_id = db_components.insert_one(json_obj).inserted_id
            print(db_id)
        except pymongo.errors.DuplicateKeyError:
            print(f'Document with id {json_obj.get("_id")} '
                  'already exists! Replacing document...')
            mapping = {'_id': json_obj['_id']}
            db_components.replace_one(mapping, json_obj)
