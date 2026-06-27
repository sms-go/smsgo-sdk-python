"""Erros do SDK da SMSGo."""

from __future__ import annotations

from typing import Any, Optional


class SMSGoError(Exception):
    """Erro padronizado lançado em respostas não-2xx da API.

    Atributos:
        status: código HTTP (0 para erro de rede).
        code: código estável do erro (ex.: ``validation_error``,
            ``insufficient_balance``, ``rate_limited``).
        message: mensagem legível.
        details: corpo bruto da resposta de erro, quando houver.
    """

    def __init__(self, status: int, code: str, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def __repr__(self) -> str:  # pragma: no cover - apenas representação
        return f"SMSGoError(status={self.status!r}, code={self.code!r}, message={self.message!r})"
