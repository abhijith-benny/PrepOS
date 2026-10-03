# PrepOS

PrepOS is an AI-driven placement preparation platform built as a modular monolith with a shared learner model and four module stubs in Phase 1.

## Stack

- Backend: Python 3.13, FastAPI, Pydantic v2, supabase-py, pytest, ruff
- Frontend: React + Vite + Zustand + Supabase JS client
- Database/Auth/Storage: Supabase Postgres + SQL migrations

## Local setup

1. Create a Python virtual environment and install backend dependencies:

   ```bash
   cd prepos/services/api
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Create a frontend app:

   ```bash
   cd prepos/apps/web
   npm install
   ```

3. Copy environment files:

   ```bash
   cp .env.example .env
   cp services/api/.env.example services/api/.env
   ```

4. Start the API:

   ```bash
   cd prepos/services/api
   uvicorn app.main:app --reload
   ```

5. Start the web app:

   ```bash
   cd prepos/apps/web
   npm run dev
   ```

6. Run tests:

   ```bash
   cd prepos/services/api
   pytest
   ```

## Supabase Phase 1 persistence

1. Create or open the Supabase project that the backend will use.
2. In the Supabase Dashboard, open **SQL Editor**, create a new query, paste the complete contents of `supabase/migrations/001_init_schema.sql`, and run it.
3. Create another SQL Editor query, paste the complete contents of `supabase/seed.sql`, and run it after the migration succeeds.
4. In **Project Settings > API**, copy the project URL and the server-only `service_role` key into `services/api/.env`:

   ```dotenv
   SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVER_ONLY_SERVICE_ROLE_KEY
   JWT_SECRET=YOUR_PROJECT_JWT_SECRET
   JWT_AUDIENCE=authenticated
   ```

   Use the project's JWT secret, or set `JWT_JWKS_URL` to the project's JWKS endpoint instead. Never put `SUPABASE_SERVICE_ROLE_KEY` in `apps/web`, `VITE_*` variables, browser code, or committed files.

5. Start the API with the same environment loaded. The API selects Supabase repositories only when both `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set; otherwise tests use in-memory repositories.

To run the real persistence test, also set `SUPABASE_TEST_JWT` to a JWT issued to a test user. Optionally set `SUPABASE_TEST_USER_ID` to that user's UUID, then run:

```bash
cd services/api
pytest -m integration
```

## Phase 1 focus

- shared learner model and event bus contracts
- module stubs with ping routes only
- auth-required API protection via Supabase JWT verification
- onboarding and dashboard shell in the React app

## Notes

- Do not commit secrets.
- Environment variables are loaded from `.env` files.
- Module logic is intentionally stubbed for Phase 1.
