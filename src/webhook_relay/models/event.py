import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_relay.models.session import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="event", lazy="selectin")
