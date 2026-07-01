"""Cliente HTTP da SMSGo (zero dependências, usa apenas a stdlib).

Espelha o SDK oficial Node.js (``@orynlabs/smsgo``): mesmos métodos, mesmos
mapeamentos de campos, mesma autenticação e mesma superfície de erro.

Cobre toda a API pública ``v1``: envio de SMS, consulta de envios, catálogo de
tipos, saldo, faturamento (compra off-session), recarga automática, webhooks
de saída, contatos e listas.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

from .errors import FieldError, SMSGoError

DEFAULT_BASE_URL = "https://api.smsgo.com.br"
# Token tem validade de 48h; renova com folga aos 47h.
TOKEN_TTL_S = 47 * 60 * 60

# Modo de autenticação da chave atual.
AuthMode = str  # 'live' | 'test'


# -------------------------------------------------------------------------- #
# Tipos de envio                                                             #
# -------------------------------------------------------------------------- #
@dataclass
class SendResult:
    """Resultado de um envio."""

    id: str
    quantity: int
    #: ``scheduled`` quando há agendamento; senão ``queued``.
    status: str
    #: Presente e ``True`` apenas em modo de teste (sandbox).
    test: Optional[bool] = None


@dataclass
class PaginationMeta:
    total: int
    per_page: int
    current_page: int
    last_page: int
    first_page: int
    first_page_url: str
    last_page_url: str
    next_page_url: Optional[str]
    previous_page_url: Optional[str]


@dataclass
class Paginated:
    """Wrapper de resposta paginada (``meta`` + ``data``)."""

    meta: PaginationMeta
    data: List[Any]


@dataclass
class SendListItem:
    id: str
    number: Optional[int]
    date: Optional[str]
    quantity: int
    full_name: str
    created_at: str
    status: str
    type: str


@dataclass
class SendSummary:
    """Contagens por bucket de status de um envio."""

    total: int
    delivered: int
    failed: int
    in_progress: int
    #: ``True`` quando nenhum número está mais em andamento.
    done: bool


@dataclass
class SendNumberDetail:
    id: str
    characters: int
    code: Optional[str]
    cost: float
    message: str
    phone: str
    status: str
    template: Optional[str]
    created_at: str


@dataclass
class SendDetail:
    id: str
    quantity: int
    characters: int
    date: Optional[str]
    total: float
    cost: float
    user: str
    status: str
    type: str
    summary: SendSummary
    phones: List[SendNumberDetail]


@dataclass
class SendNumberItem:
    id: str
    phone: str
    code: Optional[str]
    status: str
    created_at: str


# -------------------------------------------------------------------------- #
# Conta e catálogo                                                           #
# -------------------------------------------------------------------------- #
@dataclass
class Balance:
    #: Saldo disponível em R$.
    balance: float
    currency: str
    #: ``{"name": ..., "document": ...}``.
    company: Dict[str, Any]


@dataclass
class SmsTypeItem:
    #: Valor a enviar em ``sms_type_id``.
    id: int
    name: str
    #: Preço unitário (R$).
    price: float
    #: Preço promocional (R$), se houver.
    sale: Optional[float]


@dataclass
class AutoRechargeConfig:
    enabled: bool
    #: Limiar de recarga (R$).
    threshold: float
    #: Créditos comprados a cada recarga.
    plan_quantity: int
    card_id: Optional[str]
    alert_enabled: bool
    #: Limiar de alerta de saldo (R$).
    alert_threshold: float


@dataclass
class WebhookConfig:
    #: URL configurada (``None`` = desativado).
    url: Optional[str]
    #: Segredo HMAC. Assine o corpo bruto p/ validar ``X-SMSGo-Signature``.
    secret: Optional[str]


# -------------------------------------------------------------------------- #
# Faturamento                                                                #
# -------------------------------------------------------------------------- #
@dataclass
class Plan:
    id: str
    quantity: int
    price: float
    sale: float
    #: Preço unitário efetivo (R$).
    unit: float
    #: Total do pacote (R$).
    total: float
    popular: bool


@dataclass
class Card:
    id: str
    #: Últimos 4 dígitos.
    number: str
    name: str
    alias: Optional[str]
    #: Validade MM/AA.
    validate: str
    flag: str
    default: bool


@dataclass
class InvoiceItem:
    uuid: str
    total: float
    date: str
    expiry: str
    display_id: int
    #: ``{"code","name","icon","color"}`` ou ``None``.
    status: Optional[Dict[str, Any]]
    #: ``{"code","name"}`` ou ``None``.
    card: Optional[Dict[str, Any]]


@dataclass
class PurchaseResult:
    #: ``succeeded`` já creditou o saldo; ``processing`` confirma via webhook.
    status: str
    invoice_uuid: str
    #: Valor cobrado (R$).
    total: float
    quantity: int
    payment_intent_id: str


# -------------------------------------------------------------------------- #
# Contatos e listas                                                          #
# -------------------------------------------------------------------------- #
@dataclass
class ContactDetail:
    full_name: str
    email: Optional[str]
    phone: str


@dataclass
class ListResult:
    name: str
    id: str


# -------------------------------------------------------------------------- #
# Transporte compartilhado (usado pelos namespaces)                          #
# -------------------------------------------------------------------------- #
Requester = Callable[..., Any]


class SMSGo:
    """SDK oficial da SMSGo para Python.

    Cuida da autenticação de 2 passos (SMSGo-key -> token Bearer de 48h) de
    forma transparente: você passa apenas a ``api_key``. O token é buscado sob
    demanda, cacheado e renovado automaticamente quando expira ou retorna 401.

    Uma chave com prefixo ``test_`` seleciona o modo de teste (sandbox)
    transparentemente — nada muda no código.

    Exemplo::

        from smsgo import SMSGo

        smsgo = SMSGo(api_key="sua-chave")
        smsgo.send(phone="+5511999990000", message="Olá do SMSGo")

    Namespaces disponíveis: ``smsgo.contacts``, ``smsgo.lists``,
    ``smsgo.billing``.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("SMSGo: api_key é obrigatório.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._auth_mode: Optional[AuthMode] = None

        # Namespaces compartilham o transporte (auth/refresh/erros) do cliente.
        self.contacts = ContactsResource(self._request)
        self.lists = ListsResource(self._request)
        self.billing = BillingResource(self._request)

    # ------------------------------------------------------------------ #
    # Modo de autenticação
    # ------------------------------------------------------------------ #
    @property
    def mode(self) -> Optional[AuthMode]:
        """Modo da chave atual (``'live'`` ou ``'test'``).

        Retorna ``None`` antes da 1ª chamada autenticada — use
        :meth:`resolve_mode` para forçar.
        """
        return self._auth_mode

    def resolve_mode(self) -> AuthMode:
        """Garante um token e devolve o modo (``'live'``/``'test'``) da chave."""
        self._ensure_token()
        return self._auth_mode or "live"

    # ------------------------------------------------------------------ #
    # SMS
    # ------------------------------------------------------------------ #
    def send(
        self,
        phone: str,
        message: str,
        *,
        schedule: Optional[str] = None,
        reference: Optional[str] = None,
        sender: Optional[str] = None,
        sms_type_id: Optional[int] = None,
    ) -> SendResult:
        """Envia um SMS para um número (E.164, ex.: ``+5511999990000``).

        ``sender`` é mapeado para o campo ``from`` da API (palavra reservada
        em Python).
        """
        body = _strip_none(
            {
                "phone": phone,
                "message": message,
                "schedule": schedule,
                "reference": reference,
                "from": sender,
                "sms_type_id": sms_type_id,
            }
        )
        data = self._request("POST", "/v1/sms/send/single", body)
        return _to_send_result(data)

    def send_bulk(
        self,
        messages: List[Dict[str, Any]],
        *,
        url_callback: Optional[str] = None,
        flash_sms: Optional[bool] = None,
        sms_type_id: Optional[int] = None,
    ) -> SendResult:
        """Envia várias mensagens numa única transação (até 5000).

        Cada item de ``messages`` é um dict com ``phone`` e ``message`` (e,
        opcionalmente, ``schedule``, ``reference``, ``from``).
        """
        body = _strip_none(
            {
                "messages": messages,
                "urlCallback": url_callback,
                "flashSms": flash_sms,
                "sms_type_id": sms_type_id,
            }
        )
        data = self._request("POST", "/v1/sms/send/multiple", body)
        return _to_send_result(data)

    def list(self, page: int = 1) -> Paginated:
        """Lista os envios da conta (paginado)."""
        path = "/v1/sms/list" + _build_query({"page": page})
        return _to_paginated(self._request("GET", path), _to_send_list_item)

    def get(self, id: str) -> SendDetail:
        """Detalha um envio pelo seu UUID (inclui ``summary`` de acompanhamento)."""
        data = self._request("GET", f"/v1/sms/{urllib.parse.quote(str(id))}/show")
        return _to_send_detail(data)

    def get_numbers(
        self,
        id: str,
        *,
        status: Optional[str] = None,
        page: Optional[int] = None,
    ) -> Paginated:
        """Números de um envio, paginado e filtrável por bucket de status.

        ``status`` aceita ``'delivered'``, ``'failed'`` ou ``'in_progress'``.
        """
        path = f"/v1/sms/{urllib.parse.quote(str(id))}/numbers" + _build_query(
            {"status": status, "page": page}
        )
        return _to_paginated(self._request("GET", path), _to_send_number_item)

    def get_sms_types(self) -> List[SmsTypeItem]:
        """Catálogo de tipos de SMS ativos (o ``id`` é o valor de ``sms_type_id``)."""
        res = self._request("GET", "/v1/sms-types")
        items = res.get("data", []) if isinstance(res, dict) else []
        return [_to_sms_type(x) for x in items]

    # ------------------------------------------------------------------ #
    # Conta
    # ------------------------------------------------------------------ #
    def get_balance(self) -> Balance:
        """Saldo monetário (R$) + dados básicos da conta."""
        data = self._request("GET", "/v1/account/balance")
        return _to_balance(data)

    def get_auto_recharge(self) -> AutoRechargeConfig:
        """Lê a configuração de recarga automática + alerta de saldo."""
        data = self._request("GET", "/v1/account/auto-recharge")
        return _to_auto_recharge(data)

    def set_auto_recharge(
        self,
        *,
        enabled: Optional[bool] = None,
        threshold: Optional[float] = None,
        plan_quantity: Optional[int] = None,
        card_id: Optional[str] = None,
        alert_enabled: Optional[bool] = None,
        alert_threshold: Optional[float] = None,
    ) -> AutoRechargeConfig:
        """Atualiza recarga automática + alerta de saldo.

        Para LIGAR a recarga é obrigatório ``card_id`` + ``plan_quantity``.
        """
        body = _strip_none(
            {
                "enabled": enabled,
                "threshold": threshold,
                "plan_quantity": plan_quantity,
                "card_id": card_id,
                "alert_enabled": alert_enabled,
                "alert_threshold": alert_threshold,
            }
        )
        data = self._request("PUT", "/v1/account/auto-recharge", body)
        return _to_auto_recharge(data)

    def get_webhook(self) -> WebhookConfig:
        """Lê a URL e o segredo do webhook de saída."""
        data = self._request("GET", "/v1/account/webhook")
        return _to_webhook(data)

    def set_webhook(
        self,
        *,
        url: Optional[str] = None,
        rotate_secret: Optional[bool] = None,
    ) -> WebhookConfig:
        """Define o webhook de saída (DLR + respostas).

        String vazia em ``url`` desativa o webhook; use ``rotate_secret`` para
        girar o segredo de assinatura.
        """
        body = _strip_none({"url": url, "rotate_secret": rotate_secret})
        data = self._request("PUT", "/v1/account/webhook", body)
        return _to_webhook(data)

    # ------------------------------------------------------------------ #
    # Auth interna
    # ------------------------------------------------------------------ #
    def _ensure_token(self, force: bool = False) -> str:
        now = time.time()
        if not force and self._token and now < self._token_expires_at:
            return self._token

        status, body = self._raw(
            "GET",
            "/v1/auth/token",
            None,
            {"SMSGo-key": self.api_key, "Accept": "application/json"},
        )
        if not (200 <= status < 300) or not isinstance(body, dict) or not body.get("token"):
            raise _to_error(status, body, "Falha ao autenticar a SMSGo-key.")

        self._token = str(body["token"])
        self._auth_mode = "test" if body.get("mode") == "test" else "live"
        self._token_expires_at = now + TOKEN_TTL_S
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        _retry: bool = False,
    ) -> Any:
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        status, body = self._raw(method, path, payload, headers)

        # Token expirado/revogado: renova uma vez e tenta de novo.
        if status == 401 and not _retry:
            self._ensure_token(force=True)
            return self._request(method, path, payload, _retry=True)

        if not (200 <= status < 300):
            raise _to_error(status, body)
        return body

    def _raw(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]],
        headers: Dict[str, str],
    ):
        url = f"{self.base_url}{path}"
        data = None
        h = dict(headers)
        if payload is not None:
            data = json.dumps(_strip_none(payload)).encode("utf-8")
            h["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, _parse(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _parse(exc.read())
        except urllib.error.URLError as exc:
            raise SMSGoError(0, "network_error", str(exc.reason), None) from exc


# -------------------------------------------------------------------------- #
# Namespaces (contatos, listas, faturamento)                                 #
# -------------------------------------------------------------------------- #
class ContactsResource:
    """CRUD de contatos. Compartilha auth/refresh/erros do cliente."""

    def __init__(self, req: Requester) -> None:
        self._req = req

    def list(
        self,
        *,
        page: int,
        per_page: Optional[int] = None,
        search: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Paginated:
        """Lista contatos (paginado; ``page`` obrigatório)."""
        path = "/v1/contacts/list" + _build_query(
            {"page": page, "perPage": per_page, "search": search, "title": title}
        )
        return _to_paginated(self._req("GET", path), lambda x: x)

    def create(
        self,
        *,
        full_name: str,
        phone: str,
        email: Optional[str] = None,
        lists: Optional[List[str]] = None,
    ) -> str:
        """Cria (ou faz upsert pelo telefone) um contato. Retorna o UUID."""
        body = _contact_body(full_name, phone, email, lists)
        return self._req("POST", "/v1/contacts/store", body)

    def get(self, id: str) -> ContactDetail:
        """Detalha um contato pelo UUID."""
        data = self._req("GET", f"/v1/contacts/{urllib.parse.quote(str(id))}/show")
        return _to_contact_detail(data)

    def update(
        self,
        id: str,
        *,
        full_name: str,
        phone: str,
        email: Optional[str] = None,
        lists: Optional[List[str]] = None,
    ) -> str:
        """Atualiza um contato. Retorna o UUID."""
        body = _contact_body(full_name, phone, email, lists)
        return self._req("PUT", f"/v1/contacts/{urllib.parse.quote(str(id))}/update", body)

    def delete(self, id: str) -> Dict[str, Any]:
        """Exclui um contato."""
        return self._req("DELETE", f"/v1/contacts/{urllib.parse.quote(str(id))}/delete")


class ListsResource:
    """CRUD de listas. Compartilha auth/refresh/erros do cliente."""

    def __init__(self, req: Requester) -> None:
        self._req = req

    def list(
        self,
        *,
        page: int,
        per_page: Optional[int] = None,
        title: Optional[str] = None,
    ) -> Paginated:
        """Lista as listas da conta (paginado; ``page`` obrigatório)."""
        path = "/v1/lists/list" + _build_query(
            {"page": page, "perPage": per_page, "title": title}
        )
        return _to_paginated(self._req("GET", path), lambda x: x)

    def create(self, *, name: str) -> ListResult:
        """Cria uma lista."""
        return _to_list_result(self._req("POST", "/v1/lists/store", {"name": name}))

    def get(self, id: str) -> ListResult:
        """Detalha uma lista pelo UUID."""
        return _to_list_result(
            self._req("GET", f"/v1/lists/{urllib.parse.quote(str(id))}/show")
        )

    def update(self, id: str, *, name: str) -> ListResult:
        """Atualiza uma lista."""
        return _to_list_result(
            self._req("PUT", f"/v1/lists/{urllib.parse.quote(str(id))}/update", {"name": name})
        )

    def delete(self, id: str) -> Dict[str, Any]:
        """Exclui uma lista."""
        return self._req("DELETE", f"/v1/lists/{urllib.parse.quote(str(id))}/delete")


class BillingResource:
    """Pacotes, cartões, faturas e compra off-session."""

    def __init__(self, req: Requester) -> None:
        self._req = req

    def plans(self) -> List[Plan]:
        """Pacotes de recarga (tiers) disponíveis."""
        res = self._req("GET", "/v1/billing/plans")
        items = res.get("data", []) if isinstance(res, dict) else []
        return [_to_plan(x) for x in items]

    def cards(self) -> List[Card]:
        """Cartões salvos (apenas os 4 últimos dígitos)."""
        res = self._req("GET", "/v1/billing/cards")
        items = res.get("data", []) if isinstance(res, dict) else []
        return [_to_card(x) for x in items]

    def invoices(
        self,
        *,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
    ) -> Paginated:
        """Histórico de faturas/recibos (paginado)."""
        path = "/v1/billing/invoices" + _build_query({"page": page, "perPage": per_page})
        return _to_paginated(self._req("GET", path), _to_invoice_item)

    def purchase(
        self,
        *,
        quantity: Optional[int] = None,
        plan_id: Optional[str] = None,
        card_id: Optional[str] = None,
        coupon: Optional[str] = None,
    ) -> PurchaseResult:
        """Compra créditos cobrando um cartão salvo (off-session).

        Informe ``quantity`` ou ``plan_id``. Sem ``card_id``, usa o cartão
        padrão.

        .. warning::
            **NÃO é idempotente**: cada chamada gera uma cobrança nova. Em
            timeout, consulte :meth:`invoices` antes de repetir — não faça
            retry cego.
        """
        body = _strip_none(
            {
                "quantity": quantity,
                "plan_id": plan_id,
                "card_id": card_id,
                "coupon": coupon,
            }
        )
        return _to_purchase_result(self._req("POST", "/v1/billing/purchase", body))


# -------------------------------------------------------------------------- #
# Webhook: verificação de assinatura (helper de nível de módulo)             #
# -------------------------------------------------------------------------- #
def verify_webhook_signature(
    raw_body: Union[str, bytes, None],
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """Valida a assinatura ``X-SMSGo-Signature`` de um webhook de saída.

    Calcula ``sha256=<hmac>`` (HMAC-SHA256 do corpo bruto com o ``secret``) e
    compara em tempo constante com o cabeçalho recebido.

    Args:
        raw_body: corpo bruto exatamente como recebido (``str`` ou ``bytes``).
        signature_header: valor do cabeçalho ``X-SMSGo-Signature``.
        secret: segredo do webhook (``get_webhook().secret``).

    Returns:
        ``True`` se a assinatura confere; ``False`` caso contrário (inclui
        ``None``/vazio). Nunca levanta exceção.
    """
    if not signature_header or not secret or raw_body is None:
        return False

    body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    # Compara em bytes: um cabeçalho com caracteres não-ASCII não deve levantar
    # exceção (compare_digest com dois str exige ASCII) — apenas retornar False.
    expected = ("sha256=" + digest).encode("ascii")
    provided = signature_header.encode("utf-8", "replace")
    return hmac.compare_digest(expected, provided)


# -------------------------------------------------------------------------- #
# Helpers de transporte                                                      #
# -------------------------------------------------------------------------- #
def _strip_none(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _build_query(params: Dict[str, Any]) -> str:
    """Monta ``?a=1&b=2``, ignorando valores ``None``."""
    pairs = [(k, str(v)) for k, v in params.items() if v is not None]
    if not pairs:
        return ""
    return "?" + urllib.parse.urlencode(pairs)


def _parse(raw: bytes) -> Any:
    text = raw.decode("utf-8") if raw else ""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _to_error(status: int, body: Any, fallback: str = "Erro na requisição.") -> SMSGoError:
    code = body.get("code") if isinstance(body, dict) else None
    message = (
        (body.get("message") if isinstance(body, dict) else None)
        or (body if isinstance(body, str) else None)
        or fallback
    )
    errors: Optional[List[FieldError]] = None
    if isinstance(body, dict) and isinstance(body.get("errors"), list):
        errors = [
            FieldError(field=e.get("field"), message=e.get("message"))
            for e in body["errors"]
            if isinstance(e, dict)
        ]
    return SMSGoError(status, str(code or _http_code_name(status)), str(message), body, errors)


def _http_code_name(status: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        402: "insufficient_balance",
        409: "provider_out_of_stock",
        422: "validation_error",
        429: "rate_limited",
        503: "payment_unavailable",
    }.get(status, f"http_{status}")


# -------------------------------------------------------------------------- #
# Helpers de desserialização (dict -> dataclass)                             #
# -------------------------------------------------------------------------- #
def _require_dict(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise SMSGoError(0, "invalid_response", "Resposta inesperada da API.", data)
    return data


def _to_send_result(data: Any) -> SendResult:
    d = _require_dict(data)
    return SendResult(
        id=d["id"],
        quantity=d["quantity"],
        status=d["status"],
        test=d.get("test"),
    )


def _to_pagination_meta(data: Any) -> PaginationMeta:
    d = data if isinstance(data, dict) else {}
    return PaginationMeta(
        total=d.get("total"),
        per_page=d.get("perPage"),
        current_page=d.get("currentPage"),
        last_page=d.get("lastPage"),
        first_page=d.get("firstPage"),
        first_page_url=d.get("firstPageUrl"),
        last_page_url=d.get("lastPageUrl"),
        next_page_url=d.get("nextPageUrl"),
        previous_page_url=d.get("previousPageUrl"),
    )


def _to_paginated(data: Any, item_fn: Callable[[Any], Any]) -> Paginated:
    d = _require_dict(data)
    rows = d.get("data") or []
    return Paginated(
        meta=_to_pagination_meta(d.get("meta")),
        data=[item_fn(x) for x in rows],
    )


def _to_send_list_item(d: Any) -> SendListItem:
    d = d if isinstance(d, dict) else {}
    return SendListItem(
        id=d.get("id"),
        number=d.get("number"),
        date=d.get("date"),
        quantity=d.get("quantity"),
        full_name=d.get("full_name"),
        created_at=d.get("created_at"),
        status=d.get("status"),
        type=d.get("type"),
    )


def _to_send_summary(d: Any) -> SendSummary:
    d = d if isinstance(d, dict) else {}
    return SendSummary(
        total=d.get("total"),
        delivered=d.get("delivered"),
        failed=d.get("failed"),
        in_progress=d.get("inProgress"),
        done=d.get("done"),
    )


def _to_send_number_detail(d: Any) -> SendNumberDetail:
    d = d if isinstance(d, dict) else {}
    return SendNumberDetail(
        id=d.get("id"),
        characters=d.get("characters"),
        code=d.get("code"),
        cost=d.get("cost"),
        message=d.get("message"),
        phone=d.get("phone"),
        status=d.get("status"),
        template=d.get("template"),
        created_at=d.get("created_at"),
    )


def _to_send_detail(data: Any) -> SendDetail:
    d = _require_dict(data)
    return SendDetail(
        id=d.get("id"),
        quantity=d.get("quantity"),
        characters=d.get("characters"),
        date=d.get("date"),
        total=d.get("total"),
        cost=d.get("cost"),
        user=d.get("user"),
        status=d.get("status"),
        type=d.get("type"),
        summary=_to_send_summary(d.get("summary")),
        phones=[_to_send_number_detail(x) for x in (d.get("phones") or [])],
    )


def _to_send_number_item(d: Any) -> SendNumberItem:
    d = d if isinstance(d, dict) else {}
    return SendNumberItem(
        id=d.get("id"),
        phone=d.get("phone"),
        code=d.get("code"),
        status=d.get("status"),
        created_at=d.get("created_at"),
    )


def _to_sms_type(d: Any) -> SmsTypeItem:
    d = d if isinstance(d, dict) else {}
    return SmsTypeItem(id=d.get("id"), name=d.get("name"), price=d.get("price"), sale=d.get("sale"))


def _to_balance(data: Any) -> Balance:
    d = _require_dict(data)
    return Balance(
        balance=d.get("balance"),
        currency=d.get("currency"),
        company=d.get("company") or {},
    )


def _to_auto_recharge(data: Any) -> AutoRechargeConfig:
    d = _require_dict(data)
    return AutoRechargeConfig(
        enabled=d.get("enabled"),
        threshold=d.get("threshold"),
        plan_quantity=d.get("planQuantity"),
        card_id=d.get("cardId"),
        alert_enabled=d.get("alertEnabled"),
        alert_threshold=d.get("alertThreshold"),
    )


def _to_webhook(data: Any) -> WebhookConfig:
    d = _require_dict(data)
    return WebhookConfig(url=d.get("url"), secret=d.get("secret"))


def _to_plan(d: Any) -> Plan:
    d = d if isinstance(d, dict) else {}
    return Plan(
        id=d.get("id"),
        quantity=d.get("quantity"),
        price=d.get("price"),
        sale=d.get("sale"),
        unit=d.get("unit"),
        total=d.get("total"),
        popular=d.get("popular"),
    )


def _to_card(d: Any) -> Card:
    d = d if isinstance(d, dict) else {}
    return Card(
        id=d.get("id"),
        number=d.get("number"),
        name=d.get("name"),
        alias=d.get("alias"),
        validate=d.get("validate"),
        flag=d.get("flag"),
        default=d.get("default"),
    )


def _to_invoice_item(d: Any) -> InvoiceItem:
    d = d if isinstance(d, dict) else {}
    return InvoiceItem(
        uuid=d.get("uuid"),
        total=d.get("total"),
        date=d.get("date"),
        expiry=d.get("expiry"),
        display_id=d.get("displayId"),
        status=d.get("status"),
        card=d.get("card"),
    )


def _to_purchase_result(data: Any) -> PurchaseResult:
    d = _require_dict(data)
    return PurchaseResult(
        status=d.get("status"),
        invoice_uuid=d.get("invoiceUuid"),
        total=d.get("total"),
        quantity=d.get("quantity"),
        payment_intent_id=d.get("paymentIntentId"),
    )


def _to_contact_detail(data: Any) -> ContactDetail:
    d = _require_dict(data)
    return ContactDetail(
        full_name=d.get("fullName"),
        email=d.get("email"),
        phone=d.get("phone"),
    )


def _to_list_result(data: Any) -> ListResult:
    d = _require_dict(data)
    return ListResult(name=d.get("name"), id=d.get("id"))


def _contact_body(
    full_name: str,
    phone: str,
    email: Optional[str],
    lists: Optional[List[str]],
) -> Dict[str, Any]:
    return _strip_none(
        {
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "lists": lists,
        }
    )
