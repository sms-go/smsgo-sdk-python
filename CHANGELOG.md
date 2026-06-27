# Changelog

Todas as mudanças relevantes deste pacote são documentadas aqui.
O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

## [0.1.0] - 2026-06-27

### Adicionado

- Cliente `SMSGo` com autenticação de 2 passos transparente (SMSGo-key → token
  Bearer de 48h, com cache e refresh automático no 401).
- Métodos `send`, `send_bulk`, `list` e `get`.
- `SMSGoError` tipado por `code` estável (`validation_error`,
  `insufficient_balance`, `rate_limited`, etc.).
- Zero dependências de runtime (usa apenas a stdlib `urllib`). Pacote tipado
  (`py.typed`), compatível com Python 3.8+.
