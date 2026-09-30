from app.vectorstore import read_catalog, write_catalog


def test_same_product_name_keeps_vendor_documents_separate(settings):
    catalog = write_catalog([
        dict(vendor="B", product="Router", version="1", title="B instructions"),
        dict(vendor="A", product="Router", version="1", title="A instructions"),
        dict(vendor="A", product="Router", version="1", title="A instructions"),
    ], settings)
    assert [p["vendor"] for p in catalog["products"]] == ["A", "B"]
    assert catalog["products"][0]["versions"] == [
        dict(version="1", documents=["A instructions"], chunks=2)
    ]
    assert catalog["products"][1]["versions"] == [
        dict(version="1", documents=["B instructions"], chunks=1)
    ]
    assert read_catalog(settings) == catalog
