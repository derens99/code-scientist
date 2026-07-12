from rate_limiter import TokenBucket


def test_starts_full():
    bucket = TokenBucket(capacity=5, refill_rate=1)
    for _ in range(5):
        assert bucket.allow(1, now=0.0) is True
    assert bucket.allow(1, now=0.0) is False


def test_refills_over_time():
    bucket = TokenBucket(capacity=5, refill_rate=1)
    for _ in range(5):
        bucket.allow(1, now=0.0)
    assert bucket.allow(1, now=0.0) is False
    assert bucket.allow(1, now=3.0) is True


def test_does_not_exceed_capacity():
    bucket = TokenBucket(capacity=2, refill_rate=10)
    bucket.allow(1, now=0.0)
    assert bucket.allow(2, now=100.0) is True
    assert bucket.allow(1, now=100.0) is False
