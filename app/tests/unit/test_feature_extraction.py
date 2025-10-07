# /app/tests/unit/test_feature_extraction.py

from app.services.feature_extractor import extract_features, FEATURE_SCHEMA

def test_extract_features_basic():
    """
    Tests feature extraction with a standard, valid product dictionary.
    """
    product_data = {
        "relevance_score": 0.85,
        "rating": 4.5,
        "review_count": 100,
        "sale_count": 500,
        "price": 250000,
        "product_images": ["img1.jpg", "img2.jpg"],
        "is_certified": True,
        "store_status": "Approved",
        "category_id": ["food_category_uuid"]
    }
    query = "mật ong thơm ngon" # "mật ong" is a keyword for food_category_uuid

    features = extract_features(product_data, query)

    # Ensure the feature vector has the correct number of features
    assert len(features) == len(FEATURE_SCHEMA)

    # Check specific feature values
    assert features[FEATURE_SCHEMA.index("semantic_similarity")] == 0.85
    assert features[FEATURE_SCHEMA.index("rating")] == 4.5
    assert features[FEATURE_SCHEMA.index("image_count")] == 2
    assert features[FEATURE_SCHEMA.index("is_certified")] == 1
    assert features[FEATURE_SCHEMA.index("store_status_approved")] == 1
    assert features[FEATURE_SCHEMA.index("category_match")] == 1

def test_extract_features_handles_nulls_and_missing_data():
    """
    Tests that feature extraction gracefully handles NULLs (None) and edge cases.
    """
    product_data = {
        "relevance_score": 0.7,
        "rating": 0.0,
        "review_count": 0,
        "sale_count": 0,
        "price": 50000,
        "product_images": None,   # NULL case
        "is_certified": False,
        "store_status": "Pending",
        "category_id": None       # NULL case
    }
    query = "some random query with no category"

    features = extract_features(product_data, query)

    assert len(features) == len(FEATURE_SCHEMA)

    # Check features that should be 0 due to missing data or status
    assert features[FEATURE_SCHEMA.index("image_count")] == 0
    assert features[FEATURE_SCHEMA.index("is_certified")] == 0
    assert features[FEATURE_SCHEMA.index("store_status_approved")] == 0
    assert features[FEATURE_SCHEMA.index("category_match")] == 0

def test_extract_features_no_category_match():
    """
    Tests that category_match is 0 when the query keywords do not match the product's category.
    """
    product_data = {
        "relevance_score": 0.9,
        "rating": 5.0,
        "review_count": 10,
        "sale_count": 20,
        "price": 100000,
        "product_images": ["img1.jpg"],
        "is_certified": True,
        "store_status": "Approved",
        "category_id": ["fashion_category_uuid"] # Product is fashion
    }
    # Query is for food
    query = "mua nước mắm"

    features = extract_features(product_data, query)

    assert features[FEATURE_SCHEMA.index("category_match")] == 0