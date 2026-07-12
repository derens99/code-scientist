"""A token-bucket rate limiter driven by an externally supplied clock."""


class TokenBucket:
    """A token-bucket rate limiter with an externally supplied clock.

    Parameters
    ----------
    capacity: float
        Maximum number of tokens the bucket can hold. Must be > 0.
    refill_rate: float
        Tokens added per second of elapsed time. Must be > 0.

    The bucket starts full (holding exactly `capacity` tokens) at
    construction time, with its internal "last update" timestamp set to
    0.0. The bucket never reads a real clock; all time information comes
    from the `now` argument passed to `allow`.
    """

    def __init__(self, capacity, refill_rate):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_update_time = 0.0

    def allow(self, n_tokens=1, now=0.0):
        """Attempt to consume `n_tokens` tokens at time `now`.

        Behavior:
        - Raise ValueError if `n_tokens <= 0`.
        - First, refill the bucket: the number of tokens increases by
          `(now - last_update_time) * refill_rate`, capped so the bucket
          never holds more than `capacity` tokens. `last_update_time` is
          then set to `now` (even if no tokens were added).
        - Callers are expected to supply non-decreasing `now` values
          across successive calls. If `now` is nonetheless less than the
          stored `last_update_time`, treat the elapsed time for this call
          as 0 (i.e. do not refill and do not raise an error), and do not
          move `last_update_time` backwards.
        - After refilling, if the bucket holds at least `n_tokens`
          tokens, subtract `n_tokens` from the bucket and return True.
        - Otherwise, leave the bucket's token count unchanged and return
          False.
        """
        if n_tokens <= 0:
            raise ValueError("n_tokens must be positive")

        if now >= self.last_update_time:
            elapsed = now - self.last_update_time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_update_time = now

        if self.tokens >= n_tokens:
            self.tokens -= n_tokens
            return True
        return False
