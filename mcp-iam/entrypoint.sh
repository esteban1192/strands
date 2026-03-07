#!/bin/bash
set -e

pip install --quiet --no-cache-dir /opt/mcp-server
exec npx -y supergateway "$@"
