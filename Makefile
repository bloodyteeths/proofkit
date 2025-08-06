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

# Release validation targets
release-check-dev:
	python -m cli.release_check --mode development --verbose

release-check-prod:
	python -m cli.release_check --mode production --output-json release-report.json --output-html release-report.html --verbose

release-check-golden:
	python -m cli.release_check --golden-regen

# Pre-deployment validation
pre-deploy:
	./scripts/pre_deploy.sh

pre-deploy-fast:
	./scripts/pre_deploy.sh --fast

pre-deploy-no-docker:
	./scripts/pre_deploy.sh --skip-docker

# Complete release pipeline
release-validate: clean lint typecheck test-cov release-check-prod
	@echo "✅ Complete release validation passed"

# Development validation (fast)
dev-validate: lint typecheck test release-check-dev
	@echo "✅ Development validation passed"

# Performance benchmarking
benchmark:
	python -c "
	import time
	import sys
	from pathlib import Path
	sys.path.insert(0, '.')
	from core.normalize import normalize_csv_data
	from core.decide import make_decision
	import json
	
	# Benchmark with example data
	csv_path = 'examples/ok_run.csv'
	spec_path = 'examples/spec_example.json'
	
	if Path(csv_path).exists() and Path(spec_path).exists():
	    with open(spec_path, 'r') as f:
	        spec = json.load(f)
	    
	    # Multiple runs for better timing
	    times = []
	    for i in range(5):
	        start = time.time()
	        normalized_df, messages = normalize_csv_data(csv_path, spec)
	        decision = make_decision(normalized_df, spec)
	        times.append(time.time() - start)
	    
	    avg_time = sum(times) / len(times)
	    print(f'Average processing time: {avg_time:.3f}s')
	    print(f'Min time: {min(times):.3f}s')
	    print(f'Max time: {max(times):.3f}s')
	else:
	    print('Example files not found')
	"

# Security checks
security-check:
	@echo "Running security checks..."
	@if command -v safety >/dev/null 2>&1; then \
		safety check --short-report; \
	else \
		echo "⚠️  safety not installed - run: pip install safety"; \
	fi
	@if command -v bandit >/dev/null 2>&1; then \
		bandit -r . -ll; \
	else \
		echo "⚠️  bandit not installed - run: pip install bandit"; \
	fi

# Coverage reporting with detailed breakdown
coverage-report:
	pytest --cov=. --cov-report=html --cov-report=term-missing --cov-report=xml
	@echo "📊 Coverage report generated in htmlcov/"

# Example validation
validate-examples:
	python -c "
	import sys
	from pathlib import Path
	sys.path.insert(0, '.')
	
	examples_dir = Path('examples')
	csv_files = list(examples_dir.glob('*.csv'))
	spec_files = list(examples_dir.glob('*.json'))
	
	print(f'Found {len(csv_files)} CSV files and {len(spec_files)} spec files')
	
	# Test key pairs
	test_pairs = [
	    ('powder_coat_cure_successful_180c_10min_pass.csv', 'powder_coat_cure_spec_standard_180c_10min.json'),
	    ('ok_run.csv', 'spec_example.json')
	]
	
	from core.normalize import normalize_csv_data
	from core.decide import make_decision
	import json
	
	passed = 0
	failed = 0
	
	for csv_name, spec_name in test_pairs:
	    csv_path = examples_dir / csv_name
	    spec_path = examples_dir / spec_name
	    
	    if csv_path.exists() and spec_path.exists():
	        try:
	            with open(spec_path, 'r') as f:
	                spec = json.load(f)
	            
	            normalized_df, messages = normalize_csv_data(str(csv_path), spec)
	            decision = make_decision(normalized_df, spec)
	            
	            result = decision.get('decision', 'unknown')
	            print(f'✅ {csv_name} + {spec_name} → {result}')
	            passed += 1
	        except Exception as e:
	            print(f'❌ {csv_name} + {spec_name} → ERROR: {e}')
	            failed += 1
	    else:
	        print(f'⚠️  {csv_name} + {spec_name} → FILES NOT FOUND')
	        failed += 1
	
	print(f'\\nExample validation: {passed} passed, {failed} failed')
	if failed > 0:
	    sys.exit(1)
	"

# Help target
help:
	@echo "ProofKit Makefile Targets:"
	@echo ""
	@echo "Development:"
	@echo "  install         Install dependencies"
	@echo "  dev             Run development server"
	@echo "  dev-validate    Fast development validation"
	@echo ""
	@echo "Testing:"
	@echo "  test            Run tests"
	@echo "  test-cov        Run tests with coverage"
	@echo "  coverage-report Detailed coverage report"
	@echo "  validate-examples Test example CSV/spec pairs"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint            Lint code with flake8"
	@echo "  typecheck       Type check with mypy"
	@echo "  format          Format code with black/isort"
	@echo "  format-check    Check code formatting"
	@echo "  security-check  Run security analysis"
	@echo ""
	@echo "Release Validation:"
	@echo "  release-check-dev    Development mode validation"
	@echo "  release-check-prod   Production mode validation"
	@echo "  release-check-golden Regenerate golden files"
	@echo "  release-validate     Complete release validation"
	@echo ""
	@echo "Deployment:"
	@echo "  pre-deploy      Full pre-deployment validation"
	@echo "  pre-deploy-fast Fast pre-deployment check"
	@echo "  pre-deploy-no-docker Skip Docker validation"
	@echo ""
	@echo "Performance:"
	@echo "  benchmark       Run performance benchmarks"
	@echo ""
	@echo "Docker:"
	@echo "  build           Build Docker image"
	@echo "  run             Run Docker container"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean           Clean temporary files"
	@echo "  setup-hooks     Setup pre-commit hooks"