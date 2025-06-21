from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from titiler.core.factory import TilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers

app = FastAPI(title="Titiler + Leaflet demo")

# Enable CORS for all origins for simplicity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Create a Titiler factory for COG
cog = TilerFactory()

# Include Titiler router under /cog prefix
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])

add_exception_handlers(app, DEFAULT_STATUS_CODES)

# Health check endpoint
@app.get("/healthz")
def health_check():
    return {"status": "ok"}
