import pytest
import pytest_asyncio
import asyncio
import os
import tempfile
import time
import random
import gc
from src.models import Event
from src.dedup_store import DedupStore
from src.aggregator import EventAggregator


@pytest_asyncio.fixture
async def test_app():
    """Fixture for testing with isolated database"""
    test_db = tempfile.mktemp(suffix=".db")
    test_dedup = DedupStore(test_db)
    test_agg = EventAggregator(test_dedup)
    
    yield test_agg, test_dedup
    
    # Cleanup - proper shutdown
    await test_agg.stop()
    test_dedup.close()
    
    # Wait for all connections to close
    await asyncio.sleep(0.2)
    gc.collect()
    
    # Try to remove database file (ignore if still locked on Windows)
    try:
        if os.path.exists(test_db):
            os.remove(test_db)
    except (PermissionError, OSError):
        pass


@pytest.mark.asyncio
async def test_deduplication_basic(test_app):
    """Test 1: Basic deduplication - duplicate events are dropped"""
    agg, store = test_app
    await agg.start()
    
    event1 = Event(
        topic="test.topic",
        event_id="evt_001",
        timestamp="2025-10-18T10:00:00Z",
        source="test",
        payload={"data": "first"}
    )
    event2 = Event(
        topic="test.topic",
        event_id="evt_001",
        timestamp="2025-10-18T10:01:00Z",
        source="test",
        payload={"data": "duplicate"}
    )
    
    await agg.publish([event1, event2])
    await asyncio.sleep(0.2)
    
    assert agg.stats["unique_processed"] == 1
    assert agg.stats["duplicate_dropped"] >= 1
    
    await agg.stop()


@pytest.mark.asyncio
async def test_persistence_after_restart(test_app):
    """Test 2: Dedup store persists after restart"""
    agg, store = test_app
    db_path = store.db_path
    
    await agg.start()
    event = Event(
        topic="test.persist",
        event_id="evt_persist_001",
        timestamp="2025-10-18T10:00:00Z",
        source="test",
        payload={}
    )
    await agg.publish([event])
    await asyncio.sleep(0.2)
    await agg.stop()
    
    new_store = DedupStore(db_path)
    new_agg = EventAggregator(new_store)
    await new_agg.start()
    
    await new_agg.publish([event])
    await asyncio.sleep(0.2)
    
    assert new_agg.stats["duplicate_dropped"] >= 1
    assert new_agg.stats["unique_processed"] == 0
    
    await new_agg.stop()


@pytest.mark.asyncio
async def test_schema_validation():
    """Test 3: Schema validation for events"""
    valid = Event(
        topic="valid",
        event_id="evt_valid",
        timestamp="2025-10-18T10:00:00Z",
        source="test",
        payload={"key": "value"}
    )
    assert valid.topic == "valid"
    
    with pytest.raises(ValueError):
        Event(
            topic="invalid",
            event_id="evt_invalid",
            timestamp="not-a-timestamp",
            source="test",
            payload={}
        )


@pytest.mark.asyncio
async def test_stats_consistency(test_app):
    """Test 4: GET /stats returns consistent data"""
    agg, store = test_app
    await agg.start()
    
    events = [
        Event(topic="topic1", event_id=f"evt_{i}", 
              timestamp="2025-10-18T10:00:00Z", source="test", payload={})
        for i in range(10)
    ]
    events.extend(events[:3])
    
    await agg.publish(events)
    await asyncio.sleep(0.3)
    
    stats = agg.get_stats()
    assert stats.received == 13
    assert stats.unique_processed == 10
    assert stats.duplicate_dropped == 3
    
    await agg.stop()


@pytest.mark.asyncio
async def test_get_events_filtering(test_app):
    """Test 5: GET /events with topic filter"""
    agg, store = test_app
    await agg.start()
    
    events = [
        Event(topic="topic_a", event_id=f"evt_a_{i}", 
              timestamp="2025-10-18T10:00:00Z", source="test", payload={})
        for i in range(5)
    ] + [
        Event(topic="topic_b", event_id=f"evt_b_{i}", 
              timestamp="2025-10-18T10:00:00Z", source="test", payload={})
        for i in range(3)
    ]
    
    await agg.publish(events)
    await asyncio.sleep(0.3)
    
    events_a = agg.get_events("topic_a")
    assert len(events_a) == 5
    
    events_b = agg.get_events("topic_b")
    assert len(events_b) == 3
    
    await agg.stop()


