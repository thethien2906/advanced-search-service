# /app/services/suggestion_service.py
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.database import DatabaseHandler

class SuggestionService:
    """
    Xử lý logic nghiệp vụ cho việc gợi ý các truy vấn tìm kiếm,
    kết hợp giữa gợi ý cá nhân hóa và gợi ý theo xu hướng.
    """
    def __init__(self):
        self.db_handler = DatabaseHandler(settings.DATABASE_URL)

    def get_suggestions(self, prefix: str, user_id: Optional[str] = None, limit: int = 5) -> List[str]:
        """
        Lấy các gợi ý tìm kiếm, ưu tiên lịch sử của người dùng,
        sau đó bổ sung bằng các tìm kiếm phổ biến toàn hệ thống.
        """
        suggestions = []
        search_pattern = f"{prefix}%"

        # 1. Lấy gợi ý cá nhân hóa nếu có user_id
        if user_id:
            try:
                # Tìm kiếm các truy vấn duy nhất từ lịch sử của người dùng
                user_sql = """
                    SELECT DISTINCT "QueryText"
                    FROM "SearchLog"
                    WHERE "UserID" = %s AND "QueryText" ILIKE %s
                    ORDER BY "CreatedAt" DESC
                    LIMIT %s;
                """
                user_params = (user_id, search_pattern, limit)
                user_results = self.db_handler.execute_query_with_retry(user_sql, user_params)
                suggestions.extend([row[0] for row in user_results])
            except Exception as e:
                print(f"Lỗi khi lấy gợi ý cá nhân hóa cho UserID {user_id}: {e}")

        # 2. Nếu chưa đủ, lấy thêm gợi ý theo xu hướng
        remaining_limit = limit - len(suggestions)
        if remaining_limit > 0:
            try:
                # Loại trừ những gợi ý đã có để tránh trùng lặp
                trending_sql = """
                    SELECT "QueryText"
                    FROM "SearchLog"
                    WHERE "QueryText" ILIKE %s
                    AND "QueryText" NOT IN %s
                    GROUP BY "QueryText"
                    ORDER BY COUNT("QueryText") DESC
                    LIMIT %s;
                """
                # Chuyển suggestions thành tuple để dùng trong `NOT IN`
                excluded_suggestions = tuple(suggestions) if suggestions else ('',)
                trending_params = (search_pattern, excluded_suggestions, remaining_limit)
                trending_results = self.db_handler.execute_query_with_retry(trending_sql, trending_params)
                suggestions.extend([row[0] for row in trending_results])
            except Exception as e:
                print(f"Lỗi khi lấy gợi ý theo xu hướng: {e}")

        return suggestions[:limit]