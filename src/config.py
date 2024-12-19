import os
import json
from unittest.mock import patch
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application settings validated with Pydantic."""
    
    model_config = {
        'env_prefix': '',
        'extra': 'ignore',
        'env_nested_delimiter': '__'
    }

    def model_post_init(self, _: Any) -> None:
        """Handle environment file configuration after initialization."""
        env_file = getattr(self, '_env_file', '.env')
        if env_file:
            from dotenv import load_dotenv
            load_dotenv(env_file)
    
    @classmethod
    def get_test_settings(cls):
        """Get settings instance with clean environment for testing."""
        with patch.dict(os.environ, {}, clear=True):
            # Create settings with test-specific config
            return cls(
                _env_file=None,  # Disable .env file loading
                spacetraders_token=None,
                api_url='https://api.spacetraders.io/v2'
            )
    
    def __init__(self, **kwargs):
        if kwargs.pop('_clear_env', False):
            # Use class method for clean environment
            settings = self.get_test_settings()
            kwargs = {
                'spacetraders_token': settings.spacetraders_token,
                'api_url': settings.api_url,
                **kwargs
            }
        super().__init__(**kwargs)
    
    # SpaceTraders API configuration
    spacetraders_token: Optional[str] = Field(
        default=None,
        validation_alias='SPACETRADERS_TOKEN',
        description='SpaceTraders API token for authentication'
    )
    
    api_url: str = Field(
        default='https://api.spacetraders.io/v2',
        validation_alias='SPACETRADERS_API_URL',
        description='SpaceTraders API base URL'
    )
    
    def update_token(self, token: str) -> None:
        """Update the token and save it to both .env and config.json files."""
        self.spacetraders_token = token
        
        # Update .env file
        env_path = '.env'
        try:
            # Read existing content
            lines = []
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    lines = f.readlines()
            
            # Find and replace or append token
            token_line = f'SPACETRADERS_TOKEN={token}\n'
            token_found = False
            for i, line in enumerate(lines):
                if line.startswith('SPACETRADERS_TOKEN='):
                    lines[i] = token_line
                    token_found = True
                    break
            if not token_found:
                lines.append(token_line)
            
            # Write back to file
            with open(env_path, 'w') as f:
                for line in lines:
                    f.write(line)
            
            # Update config.json
            config_data = {}
            if os.path.exists('config.json'):
                with open('config.json', 'r') as f:
                    config_data = json.load(f)
            
            config_data['agent_symbol'] = "TEST_AGENT"  # In a real scenario, we'd get this from the registration response
            
            with open('config.json', 'w') as f:
                json.dump(config_data, f, indent=2)
            
            logger.info("Token updated and saved to .env and config.json files")
        except Exception as e:
            logger.error(f"Failed to update token in configuration files: {str(e)}")
            raise

    def validate_config(self) -> None:
        """Validate the configuration and log the status."""
        logger.info("Validating configuration...")
        
        if not self.spacetraders_token:
            logger.warning("SPACETRADERS_TOKEN not set")
        else:
            logger.info("SPACETRADERS_TOKEN is configured")
        
        logger.info(f"Using API URL: {self.api_url}")

# Create a global settings instance
def get_settings():
    """Get settings instance, allowing for test overrides."""
    return Settings()

settings = get_settings()