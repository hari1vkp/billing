"""End-to-end verification of the general-purpose supplier module."""

import httpx

B = "http://localhost:8000/api/v1"


def main():
    c = httpx.Client(base_url=B, timeout=30)
    c.headers["Authorization"] = "Bearer " + c.post(
        "/auth/login", json={"email": "demo@billingapp.com", "password": "Demo@1234"}
    ).json()["access_token"]

    a = c.post("/suppliers", json={
        "name": "ABC Textile Supplier", "contact_person": "Ramesh", "phone": "9876500001",
        "whatsapp": "9876500001", "email": "abc@example.com", "address": "Market Road",
        "category": "Textile Supplier", "brands": "Shirts, Trousers, Fabrics",
        "notes": "Visit on Tuesdays",
    })
    b = c.post("/suppliers", json={
        "name": "Electronics Distributor", "category": "Electronics Distributor",
        "brands": "Fans, Switches, Cables",
    })
    print("create suppliers:", a.status_code, b.status_code)
    assert a.status_code == 201 and b.status_code == 201
    sa, sb = a.json(), b.json()

    cats = c.get("/suppliers/categories").json()
    print("categories:", cats)
    assert any("Textile Supplier" in str(x) for x in cats.get("categories", cats.get("items", [])))

    product = c.get("/products?page_size=3").json()["items"][0]
    for supplier in (sa, sb):
        r = c.post(f"/suppliers/{supplier['id']}/products", json={
            "product_id": product["id"], "supplier_sku": "SKU-" + supplier["id"][:4],
            "supplier_price": 123.45,
        })
        print("link product:", supplier["name"], r.status_code)
        assert r.status_code in (200, 201)

    stock_before = float(c.get(f"/products/{product['id']}").json()["stock"])
    lst = c.post(f"/suppliers/{sa['id']}/reminders", json={"title": "Next visit", "notes": "Sample"})
    print("reminder list:", lst.status_code)
    assert lst.status_code in (200, 201)
    lid = lst.json()["id"]

    item1 = c.post(f"/suppliers/reminders/{lid}/items", json={
        "product_id": product["id"], "name": product["name"], "quantity": 10,
        "unit": "boxes", "expected_price": 100,
    })
    item2 = c.post(f"/suppliers/reminders/{lid}/items", json={
        "name": "Handmade Wooden Shelf", "quantity": 3, "unit": "pcs", "notes": "custom item",
    })
    print("reminder items:", item1.status_code, item2.status_code)
    assert item1.status_code in (200, 201) and item2.status_code in (200, 201)
    assert c.patch(f"/suppliers/reminders/{lid}/items/{item1.json()['id']}", json={"is_purchased": True}).status_code == 200
    stock_after_tick = float(c.get(f"/products/{product['id']}").json()["stock"])
    print("stock after marking purchased:", stock_before, "->", stock_after_tick)
    assert stock_after_tick == stock_before

    conv = c.post(f"/suppliers/reminders/{lid}/convert-to-purchase", json={"notes": "Converted"})
    print("convert:", conv.status_code, conv.text[:200])
    assert conv.status_code in (200, 201)
    stock_after_convert = float(c.get(f"/products/{product['id']}").json()["stock"])
    print("stock after convert:", stock_after_convert)
    assert stock_after_convert > stock_before

    movements = c.get(f"/inventory/movements?product_id={product['id']}").json()["items"]
    purchase = [m for m in movements if m["reason"] == "purchase"]
    print("purchase movements:", len(purchase), purchase[0]["reference"] if purchase else None)
    assert purchase

    visit = c.post(f"/suppliers/{sa['id']}/visits", json={
        "visit_date": "2026-11-20", "discussion_notes": "Discussed rates",
        "items_discussed": "Shirts", "items_requested": "Trousers", "follow_up": "Call Friday",
        "next_visit_date": "2026-11-27",
    })
    print("visit:", visit.status_code)
    assert visit.status_code in (200, 201)

    assert c.delete(f"/suppliers/{sb['id']}").status_code in (200, 204)
    print("All supplier checks passed.")


if __name__ == "__main__":
    main()
