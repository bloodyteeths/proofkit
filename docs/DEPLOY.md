# Deployment Guide - Single Environment

This document describes the streamlined single-environment deployment process for ProofKit, which eliminates staging in favor of a robust single production pipeline with comprehensive testing.

## Overview

ProofKit now uses a **single release pipeline** that combines:
- Registry and differential validation
- Industry acceptance tests (all 6 industries)
- Live smoke tests against production
- Comprehensive release validation
- Automated deployment to production

**Key Benefits:**
- Simplified deployment process (no staging confusion)
- Faster feedback loops
- Production-validated releases
- Comprehensive testing before deployment

## Architecture

### Single Production Environment
- **Production URL**: `https://proofkit.net`
- **Infrastructure**: Fly.io hosting
- **Database**: Production PostgreSQL
- **Monitoring**: Built-in health checks + live smoke tests

### CI/CD Pipeline
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Registry        │    │ Acceptance Tests │    │ Live Smoke      │
│ Validation      │───▶│ (6 Industries)   │───▶│ Tests           │
│                 │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
                                              ┌─────────────────┐
                                              │ Release         │
                                              │ Validation      │
                                              │                 │
                                              └─────────────────┘
```

## Deployment Process

### Automatic Deployment (Recommended)

1. **Push to main branch**:
   ```bash
   git push origin main
   ```

2. **Pipeline automatically runs**:
   - Registry sanity checks
   - All industry acceptance tests
   - Live smoke tests against current production
   - Release validation with coverage checks
   - Performance regression testing

3. **Deployment happens** if all tests pass

### Manual Deployment

For emergency deployments or testing specific scenarios:

```bash
# Trigger manual workflow
gh workflow run release.yml \
  --ref main \
  --field validation_mode=full
```

### Release Tags

For versioned releases:

```bash
# Create and push release tag
git tag -a v1.2.3 -m "Release v1.2.3: Description"
git push origin v1.2.3
```

This triggers the full pipeline plus:
- GitHub release creation
- Release artifact packaging
- Extended validation reports

## Pipeline Stages

### 1. Registry Validation (5-10 minutes)
- Validates `validation_campaign/registry.yaml`
- Runs differential checks against known examples
- Ensures algorithm consistency

**Failure conditions:**
- Critical registry errors > 0
- Differential tolerance violations > 3 cases

### 2. Acceptance Tests (15-30 minutes)
Matrix testing across all industries:
- Autoclave (pressure + temperature validation)
- Coldchain (temperature monitoring)
- Concrete (cure temperature tracking)  
- HACCP (cooling validation)
- Powder (cure process validation)
- Sterile (sterilization validation)

**Failure conditions:**
- Any critical industry test fails (powder, haccp)
- Matrix test suite failures

### 3. Live Smoke Tests (5-10 minutes)
Tests against **current production**:
- Health endpoint validation
- Industry page accessibility
- API preset availability
- Example compilation
- Performance baselines

**Failure conditions:**
- Any production endpoint fails
- Response times exceed thresholds
- Missing critical functionality

### 4. Release Validation (10-15 minutes)
- Code quality checks (flake8, mypy)
- Test coverage validation (92%+ required)
- Performance regression testing
- Security scanning

**Failure conditions:**
- Coverage below 92%
- Performance regression > thresholds
- Code quality failures

## Monitoring & Health Checks

### Built-in Monitoring
- **Health endpoint**: `https://proofkit.net/health`
- **Response time monitoring**: < 5s for health, < 15s for pages
- **Availability checks**: Every 15 minutes during business hours

### Live Smoke Tests
Run automatically:
- **After every deployment** (production validation)
- **Nightly at 2 AM UTC** (continuous monitoring)
- **On-demand** via GitHub Actions

### Alerts & Notifications

**Pipeline Failures:**
- Automatic GitHub issue creation for nightly failures
- Workflow summaries in GitHub Actions
- Artifact preservation for debugging

**Production Issues:**
- Live smoke test failures trigger investigation
- Health check failures visible in monitoring
- Response time degradation alerts

## Rollback Strategy

### Immediate Rollback
If production issues are detected:

```bash
# Revert to previous known-good commit
git revert <commit-hash>
git push origin main
```

The pipeline will automatically redeploy the reverted version.

### Emergency Hotfix
For critical fixes:

1. Create hotfix branch from main
2. Apply minimal fix
3. Push to trigger pipeline
4. Pipeline validates fix before deployment

```bash
git checkout -b hotfix/critical-fix
# Make minimal changes
git commit -m "fix: critical production issue"
git push origin hotfix/critical-fix
# Create PR to main for immediate deployment
```

## Environment Variables

