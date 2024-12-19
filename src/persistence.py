import sqlite3
import json
import hashlib
import time
import logging
from typing import Any, Dict, Optional
from threading import Lock, Timer
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class StateManager:
    """Manages agent state persistence using SQLite with periodic saves and state hashing."""
    
    def __init__(self, db_path: str = 'agent_state.db', save_interval: int = 300):
        """
        Initialize the state manager.
        
        Args:
            db_path: Path to SQLite database file
            save_interval: How often to save state in seconds (default: 5 minutes)
        """
        self.db_path = db_path
        self.save_interval = save_interval
        self.last_hash = None
        self.lock = Lock()
        self.timer: Optional[Timer] = None
        
        self._init_db()
        self._start_periodic_save()
    
    def _init_db(self) -> None:
        """Initialize the SQLite database with required tables."""
        with self._get_db() as (conn, cursor):
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS agent_state (
                    id INTEGER PRIMARY KEY,
                    state_data TEXT NOT NULL,
                    state_hash TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            ''')
            conn.commit()
    
    @contextmanager
    def _get_db(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn, conn.cursor()
        finally:
            conn.close()
    
    def _compute_hash(self, state: Dict[str, Any]) -> str:
        """Compute a hash of the state dictionary."""
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()
    
    def _start_periodic_save(self) -> None:
        """Start the periodic save timer."""
        if self.timer:
            self.timer.cancel()
        self.timer = Timer(self.save_interval, self._periodic_save)
        self.timer.daemon = True
        self.timer.start()
    
    def _periodic_save(self) -> None:
        """Periodic save function that's called by the timer."""
        try:
            self.save_if_changed()
        finally:
            self._start_periodic_save()
    
    def save_state(self, state: Dict[str, Any]) -> None:
        """
        Save the current state to the database.
        
        Args:
            state: Dictionary containing the current state
        """
        with self.lock:
            state_hash = self._compute_hash(state)
            if state_hash == self.last_hash:
                logger.debug("State unchanged, skipping save")
                return
            
            with self._get_db() as (conn, cursor):
                cursor.execute(
                    'INSERT INTO agent_state (state_data, state_hash, timestamp) VALUES (?, ?, ?)',
                    (json.dumps(state), state_hash, time.time())
                )
                conn.commit()
                self.last_hash = state_hash
                logger.info("State saved to database")
    
    def save_if_changed(self) -> None:
        """Save the current state only if it has changed."""
        self.save_state(self.get_latest_state() or {})
    
    def get_latest_state(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent state from the database.
        
        Returns:
            The most recent state as a dictionary, or None if no state exists
        """
        with self._get_db() as (conn, cursor):
            cursor.execute(
                'SELECT state_data FROM agent_state ORDER BY timestamp DESC LIMIT 1'
            )
            result = cursor.fetchone()
            if result:
                return json.loads(result[0])
            return None
    
    def cleanup_old_states(self, keep_days: int = 7) -> None:
        """
        Remove states older than the specified number of days.
        
        Args:
            keep_days: Number of days of history to keep
        """
        cutoff_time = time.time() - (keep_days * 24 * 60 * 60)
        with self._get_db() as (conn, cursor):
            cursor.execute('DELETE FROM agent_state WHERE timestamp < ?', (cutoff_time,))
            conn.commit()
            logger.info(f"Cleaned up states older than {keep_days} days")
    
    def stop(self) -> None:
        """Stop the periodic save timer."""
        if self.timer:
            self.timer.cancel()
            self.timer = None