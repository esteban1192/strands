"""
Database configuration and session management
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://strands_user:strands_password@localhost:5432/strands")

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    future=True
)

# Create sessionmaker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for our models
Base = declarative_base()

@asynccontextmanager
async def get_db_session():
    """Get database session with proper cleanup"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_db():
    """Dependency for FastAPI to get database session"""
    async with get_db_session() as session:
        yield session