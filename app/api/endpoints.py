from fastapi import APIRouter

# Create a new router
router = APIRouter()

@router.get("/")
def read_root():
    """
    Wellcome message
    """
    return {"message": "Hello, World"}