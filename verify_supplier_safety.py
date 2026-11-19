"""End-to-end verification of supplier status, dedupe and history safety."""

import httpx

B = "http://localhost:8000/api/v1"


def main():
    c = httpx.Client(base_url=B, timeout=30)
    c.headers["Authorization"] = "Bearer " + c.post(
        "/auth/login", json={"email": "demo@billingapp.com", "password": "Demo@1234"}
    ).json()["access_token"]

    product = c.get("/products?page_size=2").json()["items"][0]
    supplier = c.post("/suppliers", json={"name": "Safety Check Vendor"}).json()
    sid = supplier["id"]

    active = c.get("/suppliers?is_active=true&page_size=200").json()["items"]
    assert any(s["id"] == sid for s in active)
    print("active list contains new supplier:", True)

    link1 = c.post(f"/suppliers/{sid}/products", json={"product_id": product["id"]})
    dup = c.post(f"/suppliers/{sid}/products", json={"product_id": product["id"]})
    print("duplicate link:", dup.status_code, dup.text[:90])
    assert link1.status_code == 201 and dup.status_code == 400
    custom = c.post(f"/suppliers/{sid}/products", json={"custom_name": "Local handmade item"})
    print("custom item still allowed:", custom.status_code)
    assert custom.status_code == 201

    lst = c.post(f"/suppliers/{sid}/reminders/quick-save", json={
        "title": "Safety visit", "items": [{"product_id": product["id"], "quantity": 4}],
    }).json()
    item = lst["items"][0]
    c.delete(f"/suppliers/{sid}/products/{link1.json()['id']}")
    patched = c.patch(f"/suppliers/reminders/{lst['id']}/items/{item['id']}", json={"quantity": 9})
    print("historical reminder edit after unlink:", patched.status_code, patched.json().get("quantity"))
    assert patched.status_code == 200 and patched.json()["quantity"] == 9

    other = c.get("/products?page_size=3").json()["items"][2]
    new_item = c.post(f"/suppliers/reminders/{lst['id']}/items", json={
        "product_id": other["id"], "name": other["name"], "quantity": 1,
    })
    print("new item after unlink rejected:", new_item.status_code)
    assert new_item.status_code == 422

    assert c.delete(f"/suppliers/{sid}").status_code == 200
    inactive = c.get("/suppliers?is_active=false&page_size=200").json()["items"]
    assert any(s["id"] == sid for s in inactive)
    active_after = c.get("/suppliers?is_active=true&page_size=200").json()["items"]
    assert not any(s["id"] == sid for s in active_after)
    detail = c.get(f"/suppliers/{sid}").json()
    print("history preserved:", len(detail["products"]), len(detail["reminder_lists"]))
    assert detail["is_active"] is False and len(detail["reminder_lists"]) >= 1

    assert c.patch(f"/suppliers/{sid}", json={"is_active": True}).status_code == 200
    active_again = c.get("/suppliers?is_active=true&page_size=200").json()["items"]
    assert any(s["id"] == sid for s in active_again)
    print("reactivated:", True)
    print("All supplier safety checks passed.")


if __name__ == "__main__":
    main()
