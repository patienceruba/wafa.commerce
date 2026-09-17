import os
import dotenv

dotenv.load_dotenv(override=True)

# CORS settings
CORS_ORIGINS = ["*"]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "super_secret_fallback_key_for_development_purposes_only_change_me_in_prod")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "5"))

# SMTP Email Settings (Supports Gmail App Password)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER") or os.getenv("MAIL_USERNAME") or ""
# Support 'app' from .env or 'SMTP_PASS' / 'MAIL_PASSWORD'
_raw_app_pass = os.getenv("app") or os.getenv("SMTP_PASS") or os.getenv("MAIL_PASSWORD") or ""
SMTP_PASS = _raw_app_pass.replace(" ", "").strip()
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USER or "noreply@wafa.com"
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "WAFA Luxury Hub")


