import asyncio
from asyncio import Queue
import logging
from typing import List, Dict, Any, Optional
import time
from .models import Event, StatsResponse
from .dedup_store import DedupStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventAggregator:
    """Core event aggregator dengan internal queue dan consumer"""
    
    def __init__(self, dedup_store: DedupStore):
        self.dedup_store = dedup_store
        self.queue: Queue = Queue()
        self.stats = {
            "received": 0,
            "unique_processed": 0,
            "duplicate_dropped": 0,
            "start_time": time.time()
        }
        self.running = False
        self.consumer_tasks = []
    
    async def start(self):
        """Start background consumers (multiple workers)"""
        if not self.running:
            self.running = True
            # Start 5 concurrent consumers for faster processing
            self.consumer_tasks = [
                asyncio.create_task(self._consume_events(worker_id=i))
                for i in range(5)
            ]
            logger.info("Event aggregator started with 5 workers")
    
    async def stop(self):
        """Stop consumers gracefully"""
        self.running = False
        if self.consumer_tasks:
            await asyncio.gather(*self.consumer_tasks, return_exceptions=True)
            logger.info("Event aggregator stopped")
    
    async def publish(self, events: List[Event]) -> Dict[str, Any]:
        """Publish events to internal queue"""
        result = {
            "accepted": 0,
            "rejected": 0,
            "duplicates_immediate": 0
        }
        
        for event in events:
            self.stats["received"] += 1
            
            if self.dedup_store.is_duplicate(event.topic, event.event_id):
                result["duplicates_immediate"] += 1
                result["rejected"] += 1
                self.stats["duplicate_dropped"] += 1
                logger.debug(f"Duplicate detected: {event.topic}/{event.event_id}")
                continue
            
            await self.queue.put(event)
            result["accepted"] += 1
        
        return result
    
    async def _consume_events(self, worker_id: int = 0):
        """Background consumer that processes events from queue"""
        logger.info(f"Consumer worker {worker_id} started")
        
        while self.running or not self.queue.empty():
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                await self._process_event(event)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in consumer {worker_id}: {e}")
        
        logger.info(f"Consumer worker {worker_id} stopped")
    
    async def _process_event(self, event: Event):
        """Process single event with idempotency guarantee"""
        was_new = self.dedup_store.mark_processed(
            event.topic, 
            event.event_id, 
            event.timestamp
        )
        
        if was_new:
            self.stats["unique_processed"] += 1
            logger.debug(f"Processed NEW event: {event.topic}/{event.event_id}")
            # Simulate minimal processing work
            await asyncio.sleep(0.0001)  # Reduced from 0.001
        else:
            self.stats["duplicate_dropped"] += 1
            logger.debug(f"Dropped DUPLICATE: {event.topic}/{event.event_id}")
    
    def get_stats(self) -> StatsResponse:
        """Get current statistics"""
        store_stats = self.dedup_store.get_stats()
        uptime = time.time() - self.stats["start_time"]
        
        return StatsResponse(
            received=self.stats["received"],
            unique_processed=self.stats["unique_processed"],
            duplicate_dropped=self.stats["duplicate_dropped"],
            topics=store_stats["topics"],
            uptime=uptime
        )
    
    def get_events(self, topic: Optional[str] = None) -> List[Dict]:
        """Get processed events"""
        events = self.dedup_store.get_processed_events(topic)
        return [
            {
                "topic": e[0],
                "event_id": e[1],
                "timestamp": e[2],
                "processed_at": e[3]
            }
            for e in events
        ]