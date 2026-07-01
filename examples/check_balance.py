"""Consulta o saldo, o catálogo de tipos de SMS e a config de recarga automática.

    SMSGO_KEY=suachave python examples/check_balance.py
"""

import os

from smsgo import SMSGo

smsgo = SMSGo(api_key=os.environ["SMSGO_KEY"])

balance = smsgo.get_balance()
print(f"Saldo: R$ {balance.balance:.2f} ({balance.currency})")
print(f"Conta: {balance.company.get('name')}")

print("\nTipos de SMS disponíveis (use o id em sms_type_id):")
for t in smsgo.get_sms_types():
    price = t.sale if t.sale is not None else t.price
    print(f"  [{t.id}] {t.name} — R$ {price:.4f}/SMS")

cfg = smsgo.get_auto_recharge()
print(f"\nRecarga automática: {'ligada' if cfg.enabled else 'desligada'} "
      f"(limiar R$ {cfg.threshold:.2f}, {cfg.plan_quantity} créditos/recarga)")
