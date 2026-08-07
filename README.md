# QuestBoard

Backend-first collaborative workflow API built with Django, Django REST Framework, and PostgreSQL.

QuestBoard is intentionally not a generic task manager. Its backend centers on dependency-aware workflows, contextual permissions, business invariants, transactional graph mutation, and auditable state transitions.

## Live API

- Swagger UI: https://questboard-4tnl.onrender.com/api/docs/
- OpenAPI schema: https://questboard-4tnl.onrender.com/api/schema/
- Database-backed health check: https://questboard-4tnl.onrender.com/health/

The Render deployment runs the same Docker image used locally, connects to managed PostgreSQL, applies migrations at startup, and serves Django through Gunicorn.

## Backend evidence at a glance

- Project-scoped authorization with `OWNER`, `REVIEWER`, and `CONTRIBUTOR` memberships.
- Explicit quest workflow: `BACKLOG -> READY -> IN_PROGRESS -> REVIEW -> DONE`, with controlled review return to `IN_PROGRESS`.
- State changes go through a dedicated transition operation instead of arbitrary state PATCHes.
- Dependency graph mutation is restricted to planning states, rejects self-dependencies and duplicate edges, and prevents cycles.
- `BACKLOG -> READY` is blocked until all prerequisite quests are `DONE`.
- Only the assignee can start and submit a quest; reviewers/owners control review decisions; self-approval is rejected.
- Assignment becomes frozen from `IN_PROGRESS` onward.
- Project-level row locks serialize graph-sensitive operations and owner-preservation membership changes.
- Domain mutations run in explicit transactions and use row-level locking where concurrent writes matter.
- Audit events persist key state, assignment, and dependency changes, including a quest ID snapshot after legal quest deletion.
- PostgreSQL constraints and FK deletion semantics backstop local invariants.
- CI validates linting, formatting, migration drift, Django checks, migrations, OpenAPI, the automated test suite, and Docker image construction.

See [`docs/evidence-map.md`](docs/evidence-map.md) for the code-level evidence map and interview-oriented rationale.

## Stack

- Python 3.12+
- Django 5.2 LTS
- Django REST Framework 3.17
- PostgreSQL 17
- Psycopg 3
- Gunicorn
- Docker / Docker Compose
- OpenAPI via drf-spectacular
- GitHub Actions CI
- Render Web Service + managed PostgreSQL

## Architecture

QuestBoard is a Django modular monolith with two main domain apps:

- `projects`: project membership and the project authorization boundary;
- `quests`: quests, dependency graph, workflow transitions, and audit events.

The HTTP layer delegates meaningful mutations to explicit application/domain services. The intent is to keep workflow rules, authorization decisions, transactions, and locking visible and testable rather than hiding them behind unrestricted model updates.

### Core invariants

| Invariant | Enforcement |
| --- | --- |
| A project always has at least one owner | transactional membership service + project lock |
| An assigned membership cannot be deleted while referenced by a quest | `Quest.assignee` uses `PROTECT` |
| Quest metadata is editable only in `BACKLOG` | quest mutation service |
| Assignee changes are limited to `BACKLOG` / `READY` | quest mutation service |
| Dependencies are mutable only while the dependent quest is `BACKLOG` | dependency services |
| Dependency edges cannot point to self or duplicate an existing edge | PostgreSQL constraints + service validation |
| Dependency graph must remain acyclic | graph traversal before insert, serialized by project lock |
| A quest cannot become `READY` until all prerequisites are `DONE` | transition service |
| Only the assignee executes `READY -> IN_PROGRESS -> REVIEW` | transition service |
| Review approval cannot be performed by the assignee | transition service |
| `DONE` is terminal | transition service |
| Quest deletion is limited to legal `BACKLOG` cases and cannot break dependents | quest deletion service |

## API contract

API endpoints use Django session authentication or HTTP Basic authentication. Protected operations still enforce project-scoped membership and domain permissions.

Important API surfaces include:

- `/api/projects/`
- `/api/projects/{project_pk}/memberships/`
- `/api/projects/{project_pk}/quests/`
- `/api/projects/{project_pk}/quests/{quest_pk}/dependencies/`
- `/api/projects/{project_pk}/quests/{quest_pk}/transition/`
- `/api/projects/{project_pk}/quests/{quest_pk}/events/`

The OpenAPI schema is generated with `drf-spectacular` and validated in CI so contract drift is caught alongside code and database checks.

## Testing and CI

The automated suite covers API authorization, project membership invariants, quest mutation rules, dependency behavior, workflow transitions, audit events, and delivery endpoints.

The GitHub Actions pipeline runs against PostgreSQL 17 and checks:

1. dependency installation;
2. Ruff linting;
3. Ruff formatting for changed Python files;
4. migration drift with `makemigrations --check`;
5. Django system checks;
6. migrations against PostgreSQL;
7. OpenAPI schema validation;
8. the Django test suite;
9. Docker image build.

This makes PostgreSQL-specific behavior part of CI rather than relying only on SQLite or local developer state.

## Docker quick start

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Replace `DJANGO_SECRET_KEY` before using the configuration outside local development.
3. Build and start the application and PostgreSQL:

   ```bash
   docker compose up --build
   ```

The app waits for PostgreSQL to become healthy, applies migrations, and starts Gunicorn on `http://localhost:8000`.

Verify:

```bash
curl http://localhost:8000/health/
```

Expected response:

```json
{"status": "ok"}
```

Stop the stack with:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the local PostgreSQL volume.

## Local Python setup

1. Create and activate a Python 3.12+ virtual environment.
2. Install the project and development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

3. Copy the environment template if needed:

   ```bash
   cp .env.example .env
   ```

4. Export the variables from `.env` in your shell or development environment.
5. Start PostgreSQL only:

   ```bash
   docker compose up -d db
   ```

6. Apply migrations and run tests:

   ```bash
   python manage.py migrate
   python manage.py test config projects quests
   ```

7. Start the development server:

   ```bash
   python manage.py runserver
   ```

## Deployment notes

Production-style configuration is environment-driven:

- `DATABASE_URL` for managed PostgreSQL;
- `DJANGO_SECRET_KEY` for the production secret;
- `DJANGO_DEBUG=false`;
- `DJANGO_ALLOWED_HOSTS` for the public service hostname;
- Render-provided `PORT` for Gunicorn binding.

The `/health/` endpoint executes `SELECT 1`, so a healthy deployment demonstrates both application liveness and database connectivity.

For the MVP single-service deployment, migrations run before Gunicorn in the container startup command. A multi-replica production deployment should move migrations to a dedicated release/pre-deploy step.

## Deliberate scope boundaries

The MVP does **not** add comments, notifications, tags, subtasks, gamification, configurable RBAC/workflows, Celery, Redis, microservices, analytics, or additional workflow states.

Those omissions are deliberate: the project prioritizes a small set of deep backend behaviors that can be inspected, tested, and defended in an interview over feature count.
