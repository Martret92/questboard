# QuestBoard — Evidence Map

This document maps the portfolio claims in the README to inspectable implementation evidence. The goal is to make the backend depth easy to evaluate without relying on feature count or presentation alone.

## 1. Project-scoped authorization

**Claim:** access and mutations are scoped to project membership, with role-sensitive planning and review authority.

**Evidence:**

- `projects/models.py` defines `ProjectMembership` and its roles.
- `projects/services.py` centralizes owner-only membership mutation and preserves the invariant that a project cannot lose its final owner.
- `projects/views.py` scopes project and membership access to the authenticated user's memberships.
- `quests/services.py::_actor_membership` rejects actors outside the project.
- `quests/services.py::_require_planning_authority` restricts planning/review-sensitive operations to `OWNER` and `REVIEWER`.

**Interview angle:** authorization is contextual to both project membership and operation; it is not a single global role check.

## 2. Explicit workflow rather than generic state CRUD

**Claim:** quest state is not an unrestricted mutable field at the API boundary.

**Evidence:**

- `quests/urls.py` exposes a dedicated `/transition/` route.
- `quests/views.py::QuestTransitionView` delegates state changes to `transition_quest`.
- `quests/services.py::transition_quest` enumerates legal transitions and rejects every other source/target pair.
- `DONE` is explicitly terminal.
- `QuestSerializer` exposes state as read-only for ordinary quest mutation.

**Interview angle:** state transitions are modeled as domain operations so preconditions, permissions, locking, and audit recording stay explicit.

## 3. Dependency-aware workflow

**Claim:** dependencies affect both graph integrity and workflow eligibility.

**Evidence:**

- `QuestDependency` models prerequisite edges.
- `quests/services.py::add_dependency` rejects cross-project prerequisites, duplicates, self-dependencies, and cycles.
- `_would_create_cycle` performs graph traversal before an edge is inserted.
- `transition_quest` blocks `BACKLOG -> READY` while any prerequisite is not `DONE`.
- dependency creation/removal is permitted only while the dependent quest is `BACKLOG`.

**Interview angle:** dependencies are business behavior, not decorative relations; they change whether work may progress.

## 4. PostgreSQL constraints as a backstop

**Claim:** local invariants are reinforced at database level where practical.

**Evidence:**

`quests/models.py::QuestDependency.Meta.constraints` defines:

- a unique `(dependent, prerequisite)` edge constraint;
- a check constraint preventing self-dependency.

`Quest.assignee` uses `on_delete=PROTECT`, preventing membership deletion from silently unassigning quests and bypassing assignment rules.

**Interview angle:** service validation produces useful domain errors, while PostgreSQL constraints protect integrity if an invalid local write reaches the database.

## 5. Transaction boundaries and concurrency reasoning

**Claim:** graph-sensitive and membership-sensitive mutations have deliberate transaction and locking semantics.

**Evidence:**

- domain mutations use `@transaction.atomic`.
- `_locked_project` uses `select_for_update()` to serialize operations whose invariant spans multiple rows.
- graph mutation takes a project lock before cycle validation and edge mutation.
- owner-preservation membership mutations use the same project-level serialization strategy.
- individual quest mutation uses row-level locks where appropriate.

A PostgreSQL-specific implementation issue was encountered during workflow work: applying `FOR UPDATE` through a nullable assignee join produced an invalid locking shape. `transition_quest` therefore locks only the Quest row and resolves the nullable relation separately. The code includes a comment documenting the reason.

**Interview angle:** locking was driven by concrete invariants and PostgreSQL behavior rather than adding `select_for_update()` indiscriminately.

## 6. Execution and review separation

**Claim:** execution and approval are separate responsibilities.

**Evidence in `transition_quest`:**

- a quest must have an assignee before `READY -> IN_PROGRESS`;
- only that assignee can start it;
- only that assignee can submit `IN_PROGRESS -> REVIEW`;
- owners/reviewers control review return or approval;
- the assignee cannot approve their own quest.

**Interview angle:** this creates a small but meaningful contextual permission model tied to workflow state and resource assignment.

## 7. Assignment invariants

**Claim:** assignment has lifecycle semantics rather than being an arbitrary nullable FK.

