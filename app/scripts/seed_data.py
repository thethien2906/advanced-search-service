# /app/scripts/seed_data.py
import os
import psycopg2
import uuid
import random
import json
from sentence_transformers import SentenceTransformer
from faker import Faker
from dotenv import load_dotenv

# --- CẤU HÌNH ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")
MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"
NUM_SELLERS = 5
NUM_PRODUCTS = 30

# --- DỮ LIỆU MẪU (ĐÃ MỞ RỘNG) ---
# Thêm các trường story_title, made_by, và type_name để khớp với logic embedding mới
SAMPLE_PRODUCTS_DATA = [
    {"name": "Mật ong rừng U Minh Hạ nguyên chất", "desc": "Mật ong tự nhiên thu hoạch từ hoa tràm trong rừng U Minh, có màu vàng sẫm và hương thơm đặc trưng.", "category": "Thực phẩm", "story_title": "Hương vị từ trái tim rừng tràm", "made_by": "Ong hút mật hoa tràm", "type_name": "Sản phẩm tự nhiên"},
    {"name": "Bộ ấm trà gốm sứ Bát Tràng men lam", "desc": "Sản phẩm thủ công từ làng gốm Bát Tràng, họa tiết hoa sen vẽ tay tinh xảo. Thích hợp làm quà tặng.", "category": "Thủ công mỹ nghệ", "story_title": "Nét tinh hoa làng gốm Việt", "made_by": "Nghệ nhân Bát Tràng", "type_name": "Đồ gốm"},
    {"name": "Nước mắm cốt cá cơm Phú Quốc", "desc": "Nước mắm truyền thống 40 độ đạm, ủ chượp tự nhiên trong thùng gỗ, hương vị đậm đà.", "category": "Thực phẩm", "story_title": "Giọt mắm tinh túy từ đảo ngọc", "made_by": "Cá cơm tươi", "type_name": "Gia vị"},
    {"name": "Trà sen Tây Hồ ướp tự nhiên", "desc": "Trà xanh Thái Nguyên được ướp trong bông hoa sen tươi của Hồ Tây, hương thơm thanh khiết.", "category": "Thực phẩm", "story_title": "Nghệ thuật ướp trà cầu kỳ", "made_by": "Lá trà và hoa sen", "type_name": "Đồ uống"},
    {"name": "Lụa tơ tằm Vạn Phúc Hà Đông", "desc": "Khăn choàng lụa tơ tằm 100% từ làng lụa Vạn Phúc, mềm mại và óng ả.", "category": "Thời trang", "story_title": "Sự mềm mại từ sợi tơ tằm", "made_by": "Tơ tằm tự nhiên", "type_name": "Phụ kiện"},
    {"name": "Tranh Đông Hồ 'Đám cưới chuột'", "desc": "Tranh dân gian in trên giấy điệp, thể hiện nét văn hóa độc đáo của Việt Nam.", "category": "Thủ công mỹ nghệ", "story_title": "Nét hóm hỉnh trong văn hóa dân gian", "made_by": "Giấy điệp và màu tự nhiên", "type_name": "Trang trí"},
    {"name": "Cà phê Robusta rang mộc Cầu Đất", "desc": "Hạt cà phê Robusta từ vùng Cầu Đất, Đà Lạt. Vị đậm, đắng nhẹ, hương thơm nồng nàn.", "category": "Thực phẩm", "story_title": "Đánh thức mọi giác quan", "made_by": "Hạt cà phê Robusta", "type_name": "Đồ uống"},
    {"name": "Nón lá bài thơ Huế", "desc": "Nón lá truyền thống của Huế, có hình ảnh cầu Tràng Tiền và các câu thơ được lồng ghép tinh tế.", "category": "Thủ công mỹ nghệ", "story_title": "Nét thơ trong vành nón", "made_by": "Lá nón và chỉ cước", "type_name": "Phụ kiện"},
    {"name": "Bánh Pía Sóc Trăng nhân sầu riêng", "desc": "Đặc sản Sóc Trăng với lớp vỏ mỏng, nhân sầu riêng béo ngậy và trứng muối đậm đà.", "category": "Thực phẩm", "story_title": "Vị ngọt miền Tây sông nước", "made_by": "Sầu riêng và trứng muối", "type_name": "Bánh kẹo"},
    {"name": "Túi cói thủ công họa tiết thổ cẩm", "desc": "Túi xách làm từ sợi cói tự nhiên, trang trí bằng vải thổ cẩm dệt tay.", "category": "Thời trang", "story_title": "Vẻ đẹp mộc mạc và tinh tế", "made_by": "Sợi cói và vải thổ cẩm", "type_name": "Phụ kiện"},
]

