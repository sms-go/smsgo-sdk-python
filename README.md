# smsgo (Python)

[![PyPI](https://img.shields.io/pypi/v/smsgo.svg)](https://pypi.org/project/smsgo/)
[![Python](https://img.shields.io/pypi/pyversions/smsgo.svg)](https://pypi.org/project/smsgo/)
[![CI](https://github.com/sms-go/smsgo-sdk-python/actions/workflows/ci.yml/badge.svg)](https://github.com/sms-go/smsgo-sdk-python/actions/workflows/ci.yml)
[![license](https://img.shields.io/pypi/l/smsgo.svg)](./LICENSE)

SDK oficial **Python** para a [SMSGo](https://smsgo.com.br) — a API de SMS simples para o Brasil. Envie **OTP/2FA, alertas transacionais e campanhas** com poucas linhas.

- ⚡ **Integra em minutos** — autenticação cuidada pra você (sem ritual de token manual).
- 💸 **Sem mensalidade** — créditos pré-pagos que não expiram, preço em real.
- 🇧🇷 **Brasil-first** — entrega para todas as operadoras, LGPD nativo.
- 🟢 **Zero dependências** — usa só a biblioteca padrão. Tipado (`py.typed`).
- 🎁 **R$ 10 grátis** ao criar a conta — dá pra testar sem cartão.

> Nova conta e chave em **[smsgo.com.br](https://smsgo.com.br)** → painel → **Minha conta → API**.

Paridade total com o [SDK oficial Node.js](https://www.npmjs.com/package/@orynlabs/smsgo): mesmos métodos, mapeamentos de campo, autenticação e erros.

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

Você passa só a `api_key`. O SDK troca a chave por um token Bearer (válido 48h), guarda em cache e renova sozinho quando expira ou retorna 401.

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
page = smsgo.list(page=1)                 # Paginated(meta, data=[SendListItem, ...])
detail = smsgo.get("a1b2c3-...")          # SendDetail com summary de acompanhamento
print(detail.summary.delivered, detail.summary.done)

# Números de um envio, filtrando por bucket de status:
nums = smsgo.get_numbers("a1b2c3-...", status="failed", page=1)  # delivered|failed|in_progress
```

## Modo de teste (sandbox)

Use a **chave de teste** (prefixo `test_`, no painel → Minha conta → API) como `api_key`. Nada muda no código: os envios **não debitam saldo nem são despachados de verdade**, as respostas são idênticas às de produção (com `test=True`) e os webhooks disparam com o mesmo flag.

```python
sandbox = SMSGo(api_key=os.environ["SMSGO_TEST_KEY"])
print(sandbox.resolve_mode())  # 'test'  (ou use a propriedade `sandbox.mode`)
r = sandbox.send(phone="+5511999990000", message="teste")
print(r.test)  # True
```

`mode` retorna `None` antes da 1ª chamada autenticada; `resolve_mode()` força a resolução.

## Saldo e catálogo

```python
balance = smsgo.get_balance()
print(balance.balance, balance.currency)          # 42.50 'BRL'
print(balance.company["name"])

for t in smsgo.get_sms_types():                   # catálogo (id vai em sms_type_id)
    print(t.id, t.name, t.sale or t.price)
```

## Comprar créditos + recarga automática

`billing.purchase` cobra um cartão salvo **off-session**. Informe `quantity` **ou** `plan_id`; sem `card_id`, usa o cartão padrão.

> ⚠️ **Não é idempotente**: cada chamada gera uma cobrança nova. Em timeout, consulte `smsgo.billing.invoices()` antes de repetir — não faça retry cego.

```python
plans = smsgo.billing.plans()      # pacotes (tiers)
cards = smsgo.billing.cards()      # cartões salvos (4 últimos dígitos)

receipt = smsgo.billing.purchase(quantity=1000, card_id=cards[0].id)
print(receipt.status)   # 'succeeded' já creditou o saldo | 'processing' confirma via webhook
print(receipt.invoice_uuid, receipt.total)

# Recarga automática + alerta de saldo:
smsgo.set_auto_recharge(
    enabled=True,
    threshold=10,          # recarrega quando o saldo <= R$ 10
    plan_quantity=1000,    # compra 1000 créditos a cada recarga
    card_id=cards[0].id,   # obrigatório p/ ligar
    alert_enabled=True,
    alert_threshold=15,    # e-mail quando o saldo <= R$ 15
)
cfg = smsgo.get_auto_recharge()
```

## Webhooks de saída (DLR + respostas)

```python
# Define a URL que recebe `sms.status` (DLR) e `sms.reply` (resposta). Guarde o secret.
cfg = smsgo.set_webhook(url="https://seuapp.com/webhooks/smsgo")
print(cfg.url, cfg.secret)

smsgo.set_webhook(rotate_secret=True)   # gira o segredo
smsgo.set_webhook(url="")               # desativa
```

Cada requisição traz `X-SMSGo-Signature: sha256=<hmac>` — o HMAC-SHA256 do **corpo bruto** com o seu `secret`. **Valide sempre** com o helper embutido (comparação em tempo constante, nunca levanta exceção):

```python
from smsgo import verify_webhook_signature

# raw_body: bytes/str exatamente como recebido (NÃO reparseie antes de validar)
ok = verify_webhook_signature(raw_body, request.headers["X-SMSGo-Signature"], secret)
if not ok:
    return "invalid signature", 401
```

Servidor completo em [`examples/receive_dlr_webhook.py`](./examples/receive_dlr_webhook.py).

## Contatos e listas

```python
list_id = smsgo.lists.create(name="Clientes VIP").id
contact_id = smsgo.contacts.create(
    full_name="Ana Souza",
    phone="+5511999990000",
    email="ana@exemplo.com",
    lists=[list_id],
)

smsgo.contacts.list(page=1, search="ana")   # Paginated(meta, data)
smsgo.contacts.update(contact_id, full_name="Ana S.", phone="+5511999990000")
smsgo.contacts.delete(contact_id)
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
    elif err.code == "validation_error":    # 422 — detalhe por campo
        for fe in err.errors or []:
            print(fe.field, fe.message)
    else:
        print(err.status, err.code, err.message)
```

| `code`                  | HTTP | Significado                       |
| ----------------------- | ---- | --------------------------------- |
| `bad_request`           | 400  | Requisição malformada             |
| `unauthorized`          | 401  | Chave/token inválido              |
| `insufficient_balance`  | 402  | Saldo insuficiente                |
| `provider_out_of_stock` | 409  | Estoque do provedor indisponível  |
| `validation_error`      | 422  | Dados do request inválidos        |
| `rate_limited`          | 429  | Limite de envios atingido         |
| `payment_unavailable`   | 503  | Pagamento temporariamente fora    |
| `network_error`         | 0    | Falha de rede/transporte          |

## Referência

### `SMSGo(api_key, *, base_url=..., timeout=30.0)`

| Parâmetro  | Tipo    | Default                    | Descrição                      |
| ---------- | ------- | -------------------------- | ------------------------------ |
| `api_key`  | `str`   | —                          | **Obrigatório.** Sua SMSGo-key.|
| `base_url` | `str`   | `https://api.smsgo.com.br` | Não precisa mexer; só se a SMSGo orientar. |
| `timeout`  | `float` | `30.0`                     | Timeout das requisições (s).   |

### Métodos (cliente)

- `send(phone, message, *, schedule=None, reference=None, sender=None, sms_type_id=None)` → `SendResult`
- `send_bulk(messages, *, url_callback=None, flash_sms=None, sms_type_id=None)` → `SendResult`
- `list(page=1)` → `Paginated[SendListItem]`
- `get(id)` → `SendDetail`
- `get_numbers(id, *, status=None, page=None)` → `Paginated[SendNumberItem]`
- `get_sms_types()` → `list[SmsTypeItem]`
- `get_balance()` → `Balance`
- `get_auto_recharge()` → `AutoRechargeConfig`
- `set_auto_recharge(*, enabled=None, threshold=None, plan_quantity=None, card_id=None, alert_enabled=None, alert_threshold=None)` → `AutoRechargeConfig`
- `get_webhook()` / `set_webhook(*, url=None, rotate_secret=None)` → `WebhookConfig`
- `resolve_mode()` → `'live' | 'test'` · propriedade `mode` → `'live' | 'test' | None`

> `sender` é mapeado para o campo `from` da API (palavra reservada em Python).

### `smsgo.contacts`

- `list(*, page, per_page=None, search=None, title=None)` → `Paginated`
- `create(*, full_name, phone, email=None, lists=None)` → `str` (UUID)
- `get(id)` → `ContactDetail` · `update(id, *, full_name, phone, email=None, lists=None)` → `str` · `delete(id)` → `dict`

### `smsgo.lists`

- `list(*, page, per_page=None, title=None)` → `Paginated`
- `create(*, name)` / `get(id)` / `update(id, *, name)` → `ListResult` · `delete(id)` → `dict`

### `smsgo.billing`

- `plans()` → `list[Plan]` · `cards()` → `list[Card]`
- `invoices(*, page=None, per_page=None)` → `Paginated[InvoiceItem]`
- `purchase(*, quantity=None, plan_id=None, card_id=None, coupon=None)` → `PurchaseResult` (**não idempotente**)

### Módulo

- `verify_webhook_signature(raw_body, signature_header, secret)` → `bool` — valida `X-SMSGo-Signature` em tempo constante.

## Exemplos

Na pasta [`examples/`](./examples):

```bash
SMSGO_KEY=suachave python examples/send_sms.py +5511999990000
SMSGO_KEY=suachave python examples/send_otp.py +5511999990000
SMSGO_KEY=suachave python examples/check_status.py
SMSGO_KEY=suachave python examples/check_balance.py
SMSGO_KEY=suachave python examples/buy_credits.py
SMSGO_KEY=suachave python examples/configure_webhook.py https://seuapp.com/webhooks/smsgo
SMSGO_WEBHOOK_SECRET=whsec_... python examples/receive_dlr_webhook.py
```

## Migrando da TotalVoice / Twilio?

SMSGo foca em **DX simples e preço em real**. Sem cadastro de remetente pra começar, sem cobrança em dólar, créditos que não expiram. Há também o [SDK oficial Node.js](https://www.npmjs.com/package/@orynlabs/smsgo).

## Licença

MIT © SMSGo
