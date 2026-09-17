import random
import string
import uuid
import logging
import requests
import argon2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from config.database import Sessionlocal
from config.settings import (
    JWT_SECRET,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    OTP_EXPIRE_MINUTES,
)
from users.models import User, RefreshToken, LoginActivity, OTPSession
from users.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    LoginRequest,
    VerifyOTPRequest,
    GoogleAuthRequest,
)
from services.email_service import send_otp_email, send_welcome_email

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing using Argon2id (OWASP-recommended)
# ---------------------------------------------------------------------------
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,   # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Legacy bcrypt hashes start with one of these prefixes.
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


def _is_bcrypt_hash(hashed_password: str) -> bool:
    return bool(hashed_password) and hashed_password.startswith(_BCRYPT_PREFIXES)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 (or legacy bcrypt) hash."""
    if not plain_password or not hashed_password:
        return False

    # Legacy bcrypt hashes — verify once with bcrypt, then rehash as Argon2 on next login.
    if _is_bcrypt_hash(hashed_password):
        try:
            import bcrypt  # imported lazily so it can be removed once all hashes are migrated
            return bcrypt.checkpw(
                plain_password.encode("utf-8")[:72],
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    try:
        _ph.verify(hashed_password, plain_password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using Argon2id."""
    if not password:
        raise ValueError("Password must not be empty")
    return _ph.hash(password)


def needs_rehash(hashed_password: str) -> bool:
    """True if the stored hash was made with outdated params or an old algorithm."""
    if not hashed_password:
        return True
    if _is_bcrypt_hash(hashed_password):
        return True  # upgrade legacy bcrypt to Argon2
    try:
        return _ph.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return True
    except Exception:
        return True


def resolve_device_ip(ip: str = None) -> str:
    if ip and ip.strip() and ip.strip() not in ("127.0.0.1", "localhost", "::1"):
        clean_ip = ip.strip()
        if (
            clean_ip.startswith("192.168.")
            or clean_ip.startswith("10.")
            or clean_ip.startswith("172.")
        ):
            return clean_ip
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "192.168.240.210"


