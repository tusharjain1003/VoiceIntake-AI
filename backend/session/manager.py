"""
Re-export the active session manager.

The concrete implementation (RedisSessionManager) lives in redis_manager.py.
Importers use ``from backend.session.manager import session_manager`` and
are insulated from the backend choice.
"""

from backend.session.redis_manager import RedisSessionManager, session_manager

__all__ = ["session_manager", "RedisSessionManager"]
