#!/bin/bash
set -e

# Create additional schemas and extensions if needed
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create extensions
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "pg_trgm";
    CREATE EXTENSION IF NOT EXISTS "btree_gin";
    
    -- Create application user (different from admin user)
    CREATE USER strands_app WITH PASSWORD 'app_password';
    
    -- Grant necessary privileges
    GRANT CONNECT ON DATABASE strands TO strands_app;
    GRANT USAGE ON SCHEMA public TO strands_app;
    GRANT CREATE ON SCHEMA public TO strands_app;
    
    -- Create function for updating timestamps
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS \$\$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    \$\$ language 'plpgsql';
    
    -- Log initialization
    \echo 'Database initialization completed successfully'
EOSQL