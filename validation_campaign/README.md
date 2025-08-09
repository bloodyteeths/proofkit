# Validation Campaign Dataset Registry

This directory contains the validation campaign infrastructure for tracking and testing datasets across all ProofKit industry types.

## Overview

The validation campaign ensures that our CSV normalization and decision algorithms work correctly across different industrial processes by maintaining a registry of test datasets with known expected outcomes.

## Registry Schema

The `registry.yaml` file follows the `registry_v1` schema with the following structure:

### Dataset Entry Format

```yaml
dataset_name:
  id: "unique_dataset_id"          # Unique identifier for the dataset
  industry: "industry_type"        # One of: powder, haccp, autoclave, coldchain, concrete, sterile
  csv_path: "path/to/data.csv"     # Relative path to CSV file from repo root
  spec_path: "path/to/spec.json"   # Relative path to spec JSON from repo root
  expected_outcome: "OUTCOME"      # PASS | FAIL | ERROR | INDETERMINATE
  provenance:
    source: "data_source"          # Source of the data (synthetic_generator, real_world, etc.)
    owner_permission: boolean      # Whether we have permission to use this data
    pii_checked: boolean           # Whether data has been checked for PII
    created_by: "creator"          # Who created/added this dataset
    created_date: "YYYY-MM-DD"    # When dataset was added
  metadata:
    vendor: "vendor_name"          # Equipment vendor or source
    units: "temperature_units"     # celsius or fahrenheit
    cadence: "sampling_rate"       # e.g., "30s", "60s", "300s"
    sensors: ["sensor_list"]       # List of sensors/columns in CSV
    duration_minutes: integer      # Total duration of the dataset
    notes: "description"           # Human-readable description
```

## Expected Outcomes

- **PASS**: Process meets all specification requirements
- **FAIL**: Process fails specification requirements (but data is valid)
- **ERROR**: Data quality issues prevent analysis (gaps, duplicates, missing columns)
- **INDETERMINATE**: Ambiguous cases where outcome depends on interpretation

## Adding New Datasets

### For Real-World CSV Data

1. **Obtain Permission**: Ensure you have explicit permission to use the data
2. **PII Check**: Verify no personally identifiable information is present
3. **Data Placement**: 
   - Add CSV to appropriate `audit/fixtures/{industry}/` directory
   - Add corresponding spec JSON to same directory
4. **Registry Entry**: Add entry to `registry.yaml` following the schema
5. **Validation**: Run `scripts/registry_sanity.py` to validate the entry

### For Synthetic Test Data

1. **Generate Data**: Use our synthetic data generators
2. **Data Placement**: Place in `audit/fixtures/{industry}/` directory
3. **Registry Entry**: Add to `registry.yaml` with `source: "synthetic_generator"`
4. **Validation**: Run sanity checks

## File Organization

```
validation_campaign/
├── registry.yaml              # Main dataset registry
├── README.md                  # This file
audit/fixtures/
├── powder/                    # Powder coating datasets
├── haccp/                     # HACCP cooling datasets
├── autoclave/                 # Autoclave sterilization datasets
├── coldchain/                 # Cold chain storage datasets
├── concrete/                  # Concrete curing datasets
└── sterile/                   # Sterile processing datasets
```

## Industry-Specific Notes

### Powder Coating
- Target temperatures typically 160-200°C
- Hold times 5-20 minutes
- Common failure modes: insufficient hold, temperature overshoot

### HACCP Cooling
- Two-stage cooling requirements (135°C→70°C→41°C)
- Time limits: 2hrs for first stage, 6hrs total
- Common failures: slow cooling rates

### Autoclave Sterilization
- Temperature/pressure combinations (121°C + 15psi)
- Precise timing requirements (15-30 minutes)
- F-value calculations for equivalent sterilization

### Cold Chain Storage
- Narrow temperature bands (2-8°C for vaccines)
- Long monitoring periods (days to months)
- Excursion detection and recovery

### Concrete Curing
- Temperature monitoring during cure (typically 48-72hrs)
- Heat of hydration tracking
- ASTM C31 compliance requirements

### Sterile Processing
- Dry heat sterilization (160-180°C)
- Extended hold times (1-4 hours)
- Bioburden reduction requirements

## Data Quality Requirements

All datasets must meet these minimum quality standards:

1. **Valid CSV Format**: Parseable by pandas
2. **Required Columns**: timestamp + at least one temperature sensor
3. **No Missing Required Data**: Complete timestamp and temperature columns
4. **Reasonable Sampling**: Cadence appropriate for industry type
5. **Proper Timestamps**: ISO format or unambiguous local format

## Testing Integration

The registry integrates with our test suite:

- `scripts/registry_sanity.py`: Validates all registry entries
- `tests/validation/test_registry_sanity.py`: Tests the sanity checker
- Golden file comparisons for deterministic outputs
- Automated CI validation of new datasets

## Maintenance

- Review registry monthly for data quality
- Update provenance information when datasets change
- Retire datasets that become obsolete
- Add new edge cases as discovered in production

## Security Considerations

- Never commit datasets containing real customer data without explicit permission
- Sanitize all real-world datasets for PII before inclusion
- Document data sources and usage permissions clearly
- Use synthetic data whenever possible for edge cases