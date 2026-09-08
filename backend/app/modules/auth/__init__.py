"""Auth module: identity, authentication, and password reset.

Public interface for other modules — import models from here, never internals.
"""

from app.modules.auth.models import Permission, Role, User

__all__ = ["Permission", "Role", "User"]
