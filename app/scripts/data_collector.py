# /app/scripts/data_collector.py
import os
import sys
import json
import logging
import psycopg2
from kafka import KafkaConsumer
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
KAFKA_BROKER_URL = os.getenv("KAFKA_BROKER_URL", "kafka:9092").split(',')
KAFKA_TOPIC = os.getenv("KAFKA_SEARCH_EVENTS_TOPIC", "search_events")
CONSUMER_GROUP_ID = "search-log-consumer-group"

def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"FATAL: Could not connect to database: {e}")
        sys.exit(1)

def insert_log_to_db(cursor, event_data: dict):
    """Inserts a single search log event into the database."""
    sql = """
    INSERT INTO "SearchLog" ("ID", "UserID", "QueryText", "ResultCount", "CreatedAt")
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT ("ID") DO NOTHING;
    """
    params = (
        event_data.get("search_id"),
        event_data.get("user_id"),
        event_data.get("query_text"),
        event_data.get("result_count"),
        event_data.get("timestamp")
    )
    try:
        cursor.execute(sql, params)
        logger.info(f"Successfully inserted SearchLog with ID: {event_data.get('search_id')}")
    except psycopg2.Error as e:
        logger.error(f"Database insertion failed for SearchLog ID {event_data.get('search_id')}: {e}")
        raise

def main():
    """Main function to consume from Kafka and write to PostgreSQL."""
    if not DATABASE_URL:
        logger.error("FATAL: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    db_conn = get_db_connection()
    db_cursor = db_conn.cursor()

    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=KAFKA_BROKER_URL,
            auto_offset_reset='earliest',
            enable_auto_commit=False, # Manual commit control
            group_id=CONSUMER_GROUP_ID,
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        logger.info(f"KafkaConsumer connected. Listening for messages on topic '{KAFKA_TOPIC}'...")
    except Exception as e:
        logger.error(f"FATAL: Could not connect to Kafka: {e}")
        sys.exit(1)

    try:
        for message in consumer:
            event_data = message.value
            try:
                insert_log_to_db(db_cursor, event_data)
                db_conn.commit()  # Commit after successful insert
                consumer.commit() # Commit Kafka offset
            except (Exception, psycopg2.Error) as e:
                logger.error(f"Rolling back database transaction due to error: {e}")
                db_conn.rollback()
                # Do not commit Kafka offset, message will be re-processed later

    except KeyboardInterrupt:
        logger.info("Consumer stopped by user.")
    finally:
        db_cursor.close()
        db_conn.close()
        consumer.close()
        logger.info("Database connection and Kafka consumer closed.")

if __name__ == "__main__":
    main()