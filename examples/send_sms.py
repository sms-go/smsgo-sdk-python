"""Envio simples de 1 SMS.

    SMSGO_KEY=suachave python examples/send_sms.py +5511999990000
"""

import os
import sys

from smsgo import SMSGo

smsgo = SMSGo(api_key=os.environ["SMSGO_KEY"])

phone = sys.argv[1] if len(sys.argv) > 1 else "+5511999990000"
result = smsgo.send(phone=phone, message="Olá do SMSGo 👋")

print("Enviado:", result)  # SendResult(id=..., quantity=1, status=...)
