# GitHub Copilot Instructions — Strands Workspace

## Environment & Tooling

### Docker-First Development

- **Always check `docker-compose.yml`** in the project root to understand how services are built, connected, and configured. All services (PostgreSQL, PgAdmin, Liquibase, FastAPI backend, React frontend) are defined there.
- **Never install packages, runtimes, databases, or any software directly on the host machine.** Everything must run inside Docker containers. If a task requires additional software (e.g., a new database, cache, message broker, CLI tool), add or modify a service in `docker-compose.yml` instead.
- When adding a new dependency, add it to the appropriate container's dependency file (`backend/requirements.txt` for Python, `frontend/package.json` for Node) — the containers will pick it up on rebuild.
- Use `docker compose up`, `docker compose build`, and `docker compose exec` to run, build, and interact with services.

### Container Networking

- Services communicate over the `strands-network` Docker bridge network using service names as hostnames (e.g., `postgres`, `api`).
- The frontend Vite dev server proxies `/api` requests to `http://api:8000` with the `/api` prefix stripped.
- The backend connects to PostgreSQL at `postgresql+asyncpg://strands_user:strands_password@postgres:5432/strands`.

---

## Project Architecture

This is a 3-tier application:

| Layer | Tech | Directory |
|-------|------|-----------|
| Frontend | React 19, TypeScript, Vite, React Router v7 | `frontend/` |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 | `backend/` |
| Database | PostgreSQL 15, Liquibase migrations | `liquibase/`, `pgadmin/` |

### Entities

The application manages four core entities: **Agent**, **Tool**, **MCP**, and **ToolParameter**. Each entity follows an identical structural pattern across the full stack (see conventions below).

---

## Backend Conventions (Python / FastAPI)

### Project Structure

```
backend/
├── main.py                     # FastAPI app setup, CORS, router includes, lifespan
├── api/
│   ├── database.py             # Async engine, session maker, Base, get_db dependency
│   ├── db_models.py            # SQLAlchemy ORM models
│   ├── models/                 # Pydantic request/response schemas
│   │   ├── agent_models.py
│   │   ├── tool_models.py
│   │   ├── mcp_models.py
│   │   └── tool_parameters_models.py
│   ├── resources/              # FastAPI routers (thin controllers)
│   │   ├── agent.py
│   │   ├── tool.py
│   │   ├── mcp.py
│   │   └── tool_parameters.py
│   └── services/               # Business logic (static async methods)
│       ├── agent_service.py
│       ├── tool_service.py
│       ├── mcp_service.py
│       └── tool_parameters_service.py
```

### Patterns to Follow

- **Async everywhere**: All DB operations use `AsyncSession` from SQLAlchemy 2.0 with `asyncpg`.
- **Service layer**: Business logic lives in service classes with `@staticmethod async` methods. Routes must stay thin — delegate to services.
- **Dependency injection**: Inject `AsyncSession` via `Depends(get_db)` in route functions.
- **ORM models**: Use `Mapped[]` type annotations, UUID primary keys (`uuid.uuid4`), `created_at`/`updated_at` timestamps, and the `strands` schema (`__table_args__ = {"schema": "strands"}`).
- **Pydantic models**: Name them `<Entity>Response`, `<Entity>CreateRequest`, `<Entity>UpdateRequest`. Use `Field(...)` with validation constraints. Update models have all fields `Optional` for partial updates. Manual mapping from ORM to Pydantic (no `from_attributes`).
- **HTTP status codes**: POST → `201`, DELETE → JSON message, unique violation → `409`, not found → `404`.
- **Naming**: snake_case for everything. Class names are PascalCase.
- **Barrel exports**: Every package has an `__init__.py` re-exporting its public API.

### Adding a New Entity

1. Add SQLAlchemy model in `api/db_models.py`
2. Add Pydantic schemas in `api/models/<entity>_models.py`
3. Add service class in `api/services/<entity>_service.py`
4. Add router in `api/resources/<entity>.py`
5. Include the router in `main.py`
6. Add Liquibase migration (see Database section)

---

## Frontend Conventions (React / TypeScript)

### Project Structure

```
frontend/src/
├── App.tsx                    # Renders RouterProvider
├── main.tsx                   # Entry point
├── api/                       # Axios-based API modules
│   ├── client.ts              # Shared Axios instance with interceptor
│   ├── agents.ts, tools.ts, mcps.ts, toolParameters.ts
├── components/
│   ├── common/                # Reusable UI (ConfirmDialog, EmptyState, ErrorMessage, LoadingSpinner, StatusBadge)
│   └── layout/                # Layout + Sidebar
├── hooks/                     # useApi, useMutation generic hooks
├── pages/                     # Route pages organized by entity
│   ├── agents/                # AgentList, AgentForm
│   ├── tools/
│   ├── mcps/
│   └── shared/                # Shared page CSS (FormPage.css, etc.)
├── router/                    # createBrowserRouter config
├── styles/                    # Global CSS
└── types/                     # TypeScript interfaces per entity
```

### Patterns to Follow

- **API modules**: Export a const object with methods (`getAll`, `getById`, `create`, `update`, `delete`). Each method returns `apiClient.<method>(...).then(r => r.data)`.
- **TypeScript types**: Interfaces named `<Entity>`, `<Entity>CreateRequest`, `<Entity>UpdateRequest`. Use snake_case field names to match the backend JSON. Use union types for statuses.
- **Hooks**: Use the generic `useApi<T>(fetcher, deps)` for data fetching and `useMutation<TArgs, TResult>(mutator)` for mutations. No external state management library.
- **Components**: Default function exports. Dual-purpose form components (create + edit in one component, determined by `useParams().id`). 
- **Routing**: Flat nested routes under the `Layout` element — `/{entity}`, `/{entity}/new`, `/{entity}/:id`, `/{entity}/:id/edit`.
- **CSS**: Plain CSS files co-located with components. BEM-like class names. No CSS-in-JS, no Tailwind, no CSS modules.
- **Path alias**: Use `@/` to import from `src/` (configured in Vite and tsconfig).
- **Barrel exports**: Every directory has an `index.ts` re-exporting its modules.

---

## Database & Migrations (Liquibase)

- Migrations are in `liquibase/changelogs/`, numbered sequentially: `001-...`, `002-...`, etc.
- The master file `liquibase/changelog.xml` includes each changelog file in order.
- All tables live in the `strands` PostgreSQL schema.
- ChangeSet conventions: ID matches filename prefix, author is `system`, context is `all`.
- Every changeset must include a `<comment>` and an explicit `<rollback>` block.
- UUIDs as primary keys with `defaultValueComputed="gen_random_uuid()"`.
- Timestamps use `TIMESTAMP WITH TIME ZONE` with `CURRENT_TIMESTAMP` default.
- Foreign keys: `onDelete="SET NULL"`, `onUpdate="CASCADE"`.
- **Never modify existing changesets.** Always create a new numbered changeset file.
- The Liquibase container runs migrations automatically on `docker compose up`.

---

## General Rules

- **UUIDs** are used for all entity IDs across the entire stack.
- **Naming**: Backend uses snake_case; frontend code uses camelCase but API-facing types use snake_case to match JSON payloads.
- **Error handling**: Backend maps exceptions to HTTP status codes via `HTTPException`. The frontend Axios interceptor normalizes errors to `Error` objects with the backend's `detail` message.
- All relationships between entities (e.g., Agent ↔ Tool) are managed through dedicated association endpoints and junction tables.
