import os
import pytest
from unittest.mock import patch
import logging
from src.config import Settings

def test_default_settings():
    """Test that default settings are loaded correctly"""
    # Clean up any existing config files
    if os.path.exists('config.json'):
        os.remove('config.json')
    if os.path.exists('.env'):
        os.remove('.env')
    settings = Settings(_env_file=None)  # Disable .env loading
    assert settings.api_url == 'https://api.spacetraders.io/v2'
    assert settings.spacetraders_token is None

def test_custom_settings():
    """Test that environment variables override defaults"""
    with patch.dict(os.environ, {
        'SPACETRADERS_TOKEN': 'test-token',
        'SPACETRADERS_API_URL': 'https://test-api.example.com'
    }):
        settings = Settings()
        assert settings.api_url == 'https://test-api.example.com'
        assert settings.spacetraders_token == 'test-token'

def test_validate_config(caplog):
    """Test that configuration validation works and logs correctly"""
    # Clean up any existing config files
    if os.path.exists('config.json'):
        os.remove('config.json')
    if os.path.exists('.env'):
        os.remove('.env')
        
    with caplog.at_level(logging.INFO):
        settings = Settings(_env_file=None)  # Disable .env loading
        settings.validate_config()
        
        # Check warning about missing token
        assert any('SPACETRADERS_TOKEN not set' in record.message 
                  for record in caplog.records)
        
        # Check API URL info
        assert any('Using API URL: https://api.spacetraders.io/v2' in record.message 
                  for record in caplog.records)

def test_validate_config_with_token(caplog):
    """Test validation with token present"""
    with patch.dict(os.environ, {'SPACETRADERS_TOKEN': 'test-token'}):
        with caplog.at_level(logging.INFO):
            settings = Settings()
            settings.validate_config()
            
            # Check token configured message
            assert any('SPACETRADERS_TOKEN is configured' in record.message 
                      for record in caplog.records)

def test_update_token(tmp_path, caplog):
    """Test token update functionality"""
    from unittest.mock import mock_open as mock_open_func, call, Mock
    
    mock_env_content = 'SPACETRADERS_API_URL=https://api.example.com\n'
    mock_config_content = '{"agent_symbol": "OLD_AGENT"}'
    
    # Create a mock file that behaves like a real file
    mock_file = Mock()
    mock_file.read.side_effect = [mock_env_content, mock_config_content]
    mock_file.readlines.return_value = [mock_env_content]
    mock_file.write = Mock()
    mock_file.__enter__ = Mock(return_value=mock_file)
    mock_file.__exit__ = Mock()
    
    m = mock_open_func()
    m.return_value = mock_file
    
    with patch('src.config.os.path.exists', return_value=True), \
         patch('builtins.open', m), \
         caplog.at_level(logging.INFO):
        
        # Test updating token
        settings = Settings()
        settings.update_token('new-token')
        
        # Verify token was updated in memory
        assert settings.spacetraders_token == 'new-token'
        
        # Verify all file operations
        expected_calls = [
            call('.env', 'r'),           # First read .env
            call('.env', 'w'),           # Write to .env
            call('config.json', 'r'),    # Then read config.json
            call('config.json', 'w')     # Write to config.json
        ]
        assert m.call_args_list == expected_calls
        
        # Get the written content for .env
        env_handle = m.return_value
        env_written = ''.join([call.args[0] for call in env_handle.write.call_args_list])
        assert 'SPACETRADERS_TOKEN=new-token\n' in env_written
        
        # Verify logging
        assert any('Token updated and saved to .env and config.json files' in record.message 
                  for record in caplog.records)