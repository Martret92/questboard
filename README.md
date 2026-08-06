# QuestBoard

Backend-first collaborative workflow API built with Django, Django REST Framework, and PostgreSQL.

QuestBoard focuses on dependency-aware workflows, project-level authorization, and auditable state transitions rather than generic task-management CRUD.

## Stack

- Python 3.12+
- Django 5.2 LTS
- Django REST Framework 3.17
- PostgreSQL
- Psycopg 3

## Local setup

1. Create and activate a Python 3.12+ virtual environment.
2. Install the project dependencies:

   ```bash
   pip install -e .
   ```

3. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

4. Export the variables from `.env` in your shell or development environment.
5. Start PostgreSQL:

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

Business rules and API endpoints are intentionally added in later milestones. The foundation does not encode workflow semantics through generic model updates.
