class NetGuard:
    """Counts back-to-back Telegram connection failures. A runner whose network is broken
    would otherwise burn its whole polling budget retrying; ending the run early lets the
    next scheduled run start on a fresh machine."""

    def __init__(self, limit: int = 4, base: float = 3.0, cap: float = 20.0):
        self.limit, self.base, self.cap = limit, base, cap
        self.streak = 0

    def ok(self) -> None:
        self.streak = 0

    def failed(self) -> bool:
        """Record a failure; True means stop polling now."""
        self.streak += 1
        return self.streak >= self.limit

    def pause(self) -> float:
        return min(self.cap, self.base * 2 ** (self.streak - 1))
