from fastapi import FastAPI
from .api import endpoints

# Create the FastAPI application instance
app = FastAPI(title="Search Service")

# Include the API router
app.include_router(endpoints.router)