### Required Secrets (GitHub Actions)
- `FLY_API_TOKEN`: Fly.io deployment token
- `LIVE_QA_EMAIL`: Email for live testing (optional)
- `LIVE_QA_TOKEN`: Authentication token for live tests (optional)

### Production Configuration
All production config is managed through Fly.io:

```bash
# View current configuration
flyctl config show --app proofkit-prod

# Update environment variables
flyctl secrets set VARIABLE_NAME=value --app proofkit-prod
```

## Testing Strategy

### Pre-deployment Testing
1. **Unit tests**: Core algorithm validation
2. **Integration tests**: Component interaction
3. **Acceptance tests**: Industry-specific validation
4. **Live smoke tests**: Production endpoint validation

### Post-deployment Validation
1. **Automatic health checks**: Immediate post-deploy validation
2. **Live smoke tests**: Full functionality validation
3. **Performance monitoring**: Response time tracking

### Manual Testing
For complex features, supplement automated tests with:
1. **Example validation**: Test representative CSV files
2. **UI testing**: Verify form functionality
3. **PDF generation**: Validate output quality

## Troubleshooting

### Pipeline Failures

**Registry Validation Failed:**
- Check `validation_campaign/registry.yaml` syntax
- Review differential tolerance issues
- Verify example files are valid

**Acceptance Tests Failed:**
- Review industry-specific test logs
- Check for algorithm regressions
- Validate test data integrity

**Live Smoke Tests Failed:**
- Verify production environment health
- Check for DNS/connectivity issues
- Review response time thresholds

**Release Validation Failed:**
- Address code quality issues
- Increase test coverage to 92%+
- Fix performance regressions

### Production Issues

**Application Down:**
```bash
# Check Fly.io status
flyctl status --app proofkit-prod

# View logs
flyctl logs --app proofkit-prod

# Restart if needed
flyctl restart --app proofkit-prod
```

**Performance Issues:**
```bash
# Check resource usage
flyctl vm status --app proofkit-prod

# Scale if needed
flyctl scale count 2 --app proofkit-prod
```

**Database Issues:**
```bash
# Check database connection
flyctl postgres connect --app proofkit-db

# View database logs
flyctl logs --app proofkit-db
```

## Development Workflow

### Feature Development
1. Create feature branch from main
2. Implement feature with tests
3. Create PR to main
4. Pipeline runs automatically on PR
5. Merge triggers full deployment pipeline

### Testing Changes
```bash
# Run tests locally
python -m pytest tests/ -v

# Run live smoke tests against production
python -m tests.smoke.test_live_smoke --base-url https://proofkit.net

# Run release validation
python -m cli.release_check --mode development
```

### Code Quality
```bash
# Format code
black .
isort .

# Check quality
flake8 .
mypy .

# Run security checks
bandit -r .
```

## Security Considerations

### Secrets Management
- All secrets stored in GitHub Actions secrets
- Production environment variables via Fly.io secrets
- No secrets in code or configuration files

### Access Control
- Fly.io production access limited to maintainers
- GitHub Actions deployment requires successful tests
- Production database access restricted

### Monitoring
- Security scanning in CI/CD pipeline
- Dependency vulnerability checking
- Regular security updates

## Performance Optimization

### Response Time Targets
- **Health endpoint**: < 5 seconds
- **Home page**: < 15 seconds  
- **Industry pages**: < 10 seconds
- **API endpoints**: < 10 seconds

### Scaling Strategy
- **Horizontal scaling**: Increase Fly.io instance count
- **Vertical scaling**: Upgrade instance resources
- **Caching**: Static asset optimization
- **Database optimization**: Query performance tuning

## Maintenance

### Regular Tasks
- **Weekly**: Review pipeline health and performance
- **Monthly**: Update dependencies and security patches
- **Quarterly**: Review and update deployment process

### Dependency Updates
```bash
# Update Python dependencies
pip-compile requirements.in
pip-compile requirements-dev.in

# Test updated dependencies
python -m pytest tests/ -v
```

### Monitoring Review
- Check nightly pipeline success rates
- Review live smoke test trends
- Monitor production performance metrics
- Update alerting thresholds as needed

## Support

### Documentation
- **Repository**: GitHub repository README
- **API docs**: Generated from code annotations
- **Architecture**: See `/docs` directory

### Getting Help
- **Issues**: Create GitHub issue for bugs/features
- **Discussions**: Use GitHub discussions for questions
- **Emergency**: Contact repository maintainers directly

### Contributing
1. Fork repository
2. Create feature branch
3. Add tests for changes
4. Ensure pipeline passes
5. Create pull request

---

This single-environment approach ensures robust, well-tested deployments while simplifying the development and deployment workflow. The comprehensive testing pipeline provides confidence in production releases without the overhead of maintaining separate staging infrastructure.