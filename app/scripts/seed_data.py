import os
import sys
import psycopg2
import uuid
import random
import json
from faker import Faker
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.embedding_service import EmbeddingService
from app.models.pydantic_models import EnhancedEmbeddingRequest

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")
NUM_PRODUCTS = 50

# --- DỮ LIỆU CỬA HÀNG MẪU (ID ĐÃ ĐƯỢC CHUẨN HÓA) ---
SAMPLE_STORES_DATA = [
    {
        "name": "Tinh Hoa Đất Bắc", "story": "Chúng tôi đi khắp các làng nghề miền Bắc để mang về những sản phẩm thủ công và đặc sản đậm đà bản sắc, từ gốm Bát Tràng đến lụa Vạn Phúc.",
        "province": "Thành phố Hà Nội", "district": "Quận Hoàn Kiếm", "ward": "Phường Hàng Trống",
        "province_id": 1, "ward_id": 7, "region": "Đồng bằng sông Hồng"
    },
    {
        "name": "Hồn Việt Xứ Huế", "story": "Nơi hội tụ những sản phẩm tinh xảo của vùng đất Cố đô, từ nón lá bài thơ, đặc sản cung đình cho đến các loại trà thảo dược.",
        "province": "Tỉnh Thừa Thiên Huế", "district": "Thành phố Huế", "ward": "Phường Phú Hội",
        "province_id": 46, "ward_id": 9078, "region": "Bắc Trung Bộ"
    },
    {
        "name": "Hương Vị Phương Nam", "story": "Khám phá sự trù phú của miền Tây sông nước qua các loại trái cây sấy dẻo, bánh kẹo dân gian và những sản phẩm từ dừa Bến Tre.",
        "province": "Thành phố Hồ Chí Minh", "district": "Quận 1", "ward": "Phường Bến Nghé",
        "province_id": 79, "ward_id": 27883, "region": "Đông Nam Bộ"
    },
    {
        "name": "Gió Đại Ngàn Tây Nguyên", "story": "Mang hương vị của núi rừng Tây Nguyên đến mọi nhà, từ cà phê Robusta trứ danh, hạt tiêu Chư Sê đến mật ong hoa rừng nguyên chất.",
        "province": "Tỉnh Đắk Lắk", "district": "Thành phố Buôn Ma Thuột", "ward": "Phường Thắng Lợi",
        "province_id": 66, "ward_id": 24088, "region": "Tây Nguyên"
    }
]

