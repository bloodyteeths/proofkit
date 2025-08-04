.PHONY: install dev test lint typecheck clean build run

# Install dependencies
install:
	pip install -r requirements.txt

# Run development server
dev:
	uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	pytest tests/ -v

# Run tests with coverage
test-cov:
	pytest --cov=. --cov-report=xml --cov-report=html --cov-report=term-missing

# Lint code
lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --statistics

# Type check
typecheck:
	mypy .

# Format code
format:
	black .
	isort .

# Check formatting
format-check:
	black --check .
	isort --check-only --diff .

# Clean temporary files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/
	rm -rf storage/*

# Build Docker image
build:
	docker build -t proofkit .

# Run Docker container
run:
	docker run -p 8000:8000 -v $(PWD)/storage:/app/storage proofkit

# Run all checks (CI-like)
check: lint typecheck test-cov

# Run all checks (fast)
check-fast: lint typecheck test

# Setup pre-commit hooks
setup-hooks:
	pre-commit install