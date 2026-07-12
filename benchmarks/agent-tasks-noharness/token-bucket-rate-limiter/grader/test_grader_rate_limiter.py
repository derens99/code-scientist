import pytest

from rate_limiter import TokenBucket


def test_default_n_tokens_is_one():
    bucket = TokenBucket(capacity=1, refill_rate=1)
    assert bucket.allow(now=0.0) is True
    assert bucket.allow(now=0.0) is False


def test_negative_or_zero_n_tokens_raises():
    bucket = TokenBucket(capacity=5, refill_rate=1)
    with pytest.raises(ValueError):
        bucket.allow(0, now=0.0)
    with pytest.raises(ValueError):
        bucket.allow(-1, now=0.0)


def test_partial_refill_not_enough():
    bucket = TokenBucket(capacity=5, refill_rate=1)
    for _ in range(5):
        bucket.allow(1, now=0.0)
    assert bucket.allow(1, now=0.5) is False


def test_out_of_order_now_treated_as_no_elapsed_time():
    bucket = TokenBucket(capacity=5, refill_rate=1)
    for _ in range(5):
        bucket.allow(1, now=10.0)
    assert bucket.allow(1, now=5.0) is False
    assert bucket.allow(1, now=11.0) is True


def test_failed_attempt_does_not_consume_tokens():
    bucket = TokenBucket(capacity=3, refill_rate=1)
    assert bucket.allow(5, now=0.0) is False
    assert bucket.allow(3, now=0.0) is True


def test_multi_token_request_exact_capacity():
    bucket = TokenBucket(capacity=10, refill_rate=2)
    assert bucket.allow(10, now=0.0) is True
    assert bucket.allow(1, now=0.0) is False
    assert bucket.allow(4, now=2.0) is True
    assert bucket.allow(1, now=2.0) is False