**Evidence:**

- assignee must be a `ProjectMembership` in the same project;
- changing assignee requires planning authority;
- assignee is mutable only in `BACKLOG` or `READY`;
- assignment is therefore frozen from `IN_PROGRESS` onward;
- `PROTECT` prevents membership deletion from indirectly mutating a frozen assignment.

## 8. Auditable state changes

**Claim:** significant mutations create inspectable audit events.

**Evidence:**

`QuestEvent` records:

- quest creation;
- assignee changes;
- dependency additions/removals;
- state changes.

Each event stores project, actor, timestamp, event type, structured data, and `quest_id_snapshot`. The live `quest` FK uses `SET_NULL`, so legally deleting a quest does not erase the historical identifier needed to query its audit trail.

The API exposes `/events/` separately from the quest resource.

**Interview angle:** audit history is append-style domain evidence, not inferred later from current row state.

## 9. Safe deletion semantics

**Claim:** deletion respects domain relationships and history.

**Evidence:**

- quests can be deleted only while `BACKLOG`;
- a quest cannot be deleted while another quest depends on it;
- membership deletion is blocked while assigned quests reference it;
- audit events survive legal quest deletion through `SET_NULL` plus `quest_id_snapshot`.

## 10. Automated tests

**Claim:** tests target domain behavior, not only happy-path CRUD.

**Evidence:**

- `projects/tests/` covers project and membership behavior.
- `quests/tests/test_quest_core.py` covers quest core/API behavior and invariants.
- `quests/tests/test_workflow_dependencies.py` covers dependency-aware workflow, cycle prevention, permissions, transitions, and audit behavior.
- `config/tests.py` covers deployment-facing health and OpenAPI endpoints.

CI runs the suite against PostgreSQL 17.

**Interview angle:** high-value tests sit around invariants and state transitions where regressions would change business meaning.

## 11. CI delivery baseline

**Claim:** the repository has an automated delivery-quality gate.

**Evidence:** `.github/workflows/ci.yml` runs:

1. PostgreSQL 17 service;
2. Python 3.12 setup;
3. project/dev dependency installation;
4. Ruff lint;
5. formatting checks for changed Python files;
6. migration drift check;
7. Django system checks;
8. migrations;
9. OpenAPI schema validation;
10. Django tests;
11. Docker image build.

**Interview angle:** schema, database, tests, and container construction are validated together on pull requests.

## 12. Reproducible containerized runtime

**Claim:** local and deployed runtime paths are aligned.

**Evidence:**

- `Dockerfile` packages the Django application on Python 3.12 slim and starts Gunicorn.
- startup applies migrations then binds Gunicorn to `${PORT:-8000}`.
- `docker-compose.yml` provides local PostgreSQL and application services.
- `.env.example` documents local configuration without production secrets.
- CI builds the Docker image.
- Render deploys from the same Dockerfile.

## 13. Real deployment evidence

**Public endpoints:**

- Swagger UI: https://questboard-4tnl.onrender.com/api/docs/
- schema: https://questboard-4tnl.onrender.com/api/schema/
- health: https://questboard-4tnl.onrender.com/health/

The Render service uses managed PostgreSQL 17. `/health/` executes a database query, so `{"status": "ok"}` demonstrates application-to-database connectivity rather than only process liveness.

## 14. Deliberate compromises

These are conscious MVP decisions, not claims of production completeness:

- Session and Basic authentication are sufficient for the portfolio API; token/OAuth flows are out of current scope.
- Migrations run in the container startup command. This is acceptable for the current single-service deployment; multi-replica production should use a dedicated release/pre-deploy step.
- Render Free infrastructure is demonstration-grade and may sleep or expire according to provider limits.
- No background queue, cache, microservice split, or configurable RBAC/workflow layer has been introduced because none is required to demonstrate the chosen backend evidence.

## 15. Generic Portfolio Guardrail

QuestBoard should remain differentiated by:

- dependency-aware progression;
- contextual permissions;
- explicit business invariants;
- concurrency-aware graph mutation;
- auditable state transitions.

Adding generic task-management surface area without strengthening those properties would reduce rather than improve the portfolio signal.
