# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (including Node.js for stdio MCP servers)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy application code first
COPY . .

# Install Python dependencies after copying code
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Generate AWS credentials/config from env vars at startup so that MCP servers
# using boto3.Session(profile_name='default') can resolve the "default" profile.
CMD ["sh", "-c", "\
  mkdir -p ~/.aws && \
  printf '[default]\\naws_access_key_id = %s\\naws_secret_access_key = %s\\n' \"$AWS_ACCESS_KEY_ID\" \"$AWS_SECRET_ACCESS_KEY\" > ~/.aws/credentials && \
  printf '[default]\\nregion = %s\\n' \"$AWS_REGION\" > ~/.aws/config && \
  pip install --no-cache-dir -r requirements.txt && \
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload"]