from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Dict, Any, Optional, List
from datetime import datetime


class Event(BaseModel):
    """Model Event dengan validasi schema"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "topic": "user.created",
                "event_id": "evt_123456",
                "timestamp": "2025-10-19T10:30:00Z",
                "source": "auth-service",
                "payload": {"user_id": 42, "email": "user@example.com"}
            }
        }
    )
    
    topic: str = Field(..., min_length=1, description="Topic/kategori event")
    event_id: str = Field(..., min_length=1, description="Unique event identifier")
    timestamp: str = Field(..., description="ISO8601 timestamp")
    source: str = Field(..., min_length=1, description="Event source identifier")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event data")
    
    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Validasi format ISO8601"""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError('timestamp must be valid ISO8601 format')


class EventBatch(BaseModel):
    """Model untuk batch publishing"""
    events: List[Event]


class StatsResponse(BaseModel):
    """Response model untuk endpoint /stats"""
    received: int = Field(description="Total events received")
    unique_processed: int = Field(description="Unique events processed")
    duplicate_dropped: int = Field(description="Duplicate events dropped")
    topics: Dict[str, int] = Field(description="Event count per topic")
    uptime: float = Field(description="Service uptime in seconds")