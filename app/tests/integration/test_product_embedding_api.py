# /app/tests/integration/test_product_embedding_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
import numpy as np

client = TestClient(app)

# The expected dimension of the embedding vector from the model
EXPECTED_EMBEDDING_DIMENSION = 768

def test_get_enhanced_embedding_with_full_data():
    """
    Tests the /embeddings endpoint with a complete, valid request.
    It verifies the status code, response structure, and embedding dimension.
    """
    response = client.post(
        "/embeddings",
        json={
            "product_name": "Mật ong rừng U Minh Hạ",
            "product_description": "Mật ong tự nhiên thu hoạch từ hoa tràm trong rừng U Minh, có màu vàng sẫm và hương thơm đặc trưng.",
            "product_category": "Thực phẩm",
            "product_story_title": "Hương vị từ trái tim rừng tràm",
            "product_made_by": "Ong hút mật hoa tràm",
            "product_type_name": "Sản phẩm tự nhiên"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "embedding" in data
    assert isinstance(data["embedding"], list)
    assert len(data["embedding"]) == EXPECTED_EMBEDDING_DIMENSION

def test_embedding_is_normalized():
    """
    Tests if the returned embedding vector is properly L2-normalized (has a magnitude of 1).
    """
    response = client.post(
        "/embeddings",
        json={
            "product_name": "Cà phê Robusta rang mộc",
            "product_description": "Hạt cà phê Robusta từ vùng Cầu Đất, Đà Lạt."
        }
    )
    assert response.status_code == 200
    embedding = np.array(response.json()["embedding"])
    # The norm of a normalized vector should be very close to 1.0
    norm = np.linalg.norm(embedding)
    assert np.isclose(norm, 1.0), f"Vector norm is {norm}, expected 1.0"

def test_get_embedding_with_only_required_fields():
    """
    Tests that the endpoint works correctly when only the mandatory fields
    (product_name and product_description) are provided.
    """
    response = client.post(
        "/embeddings",
        json={
            "product_name": "Lụa tơ tằm Vạn Phúc",
            "product_description": "Khăn choàng lụa tơ tằm 100% từ làng lụa Vạn Phúc, mềm mại và óng ả."
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "embedding" in data
    assert len(data["embedding"]) == EXPECTED_EMBEDDING_DIMENSION

def test_get_embedding_missing_required_field_returns_422():
    """
    Tests that the endpoint returns a 422 Unprocessable Entity error if a required
    field (e.g., product_description) is missing from the request.
    """
    response = client.post(
        "/embeddings",
        json={
            "product_name": "Trà sen Tây Hồ"
            # product_description is intentionally omitted
        }
    )
    assert response.status_code == 422