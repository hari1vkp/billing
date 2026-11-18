"""End-to-end verification of the AI catalogue onboarding workflow.

Run with the backend and frontend dev server up:
    backend/.venv/bin/python verify_ai_catalogue.py
"""

import csv
import io
import time

import httpx

BASE = "http://localhost:8000/api/v1"
HEADER = (
    "Product Name,Brand,Category,Subcategory,Variant,Size / Pack Size,Barcode,"
    "Barcode Type,SKU,Purchase Price,Selling Price,Discount Type,Discount Value,"
    "Opening Stock"
)


def main():
    c = httpx.Client(base_url=BASE, timeout=30)
    token = c.post(
        "/auth/login", json={"email": "demo@billingapp.com", "password": "Demo@1234"}
    ).json()["access_token"]
    c.headers["Authorization"] = "Bearer " + token

    cats = c.get("/products/ai/categories").json()["categories"]
    print("categories:", len(cats), [x["id"] for x in cats][:4])
    assert len(cats) >= 9

    prompt = c.post(
        "/products/ai/prompt", json={"category_id": "grocery", "business_name": "Test Kirana"}
    ).json()["prompt"]
    print("prompt chars:", len(prompt), "has header:", HEADER in prompt)
    assert len(prompt) > 1000 and HEADER in prompt

    template = c.get("/products/import/template").text.splitlines()
    print("template header ok:", template[0] == HEADER, "lines:", len(template))
    assert template[0] == HEADER

    suffix = str(int(time.time()))[-6:]
    manufacturer = "890" + suffix + "1234"
    rows = [
        [
            f"Test Atta {suffix}", "Aashirvaad", "Staples", "Flour", "Whole Wheat", "5 kg",
            manufacturer, "manufacturer", f"MFG-{suffix}", "180", "240", "percent", "5", "12",
        ],
        [
            f"Test Cotton Tee {suffix}", "Generic", "Clothing", "T-Shirts", "Red", "M",
            "", "internal", "", "150", "299", "flat", "20", "8",
        ],
        [
            f"Duplicate {suffix}", "X", "Staples", "", "", "", manufacturer,
            "manufacturer", "", "10", "20", "none", "0", "3",
        ],
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADER.split(","))
    writer.writerows(rows)
    content = buf.getvalue().encode()

    parsed = c.post(
        "/products/import/parse", files={"file": ("catalogue.csv", content, "text/csv")}
    ).json()
    print("parsed rows:", len(parsed["rows"]), "errors:", parsed["error_count"])
    for r in parsed["rows"]:
        print(" ", r["name"][:24], r["barcode_type"], r["barcode"], r["valid"], r["errors"][:1])
    assert len(parsed["rows"]) == 3

    valid = [r for r in parsed["rows"] if r["valid"]]
    payload = [
        {
            "name": r["name"], "brand": r.get("brand"), "category": r.get("category"),
            "subcategory": r.get("subcategory"), "variant": r.get("variant"),
            "size_pack": r.get("size_pack"), "barcode": r.get("barcode"),
            "barcode_type": r.get("barcode_type"), "sku": r.get("sku"),
            "cost_price": r.get("cost_price"), "selling_price": r.get("selling_price"),
            "discount_type": r.get("discount_type"), "discount_value": r.get("discount_value"),
            "quantity": r.get("quantity"), "gst_rate": r.get("gst_rate", 18),
        }
        for r in valid
    ]
    committed = c.post("/products/import/commit", json={"rows": payload}).json()
    print("commit:", committed)
    assert committed["created"] == 2

    products = c.get(f"/products?query={suffix}").json()["items"]
    created = [p for p in products if suffix in p["name"]]
    print("created products:", [(p["name"][:24], p["barcode"], p["barcode_type"] if "barcode_type" in p else "n/a", p["stock"]) for p in created])
    internal = [p for p in created if p["barcode"] and p["barcode"].startswith("BF")]
    assert internal, "no internal barcode generated"
    pos = c.get(f"/products/barcode/{internal[0]['barcode']}")
    print("POS lookup internal barcode:", pos.status_code)
    assert pos.status_code == 200

    ids = ",".join(p["id"] for p in created)
    labels = c.get(f"/products/barcodes/labels?ids={ids}")
    print("labels:", labels.status_code, labels.content[:4])
    assert labels.status_code == 200 and labels.content.startswith(b"%PDF")

    print("\nAll AI catalogue checks passed.")


if __name__ == "__main__":
    main()
