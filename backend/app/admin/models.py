"""Persisted global platform configuration."""

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

from app.core.database import TimestampMixin


class PlatformCodeConfigRow(SQLModel, TimestampMixin, table=True):
    """Single-row store for global code assessment admin settings."""

    __tablename__ = "platform_code_config"

    id: int = Field(default=1, primary_key=True)
    config_json: str = Field(sa_column=Column(Text, nullable=False))
