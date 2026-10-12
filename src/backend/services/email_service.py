#!/usr/bin/env python3.13
"""
Mail of the catalog (decisions 8.124 and 8.138): verification, password reset,
invitation, "added to a dataset" and the admin's "dataset created" notice.

* Jinja2 templates in ``templates/mail/``: one layout (``base``) and one
  template per mail, each as HTML and plain text. English, the site's colour
  theme, no logo and no image; the subject prefix ``[CSC]`` and a footer that
  says why the address got the mail and links the imprint and the privacy
  notice. Every value that goes into the HTML is escaped.
* One sender: ``From`` is ``SMTP_FROM_NAME <SMTP_FROM_EMAIL>`` (the noreply
  mailbox). ``Reply-To`` is the acting moderator for the invitation and the
  member notice, and ``SMTP_REPLY_TO`` (the support address) for the
  verification and the password reset; absent when that is not set. The
  footer says who a reply reaches.
* The send functions block: routes call them with ``run_in_threadpool`` (or
  as a background task), never on the event loop. ``send_mails`` sends a
  bulk over **one** SMTP connection and says per mail whether it went out.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

SUBJECT_PREFIX = '[CSC]'


# CONFIGURATION ---------------------------------------------------------------

def load_email_config() -> Dict[str, str]:
    """
    Load email configuration from environment variables.

    Required env vars: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL,
    FRONTEND_URL.
    Optional env vars: SMTP_PORT (default 587), SMTP_FROM_NAME,
    SMTP_REPLY_TO (the support address: where a reply to a verification or
    a password-reset mail goes; none when unset), SMTP_DEV_MODE (default
    false).
    """
    return {
        'smtp_host': os.environ['SMTP_HOST'],
        'smtp_port': os.getenv('SMTP_PORT', '587'),
        'smtp_user': os.environ['SMTP_USER'],
        'smtp_password': os.environ['SMTP_PASSWORD'],
        'from_email': os.environ['SMTP_FROM_EMAIL'],
        'from_name': os.getenv('SMTP_FROM_NAME', 'Catalog of Second Chances'),
        'reply_to': os.getenv('SMTP_REPLY_TO', '').strip(),
        'frontend_url': os.environ['FRONTEND_URL'],
        'dev_mode': os.getenv('SMTP_DEV_MODE', 'false').lower() == 'true',
    }


# TOKEN GENERATION ------------------------------------------------------------

def generate_verification_token() -> str:
    """
    Generate a secure random token for email verification.
    Returns a URL-safe token string.
    """
    return secrets.token_urlsafe(32)


def get_token_expiry(hours: int = 24) -> datetime:
    """
    Get expiry timestamp for verification token.
    Default: 24 hours from now.
    """
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# THE TEMPLATES ---------------------------------------------------------------

@dataclass
class Mail:
    """One mail, ready to send."""
    to: str
    subject: str
    text: str
    html: str
    reply_to: Optional[str] = None       # "Name <address>" or an address


# The mails are Jinja2 files (decision 8.138 e): templates/mail/base.html.j2
# and base.txt.j2 are the layout, <kind>.html.j2 and <kind>.txt.j2 the words of
# one mail. HTML templates are autoescaped, the text ones are not (a plain-text
# mail must not show "&amp;"). A value a template lacks is an error, not a gap.
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / 'templates' / 'mail'

_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=('html.j2',),
                                 default_for_string=False, default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


def _base(config: Dict[str, str]) -> str:
    return (config.get('frontend_url') or 'http://localhost:3000').rstrip('/')


def render_mail(kind: str, config: Dict[str, str], *, to: str, subject: str,
                title: str, reason: str, preheader: str = '',
                button: Optional[tuple] = None,
                reply_to: Optional[str] = None,
                replies_reach: Optional[str] = None, **context) -> Mail:
    """Render ``templates/mail/<kind>.html.j2`` and ``.txt.j2`` into one
    mail. ``button`` is ``(label, url)``; ``reason`` completes "You received
    this email because ..."; ``replies_reach`` says who a reply reaches (given
    with ``reply_to``). The values in ``context`` are the words of the mail;
    the HTML escapes them, the text does not. Plain text and HTML say the
    same."""
    footer = f'You received this email because {reason}.'
    if reply_to and replies_reach:
        footer += f' Replies to this email reach {replies_reach}.'
    values = {
        'title': title,
        'preheader': preheader,
        'button_label': button[0] if button else '',
        'button_url': button[1] if button else '',
        'footer': footer,
        'imprint_url': f'{_base(config)}/imprint',
        'privacy_url': f'{_base(config)}/privacy',
        **context,
    }
    text = _ENV.get_template(f'{kind}.txt.j2').render(**values).strip() + '\n'
    page = _ENV.get_template(f'{kind}.html.j2').render(**values)
    return Mail(to=to, subject=f'{SUBJECT_PREFIX} {subject}', text=text,
                html=page, reply_to=reply_to)


def render(config: Dict[str, str], *, subject: str, title: str,
           paragraphs: Sequence[str], reason: str,
           button: Optional[tuple] = None, to: str,
           reply_to: Optional[str] = None,
           replies_reach: Optional[str] = None) -> Mail:
    """A mail made of plain paragraphs (the ``generic`` template): for a mail
    that has no template of its own yet. Escaped like the others."""
    return render_mail(
        'generic', config, to=to, subject=subject, title=title, reason=reason,
        button=button, reply_to=reply_to, replies_reach=replies_reach,
        paragraphs=list(paragraphs))


def _support(config: Dict[str, str]) -> Dict[str, Optional[str]]:
    """Reply-To of the mails that have no acting person: the support address
    (``SMTP_REPLY_TO``), none when it is not set."""
    address = (config.get('reply_to') or '').strip() or None
    return {'reply_to': address,
            'replies_reach': 'the support of the catalog' if address else None}


def _address(name: Optional[str], email: Optional[str]) -> Optional[str]:
    """``Name <address>`` for a Reply-To header; None without an address."""
    if not email:
        return None
    return formataddr((name or '', email)) if name else email


# THE MAILS -------------------------------------------------------------------

def verification_mail(config: Dict[str, str], to: str, full_name: str,
                      token: str) -> Mail:
    url = f'{_base(config)}/auth/verify-email?token={token}'
    return render_mail(
        'verification', config, to=to, subject='Verify your email address',
        title='Welcome to the Catalog of Second Chances',
        preheader='Verify your email address to activate your account.',
        button=('Verify email address', url),
        reason='someone registered an account with this address',
        full_name=full_name, **_support(config))


def reset_mail(config: Dict[str, str], to: str, full_name: str,
               token: str) -> Mail:
    url = f'{_base(config)}/auth/reset-password?token={token}'
    return render_mail(
        'reset', config, to=to, subject='Reset your password',
        title='Reset your password',
        preheader='Choose a new password. The link works once.',
        button=('Choose a new password', url),
        reason='a password reset was requested for the account with this '
               'address',
        full_name=full_name, **_support(config))


def invitation_mail(config: Dict[str, str], to: str, code: str,
                    inviter_name: str, inviter_email: Optional[str],
                    dataset_name, roles, expires_at: str) -> Mail:
    """The single-use registration link of an invitation (8.14). The link
    goes to the mailbox only, never to the inviter's screen."""
    url = f'{_base(config)}/auth/register?code={code}'
    return render_mail(
        'invitation', config, to=to,
        subject='You are invited to the Catalog of Second Chances',
        title='You are invited',
        preheader=f'{inviter_name} invited you to the Catalog of Second '
                  'Chances.',
        button=('Register', url),
        reason=f'{inviter_name} invited this address to the Catalog of '
               'Second Chances',
        reply_to=_address(inviter_name, inviter_email),
        replies_reach=inviter_name,
        inviter_name=inviter_name, dataset_name=dataset_name or '',
        roles=list(roles or []), expires_on=expires_at[:10])


