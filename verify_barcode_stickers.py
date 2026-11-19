"""End-to-end verification of the Barcode Sticker Studio."""

import re
import subprocess

import httpx

B = "http://localhost:8000/api/v1"


def pdf_pages(path: str) -> int:
    out = subprocess.check_output(["pdfinfo", path], text=True)
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))


def pdf_size(path: str) -> tuple[float, float]:
    out = subprocess.check_output(["pdfinfo", path], text=True)
    m = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", out)
    return float(m.group(1)), float(m.group(2))


def main():
    c = httpx.Client(base_url=B, timeout=60)
    c.headers["Authorization"] = "Bearer " + c.post(
        "/auth/login", json={"email": "demo@billingapp.com", "password": "Demo@1234"}
    ).json()["access_token"]

    products = c.get("/products?page_size=6").json()["items"]
    p1, p2, p3 = products[0], products[1], products[2]
    known = "8901234567890"
    c.patch(f"/products/{p1['id']}", json={"barcode": known})
    c.patch(f"/products/{p2['id']}", json={"barcode": None})
    before = {p["id"]: (p["stock"], p["price"]) for p in (p1, p2, p3)}

    ensured = c.post("/barcode-stickers/ensure", json={
        "product_ids": [p1["id"], p2["id"], p3["id"]]
    }).json()
    codes = ensured["barcodes"]
    print("ensured:", codes, "generated:", ensured["generated"])
    assert codes[p1["id"]] == known
    assert codes[p2["id"]].startswith("BF") and len(codes[p2["id"]]) == 12
    assert len(set(codes.values())) == 3

    after = c.get("/products?page_size=6").json()["items"]
    for p in after:
        if p["id"] in before:
            assert (p["stock"], p["price"]) == before[p["id"]]

    preview = c.post("/barcode-stickers/preview", json={
        "items": [
            {"product_id": p1["id"], "quantity": 10},
            {"product_id": p2["id"], "quantity": 5},
            {"product_id": p3["id"], "quantity": 20},
        ],
        "size": "small", "layout": "sheet",
    }).json()
    print("preview:", preview["total_stickers"], "stickers,", preview["pages"], "page(s),",
          preview["width_mm"], "x", preview["height_mm"], "mm")
    assert preview["total_stickers"] == 35
    assert preview["width_mm"] == 40 and preview["height_mm"] == 25
    assert known in preview["svg"]

    payload = {
        "items": [
            {"product_id": p1["id"], "quantity": 10},
            {"product_id": p2["id"], "quantity": 5},
            {"product_id": p3["id"], "quantity": 20},
        ],
        "size": "small", "layout": "sheet",
    }
    pdf = c.post("/barcode-stickers/pdf", json=payload)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    open("/tmp/opencode/stickers-sheet.pdf", "wb").write(pdf.content)
    print("sheet pages:", pdf_pages("/tmp/opencode/stickers-sheet.pdf"))
    text = subprocess.check_output(["pdftotext", "/tmp/opencode/stickers-sheet.pdf", "-"], text=True)
    for name, qty in ((p1["name"], 10), (p2["name"], 5), (p3["name"], 20)):
        count = text.count(name)
        print(" ", name[:24], "occurrences:", count, "expected:", qty)
        assert count == qty

    individual = c.post("/barcode-stickers/pdf", json={
        "items": [{"product_id": p1["id"], "quantity": 3}],
        "size": "small", "layout": "individual",
    })
    assert individual.status_code == 200
    open("/tmp/opencode/sticker-individual.pdf", "wb").write(individual.content)
    w_pt, h_pt = pdf_size("/tmp/opencode/sticker-individual.pdf")
    print("individual page pts:", round(w_pt, 2), round(h_pt, 2))
    assert abs(w_pt - 40 * 72 / 25.4) < 1 and abs(h_pt - 25 * 72 / 25.4) < 1
    assert pdf_pages("/tmp/opencode/sticker-individual.pdf") == 3

    print("All barcode sticker checks passed.")


if __name__ == "__main__":
    main()
