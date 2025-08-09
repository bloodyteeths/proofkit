# ProofKit Examples Directory

This directory contains comprehensive example datasets for testing and demonstrating ProofKit's temperature validation capabilities across 5 key industries.

## 📁 File Structure by Industry

### 🎨 Powder Coating Industry
**✅ PASS Examples:**
- `powder_coat_cure_successful_180c_10min_pass.csv` - Standard automotive cure with clean temperature profile
- `powder_coat_cure_cumulative_hold_pass_170c_20min.csv` - Large part cure allowing temperature dips
- `powder_coat_cure_fahrenheit_input_356f_10min_pass.csv` - US automotive data in Fahrenheit units
- `powder_pass_fixed.csv` - Optimized example with proper ramp rate

**❌ FAIL Examples:**
- `powder_coat_cure_insufficient_hold_time_fail.csv` - Temperature reached but inadequate hold time
- `powder_coat_cure_data_gaps_sensor_disconnect_fail.csv` - Sensor disconnection creating data gaps
- `powder_coat_cure_slow_ramp_rate_fail.csv` - Excessive time to reach target temperature
- `powder_coat_cure_sensor_failure_mid_run_fail.csv` - Complete sensor failure during cure

**📋 Specifications:**
- `powder_coat_cure_spec_standard_180c_10min.json` - General-purpose cure specification
- `powder_coat_cure_spec_strict_tolerances_190c_15min.json` - High-precision cure requirements
- `powder_coat_cure_spec_cumulative_hold_170c_20min.json` - Flexible cure with dip tolerance
- `powder_coat_cure_spec_fahrenheit_input_356f_10min.json` - Fahrenheit input specification
- `powder_pass_spec_fixed.json` - Optimized specification

### 🏥 Autoclave Sterilization
**✅ PASS Examples:**
- `autoclave_sterilization_pass.csv` - Medical device sterilization at 121°C

**❌ FAIL Examples:**
- `autoclave_sterilization_fail.csv` - Incomplete steam penetration
- `autoclave_missing_pressure_indeterminate.csv` - Missing pressure data (INDETERMINATE)

**📋 Specifications:**
- `autoclave-medical-device-validation.json` - Medical device validation spec

### 🏗️ Concrete Curing
**✅ PASS Examples:**
- `concrete_curing_pass.csv` - ASTM C31 compliant curing process

**❌ FAIL Examples:**
- `concrete_curing_fail.csv` - Temperature runaway exceeding safe limits

**📋 Specifications:**
- `concrete-curing-astm-c31.json` - ASTM C31 construction standard

### ❄️ Cold Chain Storage
**✅ PASS Examples:**
- `coldchain_storage_pass.csv` - Pharmaceutical storage 2-8°C

**❌ FAIL Examples:**
- `coldchain_storage_fail.csv` - Temperature excursion above safe range

**📋 Specifications:**
- `coldchain-storage-validation.json` - USP 797 cold storage requirements

### 🍽️ HACCP Food Safety
**✅ PASS Examples:**
- `haccp_cooling_pass.csv` - Proper cooling from 135°F to 41°F

**❌ FAIL Examples:**
- `haccp_cooling_fail.csv` - Slow cooling violating FDA time limits

**📋 Specifications:**
- `haccp-cooling-validation.json` - FDA Food Code cooling requirements

### 🧪 Sterile Processing
**✅ PASS Examples:**
- `sterile_processing_pass.csv` - ISO 17665 steam sterilization

**❌ FAIL Examples:**
- `sterile_processing_fail.csv` - Inadequate temperature exposure

**📋 Specifications:**
- `sterile-processing-validation.json` - ISO 17665 sterile processing standard

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

## 📋 Data Provenance

### Synthetic Test Data
**Purpose:** Designed for reliable testing and demonstration
**Industries:** All 5 industries have synthetic examples
**Characteristics:**
- Predictable outcomes (guaranteed PASS/FAIL results)
- Clean data patterns for educational purposes  
- Covers common failure modes and edge cases
- Optimized for automated testing pipelines

**Source Files:**
- All files copied from `audit/fixtures/` directory
- Generated using mathematically precise temperature profiles
- Validated against specification requirements
- Suitable for CI/CD and regression testing

### Real-World Data Integration
**Future Enhancement:** Integration with anonymized industrial datasets
**Target Sources:**
- Manufacturing quality control systems
- Laboratory validation processes
- Regulatory compliance documentation
- Industry partnership data sharing

**Privacy Protection:**
- All real-world data will be anonymized
- Proprietary process parameters will be generalized
- Company identification will be removed
- Compliance with data protection regulations

### Data Quality Standards
**All Examples Meet:**
- ✅ Schema validation requirements
- ✅ Temporal consistency checks  
- ✅ Sensor redundancy principles
- ✅ Missing data handling protocols
- ✅ Unit conversion accuracy
- ✅ Specification compliance verification

---

*These examples demonstrate ProofKit's comprehensive temperature validation capabilities across 5 industries while providing practical, reliable testing scenarios for quality control applications.*