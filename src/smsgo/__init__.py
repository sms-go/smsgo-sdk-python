"""SDK oficial Python da SMSGo — API de SMS para o Brasil."""

from __future__ import annotations

from .client import SMSGo, SendResult
from .errors import SMSGoError

__all__ = ["SMSGo", "SendResult", "SMSGoError", "__version__"]
__version__ = "0.1.0"
