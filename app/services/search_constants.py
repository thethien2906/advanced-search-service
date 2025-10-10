# /app/services/search_constants.py
"""
This file centralizes all constants used by the search and feature extraction
services, making the codebase cleaner and easier to maintain.
"""

# --- Feature Schema for the ML Ranker ---
FEATURE_SCHEMA = [
    "semantic_similarity",
    "unaccented_name_match",
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


QUERY_EXPANSION_MAP = {
    # ======================================================================
    # PHIÊN BẢN CÓ DẤU - DÀNH CHO TRUY VẤN TIẾNG VIỆT CHUẨN
    # ======================================================================

    # Tụ tập, ăn uống cùng bạn bè
    "nhậu": ["lai rai", "bạn bè", "cuối tuần", "món nhắm", "đậm vị", "cay nồng"],

    # Mua quà, biếu tặng
    "biếu tặng": [
        "cao cấp", "sang trọng", "lịch sự", "ý nghĩa", "hộp quà",
        "doanh nghiệp", "gia đình", "người thân", "truyền thống"
    ],

    # Phục vụ nấu nướng hàng ngày
    "nấu ăn": ["gia vị", "nêm nếm", "nguyên liệu", "hương vị", "đậm đà", "bữa cơm", "nhà bếp"],

    # Ăn vặt, giải trí
    "ăn vặt": ["buồn miệng", "thư giãn", "giòn", "ngọt", "mặn mà", "xem phim"],

    # Chăm sóc sức khỏe
    "sức khỏe": ["bồi bổ", "dinh dưỡng", "tự nhiên", "nguyên chất", "thanh lọc", "người lớn tuổi"],

    # Mua sắm khi đi du lịch
    "du lịch": ["mang về", "kỷ niệm", "vùng miền", "đặc trưng", "khám phá"],

    # ======================================================================
    # PHIÊN BẢN KHÔNG DẤU - ĐỒNG BỘ VỚI PHIÊN BẢN CÓ DẤU
    # ======================================================================

    "nhau": ["lai rai", "ban be", "cuoi tuan", "mon nham", "dam vi", "cay nong"],

    "bieu tang": [
        "cao cap", "sang trong", "lich su", "y nghia", "hop qua",
        "doanh nghiep", "gia dinh", "nguoi than", "truyen thong"
    ],

    "nau an": ["gia vi", "nem nem", "nguyen lieu", "huong vi", "dam da", "bua com", "nha bep"],

    "an vat": ["buon mieng", "thu gian", "gion", "ngot", "man ma", "xem phim"],

    "suc khoe": ["boi bo", "dinh duong", "tu nhien", "nguyen chat", "thanh loc", "nguoi lon tuoi"],

    "du lich": ["mang ve", "ky niem", "vung mien", "dac trung", "kham pha"],
}
SUB_REGION_KEYWORDS = {
    # --- MIỀN BẮC ---
    "Tây Bắc Bộ": [
        "tây bắc", "tay bac",
        "hòa bình", "hoa binh", "sơn la", "son la", "điện biên", "dien bien",
        "lai châu", "lai chau", "lào cai", "lao cai", "yên bái", "yen bai"
    ],
    "Đông Bắc Bộ": [
        "đông bắc", "dong bac",
        "hà giang", "ha giang", "cao bằng", "cao bang", "bắc kạn", "bac can",
        "lạng sơn", "lang son", "tuyên quang", "tuyen quang", "thái nguyên", "thai nguyen",
        "phú thọ", "phu tho", "bắc giang", "bac giang", "quảng ninh", "quang ninh"
    ],
    "Đồng bằng sông Hồng": [
        "đồng bằng sông hồng", "dong bang song hong", "đồng bằng bắc bộ",
        "hà nội", "ha noi", "bắc ninh", "bac ninh", "hà nam", "ha nam",
        "hải dương", "hai duong", "hải phòng", "hai phong", "hưng yên", "hung yen",
        "nam định", "nam dinh", "ninh bình", "ninh binh", "thái bình", "thai binh",
        "vĩnh phúc", "vinh phuc"
    ],

    # --- MIỀN TRUNG ---
    "Bắc Trung Bộ": [
        "bắc trung bộ", "bac trung bo",
        "thanh hóa", "thanh hoa", "nghệ an", "nghe an", "hà tĩnh", "ha tinh",
        "quảng bình", "quang binh", "quảng trị", "quang tri", "thừa thiên huế", "thua thien hue", "huế"
    ],
    "Duyên hải Nam Trung Bộ": [
        "duyên hải nam trung bộ", "duyen hai nam trung bo",
        "đà nẵng", "da nang", "quảng nam", "quang nam", "quảng ngãi", "quang ngai",
        "bình định", "binh dinh", "phú yên", "phu yen", "khánh hòa", "khanh hoa",
        "ninh thuận", "ninh thuan", "bình thuận", "binh thuan"
    ],
    "Tây Nguyên": [
        "tây nguyên", "tay nguyen",
        "kon tum", "gia lai", "đắk lắk", "dak lak", "đắc nông", "đắk nông", "dak nong",
        "lâm đồng", "lam dong", "đà lạt", "da lat"
    ],

    # --- MIỀN NAM ---
    "Đông Nam Bộ": [
        "đông nam bộ", "dong nam bo", "miền đông", "mien dong",
        "bình phước", "binh phuoc", "bình dương", "binh duong", "đồng nai", "dong nai",
        "tây ninh", "tay ninh", "bà rịa vũng tàu", "ba ria vung tau", "vũng tàu", "vung tau",
        "thành phố hồ chí minh", "ho chi minh", "hcm", "sài gòn", "sai gon"
    ],
    "Đồng bằng sông Cửu Long": [
        "đồng bằng sông cửu long", "dong bang song cuu long", "miền tây", "mien tay",
        "cần thơ", "can tho", "long an", "tiền giang", "tien giang", "bến tre", "ben tre",
        "vĩnh long", "vinh long", "trà vinh", "tra vinh", "hậu giang", "hau giang",
        "sóc trăng", "soc trang", "đồng tháp", "dong thap", "an giang",
        "kiên giang", "kien giang", "phú quốc", "phu quoc", "bạc liêu", "bac lieu",
        "cà mau", "ca mau"
    ]
}

REGION_HIERARCHY = {
    "miền bắc": ["Tây Bắc Bộ", "Đồng bằng sông Hồng", "Đông Bắc Bộ"],
    "miền trung": ["Bắc Trung Bộ", "Tây Nguyên", "Duyên Hải Nam Trung Bộ"],
    "miền nam": ["Đông Nam Bộ", "Đồng bằng sông Cửu Long"]
}


GIFT_INTENT_KEYWORDS = [
    "quà", "biếu", "tặng", "tết", "người thân", "gia đình", "đồng nghiệp"
]

GIFT_CATEGORY_NAMES = [
    "Bánh, Mứt & Kẹo truyền thống",
    "Gốm sứ nghệ thuật",
    "Sản phẩm từ Vải & Lụa tơ tằm",
    "Sơn mài truyền thống",
    "Trang sức & Phụ kiện thủ công",
    "Đồ trang trí & Quà tặng",
    "Thực phẩm chế biến & Khô",
    "Cà phê, Trà & Đồ uống",
    "Mật ong & Sản phẩm từ ong"
]