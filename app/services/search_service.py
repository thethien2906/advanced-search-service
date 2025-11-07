# /app/services/search_service.py
import json
import logging
from kafka import KafkaProducer
from kafka.errors import KafkaError
# (MỚI) Thêm UUID
from typing import List, Dict, Any, Optional
from uuid import UUID
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
        (ĐÃ CẬP NHẬT Ở GIAI ĐOẠN 2)
        Triển khai SKU-Driven.
        1. Tìm các "Gốc Hiển thị" (Master/Detail) gần nhất bằng pgvector.
        2. Lọc Gốc theo Status = 'Approved' và IsActive = true.
        3. Dùng AND EXISTS để kiểm tra Gốc "còn sống".
        4. Chỉ trả về các trường cần thiết cho Giai đoạn 2 (ML Re-ranking).
        """
        if not self.model:
            raise RuntimeError("Search model is not available.")

        expanded_query = self._expand_query(query)
        query_embedding = self.model.encode(expanded_query, normalize_embeddings=True)

        base_sql = """
        SELECT
            P_Goc."ID",
            (P_Goc."Embedding" <=> %(query_embedding)s) AS distance,

            -- Lấy các trường GĐ 1 cần cho GĐ 2
            P_Goc."Name" AS "name",
            P_Goc."ProductImages" AS "product_images",
            s."Status" AS "store_status",
            (
                SELECT array_agg(pc."Name")
                FROM "ProductCategory" pc
                WHERE pc."ID"::text IN (SELECT jsonb_array_elements_text(P_Goc."CategoryID"))
            ) as "category_names",
            pr."RegionSpecified" AS "sub_region_name"

        FROM "Product" P_Goc
        LEFT JOIN "Store" s ON P_Goc."StoreID" = s."ID"
        LEFT JOIN "Province" pr ON P_Goc."ProvinceID" = pr."ID"

        WHERE
            -- 1. Lọc Gốc (QĐ 6)
            P_Goc."ProductType" IN ('ProductMaster', 'ProductDetail')
            -- 2. Lọc Status (QĐ 1)
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

        # 4. Lọc "Sống" (QĐ 1 - Logic từ Step 2.1)
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
                JOIN "ProductVariant" pv ON t."ID" = pv."ID"
                JOIN "Product" p_la ON t."ID" = p_la."ID"
                WHERE
                    p_la."ProductType" = 'ProductVariant'
                    AND p_la."IsActive" = true
                    AND pv."Quantity" > 0
                    AND NOT EXISTS (
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
        final_sql += " ORDER BY distance ASC;"

        # Step 3: Thực thi truy vấn và xử lý kết quả
        db_results = self.db_handler.execute_query_with_retry(final_sql, params)

        candidates = []
        for row in db_results:
            candidates.append({
                "id": row[0],
                "relevance_score": float(row[1]),
                "name": row[2],
                "product_images": row[3] or [],
                "store_status": row[4],
                "category_names": row[5] or [],
                "sub_region_name": row[6]
            })

        # Sắp xếp lại trong Python (để đảm bảo)
        # GĐ 1 sắp xếp theo distance ASC (relevance_score ASC)
        candidates.sort(key=lambda x: x["relevance_score"], reverse=False)

        return candidates[:100]

    def _get_aggregated_sku_features(self, root_id: UUID) -> Dict[str, Any]:
        """
        Truy vấn các đặc trưng tổng hợp (SUM, AVG, MIN) từ tất cả
        "SKU Lá Hợp Lệ" thuộc về một "Gốc Hiển thị".
        """
        #
        sql = """
        WITH RECURSIVE product_tree AS (
            SELECT "ID", "ParentID" FROM "Product" WHERE "ID" = %(root_id)s
            UNION ALL
            SELECT p."ID", p."ParentID" FROM "Product" p JOIN product_tree pt ON p."ParentID" = pt."ID"
        ),
        leaf_skus AS (
            SELECT
                pv."FinalPrice",
                pv."SaleCount",
                pv."Rating",
                pv."ReviewCount"
            FROM product_tree t
            JOIN "ProductVariant" pv ON t."ID" = pv."ID"
            JOIN "Product" p_la ON t."ID" = p_la."ID"
            WHERE
                p_la."ProductType" = 'ProductVariant'
                AND p_la."IsActive" = true
                AND pv."Quantity" > 0
                AND NOT EXISTS (
                    SELECT 1 FROM "Product" p_child
                    WHERE p_child."ParentID" = t."ID" AND p_child."ProductType" = 'ProductVariant'
                )
        )
        SELECT
            COALESCE(MIN(ls."FinalPrice"), 0) as min_price,
            COALESCE(SUM(ls."SaleCount"), 0) as sum_sale_count,
            COALESCE(AVG(ls."Rating"), 0.0) as avg_rating,
            COALESCE(SUM(ls."ReviewCount"), 0) as sum_review_count
        FROM leaf_skus ls
        """
        params = {"root_id": root_id}
        try:
            agg_results = self.db_handler.execute_query_with_retry(sql, params)
            if agg_results:
                row = agg_results[0]
                return {
                    "min_price": row[0],
                    "sum_sale_count": row[1],
                    "avg_rating": float(row[2]),
                    "sum_review_count": row[3]
                }
        except Exception as e:
            logger.error(f"Lỗi khi lấy GĐ 2 (agg features) cho Gốc {root_id}: {e}", exc_info=True)

        # Trả về giá trị mặc định nếu lỗi
        return {
            "min_price": 0,
            "sum_sale_count": 0,
            "avg_rating": 0.0,
            "sum_review_count": 0
        }

    def _get_is_certified(self, root_id: UUID) -> bool:
        """
        Kiểm tra xem "Gốc Master" (L1) của sản phẩm có chứng nhận
        đã được 'Approved' hay không.
        """
        #
        sql = """
        WITH RECURSIVE master_root AS (
            -- 1. Tìm ngược lên đến gốc L1
            SELECT "ID", "ParentID" FROM "Product" WHERE "ID" = %(root_id)s
            UNION ALL
            SELECT p."ID", p."ParentID" FROM "Product" p
            JOIN master_root mr ON p."ParentID" = mr."ID"
        ),
        l1_root AS (
            SELECT "ID" FROM master_root WHERE "ParentID" IS NULL
        )
        -- 2. Kiểm tra chứng nhận 'Approved' trên gốc L1 đó
        SELECT EXISTS (
            SELECT 1 FROM "ProductCertificate" pc
            JOIN l1_root ON pc."ProductID" = l1_root."ID"
            WHERE pc."Status" = 'Approved'
        )
        """
        params = {"root_id": root_id}
        try:
            cert_result = self.db_handler.execute_query_with_retry(sql, params)
            if cert_result:
                return cert_result[0][0]
        except Exception as e:
            logger.error(f"Lỗi khi lấy GĐ 2 (is_certified) cho Gốc {root_id}: {e}", exc_info=True)

        return False


    def search_semantic(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Performs a pure semantic search.
        (Chuyển đổi score GĐ 1 thành similarity)
        """
        candidates = self._get_semantic_candidates(query)
        # Chuyển đổi distance (ASC) thành similarity (DESC)
        for p in candidates:
            p["relevance_score"] = 1.0 - p["relevance_score"]

        # Sắp xếp lại theo similarity (DESC)
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
        return candidates[:limit]


    def search_with_ml(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Thực hiện tìm kiếm GĐ 1, sau đó gọi N+1 query để lấy
        đặc trưng tổng hợp (GĐ 2) và xếp hạng lại bằng ML.
        """
        # candidates chứa (id, relevance_score (là distance), name, product_images, store_status, category_names, sub_region_name)
        candidates = self._get_semantic_candidates(query) #

        if not candidates:
            return []

        # Step 3: Nếu ranker model không được tải, fallback về semantic
        if self.ranker.model is None:
            logger.warning("WARNING: ML Ranker model not found. Falling back to semantic search results.")
            for p in candidates:
                p["relevance_score"] = 1.0 - p["relevance_score"]
            candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
            return candidates[:limit]

        logger.info(f"GĐ 1: Lấy được {len(candidates)} ứng viên. Bắt đầu trích xuất đặc trưng GĐ 2...")

        feature_matrix = []

        for p_candidate in candidates:
            root_id = p_candidate["id"]

            agg_features = self._get_aggregated_sku_features(root_id) #

            # is_certified = self._get_is_certified(root_id)
            is_certified = True
            combined_product_data = {
                "relevance_score": 1.0 - p_candidate["relevance_score"],
                "name": p_candidate["name"], #
                "product_images": p_candidate["product_images"], #
                "store_status": p_candidate["store_status"], #
                "category_names": p_candidate["category_names"], #
                "sub_region_name": p_candidate["sub_region_name"], #

                "price": agg_features["min_price"], #
                "sale_count": agg_features["sum_sale_count"], #
                "rating": agg_features["avg_rating"], #
                "review_count": agg_features["sum_review_count"], #
                "is_certified": is_certified #
            }

            # Step 4: Gọi feature_extractor (KHÔNG THAY ĐỔI)
            # Hàm này sẽ tự động lấy đúng key (vd: "rating") từ dict trên
            features = extract_features(combined_product_data, query, self.all_categories)
            feature_matrix.append(features)

        try:
            # Step 5: Áp dụng ML ranker (Giữ nguyên)
            feature_matrix = np.array(feature_matrix)
            ml_scores = self.ranker.predict(feature_matrix)

            # Step 6: Cập nhật điểm và sắp xếp lại (Giữ nguyên)
            for i, product in enumerate(candidates):
                # Gán điểm ML mới
                product["relevance_score"] = float(ml_scores[i])
                # (Xóa bớt các trường không cần thiết trả về cho worker)
                del product["name"]
                del product["product_images"]
                del product["store_status"]
                del product["category_names"]
                del product["sub_region_name"]


            candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

            logger.info(f"GĐ 2: Xếp hạng ML hoàn tất. Trả về {min(limit, len(candidates))} kết quả.")
            # Step 7: Trả về top N
            return candidates[:limit]

        except Exception as e:
            logger.error(f"Lỗi nghiêm trọng trong GĐ 2 (ML Reranking): {e}", exc_info=True)
            # Fallback về kết quả GĐ 1 nếu GĐ 2 lỗi
            for p in candidates:
                p["relevance_score"] = 1.0 - p["relevance_score"]
            candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
            return candidates[:limit]