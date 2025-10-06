from fastapi import APIRouter, HTTPException
import time
from app.models.pydantic_models import SearchRequest, SearchResponse, ProductResponse
from app.services.search_service import SearchService
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
async def search_products(request: SearchRequest):
    """
    Accepts a search query and returns a ranked list of products.
    This is the main endpoint for the search microservice.
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

        # Construct the final response object
        return SearchResponse(
            query=request.query_text,
            total_results=len(product_responses),
            results=product_responses,
            processing_time_ms=round(processing_time, 2),
        )
    except Exception as e:
        # A generic catch-all for unexpected errors
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred: {str(e)}"
        )