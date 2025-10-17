# /app/suggestion_worker.py
import json
import logging
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from app.services.suggestion_service import SuggestionService
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    Kafka worker for handling auto-suggestion requests.
    - Listens for requests on 'suggestion_requests' topic.
    - Calls SuggestionService to get suggestions.
    - Sends results to 'suggestion_results' topic.
    """
    logger.info("=============================================")
    logger.info("    🚀 Suggestion Worker Starting 🚀")
    logger.info("=============================================")

    # Initialize KafkaConsumer
    try:
        consumer = KafkaConsumer(
            settings.SUGGESTION_REQUESTS_TOPIC,
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='suggestion-worker-group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        logger.info("✅ KafkaConsumer for suggestions connected successfully.")
    except KafkaError as e:
        logger.error(f"❌ CRITICAL: Could not connect suggestion KafkaConsumer: {e}")
        return

    # Initialize KafkaProducer
    try:
        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        logger.info("✅ KafkaProducer for suggestions connected successfully.")
    except KafkaError as e:
        logger.error(f"❌ CRITICAL: Could not connect suggestion KafkaProducer: {e}")
        return

    # Initialize SuggestionService
    try:
        suggestion_service = SuggestionService()
        logger.info("✅ SuggestionService initialized successfully.")
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to initialize SuggestionService: {e}")
        return

    logger.info("=============================================")
    logger.info("👂 Suggestion worker is now listening for messages...")
    logger.info("=============================================")

    for message in consumer:
        try:
            request_data = message.value
            prefix = request_data.get("prefix")
            request_id = request_data.get("request_id")
            limit = request_data.get("limit", 5)

            if not prefix or not request_id:
                logger.warning(f"⚠️ Received message with missing 'prefix' or 'request_id'. Skipping.")
                continue

            logger.info(f"📬 Received suggestion request | RequestID: {request_id} | Prefix: '{prefix}'")

            # Get suggestions from the service
            suggestions = suggestion_service.get_suggestions(prefix=prefix, limit=limit)

            # Send results to 'suggestion_results' topic
            result_payload = {
                "request_id": request_id,
                "suggestions": suggestions
            }
            producer.send(settings.SUGGESTION_RESULTS_TOPIC, value=result_payload)
            logger.info(f"📤 Sent {len(suggestions)} suggestions to '{settings.SUGGESTION_RESULTS_TOPIC}' for RequestID: {request_id}")
            producer.flush()

        except json.JSONDecodeError:
            logger.error("Failed to decode message value. Skipping.")
        except Exception as e:
            logger.error(f"An unexpected error occurred while processing message: {e}", exc_info=True)

if __name__ == "__main__":
    main()