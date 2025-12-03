from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.models.schemas import LoginRequest, LoginResponse, AuthStatus
from app.config import settings
from app.auth import create_access_token, verify_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


@router.post("/login", response_model=dict)
async def login(login_data: LoginRequest):
    """관리자 로그인"""
    if login_data.username == settings.admin_id and login_data.password == settings.admin_password:
        token = create_access_token(login_data.username)
        return {
            "success": True,
            "message": "로그인 성공",
            "user": login_data.username,
            "token": token
        }
    else:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")


@router.post("/logout", response_model=dict)
async def logout():
    """로그아웃 (클라이언트에서 토큰 삭제)"""
    return {"success": True, "message": "로그아웃되었습니다."}


@router.get("/status", response_model=AuthStatus)
async def get_auth_status(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """인증 상태 확인"""
    if not credentials:
        return AuthStatus(authenticated=False)
    
    try:
        username = verify_token(credentials.credentials)
        return AuthStatus(authenticated=True, username=username)
    except HTTPException:
        return AuthStatus(authenticated=False)

