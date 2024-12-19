import os
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
    
    def update_token(self, token: str) -> None:
        """Update the token and save it to the .env file."""
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
            
            logger.info("Token updated and saved to .env file")
        except Exception as e:
            logger.error(f"Failed to update token in .env file: {str(e)}")
            raise

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