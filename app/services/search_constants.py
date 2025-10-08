# /app/services/search_constants.py
"""
This file centralizes all constants used by the search and feature extraction
services, making the codebase cleaner and easier to maintain.
"""

# --- Feature Schema for the ML Ranker ---
FEATURE_SCHEMA = [
    "semantic_similarity",
    "rating",
    "review_count",
    "sale_count",
    "price_log",
    "image_count",
    "is_certified",
    "store_status_approved",
    "category_match",
    "region_match"
]


# --- Rule-based Keyword Mappings for Feature Extraction ---

# Used to detect category intent from a user's query
CATEGORY_KEYWORDS = {
    "food_category_uuid": ["mật ong", "honey", "nước mắm", "fish sauce", "cà phê", "coffee", "bánh", "trà", "đặc sản", "gia vị"],
    "handicraft_category_uuid": ["gốm", "pottery", "thủ công", "handmade", "tranh", "đèn lồng", "mây tre đan"],
    "fashion_category_uuid": ["lụa", "silk", "nón lá", "áo dài", "túi cói", "vải", "thổ cẩm"],
    "jewelry_category_uuid": ["vòng tay", "trang sức", "bạc"],
}

# Used to detect region/location intent from a user's query
REGION_KEYWORDS = {
    "Tây Bắc Bộ": ["tây bắc", "sơn la", "hòa bình", "lai châu", "điện biên"],
    "Đồng bằng sông Hồng": ["hà nội", "miền bắc", "đồng bằng bắc bộ", "hải phòng", "nam định"],
    "Bắc Trung Bộ": ["huế", "thanh hóa", "nghệ an", "quảng trị", "bắc trung bộ", "hà tĩnh"],
    "Tây Nguyên": ["tây nguyên", "đà lạt", "lâm đồng", "gia lai", "đắk lắk", "kon tum"],
    "Đông Nam Bộ": ["sài gòn", "hồ chí minh", "miền đông", "bình phước", "vũng tàu", "bà rịa"],
    "Đồng bằng sông Cửu Long": [
        "miền tây", "miền nam", "cần thơ", "an giang", "bến tre",
        "sóc trăng", "đồng bằng sông cửu long", "phú quốc", "châu đốc"
    ]
}


# --- Query Expansion Dictionary ---

# Used to expand abstract queries into more concrete terms
QUERY_EXPANSION_MAP = {
    "nhậu": ["hải sản khô", "mực một nắng", "khô cá", "lai rai", "rượu", "chua cay"],
    "biếu tặng": ["cao cấp", "sang trọng", "hộp quà", "đặc sản làm quà", "quà biếu"],
    "nấu ăn": ["gia vị", "nêm nếm", "nguyên liệu", "nước chấm"],
    "ăn vặt": ["bánh kẹo", "khô", "mứt", "trái cây sấy"],
}