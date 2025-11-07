# /app/services/search_service.py
import json
import logging
from kafka import KafkaProducer
from kafka.errors import KafkaError
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
import numpy as np
from app.core.config import settings
from app.services.database import DatabaseHandler
from app.services.ranker import XGBoostRanker
from app.services.feature_extractor import extract_features, remove_vietnamese_diacritics
from app.services.search_constants import (
    QUERY_EXPANSION_MAP,
    REGION_HIERARCHY,
    SUB_REGION_KEYWORDS
)

# Khởi tạo logger
logger = logging.getLogger(__name__)

class SearchService:
    """
    Handles the business logic for searching products by orchestrating
    semantic retrieval, feature extraction, and ML re-ranking.
    """
    def __init__(self):
        self.db_handler = DatabaseHandler(settings.DATABASE_URL)
        self.model = None
        self.ranker = XGBoostRanker() # Initialize the ranker wrapper
        self.all_categories = self._load_categories() # Tải danh mục khi khởi tạo

        try:
            logger.info(f"Loading sentence-transformers model: {settings.MODEL_NAME}...")
            self.model = SentenceTransformer(settings.MODEL_NAME)
            logger.info("Model loaded successfully.")
            try:
                # Gửi tín hiệu model ready (Giữ nguyên logic gốc)
                signal_producer = KafkaProducer(
                    bootstrap_servers=settings.KAFKA_BROKER_URL,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                signal_producer.send(settings.MODEL_READY_TOPIC, value={'status': 'ready'})
                signal_producer.flush()
                signal_producer.close()
                logger.info(f"✅ Sent 'model ready' signal to topic '{settings.MODEL_READY_TOPIC}'.")
            except Exception as e:
                logger.warning(f"❌ Could not send 'model ready' signal: {e}")
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to load sentence-transformers model: {e}")
            raise

    def _load_categories(self) -> List[str]:
        """
        Tải tất cả tên danh mục đang hoạt động từ cơ sở dữ liệu.
        (Giữ nguyên)
        """
        logger.info("Loading product categories from database...")
        try:
            sql = 'SELECT "Name" FROM "ProductCategory" WHERE "IsActive" = true;'
            results = self.db_handler.execute_query_with_retry(sql)
            # Chuyển đổi tên danh mục sang chữ thường và không dấu để dễ so khớp
            categories = [remove_vietnamese_diacritics(row[0].lower()) for row in results]
            logger.info(f"Loaded {len(categories)} active categories.")
            return categories
        except Exception as e:
            logger.error(f"ERROR: Could not load categories from database: {e}", exc_info=True)
            return []

    def _expand_query(self, query: str) -> str:
        """
        Expands an abstract query with more concrete keywords.
        (Giữ nguyên)
        """
        query_lower = query.lower()
        expanded_terms = []
        for keyword, expansions in QUERY_EXPANSION_MAP.items():
            if keyword in query_lower:
                expanded_terms.extend(expansions)

        if expanded_terms:
            expanded_query = query + " " + " ".join(list(set(expanded_terms)))
            logger.info(f"Query expanded: '{query}' -> '{expanded_query}'")
            return expanded_query
        return query

    def _get_regions_for_sql_filter(self, query: str) -> Optional[List[str]]:
        """
        Phát hiện vùng miền ở cả hai cấp độ.
        (Giữ nguyên)
        """
        query_lower = query.lower()

        for sub_region, keywords in SUB_REGION_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                logger.info(f"Detected specific sub-region: {sub_region}")
                return [sub_region]

        for region, sub_regions in REGION_HIERARCHY.items():
            if region in query_lower:
                logger.info(f"Detected broad region: {region}, expanding to {sub_regions}")
                return sub_regions

        return None

    def _get_semantic_candidates(self, query: str) -> List[Dict[str, Any]]:
        """
        Triển khai Logic B (SKU-Driven).
        1. Tìm các "Gốc Hiển thị" (Master/Detail) gần nhất bằng pgvector.
        2. Lọc Gốc theo Status = 'Approved' và IsActive = true.
        3. Dùng AND EXISTS để kiểm tra Gốc "còn sống":
           - Phải có ít nhất một "SKU Lá" (Leaf SKU).
           - SKU Lá đó phải IsActive = true và Quantity > 0 (từ ProductVariant).
        4. Chỉ trả về các trường cần thiết cho Giai đoạn 2 (ML Re-ranking).
        """
        if not self.model:
            raise RuntimeError("Search model is not available.")

        # Step 1: Tạo embedding cho truy vấn (Giữ nguyên)
        expanded_query = self._expand_query(query)
        query_embedding = self.model.encode(expanded_query, normalize_embeddings=True)

        # Step 2: Xây dựng truy vấn SQL mới (Logic B)

        # (SQL MỚI - Step 2.2)
        # Truy vấn này chỉ lấy dữ liệu Gốc (GĐ 1) và lọc Gốc "sống"
        base_sql = """
        SELECT
            P_Goc."ID",
            (P_Goc."Embedding" <=> %(query_embedding)s) AS distance,

            -- Lấy các trường GĐ 1 cần cho GĐ 2 [cite: 721, 748, 753]
            P_Goc."Name" AS "name",
            P_Goc."ProductImages" AS "product_images",
            s."Status" AS "store_status",
            (
                SELECT array_agg(pc."Name")
                FROM "ProductCategory" pc
                WHERE pc."ID"::text IN (SELECT jsonb_array_elements_text(P_Goc."CategoryID"))
            ) as "category_names",
            pr."RegionSpecified" AS "sub_region_name"
            -- Lưu ý: rating, price, sale_count... sẽ được lấy ở GĐ 2 (Step 3.1)

        FROM "Product" P_Goc
        LEFT JOIN "Store" s ON P_Goc."StoreID" = s."ID"
        LEFT JOIN "Province" pr ON P_Goc."ProvinceID" = pr."ID"

        WHERE
            -- 1. Lọc Gốc (QĐ 6) [cite: 33]
            P_Goc."ProductType" IN ('ProductMaster', 'ProductDetail')
            -- 2. Lọc Status (QĐ 1) [cite: 34]
            AND P_Goc."Status" = 'Approved'
            AND P_Goc."IsActive" = true
            AND s."Status" = 'Approved'
        """

        where_clauses = []
        params = {"query_embedding": str(list(query_embedding))}

        # 3. Lọc khu vực (Giữ nguyên logic cũ)
        regions_to_filter = self._get_regions_for_sql_filter(query)
        if regions_to_filter:
            where_clauses.append('pr."RegionSpecified" = ANY(%(regions)s)')
            params["regions"] = regions_to_filter
            logger.info(f"Applying SQL filter for regions: {regions_to_filter}")

        # 4. Lọc "Sống" (QĐ 1 - Logic từ Step 2.1) [cite: 35, 724]
        # Thêm điều kiện AND EXISTS để kiểm tra Gốc "còn sống"
        live_check_sql = """
        AND EXISTS (
            WITH RECURSIVE product_tree AS (
                SELECT "ID", "ParentID" FROM "Product" WHERE "ID" = P_Goc."ID"
                UNION ALL
                SELECT p."ID", p."ParentID" FROM "Product" p JOIN product_tree pt ON p."ParentID" = pt."ID"
            ),
            valid_leaf_skus AS (
                SELECT 1
                FROM product_tree t
                JOIN "ProductVariant" pv ON t."ID" = pv."ID" -- Join ProductVariant (DDL 4.8) [cite: 822]
                JOIN "Product" p_la ON t."ID" = p_la."ID"
                WHERE
                    p_la."ProductType" = 'ProductVariant'    -- Phải là Variant
                    AND p_la."IsActive" = true            -- Phải Active
                    AND pv."Quantity" > 0                 -- Phải còn hàng (từ ProductVariant)
                    AND NOT EXISTS (                      -- Phải là "Lá"
                        SELECT 1 FROM "Product" p_child
                        WHERE p_child."ParentID" = t."ID" AND p_child."ProductType" = 'ProductVariant'
                    )
                LIMIT 1
            )
            SELECT 1 FROM valid_leaf_skus
        )
        """

        final_sql = base_sql
        if where_clauses:
            final_sql += " AND " + " AND ".join(where_clauses)

        final_sql += live_check_sql

        # Sắp xếp theo distance (pgvector)
        final_sql += " ORDER BY distance ASC;"

        # Step 3: Thực thi truy vấn và xử lý kết quả
        db_results = self.db_handler.execute_query_with_retry(final_sql, params)

        candidates = []
        for row in db_results:
            # (LOGIC MỚI - Step 2.2)
            # Chỉ đóng gói các trường GĐ 1 đã truy vấn
            candidates.append({
                "id": row[0],
                # Chuyển distance về cosine similarity
                "relevance_score": 1 - float(row[1]),
                "name": row[2],
                "product_images": row[3] or [],
                "store_status": row[4],
                "category_names": row[5] or [],
                "sub_region_name": row[6]
            })

        # Sắp xếp lại trong Python (để đảm bảo)
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        return candidates[:100]


    def search_semantic(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Performs a pure semantic search.
        """
        candidates = self._get_semantic_candidates(query)
        return candidates[:limit]


    def search_with_ml(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        (CHƯA THAY ĐỔI - Sẽ được cập nhật ở Giai đoạn 3)
        Performs semantic search followed by ML re-ranking.
        """
        # Step 1 & 2: Lấy ứng viên GĐ 1 (Hàm này đã được cập nhật ở GĐ 2)
        candidates = self._get_semantic_candidates(query)

        if not candidates:
            return []

        # Step 3: Nếu ranker model không được tải, fallback về semantic
        if self.ranker.model is None:
            logger.warning("WARNING: ML Ranker model not found. Falling back to semantic search results.")
            return candidates[:limit]

        # ==================================================================
        # CẢNH BÁO: Logic bên dưới (GĐ 2) sẽ THẤT BẠI
        # vì `candidates` từ `_get_semantic_candidates` (đã sửa)
        # KHÔNG còn chứa "rating", "price", "sale_count", v.v.
        # Logic này sẽ được sửa ở GIAI ĐOẠN 3.
        # ==================================================================

        try:
            # Step 4: Trích xuất đặc trưng
            feature_matrix = np.array([extract_features(p, query, self.all_categories) for p in candidates])

            # Step 5: Áp dụng ML ranker
            ml_scores = self.ranker.predict(feature_matrix)

            # Step 6: Cập nhật điểm và sắp xếp lại
            for i, product in enumerate(candidates):
                product["relevance_score"] = float(ml_scores[i])

            candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

            # Step 7: Trả về top N
            return candidates[:limit]
        except KeyError as e:
            logger.error(f"LỖI CHƯA XỬ LÝ (GĐ 2): Thiếu key '{e}' để trích xuất đặc trưng.")
            logger.error("Điều này là BÌNH THƯỜNG và sẽ được sửa ở Giai đoạn 3 (Nâng cấp search_with_ml).")
            logger.error("Fallback về kết quả semantic search...")
            # Fallback về kết quả GĐ 1 nếu GĐ 2 lỗi
            candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
            return candidates[:limit]
        except Exception as e:
            logger.error(f"Lỗi không mong muốn trong GĐ 2 (ML Reranking): {e}", exc_info=True)
            # Fallback về kết quả GĐ 1
            candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
            return candidates[:limit]