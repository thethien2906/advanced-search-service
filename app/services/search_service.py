# /app/services/search_service.py
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
            print(f"Loading sentence-transformers model: {settings.MODEL_NAME}...")
            self.model = SentenceTransformer(settings.MODEL_NAME)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"CRITICAL: Failed to load sentence-transformers model: {e}")
            raise

    def _load_categories(self) -> List[str]:
        """
        Tải tất cả tên danh mục đang hoạt động từ cơ sở dữ liệu.
        """
        print("Loading product categories from database...")
        try:
            sql = 'SELECT "Name" FROM "ProductCategory" WHERE "IsActive" = true;'
            results = self.db_handler.execute_query_with_retry(sql)
            # Chuyển đổi tên danh mục sang chữ thường và không dấu để dễ so khớp
            categories = [remove_vietnamese_diacritics(row[0].lower()) for row in results]
            print(f"Loaded {len(categories)} active categories.")
            return categories
        except Exception as e:
            print(f"ERROR: Could not load categories from database: {e}")
            return []

    def _expand_query(self, query: str) -> str:
        """
        Expands an abstract query with more concrete keywords for better
        semantic search results.
        """
        query_lower = query.lower()
        expanded_terms = []
        for keyword, expansions in QUERY_EXPANSION_MAP.items():
            if keyword in query_lower:
                expanded_terms.extend(expansions)

        if expanded_terms:
            # Combine original query with expanded terms
            expanded_query = query + " " + " ".join(list(set(expanded_terms))) # Use set to avoid duplicates
            print(f"Query expanded: '{query}' -> '{expanded_query}'")
            return expanded_query

        # Return original query if no keywords matched
        return query

    def _get_regions_for_sql_filter(self, query: str) -> Optional[List[str]]:
        """
        Nâng cấp logic để phát hiện vùng miền ở cả hai cấp độ.
        Ưu tiên vùng miền cụ thể trước.
        """
        query_lower = query.lower()

        # Cấp 1: Tìm kiếm vùng miền CỤ THỂ (ví dụ: "miền tây" -> "Đồng bằng sông Cửu Long")
        for sub_region, keywords in SUB_REGION_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                print(f"Detected specific sub-region: {sub_region}")
                return [sub_region] # Trả về một danh sách chứa chỉ 1 vùng miền cụ thể

        # Cấp 2: Nếu không thấy, tìm kiếm vùng miền LỚN (ví dụ: "miền nam")
        for region, sub_regions in REGION_HIERARCHY.items():
            if region in query_lower:
                print(f"Detected broad region: {region}, expanding to {sub_regions}")
                return sub_regions # Trả về danh sách các vùng miền con

        return None # Không tìm thấy vùng miền nào trong truy vấn

    def _get_semantic_candidates(self, query: str) -> List[Dict[str, Any]]:
        """
        Retrieves unique semantic search candidates using DISTINCT ON to handle product variants.
        """
        if not self.model:
            raise RuntimeError("Search model is not available.")

        expanded_query = self._expand_query(query)
        query_embedding = self.model.encode(expanded_query, normalize_embeddings=True)

        # ======================================================================
        # THAY ĐỔI LỚN: Truy vấn SQL để lấy tên danh mục thay vì ID
        # ======================================================================
        base_sql = """
            SELECT DISTINCT ON (p."ID")
                p."ID",
                p."Name",
                p."Rating",
                p."ReviewCount",
                p."SaleCount",
                -- Lấy mảng tên danh mục
                (
                    SELECT array_agg(pc."Name")
                    FROM "ProductCategory" pc
                    WHERE pc."ID"::text IN (SELECT jsonb_array_elements_text(p."CategoryID"))
                ) as "CategoryNames",
                p."ProductImages",
                pv."BasePrice" AS "price",
                s."Status" AS "StoreStatus",
                EXISTS (SELECT 1 FROM "ProductCertificate" pc WHERE pc."ProductID" = p."ID") AS "IsCertified",
                (p."Embedding" <=> %s) AS distance,
                pr."Name" AS "ProvinceName",
                pr."Region" AS "RegionName",
                pr."RegionSpecified" AS "RegionSpecifiedName"
            FROM "Product" p
            INNER JOIN "ProductVariant" pv ON p."ID" = pv."ProductID"
            INNER JOIN "InventoryProduct" ip ON pv."ID" = ip."ProductVariantID"
            INNER JOIN "Store" s ON p."StoreID" = s."ID"
            LEFT JOIN "Province" pr ON p."ProvinceID" = pr."ID"
        """

        where_clauses = [
            "ip.\"Quantity\" > 0",
            "p.\"IsActive\" = true",
            "s.\"Status\" = 'Approved'"
        ]

        params = [str(list(query_embedding))]
        regions_to_filter = self._get_regions_for_sql_filter(query)
        if regions_to_filter:
            where_clauses.append('pr."RegionSpecified" = ANY(%s)')
            params.append(regions_to_filter)
            print(f"Applying SQL filter for regions: {regions_to_filter}")

        # Nối các điều kiện WHERE
        final_sql = base_sql + " WHERE " + " AND ".join(where_clauses) + " ORDER BY p.\"ID\", distance ASC;"
        db_results = self.db_handler.execute_query_with_retry(final_sql, tuple(params))

        candidates = []
        for row in db_results:
            candidates.append({
                "id": row[0],
                "name": row[1],
                "rating": float(row[2]) if row[2] is not None else 0.0,
                "review_count": row[3],
                "sale_count": row[4],
                "category_names": row[5] or [], # Thay đổi ở đây
                "product_images": row[6] or [],
                "price": row[7],
                "store_status": row[8],
                "is_certified": row[9],
                "relevance_score": 1 - row[10], # Cosine similarity
                "province_name": row[11],
                "region_name": row[12],
                "sub_region_name": row[13]
            })
        # ======================================================================

        # Sắp xếp kết quả theo relevance_score trong Python sau khi lấy từ DB
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        return candidates[:100]

    def search_semantic(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Performs a pure semantic search. Uses query expansion.
        """
        candidates = self._get_semantic_candidates(query)
        return candidates[:limit]


    def search_with_ml(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Performs semantic search followed by ML re-ranking.
        Uses query expansion for candidate retrieval.
        """
        # Step 1 & 2: Retrieve initial candidates using semantic search (with expansion)
        candidates = self._get_semantic_candidates(query)

        if not candidates:
            return []

        # Step 3: If ranker model isn't loaded, return results based on semantic score
        if self.ranker.model is None:
            print("WARNING: ML Ranker model not found. Falling back to semantic search results.")
            return candidates[:limit]

        # Step 4: Extract features for all candidates.
        # Truyền danh sách all_categories vào hàm extract_features
        feature_matrix = np.array([extract_features(p, query, self.all_categories) for p in candidates])

        # Step 5: Apply ML ranker to get new scores
        ml_scores = self.ranker.predict(feature_matrix)

        # Step 6: Update relevance scores and re-sort
        for i, product in enumerate(candidates):
            product["relevance_score"] = float(ml_scores[i])

        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Step 7: Return top N results
        return candidates[:limit]