FROM ghcr.io/mark3labs/mcp-filesystem-server:latest AS mcp

FROM node:20-slim

COPY --from=mcp /app/server /usr/local/bin/mcp-filesystem-server

ENTRYPOINT ["npx", "-y", "supergateway"]
