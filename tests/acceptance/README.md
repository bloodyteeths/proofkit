# Acceptance Test Suite

Comprehensive acceptance tests for ProofKit validation system across all supported industries.

## Overview

The acceptance test suite validates that the ProofKit system correctly processes real-world datasets and produces expected outcomes across all supported industries. These tests serve as the final quality gate before deployment.

## Test Structure

### Industry-Specific Tests

Each industry has dedicated acceptance tests:

- **`test_autoclave_acceptance.py`** - Autoclave sterilization validation (121°C steam sterilization)
- **`test_coldchain_acceptance.py`** - Cold chain storage validation (2-8°C vaccine storage)  
- **`test_concrete_acceptance.py`** - Concrete curing validation (ASTM C31 48hr monitoring)
- **`test_haccp_acceptance.py`** - HACCP cooling validation (135°F → 70°F → 41°F compliance)
- **`test_powder_acceptance.py`** - Powder coating cure validation (180°C oven curing)
- **`test_sterile_acceptance.py`** - Sterile processing validation (EtO and dry heat sterilization)

### Cross-Cutting Tests

- **`test_required_signals.py`** - Required signal enforcement across industries
- **`test_registry_compliance.py`** - Registry-based validation of all datasets

## Test Categories

### 1. Basic Compliance Tests

Each industry tests core scenarios:
- **Pass Case**: Meets all specification requirements
- **Fail Case**: Violates specification requirements  
- **Missing Required**: Missing mandatory signals/fields
- **Performance**: Processing time and memory usage

### 2. Registry-Based Tests

Uses `validation_campaign/registry.yaml` for:
- **Synthetic Datasets**: Generated test cases with known outcomes
- **Real-World Datasets**: Industry-provided data with independent validation
- **Edge Cases**: Borderline, error, and indeterminate scenarios

### 3. Evidence Integrity Tests

Validates evidence bundle creation and verification:
- PDF generation without errors
- Bundle integrity and SHA-256 verification
- Deterministic output (identical inputs → identical results)

## Registry Integration

The registry (`validation_campaign/registry.yaml`) defines:

```yaml
datasets:
  powder_pass_001:
    id: "powder_pass_001"
    industry: "powder"
    csv_path: "audit/fixtures/powder/pass.csv"
    spec_path: "audit/fixtures/powder/pass.json"
    expected_outcome: "PASS"
    provenance:
      source: "synthetic_generator"
      owner_permission: true
    metadata:
      vendor: "ProofKit Test Suite"
      units: "celsius"
      duration_minutes: 45
```

## Running Tests

### Individual Industry Tests

```bash
# Test specific industry
pytest tests/acceptance/test_powder_acceptance.py -v

# Test with coverage
pytest tests/acceptance/test_autoclave_acceptance.py --cov=core --cov-report=html
```

### Complete Acceptance Suite

```bash
# Run all acceptance tests
pytest tests/acceptance/ -v

# Run with parallel execution
pytest tests/acceptance/ -n auto -v

# Run only registry compliance
pytest tests/acceptance/test_registry_compliance.py -v
```

### Registry Validation CLI

```bash
# Full validation of all datasets
python cli/registry_validation.py --mode full --verbose

# Smoke test (quick validation)
python cli/registry_validation.py --mode smoke

# Test specific industries
python cli/registry_validation.py --industries powder,autoclave --verbose

# Export campaign data for UI
python cli/registry_validation.py --output campaign_data.json
```

## GitHub Actions Integration

### Acceptance Workflow

`.github/workflows/acceptance.yml` runs:
- **On PR/Push**: All industry tests in parallel
- **Nightly**: Complete registry validation with performance benchmarks
- **Manual Trigger**: Configurable test modes and filters

### CI Integration

`ci.yml` includes:
- **Smoke Test**: Quick registry validation on PRs
- **Coverage Gate**: Acceptance tests must maintain coverage levels
- **Deployment Gate**: All acceptance tests must pass for main branch

## Performance Benchmarks

Each industry has performance requirements:

| Industry   | Max Processing Time | Max Memory Usage |
|------------|-------------------|------------------|
| Powder     | 8 seconds        | 10 MB           |
| Autoclave  | 10 seconds       | 10 MB           |
| Sterile    | 10 seconds       | 15 MB           |
| HACCP      | 12 seconds       | 15 MB           |
| Coldchain  | 15 seconds       | 20 MB           |
| Concrete   | 20 seconds       | 30 MB           |

## Strict Mode Campaign Analysis

The `/campaign` UI includes strict mode validation:
- **Normal Mode**: Shows accuracy percentages and confusion matrices
- **Strict Mode**: Any false positive/negative → RED badge 
- **Visual Indicators**: Pulsing animations for strict failures

Toggle strict mode: `?strict=true`

## Expected Outcomes

Tests validate these outcome categories:

- **PASS**: Meets all specification requirements
- **FAIL**: Violates one or more requirements  
- **ERROR**: Data quality or validation errors
- **INDETERMINATE**: Cannot determine compliance (ambiguous cases)

## Real-World Dataset Validation

Real-world datasets include independent validation:

```yaml
independent_validation:
  fo_value_calculated: 14.8
  sterilization_temperature_achieved: true
  hold_time_minutes: 15.2
  excursion_detected: false
```

Tests verify ProofKit results match independent calculations within tolerances.

## Troubleshooting

### Common Issues

1. **Missing Test Data**
   ```
   pytest.skip: CSV file not found
   ```
   Solution: Ensure `audit/fixtures/` and `realworld/` directories contain required datasets.

2. **Registry Validation Errors** 
   ```
   FileNotFoundError: Registry file not found
   ```
   Solution: Verify `validation_campaign/registry.yaml` exists and is valid YAML.

3. **Performance Benchmark Failures**
   ```
   AssertionError: Processing took 15.2s, expected <10s
   ```
   Solution: Check system performance or optimize validation algorithms.

### Debug Mode

Enable verbose logging:
```bash
pytest tests/acceptance/ -v -s --log-cli-level=DEBUG
```

## Contributing

When adding new industries or test cases:

1. Create industry-specific test file following naming convention
2. Add datasets to registry with proper provenance metadata
3. Update performance benchmarks in this README
4. Ensure 100% test coverage for new validation logic

## Quality Gates

All acceptance tests must pass for:
- ✅ Pull request merging
- ✅ Main branch deployment  
- ✅ Release creation
- ✅ Production deployment

The acceptance test suite serves as the final validation that ProofKit correctly processes real-world industrial data across all supported use cases.