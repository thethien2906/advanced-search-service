# /app/tests/unit/test_search_service.py

import pytest
from unittest.mock import patch, MagicMock
from app.services.search_service import SearchService
from datetime import datetime

# --- Dữ liệu giả lập (Mock Data) ---
# Dữ liệu này giả lập những gì database sẽ trả về khi được truy vấn.
# Chúng ta sẽ có 2 sản phẩm liên quan đến "cá" để kiểm tra.
MOCK_DB_RESULTS = [
    (
        "a1b2c3d4-e5f6-7890-1234-567890abcdef", # ID
        "Cá khô chỉ vàng loại 1", # Name
        4.9, # Rating
        150, # ReviewCount
        800, # SaleCount
        ["Đặc sản khô"], # CategoryNames
        ["image1.jpg"], # ProductImages
        150000, # price
        "Approved", # StoreStatus
        True, # IsCertified
        0.1, # distance (giả lập, 1 - 0.1 = 0.9 relevance_score)
        "Phú Quốc", # ProvinceName
        "Đồng bằng sông Cửu Long", # RegionName
        "Đồng bằng sông Cửu Long", # RegionSpecifiedName
        datetime(2023, 10, 26) # CreatedAt
    ),
    (
        "b2c3d4e5-f6a7-8901-2345-67890abcdef1", # ID
        "Khô cá lóc đồng", # Name
        4.7, # Rating
        120, # ReviewCount
        650, # SaleCount
        ["Đặc sản khô"], # CategoryNames
        ["image2.jpg"], # ProductImages
        180000, # price
        "Approved", # StoreStatus
        False, # IsCertified
        0.2, # distance (giả lập, 1 - 0.2 = 0.8 relevance_score)
        "An Giang", # ProvinceName
        "Đồng bằng sông Cửu Long", # RegionName
        "Đồng bằng sông Cửu Long", # RegionSpecifiedName
        datetime(2023, 10, 25) # CreatedAt
    ),
    (
        "c3d4e5f6-a7b8-9012-3456-7890abcdef2", # ID
        "Mật ong rừng nguyên chất", # Name (Không liên quan)
        4.8, # Rating
        200, # ReviewCount
        1000, # SaleCount
        ["Sản phẩm khác"], # CategoryNames
        ["image3.jpg"], # ProductImages
        250000, # price
        "Approved", # StoreStatus
        True, # IsCertified
        0.8, # distance (giả lập, 1 - 0.8 = 0.2 relevance_score)
        "Gia Lai", # ProvinceName
        "Tây Nguyên", # RegionName
        "Tây Nguyên", # RegionSpecifiedName
        datetime(2023, 10, 24) # CreatedAt
    ),
]


# --- Viết Unit Test ---

# @patch được dùng để thay thế các class thật bằng các đối tượng giả lập (MagicMock)
# Điều này giúp chúng ta không cần kết nối DB hay load model thật khi chạy test
@patch('app.services.search_service.XGBoostRanker')
@patch('app.services.search_service.SentenceTransformer')
@patch('app.services.search_service.DatabaseHandler')
def test_search_semantic_for_ca_kho(MockDatabaseHandler, MockSentenceTransformer, MockXGBoostRanker):
    """
    Hàm này sẽ test chức năng search_semantic với query là "Cá khô"
    """
    # 1. Thiết lập các Mock (Giả lập)
    # ------------------------------------
    # Giả lập DatabaseHandler trả về dữ liệu mock của chúng ta
    mock_db_instance = MockDatabaseHandler.return_value
    mock_db_instance.execute_query_with_retry.return_value = MOCK_DB_RESULTS

    # Giả lập SentenceTransformer, không cần nó làm gì cả
    MockSentenceTransformer.return_value.encode.return_value = [0.1] * 768

    # 2. Khởi tạo SearchService (với các thành phần đã được giả lập)
    # ------------------------------------
    search_service = SearchService()
    # Gán lại mock_db_instance để đảm bảo nó được sử dụng
    search_service.db_handler = mock_db_instance

    # 3. Gọi hàm cần test
    # ------------------------------------
    query = "Cá khô"
    results = search_service.search_semantic(query, limit=10)

    # 4. Kiểm tra kết quả (Assertions)
    # ------------------------------------
    # Kiểm tra rằng hàm có trả về kết quả
    assert results is not None
    assert isinstance(results, list)
    assert len(results) > 0

    # Kiểm tra sản phẩm đầu tiên có phải là "Cá khô chỉ vàng loại 1" không
    # vì nó có 'distance' thấp nhất (relevance_score cao nhất)
    first_product = results[0]
    assert first_product['name'] == "Cá khô chỉ vàng loại 1"
    assert first_product['relevance_score'] == pytest.approx(0.9) # 1 - 0.1

    # Kiểm tra sản phẩm thứ hai
    second_product = results[1]
    assert second_product['name'] == "Khô cá lóc đồng"
    assert second_product['relevance_score'] == pytest.approx(0.8) # 1 - 0.2

    # Kiểm tra rằng kết quả được sắp xếp đúng theo relevance_score giảm dần
    scores = [p['relevance_score'] for p in results]
    assert scores == sorted(scores, reverse=True)

    # Kiểm tra xem tất cả các key cần thiết có trong kết quả không
    expected_keys = [
        "id", "name", "rating", "review_count", "sale_count", "category_names",
        "product_images", "price", "store_status", "is_certified", "relevance_score",
        "province_name", "region_name", "sub_region_name", "createdAt"
    ]
    for product in results:
        for key in expected_keys:
            assert key in product

    print(f"\n✅ Test cho query '{query}' đã thành công!")
    print(f"Tìm thấy {len(results)} sản phẩm.")
    print(f"Sản phẩm top 1: '{first_product['name']}' với điểm liên quan là {first_product['relevance_score']:.2f}")