def member_added_mail(config: Dict[str, str], to: str, full_name: str,
                      dataset_name: str, roles, by_name: str,
                      by_email: Optional[str]) -> Mail:
    """Tell an existing account it was added to a dataset (8.20)."""
    return render_mail(
        'member_added', config, to=to, subject='You were added to a dataset',
        title='Added to a dataset',
        preheader=f'{by_name} added you to a dataset.',
        button=('Open the catalog', _base(config)),
        reason=f'{by_name} added the account with this address to the '
               f'dataset "{dataset_name}"',
        reply_to=_address(by_name, by_email), replies_reach=by_name,
        full_name=full_name, by_name=by_name,
        dataset_name=dataset_name or '', roles=list(roles or []))


def dataset_created_mail(config: Dict[str, str], to: str, dataset_name: str,
                         slug: str, by_name: str, by_email: Optional[str]
                         ) -> Mail:
    """Tell an admin that an account created a dataset (8.139 i)."""
    return render_mail(
        'dataset_created', config, to=to, subject='A dataset was created',
        title='Dataset created',
        preheader=f'{by_name} created the dataset "{dataset_name}".',
        button=('Open the dataset', f'{_base(config)}/admin/datasets/{slug}'),
        reason='you are an admin of the Catalog of Second Chances',
        reply_to=_address(by_name, by_email), replies_reach=by_name,
        by_name=by_name, dataset_name=dataset_name, slug=slug)


