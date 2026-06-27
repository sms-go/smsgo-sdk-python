"""Envio de um código OTP (2FA) por SMS.

    SMSGO_KEY=suachave python examples/send_otp.py +5511999990000
"""

import os
import random
import sys

from smsgo import SMSGo, SMSGoError

smsgo = SMSGo(api_key=os.environ["SMSGO_KEY"])

phone = sys.argv[1] if len(sys.argv) > 1 else "+5511999990000"
code = f"{random.randint(0, 999999):06d}"  # 6 dígitos

try:
    smsgo.send(phone=phone, message=f"Seu código SMSGo é {code}. Válido por 5 minutos.")
    # Em produção: guarde `code` com TTL (ex.: Redis) e compare na verificação.
    print(f"OTP {code} enviado para {phone}")
except SMSGoError as err:
    print(f"Falhou ({err.code}): {err.message}")
