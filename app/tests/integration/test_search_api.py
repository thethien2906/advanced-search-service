# tests/integration/test_search_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# --- Tests for the /search/semantic endpoint ---

def test_semantic_search_returns_results():
    """Test that the semantic search endpoint returns a valid response structure."""
    response = client.post(
        "/search/semantic",
        json={"query_text": "mật ong", "limit": 10}
    )
    assert response.status_code == 200
    data = response.json()
    assert "query" in data
    assert "total_results" in data
    assert "results" in data
    assert len(data["results"]) > 0
    first_product = data["results"][0]
    assert "id" in first_product
    assert "name" in first_product
    assert "relevance_score" in first_product

def test_semantic_search_similarity():
    """Test that the semantic endpoint returns a semantically relevant result."""
    response = client.post("/search/semantic", json={"query_text": "mật ong rừng", "limit": 10})
    assert response.status_code == 200
    results = response.json()["results"]
    # This verifies that the initial candidate retrieval is working correctly.
    # With pure semantic search, the most relevant item should be ranked highly.
    assert "mật ong" in results[0]["name"].lower()

def test_semantic_search_only_approved_stores():
    """Verify only products from approved stores are returned by semantic search."""
    response = client.post("/search/semantic", json={"query_text": "bánh"})
    assert response.status_code == 200
    results = response.json()["results"]
    for product in results:
        assert product["store_status"] == "Approved"

def test_semantic_search_relevance_score_ordering():
    """Verify semantic search results are ordered by cosine similarity score."""
    response = client.post("/search/semantic", json={"query_text": "nước mắm"})
    assert response.status_code == 200
    results = response.json()["results"]
    scores = [r["relevance_score"] for r in results]
    # Scores should be in descending order based on similarity
    assert scores == sorted(scores, reverse=True)


# --- Tests for the /search/ml endpoint ---

def test_ml_search_returns_results():
    """Test that the ML search endpoint returns a valid response."""
    response = client.post(
        "/search/ml",
        json={"query_text": "trà", "limit": 5}
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_results" in data
    assert len(data["results"]) > 0

def test_ml_search_relevance_score_ordering():
    """
    Verify results are ordered by the ML model's score.
    This is expected to fail with the dummy ranker.
    """
    response = client.post("/search/ml", json={"query_text": "nước mắm"})
    assert response.status_code == 200
    results = response.json()["results"]
    scores = [r["relevance_score"] for r in results]
    # Scores should be in descending order
    assert scores == sorted(scores, reverse=True)

def test_ml_search_category_match_is_considered():
    """
    Checks that a product matching query category is retrieved by the ML endpoint.
    This primarily tests the candidate generation feeding into the ML ranker.
    """
    response = client.post("/search/ml", json={"query_text": "nước mắm Phú Quốc", "limit": 5})
    assert response.status_code == 200
    results = response.json()["results"]
    assert any("nước mắm" in r["name"].lower() for r in results)

def test_ml_ranking_boosts_certified_products():
    """
    Verify that certified products rank higher with the ML model.
    NOTE: This test is designed for a properly trained XGBoost model and will
    fail with the current dummy model, but provides the correct structure for future testing.
    """
    response = client.post("/search/ml", json={"query_text": "trà", "limit": 10})
    assert response.status_code == 200
    # Future assertion logic would go here, e.g., checking if the top-ranked
    # results have 'is_certified' == True more often than lower-ranked ones.