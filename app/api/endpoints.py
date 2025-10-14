# /app/api/endpoints.py
from fastapi import APIRouter, HTTPException
import time
import uuid
from datetime import datetime, timezone
from app.models.pydantic_models import (
    EmbeddingRequest,
    EmbeddingResponse,
    SuggestionRequest,
    SuggestionResponse
)
from app.services.suggestion_service import SuggestionService
from app.services.embedding_service import EmbeddingService
from app.services.database import DatabaseConnectionError

# Create an APIRouter instance
router = APIRouter()
embedding_service = EmbeddingService()
suggestion_service = SuggestionService()

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

@router.post("/search/suggestions", response_model=SuggestionResponse, summary="Lấy gợi ý tìm kiếm")
async def get_suggestions(request: SuggestionRequest):
    """
    Nhận một tiền tố (prefix) và trả về các gợi ý tìm kiếm phổ biến.
    """
    try:
        suggestions = suggestion_service.get_suggestions(
            prefix=request.prefix,
            limit=request.limit
        )
        return SuggestionResponse(
            prefix=request.prefix,
            suggestions=suggestions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi máy chủ nội bộ: {str(e)}")