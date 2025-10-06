# /app/services/search_service.py
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
import numpy as np
from app.core.config import settings
from app.services.database import DatabaseHandler

class SearchService:
    """
    Handles the business logic for searching products.
    In Phase 3, this is updated to use a real model and database.
    """
    def __init__(self):
        # Per Phase 3 guide, instantiate the database handler
        self.db_handler = DatabaseHandler(settings.DATABASE_URL)
        self.model = None

        # Per Phase 3 guide, load the model on startup and fail fast if it fails.
        try:
            print(f"Loading sentence-transformers model: {settings.MODEL_NAME}...")
            self.model = SentenceTransformer(settings.MODEL_NAME)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"CRITICAL: Failed to load sentence-transformers model: {e}")
            # Re-raising the exception will prevent the FastAPI app from starting
            raise

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Phase 3 implementation: Performs real semantic search.
        1. Generates a normalized query embedding.
        2. Executes the comprehensive SQL query with vector similarity.
        3. Transforms database rows into the required dictionary format.
        """
        if not self.model:
             raise RuntimeError("Search model is not available.")

        # Step 1: Generate and normalize the query embedding
        query_embedding = self.model.encode(query, normalize_embeddings=True)

        # Step 2: Define the comprehensive SQL query from the Phase 3 guide
        # We add `(p."Embedding" <=> %s) AS distance` to get the relevance score.
        sql_query = """
            SELECT
                p."ID", p."Name", p."Rating", p."ReviewCount", p."SaleCount", p."CategoryID", p."ProductImages",
                pv."FinalPrice" AS "price",
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

        # Step 3: Execute the query using the database handler
        # Note: psycopg2 requires the vector to be passed as a string representation of a list
        params = (str(list(query_embedding)),)
        db_results = self.db_handler.execute_query_with_retry(sql_query, params)

        # Step 4: Transform database rows into dictionaries
        results = []
        for row in db_results:
            # Map database columns to the Pydantic model field names
            # Per Phase 3 guide, relevance_score = 1 - cosine_distance
            results.append({
                "id": row[0],
                "name": row[1],
                "rating": float(row[2]), # Ensure correct type from NUMERIC
                "review_count": row[3],
                "sale_count": row[4],
                # category_id and product_images are passed through for Phase 4
                # "category_id": row[5],
                "product_images": row[6],
                "price": row[7],
                "store_status": row[8],
                "is_certified": row[9],
                "relevance_score": 1 - row[10]
            })

        # The final limit is applied here after fetching 100 candidates for ranking (in Phase 4)
        return results[:limit]