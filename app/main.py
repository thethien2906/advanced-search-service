from fastapi import FastAPI
from app.api import endpoints

# Create the main FastAPI application instance
app = FastAPI(
    title="Homeland's Finest - Search Service",
    description="A microservice for product search using a hybrid ML ranking system.",
    version="0.2.0" # Phase 2
)

# Include the API router from the endpoints module
app.include_router(endpoints.router)