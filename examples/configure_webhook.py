"""Configura o webhook de saída (DLR + respostas) e guarda o segredo.

    SMSGO_KEY=suachave python examples/configure_webhook.py https://seuapp.com/webhooks/smsgo
"""

import os
import sys

from smsgo import SMSGo

smsgo = SMSGo(api_key=os.environ["SMSGO_KEY"])

url = sys.argv[1] if len(sys.argv) > 1 else "https://seuapp.com/webhooks/smsgo"

cfg = smsgo.set_webhook(url=url)
print(f"Webhook: {cfg.url}")
print(f"Segredo (guarde com segurança): {cfg.secret}")

# Gire o segredo quando precisar:
#   smsgo.set_webhook(rotate_secret=True)
# Desative o webhook com uma URL vazia:
#   smsgo.set_webhook(url="")
