# Strands Backend API

A FastAPI-based REST API service for managing Agents, MCPs, Tools, and Tool Parameters.

## Features

- **Auto-generated API Documentation**: Available at `/docs` (Swagger UI) and `/redoc` (ReDoc)
- **CRUD Operations**: Full Create, Read, Update, Delete operations for all entities
- **Relationship Management**: Assign tools to agents and manage relationships
- **Health Checks**: Built-in health check endpoints for monitoring
- **CORS Support**: Cross-origin resource sharing enabled for frontend integration

## API Endpoints

### Health
- `GET /` - Root endpoint with basic status
- `GET /health` - Health check endpoint

### Agents
- `GET /agents` - List all agents
- `POST /agents` - Create a new agent
- `GET /agents/{agent_id}` - Get specific agent
- `DELETE /agents/{agent_id}` - Delete an agent
- `POST /agents/{agent_id}/tools/{tool_id}` - Assign tool to agent
- `DELETE /agents/{agent_id}/tools/{tool_id}` - Remove tool from agent

### Tools
- `GET /tools` - List all tools
- `POST /tools` - Create a new tool
- `GET /tools/{tool_id}` - Get specific tool
- `DELETE /tools/{tool_id}` - Delete a tool

### MCPs
- `GET /mcps` - List all MCPs
- `POST /mcps` - Create a new MCP
- `GET /mcps/{mcp_id}` - Get specific MCP
- `DELETE /mcps/{mcp_id}` - Delete an MCP

### Tool Parameters
- `GET /tool-parameters` - List all tool parameters
- `POST /tool-parameters` - Create new tool parameters
- `GET /tool-parameters/{tp_id}` - Get specific tool parameters
- `DELETE /tool-parameters/{tp_id}` - Delete tool parameters

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload

# Or run with python
python main.py
```

The API will be available at `http://localhost:8000`

## Docker

The service is containerized and can be run with Docker:

```bash
# Build the image
docker build -t strands-api .

# Run the container
docker run -p 8000:8000 strands-api
```

## Development

The API is built using:
- **FastAPI**: Modern, fast web framework for building APIs
- **Pydantic**: Data validation and settings management
- **Uvicorn**: ASGI server for running the application

### Data Storage

Currently uses in-memory storage for demonstration purposes. In production, you should integrate with a proper database using the PostgreSQL instance defined in docker-compose.

### Architecture

The API uses a modern layered architecture:
- **SQLAlchemy models** for database persistence and relationships
- **Pydantic models** for request/response validation and serialization
- **Service layer** for business logic and database operations
- **FastAPI routers** for HTTP endpoints and API documentation