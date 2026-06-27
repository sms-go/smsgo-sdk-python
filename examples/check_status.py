"""Envio em massa + consulta de status pelo id retornado.

    SMSGO_KEY=suachave python examples/check_status.py
"""

import os

from smsgo import SMSGo

smsgo = SMSGo(api_key=os.environ["SMSGO_KEY"])

sent = smsgo.send_bulk(
    messages=[
        {"phone": "+5511999990000", "message": "Oi, Ana!"},
        {"phone": "+5521988887777", "message": "Oi, Bruno!"},
    ]
)
print("Lote enviado:", sent)

# Detalhe de um envio pelo UUID
print("Status:", smsgo.get(sent.id))

# Lista paginada dos últimos envios da conta
print("Página 1:", smsgo.list(page=1))
