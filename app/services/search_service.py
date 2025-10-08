# /app/services/search_service.py
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
import numpy as np
from app.core.config import settings
from app.services.database import DatabaseHandler
from app.services.ranker import XGBoostRanker
from app.services.feature_extractor import extract_features
# Import the new query expansion map
from app.services.search_constants import QUERY_EXPANSION_MAP


class SearchService:
    """
    Handles the business logic for searching products by orchestrating
    semantic retrieval, feature extraction, and ML re-ranking.
    """
    def __init__(self):
        self.db_handler = DatabaseHandler(settings.DATABASE_URL)
        self.model = None
        self.ranker = XGBoostRanker() # Initialize the ranker wrapper

        try:
            print(f"Loading sentence-transformers model: {settings.MODEL_NAME}...")
            self.model = SentenceTransformer(settings.MODEL_NAME)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"CRITICAL: Failed to load sentence-transformers model: {e}")
            raise

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

    def _get_semantic_candidates(self, query: str) -> List[Dict[str, Any]]:
        """
        Retrieves unique semantic search candidates using DISTINCT ON to handle product variants.
        """
        if not self.model:
            raise RuntimeError("Search model is not available.")

        expanded_query = self._expand_query(query)
        query_embedding = self.model.encode(expanded_query, normalize_embeddings=True)

        # === START: TỐI ƯU HÓA SQL VỚI DISTINCT ON ===
        # Lỗi cũ: GROUP BY phức tạp hoặc ORDER BY sai.
        # Giải pháp: Dùng DISTINCT ON (p."ID") để lấy sản phẩm duy nhất.
        # ORDER BY p."ID", pv."BasePrice" ASC bên trong để đảm bảo giá được chọn là giá thấp nhất.
        # ORDER BY distance bên ngoài để sắp xếp kết quả cuối cùng theo độ liên quan.
        sql_query = """
            SELECT DISTINCT ON (p."ID")
                p."ID",
                p."Name",
                p."Rating",
                p."ReviewCount",
                p."SaleCount",
                p."CategoryID",
                p."ProductImages",
                pv."BasePrice" AS "price",
                s."Status" AS "StoreStatus",
                EXISTS (SELECT 1 FROM "ProductCertificate" pc WHERE pc."ProductID" = p."ID") AS "IsCertified",
                (p."Embedding" <=> %s) AS distance,
                pr."Name" AS "ProvinceName",
                pr."Region" AS "RegionName"
            FROM "Product" p
            INNER JOIN "ProductVariant" pv ON p."ID" = pv."ProductID"
            INNER JOIN "InventoryProduct" ip ON pv."ID" = ip."ProductVariantID"
            INNER JOIN "Store" s ON p."StoreID" = s."ID"
            LEFT JOIN "Province" pr ON p."ProvinceID" = pr."ID"
            WHERE
                ip."Quantity" > 0
                AND p."IsActive" = true
                AND s."Status" = 'Approved'
            ORDER BY
                p."ID", pv."BasePrice" ASC;
        """
        # === END: TỐI ƯU HÓA SQL ===

        params = (str(list(query_embedding)),)
        db_results = self.db_handler.execute_query_with_retry(sql_query, params)

        candidates = []
        for row in db_results:
            candidates.append({
                "id": row[0],
                "name": row[1],
                "rating": float(row[2]) if row[2] is not None else 0.0,
                "review_count": row[3],
                "sale_count": row[4],
                "category_id": row[5],
                "product_images": row[6] or [],
                "price": row[7],
                "store_status": row[8],
                "is_certified": row[9],
                "relevance_score": 1 - row[10],
                "province_name": row[11],
                "region_name": row[12]
            })

        # Sắp xếp kết quả theo relevance_score trong Python sau khi lấy từ DB
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        return candidates[:100]

    def search_semantic(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Performs a pure semantic search. Uses query expansion.
        """
        # The original query is passed to _get_semantic_candidates,
        # which internally handles expansion for the embedding part.
        candidates = self._get_semantic_candidates(query)
        return candidates[:limit]


    def search_with_ml(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Performs semantic search followed by ML re-ranking.
        Uses query expansion for candidate retrieval.
        """
        # Step 1 & 2: Retrieve initial candidates using semantic search (with expansion)
        candidates = self._get_semantic_candidates(query)

        # Step 3: If ranker model isn't loaded, return results based on semantic score
        if self.ranker.model is None:
            print("WARNING: ML Ranker model not found. Falling back to semantic search results.")
            return candidates[:limit]

        # Step 4: Extract features for all candidates.
        # IMPORTANT: Use the ORIGINAL query for feature extraction to match user intent precisely.
        feature_matrix = np.array([extract_features(p, query) for p in candidates])

        # Step 5: Apply ML ranker to get new scores
        ml_scores = self.ranker.predict(feature_matrix)

        # Step 6: Update relevance scores and re-sort
        for i, product in enumerate(candidates):
            product["relevance_score"] = float(ml_scores[i])

        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Step 7: Return top N results
        return candidates[:limit]