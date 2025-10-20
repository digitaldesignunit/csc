#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from typing import Dict


# CONFIGURATION ---------------------------------------------------------------

def load_email_config(config_path: str) -> Dict[str, str]:
    """
    Load email configuration from JSON file.

    Expected structure:
    {
        'smtp_host': 'your-uberspace-host.uberspace.de',
        'smtp_port': 587,
        'smtp_user': 'noreply@ddu.uber.space',
        'smtp_password': 'your-password',
        'from_email': 'noreply@ddu.uber.space',
        'from_name': 'Catalogue of Second Chances',
        'frontend_url': 'https://ddu.uber.space'
    }
    """
    with open(config_path, 'r', encoding='utf-8-sig') as f:
        config = json.load(f)
    return config


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
        <h1 style="color: #2563eb; margin-bottom: 20px;">Welcome to Catalogue of Second Chances!</h1>

        <p>Hello {full_name},</p>

        <p>Thank you for registering with the Catalogue of Second Chances. To complete your registration and activate your account, please verify your email address by clicking the button below:</p>

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
            This is an automated message from the Catalogue of Second Chances.<br>
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

Thank you for registering with the Catalogue of Second Chances. To complete your registration and activate your account, please verify your email address by clicking the link below:

{verification_url}

This verification link will expire in 24 hours.

If you did not create an account with us, please ignore this email.

---
This is an automated message from the Catalogue of Second Chances.
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
        msg['Subject'] = 'Verify Your Email - Catalogue of Second Chances'
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

        print(f'[EMAIL] Verification email sent to: {to_email}')
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
