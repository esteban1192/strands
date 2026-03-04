import os
from typing import Optional


class AWSConfig:
    """AWS-related configuration."""
    
    def __init__(self):
        self.region: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "")
        self.secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self.session_token: Optional[str] = os.getenv("AWS_SESSION_TOKEN")
        
    def get_env_dict(self) -> dict:
        """Return AWS configuration as environment dictionary."""
        env_dict = {
            "AWS_ACCESS_KEY_ID": self.access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.secret_access_key,
            "AWS_DEFAULT_REGION": self.region,
        }
        
        if self.session_token:
            env_dict["AWS_SESSION_TOKEN"] = self.session_token
            
        return env_dict