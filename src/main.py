from fastapi import FastAPI, HTTPException, Query
from contextlib import asynccontextmanager
from typing import Optional
import logging
from datetime import datetime

from .models import Event, EventBatch, StatsResponse
from .dedup_store import DedupStore
from .aggregator import EventAggregator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize stores and aggregator
dedup_store = DedupStore()
aggregator = EventAggregator(dedup_store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management: startup and shutdown"""
    await aggregator.start()
    logger.info("Application started")
    yield
    await aggregator.stop()
    logger.info("Application stopped")


app = FastAPI(
    title="Event Aggregator Service",
    description="Distributed event aggregator with deduplication",
    version="1.0.0",
    lifespan=lifespan
)


@app.post("/publish")
async def publish_events(data: Event | EventBatch):
    """Publish single event or batch of events"""
    try:
        events = data.events if isinstance(data, EventBatch) else [data]
        result = await aggregator.publish(events)
        
        return {
            "status": "success",
            "message": f"Processed {len(events)} events",
            "details": result
        }
    except Exception as e:
        logger.error(f"Error publishing events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events")
async def get_events(topic: Optional[str] = Query(None)):
    """Get list of processed unique events"""
    try:
        events = aggregator.get_events(topic)
        return {
            "status": "success",
            "count": len(events),
            "events": events
        }
    except Exception as e:
        logger.error(f"Error getting events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get aggregator statistics"""
    try:
        return aggregator.get_stats()
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "event-aggregator",
        "timestamp": datetime.utcnow().isoformat()
    }