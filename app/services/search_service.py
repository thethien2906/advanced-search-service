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
from app.services.embedding_service import EmbeddingService
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
    def _get_popular_candidates(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sản phẩm phổ biến (bán chạy nhất & rating cao nhất)
        khi người dùng không nhập từ khóa.
        """
        # Sử dụng CTE tương tự như search semantic để đảm bảo lấy đúng Root Product
        sql = """
        WITH RECURSIVE valid_leaf_skus AS (
            SELECT
                p_leaf."ID",
                p_leaf."ParentID",
                pv."SaleCount",
                pv."Rating"
            FROM "Product" p_leaf
            JOIN "ProductVariant" pv ON p_leaf."ID" = pv."ID"
            WHERE
                p_leaf."ProductType" = 'ProductVariant'
                AND p_leaf."IsActive" = true
                AND pv."Quantity" > 0
                AND NOT EXISTS (
                    SELECT 1 FROM "Product" p_child
                    WHERE p_child."ParentID" = p_leaf."ID" AND p_child."ProductType" = 'ProductVariant'
                )
        ),
        -- Truy ngược từ Leaf lên Root để tính tổng
        product_tree AS (
            SELECT
                vls."ID" as "LeafID",
                vls."ParentID",
                vls."SaleCount",
                vls."Rating",
                p_parent."ID" as "RootID",
                p_parent."ProductType"
            FROM valid_leaf_skus vls
            JOIN "Product" p_parent ON vls."ParentID" = p_parent."ID"

            UNION ALL

            SELECT
                pt."LeafID",
                pt."ParentID",
                pt."SaleCount",
                pt."Rating",
                p_grand."ID" as "RootID",
                p_grand."ProductType"
            FROM product_tree pt
            JOIN "Product" p_grand ON pt."RootID" = p_grand."ParentID"
        ),
        -- Chỉ giữ lại các Root là ProductMaster/ProductDetail (không phải Variant trung gian)
        root_stats AS (
            SELECT
                "RootID",
                SUM("SaleCount") as "TotalSales",
                AVG("Rating") as "AvgRating"
            FROM product_tree
            WHERE "ProductType" != 'ProductVariant'
            GROUP BY "RootID"
        )
        SELECT
            P_Goc."ID",
            0.0 AS distance, -- Mặc định distance = 0 cho top products
            P_Goc."Name" AS "name",
            P_Goc."ProductImages" AS "product_images",
            s."Status" AS "store_status",
            ARRAY_REMOVE(ARRAY[pc."Name", pc_parent."Name"], NULL) as "category_names",
            pr."RegionSpecified" AS "sub_region_name",
            pr."Name" AS "province_name",
            pr."Region" AS "region_name",
            P_Goc."CreatedAt" AS "createdAt"
        FROM root_stats rs
        JOIN "Product" P_Goc ON rs."RootID" = P_Goc."ID"
        LEFT JOIN "Store" s ON P_Goc."StoreID" = s."ID"
        LEFT JOIN "Province" pr ON P_Goc."ProvinceID" = pr."ID"
        LEFT JOIN "ProductCategory" pc ON P_Goc."CategoryID" = pc."ID"
        LEFT JOIN "ProductCategory" pc_parent ON pc."ParentId" = pc_parent."ID"
        WHERE
            P_Goc."Status" = 'Approved'
            AND P_Goc."IsActive" = true
            AND s."Status" = 'Approved'
        ORDER BY rs."TotalSales" DESC, rs."AvgRating" DESC
        LIMIT %(limit)s;
        """

        params = {"limit": limit}

        try:
            logger.info("Executing Popular Products Query for empty search...")
            db_results = self.db_handler.execute_query_with_retry(sql, params)

            candidates = []
            for row in db_results:
                candidates.append({
                    "id": row[0],
                    "relevance_score": 0.0, # Đặt là 0.0 để tương thích logic tính distance
                    "name": row[2],
                    "product_images": row[3] or [],
                    "store_status": row[4],
                    "category_names": row[5] or [],
                    "sub_region_name": row[6],
                    "province_name": row[7],
                    "region_name": row[8],
                    "createdAt": row[9]
                })
            return candidates
        except Exception as e:
            logger.error(f"Error fetching popular candidates: {e}", exc_info=True)
            return []



    def _get_semantic_candidates(self, query: str) -> List[Dict[str, Any]]:
        """
        Triển khai logic "SKU-Driven"
        (Hàm này đã được sửa để thêm 'createdAt' vào candidates)
        """
        if not self.model:
            raise RuntimeError("Search model is not available.")

        expanded_query = self._expand_query(query)
        query_embedding = self.model.encode(expanded_query, normalize_embeddings=True)

        base_sql = """
        -- (Giữ nguyên các CTE 1, 2, 3) ...
        WITH RECURSIVE valid_leaf_skus AS (
            SELECT
                p_leaf."ID",
                p_leaf."ParentID"
            FROM "Product" p_leaf
            JOIN "ProductVariant" pv ON p_leaf."ID" = pv."ID"
            WHERE
                p_leaf."ProductType" = 'ProductVariant'
                AND p_leaf."IsActive" = true
                AND pv."Quantity" > 0
                AND NOT EXISTS (
                    SELECT 1 FROM "Product" p_child
                    WHERE p_child."ParentID" = p_leaf."ID" AND p_child."ProductType" = 'ProductVariant'
                )
        ),
        display_root_cte AS (
            SELECT
                p_parent."ID",
                p_parent."ParentID",
                p_parent."ProductType"
            FROM "Product" p_parent
            JOIN valid_leaf_skus vls ON p_parent."ID" = vls."ParentID"
            UNION ALL
            SELECT
                p_parent."ID",
                p_parent."ParentID",
                p_parent."ProductType"
            FROM "Product" p_parent
            JOIN display_root_cte dr ON p_parent."ID" = dr."ParentID"
            WHERE
                dr."ProductType" = 'ProductVariant'
        ),
        valid_display_roots AS (
            SELECT DISTINCT "ID"
            FROM display_root_cte
            WHERE "ProductType" != 'ProductVariant'
        )

        -- Truy vấn chính: Chỉ tìm kiếm trên các Gốc Hiển thị hợp lệ
        SELECT
            P_Goc."ID",
            (P_Goc."Embedding" <=> %(query_embedding)s) AS distance,
            P_Goc."Name" AS "name",
            P_Goc."ProductImages" AS "product_images",
            s."Status" AS "store_status",
            ARRAY_REMOVE(ARRAY[pc."Name", pc_parent."Name"], NULL) as "category_names",
            pr."RegionSpecified" AS "sub_region_name",
            pr."Name" AS "province_name",
            pr."Region" AS "region_name",
            P_Goc."CreatedAt" AS "createdAt" -- Cột này là index 9

        FROM "Product" P_Goc
        JOIN valid_display_roots vdr ON P_Goc."ID" = vdr."ID"
        LEFT JOIN "Store" s ON P_Goc."StoreID" = s."ID"
        LEFT JOIN "Province" pr ON P_Goc."ProvinceID" = pr."ID"
        LEFT JOIN "ProductCategory" pc ON P_Goc."CategoryID" = pc."ID"
        LEFT JOIN "ProductCategory" pc_parent ON pc."ParentId" = pc_parent."ID"
        WHERE
            P_Goc."Status" = 'Approved'
            AND P_Goc."IsActive" = true
            AND s."Status" = 'Approved'
        """
        where_clauses = []
        params = {"query_embedding": str(list(query_embedding))}
        regions_to_filter = self._get_regions_for_sql_filter(query)
        if regions_to_filter:
            where_clauses.append('pr."RegionSpecified" = ANY(%(regions)s)')
            params["regions"] = regions_to_filter
            logger.info(f"Applying SQL filter for regions: {regions_to_filter}")
        final_sql = base_sql
        if where_clauses:
            final_sql += " AND " + " AND ".join(where_clauses)
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
                "sub_region_name": row[6],
                "province_name": row[7],
                "region_name": row[8],
                "createdAt": row[9]
            })

        # Sắp xếp lại trong Python (để đảm bảo)
        candidates.sort(key=lambda x: x["relevance_score"], reverse=False)

        return candidates[:100]


    def _get_aggregated_sku_features(self, root_id: UUID) -> Dict[str, Any]:
        """
        (Giữ nguyên hàm này)
        """
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
                    "min_price": row[0], # Đây là kiểu Decimal
                    "sum_sale_count": row[1],
                    "avg_rating": float(row[2]),
                    "sum_review_count": row[3]
                }
        except Exception as e:
            logger.error(f"Lỗi khi lấy GĐ 2 (agg features) cho Gốc {root_id}: {e}", exc_info=True)

        return {
            "min_price": 0,
            "sum_sale_count": 0,
            "avg_rating": 0.0,
            "sum_review_count": 0
        }

    def _get_is_certified(self, root_id: UUID) -> bool:
        """
        (Giữ nguyên hàm này)
        """
        sql = """
        WITH RECURSIVE master_root AS (
            SELECT "ID", "ParentID" FROM "Product" WHERE "ID" = %(root_id)s
            UNION ALL
            SELECT p."ID", p."ParentID" FROM "Product" p
            JOIN master_root mr ON p."ParentID" = mr."ID"
        ),
        l1_root AS (
            SELECT "ID" FROM master_root WHERE "ParentID" IS NULL
        )
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
        """
        # Step 1: Lấy các ứng viên Gốc
        # Kiểm tra query rỗng
        if not query or not query.strip():
            logger.info("Query is empty. Fetching popular products instead.")
            candidates = self._get_popular_candidates(limit)
        else:
            candidates = self._get_semantic_candidates(query)
        if not candidates:
            return []

        logger.info(f"GĐ 1 (Semantic): Lấy được {len(candidates)} ứng viên. Bắt đầu trích xuất đặc trưng GĐ 2...")

        enriched_results = []
        for p_candidate in candidates:
            root_id = p_candidate["id"]

            agg_features = self._get_aggregated_sku_features(root_id)
            created_at_iso = None

            # Kiểm tra xem p_candidate["createdAt"] có tồn tại, không None,
            # và là một đối tượng datetime (có hàm isoformat)
            if p_candidate.get("createdAt") and hasattr(p_candidate["createdAt"], 'isoformat'):
                try:
                    # Dùng .isoformat() để CHUẨN HÓA CÓ CHỮ 'T'
                    # Kết quả sẽ là: "2025-09-21T01:13:16.222527+00:00"
                    created_at_iso = p_candidate["createdAt"].isoformat()
                except Exception as e:
                    logger.warning(f"Không thể format iso cho ngày: {p_candidate['createdAt']}. Lỗi: {e}")
            enriched_product = {
                # Lưu ý: Key phải là PascalCase để khớp với C# DTO
                "Id": p_candidate["id"],
                "Name": p_candidate["name"],
                "Price": float(agg_features["min_price"]), # <-- FIX 1: ÉP KIỂU SANG FLOAT
                "Rating": agg_features["avg_rating"], # Đã là float

                # Các trường .NET DTO mong đợi là snake_case (vì có [JsonPropertyName])
                "review_count": agg_features["sum_review_count"],
                "sale_count": agg_features["sum_sale_count"],
                "store_status": p_candidate["store_status"],
                "product_images": p_candidate["product_images"] or [],
                "relevance_score": 1.0 - p_candidate["relevance_score"],
                "category_names": p_candidate["category_names"] or [],
                "province_name": p_candidate["province_name"],
                "region_name": p_candidate["region_name"],
                "sub_region_name": p_candidate["sub_region_name"],

                # <-- FIX 2.2: THÊM TRƯỜNG CreatedAt (key là PascalCase)
                "CreatedAt": created_at_iso
            }
            enriched_results.append(enriched_product)

        # Step 3: Sắp xếp lại theo similarity (DESC)
        enriched_results.sort(key=lambda x: x["relevance_score"], reverse=True)

        logger.info(f"GĐ 2 (Enrichment): Hoàn tất. Trả về {min(limit, len(enriched_results))} kết quả.")
        return enriched_results[:limit]


    def search_with_ml(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Thực hiện tìm kiếm GĐ 1, sau đó gọi N+1 query để lấy
        đặc trưng tổng hợp (GĐ 2) và xếp hạng lại bằng ML.
        """
        if not query or not query.strip():
            logger.info("ML Search: Query is empty. Falling back to popular products (skipping ML ranking).")
            # Với query rỗng, ta không cần chạy qua ML Ranker vì không có ngữ cảnh "query" để khớp
            # Ta trả về trực tiếp kết quả enriched (đã sort theo Sale/Rating)
            return self.search_semantic(query, limit)

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

    def search_documents(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Tìm kiếm tài liệu dựa trên độ tương đồng vector (Cosine Similarity).
        """
        if not self.model:
            raise RuntimeError("Model chưa được load.")

        # 1. Tạo vector cho câu query (Dùng logic mở rộng query nếu cần)
        # Ở đây dùng simple query embedding
        embedding_service = EmbeddingService() # Hoặc inject vào __init__ để tối ưu
        query_vector = embedding_service.create_text_embedding(query)
        
        # 2. SQL Query
        sql = """
        SELECT
            "ID",
            "Title",
            "Content",
            "Slug",
            ("Embedding" <=> %(query_vector)s) as distance
        FROM "Document"
        WHERE "IsPublished" = true 
          AND "Embedding" IS NOT NULL
        ORDER BY distance ASC
        LIMIT %(limit)s;
        """
        
        params = {
            "query_vector": str(query_vector),
            "limit": limit
        }

        try:
            results = self.db_handler.execute_query_with_retry(sql, params)
            
            # 3. Map kết quả
            documents = []
            for row in results:
                documents.append({
                    "Id": row[0],              # UUID
                    "Title": row[1],
                    "Content": row[2][:500] if row[2] else "",   # Cắt ngắn nội dung để preview
                    "Slug": row[3],
                    "RelevanceScore": 1 - float(row[4]), # Convert Distance -> Similarity
                    "Type": "Document"
                })
            return documents
        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm Document: {e}", exc_info=True)
            return []