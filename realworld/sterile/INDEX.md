# Sterile Processing Datasets

## Overview
This directory contains temperature monitoring datasets for sterile processing operations following ISO standards. Data demonstrates proper steam sterilization cycles for medical devices and pharmaceutical products.

## Datasets

### raw/iso_17665_steam_sterilization.csv
**Source**: Representative dataset based on ISO 17665 standard  
**Standard**: ISO 17665:2024 (Moist heat sterilization)  
**Parameters**: 
- Temperature: 121°C for 15 minutes minimum
- Pressure: 147-149 kPa above atmospheric
- Steam quality: >90% dry saturated steam
- Air removal: Pre-vacuum or gravity displacement

**Columns**:
- `timestamp`: ISO 8601 formatted datetime
- `temperature_celsius`: Chamber temperature (°C)
- `pressure_kpa`: Chamber pressure (kPa absolute)
- `steam_quality_percent`: Steam dryness fraction (%)
- `cycle_phase`: Current sterilization phase
- `notes`: Process milestones and observations

**Cycle Phases**:
- `preconditioning`: Initial chamber preparation
- `air_removal`: Air evacuation for steam penetration
- `heating`: Temperature ramp to sterilization level
- `sterilization`: Hold period at lethal temperature
- `cooling`: Controlled cooling with steam exhaust
- `drying`: Final moisture removal
- `complete`: Cycle completion and safety checks

## Critical Control Points
- **Sterilization Temperature**: 121°C ± 1°C
- **Hold Time**: Minimum 15 minutes at temperature
- **Steam Quality**: ≥90% dry saturated steam
- **Air Removal**: Complete air evacuation required
- **Pressure**: 147-149 kPa (15 PSI gauge)

## Alternative Cycles
- **High Temperature**: 134°C for 3 minutes (flash sterilization)
- **Low Temperature**: 115°C for extended time (heat-sensitive items)
- **Porous Loads**: Extended cycles for textile materials
- **Liquid Loads**: Slow exhaust to prevent boiling

## Quality Specifications
- **Data logging**: 1-minute intervals minimum
- **Temperature accuracy**: ±0.5°C
- **Pressure accuracy**: ±2 kPa
- **Calibration frequency**: Monthly with NIST standards

## ISO Standards References
- **ISO 17665:2024**: Primary moist heat sterilization standard
- **ISO 11138**: Biological indicators for validation
- **ISO 11140**: Chemical indicators systems
- **ISO 14161**: Validation and routine monitoring
- **ISO 17664**: Processing of medical devices

## Validation Requirements
- **Installation Qualification (IQ)**: Equipment installation verification
- **Operational Qualification (OQ)**: Performance parameter testing
- **Performance Qualification (PQ)**: Process effectiveness validation
- **Routine Monitoring**: Ongoing cycle verification

## Steam Quality Testing
- **Dryness Value**: Minimum 97% dry saturated steam
- **Non-Condensable Gas**: Maximum 3.5% by volume
- **Superheating**: Maximum 25°C above saturation temperature
- **Chemical Quality**: Conductivity, pH, chloride, hardness limits

## Load Configurations
- **Wrapped Items**: Surgical instruments in pouches/wraps
- **Unwrapped Items**: Flash sterilization applications
- **Porous Materials**: Textiles, rubber, plastics
- **Liquids**: Media, solutions in sealed containers

## Monitoring Points
- **Chamber**: Primary control sensor location
- **Load**: Thermocouple probes in product
- **Drain**: Condensate temperature verification
- **Supply**: Incoming steam quality assessment

## Notes
Dataset represents typical pre-vacuum steam sterilization cycle for wrapped medical devices. Demonstrates critical importance of air removal, steam quality, and precise temperature control. Proper monitoring ensures sterility assurance level (SAL) of 10⁻⁶ or better as required by regulatory standards.