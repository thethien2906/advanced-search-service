# /app/api/endpoints.py
from fastapi import APIRouter, HTTPException
from app.models.pydantic_models import (
    EmbeddingRequest,
    EmbeddingResponse
)
from app.services.embedding_service import EmbeddingService

# Create an APIRouter instance
router = APIRouter()
embedding_service = EmbeddingService()

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

@router.post("/embeddings", response_model=EmbeddingResponse, summary="Generate Product Embedding")
def get_embedding(request: EmbeddingRequest):
    """
    Receives a set of product attributes, combines them, and returns a
    normalized vector embedding.
    """
    try:
        embedding_vector = embedding_service.create_embedding(request)
        return EmbeddingResponse(embedding=embedding_vector)
    except Exception as e:
        # This will catch potential errors during the embedding process
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")