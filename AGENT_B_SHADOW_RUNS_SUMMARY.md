# Agent B - Shadow Runs Implementation Summary

## Overview

Successfully implemented differential verification system with shadow runs comparing the main ProofKit engine against independent reference calculators. This system helps ensure algorithmic correctness and detect regressions.

## Files Created/Modified

### Core Implementation
- **`core/shadow_compare.py`** - New shadow comparison engine with industry-specific tolerances
- **`app.py`** - Modified process_csv_and_spec() to integrate shadow runs
- **`scripts/diff_check.py`** - Enhanced to use autoclave_fo.py function name fix

### Independent Calculators (Enhanced)
- **`validation/independent/coldchain_daily.py`** - Added calculate_daily_compliance function
- **`validation/independent/autoclave_fo.py`** - Added calculate_fo_metrics function and fixed naming conflict

### Test Suite
- **`tests/diff/test_shadow_compare.py`** - Comprehensive unit tests for shadow comparison engine
- **`tests/test_shadow_integration.py`** - Integration tests for full app pipeline

## Key Features Implemented

### 1. Environment Variable Control
- Shadow runs controlled by `REQUIRE_DIFF_AGREEMENT` environment variable
- Values: `"1"`, `"true"`, `"yes"` enable shadow runs (case insensitive)
- Default: disabled for production safety

### 2. Industry-Specific Tolerances
```python
INDUSTRY_TOLERANCES = {
    'powder': {
        'hold_time_s': 1.0,                    # ±1s for powder hold times
        'ramp_rate_C_per_min': 0.05,          # ±5% relative for ramp rates
        'time_to_threshold_s': 1.0,           # ±1s for time to threshold
    },
    'autoclave': {
        'fo_value': 0.1,                      # ±0.1 for F0 values
        'hold_time_s': 1.0,                   # ±1s for sterilization times
    },
    'sterile': {
        'phase_times_s': 60.0,                # ±60s for sterile phase times
    },
    'haccp': {
        'phase1_time_s': 30.0,                # ±30s for 135→70C phase
        'phase2_time_s': 30.0,                # ±30s for 70→41C phase
    },
    'concrete': {
        'percent_in_spec_24h': 1.0,           # ±1% for 24h compliance
        'temperature_time_hours': 0.1,       # ±0.1h for temperature-time
    },
    'coldchain': {
        'overall_compliance_pct': 0.5,       # ±0.5% for compliance percentages
        'excursion_duration_s': 1.0,         # ±1s for excursion timing
    }
}
```

### 3. Shadow Comparison Logic
- Main engine and independent calculator run in parallel
- Results compared against industry-specific tolerances
- Status outcomes:
  - **AGREEMENT**: Results within tolerance
  - **TOLERANCE_VIOLATION**: Outside tolerance → INDETERMINATE result
  - **ENGINE_ERROR**: Main engine failed
  - **INDEPENDENT_ERROR**: Independent calculator failed  
  - **NOT_SUPPORTED**: Industry not supported
  - **DISABLED**: Shadow runs disabled

### 4. INDETERMINATE Result Handling
When shadow comparison finds tolerance violations:
- Original decision overridden with `status: "INDETERMINATE"`
- `pass_: false` to prevent certification of questionable results
- Reason includes detailed tolerance violation information
- Original measurements preserved for audit trail

### 5. Independent Calculator Functions
Each industry has dedicated independent calculators:

#### Powder Coating
- `calculate_hold_time()` - Hold time calculation with hysteresis
- `calculate_ramp_rate()` - Maximum ramp rate using central differences
- `calculate_time_to_threshold()` - Time from start to threshold crossing

#### HACCP Cooling  
- `validate_cooling_phases()` - FDA Food Code phase validation
- Linear interpolation for precise temperature crossing times

#### Cold Chain
- `calculate_daily_compliance()` - Overall compliance percentage
- `detect_excursions()` - Temperature excursion detection
- `calculate_mean_kinetic_temperature()` - MKT for stability assessment

#### Autoclave Sterilization
- `calculate_fo_value()` - F0 value calculation using lethal rate integration
- `calculate_sterilization_hold()` - Hold time at sterilization temperature
- `calculate_fo_metrics()` - Complete metrics package

#### Concrete Curing
- `calculate_curing_compliance()` - 24-hour window compliance analysis  
- `calculate_strength_gain_estimation()` - Maturity-based strength estimation
- `validate_concrete_curing()` - Complete curing validation

### 6. Audit Trail and Debugging
- Shadow comparison results saved to `shadow_comparison.json` in job directory
- Detailed difference analysis with tolerance information
- Graceful error handling - shadow failures don't break main processing
- Comprehensive logging for troubleshooting

## Usage Examples

### Enable Shadow Runs
```bash
export REQUIRE_DIFF_AGREEMENT=1
# or
export REQUIRE_DIFF_AGREEMENT=true
```

### Sample Shadow Comparison Result
```json
{
  "status": "TOLERANCE_VIOLATION",
  "reason": "DIFF_EXCEEDS_TOL: hold_time_s: 1200 vs 1205 (diff: 5.000, tolerance: ±1)",
  "engine_result": {
    "pass": true,
    "actual_hold_time_s": 1200.0,
    "status": "PASS"
  },
  "independent_result": {
    "hold_time_s": 1205.0,
    "pass": true
  },
  "differences": {
    "hold_time_s": {
      "engine_value": 1200.0,
      "independent_value": 1205.0,
      "difference": 5.0,
      "within_tolerance": false,
      "tolerance_used": 1.0,
      "tolerance_type": "absolute"
    }
  }
}
```

### Resulting INDETERMINATE Decision
```json
{
  "pass": false,
  "status": "INDETERMINATE", 
  "actual_hold_time_s": 1200.0,
  "reasons": ["DIFF_EXCEEDS_TOL: hold_time_s: 1200 vs 1205 (diff: 5.000, tolerance: ±1)"],
  "industry": "powder",
  "job_id": "abc123"
}
```

## Testing Coverage

### Unit Tests (`tests/diff/test_shadow_compare.py`)
- Shadow comparison logic for all industries
- Tolerance violation scenarios
- Error handling (engine errors, independent errors)
- Serialization and result handling
- Multiple metrics comparison
- INDETERMINATE result creation

### Integration Tests (`tests/test_shadow_integration.py`)  
- Full app pipeline with shadow runs enabled/disabled
- Environment variable control
- Graceful error fallback behavior
- File system integration (shadow_comparison.json)
- All industry support verification

## Security and Production Considerations

### Safe Defaults
- Shadow runs **disabled by default** to prevent production disruption
- Original decision used if shadow comparison fails
- No breaking changes to existing API contracts

### Error Resilience
- Shadow comparison errors logged but don't fail main processing
- Fallback to original decision maintains service availability
- Comprehensive exception handling prevents crashes

### Performance Impact
- Shadow runs add computational overhead (~2x processing time)
- Only enabled when explicitly requested via environment variable
- Independent calculators optimized for simple, fast execution

## Roadmap Integration

This implementation fulfills **Milestone PR-B** requirements:

✅ **Shadow compute flag** via `REQUIRE_DIFF_AGREEMENT` environment variable  
✅ **Industry-specific tolerances** for all supported industries  
✅ **INDETERMINATE status** when tolerance violations detected  
✅ **Comprehensive testing** with unit and integration tests  
✅ **Safe mode integration** through environment variable control  
✅ **Independent calculator library** with pure functions exported  
✅ **Differential verification** comparing engine vs independent implementations

The system provides robust algorithmic validation while maintaining production safety through careful error handling and disabled-by-default operation.