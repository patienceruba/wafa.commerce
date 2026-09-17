import smtplib
import ssl
import logging
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from config.settings import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    MAIL_FROM,
    MAIL_FROM_NAME,
    OTP_EXPIRE_MINUTES
)

logger = logging.getLogger("email_service")
logging.basicConfig(level=logging.INFO)


def _get_smtp_config():
    import os
    import dotenv
    dotenv.load_dotenv(override=True)
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = (os.getenv("SMTP_USER") or os.getenv("GMAIL_USER") or os.getenv("MAIL_USERNAME") or "").strip()
    raw_pass = os.getenv("app") or os.getenv("SMTP_PASS") or os.getenv("MAIL_PASSWORD") or ""
    password = raw_pass.replace(" ", "").strip()
    from_name = os.getenv("MAIL_FROM_NAME", "WAFA Luxury Hub")
    from_email = os.getenv("MAIL_FROM") or user or ""
    return host, port, user, password, from_name, from_email


def _send_smtp_message_sync(to_email: str, subject: str, html_body: str, text_body: str = ""):
    """Internal synchronous worker that delivers email via SMTP."""
    host, port, user, password, from_name, from_email = _get_smtp_config()

    if not password:
        logger.warning("[EMAIL] SMTP Password / App Password not configured in .env. Email dispatch skipped.")
        return False

    if not user or "@" not in user:
        logger.warning(
            f"[EMAIL SETUP REQUIRED] Google SMTP server ({host}) requires your Gmail account address as SMTP_USER.\n"
            f"Please add your Gmail address to app/.env:\n"
            f"  SMTP_USER=your_email@gmail.com\n"
            f"The OTP code is displayed above in the terminal for local testing."
        )
        return False

    sender_email = user

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = formataddr((from_name, sender_email))
    message["To"] = to_email

    if text_body:
        message.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        message.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        if port == 465:
            # SSL Connection
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                server.login(sender_email, password)
                server.sendmail(sender_email, [to_email], message.as_string())
        else:
            # STARTTLS Connection (Default: 587)
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(sender_email, password)
                server.sendmail(sender_email, [to_email], message.as_string())

        logger.info(f"[EMAIL] Successfully dispatched email '{subject}' to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as auth_err:
        logger.error(
            f"[EMAIL AUTH ERROR] Failed to authenticate with SMTP server for sender ({sender_email}).\n"
            f"1. Check that SMTP_USER in .env matches the Gmail account where the App Password was generated.\n"
            f"2. Ensure the App Password in .env (app = {password[:4]}...{password[-4:] if len(password)>=8 else ''}) is active.\n"
            f"Details: {auth_err}"
        )
        return False
    except Exception as e:
        logger.error(f"[EMAIL ERROR] Failed sending email to {to_email}: {e}")
        return False


def send_email_async(to_email: str, subject: str, html_body: str, text_body: str = ""):
    """Dispatches email sending in a non-blocking background thread."""
    thread = threading.Thread(
        target=_send_smtp_message_sync,
        args=(to_email, subject, html_body, text_body),
        daemon=True
    )
    thread.start()


def send_otp_email(to_email: str, username: str, otp_code: str):
    """Sends a luxury branded OTP verification code email."""
    subject = f"🔐 Your WAFA Verification Code: {otp_code}"
    
    text_content = (
        f"Hello {username},\n\n"
        f"Your verification code for WAFA Luxury Hub is: {otp_code}\n\n"
        f"This code will expire in {OTP_EXPIRE_MINUTES} minutes.\n"
        f"If you did not request this code, please secure your account immediately.\n\n"
        f"— WAFA Luxury Hub Team"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Verification Code</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #0c0e14;
      color: #f1f5f9;
      margin: 0;
      padding: 30px 15px;
    }}
    .email-container {{
      max-width: 540px;
      margin: 0 auto;
      background: #151922;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
    }}
    .header {{
      background: linear-gradient(135deg, #1e2433 0%, #151922 100%);
      padding: 32px 24px;
      text-align: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }}
    .logo {{
      font-size: 26px;
      font-weight: 800;
      letter-spacing: 0.12em;
      color: #f59e0b;
      text-transform: uppercase;
      margin: 0;
    }}
    .subtitle {{
      font-size: 12px;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.15em;
      margin-top: 4px;
    }}
    .content {{
      padding: 36px 30px;
      text-align: center;
    }}
    .greeting {{
      font-size: 18px;
      font-weight: 600;
      color: #ffffff;
      margin-bottom: 12px;
    }}
    .instruction {{
      font-size: 14px;
      color: #94a3b8;
      line-height: 1.6;
      margin-bottom: 28px;
    }}
    .otp-card {{
      background: #0d1117;
      border: 1px solid rgba(245, 158, 11, 0.35);
      border-radius: 14px;
      padding: 24px 16px;
      margin: 0 auto 28px;
      max-width: 320px;
      box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);
    }}
    .otp-digits {{
      font-family: 'Courier New', Courier, monospace;
      font-size: 38px;
      font-weight: 800;
      letter-spacing: 8px;
      color: #f59e0b;
      margin: 0;
    }}
    .otp-expire {{
      font-size: 12px;
      color: #64748b;
      margin-top: 10px;
    }}
    .security-notice {{
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.2);
      border-radius: 10px;
      padding: 12px 16px;
      font-size: 12px;
      color: #fca5a5;
      line-height: 1.5;
      text-align: left;
      margin-bottom: 24px;
    }}
    .footer {{
      padding: 24px;
      text-align: center;
      font-size: 11px;
      color: #64748b;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      background: #11141c;
    }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="header">
      <div class="logo">WAFA</div>
      <div class="subtitle">Luxury & Prestige Commerce</div>
    </div>
    <div class="content">
      <div class="greeting">Hello, {username} 👋</div>
      <p class="instruction">
        Use the single-use 6-digit verification code below to complete your login and authenticate your VIP session:
      </p>

      <div class="otp-card">
        <div class="otp-digits">{otp_code}</div>
        <div class="otp-expire">⏱ Expires in {OTP_EXPIRE_MINUTES} minutes</div>
      </div>

      <div class="security-notice">
        ⚠️ <strong>Security Notice:</strong> Never share this code with anyone. WAFA staff will never ask for your verification code.
      </div>
    </div>
    <div class="footer">
      This is an automated notification from WAFA Security Services.<br>
      © 2026 WAFA Commerce. All rights reserved.
    </div>
  </div>
</body>
</html>"""

    send_email_async(to_email, subject, html_content, text_content)


def send_welcome_email(to_email: str, username: str):
    """Sends a welcome email to newly registered users."""
    subject = "🌟 Welcome to WAFA Luxury Hub!"
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: sans-serif; background: #0c0e14; color: #f1f5f9; padding: 25px; }}
    .box {{ max-width: 520px; margin: 0 auto; background: #151922; border-radius: 16px; border: 1px solid #2d3748; padding: 30px; text-align: center; }}
    .title {{ color: #f59e0b; font-size: 24px; font-weight: bold; margin-bottom: 15px; }}
    p {{ color: #94a3b8; line-height: 1.6; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="title">Welcome to WAFA, {username}!</div>
    <p>Your account has been successfully created. You now have access to exclusive luxury collections, verified merchant studios, and premium member rewards.</p>
  </div>
</body>
</html>"""

    send_email_async(to_email, subject, html_content, f"Welcome to WAFA, {username}!")


def send_order_confirmation_email(to_email: str, order_number: str, total_amount: float, customer_name: str):
    """Sends an order confirmation receipt email."""
    subject = f"🛍️ Order Confirmed #{order_number} - WAFA Luxury Hub"
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0c0e14; color: #f1f5f9; padding: 25px; margin: 0; }}
    .box {{ max-width: 520px; margin: 0 auto; background: #151922; border-radius: 16px; border: 1px solid #2d3748; padding: 32px; }}
    .logo {{ color: #f59e0b; font-size: 24px; font-weight: 800; letter-spacing: 0.1em; text-align: center; margin-bottom: 20px; }}
    .title {{ font-size: 20px; font-weight: bold; margin-bottom: 12px; color: #ffffff; text-align: center; }}
    .summary {{ background: #0d1117; border-radius: 12px; padding: 20px; margin: 20px 0; border: 1px solid rgba(255,255,255,0.06); }}
    .row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; color: #94a3b8; }}
    .row.total {{ font-weight: bold; color: #f59e0b; font-size: 18px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px; margin-top: 10px; }}
    p {{ color: #94a3b8; line-height: 1.6; font-size: 14px; }}
    .footer {{ text-align: center; font-size: 12px; color: #64748b; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="logo">WAFA LUXURY</div>
    <div class="title">Thank you for your order, {customer_name}!</div>
    <p>Your order <strong>#{order_number}</strong> has been received and is being prepared for dispatch.</p>
    <div class="summary">
      <div class="row"><span>Order Number:</span> <span>#{order_number}</span></div>
      <div class="row"><span>Status:</span> <span style="color:#10b981;">Processing</span></div>
      <div class="row total"><span>Total Amount:</span> <span>${total_amount:.2f}</span></div>
    </div>
    <p>You will receive tracking information as soon as your items are handed over to our courier.</p>
    <div class="footer">WAFA Luxury Commerce • Concierge Support</div>
  </div>
</body>
</html>"""

    send_email_async(to_email, subject, html_content, f"Order #{order_number} confirmed. Total: ${total_amount:.2f}")

