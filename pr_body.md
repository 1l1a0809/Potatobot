## Summary

Complete rewrite of Potatobot from a monolithic 867-line `bot.py` to a production-ready modular architecture.

## Changes

### Architecture
- **Modular structure** — split into `app/` with clear separation: config, database, handlers, services, middleware, utils, web
- **Async DB** — migrated from blocking `psycopg2` to `asyncpg` for true async operations
- **Dependency injection** — services passed to handlers via aiogram's dependency injection

### Configuration & Logging
- **Pydantic Settings** — type-safe config with validation, `.env.example` included
- **Structured logging** — structlog with JSON/console output, proper log levels
- **Custom exceptions** — CooldownError, ValidationError, DatabaseError, UserNotFoundError

### Performance & Reliability
- **TTL caching** — leaderboard caching with `@cached` decorator (30s TTL)
- **Rate limiting** — per-user request limiting (configurable)
- **Health checks** — `/health` (DB connectivity), `/ready` (traffic readiness), `/` (Render keep-alive)
- **Prometheus metrics** — `/metrics` endpoint with dig commands, kg histogram, active users, DB query duration, cache hits/misses

### Middleware
- `LoggingMiddleware` — logs all commands with user context
- `RateLimitMiddleware` — prevents command spam
- `ErrorHandlingMiddleware` — unified error responses

### DevOps
- **Multi-stage Dockerfile** — builder + runtime, non-root user, health checks, OCI labels
- **docker-compose.yml** — bot + PostgreSQL for local development
- **Alembic migrations** — initial schema with indexes
- **GitHub Actions CI** — lint (ruff + mypy), tests with PostgreSQL, Docker build
- **Pre-commit hooks** — ruff (format + lint), mypy, trailing whitespace
- **Makefile** — common tasks (install, test, lint, format, docker, migrate)

### Tests
- Unit tests for DigService (cooldown, caching, history)
- Unit tests for validators
- pytest config with coverage (80% threshold)

### Documentation
- Comprehensive README.md with quick start, config reference, architecture diagram, commands, deployment guide

## Migration Notes

**Breaking changes:**
- Requires Python 3.12+
- Database URL must be PostgreSQL (asyncpg)
- Environment variables changed (see `.env.example`)
- Entry point changed to `python -m app.main`

**Required env vars:**
```env
BOT_TOKEN=...
DATABASE_URL=postgresql://...
```