from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, func

from app.core.database import Base
from app.models.enums import UserRole
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    role = Column(Enum(UserRole, name="user_role"), nullable=False, index=True)
    is_superadmin = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
