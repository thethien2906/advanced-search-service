# /app/seeder_worker.py
import json
import logging
from kafka import KafkaConsumer
from app.core.config import settings
from app.scripts import seed_data # Import trực tiếp module
from app.scripts import seed_documents # Import module seed_documents

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("=============================================")
    logger.info("    🌱 Kafka Seeder Worker Starting 🌱")
    logger.info("=============================================")
    logger.info(f"Đang chờ tín hiệu 'model ready' trên topic: '{settings.MODEL_READY_TOPIC}'...")

    try:
        consumer = KafkaConsumer(
            settings.MODEL_READY_TOPIC,
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            auto_offset_reset='earliest', # Đảm bảo nhận được message dù khởi động sau
            group_id='seeder-worker-group-singleton' # Group ID độc nhất
        )
    except Exception as e:
        logger.error(f"❌ CRITICAL: Không thể kết nối KafkaConsumer cho Seeder: {e}")
        return

    # Chờ message đầu tiên
    for message in consumer:
        logger.info(f"✅ Đã nhận được tín hiệu 'model ready' từ topic '{message.topic}'.")

        # Gọi hàm chính của seed_data
        try:
            logger.info("--- Bắt đầu chạy script seed_data ---")
            seed_data.embed_existing_products()
            logger.info("--- ✅ Script seed_data đã hoàn thành. ---")
        except Exception as e:
            logger.error(f"❌ Lỗi khi đang chạy seed_data: {e}", exc_info=True)

        # Gọi hàm chính của seed_documents
        try:
            logger.info("--- Bắt đầu chạy script seed_documents ---")
            seed_documents.embed_existing_documents()
            logger.info("--- ✅ Script seed_documents đã hoàn thành. ---")
        except Exception as e:
            logger.error(f"❌ Lỗi khi đang chạy seed_documents: {e}", exc_info=True)

        # Nhiệm vụ đã xong, thoát khỏi vòng lặp và kết thúc worker
        break

    consumer.close()
    logger.info("=============================================")
    logger.info("    🌱 Seeder Worker đã hoàn thành. Exiting. 🌱")
    logger.info("=============================================")

if __name__ == "__main__":
    main()