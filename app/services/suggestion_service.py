# /app/services/suggestion_service.py
from typing import List, Dict, Any
from app.core.config import settings
from app.services.database import DatabaseHandler

class SuggestionService:
    """
    Xử lý logic nghiệp vụ cho việc gợi ý các truy vấn tìm kiếm.
    """
    def __init__(self):
        self.db_handler = DatabaseHandler(settings.DATABASE_URL)

    def get_suggestions(self, prefix: str, limit: int = 5) -> List[str]:
        """
        Lấy các gợi ý tìm kiếm phổ biến từ SearchLog dựa trên một tiền tố.
        """
        # Sử dụng LIKE để tìm các truy vấn bắt đầu bằng tiền tố
        # Đếm số lần xuất hiện, nhóm lại và sắp xếp theo độ phổ biến
        sql_query = """
            SELECT "QueryText"
            FROM "SearchLog"
            WHERE "QueryText" ILIKE %s
            GROUP BY "QueryText"
            ORDER BY COUNT("QueryText") DESC
            LIMIT %s;
        """
        # Thêm ký tự '%' để tạo thành mẫu tìm kiếm của SQL LIKE
        search_pattern = f"{prefix}%"
        params = (search_pattern, limit)

        try:
            results = self.db_handler.execute_query_with_retry(sql_query, params)
            # Chuyển đổi kết quả từ list of tuples sang list of strings
            suggestions = [row[0] for row in results]
            return suggestions
        except Exception as e:
            print(f"Lỗi khi lấy gợi ý tìm kiếm: {e}")
            return []