# PREVIEW (the admin page "Mail templates") -----------------------------------

# the mails that exist, in the order the admin page shows them
MAIL_KINDS: List[Dict[str, str]] = [
    {'kind': 'verification', 'label': 'Verify your email address',
     'when': 'After registering: the link that activates the account.'},
    {'kind': 'reset', 'label': 'Reset your password',
     'when': 'After "Forgot password": a single-use link.'},
    {'kind': 'invitation', 'label': 'Invitation',
     'when': 'A moderator invites an address to a dataset.'},
    {'kind': 'member_added', 'label': 'Added to a dataset',
     'when': 'An existing account is added to a dataset.'},
    {'kind': 'dataset_created', 'label': 'Dataset created (admin notice)',
     'when': 'Sent to every admin when an account creates a dataset.'},
]

# invented: sample data never holds a real person
SAMPLE_PERSON = 'Ada Lovelace'
SAMPLE_INVITER = 'Charles Babbage'
SAMPLE_INVITER_ADDRESS = 'charles.babbage@example.org'


def sample_mail(config: Dict[str, str], kind: str, to: str) -> Mail:
    """The mail ``kind`` with invented data, built by the real builder (so
    the preview is the mail that goes out). Raises ``KeyError`` for a name
    that is not a mail."""
    builders = {
        'verification': lambda: verification_mail(
            config, to, SAMPLE_PERSON, 'sample-token'),
        'reset': lambda: reset_mail(
            config, to, SAMPLE_PERSON, 'sample-token'),
        'invitation': lambda: invitation_mail(
            config, to, 'SAMPLE-CODE', SAMPLE_INVITER, SAMPLE_INVITER_ADDRESS,
            'Sample dataset', ['contributor', 'reviewer'],
            '2026-12-31T00:00:00Z'),
        'member_added': lambda: member_added_mail(
            config, to, SAMPLE_PERSON, 'Sample dataset', ['contributor'],
            SAMPLE_INVITER, SAMPLE_INVITER_ADDRESS),
        'dataset_created': lambda: dataset_created_mail(
            config, to, 'Sample dataset', 'sample_dataset', SAMPLE_INVITER,
            SAMPLE_INVITER_ADDRESS),
    }
    return builders[kind]()


# SENDING (blocking: call it off the event loop) -------------------------------

def _message(config: Dict[str, str], mail: Mail) -> EmailMessage:
    msg = EmailMessage()
    msg['Subject'] = mail.subject
    msg['From'] = formataddr((config.get('from_name', 'CSC'),
                              config['from_email']))
    msg['To'] = mail.to
    if mail.reply_to:
        msg['Reply-To'] = mail.reply_to
    msg.set_content(mail.text)
    msg.add_alternative(mail.html, subtype='html')
    return msg


def _show(mail: Mail) -> None:
    print('\n' + '=' * 80)
    print(f'DEV MODE: mail not sent via SMTP --- To: {mail.to}')
    if mail.reply_to:
        print(f'Reply-To: {mail.reply_to}')
    print(f'Subject: {mail.subject}')
    print('-' * 80)
    print(mail.text)
    print('=' * 80 + '\n')


def send_mails(config: Dict[str, str], mails: Iterable[Mail]
               ) -> List[Optional[str]]:
    """Send these mails over one SMTP connection. Returns, per mail, None
    when it went out and the error text when it did not: one refused address
    does not stop the others, an unreachable server fails them all. In dev
    mode the mails are printed instead."""
    mails = list(mails)
    if not mails:
        return []
    if config.get('dev_mode'):
        for mail in mails:
            _show(mail)
        return [None] * len(mails)
    results: List[Optional[str]] = [None] * len(mails)
    done = [False] * len(mails)        # a mail the server took stays sent
    try:
        port = int(config.get('smtp_port', 587))
        with smtplib.SMTP(config['smtp_host'], port, timeout=30) as server:
            server.starttls()
            server.login(config['smtp_user'], config['smtp_password'])
            for index, mail in enumerate(mails):
                try:
                    server.send_message(_message(config, mail))
                    done[index] = True
                except smtplib.SMTPServerDisconnected:
                    raise                       # the rest cannot go on this one
                except (smtplib.SMTPException, ValueError) as exc:
                    results[index] = f'{type(exc).__name__}: {exc}'
                    done[index] = True          # decided: this one failed alone
    except (OSError, smtplib.SMTPException) as exc:
        for index in range(len(mails)):
            if not done[index]:
                results[index] = f'{type(exc).__name__}: {exc}'
    return results


def send_mail(config: Dict[str, str], mail: Mail) -> Optional[str]:
    """One mail: None when it went out, else the error text."""
    return send_mails(config, [mail])[0]
