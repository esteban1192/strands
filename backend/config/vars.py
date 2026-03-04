from .aws import AWSConfig


class Config:
    """Application configuration object."""
    
    def __init__(self):
        # AWS Configuration
        self.aws = AWSConfig()


# Global configuration instance
config = Config()
