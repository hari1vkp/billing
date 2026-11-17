"""End-to-end smoke test against a running backend.

Start the server first, then run:  .venv/bin/python smoke_test.py
Verifies authentication, calculations, the payment-confirmation workflow,
webhook signature verification, token rotation and tenant isolation.
"""

import hashlib
import hmac
import json
import time

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = "demo@billingapp.com"
PASSWORD = "Demo@1234"


def main():
    api = httpx.Client(base_url=BASE, timeout=30)
    token = api.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()
    api.headers["Authorization"] = "Bearer " + token["access_token"]

    suffix = str(int(time.time()))
    customer = api.post("/customers", json={"name": f"Smoke Customer {suffix}"}).json()
    product = api.post(
        "/products",
        json={"name": f"Smoke Product {suffix}", "price": 1000, "gst_rate": 18,
              "stock": 10, "low_stock_threshold": 5},
    ).json()
    invoice = api.post(
        "/invoices",
        json={"customer_id": customer["id"], "items": [
            {"product_id": product["id"], "quantity": 2, "discount_percent": 10}
        ]},
    ).json()
    assert abs(invoice["total_amount"] - 2124) < 0.01, invoice

    # Customer declares a payment — must NOT confirm it.
    public = httpx.Client(base_url=BASE, timeout=30)
    ref = "UTRSMOKE" + suffix
    declared = public.post(
        f"/public/invoices/{invoice['public_token']}/payments",
        json={"amount": 2124, "method": "upi", "reference": ref},
    ).json()
    assert declared["status"] == "submitted"
    assert api.get(f"/invoices/{invoice['id']}").json()["paid_amount"] == 0

    # Staff confirms with the UTR.
    confirmed = api.post(
        f"/payments/{declared['id']}/confirm", json={"reference": ref}
    ).json()
    assert confirmed["status"] == "confirmed"
    invoice_after = api.get(f"/invoices/{invoice['id']}").json()
    assert invoice_after["status"] == "paid"
    assert api.get(f"/products/{product['id']}").json()["stock"] == 8

    # Webhook with a valid HMAC confirms a pending payment.
    inv2 = api.post(
        "/invoices",
        json={"customer_id": customer["id"],
              "items": [{"product_id": product["id"], "quantity": 1}]},
    ).json()
    ref2 = "WEBHOOK" + suffix
    api.post("/payments", json={"invoice_id": inv2["id"],
                                "amount": inv2["total_amount"],
                                "method": "upi", "reference": ref2,
                                "confirm": False})
    body = json.dumps({"event_id": "evt_" + suffix, "event": "payment.success",
                       "data": {"status": "success", "reference": ref2}}).encode()
    secret = "dev-webhook-secret-change-me"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = public.post(
        "/webhooks/payments/testprovider", content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sig},
    )
    assert response.status_code == 200 and response.json()["processed"]
    assert api.get(f"/invoices/{inv2['id']}").json()["status"] == "paid"

    # Invalid signature is rejected.
    assert public.post(
        "/webhooks/payments/testprovider", content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": "bad"},
    ).status_code == 401

    # Refresh rotation: replaying a used refresh token is rejected.
    tokens = api.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()
    assert api.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    assert api.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401

    # Cross-business isolation.
    other = httpx.Client(base_url=BASE, timeout=30)
    reg = other.post("/auth/register", json={
        "business_name": "Other " + suffix, "owner_name": "Other Owner",
        "email": f"other{suffix}@example.com", "password": "Other@1234",
    }).json()
    other.headers["Authorization"] = "Bearer " + reg["access_token"]
    assert other.get(f"/invoices/{invoice['id']}").status_code == 404

    print("All smoke tests passed.")


if __name__ == "__main__":
    main()
