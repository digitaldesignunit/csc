#!/usr/bin/env python3.13
"""
The admin page "Mail templates" (decision 8.138 e): ``GET /admin/mail-templates``
renders every mail the catalog sends with invented sample data (HTML and plain
text, the subject and the Reply-To it would carry), and
``POST /admin/mail-templates/{kind}/test`` sends one of them to the signed-in
admin's own address through the normal send path (``email_service``). Admin
only; the test send is limited to ten an hour per admin.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Annotated, List, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.models import User
from limiter import local_limiter, signed_in_or_ip
from services import email_service
from settings import SettingsError, get_settings
from .auth import require_admin

router = APIRouter()

TEST_SEND_RATE = '10/hour'


class MailPreview(BaseModel):
    kind: str
    label: str
    when: str
    subject: str
    reply_to: Optional[str] = None
    html: str
    text: str


class MailPreviews(BaseModel):
    to: Optional[str] = None            # the admin's own address
    mails: List[MailPreview]


class TestSent(BaseModel):
    kind: str
    to: str


def preview_config() -> dict:
    """The parts of the mail configuration a preview needs: the links and the
    support address. No SMTP settings, so the page works where mail is not
    set up (the test send says so)."""
    settings = get_settings()
    return {
        'frontend_url': settings.frontend_url or 'http://localhost:3000',
        'reply_to': settings.smtp_reply_to,
    }


@router.get('/admin/mail-templates', response_model=MailPreviews,
            summary='Preview every mail with sample data (admin)')
async def preview_mail_templates(
    admin: Annotated[User, Depends(require_admin)],
) -> MailPreviews:
    config = preview_config()
    to = admin.email or 'you@example.org'
    mails = []
    for entry in email_service.MAIL_KINDS:
        mail = email_service.sample_mail(config, entry['kind'], to)
        mails.append(MailPreview(
            kind=entry['kind'], label=entry['label'], when=entry['when'],
            subject=mail.subject, reply_to=mail.reply_to,
            html=mail.html, text=mail.text))
    return MailPreviews(to=admin.email, mails=mails)


@router.post('/admin/mail-templates/{kind}/test', response_model=TestSent,
             summary='Send one sample mail to the signed-in admin (admin)')
@local_limiter.limit(TEST_SEND_RATE, key_func=signed_in_or_ip)
async def send_test_mail(
    request: Request,
    kind: str,
    admin: Annotated[User, Depends(require_admin)],
) -> TestSent:
    """The sample mail ``kind`` goes to the admin's own address, built and
    sent as the real mail is. A refused or failed send answers 502 with the
    reason, so the page can show it; an admin without an address gets 400."""
    if kind not in {entry['kind'] for entry in email_service.MAIL_KINDS}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'No such mail')
    if not admin.email:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            'Your account has no e-mail address to send the test to')
    try:
        config = email_service.load_email_config()
    except SettingsError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f'Mail is not set up on this server: {exc}')
    mail = email_service.sample_mail(config, kind, str(admin.email))
    failure = await run_in_threadpool(email_service.send_mail, config, mail)
    if failure:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f'The mail was not sent: {failure}')
    return TestSent(kind=kind, to=str(admin.email))
