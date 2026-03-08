"""
FastAPI application for Strands API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from contextlib import asynccontextmanager

from api.models import HealthResponse
from api.resources import agent, tool, mcp, tool_parameters, chat, agent_sub_agents, task, webhook
from api.database import engine
from core.mcp_session_cache import session_cache
from core.task_runner import task_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    print("Starting Strands API...")
    print("Database connection configured")
    # Note: Database tables are managed by Liquibase migrations

    # Recover interrupted background tasks from DB
    await task_runner.recover()
    print("Task runner recovery complete")

    yield

    # Shutdown
    print("Shutting down Strands API...")
    session_cache.shutdown()
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="Strands API",
    description="API for managing Agents, MCPs, Tools and Tool Parameters",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agent.router)
app.include_router(tool.router)
app.include_router(mcp.router)
app.include_router(tool_parameters.router)
app.include_router(chat.router)
app.include_router(agent_sub_agents.router)
app.include_router(task.router)
app.include_router(webhook.router)

# Basic health endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint with basic health check"""
    return HealthResponse(status="healthy", message="Strands API is running with PostgreSQL database")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(status="healthy", message="All systems operational")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)