@pytest.mark.asyncio
async def test_stress_5000_events(test_app):
    """Test 6: Stress test with 5000+ events"""
    agg, store = test_app
    await agg.start()
    
    start_time = time.time()
    
    # Generate 5000 unique events
    unique_events = [
        Event(
            topic=f"topic_{i % 10}",
            event_id=f"evt_{i}",
            timestamp="2025-10-18T10:00:00Z",
            source="stress_test",
            payload={"index": i}
        )
        for i in range(5000)
    ]
    
    # Add 20% duplicates
    duplicate_events = random.choices(unique_events, k=1000)
    all_events = unique_events + duplicate_events
    random.shuffle(all_events)
    
    # Publish in batches
    batch_size = 200
    for i in range(0, len(all_events), batch_size):
        batch = all_events[i:i+batch_size]
        await agg.publish(batch)
    
    # Wait for queue to be processed
    while not agg.queue.empty():
        await asyncio.sleep(0.1)
    
    # Extra wait for final processing
    await asyncio.sleep(1.0)
    
    elapsed = time.time() - start_time
    
    # Assertions
    assert agg.stats["received"] == 6000, f"Expected 6000 received, got {agg.stats['received']}"
    assert agg.stats["unique_processed"] >= 4950, \
        f"Expected >= 4950 unique, got {agg.stats['unique_processed']}"
    assert agg.stats["duplicate_dropped"] >= 1000, \
        f"Expected >= 1000 duplicates, got {agg.stats['duplicate_dropped']}"
    assert elapsed < 35.0
    
    stats = agg.get_stats()
    assert len(stats.topics) == 10
    
    await agg.stop()
    
    print(f"\n✅ Stress test: {agg.stats['unique_processed']}/5000 unique, "
          f"{agg.stats['duplicate_dropped']} duplicates in {elapsed:.2f}s")


@pytest.mark.asyncio
async def test_concurrent_publishing(test_app):
    """Test 7: Concurrent publishing"""
    agg, store = test_app
    await agg.start()
    
    async def publisher(source_id: int):
        events = [
            Event(
                topic="concurrent",
                event_id=f"evt_{source_id}_{i}",
                timestamp="2025-10-18T10:00:00Z",
                source=f"source_{source_id}",
                payload={}
            )
            for i in range(100)
        ]
        await agg.publish(events)
    
    # Run 5 concurrent publishers
    await asyncio.gather(*[publisher(i) for i in range(5)])
    
    # Wait for queue to be processed
    while not agg.queue.empty():
        await asyncio.sleep(0.1)
    
    # Extra wait
    await asyncio.sleep(0.5)
    
    assert agg.stats["unique_processed"] >= 495, \
        f"Expected >= 495, got {agg.stats['unique_processed']}"
    
    await agg.stop()
    
    print(f"\n✅ Concurrent test: {agg.stats['unique_processed']}/500 processed")


@pytest.mark.asyncio
async def test_idempotency_guarantee(test_app):
    """Test 8: Idempotency guarantee"""
    agg, store = test_app
    await agg.start()
    
    event = Event(
        topic="idempotent",
        event_id="evt_idempotent_001",
        timestamp="2025-10-18T10:00:00Z",
        source="test",
        payload={"attempt": 1}
    )
    
    for _ in range(10):
        await agg.publish([event])
    
    await asyncio.sleep(0.3)
    
    assert agg.stats["unique_processed"] == 1
    assert agg.stats["duplicate_dropped"] == 9
    
    await agg.stop()


@pytest.mark.asyncio
async def test_batch_vs_single_publish(test_app):
    """Test 9: Batch and single publish"""
    agg, store = test_app
    await agg.start()
    
    single = Event(
        topic="single",
        event_id="evt_single",
        timestamp="2025-10-18T10:00:00Z",
        source="test",
        payload={}
    )
    await agg.publish([single])
    
    batch = [
        Event(
            topic="batch",
            event_id=f"evt_batch_{i}",
            timestamp="2025-10-18T10:00:00Z",
            source="test",
            payload={}
        )
        for i in range(10)
    ]
    await agg.publish(batch)
    
    await asyncio.sleep(0.3)
    
    assert agg.stats["unique_processed"] == 11
    
    await agg.stop()


@pytest.mark.asyncio
async def test_uptime_tracking(test_app):
    """Test 10: Uptime tracking"""
    agg, store = test_app
    await agg.start()
    
    await asyncio.sleep(1.0)
    
    stats = agg.get_stats()
    assert stats.uptime >= 1.0
    assert stats.uptime < 2.0
    
    await agg.stop()