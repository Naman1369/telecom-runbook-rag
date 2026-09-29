from app.embeddings import EmbeddingCache, LocalHashEmbedder, cosine_similarity
from app.vectorstore import VectorStore, read_catalog


def test_ingestion_indexes_every_chunk(indexed):
    settings, _, store, report = indexed
    assert report.validation_errors == []
    assert report.indexed == report.chunks > 40
    catalog = read_catalog(settings)
    versions = {(p["product"], v["version"]) for p in catalog["products"] for v in p["versions"]}
    assert versions == {("AX-9000", "7.4"), ("AX-9000", "8.1"), ("HX-5G-gNB", "22.3"), ("HX-5G-gNB", "23.1")}


def test_version_filter_is_a_hard_filter(indexed):
    _, embedder, store, _ = indexed
    qvec = embedder.embed_query("reset bgp neighbor soft")  # 8.1 wording
    where = VectorStore.build_filter(product="AX-9000", version="7.4")
    results = store.query(qvec, 10, where)
    assert results
    assert all(r.metadata["version"] == "7.4" for r in results)


def test_retrieval_finds_the_right_procedure(indexed):
    _, embedder, store, _ = indexed
    qvec = embedder.embed_query("hxcli transport ng-c reset AMF NG link down")
    results = store.query(qvec, 3, VectorStore.build_filter(product="HX-5G-gNB", version="23.1"))
    assert results[0].metadata["section"].startswith("RN-203")
    assert -1.0 <= results[0].score <= 1.0


def test_build_filter_shapes():
    assert VectorStore.build_filter() is None
    assert VectorStore.build_filter(version="8.1") == {"version": "8.1"}
    combined = VectorStore.build_filter(version="8.1", product="AX-9000", doc_types=["runbook"])
    assert combined == {"$and": [{"product": "AX-9000"}, {"version": "8.1"}, {"doc_type": {"$in": ["runbook"]}}]}


def test_local_embedder_ranks_related_text_higher():
    e = LocalHashEmbedder(256)
    a, r, u = e.embed_documents(["bgp peer down hold timer", "bgp peer flapping hold timer expired", "vswr antenna jumper"])
    assert cosine_similarity(a, r) > cosine_similarity(a, u)


def test_embedding_cache_round_trip(tmp_path):
    path = tmp_path / "cache.jsonl"
    cache = EmbeddingCache(path)
    key = EmbeddingCache.key("m", 3, "RETRIEVAL_DOCUMENT", "hello")
    cache.put_many({key: [0.1, 0.2, 0.3]})
    assert EmbeddingCache(path).get(key) == [0.1, 0.2, 0.3]
