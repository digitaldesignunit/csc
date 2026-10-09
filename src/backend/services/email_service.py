#!/usr/bin/env python3.13
"""
Mail of the catalog (decision 8.124): verification, password reset,
invitation and "added to a dataset", all from one template.

* One template: plain text + HTML, English, the blue CI colour, the subject
  prefix ``[CSC]`` and a footer that says why the address got the mail and
  links the imprint. Every value that goes into the HTML is escaped.
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
import html
import os
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Dict, Iterable, List, Optional, Sequence

SUBJECT_PREFIX = '[CSC]'
CI_BLUE = '#4080ff'


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


# THE TEMPLATE ----------------------------------------------------------------

@dataclass
class Mail:
    """One mail, ready to send."""
    to: str
    subject: str
    text: str
    html: str
    reply_to: Optional[str] = None       # "Name <address>" or an address


def _base(config: Dict[str, str]) -> str:
    return (config.get('frontend_url') or 'http://localhost:3000').rstrip('/')


def _e(value) -> str:
    """HTML-escape one inserted value (text and attribute positions)."""
    return html.escape(str(value if value is not None else ''), quote=True)


def render(config: Dict[str, str], *, subject: str, title: str,
           paragraphs: Sequence[str], reason: str,
           button: Optional[tuple] = None, to: str,
           reply_to: Optional[str] = None,
           replies_reach: Optional[str] = None) -> Mail:
    """The one template. ``paragraphs`` and ``title`` are plain text and are
    escaped here; ``button`` is ``(label, url)``; ``reason`` completes "You
    received this email because ..."; ``replies_reach`` says who a reply
    reaches (given with ``reply_to``). Plain text and HTML say the same."""
    imprint = f'{_base(config)}/imprint'
    footer = f'You received this email because {reason}.'
    if reply_to and replies_reach:
        footer += f' Replies to this email reach {replies_reach}.'
    text_parts = [title, '']
    for paragraph in paragraphs:
        text_parts += [paragraph, '']
    if button:
        text_parts += [f'{button[0]}:', button[1], '']
    text_parts += ['--', footer, f'Catalog of Second Chances. Imprint: {imprint}']
    text = '\n'.join(text_parts) + '\n'

    body = ''.join(f'<p style="margin: 0 0 16px;">{_e(p)}</p>'
                   for p in paragraphs)
    link = ''
    if button:
        link = (
            '<p style="text-align: center; margin: 28px 0;">'
            f'<a href="{_e(button[1])}" style="background-color: {CI_BLUE}; '
            'color: #ffffff; padding: 12px 30px; text-decoration: none; '
            'border-radius: 6px; display: inline-block; font-weight: bold; '
            f'font-size: 16px;">{_e(button[0])}</a></p>'
            '<p style="margin: 0 0 16px; font-size: 13px; color: #555; '
            f'word-break: break-all;">{_e(button[1])}</p>')
    page = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1.0">'
        f'<title>{_e(title)}</title></head>'
        '<body style="margin: 0; padding: 20px; background-color: #f4f6fb; '
        'font-family: Arial, Helvetica, sans-serif; line-height: 1.6; '
        'color: #1f2937;">'
        '<div style="max-width: 600px; margin: 0 auto; background-color: '
        '#ffffff; border: 1px solid #dde3ef; border-top: 4px solid '
        f'{CI_BLUE}; border-radius: 8px; padding: 28px;">'
        f'<h1 style="color: {CI_BLUE}; font-size: 22px; margin: 0 0 20px;">'
        f'{_e(title)}</h1>{body}{link}'
        '<hr style="border: none; border-top: 1px solid #dde3ef; '
        'margin: 28px 0 16px;">'
        f'<p style="margin: 0; font-size: 12px; color: #555;">{_e(footer)}'
        '<br>Catalog of Second Chances &middot; '
        f'<a href="{_e(imprint)}" style="color: {CI_BLUE};">Imprint</a></p>'
        '</div></body></html>')
    return Mail(to=to, subject=f'{SUBJECT_PREFIX} {subject}', text=text,
                html=page, reply_to=reply_to)


def _roles_phrase(dataset_name, roles) -> str:
    if not dataset_name:
        return ''
    roles_text = ', '.join(roles) if roles else 'member'
    return f' to the dataset "{dataset_name}" as {roles_text}'


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


# THE FOUR MAILS --------------------------------------------------------------

def verification_mail(config: Dict[str, str], to: str, full_name: str,
                      token: str) -> Mail:
    url = f'{_base(config)}/auth/verify-email?token={token}'
    return render(
        config, to=to, subject='Verify your email address',
        title='Welcome to the Catalog of Second Chances',
        paragraphs=[
            f'Hello {full_name or "there"},',
            'Thank you for registering. To activate your account, verify '
            'your email address with the link below. The link expires in '
            '24 hours.',
            'If you did not create an account, you can ignore this email.'],
        button=('Verify email address', url),
        reason='someone registered an account with this address',
        **_support(config))


def reset_mail(config: Dict[str, str], to: str, full_name: str,
               token: str) -> Mail:
    url = f'{_base(config)}/auth/reset-password?token={token}'
    return render(
        config, to=to, subject='Reset your password',
        title='Reset your password',
        paragraphs=[
            f'Hello {full_name or "there"},',
            'A password reset was requested for the account with this '
            'address. Choose a new password with the link below. The '
            'link works once and expires in one hour.',
            'If you did not ask for this, you can ignore this email: your '
            'password stays as it is.'],
        button=('Choose a new password', url),
        reason='a password reset was requested for the account with this '
               'address',
        **_support(config))


def invitation_mail(config: Dict[str, str], to: str, code: str,
                    inviter_name: str, inviter_email: Optional[str],
                    dataset_name, roles, expires_at: str) -> Mail:
    """The single-use registration link of an invitation (8.14). The link
    goes to the mailbox only, never to the inviter's screen."""
    url = f'{_base(config)}/auth/register?code={code}'
    return render(
        config, to=to, subject='You are invited to the Catalog of Second '
                               'Chances',
        title='You are invited',
        paragraphs=[
            'Hello,',
            f'{inviter_name} has invited you to the Catalog of Second '
            f'Chances{_roles_phrase(dataset_name, roles)}.',
            'Register with this email address using the link below. The '
            f'link works once and expires on {expires_at[:10]}.',
            'If you did not expect this invitation, you can ignore this '
            'email.'],
        button=('Register', url),
        reason=f'{inviter_name} invited this address to the Catalog of '
               'Second Chances',
        reply_to=_address(inviter_name, inviter_email),
        replies_reach=inviter_name)


def member_added_mail(config: Dict[str, str], to: str, full_name: str,
                      dataset_name: str, roles, by_name: str,
                      by_email: Optional[str]) -> Mail:
    """Tell an existing account it was added to a dataset (8.20)."""
    return render(
        config, to=to, subject='You were added to a dataset',
        title='Added to a dataset',
        paragraphs=[
            f'Hello {full_name or "there"},',
            f'{by_name} added you{_roles_phrase(dataset_name, roles)} in '
            'the Catalog of Second Chances.'],
        button=('Open the catalog', _base(config)),
        reason=f'{by_name} added the account with this address to the '
               f'dataset "{dataset_name}"',
        reply_to=_address(by_name, by_email),
        replies_reach=by_name)


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
