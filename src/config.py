from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application settings validated with Pydantic."""
    
    model_config = {
        'env_prefix': '',
        'env_file': '.env',
        'env_file_encoding': 'utf-8',
        'extra': 'ignore'
    }
    
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
    
    def validate_config(self) -> None:
        """Validate the configuration and log the status."""
        logger.info("Validating configuration...")
        
        if not self.spacetraders_token:
            logger.warning(
                "SPACETRADERS_TOKEN not set. "
                "You will need to register a new agent through the UI."
            )
        else:
            logger.info("SPACETRADERS_TOKEN is configured")
        
        logger.info(f"Using API URL: {self.api_url}")

# Create a global settings instance
settings = Settings()