# /app/main.py
import logging
from fastapi import FastAPI
from app.api import endpoints
from app.services.kafka_producer import kafka_producer # Import the producer instance

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

    # Check Kafka producer status and log it
    if kafka_producer and kafka_producer.producer:
        logger.info("✅ Kafka Producer is connected and ready.")
    else:
        logger.warning("⚠️ Kafka Producer failed to connect. Logging will be disabled.")

    logger.info("All services are initialized. The application is ready to accept requests.")
    logger.info("==================================================")


# Include the API router from the endpoints module
app.include_router(endpoints.router)