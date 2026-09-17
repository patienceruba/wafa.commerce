from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Optional, Literal, Any
from datetime import datetime

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    f_name: Optional[str] = None
    l_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Literal["admin", "user", "owner"] = Field(default="user")

    @model_validator(mode="before")
    @classmethod
    def normalize_user_create(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Extract first and last names if available, or split full_name
            first = data.get("f_name") or data.get("first_name")
            last = data.get("l_name") or data.get("last_name")
            full = (data.get("full_name") or "").strip()

            if not first and full:
                parts = full.split(maxsplit=1)
                first = parts[0]
                if len(parts) > 1 and not last:
                    last = parts[1]

            # Fallback to username if name is omitted
            username_val = (data.get("username") or "").strip()
            if not first:
                first = username_val if len(username_val) >= 2 else "User"
            if not last:
                last = first if len(str(first)) >= 2 else "Member"

            data["f_name"] = str(first)[:50]
            data["l_name"] = str(last)[:50]
            if username_val:
                data["username"] = username_val
            if data.get("email"):
                data["email"] = str(data.get("email")).strip().lower()
        return data

class UserUpdate(BaseModel):
    f_name: Optional[str] = None
    l_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[Literal["admin", "user", "owner"]] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    f_name: str
    l_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    is_email_verified: bool = False
    is_admin: bool = False
    is_seller: bool = False
    is_subcriber: bool = False

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: str

    @model_validator(mode="before")
    @classmethod
    def normalize_login_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            identifier = data.get("username") or data.get("email") or ""
            data["username"] = str(identifier).strip()
        return data

class LoginResponse(BaseModel):
    requires_otp: bool = True
    session_id: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"

class VerifyOTPRequest(BaseModel):
    session_id: str
    code: Optional[str] = None
    otp: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_otp_code(cls, data: Any) -> Any:
        if isinstance(data, dict):
            code_val = data.get("code") or data.get("otp") or ""
            data["code"] = str(code_val).strip()
        return data

class RefreshRequest(BaseModel):
    refresh_token: str

class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    session_id: str
    requires_otp: bool = True


class ResetPasswordRequest(BaseModel):
    session_id: str
    code: Optional[str] = None
    otp: Optional[str] = None
    new_password: str = Field(..., min_length=6)

    @model_validator(mode="before")
    @classmethod
    def normalize_otp_code(cls, data: Any) -> Any:
        if isinstance(data, dict):
            code_val = data.get("code") or data.get("otp") or ""
            data["code"] = str(code_val).strip()
        return data


class ResetPasswordResponse(BaseModel):
    message: str
    success: bool = True