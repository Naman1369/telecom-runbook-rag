import pytest

from app.embeddings import EmbeddingCache, EmbeddingStats, GeminiEmbedder


def embedder(vectors):
    instance = GeminiEmbedder.__new__(GeminiEmbedder)
    instance.model, instance.dim = "test", 2
    instance.batch_size = 10
    instance.cache = EmbeddingCache(None)
    instance.stats = EmbeddingStats()
    instance._call = lambda texts, task: vectors
    return instance


@pytest.mark.parametrize("vectors", [[], [[1, 0]], [[1, 0]] * 3,
                                    [[1], [0, 1]], [[float("nan"), 0], [0, 1]],
                                    [[float("inf"), 0], [0, 1]]])
def test_invalid_response_is_not_cached_or_counted(vectors):
    instance = embedder(vectors)
    with pytest.raises(ValueError, match="Embedding response"):
        instance.embed_documents(["first", "second"])
    assert instance.cache._data == {}
    assert instance.stats.embedded == 0


def test_valid_response_preserves_duplicate_order_and_cache():
    instance = embedder([[1, 0], [0, 1]])
    assert instance.embed_documents(["first", "second", "first"]) == [[1, 0], [0, 1], [1, 0]]
    instance._call = lambda *_: pytest.fail("cache should avoid another call")
    assert instance.embed_documents(["second", "first"]) == [[0, 1], [1, 0]]
