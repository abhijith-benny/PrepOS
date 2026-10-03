# PrepOS Architecture

## Layer diagram

```text
+------------------------------------------------------+
| React + Vite + Zustand frontend                     |
| - Auth UI / onboarding / protected routes           |
| - Dashboard pages for skill vector                  |
+--------------------------+---------------------------+
                           |
                           v
+------------------------------------------------------+
| FastAPI modular monolith                             |
| - app.main: app factory + router registration        |
| - app.core: config, security, deps                   |
| - app.shared: learner model + event bus + schemas    |
| - app.modules.*: stubbed module packages             |
+--------------------------+---------------------------+
                           |
                           v
+------------------------------------------------------+
| Supabase                                              |
| - Postgres tables and RLS                            |
| - Auth (JWT)                                         |
| - Storage                                            |
+------------------------------------------------------+
```

## Module rules

- The app is a modular monolith. Domain modules are isolated under `app.modules`.
- Modules may import only from `app.shared` and `app.core`.
- Modules must not import from each other.
- Shared contracts live in `app.shared` and are the only reusable interfaces across modules.
- Business logic is intentionally deferred beyond Phase 1; each module exposes a stub ping route.

## Shared learner model

The learner model maintains a per-topic skill state using a simple placeholder update strategy.
This is intentionally minimal for Phase 1 and is marked as TODO for M1 refinement.

## Security

- All routes except `/health` require a valid Supabase JWT.
- The JWT is verified in `app.core.security` and attached to request state.
- Database access is isolated by row-level security policies.
