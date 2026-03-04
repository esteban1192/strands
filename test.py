import os
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.tools.mcp import MCPClient

REGION = "us-east-1"

def ecs_mcp_transport():
    return stdio_client(
        StdioServerParameters(
            command="uvx",
            args=[
                "mcp-proxy-for-aws@latest",
                f"https://ecs-mcp.{REGION}.api.aws/mcp",
                "--service", "ecs-mcp",
                "--region", REGION,
            ],
            env={
                "AWS_ACCESS_KEY_ID": os.environ["AWS_ACCESS_KEY_ID"],
                "AWS_SECRET_ACCESS_KEY": os.environ["AWS_SECRET_ACCESS_KEY"],
                "AWS_SESSION_TOKEN": os.environ.get("AWS_SESSION_TOKEN", ""),
                "AWS_DEFAULT_REGION": REGION,
            },
        )
    )

# Create MCP client (STDIO transport)
ecs_mcp_client = MCPClient(ecs_mcp_transport)

# Create agent using Bedrock model
agent = Agent(
    model="anthropic.claude-3-haiku-20240307-v1:0",
    tools=[ecs_mcp_client],
)

if __name__ == "__main__":
    response = agent("List ECS clusters in my account")
    print(response)