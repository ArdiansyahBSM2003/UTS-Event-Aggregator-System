import asyncio
import httpx
import random
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self, aggregator_url: str):
        self.aggregator_url = aggregator_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def publish_event(self, event: dict) -> bool:
        """Publish single event ke aggregator"""
        try:
            response = await self.client.post(
                f"{self.aggregator_url}/publish",
                json=event
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to publish: {e}")
            return False
    
    async def simulate_at_least_once(
        self, 
        num_events: int = 5000, 
        duplicate_rate: float = 0.2
    ):
        """Simulate at-least-once delivery dengan duplicate events"""
        logger.info(f"Starting: {num_events} events, {duplicate_rate*100}% duplicates")
        
        events = []
        topics = ["user.created", "order.placed", "payment.processed"]
        
        for i in range(num_events):
            event = {
                "topic": random.choice(topics),
                "event_id": f"evt_{i:06d}",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "publisher-simulator",
                "payload": {"index": i, "data": f"Event {i}"}
            }
            events.append(event)
        
        num_duplicates = int(num_events * duplicate_rate)
        duplicate_events = random.choices(events, k=num_duplicates)
        all_events = events + duplicate_events
        random.shuffle(all_events)
        
        logger.info(f"Total: {len(all_events)} (unique: {num_events})")
        
        batch_size = 50
        success_count = 0
        
        for i in range(0, len(all_events), batch_size):
            batch = all_events[i:i+batch_size]
            try:
                response = await self.client.post(
                    f"{self.aggregator_url}/publish",
                    json={"events": batch}
                )
                response.raise_for_status()
                success_count += len(batch)
                
                if (i // batch_size) % 10 == 0:
                    logger.info(f"Progress: {success_count}/{len(all_events)}")
            except Exception as e:
                logger.error(f"Batch failed: {e}")
            
            await asyncio.sleep(0.01)
        
        logger.info(f"Completed: {success_count}/{len(all_events)}")
        
        try:
            response = await self.client.get(f"{self.aggregator_url}/stats")
            stats = response.json()
            logger.info(f"Final stats: {stats}")
        except Exception as e:
            logger.error(f"Failed to fetch stats: {e}")
    
    async def close(self):
        await self.client.aclose()


async def main():
    aggregator_url = os.getenv("AGGREGATOR_URL", "http://localhost:8080")
    num_events = int(os.getenv("NUM_EVENTS", "5000"))
    duplicate_rate = float(os.getenv("DUPLICATE_RATE", "0.2"))
    
    publisher = EventPublisher(aggregator_url)
    
    logger.info("Waiting for aggregator...")
    for _ in range(30):
        try:
            response = await publisher.client.get(f"{aggregator_url}/health")
            if response.status_code == 200:
                logger.info("Aggregator ready!")
                break
        except:
            pass
        await asyncio.sleep(1)
    
    await publisher.simulate_at_least_once(num_events, duplicate_rate)
    await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())