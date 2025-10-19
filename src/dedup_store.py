import sqlite3
import os
from typing import Tuple, Set, Optional, List, Dict, Any
import threading
from datetime import datetime, timezone


class DedupStore:
    """Deduplication store dengan SQLite untuk persistensi"""
    
    def __init__(self, db_path: str = "dedup_store.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_events (
                    topic TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (topic, event_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_topic 
                ON processed_events(topic)
            """)
            conn.commit()
    
    def is_duplicate(self, topic: str, event_id: str) -> bool:
        """Check if event already processed"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM processed_events WHERE topic = ? AND event_id = ?",
                    (topic, event_id)
                )
                return cursor.fetchone() is not None
    
    def mark_processed(self, topic: str, event_id: str, timestamp: str) -> bool:
        """Mark event as processed (idempotent operation)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                try:
                    conn.execute(
                        """INSERT INTO processed_events 
                           (topic, event_id, timestamp, processed_at) 
                           VALUES (?, ?, ?, ?)""",
                        (topic, event_id, timestamp, datetime.now(timezone.utc).isoformat())
                    )
                    conn.commit()
                    return True
                except sqlite3.IntegrityError:
                    return False
    
    def get_processed_events(self, topic: Optional[str] = None) -> List[Tuple]:
        """Get list of processed events"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                if topic:
                    cursor = conn.execute(
                        """SELECT topic, event_id, timestamp, processed_at 
                           FROM processed_events WHERE topic = ?
                           ORDER BY processed_at DESC""",
                        (topic,)
                    )
                else:
                    cursor = conn.execute(
                        """SELECT topic, event_id, timestamp, processed_at 
                           FROM processed_events 
                           ORDER BY processed_at DESC"""
                    )
                return cursor.fetchall()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from dedup store"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM processed_events")
                total = cursor.fetchone()[0]
                
                cursor = conn.execute(
                    "SELECT topic, COUNT(*) FROM processed_events GROUP BY topic"
                )
                topics = {row[0]: row[1] for row in cursor.fetchall()}
                
                return {"total_unique": total, "topics": topics}
    
    def clear(self):
        """Clear all data (useful for testing)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM processed_events")
                conn.commit()
    
    def close(self):
        """Close database connections (for cleanup)"""
        # Force garbage collection to close connections
        pass