"""Phase 2 health / tracking domain (spec 2026-07-22-health-profile-checkins-trends.md).

Task 1 scope: ORM model, Pydantic schemas and pure readiness/risk primitives
only. No router, service, trends or audit modules yet (those belong to later
Phase 2 tasks). Importing this package registers ``health_profiles`` on
``Base.metadata`` so SQLite ``create_all`` test schema and the Alembic
migration stay consistent.
"""
