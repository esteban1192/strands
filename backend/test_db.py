#!/usr/bin/env python3
"""
Database connectivity test script for Strands API
"""
import asyncio
import sys
import os

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.database import engine, get_db_session
from api.services import AgentService, ToolService, MCPService


async def test_database_connection():
    """Test database connectivity and basic operations"""
    try:
        print("🔌 Testing database connection...")
        
        # Test basic connection
        async with get_db_session() as session:
            print("✅ Database connection successful!")
            
            # Test getting all agents (should work even if empty)
            agents = await AgentService.get_all(session)
            print(f"📊 Found {len(agents)} agents in database")
            
            # Test getting all tools
            tools = await ToolService.get_all(session)
            print(f"🔧 Found {len(tools)} tools in database")
            
            # Test getting all MCPs
            mcps = await MCPService.get_all(session)
            print(f"🤖 Found {len(mcps)} MCPs in database")
            
            print("✅ All database operations working correctly!")
            
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n🔍 Troubleshooting tips:")
        print("1. Ensure Docker containers are running: docker-compose up -d")
        print("2. Check if Liquibase migrations have run successfully")
        print("3. Verify DATABASE_URL environment variable")
        print("4. Check PostgreSQL container logs: docker logs strands-postgres")
        return False
    
    finally:
        await engine.dispose()
    
    return True


async def main():
    """Main test function"""
    print("🚀 Strands API Database Test")
    print("=" * 40)
    
    success = await test_database_connection()
    
    if success:
        print("\n🎉 Database test completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Database test failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())