import io
import json
import os
import sys
import unittest
import urllib.error
from unittest.mock import patch

# Permite rodar `python -m unittest discover -s tests` sem instalar o pacote
# (layout src/): garante que ``src`` esteja no sys.path.
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from smsgo import (
    AutoRechargeConfig,
    Balance,
    ContactDetail,
    ListResult,
    Paginated,
    Plan,
    PurchaseResult,
    SendDetail,
    SendResult,
    SmsTypeItem,
    SMSGo,
    SMSGoError,
    WebhookConfig,
    verify_webhook_signature,
)

# Golden webhook vector (determinístico — não mude).
GOLDEN_SECRET = "whsec_3f8a9c2e1b6d4a70f5e2c9b8a1d7e0f4"
GOLDEN_BODY = (
    '{"event":"sms.status","data":{"sendId":"7c3e1a90-2b4d-4f6a-8c1e-9d0f2a3b4c5d",'
    '"phone":"5511999990000","status":"delivered"}}'
)
GOLDEN_SIG = "sha256=986eb0c41355b1c94165c4cb275ce2cc9b175e5f93efe7e2ed4294ba58d330c3"


def _auth_then(handler):
    """Responde o token e delega o resto para ``handler(seq)``.

    Registra (method, path, payload) de cada chamada em ``calls``.
    """
    calls = []
    seq = []

    def fake_raw(method, path, payload, headers):
        calls.append((method, path, payload))
        seq.append(path)
        if path == "/v1/auth/token":
            return 200, {"token": "tok", "mode": "live"}
        return handler(seq)

    return fake_raw, seq, calls


class _FakeResp(io.BytesIO):
    """Contexto p/ simular urlopen: expõe .status e .read()."""

    def __init__(self, status, body):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class TestConstructor(unittest.TestCase):
    def test_requires_api_key(self):
        with self.assertRaises(ValueError):
            SMSGo(api_key="")

    def test_default_base_url(self):
        self.assertEqual(SMSGo(api_key="k").base_url, "https://api.smsgo.com.br")

    def test_base_url_trailing_slash_stripped(self):
        self.assertEqual(SMSGo(api_key="k", base_url="http://x///").base_url, "http://x")

    def test_namespaces_present(self):
        c = SMSGo(api_key="k")
        self.assertTrue(hasattr(c, "contacts"))
        self.assertTrue(hasattr(c, "lists"))
        self.assertTrue(hasattr(c, "billing"))


