# Tech Debt: MCP Session Cache — Scaling Beyond a Single Container

**Created:** 2025  
**Component:** `backend/core/mcp_session_cache.py`  
**Status:** Known limitation — acceptable for single-instance deployment

---

## Current Design

The MCP session cache stores live `MCPClient` instances **in-process memory**,
keyed by `(chat_id, mcp_id)`.  This keeps MCP server connections (and any
server-side state, such as database cursors or authenticated sessions) alive
across chat turns within the same conversation.

- **TTL:** 30 minutes of inactivity → automatic eviction.
- **Eviction:** Explicit on chat deletion; periodic sweep; app shutdown.

## Why This Works Today

The backend runs as a **single Uvicorn process** inside one Docker container.
Every request for a given chat hits the same process, so the in-memory cache
always has the relevant session available.

## What Breaks With Horizontal Scaling

If the backend is scaled to **multiple replicas** (e.g., Kubernetes
Deployment with `replicas > 1`, ECS tasks, or multiple containers behind a
load balancer), requests for the same chat may land on different instances.
Each instance holds its own cache, leading to:

1. **Session misses** — a chat turn routed to instance B won't find the
   session that instance A created.  A new MCP connection is opened,
   losing server-side state.
2. **Orphaned sessions** — the session on instance A is never touched
   again and sits idle until the TTL sweeper evicts it, wasting resources.
3. **Inconsistent behaviour** — whether a tool "remembers" prior
   context depends on load-balancer routing luck.

## Mitigation Options

### 1. Sticky Sessions (Quick Fix)

Configure the load balancer to route requests with the same `chat_id` (or
a session cookie) to the same backend instance.

- **Pros:** Zero code changes to the cache.
- **Cons:** Uneven load distribution; if an instance dies, all its cached
  sessions are lost.

### 2. External Session Store (Recommended Long-Term)

Move the session state out of the process and into a shared store that all
instances can access.

| Store | Notes |
|-------|-------|
| **Redis** | Serialize MCP connection metadata (not the socket itself) and lazily reconnect. Works well for stateless transports. For stateful (stdio) transports, you'd need a proxy/sidecar. |
| **MCP Proxy / Gateway** | Run a dedicated sidecar (or shared service) that holds actual MCP connections. Backend instances talk to the proxy via a lightweight protocol. The proxy manages connection pooling and lifecycle. |
| **Shared-nothing with hand-off** | When a request arrives at the wrong instance, forward it internally to the one that owns the session (peer-to-peer routing). Complex but avoids external infrastructure. |

### 3. MCP Server Reconnect Tolerance

If the MCP servers themselves can resume sessions (e.g., via a session
token), the cache becomes a performance optimization rather than a
correctness requirement.  Losing a cached client would simply trigger a
reconnect + session resume.  This depends on the MCP server implementation.

## Recommendation

For the foreseeable roadmap (single-container deployment), the in-memory
cache is sufficient and correct.  If horizontal scaling becomes a
requirement:

1. First try **sticky sessions** — minimal effort, solves 90 % of cases.
2. If sticky sessions are insufficient (frequent instance churn, need for
   HA failover), invest in an **MCP proxy sidecar** that externalises
   connection management.

---

*This note exists to document the known limitation so a future team doesn't
have to rediscover it.*
