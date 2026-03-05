# Strands

A web UI for managing [Strands Agents](https://github.com/strands-agents/sdk-python) — configure agents, MCP servers, tools, approval workflows, and chat with agents in real time.

| Layer | Tech | Port |
|-------|------|------|
| Frontend | React 19, TypeScript, Vite | `3000` |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async) | `8000` |
| Database | PostgreSQL 15, Liquibase migrations | `5432` |

---

## Prerequisites

- **Docker** and **Docker Compose** (v2)
- **AWS credentials** with access to Amazon Bedrock (the agents use Bedrock models)

That's it — everything runs in containers.

---

## Local Setup

### 1. Clone the repo

```bash
git clone https://git.epam.com/esteban_ospina/strands.git
cd strands
```

### 2. Create `.api.env`

Create a file called `.api.env` in the project root with the following variables:

```dotenv
PORT=8000
DATABASE_URL=postgresql+asyncpg://strands_user:strands_password@postgres:5432/strands
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-aws-access-key>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-key>
AWS_SESSION_TOKEN=<your-aws-session-token>
```

> **Note:** If you use temporary credentials (SSO / `aws sts assume-role`), you'll need to refresh `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` whenever they expire.

### 3. Start everything

```bash
docker compose up --build
```

This brings up all services:

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API / Docs | http://localhost:8000/docs |
| PgAdmin | http://localhost:8080 |
| MCP Memory Server (test) | http://localhost:8001 |

Liquibase runs automatically on startup and applies any pending database migrations.

### 4. Verify

Open http://localhost:3000 — you should see the Strands UI.

---

## Useful Commands

```bash
# Start in detached mode
docker compose up -d

# Rebuild a specific service after code changes
docker compose up --build api

# View logs
docker compose logs -f api
docker compose logs -f frontend

# Stop everything
docker compose down

# Stop and remove volumes (resets database)
docker compose down -v
```

---

## Project Structure

```
strands/
├── backend/          # FastAPI application
├── frontend/         # React + Vite application
├── liquibase/        # Database migrations
├── pgadmin/          # PgAdmin config
├── docker-compose.yml
└── .api.env          # Your local env vars (not committed)
```
