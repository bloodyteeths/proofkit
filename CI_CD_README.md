# CI/CD Pipeline and Development Setup

This document describes the CI/CD pipeline and development tools configured for ProofKit.

## Overview

The project includes comprehensive linting, type checking, testing, and CI/CD configurations that enforce code quality and ensure reliable deployments.

## CI/CD Pipeline (GitHub Actions)

### Workflow: `.github/workflows/ci.yml`

The CI pipeline runs on:
- Push to `main` and `develop` branches
- Pull requests to `main` and `develop` branches

#### Pipeline Steps

1. **Environment Setup**
   - Python 3.11 installation
   - Dependency caching for faster builds

2. **Code Quality Checks**
   - Format checking with Black and isort
   - Linting with flake8
   - Type checking with mypy

3. **Testing**
   - Run pytest with coverage reporting
   - Generate XML and HTML coverage reports
   - Upload coverage to Codecov

4. **Docker Build** (main branch only)
   - Build Docker image
   - Use layer caching for efficiency

5. **Artifact Storage**
   - Upload test results and coverage reports
   - Available for debugging failed builds

## Code Quality Tools

### Flake8 (`.flake8`)
- Line length: 88 characters (Black compatible)
- Excludes build/cache directories
- Ignores Black-conflicting rules (E203, W503)
- Maximum complexity: 10
- Per-file ignores for common patterns

### MyPy (`mypy.ini`)
- Strict typing for project code
- Ignores missing imports for third-party libraries
- Separate configurations for different modules
- Relaxed rules for test files

### Black & isort (`pyproject.toml`)
- Line length: 88 characters
- Python 3.11 target
- Black-compatible isort profile
- Excludes storage and build directories

### Pytest (`pytest.ini`)
- Test discovery configuration
- Coverage reporting setup
- Custom markers for test categorization
- Warning filters

## Local Development

### Setup
```bash
# Install dependencies
make install

# Setup pre-commit hooks
make setup-hooks
```

### Code Quality Commands
```bash
# Format code
make format

# Check formatting
make format-check

# Lint code
make lint

# Type check
make typecheck

# Run tests
make test

# Run tests with coverage
make test-cov

# Run all checks (CI-like)
make check
```

### Pre-commit Hooks (`.pre-commit-config.yaml`)

Automatically runs on each commit:
- Trailing whitespace removal
- End-of-file fixing
- YAML validation
- Large file detection
- Merge conflict detection
- Debug statement detection
- flake8 linting
- mypy type checking
- Black formatting
- isort import sorting

## Configuration Files

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | GitHub Actions CI pipeline |
| `.flake8` | Flake8 linting configuration |
| `mypy.ini` | MyPy type checking configuration |
| `pytest.ini` | Pytest testing configuration |
| `pyproject.toml` | Black, isort, and coverage configuration |
| `.pre-commit-config.yaml` | Pre-commit hooks configuration |
| `.gitignore` | Git ignore patterns |

## Coverage Reporting

Coverage reports are generated in multiple formats:
- Terminal output with missing lines
- HTML report in `htmlcov/` directory
- XML report for CI integration
- Uploaded to Codecov in CI

## Docker Integration

The CI pipeline builds Docker images on main branch pushes:
- Uses multi-stage caching for efficiency
- Tags images with commit SHA
- Stores build cache for subsequent runs

## Troubleshooting

### Common Issues

1. **Format Check Failures**
   ```bash
   make format  # Auto-fix formatting issues
   ```

2. **Lint Failures**
   - Check `.flake8` configuration
   - Review per-file ignores
   - Consider complexity reduction

3. **Type Check Failures**
   - Add type annotations
   - Check `mypy.ini` configuration
   - Add `# type: ignore` for unavoidable issues

4. **Test Failures**
   - Run locally: `make test-cov`
   - Check test data in `tests/data/`
   - Review test artifacts in CI

5. **Docker Build Failures**
   - Ensure Dockerfile is valid
   - Check dependency installation
   - Review build context excludes

## Best Practices

1. **Before Committing**
   ```bash
   make check  # Run all quality checks
   ```

2. **Pre-commit Setup**
   ```bash
   make setup-hooks  # Install git hooks
   ```

3. **Coverage Goals**
   - Maintain >80% test coverage
   - Add tests for new features
   - Review coverage reports

4. **Code Quality**
   - Keep functions under complexity limit (10)
   - Add type hints to new code
   - Follow Black formatting

## Environment Variables

The CI pipeline uses the following secrets/variables:
- `CODECOV_TOKEN` (optional): For coverage reporting
- Docker registry credentials (if pushing images)

## Monitoring

- CI build status in GitHub
- Coverage reports in Codecov
- Test artifacts for debugging
- Docker image build logs