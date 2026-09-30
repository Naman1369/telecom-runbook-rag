from app.vectorstore import write_catalog


def test_catalog_sorts_mixed_numeric_and_named_releases(settings):
    versions = ["8.10", "rolling", "8.2", "8.rc1", "8.1"]
    catalog = write_catalog([
        dict(vendor="Acme", product="Router", version=v, title="Runbook")
        for v in versions
    ], settings)
    assert [v["version"] for v in catalog["products"][0]["versions"]] == [
        "8.1", "8.2", "8.10", "8.rc1", "rolling"
    ]