def get_db_connection():
    """Thiết lập kết nối đến cơ sở dữ liệu."""
    print("Connecting to the database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("Database connection successful.")
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to database: {e}")
        exit(1)

def generate_embeddings(model, texts):
    """Tạo embeddings đã được chuẩn hóa cho một danh sách văn bản."""
    print(f"Generating embeddings for {len(texts)} texts...")
    embeddings = model.encode(texts, normalize_embeddings=True)
    print("Embeddings generated.")
    return embeddings

def seed_database():
    """Hàm chính để xóa dữ liệu cũ và thêm dữ liệu mới."""
    conn = get_db_connection()
    cur = conn.cursor()
    fake = Faker('vi_VN')

    print(f"Loading sentence-transformer model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    print("Model loaded.")

    try:
        print("\n--- Starting Database Seeding ---")
        print("Cleaning up old data...")
        tables_to_clear = [
            "ProductCertificate", "InventoryProduct", "ProductVariant",
            "Product", "Store", "Seller", "User"
        ]
        for table in tables_to_clear:
            cur.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
        print("Cleanup complete.")

        admin_id = str(uuid.uuid4())

        print(f"Creating {NUM_SELLERS} sellers and stores...")
        store_ids = []
        for i in range(NUM_SELLERS):
            user_id = str(uuid.uuid4())
            phone_number = f"09{random.randint(10000000, 99999999)}"

            cur.execute(
                'INSERT INTO "User" ("ID", "Email", "Password", "PhoneNumber", "Role", "FirstName", "LastName") VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (user_id, fake.email(), 'hashed_password', phone_number, 'Seller', fake.first_name(), fake.last_name())
            )
            cur.execute(
                'INSERT INTO "Seller" ("UserID", "BusinessName") VALUES (%s, %s)',
                (user_id, fake.company())
            )

            store_id = str(uuid.uuid4())
            store_status = 'Approved' if random.random() < 0.8 else 'Pending'
            approved_by = admin_id if store_status == 'Approved' else None
            cur.execute(
                'INSERT INTO "Store" ("ID", "SellerID", "StoreName", "Province", "District", "Ward", "ProvinceID", "WardID", "Status", "ApprovedBy") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (store_id, user_id, f"Cửa hàng {fake.last_name()}", "Thành phố Hồ Chí Minh", "Quận 1", "Phường Bến Nghé", 79, 27883, store_status, approved_by)
            )
            store_ids.append(store_id)
        print("Sellers and stores created.")

        print(f"Preparing {NUM_PRODUCTS} products for insertion...")
        products_to_insert = []
        texts_for_embedding = []
        for i in range(NUM_PRODUCTS):
            product_template = random.choice(SAMPLE_PRODUCTS_DATA)

            # **THAY ĐỔI 1: Xây dựng "siêu tài liệu" để tạo embedding**
            # Logic này sao chép logic từ EmbeddingService để đảm bảo tính nhất quán
            parts = [
                f"{product_template['name']} - Mẫu #{i+1}",
                product_template.get('story_title'),
                product_template['desc']
            ]
            if product_template.get('category'):
                parts.append(f"Danh mục: {product_template['category']}")
            if product_template.get('type_name'):
                parts.append(f"Loại: {product_template['type_name']}")
            if product_template.get('made_by'):
                parts.append(f"Làm từ: {product_template['made_by']}")

            combined_text = ". ".join(filter(None, parts))
            texts_for_embedding.append(combined_text)

            # Thêm các trường dữ liệu mới vào product
            products_to_insert.append({
                "id": str(uuid.uuid4()),
                "store_id": random.choice(store_ids),
                "name": f"{product_template['name']} - Mẫu #{i+1}",
                "description": product_template['desc'],
                "images": json.dumps([f"https://picsum.photos/seed/{i+1}/400/300"]),
                "category_id": json.dumps([str(uuid.uuid4())]), # Giữ category ID giả
                "is_active": random.random() < 0.9,
                "made_by": product_template.get('made_by'),
                "type_product": product_template.get('type_name')
            })

        embeddings = generate_embeddings(model, texts_for_embedding)

        print("Inserting products, variants, and inventory...")
        for i, product in enumerate(products_to_insert):
            embedding_string = str(embeddings[i].tolist())

            # **THAY ĐỔI 2: Cập nhật câu lệnh INSERT để bao gồm các trường mới**
            cur.execute(
                'INSERT INTO "Product" ("ID", "StoreID", "Name", "Description", "ProductImages", "CategoryID", "IsActive", "Embedding", "MadeBy", "TypeProduct") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (product['id'], product['store_id'], product['name'], product['description'], product['images'], product['category_id'], product['is_active'], embedding_string, product['made_by'], product['type_product'])
            )

            variant_id = str(uuid.uuid4())
            price = random.randint(50, 1000) * 1000
            cur.execute(
                'INSERT INTO "ProductVariant" ("ID", "ProductID", "VariantName", "Length", "Width", "Height", "Weight", "BasePrice", "commission", "FinalPrice") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (variant_id, product['id'], 'Default', 10, 10, 10, 200, price, int(price * 0.1), int(price * 1.1))
            )

            quantity = random.randint(10, 100) if random.random() < 0.85 else 0
            cur.execute(
                'INSERT INTO "InventoryProduct" ("ProductVariantID", "Quantity") VALUES (%s, %s)',
                (variant_id, quantity)
            )

            if random.random() < 0.5:
                cur.execute(
                    'INSERT INTO "ProductCertificate" ("ProductID", "ImageURL", "Status", "ReviewedByStaffID") VALUES (%s, %s, %s, %s)',
                    (product['id'], f"https://example.com/cert/{product['id']}.pdf", 'Approved', None)
                )

        conn.commit()
        print("\n--- Seeding Complete! ---")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\n--- ERROR: Seeding failed. Rolling back changes. ---")
        print(error)
        conn.rollback()
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
        print("Database connection closed.")

if __name__ == "__main__":
    if not DATABASE_URL:
        print("FATAL: DATABASE_URL environment variable not set.")
    else:
        seed_database()