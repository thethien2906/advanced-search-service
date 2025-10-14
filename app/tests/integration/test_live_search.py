# /app/tests/integration/test_live_search.py

import pytest
from unittest.mock import patch
from app.services.search_service import SearchService

# --- Integration Test ---
# Test này sẽ kết nối đến DB thật để kiểm tra dữ liệu.
# Chúng ta vẫn patch SentenceTransformer để tránh phải load model AI nặng nề khi chạy test.
@patch('app.services.search_service.SentenceTransformer')
def test_search_for_ca_kho_and_check_null_fields(MockSentenceTransformer):
    """
    Test này thực hiện các bước sau:
    1. Khởi tạo SearchService để kết nối DB thật.
    2. Chạy tìm kiếm với query "Cá khô".
    3. Lấy sản phẩm đầu tiên trong kết quả.
    4. Kiểm tra và liệt kê tất cả các trường có giá trị là None (null).
    """
    # 1. Thiết lập Mock cho Model AI
    # ------------------------------------
    # Giả lập SentenceTransformer, không cần nó làm gì phức tạp
    MockSentenceTransformer.return_value.encode.return_value = [0.1] * 768

    # 2. Khởi tạo SearchService (sẽ dùng kết nối DB thật)
    # ------------------------------------
    print("\n--- Khởi tạo SearchService với kết nối DB thật ---")
    search_service = SearchService()

    # 3. Gọi hàm search với query cụ thể
    # ------------------------------------
    query = "Cá khô"
    print(f"--- Thực hiện tìm kiếm cho query: '{query}' ---")
    results = search_service.search_semantic(query, limit=1)

    # 4. Phân tích kết quả
    # ------------------------------------
    # Đảm bảo rằng có ít nhất một kết quả trả về để phân tích
    assert results is not None, "Hàm search không được trả về None"
    assert isinstance(results, list), "Kết quả trả về phải là một list"
    assert len(results) > 0, f"Không tìm thấy sản phẩm nào cho query '{query}'"

    first_product = results[0]
    print(f"\n--- Phân tích sản phẩm đầu tiên tìm thấy: '{first_product}' ---")

    null_fields = []
    expected_keys = [
        "id", "name", "rating", "review_count", "sale_count", "category_names",
        "product_images", "price", "store_status", "is_certified", "relevance_score",
        "province_name", "region_name", "sub_region_name", "createdAt"
    ]

    # Duyệt qua tất cả các trường mong đợi và kiểm tra giá trị
    for key in expected_keys:
        # Kiểm tra xem key có tồn tại trong sản phẩm không
        if key not in first_product:
            null_fields.append(f"{key} (trường bị thiếu)")
        # Kiểm tra xem giá trị của key có phải là None không
        elif first_product[key] is None:
            null_fields.append(key)

    # 5. Báo cáo kết quả
    # ------------------------------------
    if not null_fields:
        print("\n✅ TUYỆT VỜI! Tất cả các trường trong sản phẩm đều có giá trị.")
    else:
        print(f"\n⚠️ CẢNH BÁO: Đã tìm thấy {len(null_fields)} trường bị null hoặc thiếu trong sản phẩm đầu tiên:")
        for field in null_fields:
            print(f"  - {field}")

    # Test sẽ thất bại nếu có bất kỳ trường nào bị null, để bạn chú ý sửa lỗi
    assert not null_fields, "Đã tìm thấy các trường bị null, vui lòng kiểm tra lại câu truy vấn SQL hoặc dữ liệu."