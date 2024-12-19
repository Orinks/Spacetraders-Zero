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