import uuid
from typing import List, Dict, Any

class SearchService:
    """
    Handles the business logic for searching products.
    In Phase 2, this service returns hardcoded mock data.
    """
    def __init__(self):
        # This list of fake products acts as our mock database.
        self._fake_products: List[Dict[str, Any]] = [
            {
                "id": uuid.uuid4(),
                "name": "Mật ong rừng U Minh hạ",
                "price": 280000,
                "rating": 4.9,
                "review_count": 256,
                "sale_count": 890,
                "store_status": "Approved",
                "is_certified": True,
                "product_images": ["https://example.com/images/mat_ong_1.jpg", "https://example.com/images/mat_ong_2.jpg"],
                "relevance_score": 0.95
            },
            {
                "id": uuid.uuid4(),
                "name": "Bánh tráng phơi sương Trảng Bàng",
                "price": 75000,
                "rating": 4.7,
                "review_count": 412,
                "sale_count": 1500,
                "store_status": "Approved",
                "is_certified": False,
                "product_images": ["https://example.com/images/banh_trang_1.jpg"],
                "relevance_score": 0.87
            },
            {
                "id": uuid.uuid4(),
                "name": "Gốm sứ Bát Tràng cao cấp",
                "price": 550000,
                "rating": 4.8,
                "review_count": 88,
                "sale_count": 210,
                "store_status": "Approved",
                "is_certified": True,
                "product_images": ["https://example.com/images/gom_su_1.jpg"],
                "relevance_score": 0.76
            }
        ]

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Performs a search for products. For now, it just returns
        a slice of the hardcoded data based on the limit.
        """
        print(f"Searching for '{query}' with a limit of {limit}...")
        return self._fake_products[:limit]