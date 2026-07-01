"""SDK oficial Python da SMSGo — API de SMS para o Brasil.

Espelha o SDK Node.js (``@orynlabs/smsgo``): mesmos métodos, mapeamentos de
campo, autenticação e superfície de erro. Zero dependências de runtime.
"""

from __future__ import annotations

from .client import (
    AutoRechargeConfig,
    Balance,
    BillingResource,
    Card,
    ContactDetail,
    ContactsResource,
    InvoiceItem,
    ListResult,
    ListsResource,
    Paginated,
    PaginationMeta,
    Plan,
    PurchaseResult,
    SendDetail,
    SendListItem,
    SendNumberDetail,
    SendNumberItem,
    SendResult,
    SendSummary,
    SmsTypeItem,
    SMSGo,
    WebhookConfig,
    verify_webhook_signature,
)
from .errors import FieldError, SMSGoError

__all__ = [
    "SMSGo",
    "SMSGoError",
    "FieldError",
    "verify_webhook_signature",
    # dataclasses de tipos
    "SendResult",
    "SendListItem",
    "SendSummary",
    "SendNumberDetail",
    "SendDetail",
    "SendNumberItem",
    "PaginationMeta",
    "Paginated",
    "Balance",
    "SmsTypeItem",
    "AutoRechargeConfig",
    "WebhookConfig",
    "Plan",
    "Card",
    "InvoiceItem",
    "PurchaseResult",
    "ContactDetail",
    "ListResult",
    # namespaces
    "ContactsResource",
    "ListsResource",
    "BillingResource",
    "__version__",
]

__version__ = "0.3.0"
