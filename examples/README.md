# ProofKit Examples Directory

This directory contains comprehensive example datasets for testing and demonstrating ProofKit's powder coat cure validation capabilities.

## 📁 File Structure

### ✅ Successful Examples (PASS)
- `powder_coat_cure_successful_180c_10min_pass.csv` - Standard automotive cure with clean temperature profile
- `powder_coat_cure_cumulative_hold_pass_170c_20min.csv` - Large part cure allowing temperature dips
- `powder_coat_cure_fahrenheit_input_356f_10min_pass.csv` - US automotive data in Fahrenheit units

### ❌ Failed Examples (FAIL)
- `powder_coat_cure_insufficient_hold_time_fail.csv` - Temperature reached but inadequate hold time
- `powder_coat_cure_data_gaps_sensor_disconnect_fail.csv` - Sensor disconnection creating data gaps
- `powder_coat_cure_slow_ramp_rate_fail.csv` - Excessive time to reach target temperature
- `powder_coat_cure_sensor_failure_mid_run_fail.csv` - Complete sensor failure during cure

### 📋 Specification Templates
- `powder_coat_cure_spec_standard_180c_10min.json` - General-purpose cure specification
- `powder_coat_cure_spec_strict_tolerances_190c_15min.json` - High-precision cure requirements
- `powder_coat_cure_spec_cumulative_hold_170c_20min.json` - Flexible cure with dip tolerance
- `powder_coat_cure_spec_fahrenheit_input_356f_10min.json` - Fahrenheit input specification

### 📦 Generated Outputs
The `outputs/` directory contains golden reference files:
- `*.pdf` - Proof certificates showing PASS/FAIL results
- `*.zip` - Complete evidence bundles with tamper-evident sealing
- `*.json` - Decision analysis results
- `*.png` - Temperature profile plots

## 🎯 Scenario Coverage

### Temperature Profiles
1. **Clean Ramp** - Smooth temperature rise to target with stable hold
2. **Dip Tolerance** - Temperature drops during cure but recovers
3. **Fast Cooling** - Rapid temperature loss after reaching target
4. **Slow Heating** - Conservative ramp rate exceeding time limits

### Data Quality Issues
1. **Sensor Gaps** - Missing data periods from disconnections
2. **Sensor Failure** - Complete loss of one or more sensors
3. **Sampling Rate** - Different data collection frequencies

### Unit Handling
1. **Celsius Input** - Standard metric temperature data
2. **Fahrenheit Input** - US customary units with automatic conversion

### Validation Logic
1. **Continuous Hold** - Temperature must stay above threshold continuously
2. **Cumulative Hold** - Total time above threshold with brief dips allowed
3. **Sensor Redundancy** - Multi-sensor validation strategies

## 🔧 Usage Instructions

### Basic Testing
1. Visit the [Examples Page](/examples) in ProofKit web interface
2. Download any CSV file and corresponding JSON specification
3. Upload both files through the main ProofKit interface
4. Compare results with expected PASS/FAIL outcomes

### API Testing
```bash
# Test with curl
curl -X POST http://localhost:8000/api/compile/json \
  -F "csv_file=@powder_coat_cure_successful_180c_10min_pass.csv" \
  -F "spec_json=@powder_coat_cure_spec_standard_180c_10min.json"
```

### CLI Testing
```bash
# Process complete pipeline
proofkit normalize --csv powder_coat_cure_successful_180c_10min_pass.csv --out normalized.csv
proofkit decide --csv normalized.csv --spec powder_coat_cure_spec_standard_180c_10min.json --out decision.json
proofkit render --decision decision.json --csv normalized.csv --out proof.pdf --plot plot.png
proofkit pack --inputs powder_coat_cure_successful_180c_10min_pass.csv powder_coat_cure_spec_standard_180c_10min.json --normalized normalized.csv --decision decision.json --pdf proof.pdf --plot plot.png --out evidence.zip
proofkit verify --bundle evidence.zip
```

## 📊 Data Format Details

### CSV Temperature Data
- **Timestamp Column**: ISO 8601 format (e.g., `2024-01-15T10:00:00Z`)
- **Temperature Columns**: Numeric values in Celsius or Fahrenheit
- **Metadata Comments**: Lines starting with `#` contain descriptive information
- **Sample Rate**: Typically 30-second intervals
- **Sensor Naming**: Descriptive names like `pmt_sensor_1`, `pmt_sensor_2_f`

### JSON Specifications
All specifications follow the ProofKit v1.0 schema:
- **Required**: `version`, `job`, `spec`, `data_requirements`
- **Optional**: `sensor_selection`, `logic`, `preconditions`, `reporting`
- **Validation**: Strict schema validation prevents invalid configurations

## 🎓 Educational Value

### Real-World Scenarios
Each example represents actual situations encountered in powder coating operations:
- **Automotive**: Wheel and component coating with tight tolerances
- **Industrial**: Heavy machinery parts with thermal mass challenges  
- **Precision**: Electronic components requiring controlled heating
- **Decorative**: Furniture coating with aesthetic quality requirements

### Quality Control Principles
Examples demonstrate key concepts:
- **Conservative Thresholds**: Target + uncertainty for safety margins
- **Hold Time Logic**: Continuous vs. cumulative time calculations
- **Data Integrity**: Gap detection and sensor redundancy requirements
- **Process Validation**: Complete audit trail with tamper-evident packaging

## 🔍 SEO-Optimized Naming

File names follow SEO best practices:
- **Descriptive**: Clear indication of content and expected result
- **Keyword Rich**: Includes "powder_coat_cure" for discoverability
- **Structured**: Consistent naming pattern across all files
- **Meaningful**: Technical parameters visible in filename

Pattern: `powder_coat_cure_[scenario]_[temperature]_[time]_[result].[ext]`

## 🚀 Future Enhancements

Potential additions to example set:
- **OVEN_AIR Method**: Air temperature validation examples
- **Multi-Zone Cures**: Complex parts with different cure requirements  
- **Batch Processing**: Multiple parts in single cure cycle
- **International Standards**: Examples following ISO/ASTM guidelines
- **Edge Cases**: Boundary condition testing scenarios

## 📞 Support

For questions about these examples:
1. Review the generated proof PDFs to understand analysis logic
2. Check the evidence bundle verification process
3. Examine the decision JSON files for detailed reasoning
4. Visit the main ProofKit interface for interactive testing

---

*These examples demonstrate ProofKit's comprehensive powder coat cure validation capabilities while providing practical, real-world testing scenarios for quality control applications.*