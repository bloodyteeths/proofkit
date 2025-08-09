# Concrete Curing Temperature Datasets

## Overview
This directory contains temperature monitoring datasets for concrete curing processes following ASTM standards. Data demonstrates proper temperature control during the critical curing period for strength development.

## Datasets

### raw/astm_c31_sample_curing.csv
**Source**: Representative dataset based on ASTM C31 standard  
**Standard**: ASTM C31/C31M (Making and Curing Concrete Test Specimens)  
**Parameters**: 
- Temperature: 73.5°F ± 3.5°F (23°C ± 2°C)
- Relative humidity: 50% minimum
- Curing duration: 28 days (sample shows first 24 hours)
- Maturity index calculation per ASTM C1074

**Columns**:
- `timestamp`: ISO 8601 formatted datetime
- `temperature_celsius`: Curing temperature (°C)
- `relative_humidity_percent`: Environmental humidity (%)
- `maturity_index`: Cumulative temperature-time factor
- `notes`: Process annotations and milestone markers

**Curing Phases**:
- Initial curing: First 24-48 hours at controlled temperature
- Moist curing: Continuous water contact on surfaces
- Temperature control: Constant 23°C ± 2°C environment
- Maturity tracking: Age-temperature relationship

## Critical Control Points
- **Temperature Range**: 23°C ± 2°C (73.5°F ± 3.5°F)
- **Humidity**: Minimum 50% RH, maintain surface moisture
- **Initial Period**: First 24 hours most critical
- **High-Strength Concrete**: 20-25.5°C range for ≥6000 psi designs

## Maturity Index Calculation
Maturity = Σ(T - T₀) × Δt  
Where:
- T = average concrete temperature during time interval
- T₀ = datum temperature (-10°C for ordinary portland cement)
- Δt = time interval

## Quality Specifications
- **Data logging interval**: 15 minutes per ASTM C511
- **Temperature accuracy**: ±1°C
- **Calibration**: NIST-traceable standards
- **Record retention**: Minimum 2 years for compliance

## ASTM Standards References
- **ASTM C31**: Making and curing concrete test specimens in field
- **ASTM C511**: Specification for moist curing rooms and cabinets
- **ASTM C1074**: Estimating concrete strength using maturity method
- **ASTM C1064**: Temperature of freshly mixed concrete
- **ASTM C192**: Making and curing test specimens in laboratory

## Environmental Requirements
- **Curing Room**: 23°C ± 2°C, >95% RH
- **Water Temperature**: 23°C ± 2°C for specimen immersion
- **Air Circulation**: Prevent moisture loss and temperature gradients
- **Specimen Storage**: Free water maintained on all surfaces

## Strength Development
- **24 hours**: ~25% of 28-day strength
- **7 days**: ~65% of 28-day strength  
- **28 days**: Design strength achievement
- **Temperature sensitivity**: Higher temperature accelerates early strength

## Common Issues
- Temperature fluctuations during initial set
- Insufficient moisture maintenance
- Thermal gradients in large specimens
- Delayed temperature control implementation
- Inadequate data logging frequency

## Notes
Dataset represents standard laboratory curing conditions for concrete test specimens. Proper temperature control during curing is essential for achieving design strength and ensuring structural safety. Temperature variations can significantly impact strength development and long-term durability characteristics.