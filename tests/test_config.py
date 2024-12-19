import os
import pytest
from unittest.mock import patch
import logging
from src.config import Settings

def test_default_settings():
    """Test that default settings are loaded correctly"""
    settings = Settings()
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
    with caplog.at_level(logging.INFO):
        settings = Settings()
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
    from unittest.mock import mock_open as mock_open_func
    
    mock_file_content = 'SPACETRADERS_API_URL=https://api.example.com\n'
    m = mock_open_func(read_data=mock_file_content)
    
    with patch('src.config.os.path.exists', return_value=True), \
         patch('builtins.open', m), \
         caplog.at_level(logging.INFO):
        
        # Test updating token
        settings = Settings()
        settings.update_token('new-token')
        
        # Verify token was updated in memory
        assert settings.spacetraders_token == 'new-token'
        
        # Verify .env file was written to
        m.assert_called_with('.env', 'w')
        handle = m()
        
        # Get the written content
        written_content = ''.join([call.args[0] for call in handle.write.call_args_list])
        assert 'SPACETRADERS_TOKEN=new-token\n' in written_content
        
        # Verify logging
        assert any('Token updated and saved to .env file' in record.message 
                  for record in caplog.records)