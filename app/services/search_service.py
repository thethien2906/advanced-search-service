# /app/services/search_service.py
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
import numpy as np
from app.core.config import settings
from app.services.database import DatabaseHandler
from app.services.ranker import XGBoostRanker
from app.services.feature_extractor import extract_features


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

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Phase 4 implementation: Performs semantic search followed by ML re-ranking.
        """
        if not self.model:
            raise RuntimeError("Search model is not available.")

        # Step 1: Generate query embedding
        query_embedding = self.model.encode(query, normalize_embeddings=True)

        # Step 2: Retrieve initial candidates from the database
        sql_query = """
            SELECT
                p."ID", p."Name", p."Rating", p."ReviewCount", p."SaleCount", p."CategoryID", p."ProductImages",
                pv."BasePrice" AS "price",
                s."Status" AS "StoreStatus",
                EXISTS (SELECT 1 FROM "ProductCertificate" pc WHERE pc."ProductID" = p."ID") AS "IsCertified",
                (p."Embedding" <=> %s) AS distance
            FROM "Product" p
            INNER JOIN "ProductVariant" pv ON p."ID" = pv."ProductID"
            INNER JOIN "InventoryProduct" ip ON pv."ID" = ip."ProductVariantID"
            INNER JOIN "Store" s ON p."StoreID" = s."ID"
            WHERE
                ip."Quantity" > 0
                AND p."IsActive" = true
                AND s."Status" = 'Approved'
            ORDER BY
                distance
            LIMIT 100;
        """
        params = (str(list(query_embedding)),)
        db_results = self.db_handler.execute_query_with_retry(sql_query, params)

        # Step 3: Transform DB rows into a list of candidate dictionaries
        candidates = []
        for row in db_results:
            candidates.append({
                "id": row[0],
                "name": row[1],
                "rating": float(row[2]),
                "review_count": row[3],
                "sale_count": row[4],
                "category_id": row[5],
                "product_images": row[6],
                "price": row[7],
                "store_status": row[8],
                "is_certified": row[9],
                "relevance_score": 1 - row[10]
            })

        # Step 4: If ranker model isn't loaded, return results based on semantic score
        if self.ranker.model is None:
            return candidates[:limit]

        # Step 5: Extract features for all candidates
        feature_matrix = np.array([extract_features(p, query) for p in candidates])

        # Step 6: Apply ML ranker to get new scores
        ml_scores = self.ranker.predict(feature_matrix)

        # Step 7: Update relevance scores and re-sort
        for i, product in enumerate(candidates):
            product["relevance_score"] = float(ml_scores[i])

        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Step 8: Return top N results
        return candidates[:limit]