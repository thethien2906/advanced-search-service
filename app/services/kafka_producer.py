# /app/services/kafka_producer.py
import json
import logging
import time
from kafka import KafkaProducer
from kafka.errors import KafkaError, NoBrokersAvailable
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventProducer:
    def __init__(self, bootstrap_servers, retries=5, delay=10):
        """
        Initializes the KafkaProducer with a retry mechanism.
        """
        self.producer = None
        for i in range(retries):
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    acks=0,  # Fire-and-forget
                    retries=0 # No retries on individual sends
                )
                logger.info("KafkaProducer initialized successfully.")
                return # Exit the loop if connection is successful
            except NoBrokersAvailable:
                logger.warning(f"Kafka brokers not available. Retrying in {delay} seconds... (Attempt {i+1}/{retries})")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"An unexpected error occurred during Kafka initialization: {e}")
                time.sleep(delay)

        # If the loop completes without connecting, log a critical error
        if self.producer is None:
            logger.error("CRITICAL: Failed to initialize KafkaProducer after all retries.")


    def publish_search_event(self, topic: str, event_data: dict):
        """
        Publishes a search event to the specified Kafka topic.
        This operation is non-blocking and handles errors gracefully.
        """
        if self.producer is None:
            logger.error("Kafka producer is not available. Skipping event publish.")
            return

        try:
            future = self.producer.send(topic, value=event_data)
            # We don't block on get(), but can add callbacks for logging
            future.add_callback(self.on_send_success)
            future.add_errback(self.on_send_error)
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka topic '{topic}': {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred when publishing to Kafka: {e}")

    def on_send_success(self, record_metadata):
        logger.info(f"Event published to topic '{record_metadata.topic}' partition {record_metadata.partition}")

    def on_send_error(self, excp):
        logger.error("Failed to publish event to Kafka", exc_info=excp)

# Create a single, reusable instance of the producer
kafka_producer = EventProducer(bootstrap_servers=settings.KAFKA_BROKER_URL)