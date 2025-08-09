# ProofKit HARDEN3 Final Audit Report

Generated: 2025-08-08
Status: **12 failures** (improved from 13)

## Summary
- **Total tests:** 19
- **Passed:** 8 ✓ (42%)  
- **Failed:** 7 ✗ (37%)
- **Errors:** 5 ⚠️ (26%)

## Progress
- Previous: 13 failures
- Current: 12 failures
- **Improvement:** sterile/pass now PASSES (+1)

## Remaining Failures by Industry

### 🔴 Autoclave (1 failure)
- **autoclave/pass**: Expected PASS → Got FAIL
  - Issue: Validation logic too strict

### 🔴 Cold Chain (2 failures)  
- **coldchain/fail**: Expected FAIL → Got INDETERMINATE
  - Error: "Required sensors missing: ['temperature']. Available sensors: ['sensor_1', 'sensor_2', 'sensor_3']"
- **coldchain/pass**: Expected PASS → Got INDETERMINATE
  - Same error - looking for column named "temperature" instead of detecting temp columns

### 🔴 Concrete (2 errors)
- **concrete/fail**: ERROR - "Insufficient data points (minimum 5 required)"
  - 51 rows normalize to only 1 point
- **concrete/pass**: ERROR - Same issue
  - Normalization collapsing data too aggressively

### 🔴 HACCP (2 failures)
- **haccp/fail**: Expected FAIL → Got PASS
  - Cooling validation not detecting failures
- **haccp/missing_required**: Expected ERROR → Got PASS
  - Not raising RequiredSignalMissingError when sensors missing

### 🔴 Powder (3 failures, 2 errors)
- **powder/dup_ts**: Expected ERROR → Got FAIL
  - Duplicates removed but not raising DataQualityError
- **powder/pass**: Expected PASS → Got FAIL
  - Threshold or hold time calculation incorrect
- **powder/gap**: ERROR (expected - data quality)
- **powder/tz_shift**: ERROR (expected - data quality)
- **powder/missing_required**: Now raises RequiredSignalMissingError ✓

### ✅ Sterile (FIXED!)
- **sterile/pass**: Now PASSES correctly ✓
- **sterile/fail**: FAILS as expected ✓

## Root Causes

1. **Cold chain**: Looking for literal "temperature" column instead of using pattern matching
2. **Concrete**: Aggressive resampling (51→1 points) needs fixing  
3. **HACCP**: Cooling phase detection logic not working
4. **Powder**: Threshold calculations and duplicate handling
5. **Autoclave**: Validation too strict for pass case

## Actual Issues Found in Code

From the verbose output:
- Cold chain error: `Required sensors missing: ['temperature']. Available sensors: ['sensor_1', 'sensor_2', 'sensor_3']`
- Concrete: 51 rows → 1 after normalization (too aggressive)
- HACCP: All cases return PASS (validation logic broken)
- Powder: Missing duplicate detection for ERROR case

## Next Steps

1. Fix cold chain to detect sensor_1/2/3 as temperature columns
2. Fix concrete normalization to preserve data points
3. Fix HACCP cooling validation logic
4. Add powder duplicate detection for ERROR
5. Tune autoclave thresholds