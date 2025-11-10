# /app/kafka_worker.py
import json
import logging
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from app.services.search_service import SearchService
from app.core.config import settings
import uuid
from datetime import datetime, timezone
import os

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
    logger.info("      🚀 Search Worker Starting 🚀")
    logger.info("=============================================")

    # Khởi tạo KafkaConsumer để lắng nghe yêu cầu
    try:
        consumer = KafkaConsumer(
            settings.SEARCH_REQUESTS_TOPIC,
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
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8') # Hỗ trợ serialize UUID
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
            user_id = request_data.get("user_id") # Nhận user_id
            limit = request_data.get("limit", 20)

            if not query_text or not request_id:
                logger.warning(f"⚠️ Received message with missing 'query_text' or 'request_id'. Skipping.")
                continue

            logger.info(f"📬 Received search request | RequestID: {request_id} | Query: '{query_text}'")

            # Gọi logic tìm kiếm từ SearchService
            search_results = search_service.search_semantic(query=query_text, limit=limit)

            # --- GIAI ĐOẠN 3: GỬI KẾT QUẢ VÀ LOGGING ---

            # 1. Gửi kết quả tìm kiếm vào topic 'search_results'
            result_payload = {
                "request_id": request_id,
                "products": search_results
            }
            logger.info(f"--- GỬI PAYLOAD LÊN KAFKA (RequestID: {request_id}) ---")
            logger.info(json.dumps(result_payload, default=str, indent=4, ensure_ascii=False))

            producer.send(settings.SEARCH_RESULTS_TOPIC, value=result_payload)
            logger.info(f"📤 Sent {len(search_results)} results to '{settings.SEARCH_RESULTS_TOPIC}' for RequestID: {request_id}")

            # 2. Gửi dữ liệu log vào topic 'search_logging_events'
            ranked_ids = [result['Id'] for result in search_results]
            log_payload = {
                "search_id": str(uuid.uuid4()),
                "user_id": user_id,
                "query_text": query_text,
                "result_count": len(search_results),
                "ranked_product_ids": ranked_ids,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            producer.send(settings.SEARCH_LOGGING_TOPIC, value=log_payload)
            logger.info(f"📝 Sent log event to '{settings.SEARCH_LOGGING_TOPIC}' for RequestID: {request_id}")

            # Đảm bảo message được gửi đi
            producer.flush()

        except json.JSONDecodeError:
            logger.error("Failed to decode message value. Skipping.")
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing message: {e}", exc_info=True)


if __name__ == "__main__":
    main()