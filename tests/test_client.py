import unittest
from unittest.mock import patch

from smsgo import SMSGo, SMSGoError, SendResult


def _auth_then(handler):
    """Helper: responde o token e delega o resto para `handler(seq)`."""
    seq = []

    def fake_raw(method, path, payload, headers):
        seq.append(path)
        if path == "/v1/auth/token":
            return 200, {"token": "tok"}
        return handler(seq)

    return fake_raw, seq


class TestClient(unittest.TestCase):
    def test_requires_api_key(self):
        with self.assertRaises(ValueError):
            SMSGo(api_key="")

    def test_default_base_url(self):
        self.assertEqual(SMSGo(api_key="k").base_url, "https://api.smsgo.com.br")

    def test_base_url_trailing_slash_stripped(self):
        self.assertEqual(SMSGo(api_key="k", base_url="http://x/").base_url, "http://x")

    def test_send_flow(self):
        c = SMSGo(api_key="k")
        fake_raw, seq = _auth_then(lambda s: (200, {"id": "abc", "quantity": 1, "status": "queued"}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            result = c.send(phone="+5511999990000", message="oi")
        self.assertIsInstance(result, SendResult)
        self.assertEqual(result.id, "abc")
        self.assertEqual(result.status, "queued")
        self.assertEqual(seq[0], "/v1/auth/token")
        self.assertEqual(seq[1], "/v1/sms/send/single")

    def test_token_is_cached(self):
        c = SMSGo(api_key="k")
        fake_raw, seq = _auth_then(lambda s: (200, {"id": "x", "quantity": 1, "status": "queued"}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.send(phone="+55", message="a")
            c.send(phone="+55", message="b")
        # apenas 1 chamada ao /auth/token, reaproveitando o token
        self.assertEqual(seq.count("/v1/auth/token"), 1)

    def test_error_raises_smsgoerror(self):
        c = SMSGo(api_key="k")
        fake_raw, _ = _auth_then(
            lambda s: (402, {"code": "insufficient_balance", "message": "Sem saldo"})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            with self.assertRaises(SMSGoError) as ctx:
                c.send(phone="+55", message="x")
        self.assertEqual(ctx.exception.status, 402)
        self.assertEqual(ctx.exception.code, "insufficient_balance")

    def test_401_refreshes_token_and_retries(self):
        c = SMSGo(api_key="k")

        def handler(seq):
            sends = [p for p in seq if p == "/v1/sms/send/single"]
            if len(sends) == 1:
                return 401, {"code": "unauthorized"}
            return 200, {"id": "ok", "quantity": 1, "status": "queued"}

        fake_raw, seq = _auth_then(handler)
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            result = c.send(phone="+55", message="x")
        self.assertEqual(result.id, "ok")
        # token foi buscado 2x (inicial + refresh no 401)
        self.assertEqual(seq.count("/v1/auth/token"), 2)


if __name__ == "__main__":
    unittest.main()
