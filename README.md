# smsgo (Python)

[![PyPI](https://img.shields.io/pypi/v/smsgo.svg)](https://pypi.org/project/smsgo/)
[![Python](https://img.shields.io/pypi/pyversions/smsgo.svg)](https://pypi.org/project/smsgo/)
[![CI](https://github.com/SMSFy/smsgo-python/actions/workflows/ci.yml/badge.svg)](https://github.com/SMSFy/smsgo-python/actions/workflows/ci.yml)
[![license](https://img.shields.io/pypi/l/smsgo.svg)](./LICENSE)

SDK oficial **Python** para a [SMSGo](https://smsgo.com.br) — a API de SMS simples para o Brasil. Envie **OTP/2FA, alertas transacionais e campanhas** com poucas linhas.

- ⚡ **Integra em minutos** — autenticação cuidada pra você (sem ritual de token manual).
- 💸 **Sem mensalidade** — créditos pré-pagos que não expiram, preço em real.
- 🇧🇷 **Brasil-first** — entrega para todas as operadoras, LGPD nativo.
- 🟢 **Zero dependências** — usa só a biblioteca padrão. Tipado (`py.typed`).
- 🎁 **R$ 10 grátis** ao criar a conta — dá pra testar sem cartão.

> Nova conta e chave em **[smsgo.com.br](https://smsgo.com.br)** → painel → **Minha conta → API**.

## Instalação

```bash
pip install smsgo
```

Requer Python 3.8+.

## Começo rápido

```python
import os
from smsgo import SMSGo

smsgo = SMSGo(api_key=os.environ["SMSGO_KEY"])

result = smsgo.send(
    phone="+5511999990000",
    message="Olá do SMSGo 👋",
)

print(result.id, result.status)  # -> "a1b2c3...", "queued"
```

Você passa só a `api_key`. O SDK troca a chave por um token Bearer (válido 48h), guarda em cache e renova sozinho quando expira.

## Enviar um OTP (2FA)

```python
import random
from smsgo import SMSGo, SMSGoError

smsgo = SMSGo(api_key="...")
code = f"{random.randint(0, 999999):06d}"  # 6 dígitos

try:
    smsgo.send(phone="+5511999990000", message=f"Seu código SMSGo é {code}. Válido por 5 minutos.")
    # guarde `code` com TTL (ex.: Redis) e compare na verificação
except SMSGoError as err:
    print(err.status, err.code, err.message)
```

## Envio em massa

```python
smsgo.send_bulk(
    messages=[
        {"phone": "+5511999990000", "message": "Oi, Ana!"},
        {"phone": "+5521988887777", "message": "Oi, Bruno!"},
    ],
    url_callback="https://seuapp.com/webhooks/smsgo",  # status de entrega (opcional)
)
```

## Consultar envios

```python
page = smsgo.list(page=1)
one = smsgo.get("a1b2c3-...")  # status de um envio específico
```

## Tratamento de erros

Toda resposta não-2xx vira um `SMSGoError` com `status` e um `code` estável:

```python
from smsgo import SMSGo, SMSGoError

try:
    smsgo.send(phone="+5511999990000", message="Olá")
except SMSGoError as err:
    if err.code == "insufficient_balance":  # 402 — sem saldo
        ...
    elif err.code == "rate_limited":        # 429 — muitas requisições
        ...
    else:
        print(err.status, err.code, err.message)
```

| `code`                  | HTTP | Significado                       |
| ----------------------- | ---- | --------------------------------- |
| `validation_error`      | 422  | Dados do request inválidos        |
| `unauthorized`          | 401  | Chave/token inválido              |
| `insufficient_balance`  | 402  | Saldo insuficiente                |
| `provider_out_of_stock` | 409  | Estoque do provedor indisponível  |
| `rate_limited`          | 429  | Limite de envios atingido         |

## Referência

### `SMSGo(api_key, *, base_url=..., timeout=30.0)`

| Parâmetro  | Tipo    | Default                    | Descrição                      |
| ---------- | ------- | -------------------------- | ------------------------------ |
| `api_key`  | `str`   | —                          | **Obrigatório.** Sua SMSGo-key.|
| `base_url` | `str`   | `https://api.smsgo.com.br` | Útil para local/staging.       |
| `timeout`  | `float` | `30.0`                     | Timeout das requisições (s).   |

### Métodos

- `send(phone, message, *, schedule=None, reference=None, sender=None, sms_type_id=None)` → `SendResult`
- `send_bulk(messages, *, url_callback=None, flash_sms=None, sms_type_id=None)` → `SendResult`
- `list(page=1)` → resposta paginada
- `get(id)` → detalhe de um envio

> `sender` é mapeado para o campo `from` da API (palavra reservada em Python).

## Ambiente local

```python
smsgo = SMSGo(api_key="...", base_url="http://localhost:3333")
```

## Exemplos

Na pasta [`examples/`](./examples):

```bash
SMSGO_KEY=suachave python examples/send_otp.py +5511999990000
```

## Migrando da TotalVoice / Twilio?

SMSGo foca em **DX simples e preço em real**. Sem cadastro de remetente pra começar, sem cobrança em dólar, créditos que não expiram. Há também o [SDK oficial Node.js](https://www.npmjs.com/package/@orynlabs/smsgo).

## Licença

MIT © SMSGo
