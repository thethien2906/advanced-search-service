# /app/services/feature_extractor.py
import math
from typing import List, Optional
from app.services.search_constants import CATEGORY_KEYWORDS, SUB_REGION_KEYWORDS

def detect_query_categories(query: str) -> List[str]:
    """Returns a list of category UUIDs that match the query keywords."""
    query_lower = query.lower()
    matched_categories = []
    for category_uuid, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in query_lower for keyword in keywords):
            matched_categories.append(category_uuid)
    return matched_categories


def check_category_match(product_category_ids: List[str], query_category_ids: List[str]) -> int:
    """Returns 1 if there's any overlap between product and query categories, 0 otherwise."""
    if not query_category_ids or not product_category_ids:
        return 0
    # Check for intersection between the two lists
    return 1 if any(cat in product_category_ids for cat in query_category_ids) else 0


def check_region_match(product_region: Optional[str], product_sub_region: Optional[str], query_region: Optional[str]) -> int:
    """
    Returns 1 if the product's region OR sub-region matches the detected query region.
    This allows matching at both general and specific levels.
    """
    if not query_region:
        return 0

    # Check for an exact match at the more specific level (SubRegion)
    if product_sub_region and product_sub_region == query_region:
        return 1

    # If no specific match, check for a match at the broader level (Region)
    if product_region and product_region == query_region:
        return 1

    return 0


def extract_features(product_data: dict, query: str) -> List[float]:
    """
    Extracts a feature vector from a single product's database row.
    """
    features = []

    # 1. Semantic Similarity
    features.append(product_data.get("relevance_score", 0.0))

    # 2. Business Metrics
    features.append(float(product_data.get("rating", 0.0)))
    features.append(product_data.get("review_count", 0))
    features.append(product_data.get("sale_count", 0))

    # 3. Price (log-transformed)
    features.append(math.log(product_data.get("price", 0) + 1))

    # 4. Content Richness (Image Count)
    product_images = product_data.get("product_images", [])
    image_count = len(product_images) if isinstance(product_images, list) else 0
    features.append(image_count)

    # 5. Quality Signals
    features.append(1 if product_data.get("is_certified") else 0)
    features.append(1 if product_data.get("store_status") == "Approved" else 0)

    # 6. Category Match
    query_categories = detect_query_categories(query)
    product_categories = product_data.get("category_id", [])
    if not isinstance(product_categories, list):
        product_categories = []
    category_match = check_category_match(product_categories, query_categories)
    features.append(category_match)

    # 7. Region Match
    query_sub_region = detect_query_sub_region(query)
    product_sub_region = product_data.get("sub_region_name")
    region_match = check_region_match(product_sub_region, query_sub_region)
    features.append(region_match)

    return features