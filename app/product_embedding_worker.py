# /app/product_embedding_worker.py
import json
import logging
import time
from kafka import KafkaConsumer
from app.core.config import settings
from app.models.pydantic_models import ProductEmbeddingMessage, EmbeddingRequest
from app.services.embedding_service import EmbeddingService
from app.services.database import DatabaseHandler
import psycopg2
from psycopg2 import extras

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductEmbeddingWorker:
    """
    Worker xử lý embedding product khi staff approve.
    Lắng nghe Kafka topic 'embed_product' và lưu embedding vào database.
    """

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.db_handler = DatabaseHandler(settings.DATABASE_URL)
        self.consumer = None
        self.max_retries = 3
        self.retry_delay = 2  # seconds

    def connect_consumer(self):
        """Kết nối tới Kafka consumer"""
        try:
            self.consumer = KafkaConsumer(
                settings.EMBED_PRODUCT_TOPIC,
                bootstrap_servers=settings.KAFKA_BROKER_URL,
                auto_offset_reset='earliest',
                enable_auto_commit=False,  # Manual commit để đảm bảo xử lý thành công
                group_id='product-embedding-worker-group',
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            logger.info(f"✅ Connected to Kafka topic: {settings.EMBED_PRODUCT_TOPIC}")
            return True
        except Exception as e:
            logger.error(f"❌ CRITICAL: Không thể kết nối Kafka Consumer: {e}")
            return False

    def get_product_data_from_db(self, product_id: str):
        """
        Lấy đầy đủ thông tin product từ database để tạo embedding.
        Sử dụng 14 trường giống seed_data.py
        """
        try:
            sql_query = """
            SELECT
                p."ID" as product_id,
                p."Name" as product_name,
                p."Description" as product_description,
                p."ProductType" as product_type,
                p."Material" as product_material,

                -- Lấy Hashtag Names
                (
                    SELECT array_agg(ht."Name")
                    FROM "Hashtag" ht
                    WHERE ht."ID"::text IN (SELECT jsonb_array_elements_text(p."HashtagIDs"))
                ) as hashtag_names,

                -- Lấy Category Names
                pc."Name" as category_name,
                pc_parent."Name" as parent_category_name,

                -- Lấy Store
                s."StoreName" as store_name,
                (SELECT "ContentData" FROM "StoreStoryContent" WHERE "StoreStoryID" = ss."ID" LIMIT 1) as store_story_detail,

                -- Lấy Product Story
                ps."Title" as product_story_title,
                (SELECT "ContentData" FROM "ProductStoryContent" WHERE "ProductStoryID" = ps."ID" LIMIT 1) as product_story_detail,

                -- Lấy Location
                prov."Name" as province_name,
                prov."Region" as region_name,
                prov."RegionSpecified" as sub_region_name

            FROM "Product" p
            LEFT JOIN "Store" s ON p."StoreID" = s."ID"
            LEFT JOIN "Province" prov ON p."ProvinceID" = prov."ID"
            LEFT JOIN "ProductStory" ps ON p."ID" = ps."ProductID"
            LEFT JOIN "StoreStory" ss ON p."StoreID" = ss."StoreID"
            LEFT JOIN "ProductCategory" pc ON p."CategoryID" = pc."ID"
            LEFT JOIN "ProductCategory" pc_parent ON pc."ParentId" = pc_parent."ID"

            WHERE p."ID" = %s
            AND p."ProductType" IN ('ProductMaster', 'ProductDetail');
            """

            results = self.db_handler.execute_query_with_retry(sql_query, (product_id,))

            if results and len(results) > 0:
                # Convert tuple result to dict
                columns = [
                    'product_id', 'product_name', 'product_description', 'product_type',
                    'product_material', 'hashtag_names', 'category_name', 'parent_category_name',
                    'store_name', 'store_story_detail', 'product_story_title', 'product_story_detail',
                    'province_name', 'region_name', 'sub_region_name'
                ]
                return dict(zip(columns, results[0]))
            else:
                logger.warning(f"⚠️ Product not found or not Master/Detail type: {product_id}")
                return None

        except Exception as e:
            logger.error(f"❌ Database error when fetching product {product_id}: {e}")
            return None

    def save_embedding_to_db(self, product_id: str, embedding_vector: list) -> bool:
        """
        Lưu embedding vào database.
        Returns True nếu thành công, False nếu thất bại.
        """
        try:
            embedding_string = str(embedding_vector)

            rows_affected = self.db_handler.execute_update_with_retry(
                'UPDATE "Product" SET "Embedding" = %s WHERE "ID" = %s',
                (embedding_string, product_id)
            )

            if rows_affected > 0:
                logger.info(f"✅ Successfully saved embedding for Product: {product_id}")
                return True
            else:
                logger.warning(f"⚠️ No rows updated for Product: {product_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to save embedding for Product {product_id}: {e}")
            return False

    def process_message(self, message_data: dict) -> bool:
        """
        Xử lý message từ Kafka.
        Returns True nếu thành công, False nếu thất bại.
        """
        try:
            # Parse và validate message
            embed_message = ProductEmbeddingMessage(**message_data)
            logger.info(f"📥 Received embed request - ProductId: {embed_message.product_id}, Name: {embed_message.product_name}")

            # Lấy đầy đủ thông tin product từ database
            product_data = self.get_product_data_from_db(embed_message.product_id)

            if not product_data:
                logger.warning(f"⚠️ Skipping embedding - Product data not found or invalid type: {embed_message.product_id}")
                return True  # Return True để commit offset (không retry)

            # Tạo embedding request với 14 trường
            embedding_request = EmbeddingRequest(
                product_name=product_data.get('product_name'),
                product_description=product_data.get('product_description'),
                product_type=product_data.get('product_type'),
                product_material=product_data.get('product_material'),
                product_story_title=product_data.get('product_story_title'),
                product_story_detail=product_data.get('product_story_detail'),
                hashtag_names=product_data.get('hashtag_names'),
                category_name=product_data.get('category_name'),
                parent_category_name=product_data.get('parent_category_name'),
                store_name=product_data.get('store_name'),
                store_story_detail=product_data.get('store_story_detail'),
                province_name=product_data.get('province_name'),
                region_name=product_data.get('region_name'),
                sub_region_name=product_data.get('sub_region_name')
            )

            # Generate embedding
            logger.info(f"🔄 Generating embedding for Product: {embed_message.product_id}")
            embedding_vector = self.embedding_service.create_embedding(embedding_request)

            # Lưu vào database
            success = self.save_embedding_to_db(embed_message.product_id, embedding_vector)

            if success:
                logger.info(f"✅ Successfully embedded Product: {embed_message.product_id} - {embed_message.product_name}")
                return True
            else:
                logger.error(f"❌ Failed to save embedding for Product: {embed_message.product_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)
            return False

    def process_with_retry(self, message_data: dict) -> bool:
        """
        Xử lý message với retry logic.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                success = self.process_message(message_data)
                if success:
                    return True

                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    logger.warning(f"⚠️ Retry attempt {attempt}/{self.max_retries} after {wait_time}s...")
                    time.sleep(wait_time)

            except Exception as e:
                logger.error(f"❌ Attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        logger.error(f"❌ Failed after {self.max_retries} attempts. Message will be committed to avoid blocking.")
        return False

    def run(self):
        """Main loop để lắng nghe và xử lý messages"""
        logger.info("=============================================")
        logger.info("  🚀 Product Embedding Worker Starting 🚀")
        logger.info("=============================================")
        logger.info(f"Listening on topic: {settings.EMBED_PRODUCT_TOPIC}")
        logger.info(f"Kafka broker: {settings.KAFKA_BROKER_URL}")

        if not self.connect_consumer():
            logger.error("Failed to connect to Kafka. Exiting.")
            return

        try:
            for message in self.consumer:
                try:
                    message_data = message.value
                    logger.info(f"📨 New message received at offset {message.offset}")

                    # Process với retry
                    success = self.process_with_retry(message_data)

                    # Commit offset regardless of success để không block queue
                    self.consumer.commit()

                    if not success:
                        logger.warning(f"⚠️ Message processed with errors but offset committed.")

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Invalid JSON format: {e}")
                    self.consumer.commit()  # Skip invalid message
                except Exception as e:
                    logger.error(f"❌ Unexpected error processing message: {e}", exc_info=True)
                    self.consumer.commit()  # Skip problematic message

        except KeyboardInterrupt:
            logger.info("⚠️ Received shutdown signal...")
        except Exception as e:
            logger.error(f"❌ Critical error in main loop: {e}", exc_info=True)
        finally:
            if self.consumer:
                self.consumer.close()
            logger.info("=============================================")
            logger.info("  🛑 Product Embedding Worker Stopped 🛑")
            logger.info("=============================================")

def main():
    """Entry point"""
    psycopg2.extras.register_uuid()
    worker = ProductEmbeddingWorker()
    worker.run()

if __name__ == "__main__":
    main()
