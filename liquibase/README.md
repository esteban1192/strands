# Strands Database Schema Management with Liquibase

This directory contains the Liquibase configuration and database schema definitions for the Strands project.

## Overview

The database schema supports the following core entities:
- **MCPs** (Model Context Protocol instances)
- **Agents** (AI agents in the system)
- **Tools** (Tools that agents can use)
- **Tool Parameters** (Configuration parameters for tools)
- **Agent-Tool Relationships** (Many-to-many mapping)

## Directory Structure

```
strands/                              # Project root
├── docker-compose.yml                # Docker services configuration
└── liquibase/
    ├── changelog.xml                 # Main changelog file
    ├── liquibase.properties          # Database configuration
    ├── liquibase.sh                  # Management script (Linux/Mac)
    ├── liquibase.bat                 # Management script (Windows)
    ├── README.md                     # This file
    ├── init-scripts/
    │   └── 01-init.sql              # Database initialization
    └── changelogs/
        ├── 001-create-schema.xml     # Schema creation
        ├── 002-create-mcps-table.xml # MCPs table
        ├── 003-create-agents-table.xml # Agents table
        ├── 004-create-tools-table.xml # Tools table
        ├── 005-create-tool-parameters-table.xml # Tool parameters
        ├── 006-create-agent-tools-relationship.xml # Relations
        ├── 007-create-indexes.xml    # Performance indexes
        └── 008-insert-sample-data.xml # Sample data (dev only)
```

## Quick Start

### 1. Start Local PostgreSQL (Docker)

```bash
# Start PostgreSQL with Docker Compose (from project root)
cd ..  # or navigate to project root
docker-compose up -d postgres

# Check if database is ready
docker-compose ps
```

### 2. Configure Database Connection

Update `liquibase.properties` with your database credentials:

```properties
# For local Docker setup
url=jdbc:postgresql://localhost:5432/strands
username=strands_user
password=strands_password

# For production, update accordingly
```

### 3. Apply Database Schema

```bash
# Make script executable (Linux/Mac)
chmod +x liquibase.sh

# Apply all changes
./liquibase.sh update

# Or with development sample data
./liquibase.sh dev-update
```

### 4. Verify Installation

```bash
# Check database status
./liquibase.sh status

# Validate changelog
./liquibase.sh validate
```

## Database Schema

### Tables Overview

#### strands.mcps
Model Context Protocol instances that manage tool communication.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Unique MCP name |
| description | TEXT | MCP description |
| configuration | JSONB | MCP configuration |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### strands.agents
AI agents that can use tools to perform tasks.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Unique agent name |
| description | TEXT | Agent description |
| configuration | JSONB | Agent configuration |
| status | VARCHAR(50) | Agent status (active/inactive/paused) |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### strands.tools
Tools that can be used by agents, optionally managed by MCPs.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| mcp_id | UUID | Optional MCP reference |
| name | VARCHAR(255) | Tool name |
| description | TEXT | Tool description |
| tool_type | VARCHAR(100) | Tool type/category |
| configuration | JSONB | Tool configuration |
| is_active | BOOLEAN | Active status |
| version | VARCHAR(50) | Tool version |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### strands.tool_parameters
Configuration parameters for tools.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| tool_id | UUID | Tool reference |
| parameter_name | VARCHAR(255) | Parameter name |
| parameter_type | VARCHAR(50) | Parameter type |
| parameter_value | TEXT | Current value |
| default_value | TEXT | Default value |
| is_required | BOOLEAN | Required flag |
| validation_rules | JSONB | Validation configuration |
| description | TEXT | Parameter description |
| sort_order | INTEGER | Display order |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### strands.agent_tools
Many-to-many relationship between agents and tools.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| agent_id | UUID | Agent reference |
| tool_id | UUID | Tool reference |
| added_at | TIMESTAMP | Association timestamp |
| is_enabled | BOOLEAN | Enable status |
| configuration_override | JSONB | Override configuration |
| usage_priority | INTEGER | Usage priority |

### Relationships

- **MCPs → Tools**: One-to-many (optional)
- **Tools → Tool Parameters**: One-to-many
- **Agents ↔ Tools**: Many-to-many via agent_tools

## Usage Examples

### Check Status
```bash
# See what changes are pending
./liquibase.sh status
```

### Apply Changes
```bash
# Apply all pending changes
./liquibase.sh update

# Apply only the next 3 changes
./liquibase.sh update-count 3

# Apply with specific context
./liquibase.sh dev-update     # development + sample data
./liquibase.sh test-update    # test environment
./liquibase.sh prod-update    # production (no sample data)
```

### Rollback Changes
```bash
# Rollback last change
./liquibase.sh rollback-count 1

# Rollback to a specific tag
./liquibase.sh tag production-v1.0
./liquibase.sh rollback production-v1.0
```

### Validation and Docs
```bash
# Validate changelog
./liquibase.sh validate

# Generate documentation
./liquibase.sh generate-docs

# View deployment history
./liquibase.sh history
```

## Environment-Specific Configurations

### Development
- Includes sample data via context `development`
- Relaxed constraints for testing
- Additional debugging indexes

### Test
- Clean schema without sample data
- Context `test` for test-specific changes
- Performance monitoring enabled

### Production
- Strict constraints and validation
- Context `production` for prod-specific optimizations
- No sample data insertion
- Comprehensive indexing strategy

## Troubleshooting

### Common Issues

1. **Connection Failed**
   ```bash
   # Check if PostgreSQL is running
   docker-compose ps
   
   # Check connection
   psql -h localhost -U strands_user -d strands
   ```

2. **Liquibase Not Found**
   ```bash
   # Install Liquibase or set LIQUIBASE_HOME
   export LIQUIBASE_HOME=/path/to/liquibase
   ```

3. **Checksum Mismatch**
   ```bash
   # Clear checksums and re-apply
   ./liquibase.sh clear-checksums
   ./liquibase.sh update
   ```

4. **Permission Denied**
   ```bash
   # Make script executable
   chmod +x liquibase.sh
   ```

### Reset Database
```bash
# Stop and remove containers (from project root)
cd ..  # or navigate to project root
docker-compose down -v

# Restart with fresh database
docker-compose up -d postgres

# Re-apply schema (back to liquibase directory)
cd liquibase
./liquibase.sh dev-update
```

## Integration with Application

The schema is designed to work seamlessly with the FastAPI application:

- **Agent models** → `strands.agents` + `strands.agent_tools`
- **Tool models** → `strands.tools` with MCP relationship
- **Tool Parameter models** → `strands.tool_parameters`
- **MCP models** → `strands.mcps`

Each table includes:
- UUID primary keys for distributed systems
- JSONB configuration fields for flexibility
- Timestamp tracking for audit trails
- Proper foreign key relationships with cascade behavior
- Performance indexes for common query patterns

## Next Steps

1. **Update Application Code**: Modify your Python interfaces to work with the database
2. **Add Migrations**: Create new changelog files for schema evolution
3. **Setup CI/CD**: Integrate Liquibase into your deployment pipeline
4. **Monitor Performance**: Add database monitoring and query optimization
5. **Backup Strategy**: Implement regular database backups

For questions or issues, refer to the [Liquibase documentation](https://docs.liquibase.com/) or check the project's issue tracker.