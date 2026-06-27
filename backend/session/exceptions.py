class SessionStoreUnavailableError(Exception):
    """Raised when the session store (Redis) is unavailable and no fallback is configured."""
