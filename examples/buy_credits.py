"""Compra créditos off-session (cobra um cartão salvo) e liga a recarga automática.

    SMSGO_KEY=suachave python examples/buy_credits.py

AVISO: `billing.purchase` NÃO é idempotente — cada chamada gera uma cobrança
nova. Em timeout, consulte `billing.invoices()` antes de repetir.
"""

import os

from smsgo import SMSGo, SMSGoError

smsgo = SMSGo(api_key=os.environ["SMSGO_KEY"])

# Cartão padrão (ou escolha um id específico).
cards = smsgo.billing.cards()
if not cards:
    raise SystemExit("Nenhum cartão salvo. Cadastre um no painel primeiro.")
card = next((c for c in cards if c.default), cards[0])
print(f"Usando cartão final {card.number} ({card.flag}).")

try:
    receipt = smsgo.billing.purchase(quantity=1000, card_id=card.id)
    # 'succeeded' já creditou o saldo; 'processing' confirma via webhook.
    print(f"Compra {receipt.status}: {receipt.quantity} créditos por R$ {receipt.total:.2f}")
    print(f"Fatura: {receipt.invoice_uuid}")
except SMSGoError as err:
    print(f"Falhou ({err.code}): {err.message}")
    raise SystemExit(1)

# Liga a recarga automática: recompra 1000 créditos quando o saldo cair a R$ 10.
cfg = smsgo.set_auto_recharge(
    enabled=True,
    threshold=10,
    plan_quantity=1000,
    card_id=card.id,
    alert_enabled=True,
    alert_threshold=15,  # e-mail de alerta quando o saldo <= R$ 15
)
print(f"Recarga automática ligada: limiar R$ {cfg.threshold:.2f}.")
