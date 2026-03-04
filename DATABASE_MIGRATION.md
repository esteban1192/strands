# Database Migration Guide

## Overview

The Strands API has been successfully migrated from in-memory storage to PostgreSQL database.

## Key Changes

### 1. Database Models
- All entities now use UUIDs instead of integers
- Added proper timestamps, configuration fields, and relationships
- Database schema is managed by Liquibase migrations

### 2. API Changes
- **UUIDs**: All IDs are now UUIDs (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- **Enhanced Models**: More fields available (name, description, configuration, status, timestamps)
- **Validation**: Proper field validation and constraints
- **HTTP Status Codes**: Better status code usage (201 for creation, 409 for conflicts)

### 3. New Endpoints
- `PUT` endpoints for updating resources
- Enhanced tool parameters management
- Proper relationship management between agents and tools

## Running the Application

### Step 1: Start Database Services
```bash
# Start PostgreSQL, PgAdmin, and run Liquibase migrations
docker-compose up -d

# Wait for all services to be healthy
docker-compose ps
```

### Step 2: Install Python Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Step 3: Test Database Connectivity
```bash
# Run the database test script
python test_db.py
```

### Step 4: Start the API Server
```bash
# Development mode with auto-reload
python main.py

# Or using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 5: Verify API
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- PgAdmin: http://localhost:8080 (admin@example.com / admin)

## API Usage Examples

### Create an Agent
```bash
curl -X POST "http://localhost:8000/agents" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Customer Support Agent",
    "description": "Handles customer inquiries",
    "status": "active"
  }'
```

### Create a Tool
```bash
curl -X POST "http://localhost:8000/tools" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Email Sender",
    "description": "Sends email notifications",
    "tool_type": "communication",
    "version": "1.0.0"
  }'
```

### Create an MCP
```bash
curl -X POST "http://localhost:8000/mcps" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenAI MCP",
    "description": "OpenAI Model Context Protocol",
    "configuration": {"api_key": "sk-..."}
  }'
```

## Database Access

### Using PgAdmin
1. Navigate to http://localhost:8080
2. Login with: admin@example.com / admin
3. Server is pre-configured in servers.json

### Direct Connection
```bash
# Connection details
Host: localhost
Port: 5432
Database: strands
Username: strands_user
Password: strands_password
```

## Troubleshooting

### Common Issues

1. **Connection Refused**: Ensure PostgreSQL container is running
   ```bash
   docker-compose logs postgres
   ```

2. **Migration Errors**: Check Liquibase container logs
   ```bash
   docker-compose logs liquibase
   ```

3. **Import Errors**: Ensure all dependencies are installed
   ```bash
   pip install -r requirements.txt
   ```

4. **UUID Format Errors**: Ensure you're using proper UUID format in API calls

### Reset Database
```bash
# Stop services, remove volumes, and restart
docker-compose down -v
docker-compose up -d
```

## Development Notes

- **Database Echo**: Set to `True` in development for SQL logging
- **Async Operations**: All database operations are async
- **Connection Pooling**: Managed by SQLAlchemy async engine
- **Transaction Management**: Service layer handles commits/rollbacks
- **Schema Management**: Use Liquibase for schema changes

## Next Steps

This migration provides a solid foundation for:
- Data persistence across restarts
- Better performance with proper indexing
- Concurrent access support
- Data integrity with constraints
- Audit trails with timestamps
- Configuration management with JSONB fields