class TestSend(unittest.TestCase):
    def test_send_flow_and_mapping(self):
        c = SMSGo(api_key="k")
        fake_raw, seq, calls = _auth_then(
            lambda s: (200, {"id": "abc", "quantity": 1, "status": "queued"})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            result = c.send(phone="+5511999990000", message="oi", sender="MyBrand", sms_type_id=3)
        self.assertIsInstance(result, SendResult)
        self.assertEqual(result.id, "abc")
        self.assertEqual(seq[1], "/v1/sms/send/single")
        method, path, payload = calls[1]
        self.assertEqual(method, "POST")
        # sender -> from ; sms_type_id preservado ; None removido
        self.assertEqual(payload["from"], "MyBrand")
        self.assertEqual(payload["sms_type_id"], 3)
        self.assertNotIn("schedule", payload)

    def test_send_test_flag(self):
        c = SMSGo(api_key="test_k")
        fake_raw, _, _ = _auth_then(
            lambda s: (200, {"id": "x", "quantity": 1, "status": "queued", "test": True})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            result = c.send(phone="+55", message="a")
        self.assertTrue(result.test)

    def test_send_bulk_mapping(self):
        c = SMSGo(api_key="k")
        fake_raw, seq, calls = _auth_then(
            lambda s: (200, {"id": "bulk", "quantity": 2, "status": "queued"})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.send_bulk(
                messages=[{"phone": "+55", "message": "a"}],
                url_callback="https://cb",
                flash_sms=True,
                sms_type_id=1,
            )
        _, path, payload = calls[1]
        self.assertEqual(path, "/v1/sms/send/multiple")
        self.assertEqual(payload["urlCallback"], "https://cb")
        self.assertTrue(payload["flashSms"])
        self.assertEqual(payload["sms_type_id"], 1)

    def test_token_is_cached(self):
        c = SMSGo(api_key="k")
        fake_raw, seq, _ = _auth_then(
            lambda s: (200, {"id": "x", "quantity": 1, "status": "queued"})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.send(phone="+55", message="a")
            c.send(phone="+55", message="b")
        self.assertEqual(seq.count("/v1/auth/token"), 1)


class TestAuthMode(unittest.TestCase):
    def test_mode_none_before_call(self):
        self.assertIsNone(SMSGo(api_key="k").mode)

    def test_resolve_mode_test(self):
        c = SMSGo(api_key="test_k")

        def fake_raw(method, path, payload, headers):
            return 200, {"token": "tok", "mode": "test"}

        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            self.assertEqual(c.resolve_mode(), "test")
        self.assertEqual(c.mode, "test")

    def test_resolve_mode_live(self):
        c = SMSGo(api_key="k")
        fake_raw, _, _ = _auth_then(lambda s: (200, {}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            self.assertEqual(c.resolve_mode(), "live")


class TestQuery(unittest.TestCase):
    def test_list_paginated(self):
        c = SMSGo(api_key="k")
        page = {
            "meta": {
                "total": 1,
                "perPage": 20,
                "currentPage": 1,
                "lastPage": 1,
                "firstPage": 1,
                "firstPageUrl": "/?page=1",
                "lastPageUrl": "/?page=1",
                "nextPageUrl": None,
                "previousPageUrl": None,
            },
            "data": [
                {
                    "id": "s1",
                    "number": 5,
                    "date": None,
                    "quantity": 1,
                    "full_name": "Ana",
                    "created_at": "2026-01-01",
                    "status": "entregue",
                    "type": "single",
                }
            ],
        }
        fake_raw, _, calls = _auth_then(lambda s: (200, page))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.list(page=2)
        self.assertIsInstance(out, Paginated)
        self.assertEqual(out.meta.per_page, 20)
        self.assertEqual(out.data[0].full_name, "Ana")
        self.assertEqual(calls[1][1], "/v1/sms/list?page=2")

    def test_get_detail_summary(self):
        c = SMSGo(api_key="k")
        detail = {
            "id": "s1",
            "quantity": 1,
            "characters": 10,
            "date": None,
            "total": 0.1,
            "cost": 0.1,
            "user": "u",
            "status": "entregue",
            "type": "single",
            "summary": {"total": 1, "delivered": 1, "failed": 0, "inProgress": 0, "done": True},
            "phones": [
                {
                    "id": "p1",
                    "characters": 10,
                    "code": None,
                    "cost": 0.1,
                    "message": "oi",
                    "phone": "+55",
                    "status": "entregue",
                    "template": None,
                    "created_at": "2026-01-01",
                }
            ],
        }
        fake_raw, _, calls = _auth_then(lambda s: (200, detail))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.get("s1")
        self.assertIsInstance(out, SendDetail)
        self.assertTrue(out.summary.done)
        self.assertEqual(out.summary.in_progress, 0)
        self.assertEqual(out.phones[0].id, "p1")

    def test_get_numbers_query(self):
        c = SMSGo(api_key="k")
        page = {"meta": {}, "data": []}
        fake_raw, _, calls = _auth_then(lambda s: (200, page))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.get_numbers("s1", status="failed", page=3)
        self.assertEqual(calls[1][1], "/v1/sms/s1/numbers?status=failed&page=3")

    def test_get_sms_types_unwraps_data(self):
        c = SMSGo(api_key="k")
        payload = {"data": [{"id": 1, "name": "Marketing", "price": 0.12, "sale": None}]}
        fake_raw, _, calls = _auth_then(lambda s: (200, payload))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.get_sms_types()
        self.assertEqual(calls[1][1], "/v1/sms-types")
        self.assertIsInstance(out[0], SmsTypeItem)
        self.assertEqual(out[0].id, 1)


class TestAccount(unittest.TestCase):
    def test_get_balance(self):
        c = SMSGo(api_key="k")
        body = {"balance": 42.5, "currency": "BRL", "company": {"name": "X", "document": None}}
        fake_raw, _, calls = _auth_then(lambda s: (200, body))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.get_balance()
        self.assertEqual(calls[1][1], "/v1/account/balance")
        self.assertIsInstance(out, Balance)
        self.assertEqual(out.balance, 42.5)
        self.assertEqual(out.company["name"], "X")

    def test_get_auto_recharge_mapping(self):
        c = SMSGo(api_key="k")
        body = {
            "enabled": True,
            "threshold": 10,
            "planQuantity": 1000,
            "cardId": "card_1",
            "alertEnabled": True,
            "alertThreshold": 15,
        }
        fake_raw, _, _ = _auth_then(lambda s: (200, body))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.get_auto_recharge()
        self.assertIsInstance(out, AutoRechargeConfig)
        self.assertEqual(out.plan_quantity, 1000)
        self.assertEqual(out.card_id, "card_1")

    def test_set_auto_recharge_body_mapping(self):
        c = SMSGo(api_key="k")
        body = {
            "enabled": True,
            "threshold": 10,
            "planQuantity": 1000,
            "cardId": "card_1",
            "alertEnabled": False,
            "alertThreshold": 5,
        }
        fake_raw, _, calls = _auth_then(lambda s: (200, body))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.set_auto_recharge(enabled=True, plan_quantity=1000, card_id="card_1", threshold=10)
        method, path, payload = calls[1]
        self.assertEqual(method, "PUT")
        self.assertEqual(path, "/v1/account/auto-recharge")
        self.assertEqual(payload["plan_quantity"], 1000)
        self.assertEqual(payload["card_id"], "card_1")
        self.assertNotIn("alert_enabled", payload)

    def test_get_webhook(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(
            lambda s: (200, {"url": "https://cb", "secret": "whsec_x"})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.get_webhook()
        self.assertEqual(calls[1][1], "/v1/account/webhook")
        self.assertIsInstance(out, WebhookConfig)
        self.assertEqual(out.secret, "whsec_x")

    def test_set_webhook_body_mapping(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(lambda s: (200, {"url": None, "secret": "new"}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.set_webhook(rotate_secret=True)
        method, path, payload = calls[1]
        self.assertEqual(method, "PUT")
        self.assertEqual(payload, {"rotate_secret": True})


class TestContacts(unittest.TestCase):
    def test_create_body_and_uuid(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(lambda s: (200, "uuid-123"))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.contacts.create(
                full_name="Ana Souza", phone="+55", email="a@x.com", lists=["l1"]
            )
        self.assertEqual(out, "uuid-123")
        method, path, payload = calls[1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/v1/contacts/store")
        self.assertEqual(payload["full_name"], "Ana Souza")
        self.assertEqual(payload["lists"], ["l1"])

    def test_get_detail(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(
            lambda s: (200, {"fullName": "Ana", "email": None, "phone": "+55"})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.contacts.get("id1")
        self.assertEqual(calls[1][1], "/v1/contacts/id1/show")
        self.assertIsInstance(out, ContactDetail)
        self.assertEqual(out.full_name, "Ana")

    def test_list_query(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(lambda s: (200, {"meta": {}, "data": []}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.contacts.list(page=1, search="ana")
        self.assertEqual(calls[1][1], "/v1/contacts/list?page=1&search=ana")

    def test_delete(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(lambda s: (200, {"message": "ok"}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.contacts.delete("id1")
        self.assertEqual(calls[1][0], "DELETE")
        self.assertEqual(calls[1][1], "/v1/contacts/id1/delete")
        self.assertEqual(out["message"], "ok")


class TestLists(unittest.TestCase):
    def test_create(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(lambda s: (200, {"name": "VIP", "id": "l1"}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.lists.create(name="VIP")
        self.assertIsInstance(out, ListResult)
        self.assertEqual(out.id, "l1")
        self.assertEqual(calls[1][2], {"name": "VIP"})


class TestBilling(unittest.TestCase):
    def test_plans_unwraps(self):
        c = SMSGo(api_key="k")
        payload = {
            "data": [
                {
                    "id": "p1",
                    "quantity": 1000,
                    "price": 120,
                    "sale": 100,
                    "unit": 0.1,
                    "total": 100,
                    "popular": True,
                }
            ]
        }
        fake_raw, _, calls = _auth_then(lambda s: (200, payload))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.billing.plans()
        self.assertEqual(calls[1][1], "/v1/billing/plans")
        self.assertIsInstance(out[0], Plan)
        self.assertTrue(out[0].popular)

    def test_invoices_query(self):
        c = SMSGo(api_key="k")
        fake_raw, _, calls = _auth_then(lambda s: (200, {"meta": {}, "data": []}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            c.billing.invoices(page=2, per_page=50)
        self.assertEqual(calls[1][1], "/v1/billing/invoices?page=2&perPage=50")

    def test_purchase_body_and_result(self):
        c = SMSGo(api_key="k")
        result = {
            "status": "succeeded",
            "invoiceUuid": "inv-1",
            "total": 100,
            "quantity": 1000,
            "paymentIntentId": "pi_1",
        }
        fake_raw, _, calls = _auth_then(lambda s: (200, result))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            out = c.billing.purchase(quantity=1000, card_id="card_1", coupon="X10")
        method, path, payload = calls[1]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/v1/billing/purchase")
        self.assertEqual(payload["plan_id"] if "plan_id" in payload else None, None)
        self.assertEqual(payload["card_id"], "card_1")
        self.assertEqual(payload["coupon"], "X10")
        self.assertIsInstance(out, PurchaseResult)
        self.assertEqual(out.invoice_uuid, "inv-1")
        self.assertEqual(out.payment_intent_id, "pi_1")


class TestErrors(unittest.TestCase):
    def test_error_raises_smsgoerror(self):
        c = SMSGo(api_key="k")
        fake_raw, _, _ = _auth_then(
            lambda s: (402, {"code": "insufficient_balance", "message": "Sem saldo"})
        )
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            with self.assertRaises(SMSGoError) as ctx:
                c.send(phone="+55", message="x")
        self.assertEqual(ctx.exception.status, 402)
        self.assertEqual(ctx.exception.code, "insufficient_balance")

    def test_validation_errors_parsed(self):
        c = SMSGo(api_key="k")
        body = {
            "code": "validation_error",
            "message": "inválido",
            "errors": [{"field": "phone", "message": "obrigatório"}],
        }
        fake_raw, _, _ = _auth_then(lambda s: (422, body))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            with self.assertRaises(SMSGoError) as ctx:
                c.send(phone="", message="x")
        self.assertEqual(ctx.exception.code, "validation_error")
        self.assertEqual(ctx.exception.errors[0].field, "phone")

    def test_http_code_name_fallback(self):
        c = SMSGo(api_key="k")
        fake_raw, _, _ = _auth_then(lambda s: (503, {"message": "down"}))
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            with self.assertRaises(SMSGoError) as ctx:
                c.get_balance()
        self.assertEqual(ctx.exception.code, "payment_unavailable")

    def test_401_refreshes_token_and_retries(self):
        c = SMSGo(api_key="k")

        def handler(seq):
            sends = [p for p in seq if p == "/v1/sms/send/single"]
            if len(sends) == 1:
                return 401, {"code": "unauthorized"}
            return 200, {"id": "ok", "quantity": 1, "status": "queued"}

        fake_raw, seq, _ = _auth_then(handler)
        with patch.object(SMSGo, "_raw", side_effect=fake_raw):
            result = c.send(phone="+55", message="x")
        self.assertEqual(result.id, "ok")
        self.assertEqual(seq.count("/v1/auth/token"), 2)


class TestTransport(unittest.TestCase):
    """Cobre _raw via patch de urllib.request.urlopen no nível do módulo."""

    def test_network_error(self):
        c = SMSGo(api_key="k")
        with patch(
            "smsgo.client.urllib.request.urlopen",
            side_effect=urllib.error.URLError("boom"),
        ):
            with self.assertRaises(SMSGoError) as ctx:
                c.send(phone="+55", message="x")
        self.assertEqual(ctx.exception.status, 0)
        self.assertEqual(ctx.exception.code, "network_error")

    def test_content_type_only_with_body(self):
        c = SMSGo(api_key="k")
        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append((req.method, req.full_url, dict(req.header_items()), req.data))
            if req.full_url.endswith("/v1/auth/token"):
                return _FakeResp(200, {"token": "tok", "mode": "live"})
            return _FakeResp(200, {"id": "a", "quantity": 1, "status": "queued"})

        with patch("smsgo.client.urllib.request.urlopen", side_effect=fake_urlopen):
            c.send(phone="+55", message="x")

        auth = next(x for x in seen if x[1].endswith("/v1/auth/token"))
        post = next(x for x in seen if x[1].endswith("/v1/sms/send/single"))
        # GET de token não tem Content-Type; POST tem.
        self.assertNotIn("Content-type", auth[2])
        self.assertEqual(post[2].get("Content-type"), "application/json")
        self.assertIsNotNone(post[3])


class TestWebhookVerify(unittest.TestCase):
    def test_golden_vector_true(self):
        self.assertTrue(verify_webhook_signature(GOLDEN_BODY, GOLDEN_SIG, GOLDEN_SECRET))

    def test_golden_vector_bytes(self):
        self.assertTrue(
            verify_webhook_signature(GOLDEN_BODY.encode(), GOLDEN_SIG, GOLDEN_SECRET)
        )

    def test_tampered_body(self):
        tampered = GOLDEN_BODY.replace("delivered", "failed")
        self.assertFalse(verify_webhook_signature(tampered, GOLDEN_SIG, GOLDEN_SECRET))

    def test_wrong_secret(self):
        self.assertFalse(verify_webhook_signature(GOLDEN_BODY, GOLDEN_SIG, "whsec_wrong"))

    def test_flipped_byte_signature(self):
        bad = GOLDEN_SIG[:-1] + ("0" if GOLDEN_SIG[-1] != "0" else "1")
        self.assertFalse(verify_webhook_signature(GOLDEN_BODY, bad, GOLDEN_SECRET))

    def test_empty_and_none_signature(self):
        self.assertFalse(verify_webhook_signature(GOLDEN_BODY, "", GOLDEN_SECRET))
        self.assertFalse(verify_webhook_signature(GOLDEN_BODY, None, GOLDEN_SECRET))

    def test_none_body(self):
        self.assertFalse(verify_webhook_signature(None, GOLDEN_SIG, GOLDEN_SECRET))


if __name__ == "__main__":
    unittest.main()
