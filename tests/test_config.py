import os
import pytest
from unittest.mock import patch
import logging
from src.config import Settings
import json

def test_default_settings(tmp_path):
    """Test that default settings are loaded correctly"""
    # Clean up any existing config files
    config_path = tmp_path / "config.json"
    env_path = tmp_path / ".env"
    if config_path.exists():
        config_path.unlink()
    if env_path.exists():
        env_path.unlink()
    with patch.dict(os.environ, {}, clear=True):  # Clear all environment variables
        settings = Settings(_env_file=None)  # Disable .env loading
        assert settings.api_url == 'https://api.spacetraders.io/v2'
        assert settings.spacetraders_token is None

def test_custom_settings(tmp_path):
    """Test that environment variables override defaults"""
    config_path = tmp_path / "config.json"
    env_path = tmp_path / ".env"
    if config_path.exists():
        config_path.unlink()
    if env_path.exists():
        env_path.unlink()
    with patch.dict(os.environ, {
        'SPACETRADERS_TOKEN': 'test-token',
        'SPACETRADERS_API_URL': 'https://test-api.example.com'
    }):
        settings = Settings()
        assert settings.api_url == 'https://test-api.example.com'
        assert settings.spacetraders_token == 'test-token'

def test_validate_config(caplog, tmp_path):
    """Test that configuration validation works and logs correctly"""
    config_path = tmp_path / "config.json"
    env_path = tmp_path / ".env"
    if config_path.exists():
        config_path.unlink()
    if env_path.exists():
        env_path.unlink()
    
    with patch.dict(os.environ, {}, clear=True), caplog.at_level(logging.INFO):  # Clear all environment variables
        settings = Settings(_env_file=None)  # Disable .env loading
        settings.validate_config()
    
        # Check warning about missing token
        assert any('SPACETRADERS_TOKEN not set' in record.message
                  for record in caplog.records)

def test_validate_config_with_token(caplog, tmp_path):
    """Test validation with token present"""
    config_path = tmp_path / "config.json"
    env_path = tmp_path / ".env"
    if config_path.exists():
        config_path.unlink()
    if env_path.exists():
        env_path.unlink()
    with patch.dict(os.environ, {'SPACETRADERS_TOKEN': 'test-token'}), caplog.at_level(logging.INFO):
        settings = Settings()
        settings.validate_config()
        
        # Check token configured message
        assert any('SPACETRADERS_TOKEN is configured' in record.message 
                  for record in caplog.records)

def test_update_token(tmp_path, caplog):
    """Test token update functionality"""
    config_path = tmp_path / "config.json"
    env_path = tmp_path / ".env"
    
    # Test updating token with no existing config
    with patch.dict(os.environ, {}, clear=True), caplog.at_level(logging.INFO):
        settings = Settings(_env_file=None)
        settings.update_token("new-token", str(config_path), str(env_path))
        
        # Check if token was updated in memory
        assert settings.spacetraders_token == "new-token"
        
        # Check if config file was created with correct content
        assert config_path.exists()
        with open(config_path) as f:
            config = json.load(f)
            assert config.get("SPACETRADERS_TOKEN") == "new-token"
        
        # Check if .env file was created with correct content
        assert env_path.exists()
        with open(env_path) as f:
            content = f.read()
            assert 'SPACETRADERS_TOKEN=new-token\n' in content
        
        # Check if appropriate log message was created
        assert any("Token updated and saved to .env and config.json files" in record.message
                  for record in caplog.records)
    
    # Test updating existing token
    caplog.clear()
    with patch.dict(os.environ, {}, clear=True), caplog.at_level(logging.INFO):
        settings = Settings(_env_file=None)
        settings.update_token("newer-token", str(config_path), str(env_path))
        
        # Check if token was updated in memory
        assert settings.spacetraders_token == "newer-token"
        
        # Check if config file was updated with new token
        with open(config_path) as f:
            config = json.load(f)
            assert config.get("SPACETRADERS_TOKEN") == "newer-token"
        
        # Check if .env file was updated with new token
        with open(env_path) as f:
            content = f.read()
            assert 'SPACETRADERS_TOKEN=newer-token\n' in content
        
        # Check if appropriate log message was created
        assert any("Token updated and saved to .env and config.json files" in record.message
                  for record in caplog.records)