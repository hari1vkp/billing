"""End-to-end verification of the POS redesign.

Run after both backend and frontend are in place:
    python3 -m pip install httpx   # if needed
    python3 verify_pos.py

Tests role restrictions, barcode flow, POS billing, confirmed-payment stock
movements, activity logs and UPI QR metadata against a running backend.
"""

import time

import httpx

BASE = "http://localhost:8000/api/v1"


def client_for(email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=30)
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, (email, r.status_code, r.text)
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    return c


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise AssertionError(label)


def main() -> None:
    owner = client_for("demo@billingapp.com", "Demo@1234")
    staff = client_for("staff@billingapp.com", "Staff@1234")
    stamp = str(int(time.time()))

    # --- Role restrictions -------------------------------------------------
    restricted = [
        ("GET", "/analytics/dashboard", None),
        ("GET", "/activity", None),
        ("GET", "/inventory/movements", None),
        ("GET", "/business/users", None),
        ("PATCH", "/business", {"name": "Hacked"}),
    ]
    for method, path, body in restricted:
        r = staff.request(method, path, json=body) if body is not None else staff.request(method, path)
        check(f"staff blocked from {path}", r.status_code == 403, f"got {r.status_code}")

    # --- Barcode setup + lookup -------------------------------------------
    products = owner.get("/products?page_size=100").json()["items"]
    product = products[0]
    barcode = "POS" + stamp
    r = owner.patch(f"/products/{product['id']}", json={"barcode": barcode})
    check("set product barcode", r.status_code == 200 and r.json()["barcode"] == barcode)

    r = staff.get(f"/products/barcode/{barcode}")
    check("staff barcode lookup", r.status_code == 200 and r.json()["id"] == product["id"])

    # --- POS bill via barcode ----------------------------------------------
    stock_before = float(staff.get(f"/products/{product['id']}").json()["stock"])
    inv = staff.post(
        "/invoices",
        json={
            "customer_id": None,  # walk-in
            "items": [{"barcode": barcode, "quantity": 1}],
        },
    )
    check("POS invoice with barcode + walk-in customer", inv.status_code == 201, str(inv.status_code))
    invoice = inv.json()
    check("invoice has transaction_ref", bool(invoice.get("transaction_ref")), invoice.get("transaction_ref", ""))
    check("walk-in customer resolved", bool(invoice.get("customer_name")), invoice.get("customer_name", ""))

    # --- QR metadata --------------------------------------------------------
    qr = staff.get(f"/invoices/{invoice['id']}/qr")
    check("QR generated", qr.status_code == 200 and bool(qr.json().get("qr_data_url")))
    check("QR has transaction ref", qr.json().get("transaction_ref") == invoice["transaction_ref"])

    # --- Customer declaration must NOT confirm -----------------------------
    pub = httpx.Client(base_url=BASE, timeout=30)
    ref = "UTRPOS" + stamp
    decl = pub.post(
        f"/public/invoices/{invoice['public_token']}/payments",
        json={"amount": invoice["total_amount"], "method": "upi", "reference": ref},
    )
    check("customer declaration is submitted, not confirmed",
          decl.status_code == 201 and decl.json()["status"] == "submitted")
    check("invoice still unpaid after declaration",
          staff.get(f"/invoices/{invoice['id']}").json()["status"] == "unpaid")

    # --- Staff confirms with UTR -------------------------------------------
    conf = staff.post(f"/payments/{decl.json()['id']}/confirm", json={"reference": ref})
    check("staff confirms payment", conf.status_code == 200 and conf.json()["status"] == "confirmed")
    paid = staff.get(f"/invoices/{invoice['id']}").json()
    check("invoice paid after confirmation", paid["status"] == "paid", paid["status"])

    # --- Stock movement from confirmed sale --------------------------------
    movements = owner.get(f"/inventory/movements?product_id={product['id']}").json()
    sale_rows = [m for m in movements["items"] if m["reason"] == "sale" and m["reference"] == invoice["invoice_number"]]
    check("stock movement logged for sale", len(sale_rows) >= 1, str(len(sale_rows)))
    stock_after = float(staff.get(f"/products/{product['id']}").json()["stock"])
    check("stock decremented", stock_after == stock_before - float(invoice["items"][0]["quantity"]),
          f"{stock_before} -> {stock_after}")

    # --- Limited staff stock adjustment ------------------------------------
    big = staff.post("/inventory/adjust", json={
        "product_id": product["id"], "quantity_change": 999, "reason": "correction"
    })
    check("staff large adjustment rejected", big.status_code == 400, str(big.status_code))
    small = staff.post("/inventory/adjust", json={
        "product_id": product["id"], "quantity_change": -1, "reason": "damaged", "notes": "quality check"
    })
    check("staff small adjustment allowed", small.status_code in (200, 201), str(small.status_code))

    # --- Activity logs ------------------------------------------------------
    activity = owner.get("/activity?page_size=100").json()
    actions = {a["action"] for a in activity["items"]}
    for expected in ("auth.login", "invoice.create", "payment.confirm", "stock.adjust"):
        check(f"activity log contains {expected}", expected in actions)

    print("\nAll POS verification checks passed.")


if __name__ == "__main__":
    main()
