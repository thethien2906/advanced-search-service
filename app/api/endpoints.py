# /app/api/endpoints.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
import time
import uuid
from datetime import datetime, timezone
from app.models.pydantic_models import SearchRequest, SearchResponse, ProductResponse
from app.services.search_service import SearchService
from app.services.database import DatabaseConnectionError
from app.services.kafka_producer import kafka_producer
from app.core.config import settings

# Create an APIRouter instance
router = APIRouter()
search_service = SearchService()

@router.get("/")
def read_root():
    """
    Root endpoint to confirm the service is running.
    Provides a simple health check.
    """
    return {
        "message": "Hello, World",
        "service": "Search Service",
        "status": "running"
    }

@router.post("/search", response_model=SearchResponse)
async def search_products(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Accepts a search query and returns a ranked list of products.
    This is the main endpoint for the search microservice.
    [Phase 5]: Publishes a search event to Kafka asynchronously.
    """
    start_time = time.time()
    try:
        # Call the search service with data from the request
        search_results = search_service.search(
            query=request.query_text,
            limit=request.limit
        )

        # Transform the dictionaries into Pydantic models
        product_responses = [ProductResponse(**item) for item in search_results]

        end_time = time.time()
        processing_time = (end_time - start_time) * 1000  # Convert to ms

        # Asynchronously publish search event to Kafka
        search_id = str(uuid.uuid4())
        event_data = {
            "search_id": search_id,
            "user_id": str(request.user_id) if request.user_id else None,
            "query_text": request.query_text,
            "result_count": len(product_responses),
            "ranked_product_ids": [str(p.id) for p in product_responses],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        background_tasks.add_task(
            kafka_producer.publish_search_event,
            settings.KAFKA_SEARCH_EVENTS_TOPIC,
            event_data
        )

        # Construct the final response object
        return SearchResponse(
            query=request.query_text,
            total_results=len(product_responses),
            results=product_responses,
            processing_time_ms=round(processing_time, 2),
        )
    # Per Phase 3 guide, catch the specific DB error to return a 503 status
    except DatabaseConnectionError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service Unavailable: Could not connect to the database. {str(e)}"
        )
    except Exception as e:
        # A generic catch-all for other unexpected errors
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred: {str(e)}"
        )