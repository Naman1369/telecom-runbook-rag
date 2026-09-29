import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.rag import QueryError, QueryRequest, RAGPipeline, build_history, detect_release, retrieval_text
from tests.conftest import FakeLLM

GOOD_ANSWER = {
    "answer_found": True,
    "summary": "Reset the NG-C link.",
    "steps": [
        {"instruction": "Check NG-C status", "command": "hxcli transport ng-c status", "sources": ["S1"]},
        {"instruction": "Invented step", "command": "hxcli make-it-work", "sources": ["S9"]},
    ],
    "warnings": ["Raise a transport incident if ping fails [S1]"],
    "sources_used": ["S1", "S9"],
}


def _pipeline(indexed, answer=GOOD_ANSWER, **overrides):
    settings, embedder, store, _ = indexed
    settings = dataclasses.replace(settings, **overrides)
    llm = FakeLLM(answer)
    return RAGPipeline(embedder, store, llm, settings), llm


def test_answer_keeps_only_grounded_citations(indexed):
    rag, llm = _pipeline(indexed)
    result = rag.answer(QueryRequest("NG link to AMF down, how to reset?", product="HX-5G-gNB", version="23.1"))
    assert result["status"] == "answered"
    assert [s["command"] for s in result["steps"]] == ["hxcli transport ng-c status"]  # S9 step dropped
    assert len(result["citations"]) == 1
    cite = result["citations"][0]
    assert cite["version"] == "23.1" and cite["line_start"] > 0 and cite["snippet"]
    assert result["warnings"][0] == {"text": "Raise a transport incident if ping fails", "citations": [1]}
    assert "23.1" in llm.calls[0]["system"]
    assert "[S1]" in llm.calls[0]["prompt"]


def test_no_relevant_chunks_returns_not_found_without_calling_llm(indexed):
    rag, llm = _pipeline(indexed, relevance_threshold=0.99)
    result = rag.answer(QueryRequest("How do I configure segment routing?", product="AX-9000", version="8.1"))
    assert result["status"] == "not_found"
    assert result["citations"] == [] and result["steps"] == []
    assert llm.calls == []


def test_model_saying_not_found_is_respected(indexed):
    rag, _ = _pipeline(indexed, answer={"answer_found": False, "summary": "Not covered.", "steps": [],
                                         "warnings": [], "sources_used": []})
    result = rag.answer(QueryRequest("cell down battery replacement", product="HX-5G-gNB", version="22.3"))
    assert result["status"] == "not_found"
    assert result["summary"] == "Not covered."


def test_version_is_detected_from_question(indexed):
    rag, _ = _pipeline(indexed)
    result = rag.answer(QueryRequest("On AuroraOS 8.1 how do I reset a BGP neighbor?", product="AX-9000"))
    assert result["version"] == "8.1" and result["version_detected"] is True


def test_unknown_version_is_rejected(indexed):
    rag, _ = _pipeline(indexed)
    with pytest.raises(QueryError):
        rag.answer(QueryRequest("anything", product="AX-9000", version="9.9"))
    with pytest.raises(QueryError):
        rag.answer(QueryRequest("bgp reset please", product="AX-9000"))


def test_detect_release_requires_unique_match():
    catalog = {"products": [
        {"vendor": "a", "product": "AX", "versions": [{"version": "7.4"}, {"version": "8.1"}]},
        {"vendor": "h", "product": "HX", "versions": [{"version": "22.3"}]},
    ]}
    assert detect_release("problem on 8.1 router", catalog) == ("AX", "8.1")
    assert detect_release("upgrade from 7.4 to 8.1", catalog) is None
    assert detect_release("version 18.1 is weird", catalog) is None


def test_history_is_trimmed_and_follow_ups_expand_retrieval():
    history = [{"role": "user", "content": f"question {i} " + "x " * 50} for i in range(10)]
    block = build_history(history, max_tokens=200)
    assert "Earlier in this incident" in block
    req = QueryRequest("what if that fails?", history=[{"role": "user", "content": "BGP peer down"}])
    assert retrieval_text(req) == "BGP peer down\nwhat if that fails?"


def test_api_endpoints(indexed, monkeypatch):
    from app import main

    rag, _ = _pipeline(indexed)
    monkeypatch.setattr(main, "get_pipeline", lambda: rag)
    monkeypatch.setattr(main, "read_catalog", lambda: {"products": [{"product": "HX-5G-gNB"}]})
    client = TestClient(main.app)

    assert client.get("/api/catalog").json()["products"][0]["product"] == "HX-5G-gNB"
    ok = client.post("/api/query", json={"question": "NG link down", "product": "HX-5G-gNB", "version": "23.1"})
    assert ok.status_code == 200 and ok.json()["status"] == "answered"
    bad = client.post("/api/query", json={"question": "NG link down", "product": "HX-5G-gNB", "version": "1.0"})
    assert bad.status_code == 400
    assert client.post("/api/query", json={"question": ""}).status_code == 422
    assert client.get("/").status_code == 200
