from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from config.database import get_db
from users.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    LoginRequest,
    LoginResponse,
    VerifyOTPRequest,
    TokenResponse,
    RefreshRequest,
    ChangePasswordRequest,
    GoogleAuthRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from users.services import UserService
from users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Use OAuth2 scheme for protected endpoints
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service)
) -> User:
    try:
        return user_service.get_current_user_from_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, user_service: UserService = Depends(get_user_service)):
    try:
        return user_service.create_user(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=LoginResponse)
def login(login_data: LoginRequest, user_service: UserService = Depends(get_user_service)):
    try:
        session_id = user_service.authenticate_user(login_data)
        return LoginResponse(requires_otp=True, session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def get_client_ip(request: Request) -> str:
    # 1. Check direct local device IP reported by browser client WebRTC
    device_ip = request.headers.get("x-device-ip") or request.headers.get("x-client-ip")
    if device_ip and device_ip.strip() and device_ip.strip() not in ("127.0.0.1", "localhost", "::1"):
        return device_ip.strip()

    # 2. Reverse proxy / forwarded headers if private network
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip and ip not in ("127.0.0.1", "localhost", "::1"):
            return ip

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip() not in ("127.0.0.1", "localhost", "::1"):
        return real_ip.strip()

    # 3. Direct connecting device socket IP
    if request.client and request.client.host and request.client.host not in ("127.0.0.1", "localhost", "::1"):
        return request.client.host

    # 4. Fallback to actual local network adapter IP
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "192.168.240.210"


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(
    verify_data: VerifyOTPRequest,
    request: Request,
    user_service: UserService = Depends(get_user_service)
):
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent") or "Chrome / Web Browser"
    try:
        return user_service.verify_otp(verify_data, ip_address=ip_address, user_agent=user_agent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/google", response_model=TokenResponse)
def google_auth(
    google_data: GoogleAuthRequest,
    request: Request,
    user_service: UserService = Depends(get_user_service)
):
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent") or "Chrome / Web Browser"
    try:
        return user_service.authenticate_google_user(google_data, ip_address=ip_address, user_agent=user_agent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    refresh_data: RefreshRequest,
    user_service: UserService = Depends(get_user_service)
):
    try:
        return user_service.refresh_access_token(refresh_data.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/logout")
def logout(
    logout_data: RefreshRequest,
    user_service: UserService = Depends(get_user_service)
):
    user_service.logout(logout_data.refresh_token)
    return {"detail": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
def update_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    try:
        updated = user_service.update_user(current_user.id, user_update)
        return UserResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    try:
        user_service.change_password(current_user.id, data.current_password, data.new_password)
        return {"detail": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# FORGOTTEN PASSWORD RESET ENDPOINTS (Public)
# ---------------------------------------------------------------------------

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    data: ForgotPasswordRequest,
    user_service: UserService = Depends(get_user_service)
):
    """
    Initiate the forgotten password flow.
    Sends a 6-digit OTP to the user's registered email address.
    """
    try:
        result = user_service.initiate_password_reset(data.email)
        return ForgotPasswordResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    data: ResetPasswordRequest,
    user_service: UserService = Depends(get_user_service)
):
    """
    Complete the password reset using the OTP received by email.
    """
    try:
        result = user_service.reset_password_with_otp(
            session_id=data.session_id,
            code=data.code,
            new_password=data.new_password,
        )
        return ResetPasswordResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# ADMIN EXCLUSIVE ENDPOINTS (Role: admin)
# ---------------------------------------------------------------------------

def require_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access this resource",
        )
    return current_user


@router.get("/admin/users")
def get_admin_users(
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    return user_service.get_admin_users_summary()


@router.get("/admin/sessions")
def get_admin_sessions(
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    return user_service.get_admin_active_sessions()


@router.post("/admin/sessions/{session_id}/revoke")
def revoke_session(
    session_id: int,
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    try:
        user_service.revoke_session_by_id(session_id)
        return {"detail": f"Session #{session_id} successfully revoked"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/admin/users/{user_id}/toggle-status")
def toggle_user_status(
    user_id: int,
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    try:
        return user_service.toggle_user_active_status(user_id, requesting_admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/admin/users/{user_id}/role")
def change_user_role(
    user_id: int,
    data: dict,
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    new_role = data.get("role", "user")
    try:
        return user_service.change_user_role(user_id, new_role, requesting_admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/admin/leaderboard")
def get_top_transactors(
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    return user_service.get_top_transactors_leaderboard()


@router.get("/admin/users/{user_id}/transactions")
def get_user_transactions(
    user_id: int,
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    return user_service.get_user_transactions_for_admin(user_id)


@router.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    data: dict,
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    new_password = data.get("new_password")
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters")
    try:
        return user_service.admin_reset_user_password(user_id, new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/admin/users/{user_id}/revoke-all-sessions")
def revoke_all_user_sessions(
    user_id: int,
    admin: User = Depends(require_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    try:
        return user_service.revoke_all_sessions_for_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))