# /app/services/search_service.py (OPTIMIZED VERSION)
import json
import logging
from kafka import KafkaProducer
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
    SUB_REGION_KEYWORDS,
    MINIMUM_RELEVANCE_THRESHOLD
)

logger = logging.getLogger(__name__)

class SearchService:
    """
    Optimized search service using batch queries to eliminate N+1 problem.
    """
    def __init__(self):
        self.db_handler = DatabaseHandler(settings.DATABASE_URL)
        self.model = None
        self.ranker = XGBoostRanker()
        self.all_categories = self._load_categories()

        try:
            logger.info(f"Loading model: {settings.MODEL_NAME}...")
            self.model = SentenceTransformer(settings.MODEL_NAME)
            logger.info("Model loaded successfully.")

            try:
                signal_producer = KafkaProducer(
                    bootstrap_servers=settings.KAFKA_BROKER_URL,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                signal_producer.send(settings.MODEL_READY_TOPIC, value={'status': 'ready'})
                signal_producer.flush()
                signal_producer.close()
                logger.info("✅ Model ready signal sent.")
            except Exception as e:
                logger.warning(f"Could not send model ready signal: {e}")
        except Exception as e:
            logger.critical(f"Failed to load model: {e}")
            raise

    def _load_categories(self) -> List[str]:
        """Load active categories from database."""
        logger.info("Loading product categories...")
        try:
            sql = 'SELECT "Name" FROM "ProductCategory" WHERE "IsActive" = true;'
            results = self.db_handler.execute_query_with_retry(sql)
            categories = [remove_vietnamese_diacritics(row[0].lower()) for row in results]
            logger.info(f"Loaded {len(categories)} categories.")
            return categories
        except Exception as e:
            logger.error(f"Error loading categories: {e}", exc_info=True)
            return []

    def _expand_query(self, query: str) -> str:
        """Expand query with related keywords."""
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
        """Detect regions from query."""
        query_lower = query.lower()

        for sub_region, keywords in SUB_REGION_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                logger.info(f"Detected sub-region: {sub_region}")
                return [sub_region]

        for region, sub_regions in REGION_HIERARCHY.items():
            if region in query_lower:
                logger.info(f"Detected region: {region}")
                return sub_regions

        return None

    # ============================================================================
    # 🚀 NEW: BATCH AGGREGATION - SOLVES N+1 PROBLEM
    # ============================================================================
    def _batch_get_aggregated_features(self, root_ids: List[UUID]) -> Dict[UUID, Dict[str, Any]]:
        """
        🎯 CRITICAL OPTIMIZATION: Fetch aggregated features for ALL roots in ONE query.

        This replaces the N+1 anti-pattern where _get_aggregated_sku_features
        was called inside a loop.

        Complexity: O(N) queries -> O(1) query
        """
        if not root_ids:
            return {}

        # Convert UUIDs to strings for SQL
        root_ids_str = [str(rid) for rid in root_ids]

        sql = """
        WITH RECURSIVE product_tree AS (
            -- Base: Start from all requested roots
            SELECT "ID", "ParentID", "ID" as "RootID"
            FROM "Product"
            WHERE "ID" = ANY(%(root_ids)s::uuid[])

            UNION ALL

            -- Recursive: Get all descendants
            SELECT p."ID", p."ParentID", pt."RootID"
            FROM "Product" p
            JOIN product_tree pt ON p."ParentID" = pt."ID"
        ),
        leaf_skus AS (
            SELECT
                t."RootID",
                pv."FinalPrice",
                pv."SaleCount",
                pv."Rating",
                pv."ReviewCount"
            FROM product_tree t
            JOIN "ProductVariant" pv ON t."ID" = pv."ID"
            JOIN "Product" p_leaf ON t."ID" = p_leaf."ID"
            WHERE
                p_leaf."ProductType" = 'ProductVariant'
                AND p_leaf."IsActive" = true
                AND pv."Quantity" > 0
                AND NOT EXISTS (
                    SELECT 1 FROM "Product" p_child
                    WHERE p_child."ParentID" = t."ID"
                      AND p_child."ProductType" = 'ProductVariant'
                )
        )
        SELECT
            "RootID",
            COALESCE(MIN("FinalPrice"), 0) as min_price,
            COALESCE(SUM("SaleCount"), 0) as sum_sale_count,
            COALESCE(AVG("Rating"), 0.0) as avg_rating,
            COALESCE(SUM("ReviewCount"), 0) as sum_review_count
        FROM leaf_skus
        GROUP BY "RootID"
        """

        params = {"root_ids": root_ids_str}

        try:
            results = self.db_handler.execute_query_with_retry(sql, params)

            # Build lookup dictionary
            feature_map = {}
            for row in results:
                feature_map[row[0]] = {
                    "min_price": row[1],
                    "sum_sale_count": row[2],
                    "avg_rating": float(row[3]),
                    "sum_review_count": row[4]
                }

            # Fill in defaults for roots with no data
            for rid in root_ids:
                if rid not in feature_map:
                    feature_map[rid] = {
                        "min_price": 0,
                        "sum_sale_count": 0,
                        "avg_rating": 0.0,
                        "sum_review_count": 0
                    }

            logger.info(f"✅ Batch fetched features for {len(root_ids)} roots in 1 query")
            return feature_map

        except Exception as e:
            logger.error(f"Error in batch aggregation: {e}", exc_info=True)
            # Return safe defaults
            return {rid: {
                "min_price": 0,
                "sum_sale_count": 0,
                "avg_rating": 0.0,
                "sum_review_count": 0
            } for rid in root_ids}

    # ============================================================================
    # 🚀 NEW: BATCH CERTIFICATION CHECK
    # ============================================================================
    def _batch_get_certifications(self, root_ids: List[UUID]) -> Dict[UUID, bool]:
        """
        🎯 Batch check certifications for all roots in ONE query.

        This replaces calling _get_is_certified in a loop.
        """
        if not root_ids:
            return {}

        root_ids_str = [str(rid) for rid in root_ids]

        sql = """
        WITH RECURSIVE master_roots AS (
            -- Start from requested roots
            SELECT "ID", "ParentID", "ID" as "OriginalID"
            FROM "Product"
            WHERE "ID" = ANY(%(root_ids)s::uuid[])

            UNION ALL

            -- Climb to L1 Master
            SELECT p."ID", p."ParentID", mr."OriginalID"
            FROM "Product" p
            JOIN master_roots mr ON p."ID" = mr."ParentID"
        ),
        l1_masters AS (
            SELECT DISTINCT "ID", "OriginalID"
            FROM master_roots
            WHERE "ParentID" IS NULL
        ),
        certified_products AS (
            SELECT DISTINCT l1."OriginalID"
            FROM l1_masters l1
            JOIN "ProductCertificate" pc ON pc."ProductID" = l1."ID"
            WHERE pc."Status" = 'Approved'
        )
        SELECT "OriginalID", true as is_certified
        FROM certified_products
        """

        params = {"root_ids": root_ids_str}

        try:
            results = self.db_handler.execute_query_with_retry(sql, params)

            # Build lookup set
            certified_set = {row[0] for row in results}

            # Return dict with all roots
            cert_map = {rid: (rid in certified_set) for rid in root_ids}

            logger.info(f"✅ Batch checked certifications for {len(root_ids)} roots")
            return cert_map

        except Exception as e:
            logger.error(f"Error in batch certification: {e}", exc_info=True)
            return {rid: False for rid in root_ids}

    # ============================================================================
    # EXISTING METHODS (kept for compatibility)
    # ============================================================================
    def _get_popular_candidates(
        self,
        limit: int = 20,
        category_filter_ids: Optional[List[UUID]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        province_filters: Optional[List[str]] = None,
        region_filters: Optional[List[str]] = None,
        sub_region_filters: Optional[List[str]] = None,
        sort_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get popular products with filters and sorting."""
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
                AND NOT EXISTS (
                    SELECT 1 FROM "Product" p_child
                    WHERE p_child."ParentID" = p_leaf."ID"
                      AND p_child."ProductType" = 'ProductVariant'
                )
        ),
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
            WHERE pt."ProductType" = 'ProductVariant'
        ),
        valid_display_roots AS (
            SELECT DISTINCT "RootID"
            FROM product_tree
            WHERE "ProductType" != 'ProductVariant'
        ),
        root_stats AS (
            SELECT
                pt."RootID",
                SUM(pt."SaleCount") as "TotalSales",
                AVG(pt."Rating") as "AvgRating",
                MIN(pv."FinalPrice") as "MinPrice"
            FROM product_tree pt
            JOIN valid_display_roots vdr ON pt."RootID" = vdr."RootID"
            JOIN "ProductVariant" pv ON pt."LeafID" = pv."ID"
            GROUP BY pt."RootID"
        )
        SELECT
            P_Goc."ID",
            0.0 AS distance,
            P_Goc."Name" AS "name",
            P_Goc."ProductImages" AS "product_images",
            s."Status" AS "store_status",
            ARRAY_REMOVE(ARRAY[pc."Name", pc_parent."Name"], NULL) as "category_names",
            pr."RegionSpecified" AS "sub_region_name",
            pr."Name" AS "province_name",
            pr."Region" AS "region_name",
            P_Goc."CreatedAt" AS "createdAt",
            rs."TotalSales",
            rs."AvgRating",
            rs."MinPrice"
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
        """

        where_clauses = []
        params = {"limit": limit}

        # Filter by category IDs if provided
        if category_filter_ids:
            category_ids_str = [str(cid) for cid in category_filter_ids]
            where_clauses.append('(pc."ID" = ANY(%(category_ids)s::uuid[]) OR pc_parent."ID" = ANY(%(category_ids)s::uuid[]))')
            params["category_ids"] = category_ids_str

        # Filter by price range
        if min_price is not None:
            where_clauses.append('rs."MinPrice" >= %(min_price)s')
            params["min_price"] = min_price

        if max_price is not None:
            where_clauses.append('rs."MinPrice" <= %(max_price)s')
            params["max_price"] = max_price

        # Filter by province
        if province_filters and len(province_filters) > 0:
            where_clauses.append('pr."Name" = ANY(%(province_filters)s)')
            params["province_filters"] = province_filters

        # Filter by region
        if region_filters and len(region_filters) > 0:
            where_clauses.append('pr."Region" = ANY(%(region_filters)s)')
            params["region_filters"] = region_filters

        # Filter by sub-region
        if sub_region_filters and len(sub_region_filters) > 0:
            where_clauses.append('pr."RegionSpecified" = ANY(%(sub_region_filters)s)')
            params["sub_region_filters"] = sub_region_filters

        if where_clauses:
            sql += " AND " + " AND ".join(where_clauses)

        # Dynamic ORDER BY based on sort_by parameter
        order_clause = ""
        if sort_by == "newest":
            order_clause = 'ORDER BY P_Goc."CreatedAt" DESC'
        elif sort_by == "best-selling":
            order_clause = 'ORDER BY rs."TotalSales" DESC'
        elif sort_by == "rating":
            order_clause = 'ORDER BY rs."AvgRating" DESC'
        elif sort_by == "price-asc":
            order_clause = 'ORDER BY rs."MinPrice" ASC'
        elif sort_by == "price-desc":
            order_clause = 'ORDER BY rs."MinPrice" DESC'
        else:
            # Default: by popularity (sales and rating)
            order_clause = 'ORDER BY rs."TotalSales" DESC, rs."AvgRating" DESC'

        sql += f" {order_clause} LIMIT %(limit)s;"

        try:
            db_results = self.db_handler.execute_query_with_retry(sql, params)
            candidates = []
            for row in db_results:
                candidates.append({
                    "id": row[0],
                    "relevance_score": 0.0,
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

    def _get_semantic_candidates(
        self,
        query: str,
        category_filter_ids: Optional[List[UUID]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        province_filters: Optional[List[str]] = None,
        region_filters: Optional[List[str]] = None,
        sub_region_filters: Optional[List[str]] = None,
        sort_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get semantic search candidates with filters and sorting."""
        if not self.model:
            raise RuntimeError("Search model not available.")

        expanded_query = self._expand_query(query)
        query_embedding = self.model.encode(expanded_query, normalize_embeddings=True)

        base_sql = """
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
                AND NOT EXISTS (
                    SELECT 1 FROM "Product" p_child
                    WHERE p_child."ParentID" = p_leaf."ID"
                      AND p_child."ProductType" = 'ProductVariant'
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
            WHERE dr."ProductType" = 'ProductVariant'
        ),
        valid_display_roots AS (
            SELECT DISTINCT "ID"
            FROM display_root_cte
            WHERE "ProductType" != 'ProductVariant'
        ),
        root_stats AS (
            SELECT
                vdr."ID" as "RootID",
                SUM(vls."SaleCount") as "TotalSales",
                AVG(vls."Rating") as "AvgRating",
                MIN(pv."FinalPrice") as "MinPrice"
            FROM valid_display_roots vdr
            JOIN valid_leaf_skus vls ON vls."ParentID" IN (
                SELECT "ID" FROM display_root_cte
                WHERE display_root_cte."ID" = vdr."ID"
                   OR display_root_cte."ParentID" = vdr."ID"
            )
            JOIN "ProductVariant" pv ON vls."ID" = pv."ID"
            GROUP BY vdr."ID"
        )
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
            P_Goc."CreatedAt" AS "createdAt",
            rs."TotalSales",
            rs."AvgRating",
            rs."MinPrice"
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
        """

        where_clauses = []
        params = {"query_embedding": str(list(query_embedding))}

        # Filter by category IDs if provided
        if category_filter_ids:
            category_ids_str = [str(cid) for cid in category_filter_ids]
            where_clauses.append('(pc."ID" = ANY(%(category_ids)s::uuid[]) OR pc_parent."ID" = ANY(%(category_ids)s::uuid[]))')
            params["category_ids"] = category_ids_str

        # Filter by price range
        if min_price is not None:
            where_clauses.append('rs."MinPrice" >= %(min_price)s')
            params["min_price"] = min_price

        if max_price is not None:
            where_clauses.append('rs."MinPrice" <= %(max_price)s')
            params["max_price"] = max_price

        # Filter by province
        if province_filters and len(province_filters) > 0:
            where_clauses.append('pr."Name" = ANY(%(province_filters)s)')
            params["province_filters"] = province_filters

        # Filter by region
        if region_filters and len(region_filters) > 0:
            where_clauses.append('pr."Region" = ANY(%(region_filters)s)')
            params["region_filters"] = region_filters

        # Filter by sub-region (check both explicit filters and query-based detection)
        detected_regions = self._get_regions_for_sql_filter(query)
        if sub_region_filters and len(sub_region_filters) > 0:
            where_clauses.append('pr."RegionSpecified" = ANY(%(sub_region_filters)s)')
            params["sub_region_filters"] = sub_region_filters
        elif detected_regions:
            where_clauses.append('pr."RegionSpecified" = ANY(%(regions)s)')
            params["regions"] = detected_regions

        final_sql = base_sql
        if where_clauses:
            final_sql += " AND " + " AND ".join(where_clauses)

        # Dynamic ORDER BY based on sort_by parameter
        if sort_by == "newest":
            final_sql += ' ORDER BY P_Goc."CreatedAt" DESC;'
        elif sort_by == "best-selling":
            final_sql += ' ORDER BY rs."TotalSales" DESC;'
        elif sort_by == "rating":
            final_sql += ' ORDER BY rs."AvgRating" DESC;'
        elif sort_by == "price-asc":
            final_sql += ' ORDER BY rs."MinPrice" ASC;'
        elif sort_by == "price-desc":
            final_sql += ' ORDER BY rs."MinPrice" DESC;'
        else:
            # Default: by relevance (distance)
            final_sql += " ORDER BY distance ASC;"

        db_results = self.db_handler.execute_query_with_retry(final_sql, params)

        candidates = []
        for row in db_results:
            # Handle None distance (when embedding is NULL - products not yet seeded)
            distance = row[1] if row[1] is not None else 999999.0
            candidates.append({
                "id": row[0],
                "relevance_score": float(distance),
                "name": row[2],
                "product_images": row[3] or [],
                "store_status": row[4],
                "category_names": row[5] or [],
                "sub_region_name": row[6],
                "province_name": row[7],
                "region_name": row[8],
                "createdAt": row[9]
            })

        # Filter by minimum relevance threshold if query is provided
        if query and query.strip():
            candidates = [c for c in candidates if (1.0 - c["relevance_score"]) >= MINIMUM_RELEVANCE_THRESHOLD]
            logger.info(f"Filtered to {len(candidates)} candidates above relevance threshold {MINIMUM_RELEVANCE_THRESHOLD}")

        # Only sort by relevance_score if no sort_by is specified
        # Otherwise, preserve the order from SQL (already sorted by sort_by parameter)
        if sort_by is None:
            candidates.sort(key=lambda x: x["relevance_score"], reverse=False)
            logger.info("Sorted by relevance_score (distance ascending)")
        else:
            logger.info(f"Preserving SQL sort order (sort_by={sort_by})")

        return candidates[:100]

    # ============================================================================
    # 🚀 OPTIMIZED: search_semantic - Uses batch queries
    # ============================================================================
    def search_semantic(
        self,
        query: str,
        limit: int = 20,
        category_filter_ids: Optional[List[UUID]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        province_filters: Optional[List[str]] = None,
        region_filters: Optional[List[str]] = None,
        sub_region_filters: Optional[List[str]] = None,
        sort_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Optimized semantic search using batch queries with filters and sorting.

        BEFORE: O(N) queries for aggregation
        AFTER:  O(1) query for all aggregations
        """
        # Get candidates
        if not query or not query.strip():
            logger.info("Empty query. Fetching popular products.")
            candidates = self._get_popular_candidates(
                limit, category_filter_ids, min_price, max_price,
                province_filters, region_filters, sub_region_filters, sort_by
            )
        else:
            candidates = self._get_semantic_candidates(
                query, category_filter_ids, min_price, max_price,
                province_filters, region_filters, sub_region_filters, sort_by
            )

        if not candidates:
            return []

        # Apply minimum relevance threshold for non-empty queries
        if query and query.strip():
            original_count = len(candidates)
            candidates = [c for c in candidates if (1.0 - c["relevance_score"]) >= MINIMUM_RELEVANCE_THRESHOLD]
            if len(candidates) < original_count:
                logger.info(f"Filtered from {original_count} to {len(candidates)} candidates using threshold {MINIMUM_RELEVANCE_THRESHOLD}")

            if not candidates:
                logger.info("No candidates met the minimum relevance threshold.")
                return []

        logger.info(f"Got {len(candidates)} candidates. Starting batch enrichment...")

        # 🚀 CRITICAL: Batch fetch ALL features in ONE query
        root_ids = [p["id"] for p in candidates]
        feature_map = self._batch_get_aggregated_features(root_ids)

        # Enrich results using the pre-fetched feature map
        enriched_results = []
        for p_candidate in candidates:
            root_id = p_candidate["id"]
            agg_features = feature_map.get(root_id, {
                "min_price": 0,
                "sum_sale_count": 0,
                "avg_rating": 0.0,
                "sum_review_count": 0
            })

            created_at_iso = None
            if p_candidate.get("createdAt") and hasattr(p_candidate["createdAt"], 'isoformat'):
                try:
                    created_at_iso = p_candidate["createdAt"].isoformat()
                except Exception as e:
                    logger.warning(f"Cannot format date: {e}")

            enriched_product = {
                "id": p_candidate["id"],
                "name": p_candidate["name"],
                "price": float(agg_features["min_price"]),
                "rating": agg_features["avg_rating"],
                "review_count": agg_features["sum_review_count"],
                "sale_count": agg_features["sum_sale_count"],
                "store_status": p_candidate["store_status"],
                "product_images": p_candidate["product_images"] or [],
                "relevance_score": 1.0 - p_candidate["relevance_score"],
                "category_names": p_candidate["category_names"] or [],
                "province_name": p_candidate["province_name"],
                "region_name": p_candidate["region_name"],
                "sub_region_name": p_candidate["sub_region_name"],
                "createdAt": created_at_iso
            }
            enriched_results.append(enriched_product)

        # Only sort by relevance_score if no sort_by is specified
        # Otherwise, preserve the order from candidates (already sorted by SQL)
        if sort_by is None:
            enriched_results.sort(key=lambda x: x["relevance_score"], reverse=True)
            logger.info("Sorted by relevance_score (similarity descending)")
        else:
            logger.info(f"Preserving order from SQL (sort_by={sort_by})")

        logger.info(f"✅ Enrichment complete. Returning {min(limit, len(enriched_results))} results.")

        return enriched_results[:limit]

    # ============================================================================
    # �� OPTIMIZED: search_with_ml - Uses batch queries
    # ============================================================================
    def search_with_ml(
        self,
        query: str,
        limit: int = 20,
        category_filter_ids: Optional[List[UUID]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        province_filters: Optional[List[str]] = None,
        region_filters: Optional[List[str]] = None,
        sub_region_filters: Optional[List[str]] = None,
        sort_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Optimized ML search using batch queries with filters and sorting.

        PERFORMANCE GAIN: 100x faster for 100 candidates
        - BEFORE: 100 queries for features + 100 queries for certs = 200 queries
        - AFTER:  1 query for features + 1 query for certs = 2 queries
        """
        if not query or not query.strip():
            logger.info("Empty query. Using popular products (no ML).")
            return self.search_semantic(
                query, limit, category_filter_ids, min_price, max_price,
                province_filters, region_filters, sub_region_filters, sort_by
            )

        candidates = self._get_semantic_candidates(
            query, category_filter_ids, min_price, max_price,
            province_filters, region_filters, sub_region_filters, sort_by
        )
        if not candidates:
            return []

        # Apply minimum relevance threshold
        original_count = len(candidates)
        candidates = [c for c in candidates if (1.0 - c["relevance_score"]) >= MINIMUM_RELEVANCE_THRESHOLD]
        if len(candidates) < original_count:
            logger.info(f"Filtered from {original_count} to {len(candidates)} candidates using threshold {MINIMUM_RELEVANCE_THRESHOLD}")

        if not candidates:
            logger.info("No candidates met the minimum relevance threshold.")
            return []

        if self.ranker.model is None:
            logger.warning("ML Ranker not available. Falling back to semantic.")
            for p in candidates:
                p["relevance_score"] = 1.0 - p["relevance_score"]

            # Only sort by relevance_score if no sort_by is specified
            if sort_by is None:
                candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
                logger.info("Sorted by relevance_score (fallback)")
            else:
                logger.info(f"Preserving SQL sort order (sort_by={sort_by}, fallback mode)")

            return candidates[:limit]

        logger.info(f"Got {len(candidates)} candidates. Starting batch feature extraction...")

        # 🚀 BATCH FETCH: Get ALL features and certifications in 2 queries
        root_ids = [p["id"] for p in candidates]
        feature_map = self._batch_get_aggregated_features(root_ids)
        cert_map = self._batch_get_certifications(root_ids)

        # Extract features for ML model
        feature_matrix = []
        for p_candidate in candidates:
            root_id = p_candidate["id"]
            agg_features = feature_map[root_id]
            is_certified = cert_map[root_id]

            combined_data = {
                "relevance_score": 1.0 - p_candidate["relevance_score"],
                "name": p_candidate["name"],
                "product_images": p_candidate["product_images"],
                "store_status": p_candidate["store_status"],
                "category_names": p_candidate["category_names"],
                "sub_region_name": p_candidate["sub_region_name"],
                "price": agg_features["min_price"],
                "sale_count": agg_features["sum_sale_count"],
                "rating": agg_features["avg_rating"],
                "review_count": agg_features["sum_review_count"],
                "is_certified": True
            }

            features = extract_features(combined_data, query, self.all_categories)
            feature_matrix.append(features)

        try:
            # ML Ranking
            feature_matrix = np.array(feature_matrix)
            ml_scores = self.ranker.predict(feature_matrix)

            # Update scores
            for i, product in enumerate(candidates):
                product["relevance_score"] = float(ml_scores[i])
                # Clean up unnecessary fields
                del product["name"]
                del product["product_images"]
                del product["store_status"]
                del product["category_names"]
                del product["sub_region_name"]

            candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
            logger.info(f"✅ ML ranking complete. Returning {min(limit, len(candidates))} results.")

            return candidates[:limit]

        except Exception as e:
            logger.error(f"ML ranking error: {e}", exc_info=True)
            for p in candidates:
                p["relevance_score"] = 1.0 - p["relevance_score"]

            # Only sort by relevance_score if no sort_by is specified
            if sort_by is None:
                candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
                logger.info("Sorted by relevance_score (error fallback)")
            else:
                logger.info(f"Preserving SQL sort order (sort_by={sort_by}, error fallback)")

            return candidates[:limit]

    def search_documents(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search documents (unchanged)."""
        if not self.model:
            raise RuntimeError("Model not loaded.")

        embedding_service = EmbeddingService()
        query_vector = embedding_service.create_text_embedding(query)

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
            documents = []
            for row in results:
                 documents.append({
                    "id": row[0],
                    "title": row[1],
                    "content": row[2][:500] if row[2] else "",
                    "slug": row[3],
                    "relevance_score": 1 - float(row[4]),
                    "type": "Document"
                })
            return documents
        except Exception as e:
            logger.error(f"Document search error: {e}", exc_info=True)
            return []