# --- DỮ LIỆU SẢN PHẨM MẪU (PHONG PHÚ HƠN) ---
PRODUCT_NAME_MODIFIERS = ["Thượng hạng", "Đặc biệt", "Truyền thống", "Làng nghề", "Xuất khẩu", "Tinh tuyển", "Nguyên bản"]
SAMPLE_PRODUCTS_DATA = [
    {"name": "Phở bò gia truyền", "desc": "Nước dùng được ninh từ xương bò trong 8 tiếng, bánh phở mềm mại, thịt bò thái mỏng.", "category": "Thực phẩm", "story_title": "Tinh hoa ẩm thực Thủ đô", "story_detail": "Bát phở không chỉ là một món ăn, mà là cả một câu chuyện văn hóa được truyền qua nhiều thế hệ của người Hà Nội.", "made_by": "Xương bò và gia vị quế hồi", "type_name": "Món ăn"},
    {"name": "Bún chả que tre", "desc": "Thịt ba chỉ và chả băm được nướng trên than hoa và kẹp bằng que tre, tạo nên hương vị khói đặc trưng.", "category": "Thực phẩm", "story_title": "Hương vị Hà Nội xưa", "story_detail": "Mùi thơm của thịt nướng lan tỏa khắp con ngõ nhỏ là ký ức không thể quên của nhiều người con xa xứ.", "made_by": "Thịt heo và than hoa", "type_name": "Món ăn"},
    {"name": "Bánh Pía sầu riêng trứng muối", "desc": "Vỏ bánh ngàn lớp mỏng tang, nhân sầu riêng thơm lừng hòa quyện cùng vị bùi mặn của trứng muối.", "category": "Thực phẩm", "story_title": "Ngọt ngào hương vị miền Tây", "story_detail": "Chiếc bánh là sự kết hợp hoàn hảo giữa vị ngọt của trái cây nhiệt đới và kỹ thuật làm bánh gia truyền của người Hoa.", "made_by": "Sầu riêng và trứng muối", "type_name": "Bánh kẹo"},
    {"name": "Hạt điều rang muối", "desc": "Hạt điều loại A, được rang củi thủ công cùng muối biển tinh khiết, giữ trọn vị ngọt bùi tự nhiên.", "category": "Thực phẩm", "story_title": "Quà tặng từ vùng đất đỏ bazan", "story_detail": "Mỗi hạt điều đều được tuyển chọn kỹ lưỡng, là thành quả lao động của người nông dân trên vùng đất bazan màu mỡ.", "made_by": "Hạt điều", "type_name": "Nông sản khô"},
    {"name": "Nước mắm nhỉ cá cơm", "desc": "Những giọt nước mắm tinh túy được chắt lọc từ cá cơm tươi và muối biển, ủ chượp theo phương pháp truyền thống.", "category": "Thực phẩm", "story_title": "Giọt vàng của biển cả", "story_detail": "Hơn một năm trời ủ chượp trong thùng gỗ đã tạo ra thứ nước mắm có màu hổ phách và hương vị đậm đà không thể sánh bằng.", "made_by": "Cá cơm và muối biển", "type_name": "Gia vị"},
    {"name": "Bộ ấm chén gốm men lam", "desc": "Sản phẩm được làm thủ công từ đất sét cao lanh, nung ở nhiệt độ cao và vẽ tay họa tiết hoa sen tinh xảo.", "category": "Thủ công mỹ nghệ", "story_title": "Nghệ thuật từ đất và lửa", "story_detail": "Đôi bàn tay của người nghệ nhân Bát Tràng đã thổi hồn vào đất, tạo nên những sản phẩm vừa có giá trị sử dụng, vừa có giá trị nghệ thuật.", "made_by": "Đất sét và men lam", "type_name": "Đồ gốm"},
    {"name": "Khăn choàng lụa tơ tằm", "desc": "Dệt từ 100% sợi tơ tằm tự nhiên, khăn lụa mềm mại, óng ả và giữ ấm tốt. Họa tiết được thêu tay tỉ mỉ.", "category": "Thời trang", "story_title": "Sự mềm mại từ sợi tơ vàng", "story_detail": "Làng lụa Vạn Phúc với lịch sử hơn ngàn năm tuổi vẫn giữ được nét đẹp truyền thống trong từng sản phẩm.", "made_by": "Tơ tằm tự nhiên", "type_name": "Phụ kiện"},
    {"name": "Đèn lồng tre trang trí", "desc": "Khung đèn làm từ tre vót chuốt kỹ lưỡng, bọc vải lụa Hà Đông với nhiều màu sắc rực rỡ, biểu tượng của phố cổ.", "category": "Thủ công mỹ nghệ", "story_title": "Ánh sáng từ phố cổ", "story_detail": "Mỗi chiếc đèn lồng không chỉ để thắp sáng mà còn mang theo lời chúc bình an, may mắn, là biểu tượng của Hội An.", "made_by": "Tre và vải lụa", "type_name": "Trang trí"},
    {"name": "Cà phê Robusta", "desc": "Hạt cà phê Robusta được trồng và thu hoạch thủ công tại Buôn Ma Thuột, rang mộc để giữ lại hương vị đậm đắng nguyên bản.", "category": "Thực phẩm", "story_title": "Năng lượng từ đại ngàn", "story_detail": "Cà phê không chỉ là thức uống, đó là một phần văn hóa và niềm tự hào của người dân Tây Nguyên.", "made_by": "Hạt cà phê Robusta", "type_name": "Đồ uống"},
    {"name": "Trà sen Tây Hồ", "desc": "Trà xanh Thái Nguyên được ướp trong những bông sen Bách Diệp của Hồ Tây theo phương pháp cổ truyền, tạo ra hương thơm thanh khiết.", "category": "Thực phẩm", "story_title": "Quốc ẩm Việt Nam", "story_detail": "Sự kỳ công của việc ướp trà sen đã tạo nên một sản vật quý giá, là món quà sang trọng và đầy ý nghĩa.", "made_by": "Trà xanh và hoa sen", "type_name": "Đồ uống"}
]

