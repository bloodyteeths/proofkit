#!/bin/bash

# ProofKit Pre-Deployment Validation Script
# Comprehensive validation before production deployment
#
# Usage:
#   ./scripts/pre_deploy.sh [--fast] [--skip-docker] [--help]
#
# Options:
#   --fast        Run fast validation only (skip slow tests)
#   --skip-docker Skip Docker image validation
#   --help        Show this help message
#
# Exit codes:
#   0 = All validations passed
#   1 = Validation failures
#   2 = Script errors or missing dependencies

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="${PROJECT_ROOT}/pre_deploy_${TIMESTAMP}.log"

# Default options
FAST_MODE=false
SKIP_DOCKER=false
PYTHON_CMD="python"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*" | tee -a "${LOG_FILE}"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "${LOG_FILE}"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "${LOG_FILE}"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*" | tee -a "${LOG_FILE}"
}

# Error handler
error_exit() {
    log_error "Pre-deployment validation failed at: $1"
    log_error "Check log file: ${LOG_FILE}"
    exit 1
}

# Trap errors
trap 'error_exit "${BASH_COMMAND}"' ERR

# Help function
show_help() {
    cat << EOF
ProofKit Pre-Deployment Validation Script

Usage: $0 [OPTIONS]

This script performs comprehensive pre-deployment validation including:
- Environment and dependency checks
- Code quality validation
- Full test suite with coverage
- Example validation
- Performance benchmarks
- Docker image validation (optional)
- Security checks

OPTIONS:
    --fast        Run fast validation only (skip slow tests and Docker)
    --skip-docker Skip Docker image validation
    --help        Show this help message

ENVIRONMENT VARIABLES:
    PYTHON_CMD    Python command to use (default: python)
    
EXIT CODES:
    0   All validations passed
    1   Validation failures detected
    2   Script errors or missing dependencies

EXAMPLES:
    $0                    # Full validation
    $0 --fast            # Fast validation for development
    $0 --skip-docker     # Skip Docker validation
    
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --fast)
                FAST_MODE=true
                log_info "Fast mode enabled"
                shift
                ;;
            --skip-docker)
                SKIP_DOCKER=true
                log_info "Docker validation will be skipped"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 2
                ;;
        esac
    done
}

