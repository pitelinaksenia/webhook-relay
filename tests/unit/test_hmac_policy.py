import time

from webhook_relay.security.hmac_signer import decrypt_secret, encrypt_secret, sign, verify


class TestSign:
    def test_deterministic_for_same_input(self):
        sig1 = sign("secret", "123", b"payload")
        sig2 = sign("secret", "123", b"payload")
        assert sig1 == sig2

    def test_differs_for_different_secret(self):
        sig1 = sign("secret-a", "123", b"payload")
        sig2 = sign("secret-b", "123", b"payload")
        assert sig1 != sig2

    def test_differs_for_different_body(self):
        sig1 = sign("secret", "123", b"payload-a")
        sig2 = sign("secret", "123", b"payload-b")
        assert sig1 != sig2

    def test_differs_for_different_timestamp(self):
        sig1 = sign("secret", "123", b"payload")
        sig2 = sign("secret", "456", b"payload")
        assert sig1 != sig2

    def test_is_hex_sha256(self):
        signature = sign("secret", "123", b"payload")
        assert len(signature) == 64
        int(signature, 16)  # raises if not valid hex


class TestVerify:
    def test_valid_signature_passes(self):
        timestamp = str(int(time.time()))
        raw_body = b'{"hello":"world"}'
        signature = sign("secret", timestamp, raw_body)

        assert verify("secret", timestamp, raw_body, signature) is True

    def test_wrong_signature_fails(self):
        timestamp = str(int(time.time()))
        raw_body = b'{"hello":"world"}'

        assert verify("secret", timestamp, raw_body, "0" * 64) is False

    def test_wrong_secret_fails(self):
        timestamp = str(int(time.time()))
        raw_body = b'{"hello":"world"}'
        signature = sign("secret-a", timestamp, raw_body)

        assert verify("secret-b", timestamp, raw_body, signature) is False

    def test_tampered_body_fails(self):
        timestamp = str(int(time.time()))
        signature = sign("secret", timestamp, b'{"hello":"world"}')

        assert verify("secret", timestamp, b'{"hello":"tampered"}', signature) is False

    def test_expired_timestamp_fails(self):
        old_timestamp = str(int(time.time()) - 600)
        raw_body = b"payload"
        signature = sign("secret", old_timestamp, raw_body)

        assert verify("secret", old_timestamp, raw_body, signature, max_age_seconds=300) is False

    def test_timestamp_within_max_age_passes(self):
        recent_timestamp = str(int(time.time()) - 100)
        raw_body = b"payload"
        signature = sign("secret", recent_timestamp, raw_body)

        assert verify("secret", recent_timestamp, raw_body, signature, max_age_seconds=300) is True

    def test_future_timestamp_beyond_max_age_fails(self):
        future_timestamp = str(int(time.time()) + 600)
        raw_body = b"payload"
        signature = sign("secret", future_timestamp, raw_body)

        assert verify("secret", future_timestamp, raw_body, signature, max_age_seconds=300) is False

    def test_non_numeric_timestamp_fails(self):
        raw_body = b"payload"
        signature = sign("secret", "not-a-timestamp", raw_body)

        assert verify("secret", "not-a-timestamp", raw_body, signature) is False


class TestEncryptDecryptSecret:
    def test_round_trip(self):
        plain = "my-webhook-secret"
        encrypted = encrypt_secret(plain)
        assert encrypted != plain
        assert decrypt_secret(encrypted) == plain

    def test_encrypting_same_value_twice_gives_different_ciphertext(self):
        encrypted_a = encrypt_secret("same-secret")
        encrypted_b = encrypt_secret("same-secret")
        assert encrypted_a != encrypted_b
