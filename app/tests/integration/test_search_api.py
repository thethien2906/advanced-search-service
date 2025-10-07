# tests/integration/test_search_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_search_endpoint_returns_results():
    """Test that search returns semantically relevant products"""
    response = client.post(
        "/search",
        json={
            "query_text": "mật ong",
            "limit": 10
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "query" in data
    assert "total_results" in data
    assert "results" in data
    assert "processing_time_ms" in data

    # Verify we got results
    assert data["total_results"] > 0
    assert len(data["results"]) > 0

    # Verify product structure
    first_product = data["results"][0]
    assert "id" in first_product
    assert "name" in first_product
    assert "relevance_score" in first_product

    # Verify business features are present
    assert "rating" in first_product
    assert "review_count" in first_product
    assert "sale_count" in first_product
    assert "store_status" in first_product
    assert "is_certified" in first_product

    print(f"✅ Search returned {data['total_results']} results in {data['processing_time_ms']}ms")

def test_semantic_similarity():
    """Test that semantically similar queries return relevant results"""
    # Search for honey in Vietnamese
    response = client.post("/search", json={"query_text": "mật ong rừng"})
    assert response.status_code == 200

    results = response.json()["results"]
    # The top result should contain "mật ong" in the name
    assert any("mật ong" in r["name"].lower() for r in results[:3])

def test_only_approved_stores():
    """Verify only products from approved stores are returned"""
    response = client.post("/search", json={"query_text": "bánh"})
    assert response.status_code == 200

    results = response.json()["results"]
    for product in results:
        assert product["store_status"] == "Approved"

def test_relevance_score_ordering():
    """Verify results are ordered by relevance"""
    response = client.post("/search", json={"query_text": "nước mắm"})
    assert response.status_code == 200

    results = response.json()["results"]
    scores = [r["relevance_score"] for r in results]

    # Scores should be in descending order
    assert scores == sorted(scores, reverse=True)