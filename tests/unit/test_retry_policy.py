from webhook_relay.core.retry_policy import (
    DeliveryOutcome,
    classify_response,
    compute_backoff,
    parse_retry_after,
)


class TestClassifyResponse:
    def test_2xx_is_delivered(self):
        assert classify_response(200) == DeliveryOutcome.DELIVERED
        assert classify_response(204) == DeliveryOutcome.DELIVERED
        assert classify_response(299) == DeliveryOutcome.DELIVERED

    def test_4xx_except_429_is_final_failure(self):
        assert classify_response(400) == DeliveryOutcome.FAILED_FINAL
        assert classify_response(404) == DeliveryOutcome.FAILED_FINAL
        assert classify_response(422) == DeliveryOutcome.FAILED_FINAL

    def test_429_is_retryable(self):
        assert classify_response(429) == DeliveryOutcome.RETRYABLE

    def test_5xx_is_retryable(self):
        assert classify_response(500) == DeliveryOutcome.RETRYABLE
        assert classify_response(503) == DeliveryOutcome.RETRYABLE

    def test_timeout_is_retryable_regardless_of_status(self):
        assert classify_response(None, is_timeout=True) == DeliveryOutcome.RETRYABLE

    def test_connection_error_is_retryable_regardless_of_status(self):
        assert classify_response(None, is_connection_error=True) == DeliveryOutcome.RETRYABLE

    def test_3xx_is_final_failure(self):
        assert classify_response(301) == DeliveryOutcome.FAILED_FINAL


class TestComputeBackoff:
    def test_grows_exponentially_with_attempt(self):
        delay1 = compute_backoff(attempt=1, base_delay=2, max_delay=1000, jitter=0)
        delay2 = compute_backoff(attempt=2, base_delay=2, max_delay=1000, jitter=0)
        delay3 = compute_backoff(attempt=3, base_delay=2, max_delay=1000, jitter=0)

        assert delay1 == 2
        assert delay2 == 4
        assert delay3 == 8

    def test_capped_at_max_delay(self):
        delay = compute_backoff(attempt=10, base_delay=1, max_delay=30, jitter=0)
        assert delay == 30

    def test_jitter_is_added_within_bounds(self):
        delay = compute_backoff(attempt=1, base_delay=1, max_delay=100, jitter=5)
        assert 1 <= delay <= 6

    def test_jitter_cannot_push_delay_past_max_delay(self):
        delay = compute_backoff(attempt=10, base_delay=1, max_delay=30, jitter=5)
        assert delay == 30

    def test_zero_jitter_is_deterministic(self):
        delay = compute_backoff(attempt=4, base_delay=1, max_delay=100, jitter=0)
        assert delay == 8


class TestParseRetryAfter:
    def test_numeric_seconds(self):
        assert parse_retry_after("120") == 120.0

    def test_none_when_header_missing(self):
        assert parse_retry_after(None) is None

    def test_none_when_header_empty(self):
        assert parse_retry_after("") is None

    def test_none_for_garbage_value(self):
        assert parse_retry_after("not-a-date-or-number") is None

    def test_http_date_in_future_returns_positive_delay(self):
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime

        future = datetime.now(UTC) + timedelta(seconds=60)
        header_value = format_datetime(future, usegmt=True)

        delay = parse_retry_after(header_value)

        assert delay is not None
        assert 55 <= delay <= 60

    def test_http_date_in_past_clamped_to_zero(self):
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime

        past = datetime.now(UTC) - timedelta(seconds=60)
        header_value = format_datetime(past, usegmt=True)

        assert parse_retry_after(header_value) == 0
