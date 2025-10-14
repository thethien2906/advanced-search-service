# /app/kafka_worker.py
import json
import logging
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from app.services.search_service import SearchService
from app.core.config import settings
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    Hàm chính để khởi tạo và chạy Kafka worker.
    - Lắng nghe các yêu cầu tìm kiếm từ topic 'search_requests'.
    - Gọi SearchService để xử lý.
    - Gửi kết quả và log đến các topic Kafka tương ứng.
    """
    logger.info("=============================================")
    logger.info("      🚀 Kafka Worker Service Starting 🚀")
    logger.info("=============================================")

    # Khởi tạo KafkaConsumer để lắng nghe yêu cầu
    try:
        consumer = KafkaConsumer(
            'search_requests',
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='search-worker-group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        logger.info("✅ KafkaConsumer connected successfully.")
    except KafkaError as e:
        logger.error(f"❌ CRITICAL: Could not connect KafkaConsumer: {e}")
        return # Thoát nếu không kết nối được

    # Khởi tạo KafkaProducer để gửi phản hồi
    try:
        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        logger.info("✅ KafkaProducer connected successfully.")
    except KafkaError as e:
        logger.error(f"❌ CRITICAL: Could not connect KafkaProducer: {e}")
        return

    # Khởi tạo SearchService để tái sử dụng logic tìm kiếm
    try:
        search_service = SearchService()
        logger.info("✅ SearchService initialized successfully.")
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to initialize SearchService: {e}")
        return

    logger.info("=============================================")
    logger.info("👂 Worker is now listening for messages...")
    logger.info("=============================================")


    # Vòng lặp vô tận để xử lý message
    for message in consumer:
        try:
            request_data = message.value
            query_text = request_data.get("query_text")
            request_id = request_data.get("request_id") # Nhận request_id từ message
            limit = request_data.get("limit", 20)

            if not query_text or not request_id:
                logger.warning(f"⚠️ Received message with missing 'query_text' or 'request_id'. Skipping.")
                continue

            logger.info(f"📬 Received search request | RequestID: {request_id} | Query: '{query_text}'")

            # Gọi logic tìm kiếm từ SearchService
            # Sử dụng search_with_ml làm mặc định
            search_results = search_service.search_with_ml(query=query_text, limit=limit)

            # Log lại nội dung để xác minh
            logger.info(f"✅ Search completed for RequestID: {request_id}. Found {len(search_results)} results.")
            # (Giai đoạn 3 sẽ gửi kết quả đi)

        except json.JSONDecodeError:
            logger.error("Failed to decode message value. Skipping.")
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing message: {e}")


if __name__ == "__main__":
    main()