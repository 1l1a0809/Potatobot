.PHONY: help install test lint format run docker-build docker-up docker-down migrate-up migrate-down

help:
	@echo "Available commands:"
	@echo "  install        - Install dependencies (uv)"
	@echo "  test           - Run tests with coverage"
	@echo "  lint           - Run ruff + mypy"
	@echo "  format         - Format code with ruff"
	@echo "  run            - Run bot locally"
	@echo "  docker-build   - Build Docker image"
	@echo "  docker-up      - Start with docker-compose"
	@echo "  docker-down    - Stop docker-compose"
	@echo "  migrate-up     - Run alembic migrations"
	@echo "  migrate-down   - Rollback last migration"

install:
	uv pip install -r requirements-dev.txt

test:
	pytest

lint:
	ruff check app tests
	mypy app

format:
	ruff format app tests

run:
	python -m app.main

docker-build:
	docker build -t potatobot:latest .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down -v

migrate-up:
	alembic upgrade head

migrate-down:
	alembic downgrade -1