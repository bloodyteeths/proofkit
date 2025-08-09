# Autoclave Sterilization Datasets

## Overview
This directory contains temperature monitoring datasets for steam sterilization processes used in medical device processing. Data follows ISO 17665 and FDA CFR 21 Part 11 requirements.

## Datasets

### raw/medical_device_sterilization.csv
**Source**: Representative dataset based on industry standards  
**Standard**: ISO 17665 (Moist heat sterilization)  
**Parameters**: 
- Temperature: 121°C for 15 minutes
- Pressure: 15 PSI above atmospheric
- Steam quality monitoring
- F0 value calculation

**Columns**:
- `timestamp`: ISO 8601 formatted datetime
- `temperature_celsius`: Temperature readings (°C)
- `pressure_psi`: Pressure readings (PSI above atmospheric)
- `steam_quality_percent`: Steam dryness fraction (%)
- `cycle_type`: Phase of sterilization cycle
- `validation_probe`: Probe identifier
- `fo_value`: Cumulative lethality value
- `notes`: Process annotations

**Cycle Phases**:
- `prevac`: Pre-vacuum conditioning
- `steam_injection`: Steam pulses for air removal
- `heating`: Temperature ramp to sterilization target
- `sterilization`: Hold period at target temperature
- `exhaust`: Steam exhaust and pressure reduction
- `cooling`: Controlled cooling phase
- `drying`: Final drying cycle
- `complete`: Cycle completion

## Critical Control Points
- Temperature must reach 121°C ± 1°C
- Hold time: minimum 15 minutes at sterilization temperature
- Pressure: 15 PSI ± 1 PSI above atmospheric
- F0 value: minimum 8 minutes equivalent at 121°C

## Quality Specifications
- Data logging interval: 1 minute
- Temperature accuracy: ±0.5°C
- Pressure accuracy: ±0.5 PSI
- NIST-traceable calibration required

## Regulatory Compliance
- ISO 17665: Moist heat sterilization requirements
- FDA CFR 21 Part 11: Electronic records and signatures
- ANSI/AAMI ST8: Hospital steam sterilizers
- EN 285: Steam sterilization for medical devices

## Notes
Dataset represents typical pre-vacuum steam sterilization cycle for wrapped medical instruments. Temperature excursions, pressure variations, and steam quality measurements are included to demonstrate real-world monitoring conditions.