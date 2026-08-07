# QuestBoard

Backend-first collaborative workflow API built with Django, Django REST Framework, and PostgreSQL.

QuestBoard focuses on dependency-aware workflows, project-level authorization, and auditable state transitions rather than generic task-management CRUD.

## Stack

- Python 3.12+
- Django 5.2 LTS
- Django REST Framework 3.17
- PostgreSQL 17
- Psycopg 3
- Gunicorn
- Docker / Docker Compose

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

Stop the stack with:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the local PostgreSQL volume.

## Local Python setup

1. Create and activate a Python 3.12+ virtual environment.
2. Install the project dependencies:

   ```bash
   pip install -e .
   ```

3. Copy the environment template if you have not already:

   ```bash
   cp .env.example .env
   ```

4. Export the variables from `.env` in your shell or development environment.
5. Start PostgreSQL only:

   ```bash
   docker compose up -d db
   ```

6. Apply migrations:

   ```bash
   python manage.py migrate
   ```

7. Run the development server:

   ```bash
   python manage.py runserver
   ```

## Architecture baseline

QuestBoard is a Django modular monolith. Domain code is split primarily between:

- `projects`: project membership and authorization boundary;
- `quests`: quests, workflow, dependencies, and audit behavior.

Workflow transitions, dependency graph mutations, and contextual authorization are implemented explicitly rather than through unrestricted generic model updates.
