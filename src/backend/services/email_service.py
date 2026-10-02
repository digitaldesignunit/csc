#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from typing import Dict


# CONFIGURATION ---------------------------------------------------------------

def load_email_config() -> Dict[str, str]:
    """
    Load email configuration from environment variables.

    Required env vars: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL,
    FRONTEND_URL.
    Optional env vars: SMTP_PORT (default 587), SMTP_FROM_NAME,
    SMTP_DEV_MODE (default false).
    """
    return {
        'smtp_host': os.environ['SMTP_HOST'],
        'smtp_port': os.getenv('SMTP_PORT', '587'),
        'smtp_user': os.environ['SMTP_USER'],
        'smtp_password': os.environ['SMTP_PASSWORD'],
        'from_email': os.environ['SMTP_FROM_EMAIL'],
        'from_name': os.getenv('SMTP_FROM_NAME', 'Catalog of Second Chances'),
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


# EMAIL TEMPLATES -------------------------------------------------------------

def create_verification_email_html(
    full_name: str,
    verification_url: str
) -> str:
    """
    Create HTML email template for email verification.
    """
    return f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Your Email</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 30px; border-radius: 10px; border: 1px solid #e0e0e0;">
        <h1 style="color: #2563eb; margin-bottom: 20px;">Welcome to Catalog of Second Chances!</h1>

        <p>Hello {full_name},</p>

        <p>Thank you for registering with the Catalog of Second Chances. To complete your registration and activate your account, please verify your email address by clicking the button below:</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{verification_url}"
               style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                Verify Email Address
            </a>
        </div>

        <p>Or copy and paste this link into your browser:</p>
        <p style="background-color: #e0e0e0; padding: 10px; border-radius: 5px; word-break: break-all; font-size: 14px;">
            {verification_url}
        </p>

        <p><strong>This verification link will expire in 24 hours.</strong></p>

        <p>If you did not create an account with us, please ignore this email.</p>

        <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">

        <p style="font-size: 12px; color: #666;">
            This is an automated message from the Catalog of Second Chances.<br>
            Please do not reply to this email.
        </p>
    </div>
</body>
</html>
'''


def create_verification_email_text(
    full_name: str,
    verification_url: str
) -> str:
    """
    Create plain text email template for email verification.
    """
    return f'''
Hello {full_name},

Thank you for registering with the Catalog of Second Chances. To complete your registration and activate your account, please verify your email address by clicking the link below:

{verification_url}

This verification link will expire in 24 hours.

If you did not create an account with us, please ignore this email.

---
This is an automated message from the Catalog of Second Chances.
Please do not reply to this email.
'''


# EMAIL SENDING ---------------------------------------------------------------

def send_verification_email(
    config: Dict[str, str],
    to_email: str,
    full_name: str,
    verification_token: str,
    dev_mode: bool = False
) -> bool:
    """
    Send verification email to user.

    Args:
        config: Email configuration dictionary
        to_email: Recipient email address
        full_name: Recipient's full name
        verification_token: Verification token
        dev_mode: If True, log to console instead of sending email

    Returns:
        True if email was sent successfully (or logged in dev mode)
    """
    frontend_url = config.get('frontend_url', 'http://localhost:3000')
    verification_url = (
        f'{frontend_url}/auth/verify-email?token={verification_token}'
    )

    if dev_mode:
        print('\n' + '='*80)
        print('DEV MODE: Email verification link (not sent via SMTP):')
        print('-'*80)
        print(f'To: {to_email}')
        print(f'Name: {full_name}')
        print(f'Verification URL: {verification_url}')
        print('='*80 + '\n')
        return True

    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Verify Your Email - Catalog of Second Chances'
        msg['From'] = (
            f"{config.get('from_name', 'CSC')} <{config['from_email']}>"
        )
        msg['To'] = to_email

        # Create both plain text and HTML versions
        text_part = MIMEText(
            create_verification_email_text(full_name, verification_url),
            'plain'
        )
        html_part = MIMEText(
            create_verification_email_html(full_name, verification_url),
            'html'
        )

        # Attach parts (plain text first, HTML second for proper fallback)
        msg.attach(text_part)
        msg.attach(html_part)

        # Send email
        smtp_port = int(config.get('smtp_port', 587))
        with smtplib.SMTP(config['smtp_host'], smtp_port) as server:
            server.starttls()
            server.login(config['smtp_user'], config['smtp_password'])
            server.send_message(msg)

        return True

    except Exception as e:
        print(
            f'[EMAIL] Error sending verification email to {to_email}: {str(e)}'
        )
        return False


def send_verification_resent_email(
    config: Dict[str, str],
    to_email: str,
    full_name: str,
    verification_token: str,
    dev_mode: bool = False
) -> bool:
    """
    Send email when user requests to resend verification.
    Uses same template as initial verification.
    """
    return send_verification_email(
        config,
        to_email,
        full_name,
        verification_token,
        dev_mode
    )


# INVITATIONS AND MEMBERSHIP NOTICES (decisions 8.14, 8.20) -------------------

def send_mail(config: Dict[str, str], to_email: str, subject: str,
              text: str, html: str) -> bool:
    """Send one plain-text + HTML mail; in dev mode print it instead."""
    if config.get('dev_mode'):
        print('\n' + '=' * 80)
        print(f'DEV MODE: mail not sent via SMTP --- To: {to_email}')
        print(f'Subject: {subject}')
        print('-' * 80)
        print(text)
        print('=' * 80 + '\n')
        return True
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = (
            f"{config.get('from_name', 'CSC')} <{config['from_email']}>"
        )
        msg['To'] = to_email
        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))
        smtp_port = int(config.get('smtp_port', 587))
        with smtplib.SMTP(config['smtp_host'], smtp_port) as server:
            server.starttls()
            server.login(config['smtp_user'], config['smtp_password'])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f'[EMAIL] Error sending "{subject}" to {to_email}: {str(e)}')
        return False


def _simple_html(title: str, paragraphs, link_url=None,
                 link_label=None) -> str:
    body = ''.join(f'<p>{p}</p>' for p in paragraphs)
    button = ''
    if link_url:
        button = (
            '<div style="text-align: center; margin: 30px 0;">'
            f'<a href="{link_url}" style="background-color: #2563eb; '
            'color: white; padding: 12px 30px; text-decoration: none; '
            'border-radius: 5px; display: inline-block; font-weight: bold;">'
            f'{link_label}</a></div>'
            f'<p style="word-break: break-all; font-size: 14px;">{link_url}'
            '</p>')
    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
        '<body style="font-family: Arial, sans-serif; line-height: 1.6; '
        'color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">'
        f'<h1 style="color: #2563eb;">{title}</h1>{body}{button}'
        '<hr style="border: none; border-top: 1px solid #e0e0e0;">'
        '<p style="font-size: 12px; color: #666;">This is an automated '
        'message from the Catalog of Second Chances.<br>Please do not reply '
        'to this email.</p></body></html>')


def _role_phrase(dataset_name, roles) -> str:
    if not dataset_name:
        return ''
    roles_text = ', '.join(roles) if roles else 'member'
    return f' to the dataset "{dataset_name}" as {roles_text}'


def send_invitation_email(config: Dict[str, str], to_email: str, code: str,
                          inviter_name: str, dataset_name, roles,
                          expires_at: str) -> bool:
    """Mail the single-use registration link of an invitation (8.14)."""
    frontend_url = config.get('frontend_url', 'http://localhost:3000')
    url = f'{frontend_url}/auth/register?code={code}'
    invited = _role_phrase(dataset_name, roles)
    lines = [
        'Hello,',
        f'{inviter_name} has invited you to the Catalog of Second '
        f'Chances{invited}.',
        'Register with this email address using the link below. The link '
        f'works once and expires on {expires_at[:10]}.',
        'If you did not expect this invitation, please ignore this email.',
    ]
    text = '\n\n'.join(lines[:3] + [url] + lines[3:]) + (
        '\n\n---\nThis is an automated message from the Catalog of Second '
        'Chances.\nPlease do not reply to this email.\n')
    html = _simple_html('You are invited', lines, url, 'Register')
    return send_mail(config, to_email,
                     'Invitation - Catalog of Second Chances', text, html)


def send_member_added_email(config: Dict[str, str], to_email: str,
                            full_name: str, dataset_name: str, roles,
                            by_name: str) -> bool:
    """Tell an existing account it was added to a dataset (8.20)."""
    frontend_url = config.get('frontend_url', 'http://localhost:3000')
    lines = [
        f'Hello {full_name},',
        f'{by_name} added you{_role_phrase(dataset_name, roles)} in the '
        'Catalog of Second Chances.',
    ]
    text = '\n\n'.join(lines + [frontend_url]) + (
        '\n\n---\nThis is an automated message from the Catalog of Second '
        'Chances.\nPlease do not reply to this email.\n')
    html = _simple_html('Added to a dataset', lines, frontend_url,
                        'Open the catalog')
    return send_mail(config, to_email,
                     'Added to a dataset - Catalog of Second Chances',
                     text, html)
