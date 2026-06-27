"""Cliente HTTP da SMSGo (zero dependências, usa apenas a stdlib)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .errors import SMSGoError

DEFAULT_BASE_URL = "https://api.smsgo.com.br"
# Token tem validade de 48h; renova com folga aos 47h.
TOKEN_TTL_S = 47 * 60 * 60


@dataclass
class SendResult:
    """Resultado de um envio."""

    id: str
    quantity: int
    status: str


class SMSGo:
    """SDK oficial da SMSGo para Python.

    Cuida da autenticação de 2 passos (SMSGo-key -> token Bearer de 48h) de
    forma transparente: você passa apenas a ``api_key``. O token é buscado sob
    demanda, cacheado e renovado automaticamente quando expira ou retorna 401.

    Exemplo::

        from smsgo import SMSGo

        smsgo = SMSGo(api_key="sua-chave")
        smsgo.send(phone="+5511999990000", message="Olá do SMSGo")
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

    # ------------------------------------------------------------------ #
    # API pública
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
        return _to_result(data)

    def send_bulk(
        self,
        messages: List[Dict[str, Any]],
        *,
        url_callback: Optional[str] = None,
        flash_sms: Optional[bool] = None,
        sms_type_id: Optional[int] = None,
    ) -> SendResult:
        """Envia várias mensagens numa única transação.

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
        return _to_result(data)

    def list(self, page: int = 1) -> Any:
        """Lista os envios da conta (paginado)."""
        return self._request("GET", f"/v1/sms/list?page={int(page)}")

    def get(self, id: str) -> Any:
        """Detalha um envio pelo seu UUID."""
        return self._request("GET", f"/v1/sms/{id}/show")

    # ------------------------------------------------------------------ #
    # Interno
    # ------------------------------------------------------------------ #
    def _ensure_token(self, force: bool = False) -> str:
        now = time.time()
        if not force and self._token and now < self._token_expires_at:
            return self._token

        status, body = self._raw(
            "GET", "/v1/auth/token", None, {"SMSGo-key": self.api_key, "Accept": "application/json"}
        )
        if not (200 <= status < 300) or not isinstance(body, dict) or not body.get("token"):
            raise _to_error(status, body, "Falha ao autenticar a SMSGo-key.")

        self._token = str(body["token"])
        self._token_expires_at = now + TOKEN_TTL_S
        return self._token

    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None, _retry: bool = False
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
            data = json.dumps(payload).encode("utf-8")
            h["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, _parse(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _parse(exc.read())
        except urllib.error.URLError as exc:
            raise SMSGoError(0, "network_error", str(exc.reason), None) from exc


def _strip_none(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _parse(raw: bytes) -> Any:
    text = raw.decode("utf-8") if raw else ""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _to_result(data: Any) -> SendResult:
    if not isinstance(data, dict):
        raise SMSGoError(0, "invalid_response", "Resposta inesperada da API.", data)
    return SendResult(id=data["id"], quantity=data["quantity"], status=data["status"])


def _to_error(status: int, body: Any, fallback: str = "Erro na requisição.") -> SMSGoError:
    code = body.get("code") if isinstance(body, dict) else None
    message = (
        (body.get("message") if isinstance(body, dict) else None)
        or (body if isinstance(body, str) else None)
        or fallback
    )
    return SMSGoError(status, str(code or _http_code_name(status)), str(message), body)


def _http_code_name(status: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        402: "insufficient_balance",
        409: "provider_out_of_stock",
        422: "validation_error",
        429: "rate_limited",
    }.get(status, f"http_{status}")
