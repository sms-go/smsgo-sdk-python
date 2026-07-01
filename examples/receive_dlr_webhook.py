"""Recebe callbacks de entrega (DLR) e valida a assinatura HMAC.

Servidor HTTP mínimo (stdlib) que verifica o cabeçalho `X-SMSGo-Signature`
antes de confiar no corpo. Em produção, use seu framework (Flask/FastAPI/etc.)
— o importante é validar sobre o CORPO BRUTO, sem reparsear/reserializar.

    SMSGO_WEBHOOK_SECRET=whsec_... python examples/receive_dlr_webhook.py
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from smsgo import verify_webhook_signature

SECRET = os.environ.get("SMSGO_WEBHOOK_SECRET", "whsec_troque_pelo_seu_segredo")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)  # corpo BRUTO — não reparseie antes de validar
        signature = self.headers.get("X-SMSGo-Signature")

        if not verify_webhook_signature(raw, signature, SECRET):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"invalid signature")
            return

        event = json.loads(raw)
        # event["event"]  -> "sms.status" (DLR) | "sms.reply" (resposta)
        # event["data"]   -> { sendId, phone, status, ... }
        print("Evento verificado:", event.get("event"), event.get("data"))

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silencia o log padrão
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print("Ouvindo webhooks em http://0.0.0.0:8080 (Ctrl+C p/ sair)")
    server.serve_forever()
