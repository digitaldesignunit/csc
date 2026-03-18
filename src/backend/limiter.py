from fastapi import Request
from slowapi import Limiter


def _get_client_ip(request: Request) -> str:
    # Behind Apache reverse proxy on Uberspace,
    # the real IP is in X-Forwarded-For.
    # Take only the first (leftmost) entry, which is the original client.
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.client.host if request.client else '0.0.0.0'


limiter = Limiter(key_func=_get_client_ip)
