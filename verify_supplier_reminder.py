"""End-to-end verification of supplier-specific product selection reminders."""

import httpx

B = "http://localhost:8000/api/v1"


def main():
    c = httpx.Client(base_url=B, timeout=30)
    c.headers["Authorization"] = "Bearer " + c.post(
        "/auth/login", json={"email": "demo@billingapp.com", "password": "Demo@1234"}
    ).json()["access_token"]

    products = c.get("/products?page_size=4").json()["items"]
    p1, p2 = products[0], products[1]
    c.patch(f"/products/{p1['id']}", json={"unit": "boxes"})
    a = c.post("/suppliers", json={"name": "Reminder Supplier A", "category": "Test A"}).json()
    b = c.post("/suppliers", json={"name": "Reminder Supplier B", "category": "Test B"}).json()
    c.post(f"/suppliers/{a['id']}/products", json={"product_id": p1["id"], "supplier_price": 100})
    c.post(f"/suppliers/{b['id']}/products", json={"product_id": p2["id"]})

    linked = c.get(f"/suppliers/{a['id']}/products").json()
    ids = [x.get("product_id") for x in linked]
    print("A linked ids:", ids, "names:", [x.get("product_name") for x in linked],
          "unit:", [x.get("unit") for x in linked])
    assert ids == [p1["id"]] and linked[0]["unit"] == "boxes"

    stock_before = float(c.get(f"/products/{p1['id']}").json()["stock"])
    saved = c.post(f"/suppliers/{a['id']}/reminders/quick-save", json={
        "title": "Weekly restock",
        "items": [{"product_id": p1["id"], "quantity": 7}],
    })
    print("quick-save:", saved.status_code, saved.text[:200])
    assert saved.status_code in (200, 201)
    lst = saved.json()
    item = lst["items"][0]
    print("saved item:", item["quantity"], item["unit"])
    assert item["quantity"] == 7 and item["unit"] == "boxes"
    assert float(c.get(f"/products/{p1['id']}").json()["stock"]) == stock_before

    bad = c.post(f"/suppliers/reminders/{lst['id']}/items", json={
        "product_id": p2["id"], "name": p2["name"], "quantity": 1,
    })
    print("unrelated product rejected:", bad.status_code)
    assert bad.status_code in (400, 404, 422)

    dup = c.post(f"/suppliers/reminders/{lst['id']}/items", json={
        "product_id": p1["id"], "name": p1["name"], "quantity": 99,
    })
    print("duplicate:", dup.status_code, dup.json().get("quantity"))
    assert dup.status_code == 200 and dup.json()["id"] == item["id"] and dup.json()["quantity"] == 7

    c.patch(f"/suppliers/reminders/{lst['id']}/items/{item['id']}", json={"is_purchased": True})
    assert float(c.get(f"/products/{p1['id']}").json()["stock"]) == stock_before

    pending = c.post(f"/suppliers/{a['id']}/reminders/quick-save", json={
        "title": "Pending visit", "items": [{"product_id": p1["id"], "quantity": 3}],
    }).json()
    carried = c.post(f"/suppliers/reminders/{pending['id']}/carry-forward", json={})
    print("carry-forward:", carried.status_code, carried.json().get("title"))
    assert carried.status_code in (200, 201)

    assert c.delete(f"/suppliers/reminders/{pending['id']}").status_code in (200, 204)
    print("All supplier reminder checks passed.")


if __name__ == "__main__":
    main()
