"""Erros do SDK da SMSGo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class FieldError:
    """Item de erro de validação por campo (presente em ``validation_error``)."""

    field: str
    message: str


class SMSGoError(Exception):
    """Erro padronizado lançado em respostas não-2xx da API.

    Atributos:
        status: código HTTP (0 para erro de rede).
        code: código estável do erro (ex.: ``validation_error``,
            ``insufficient_balance``, ``rate_limited``).
        message: mensagem legível.
        details: corpo bruto da resposta de erro, quando houver.
        errors: detalhe por campo, presente em ``validation_error`` (422).
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
        errors: Optional[List["FieldError"]] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.errors = errors

    def __repr__(self) -> str:  # pragma: no cover - apenas representação
        return f"SMSGoError(status={self.status!r}, code={self.code!r}, message={self.message!r})"
