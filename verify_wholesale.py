"""End-to-end verification of wholesale/retail POS pricing."""

import httpx

B = "http://localhost:8000/api/v1"


def login(email, password):
    c = httpx.Client(base_url=B, timeout=30)
    t = c.post("/auth/login", json={"email": email, "password": password}).json()
    c.headers["Authorization"] = "Bearer " + t["access_token"]
    return c


def main():
    owner = login("demo@billingapp.com", "Demo@1234")
    staff = login("staff@billingapp.com", "Staff@1234")

    product = owner.get("/products?page_size=3").json()["items"][0]
    original_price = float(product["price"])
    patched = owner.patch(
        f"/products/{product['id']}", json={"wholesale_discount_percent": 20}
    )
    print("PATCH product:", patched.status_code, patched.json().get("wholesale_discount_percent"),
          "derived wholesale:", patched.json().get("wholesale_price"))
    assert patched.status_code == 200 and abs(patched.json()["wholesale_price"] - original_price * 0.8) < 0.01

    base = {"customer_id": None, "items": [{"product_id": product["id"], "quantity": 2}]}
    retail = staff.post("/invoices", json={**base, "pricing_mode": "retail"}).json()
    wholesale = staff.post("/invoices", json={**base, "pricing_mode": "wholesale"}).json()
    print("retail mode:", retail["pricing_mode"], retail["items"][0]["unit_price"],
          "wholesale mode:", wholesale["pricing_mode"], wholesale["items"][0]["unit_price"],
          "discount:", wholesale["items"][0]["wholesale_discount_percent"])
    assert retail["pricing_mode"] == "retail"
    assert wholesale["pricing_mode"] == "wholesale"
    assert abs(wholesale["items"][0]["unit_price"] - original_price * 0.8) < 0.01
    assert wholesale["items"][0]["wholesale_discount_percent"] == 20
    assert wholesale["total_amount"] < retail["total_amount"]

    # Historical accuracy: editing the product must not change old invoices.
    owner.patch(f"/products/{product['id']}", json={"price": original_price + 500, "wholesale_discount_percent": 50})
    after = staff.get(f"/invoices/{wholesale['id']}").json()
    print("historic item price after product edit:", after["items"][0]["unit_price"])
    assert abs(after["items"][0]["unit_price"] - original_price * 0.8) < 0.01

    # POS checkout preserves mode and applied price.
    pos = staff.post("/pos/checkout", json={
        "customer_id": None, "pricing_mode": "wholesale",
        "items": [{"product_id": product["id"], "quantity": 1}], "method": "cash",
    })
    print("POS checkout:", pos.status_code)
    d = pos.json()
    assert d["invoice"]["pricing_mode"] == "wholesale"
    assert d["invoice"]["items"][0]["wholesale_discount_percent"] == 50

    # Drafts keep their mode.
    draft = staff.post("/invoices", json={**base, "pricing_mode": "wholesale", "status": "draft"}).json()
    reopened = staff.get(f"/invoices/{draft['id']}").json()
    print("draft mode:", reopened["pricing_mode"])
    assert reopened["pricing_mode"] == "wholesale"

    bad = owner.patch(f"/products/{product['id']}", json={"wholesale_discount_percent": 120})
    print("invalid discount:", bad.status_code)
    assert bad.status_code == 422

    print("All wholesale checks passed.")


if __name__ == "__main__":
    main()
