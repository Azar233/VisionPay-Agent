"""
用户服务层
处理用户注册、登录、鉴权等业务逻辑
"""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, hash_password, verify_password
from app.entity.db_models import Role, User, UserRole


class UserService:
    """用户服务"""

    @staticmethod
    def register(db: Session, username: str, email: str, password: str) -> User:
        """
        用户注册

        Args:
            db: 数据库会话
            username: 用户名
            email: 邮箱
            password: 明文密码

        Returns:
            新创建的用户对象

        Raises:
            HTTPException: 用户名或邮箱已存在
        """
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="用户名已存在")

        # 检查邮箱是否已存在
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已被注册")

        # 创建新用户
        new_user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return new_user

    @staticmethod
    def login(db: Session, username: str, password: str) -> User:
        """
        用户登录

        Args:
            db: 数据库会话
            username: 用户名
            password: 明文密码

        Returns:
            登录成功的用户对象

        Raises:
            HTTPException: 用户名或密码错误
        """
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        return user

    @staticmethod
    def create_access_token_for_user(user: User) -> str:
        """为用户生成 JWT Token"""
        return create_access_token(data={"sub": str(user.id)})

    @staticmethod
    def get_user_roles(db: Session, user: User) -> list[str]:
        """获取用户的角色标识列表"""
        return [ur.role.name for ur in user.user_roles]

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """根据 ID 获取用户"""
        user = (
            db.query(User)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
            .filter(User.id == user_id)
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user

    @staticmethod
    def serialize_user(user: User) -> dict[str, Any]:
        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "phone": user.phone,
            "avatar": user.avatar,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "roles": [item.role.name for item in user.user_roles],
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

    @staticmethod
    def is_admin(user: User) -> bool:
        """Return whether the loaded user may inspect the system directory."""
        return bool(user.is_superuser or any(item.role.name == "admin" for item in user.user_roles))

    @staticmethod
    def list_users(
        db: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict:
        query = db.query(User).options(joinedload(User.user_roles).joinedload(UserRole.role))
        keyword = (keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            query = query.filter(
                or_(
                    User.username.ilike(pattern),
                    User.nickname.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )
        total = query.count()
        users = (
            query.order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [UserService.serialize_user(user) for user in users],
        }

    @staticmethod
    def list_roles(db: Session) -> list[dict]:
        roles = db.query(Role).order_by(Role.id).all()
        return [
            {
                "id": role.id,
                "name": role.name,
                "display_name": role.display_name,
                "description": role.description,
                "is_system": role.is_system,
            }
            for role in roles
        ]

    @staticmethod
    def update_profile(
        db: Session,
        user_id: int,
        *,
        nickname: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        avatar: str | None = None,
    ) -> dict:
        user = UserService.get_user_by_id(db, user_id)
        if nickname is not None:
            user.nickname = nickname.strip() or None
        if email is not None:
            email = email.strip()
            if not email:
                raise HTTPException(status_code=422, detail="邮箱不能为空")
            duplicate = db.query(User.id).filter(User.email == email, User.id != user_id).first()
            if duplicate:
                raise HTTPException(status_code=400, detail="该邮箱已被其他用户使用")
            user.email = email
        if phone is not None:
            user.phone = phone.strip() or None
        if avatar is not None:
            user.avatar = avatar.strip() or None
        db.commit()
        db.refresh(user)
        return {"message": "个人信息已更新", "user": UserService.serialize_user(user)}

    @staticmethod
    def get_agent_custom_instructions(db: Session, user_id: int) -> dict:
        user = UserService.get_user_by_id(db, user_id)
        return {
            "instructions": user.agent_custom_instructions or "",
            "max_length": 4000,
        }

    @staticmethod
    def update_agent_custom_instructions(
        db: Session,
        user_id: int,
        *,
        instructions: str,
    ) -> dict:
        user = UserService.get_user_by_id(db, user_id)
        normalized = str(instructions or "").replace("\r\n", "\n").strip()
        user.agent_custom_instructions = normalized or None
        db.commit()
        return {
            "message": "Agent 自定义指令已更新" if normalized else "Agent 自定义指令已清除",
            "instructions": normalized,
            "max_length": 4000,
        }

    @staticmethod
    def change_password(
        db: Session,
        user_id: int,
        *,
        old_password: str,
        new_password: str,
    ) -> dict:
        user = UserService.get_user_by_id(db, user_id)
        if not verify_password(old_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="旧密码不正确")
        if verify_password(new_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
        user.hashed_password = hash_password(new_password)
        db.commit()
        return {"message": "密码修改成功"}


# 全局单例
user_service = UserService()
