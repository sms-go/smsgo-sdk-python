# Changelog

Todas as mudanças relevantes deste pacote são documentadas aqui.
O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

## [0.3.0] - 2026-07-01

### Adicionado

- **Paridade total com o SDK Node.js** (`@orynlabs/smsgo`): mesmos métodos,
  mapeamentos de campo, autenticação e superfície de erro.
- SMS: `get_numbers(id, *, status=, page=)` e `get_sms_types()`.
- Conta: `get_balance()`, `get_auto_recharge()`, `set_auto_recharge(...)`,
  `get_webhook()`, `set_webhook(...)`.
- Modo de autenticação: propriedade `mode` (`'live'`/`'test'`/`None`) e
  `resolve_mode()`. Chaves `test_…` selecionam sandbox de forma transparente.
- Namespaces como atributos, compartilhando auth/refresh/erros do cliente:
  `smsgo.contacts.*`, `smsgo.lists.*`, `smsgo.billing.*` (incl. `purchase`
  off-session — **não idempotente**).
- Helper de módulo `verify_webhook_signature(raw_body, signature_header,
  secret)` — HMAC-SHA256 do corpo bruto, comparação em tempo constante
  (`hmac.compare_digest`). Retorna `False` para assinatura ausente/vazia/`None`.
- Dataclasses tipadas para todas as respostas: `Balance`, `SmsTypeItem`,
  `AutoRechargeConfig`, `WebhookConfig`, `Plan`, `Card`, `InvoiceItem`,
  `SendDetail`/`SendSummary`/`SendNumberDetail`/`SendNumberItem`,
  `SendListItem`, `PurchaseResult`, `ContactDetail`, `ListResult`, e o wrapper
  `Paginated`/`PaginationMeta`.
- `SMSGoError.errors` (lista de `FieldError`) preenchido em `validation_error`
  (422); `httpCodeName` agora inclui `503 → payment_unavailable`.
- Exemplos: `check_balance.py`, `buy_credits.py`, `configure_webhook.py`,
  `receive_dlr_webhook.py`.

## [0.1.0] - 2026-06-27

### Adicionado

- Cliente `SMSGo` com autenticação de 2 passos transparente (SMSGo-key → token
  Bearer de 48h, com cache e refresh automático no 401).
- Métodos `send`, `send_bulk`, `list` e `get`.
- `SMSGoError` tipado por `code` estável (`validation_error`,
  `insufficient_balance`, `rate_limited`, etc.).
- Zero dependências de runtime (usa apenas a stdlib `urllib`). Pacote tipado
  (`py.typed`), compatível com Python 3.8+.
