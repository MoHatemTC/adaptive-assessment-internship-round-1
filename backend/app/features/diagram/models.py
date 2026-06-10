import uuid
from typing import Optional
from app.core.database import Field, SQLModel, TimestampMixin


class Diagram(SQLModel, TimestampMixin, table=True):
    """
    Stores metadata for diagrams generated during learner assessments.
    """

    __tablename__ = "diagrams"

    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    user_id: Optional[uuid.UUID] = Field(default=None, nullable=True)
    prompt: str = Field(nullable=False)
    image_url: Optional[str] = Field(default=None, nullable=True)
    status: str = Field(default="pending", nullable=False)
