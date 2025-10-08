# /app/main.py
import logging
import time
from fastapi import FastAPI
from app.api import endpoints
from app.services.kafka_producer import kafka_producer
from app.services.database import DatabaseHandler, DatabaseConnectionError
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the main FastAPI application instance
app = FastAPI(
    title="Homeland's Finest - Search Service",
    description="A microservice for product search using a hybrid ML ranking system.",
    version="0.2.0" # Phase 2
)

@app.on_event("startup")
async def startup_event():
    """
    Event handler that runs on application startup.
    Logs a confirmation message when all services are ready.
    """
    logger.info("==================================================")
    logger.info("          🚀 Advanced Search Service Started 🚀")
    logger.info("==================================================")
    logger.info("FastAPI application is up and running.")

    # --- START: Database Initialization Check ---
    db_handler = DatabaseHandler(settings.DATABASE_URL)
    max_retries = 5
    retry_delay = 5  # seconds

    logger.info("Attempting to verify database initialization...")
    for attempt in range(max_retries):
        try:
            # Check if the "Product" table has data, indicating DML scripts ran
            result = db_handler.execute_query_with_retry('SELECT COUNT(*) FROM "Product";', max_retries=1)
            product_count = result[0][0] if result else 0

            if product_count > 0:
                logger.info(f"✅ Database is ready. DDL & DML scripts executed successfully. Found {product_count} products.")
                break # Exit loop on success
            else:
                logger.warning(f"Database is connected, but no data found. DML scripts might still be running. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"An error occurred while checking database status: {e}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
    else: # This block runs if the for loop completes without breaking
        logger.error("❌ Failed to verify database data after multiple retries. Please check the PostgreSQL container logs.")
    # --- END: Database Initialization Check ---


    # Check Kafka producer status and log it
    if kafka_producer and kafka_producer.producer:
        logger.info("✅ Kafka Producer is connected and ready.")
    else:
        logger.warning("⚠️ Kafka Producer failed to connect. Logging will be disabled.")

    logger.info("All services are initialized. The application is ready to accept requests.")
    logger.info("==================================================")


# Include the API router from the endpoints module
app.include_router(endpoints.router)