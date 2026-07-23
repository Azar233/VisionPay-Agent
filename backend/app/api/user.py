"""Profile settings and administrator-only user/role queries."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.database.session import get_db
from app.entity.schemas import (
    AgentCustomInstructionsUpdate,
    ChangePassword,
    CustomerModePassword,
    UserUpdate,
)
from app.services.user_service import user_service

router = APIRouter(prefix="/api/user", tags=["用户管理"])
AVATAR_EXTENSIONS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
}


def _avatar_dir() -> Path:
    path = Path(settings.MEDIA_ROOT).resolve() / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _remove_local_avatar(avatar_url: str | None) -> None:
    if not avatar_url or not avatar_url.startswith("/media/avatars/"):
        return
    filename = Path(avatar_url).name
    if filename:
        (_avatar_dir() / filename).unlink(missing_ok=True)


def require_admin(current_user=Depends(get_current_user)):
    if not user_service.is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可查询用户与权限信息")
    return current_user


@router.get("/list", summary="用户列表（管理员）")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=100),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return user_service.list_users(db, page=page, page_size=page_size, keyword=keyword)


@router.get("/roles", summary="角色列表（管理员）")
def list_roles(
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {"roles": user_service.list_roles(db)}


@router.put("/profile", summary="更新个人信息")
def update_profile(
    request: UserUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    changes = request.model_dump(exclude_unset=True)
    previous_avatar = current_user.avatar
    result = user_service.update_profile(db, current_user.id, **changes)
    if "avatar" in changes and result["user"].get("avatar") != previous_avatar:
        _remove_local_avatar(previous_avatar)
    return result


@router.get("/agent-instructions", summary="读取当前用户的 Agent 自定义指令")
def get_agent_custom_instructions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.get_agent_custom_instructions(db, int(current_user.id))


@router.put("/agent-instructions", summary="更新当前用户的 Agent 自定义指令")
def update_agent_custom_instructions(
    request: AgentCustomInstructionsUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.update_agent_custom_instructions(
        db,
        int(current_user.id),
        instructions=request.instructions,
    )


@router.post("/avatar", summary="上传用户头像")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AVATAR_EXTENSIONS:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG、WEBP 或 BMP 头像")

    limit = settings.USER_AVATAR_MAX_FILE_MB * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"头像文件不能超过 {settings.USER_AVATAR_MAX_FILE_MB} MB",
        )

    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != AVATAR_EXTENSIONS[suffix]:
                raise HTTPException(status_code=415, detail="头像文件格式与扩展名不一致")
            image.verify()
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        raise HTTPException(status_code=415, detail="头像文件不是有效图片") from exc

    filename = f"user_{current_user.id}_{uuid4().hex}{suffix}"
    target = _avatar_dir() / filename
    target.write_bytes(content)
    avatar_url = f"/media/avatars/{filename}"

    try:
        previous_avatar = current_user.avatar
        result = user_service.update_profile(db, current_user.id, avatar=avatar_url)
        _remove_local_avatar(previous_avatar)
        return result
    except Exception:
        target.unlink(missing_ok=True)
        raise


@router.put("/password", summary="修改密码")
def change_password(
    request: ChangePassword,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.change_password(
        db,
        current_user.id,
        old_password=request.old_password,
        new_password=request.new_password,
    )


@router.get("/customer-mode-password", summary="读取顾客展示模式退出密码状态")
def get_customer_mode_password_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.get_customer_mode_password_status(db, int(current_user.id))


@router.put("/customer-mode-password", summary="设置顾客展示模式退出密码")
def update_customer_mode_password(
    request: CustomerModePassword,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.update_customer_mode_password(
        db,
        int(current_user.id),
        password=request.password,
    )


@router.post("/customer-mode-password/verify", summary="验证顾客展示模式退出密码")
def verify_customer_mode_password(
    request: CustomerModePassword,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_service.verify_customer_mode_password(
        db,
        int(current_user.id),
        password=request.password,
    )


@router.get("/{user_id}", summary="用户详情（管理员）")
def get_user_detail(
    user_id: int,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return user_service.serialize_user(user_service.get_user_by_id(db, user_id))