# Check system requirements
check_system_requirements() {
    log_info "Checking system requirements..."
    
    # Check Python
    if ! command -v "${PYTHON_CMD}" &> /dev/null; then
        log_error "Python not found. Please install Python 3.9+ or set PYTHON_CMD environment variable."
        exit 2
    fi
    
    # Check Python version
    PYTHON_VERSION=$("${PYTHON_CMD}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    log_info "Python version: ${PYTHON_VERSION}"
    
    # Check if version is 3.9+
    if "${PYTHON_CMD}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"; then
        log_success "Python version check passed"
    else
        log_error "Python 3.9+ required, found ${PYTHON_VERSION}"
        exit 2
    fi
    
    # Check pip
    if ! "${PYTHON_CMD}" -m pip --version &> /dev/null; then
        log_error "pip not available"
        exit 2
    fi
    
    # Check git (for version detection)
    if ! command -v git &> /dev/null; then
        log_warn "git not found - version detection may not work"
    fi
    
    # Check Docker (if not skipping)
    if [[ "${SKIP_DOCKER}" == "false" ]] && ! command -v docker &> /dev/null; then
        log_warn "Docker not found - Docker validation will be skipped"
        SKIP_DOCKER=true
    fi
    
    log_success "System requirements check completed"
}

# Check project structure
check_project_structure() {
    log_info "Checking project structure..."
    
    # Required files and directories
    local required_paths=(
        "requirements.txt"
        "requirements-dev.txt"
        "core/"
        "tests/" 
        "examples/"
        "cli/release_check.py"
        "app.py"
    )
    
    local missing_paths=()
    
    for path in "${required_paths[@]}"; do
        if [[ ! -e "${PROJECT_ROOT}/${path}" ]]; then
            missing_paths+=("${path}")
        fi
    done
    
    if [[ ${#missing_paths[@]} -gt 0 ]]; then
        log_error "Missing required project files/directories:"
        for path in "${missing_paths[@]}"; do
            log_error "  - ${path}"
        done
        exit 2
    fi
    
    log_success "Project structure check completed"
}

# Install and check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    cd "${PROJECT_ROOT}"
    
    # Install requirements
    log_info "Installing dependencies..."
    "${PYTHON_CMD}" -m pip install --upgrade pip > "${LOG_FILE}.pip" 2>&1
    "${PYTHON_CMD}" -m pip install -r requirements.txt >> "${LOG_FILE}.pip" 2>&1
    "${PYTHON_CMD}" -m pip install -r requirements-dev.txt >> "${LOG_FILE}.pip" 2>&1
    
    # Check pip dependencies
    log_info "Checking pip dependencies..."
    if "${PYTHON_CMD}" -m pip check > "${LOG_FILE}.pip_check" 2>&1; then
        log_success "Pip dependency check passed"
    else
        log_error "Pip dependency check failed:"
        cat "${LOG_FILE}.pip_check" | head -20
        exit 1
    fi
    
    # Test critical imports
    log_info "Testing critical imports..."
    local critical_modules=(
        "fastapi"
        "pydantic"
        "pandas"
        "numpy"
        "matplotlib"
        "reportlab"
        "typer"
        "pytest"
    )
    
    for module in "${critical_modules[@]}"; do
        if "${PYTHON_CMD}" -c "import ${module}" 2>/dev/null; then
            log_info "  ✓ ${module}"
        else
            log_error "  ✗ ${module} - import failed"
            exit 1
        fi
    done
    
    log_success "Dependencies check completed"
}

# Run release validation using the CLI tool
run_release_validation() {
    local mode="production"
    if [[ "${FAST_MODE}" == "true" ]]; then
        mode="development"
    fi
    
    log_info "Running release validation in ${mode} mode..."
    
    cd "${PROJECT_ROOT}"
    
    local validation_cmd=(
        "${PYTHON_CMD}" -m cli.release_check
        --mode "${mode}"
        --output-json "pre_deploy_${TIMESTAMP}_report.json"
        --output-html "pre_deploy_${TIMESTAMP}_report.html"
        --verbose
    )
    
    if "${validation_cmd[@]}" > "${LOG_FILE}.validation" 2>&1; then
        log_success "Release validation passed"
        
        # Show summary from JSON report
        if [[ -f "pre_deploy_${TIMESTAMP}_report.json" ]]; then
            local overall_passed=$("${PYTHON_CMD}" -c "
import json
with open('pre_deploy_${TIMESTAMP}_report.json', 'r') as f:
    report = json.load(f)
print(report.get('overall_passed', False))
")
            
            local coverage=$("${PYTHON_CMD}" -c "
import json
with open('pre_deploy_${TIMESTAMP}_report.json', 'r') as f:
    report = json.load(f)
print(report.get('coverage_summary', {}).get('total_coverage', 0))
")
            
            local total_duration=$("${PYTHON_CMD}" -c "
import json
with open('pre_deploy_${TIMESTAMP}_report.json', 'r') as f:
    report = json.load(f)
print(f\"{report.get('total_duration', 0):.2f}\")
")
            
            log_info "Validation Summary:"
            log_info "  Overall Passed: ${overall_passed}"
            log_info "  Test Coverage: ${coverage}%"
            log_info "  Duration: ${total_duration}s"
            
            if [[ "${overall_passed}" != "True" ]]; then
                log_error "Release validation reported failures"
                tail -50 "${LOG_FILE}.validation"
                exit 1
            fi
        fi
    else
        log_error "Release validation failed"
        tail -50 "${LOG_FILE}.validation"
        exit 1
    fi
}

# Validate Docker image (if not skipped)
validate_docker() {
    if [[ "${SKIP_DOCKER}" == "true" ]]; then
        log_info "Skipping Docker validation (--skip-docker specified)"
        return 0
    fi
    
    log_info "Validating Docker image..."
    
    cd "${PROJECT_ROOT}"
    
    # Build Docker image
    log_info "Building Docker image..."
    if docker build -t proofkit:pre-deploy-test . > "${LOG_FILE}.docker_build" 2>&1; then
        log_success "Docker image built successfully"
    else
        log_error "Docker image build failed:"
        tail -20 "${LOG_FILE}.docker_build"
        exit 1
    fi
    
    # Test Docker image
    log_info "Testing Docker image functionality..."
    
    # Start container in background
    local container_id
    if container_id=$(docker run -d --rm -p 8000:8000 proofkit:pre-deploy-test 2>/dev/null); then
        log_info "Container started: ${container_id:0:12}"
        
        # Wait for startup
        local max_attempts=30
        local attempt=0
        
        while [[ ${attempt} -lt ${max_attempts} ]]; do
            if curl -f -s http://localhost:8000/health &>/dev/null; then
                log_success "Health check passed"
                break
            fi
            
            ((attempt++))
            sleep 1
        done
        
        if [[ ${attempt} -eq ${max_attempts} ]]; then
            log_error "Health check failed after ${max_attempts} attempts"
            docker logs "${container_id}" | tail -20
            docker stop "${container_id}" &>/dev/null || true
            exit 1
        fi
        
        # Test main endpoint
        if curl -f -s http://localhost:8000/ &>/dev/null; then
            log_success "Main endpoint accessible"
        else
            log_error "Main endpoint not accessible"
            docker logs "${container_id}" | tail -20
            docker stop "${container_id}" &>/dev/null || true
            exit 1
        fi
        
        # Stop container
        docker stop "${container_id}" &>/dev/null || true
        log_success "Container stopped successfully"
        
    else
        log_error "Failed to start Docker container"
        exit 1
    fi
    
    # Get image size
    local image_size
    image_size=$(docker images proofkit:pre-deploy-test --format "{{.Size}}")
    log_info "Docker image size: ${image_size}"
    
    # Cleanup test image
    docker rmi proofkit:pre-deploy-test &>/dev/null || true
    
    log_success "Docker validation completed"
}

# Run basic security checks
run_security_checks() {
    log_info "Running basic security checks..."
    
    cd "${PROJECT_ROOT}"
    
    # Check for common security issues in Python files
    log_info "Checking for common security patterns..."
    
    local security_issues=0
    
    # Check for hardcoded secrets (basic patterns)
    if grep -r -i --include="*.py" -E "(password|secret|key|token)\s*=\s*['\"][^'\"]{8,}" . 2>/dev/null | grep -v "test" | grep -v "example"; then
        log_warn "Potential hardcoded secrets found (review above)"
        ((security_issues++))
    fi
    
    # Check for SQL injection patterns
    if grep -r --include="*.py" -E "\.execute\s*\(\s*[\"'][^\"']*%[^\"']*[\"']\s*%" . 2>/dev/null; then
        log_warn "Potential SQL injection patterns found"
        ((security_issues++))
    fi
    
    # Check for eval usage
    if grep -r --include="*.py" -E "\beval\s*\(" . 2>/dev/null; then
        log_warn "eval() usage found - review for security"
        ((security_issues++))
    fi
    
    # Check file permissions on sensitive files
    local sensitive_files=("requirements.txt" "app.py" ".env" "config.py")
    for file in "${sensitive_files[@]}"; do
        if [[ -f "${file}" ]]; then
            local perms
            perms=$(stat -c "%a" "${file}" 2>/dev/null || stat -f "%Lp" "${file}" 2>/dev/null || echo "unknown")
            if [[ "${perms}" =~ ^[0-9]+$ ]] && [[ ${perms} -gt 644 ]]; then
                log_warn "${file} has overly permissive permissions: ${perms}"
                ((security_issues++))
            fi
        fi
    done
    
    if [[ ${security_issues} -gt 0 ]]; then
        log_warn "Found ${security_issues} potential security issues"
        if [[ "${FAST_MODE}" == "false" ]]; then
            log_error "Security issues found in production mode"
            exit 1
        fi
    else
        log_success "Basic security checks passed"
    fi
}

# Generate deployment summary
generate_summary() {
    log_info "Generating deployment summary..."
    
    local summary_file="${PROJECT_ROOT}/pre_deploy_${TIMESTAMP}_summary.txt"
    
    cat > "${summary_file}" << EOF
ProofKit Pre-Deployment Validation Summary
==========================================

Timestamp: $(date '+%Y-%m-%d %H:%M:%S')
Mode: $(if [[ "${FAST_MODE}" == "true" ]]; then echo "Fast"; else echo "Production"; fi)
Python Version: ${PYTHON_VERSION}
Docker Validation: $(if [[ "${SKIP_DOCKER}" == "true" ]]; then echo "Skipped"; else echo "Passed"; fi)

Project Root: ${PROJECT_ROOT}
Log File: ${LOG_FILE}
Reports: 
  - JSON: pre_deploy_${TIMESTAMP}_report.json
  - HTML: pre_deploy_${TIMESTAMP}_report.html

All validation checks passed successfully.
The application is ready for deployment.

Next steps:
1. Review any warnings in the detailed logs
2. Deploy using your preferred method
3. Run post-deployment smoke tests
4. Monitor application metrics

EOF

    log_success "Summary generated: ${summary_file}"
    
    # Display summary
    echo
    echo "============================================="
    echo "🎉 PRE-DEPLOYMENT VALIDATION COMPLETED"
    echo "============================================="
    cat "${summary_file}"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up temporary files..."
    
    # Remove temporary log files but keep main logs
    rm -f "${LOG_FILE}.pip" "${LOG_FILE}.pip_check" "${LOG_FILE}.validation" "${LOG_FILE}.docker_build" 2>/dev/null || true
    
    # Clean up any running containers
    local test_containers
    test_containers=$(docker ps -q --filter "ancestor=proofkit:pre-deploy-test" 2>/dev/null || true)
    if [[ -n "${test_containers}" ]]; then
        log_info "Stopping test containers..."
        echo "${test_containers}" | xargs docker stop &>/dev/null || true
    fi
    
    # Remove test Docker image
    docker rmi proofkit:pre-deploy-test &>/dev/null || true
}

# Main execution
main() {
    log_info "Starting ProofKit pre-deployment validation..."
    log_info "Project root: ${PROJECT_ROOT}"
    log_info "Log file: ${LOG_FILE}"
    
    # Parse arguments
    parse_args "$@"
    
    # Run validation steps
    check_system_requirements
    check_project_structure
    check_dependencies
    run_release_validation
    validate_docker
    run_security_checks
    generate_summary
    
    log_success "All pre-deployment validations completed successfully!"
    echo
    echo "🚀 Ready for deployment!"
}

# Set up cleanup trap
trap cleanup EXIT

# Run main function with all arguments
main "$@"