import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import Enum


class DeliveryOutcome(Enum):
    DELIVERED = "delivered"
    RETRYABLE = "retryable"
    FAILED_FINAL = "failed_final"


def classify_response(
    status_code: int | None,
    is_timeout: bool = False,
    is_connection_error: bool = False,
) -> DeliveryOutcome:
    if is_timeout or is_connection_error:
        return DeliveryOutcome.RETRYABLE

    if status_code is not None and 200 <= status_code < 300:
        return DeliveryOutcome.DELIVERED

    if status_code == 429 or (status_code is not None and status_code >= 500):
        return DeliveryOutcome.RETRYABLE

    return DeliveryOutcome.FAILED_FINAL


def compute_backoff(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: float,
) -> float:
    delay = min(base_delay * (2**attempt), max_delay)
    return delay + random.uniform(0, jitter)


def parse_retry_after(header_value: str | None) -> float | None:
    if not header_value:
        return None

    header_value = header_value.strip()
    if header_value.isdigit():
        return float(header_value)

    try:
        retry_at = parsedate_to_datetime(header_value)
    except (TypeError, ValueError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)

    delay = (retry_at - datetime.now(UTC)).total_seconds()
    return max(delay, 0)