class UserService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    # User creation
    # ------------------------------------------------------------------ #
    def create_user(self, user: UserCreate) -> UserResponse:
        try:
            clean_username = user.username.strip()
            clean_email = user.email.strip().lower()

            db_user = (
                self.db.query(User)
                .filter(User.username.ilike(clean_username))
                .first()
            )
            if db_user:
                raise ValueError("Username already exists")

            db_user = (
                self.db.query(User).filter(User.email.ilike(clean_email)).first()
            )
            if db_user:
                raise ValueError("Email already exists")

            hashed_password = get_password_hash(user.password)
            new_user = User(
                username=clean_username,
                email=clean_email,
                f_name=user.f_name or "User",
                l_name=user.l_name or "Member",
                phone=user.phone,
                role=user.role,
                hashed_password=hashed_password,
            )
            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)

            # Dispatch welcome email
            try:
                if clean_email:
                    send_welcome_email(clean_email, new_user.username)
            except Exception as mail_err:
                logger.warning(f"Failed to dispatch welcome email: {mail_err}")

            return UserResponse.model_validate(new_user)
        except Exception as e:
            self.db.rollback()
            raise e

    # ------------------------------------------------------------------ #
    # Login / OTP
    # ------------------------------------------------------------------ #
    def authenticate_user(self, login_data: LoginRequest) -> str:
        from sqlalchemy import or_

        identifier = (login_data.username or login_data.email or "").strip()

        # Find user by username OR email (case-insensitive)
        user = (
            self.db.query(User)
            .filter(
                or_(
                    User.username.ilike(identifier),
                    User.email.ilike(identifier),
                )
            )
            .first()
        )
        if not user or not verify_password(login_data.password, user.hashed_password):
            raise ValueError("Invalid username or password")

        if not user.is_active:
            raise ValueError("User account is inactive")

        # Transparently upgrade the stored hash (legacy bcrypt or outdated Argon2 params)
        if needs_rehash(user.hashed_password):
            try:
                user.hashed_password = get_password_hash(login_data.password)
                self.db.commit()
            except Exception as rehash_err:
                self.db.rollback()
                logger.warning(
                    f"Failed to rehash password for {user.username}: {rehash_err}"
                )

        # Generate 6-digit OTP code
        otp_code = "".join(random.choices(string.digits, k=6))
        session_id = str(uuid.uuid4())

        # Set expiration
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)

        # Save OTP Session
        otp_session = OTPSession(
            user_id=user.id,
            session_id=session_id,
            code=otp_code,
            expires_at=expires_at,
            failed_attempts=0,
        )
        try:
            self.db.add(otp_session)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

        # Print OTP for dev/debug (visible in terminal)
        print(
            f"\n========================================\n"
            f"[OTP DEBUG] OTP for user {user.username} ({user.email}): {otp_code}\n"
            f"========================================\n",
            flush=True,
        )
        logger.info(
            f"[OTP DEBUG] Generated OTP for user {user.username}: {otp_code} "
            f"(session {session_id})"
        )

        # Dispatch OTP via SMTP Email using configured Google App Password
        try:
            if user.email:
                send_otp_email(user.email, user.username, otp_code)
        except Exception as mail_err:
            logger.warning(f"Failed to dispatch OTP email: {mail_err}")

        return session_id

    def verify_otp(
        self,
        verify_data: VerifyOTPRequest,
        ip_address: str = None,
        user_agent: str = None,
    ) -> dict:
        otp_session = (
            self.db.query(OTPSession)
            .filter(OTPSession.session_id == verify_data.session_id)
            .first()
        )
        if not otp_session:
            raise ValueError("Invalid session ID")

        # Check failed attempts
        if otp_session.failed_attempts >= 3:
            raise ValueError("Session locked due to too many failed attempts")

        # Check expiration
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_naive = otp_session.expires_at.replace(tzinfo=None)

        if now_naive > expires_naive:
            raise ValueError("OTP code has expired")

        if otp_session.code != verify_data.code:
            # Increment failed attempts
            otp_session.failed_attempts += 1
            self.db.commit()
            raise ValueError("Invalid OTP code")

        # Success! Retrieve user and clear OTP session
        user = otp_session.user

        # Mark user email as verified upon successful OTP validation
        if not user.is_email_verified:
            user.is_email_verified = True
            self.db.add(user)

        # Generate Access and Refresh Tokens
        access_token, refresh_token = self._generate_auth_tokens(
            user, ip_address=ip_address, user_agent=user_agent
        )

        # Log login activity
        login_activity = LoginActivity(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        try:
            self.db.add(login_activity)
            # Delete OTP session to prevent reuse
            self.db.delete(otp_session)
            self.db.commit()
            self.db.refresh(user)
        except Exception as e:
            self.db.rollback()
            raise e

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
        }

    # ------------------------------------------------------------------ #
    # Google auth
    # ------------------------------------------------------------------ #
    def authenticate_google_user(
        self,
        google_data: GoogleAuthRequest,
        ip_address: str = None,
        user_agent: str = None,
    ) -> dict:
        if not google_data.credential:
            raise ValueError("Google authentication credential token is required.")

        # Verify the Google token cryptographically with Google's OAuth2 tokeninfo service
        verified_payload = None
        try:
            import urllib.request
            import json

            token = google_data.credential.strip()
            # If it's an ID Token (JWT with 3 parts)
            if token.count(".") == 2:
                verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            else:
                verify_url = (
                    f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={token}"
                )

            req = urllib.request.Request(
                verify_url, headers={"User-Agent": "PETS-Auth-Service/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    verified_payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Google Token verification failed: {e}")
            raise ValueError(
                "Invalid or expired Google authentication token. Verification failed."
            )

        if not verified_payload or not verified_payload.get("email"):
            raise ValueError("Could not verify Google account email.")

        # Check email_verified flag if present
        if (
            verified_payload.get("email_verified") is False
            or verified_payload.get("email_verified") == "false"
        ):
            raise ValueError("Google account email is not verified by Google.")

        email = str(verified_payload["email"]).strip().lower()
        f_name = verified_payload.get("given_name") or (
            verified_payload.get("name", "").split()[0]
            if verified_payload.get("name")
            else "Google"
        )
        l_name = verified_payload.get("family_name") or (
            " ".join(verified_payload.get("name", "").split()[1:])
            if verified_payload.get("name")
            and len(verified_payload.get("name", "").split()) > 1
            else "User"
        )

        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            # Create verified Google user
            base_username = email.split("@")[0].lower()
            clean_username = "".join(
                c for c in base_username if c.isalnum() or c in ("_", ".")
            )
            if len(clean_username) < 3:
                clean_username = f"user_{clean_username}"

            final_username = clean_username
            counter = 1
            while self.db.query(User).filter(User.username == final_username).first():
                final_username = f"{clean_username}_{counter}"
                counter += 1

            hashed_pwd = get_password_hash(str(uuid.uuid4()))
            user = User(
                username=final_username,
                email=email,
                f_name=f_name,
                l_name=l_name,
                role="user",
                hashed_password=hashed_pwd,
                is_active=True,
                is_email_verified=True,
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        else:
            if not user.is_active:
                raise ValueError(
                    "User account is inactive. Please contact system administrator."
                )
            if not user.is_email_verified:
                user.is_email_verified = True
                self.db.add(user)
                self.db.commit()

        # Generate Access and Refresh Tokens
        access_token, refresh_token = self._generate_auth_tokens(
            user, ip_address=ip_address, user_agent=user_agent
        )

        # Log login activity
        login_activity = LoginActivity(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        try:
            self.db.add(login_activity)
            self.db.commit()
        except Exception:
            self.db.rollback()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
        }

    # ------------------------------------------------------------------ #
    # Tokens
    # ------------------------------------------------------------------ #
    def refresh_access_token(self, refresh_token_str: str) -> dict:
        # Find refresh token
        db_token = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token == refresh_token_str)
            .first()
        )
        if not db_token or db_token.revoked:
            raise ValueError("Invalid or revoked refresh token")

        # Check expiry
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_naive = db_token.expires_at.replace(tzinfo=None)
        if now_naive > expires_naive:
            raise ValueError("Refresh token has expired")

        user = db_token.user

        # Generate new access and refresh tokens (rotation)
        access_token, new_refresh_token = self._generate_auth_tokens(user)

        try:
            # Revoke old token
            db_token.revoked = True
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
        }

    def logout(self, refresh_token_str: str):
        db_token = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token == refresh_token_str)
            .first()
        )
        if db_token:
            try:
                db_token.revoked = True
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                raise e

    def get_current_user_from_token(self, token: str) -> User:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id_str: str = payload.get("sub")
            if user_id_str is None:
                raise ValueError("Could not validate credentials")
            user_id = int(user_id_str)
        except (JWTError, ValueError):
            raise ValueError("Could not validate credentials")

        user = self.db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ValueError("User not found")
        if not user.is_active:
            raise ValueError("User is inactive")
        return user

    # ------------------------------------------------------------------ #
    # Profile / password
    # ------------------------------------------------------------------ #
    def update_user(self, user_id: int, user_update: UserUpdate) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        f_name = user_update.f_name or user_update.first_name
        l_name = user_update.l_name or user_update.last_name
        if f_name is not None:
            user.f_name = f_name.strip()
        if l_name is not None:
            user.l_name = l_name.strip()
        if user_update.phone is not None:
            user.phone = user_update.phone.strip() if user_update.phone else None
        if user_update.email is not None:
            existing = (
                self.db.query(User)
                .filter(User.email == user_update.email, User.id != user_id)
                .first()
            )
            if existing:
                raise ValueError("Email already in use")
            user.email = user_update.email
        if user_update.role is not None:
            user.role = user_update.role

        try:
            self.db.commit()
            self.db.refresh(user)
            return user
        except Exception as e:
            self.db.rollback()
            raise e

    def change_password(self, user_id: int, current_password: str, new_password: str):
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("Incorrect current password")

        user.hashed_password = get_password_hash(new_password)
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

    # ------------------------------------------------------------------ #
    # Internal: token generation
    # ------------------------------------------------------------------ #
    def _generate_auth_tokens(
        self, user: User, ip_address: str = None, user_agent: str = None
    ) -> tuple[str, str]:
        # Access Token payload
        access_token_expires = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "exp": access_token_expires,
        }
        access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        # Clean up / revoke old stale tokens for this user on the same device
        if user_agent:
            self.db.query(RefreshToken).filter(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked == False,
                RefreshToken.user_agent == user_agent,
            ).update({"revoked": True})
        else:
            self.db.query(RefreshToken).filter(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked == False,
            ).update({"revoked": True})

        # Refresh Token payload & store in database
        refresh_token_str = str(uuid.uuid4())
        refresh_token_expires = datetime.now(timezone.utc) + timedelta(
            days=REFRESH_TOKEN_EXPIRE_DAYS
        )

        db_refresh_token = RefreshToken(
            user_id=user.id,
            token=refresh_token_str,
            ip_address=resolve_device_ip(ip_address),
            user_agent=user_agent or "Chrome / Web Browser",
            expires_at=refresh_token_expires,
            revoked=False,
        )
        self.db.add(db_refresh_token)

        return access_token, refresh_token_str

    # ------------------------------------------------------------------ #
    # Admin: users
    # ------------------------------------------------------------------ #
    def get_admin_users_summary(self) -> list[dict]:
        from transactions.models import Transaction
        from accounts.models import Account

        users = self.db.query(User).order_by(User.id.asc()).all()
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        result = []
        for u in users:
            last_activity = (
                self.db.query(LoginActivity)
                .filter(LoginActivity.user_id == u.id)
                .order_by(LoginActivity.login_time.desc())
                .first()
            )
            active_tokens = (
                self.db.query(RefreshToken)
                .filter(
                    RefreshToken.user_id == u.id,
                    RefreshToken.revoked == False,
                    RefreshToken.expires_at > now_naive,
                )
                .all()
            )
            distinct_devices = len(
                set((t.ip_address, (t.user_agent or "")[:50]) for t in active_tokens)
            )
            active_sessions = max(1 if active_tokens else 0, distinct_devices)

            # Accounts count & breakdown
            user_accounts = (
                self.db.query(Account).filter(Account.user_id == u.id).all()
            )
            accounts_count = len(user_accounts)
            accounts_list = [
                {
                    "id": a.id,
                    "name": a.name,
                    "type": a.type,
                    "currency": a.currency,
                    "balance": a.balance,
                }
                for a in user_accounts
            ]

            txs = (
                self.db.query(Transaction).filter(Transaction.user_id == u.id).all()
            )
            tx_count = len(txs)

            spent_rwf = sum(
                t.amount
                for t in txs
                if (t.currency == "RWF" or (not t.currency and t.amount > 50))
                and t.type in ["expense", "debit", "payment"]
            )
            income_rwf = sum(
                t.amount
                for t in txs
                if (t.currency == "RWF" or (not t.currency and t.amount > 50))
                and t.type == "income"
            )
            spent_usd = sum(
                t.amount
                for t in txs
                if t.currency == "USD" and t.type in ["expense", "debit", "payment"]
            )
            income_usd = sum(
                t.amount for t in txs if t.currency == "USD" and t.type == "income"
            )

            result.append(
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "f_name": u.f_name,
                    "l_name": u.l_name,
                    "full_name": f"{u.f_name} {u.l_name}".strip(),
                    "role": u.role or "user",
                    "is_active": u.is_active,
                    "accounts_count": accounts_count,
                    "accounts_list": accounts_list,
                    "last_login": last_activity.login_time.isoformat()
                    if last_activity and last_activity.login_time
                    else None,
                    "last_ip": resolve_device_ip(
                        last_activity.ip_address if last_activity else None
                    ),
                    "last_user_agent": last_activity.user_agent
                    if last_activity
                    else None,
                    "active_sessions_count": active_sessions,
                    "total_transactions_count": tx_count,
                    "total_spent_rwf": spent_rwf,
                    "total_income_rwf": income_rwf,
                    "total_spent_usd": spent_usd,
                    "total_income_usd": income_usd,
                }
            )

        # Calculate rank based on transaction count
        result.sort(key=lambda x: x["total_transactions_count"], reverse=True)
        for idx, u in enumerate(result):
            u["transaction_rank"] = idx + 1

        return result

    def get_admin_active_sessions(self) -> list[dict]:
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        tokens = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.revoked == False,
                RefreshToken.expires_at > now_naive,
            )
            .order_by(RefreshToken.created_at.desc())
            .all()
        )
        seen_devices = set()
        result = []
        for t in tokens:
            device_key = (
                t.user_id,
                t.ip_address or "127.0.0.1",
                (t.user_agent or "Web Browser")[:50],
            )
            if device_key in seen_devices:
                continue
            seen_devices.add(device_key)

            u = t.user
            last_activity = (
                self.db.query(LoginActivity)
                .filter(LoginActivity.user_id == t.user_id)
                .order_by(LoginActivity.login_time.desc())
                .first()
            )
            last_active_time = (
                last_activity.login_time
                if last_activity and last_activity.login_time
                else t.created_at
            )
            # Active in the last 15 minutes is live online
            is_online = bool(
                last_active_time
                and (now_naive - last_active_time).total_seconds() < 900
            )

            result.append(
                {
                    "id": t.id,
                    "user_id": t.user_id,
                    "username": u.username if u else "Unknown",
                    "email": u.email if u else "",
                    "f_name": u.f_name if u else "",
                    "l_name": u.l_name if u else "",
                    "full_name": f"{u.f_name} {u.l_name}".strip() if u else "Unknown",
                    "role": u.role if u else "user",
                    "ip_address": resolve_device_ip(t.ip_address),
                    "user_agent": t.user_agent or "Chrome / Web Browser",
                    "is_online": is_online,
                    "last_active": last_active_time.isoformat()
                    if last_active_time
                    else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                    "revoked": t.revoked,
                }
            )
        return result

    def revoke_session_by_id(self, session_id: int):
        token = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.id == session_id)
            .first()
        )
        if not token:
            raise ValueError("Session not found")
        token.revoked = True
        self.db.commit()

    def toggle_user_active_status(self, user_id: int, requesting_admin_id: int) -> dict:
        if user_id == requesting_admin_id:
            raise ValueError("You cannot deactivate your own admin account")
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        user.is_active = not user.is_active
        self.db.commit()
        return {"id": user.id, "username": user.username, "is_active": user.is_active}

    def change_user_role(
        self, user_id: int, new_role: str, requesting_admin_id: int
    ) -> dict:
        if user_id == requesting_admin_id and new_role != "admin":
            raise ValueError("You cannot revoke your own admin permissions")
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        user.role = new_role
        self.db.commit()
        return {"id": user.id, "username": user.username, "role": user.role}

    def get_top_transactors_leaderboard(self) -> list[dict]:
        from transactions.models import Transaction
        from accounts.models import Account

        users = self.db.query(User).all()
        board = []
        for u in users:
            txs = (
                self.db.query(Transaction).filter(Transaction.user_id == u.id).all()
            )
            user_accounts = (
                self.db.query(Account).filter(Account.user_id == u.id).all()
            )

            tx_count = len(txs)
            total_spent = sum(
                t.amount for t in txs if t.type in ["expense", "debit", "payment"]
            )
            total_income = sum(t.amount for t in txs if t.type == "income")
            total_transfers = sum(t.amount for t in txs if t.type == "transfer")
            latest_tx = (
                max(txs, key=lambda x: x.transaction_date or datetime.min.date())
                if txs
                else None
            )

            last_activity = (
                self.db.query(LoginActivity)
                .filter(LoginActivity.user_id == u.id)
                .order_by(LoginActivity.login_time.desc())
                .first()
            )
            last_token = (
                self.db.query(RefreshToken)
                .filter(RefreshToken.user_id == u.id)
                .order_by(RefreshToken.created_at.desc())
                .first()
            )
            ip_addr = (
                last_activity.ip_address
                if last_activity and last_activity.ip_address
                else None
            ) or (last_token.ip_address if last_token else "127.0.0.1")

            board.append(
                {
                    "user_id": u.id,
                    "username": u.username,
                    "full_name": f"{u.f_name} {u.l_name}".strip(),
                    "email": u.email,
                    "role": u.role,
                    "is_active": u.is_active,
                    "last_ip": ip_addr,
                    "accounts_count": len(user_accounts),
                    "accounts_list": [
                        {
                            "id": a.id,
                            "name": a.name,
                            "type": a.type,
                            "currency": a.currency,
                        }
                        for a in user_accounts
                    ],
                    "transaction_count": tx_count,
                    "total_spent": total_spent,
                    "total_income": total_income,
                    "total_transfers": total_transfers,
                    "latest_transaction_date": str(latest_tx.transaction_date)
                    if latest_tx and latest_tx.transaction_date
                    else None,
                    "latest_description": latest_tx.description if latest_tx else None,
                }
            )
        board.sort(key=lambda x: x["transaction_count"], reverse=True)
        for idx, item in enumerate(board):
            item["rank"] = idx + 1
        return board

    def get_user_transactions_for_admin(self, user_id: int) -> list[dict]:
        from transactions.models import Transaction
        from accounts.models import Account

        txs = (
            self.db.query(Transaction)
            .filter(Transaction.user_id == user_id)
            .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            .all()
        )
        result = []
        for t in txs:
            da = (
                self.db.query(Account)
                .filter(Account.id == t.debit_account_id)
                .first()
                if t.debit_account_id
                else None
            )
            ca = (
                self.db.query(Account)
                .filter(Account.id == t.credit_account_id)
                .first()
                if t.credit_account_id
                else None
            )
            result.append(
                {
                    "id": t.id,
                    "amount": t.amount,
                    "currency": t.currency or "USD",
                    "type": t.type,
                    "description": t.description,
                    "transaction_date": str(t.transaction_date),
                    "debit_account_name": da.name if da else None,
                    "credit_account_name": ca.name if ca else None,
                    "merchant": t.merchant,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
            )
        return result

    def admin_reset_user_password(self, user_id: int, new_password: str) -> dict:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        user.hashed_password = get_password_hash(new_password)
        # Revoke all existing sessions for security
        self.db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update(
            {"revoked": True}
        )
        self.db.commit()
        return {
            "detail": f"Password for {user.username} has been reset and all active "
            f"sessions revoked"
        }

    def revoke_all_sessions_for_user(self, user_id: int) -> dict:
        count = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked == False,
            )
            .update({"revoked": True})
        )
        self.db.commit()
        return {"detail": f"Revoked {count} active session(s)"}

    # ------------------------------------------------------------------ #
    # Password Reset (Forgotten Password)
    # ------------------------------------------------------------------ #
    def initiate_password_reset(self, email: str) -> dict:
        """
        Initiate forgotten password flow.
        Generates an OTP and sends it to the user's registered email.
        Returns a session_id for OTP verification.
        """
        clean_email = email.strip().lower()
        user = self.db.query(User).filter(User.email.ilike(clean_email)).first()

        if not user:
            # Do not reveal whether the email exists (prevents enumeration).
            logger.info(f"Password reset requested for unknown email: {clean_email}")
            return {
                "message": "If an account with that email exists, a password reset code has been sent.",
                "session_id": str(uuid.uuid4()),
                "requires_otp": True,
            }

        if not user.is_active:
            raise ValueError("User account is inactive. Please contact support.")

        # Invalidate any previous active OTP sessions for this user
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.query(OTPSession).filter(
            OTPSession.user_id == user.id,
            OTPSession.expires_at > now_naive,
        ).delete()

        # Generate 6-digit OTP
        otp_code = "".join(random.choices(string.digits, k=6))
        session_id = str(uuid.uuid4())

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)

        otp_session = OTPSession(
            user_id=user.id,
            session_id=session_id,
            code=otp_code,
            expires_at=expires_at,
            failed_attempts=0,
        )

        try:
            self.db.add(otp_session)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

        # Debug print for local testing
        print(
            f"\n========================================\n"
            f"[PASSWORD RESET OTP] Code for {user.username} ({user.email}): {otp_code}\n"
            f"========================================\n",
            flush=True,
        )
        logger.info(
            f"[PASSWORD RESET] Generated OTP for {user.username}: {otp_code} "
            f"(session {session_id})"
        )

        # Reuse the existing OTP email dispatcher
        try:
            if user.email:
                send_otp_email(user.email, user.username, otp_code)
        except Exception as mail_err:
            logger.warning(f"Failed to dispatch password reset email: {mail_err}")

        return {
            "message": "If an account with that email exists, a password reset code has been sent.",
            "session_id": session_id,
            "requires_otp": True,
        }

    def verify_password_reset_otp(self, session_id: str, code: str) -> User:
        """
        Verify OTP for password reset and return the associated user.
        Does NOT consume the OTP session — consumption happens in reset_password_with_otp.
        """
        otp_session = (
            self.db.query(OTPSession)
            .filter(OTPSession.session_id == session_id)
            .first()
        )

        if not otp_session:
            raise ValueError("Invalid or expired reset session")

        if otp_session.failed_attempts >= 3:
            raise ValueError("Too many failed attempts. Please request a new reset code.")

        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_naive = otp_session.expires_at.replace(tzinfo=None)

        if now_naive > expires_naive:
            self.db.delete(otp_session)
            self.db.commit()
            raise ValueError("Reset code has expired. Please request a new one.")

        if otp_session.code != code:
            otp_session.failed_attempts += 1
            self.db.commit()
            remaining = max(0, 3 - otp_session.failed_attempts)
            raise ValueError(
                f"Invalid reset code. {remaining} attempt(s) remaining."
            )

        return otp_session.user

    def reset_password_with_otp(
        self,
        session_id: str,
        code: str,
        new_password: str,
    ) -> dict:
        """
        Verify the OTP and reset the user's password.
        Revokes all active refresh tokens and consumes the OTP session.
        """
        # Verify OTP (raises ValueError on failure)
        user = self.verify_password_reset_otp(session_id, code)

        # Update password using the same hasher used elsewhere in the app
        user.hashed_password = get_password_hash(new_password)
        if not user.is_email_verified:
            user.is_email_verified = True
            self.db.add(user)

        # Revoke all active sessions for security
        self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked == False,
        ).update({"revoked": True})

        # Consume the OTP session
        self.db.query(OTPSession).filter(
            OTPSession.session_id == session_id
        ).delete()

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

        logger.info(f"[PASSWORD RESET] Password successfully reset for {user.username}")

        return {
            "message": "Password has been reset successfully. Please log in with your new password.",
            "success": True,
        }