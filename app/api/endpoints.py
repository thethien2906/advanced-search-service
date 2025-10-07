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


async def _handle_search_request(search_function, request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Generic handler for processing a search request, logging, and formatting the response.
    """
    start_time = time.time()
    try:
        search_results = search_function(query=request.query_text, limit=request.limit)
        product_responses = [ProductResponse(**item) for item in search_results]

        end_time = time.time()
        processing_time = (end_time - start_time) * 1000

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

        return SearchResponse(
            query=request.query_text,
            total_results=len(product_responses),
            results=product_responses,
            processing_time_ms=round(processing_time, 2),
        )
    except DatabaseConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Service Unavailable: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.post("/search/semantic", response_model=SearchResponse, summary="Semantic Search Only")
async def search_semantic(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Accepts a search query and returns a list of products based on semantic similarity ONLY.
    The results from this endpoint are used to collect data for training the ML ranker.
    """
    return await _handle_search_request(search_service.search_semantic, request, background_tasks)


@router.post("/search/ml", response_model=SearchResponse, summary="Hybrid Search with ML Re-ranking")
async def search_with_ml(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Accepts a search query and returns a ranked list of products using the full hybrid ML model.
    This endpoint should be used once the ranking model has been adequately trained.
    """
    return await _handle_search_request(search_service.search_with_ml, request, background_tasks)