def get_db_connection():
    # ... (giữ nguyên hàm này)
    print("Connecting to the database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("Database connection successful.")
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to database: {e}")
        exit(1)

def seed_database():
    conn = get_db_connection()
    cur = conn.cursor()
    fake = Faker('vi_VN')

    print("Initializing Embedding Service...")
    embedding_service = EmbeddingService()
    print("Service initialized.")

    try:
        print("\n--- Starting Database Seeding ---")
        print("Cleaning up old data (Products, Stores, Sellers)...")
        tables_to_clear = [
            "ProductCertificate", "ProductStoryContent", "ProductStory", "InventoryProduct", "ProductVariant",
            "Product", "Store", "Seller", "User"
        ]
        for table in tables_to_clear:
            cur.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
        print("Cleanup complete.")

        print(f"Creating {len(SAMPLE_STORES_DATA)} sellers and stores from sample data...")
        created_stores = []
        for store_data in SAMPLE_STORES_DATA:
            user_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO "User" ("ID", "Email", "Password", "PhoneNumber", "Role", "FirstName", "LastName") VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (user_id, fake.email(), 'hashed_password', f"09{random.randint(10000000, 99999999)}", 'Seller', fake.first_name(), fake.last_name())
            )
            cur.execute(
                'INSERT INTO "Seller" ("UserID", "BusinessName", "SellerStatus") VALUES (%s, %s, %s)',
                (user_id, store_data["name"], 'Approved')
            )
            store_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO "Store" ("ID", "SellerID", "StoreName", "Province", "District", "Ward", "ProvinceID", "WardID", "Status") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (store_id, user_id, store_data["name"], store_data["province"], store_data["district"], store_data["ward"], store_data["province_id"], store_data["ward_id"], 'Approved')
            )
            store_info = {**store_data, "id": store_id}
            created_stores.append(store_info)
        print("Sellers and stores created.")

        print(f"Generating and inserting {NUM_PRODUCTS} products...")
        for i in range(NUM_PRODUCTS):
            product_template = random.choice(SAMPLE_PRODUCTS_DATA)
            store = random.choice(created_stores)

            # --- TẠO TÊN SẢN PHẨM ĐỘC ĐÁO, CHẤT LƯỢNG CAO ---
            modifier = random.choice(PRODUCT_NAME_MODIFIERS)
            product_name = f"{product_template['name']} {modifier}"

            embedding_request = EnhancedEmbeddingRequest(
                product_name=product_name,
                product_description=product_template['desc'],
                product_story_title=product_template.get('story_title'),
                product_story_detail=product_template.get('story_detail'),
                product_category_names=[product_template.get('category')],
                product_type_name=product_template.get('type_name'),
                product_made_by=product_template.get('made_by'),
                variant_names=['Tiêu chuẩn 500g', 'Hộp quà biếu'],
                store_name=store.get('name'),
                store_story_detail=store.get('story'),
                province_name=store.get('province'),
                region_name=store.get('region')
            )

            embedding_vector = embedding_service.create_enhanced_embedding(embedding_request)
            embedding_string = str(embedding_vector)

            product_id = str(uuid.uuid4())
            cur.execute(
                'INSERT INTO "Product" ("ID", "StoreID", "Name", "Description", "ProvinceID", "Embedding", "MadeBy", "TypeProduct", "Status", "ProductImages") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (
                    product_id,
                    store["id"],
                    product_name,
                    product_template['desc'],
                    store["province_id"],
                    embedding_string,
                    product_template.get('made_by'),
                    product_template.get('type_name'),
                    'Approved',
                    json.dumps([f"https://picsum.photos/seed/{uuid.uuid4()}/400/300"]) # Thêm dữ liệu ảnh mẫu
                )
            )

            # Tạo variant và inventory... (giữ nguyên logic)
            variant_id = str(uuid.uuid4())
            price = random.randint(50, 1000) * 1000
            cur.execute(
                'INSERT INTO "ProductVariant" ("ID", "ProductID", "VariantName", "Length", "Width", "Height", "Weight", "BasePrice", "commission", "FinalPrice") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (variant_id, product_id, 'Tiêu chuẩn', 15, 15, 10, 300, price, int(price * 0.1), int(price * 1.1))
            )
            cur.execute(
                'INSERT INTO "InventoryProduct" ("ProductVariantID", "Quantity") VALUES (%s, %s)',
                (variant_id, random.randint(20, 150))
            )

        conn.commit()
        print(f"\n--- Seeding Complete! {NUM_PRODUCTS} high-quality products created for {len(created_stores)} stores. ---")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\n--- ERROR: Seeding failed. Rolling back changes. ---")
        print(error)
        conn.rollback()
    finally:
        if cur is not None: cur.close()
        if conn is not None: conn.close()
        print("Database connection closed.")

if __name__ == "__main__":
    if not DATABASE_URL:
        print("FATAL: DATABASE_URL environment variable not set.")
    else:
        seed_database()