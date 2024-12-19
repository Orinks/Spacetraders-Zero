import os
import time
import pytest
from src.persistence import StateManager

@pytest.fixture
def state_manager(tmp_path):
    """Create a state manager with a temporary database file."""
    db_path = str(tmp_path / "test_state.db")
    manager = StateManager(db_path=db_path, save_interval=1)
    yield manager
    manager.stop()
    if os.path.exists(db_path):
        os.remove(db_path)

def test_save_and_load_state(state_manager):
    """Test basic save and load functionality."""
    test_state = {"key": "value", "number": 42}
    state_manager.save_state(test_state)
    loaded_state = state_manager.get_latest_state()
    assert loaded_state == test_state

def test_state_hashing(state_manager):
    """Test that identical states are not saved multiple times."""
    test_state = {"key": "value"}
    
    # Save the same state twice
    state_manager.save_state(test_state)
    first_hash = state_manager.last_hash
    state_manager.save_state(test_state)
    second_hash = state_manager.last_hash
    
    assert first_hash == second_hash

def test_periodic_save(state_manager):
    """Test that periodic save works."""
    test_state = {"key": "value"}
    state_manager.save_state(test_state)
    
    # Modify state and wait for periodic save
    modified_state = {"key": "new_value"}
    state_manager.save_state(modified_state)
    time.sleep(2)  # Wait for periodic save
    
    loaded_state = state_manager.get_latest_state()
    assert loaded_state == modified_state

def test_cleanup_old_states(state_manager):
    """Test cleanup of old states."""
    # Save some states with different timestamps
    old_state = {"key": "old"}
    new_state = {"key": "new"}
    
    with state_manager._get_db() as (conn, cursor):
        # Insert old state (8 days ago)
        old_time = time.time() - (8 * 24 * 60 * 60)
        cursor.execute(
            'INSERT INTO agent_state (state_data, state_hash, timestamp) VALUES (?, ?, ?)',
            ('{"key": "old"}', 'old_hash', old_time)
        )
        # Insert new state
        cursor.execute(
            'INSERT INTO agent_state (state_data, state_hash, timestamp) VALUES (?, ?, ?)',
            ('{"key": "new"}', 'new_hash', time.time())
        )
        conn.commit()
    
    # Clean up states older than 7 days
    state_manager.cleanup_old_states(keep_days=7)
    
    # Check that only the new state remains
    loaded_state = state_manager.get_latest_state()
    assert loaded_state == new_state