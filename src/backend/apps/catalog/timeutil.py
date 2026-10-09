#!/usr/bin/env python3.13
"""ISO-8601 UTC timestamps as the catalog stores them ("...Z" strings),
parsed to aware datetimes for comparison. A string compare is wrong as soon
as one side has fractional seconds."""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from datetime import datetime, timedelta, timezone

# how much later than its stored value the true time may be, per precision
# (spec 2.7); `unknown` has no bound
PRECISION_SPAN = {
    'exact': timedelta(0),
    'day': timedelta(days=1),
    'month': timedelta(days=31),
    'year': timedelta(days=366),
    'unknown': None,
}


def parse_ts(value: str) -> datetime:
    """Aware UTC datetime of a stored timestamp; a bare date is midnight."""
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
