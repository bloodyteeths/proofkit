# Kiln/Oven Temperature Datasets

## Overview
This directory contains temperature monitoring datasets for high-temperature thermal processes including ceramic firing, heat treatment, and industrial oven operations. Data demonstrates proper temperature control and firing curve management.

## Datasets

### raw/ceramic_kiln_firing_log.csv
**Source**: Representative dataset based on ceramic firing standards  
**Application**: Pottery/ceramics bisque and glaze firing  
**Parameters**: 
- Temperature range: Ambient to 900°C (Cone 9 equivalent)
- Ramp rates: Variable from 50-300°C/hour
- Hold periods: Moisture removal, bisque, and glaze maturation
- Cooling curve: Controlled natural cooling

**Columns**:
- `timestamp`: ISO 8601 formatted datetime
- `temperature_celsius`: Kiln chamber temperature (°C)
- `target_temperature`: Programmed setpoint (°C)
- `ramp_rate_c_per_hour`: Temperature change rate (°C/hr)
- `kiln_zone`: Measurement location (bottom, middle, top)
- `cone_equivalent`: Orton cone temperature equivalent
- `firing_phase`: Current stage of firing cycle
- `notes`: Process annotations and milestones

**Firing Phases**:
- `loading`: Initial ambient temperature loading
- `ramp1-4`: Controlled heating phases
- `hold1-4`: Temperature plateau periods
- `soak`: Extended hold at peak temperature
- `cooling`: Natural cooling cycle
- `complete`: Safe opening temperature reached

## Pyrometric Cone Equivalents
- **Cone 022**: 586°C (lowest bisque temperature)
- **Cone 04**: 1060°C (typical bisque firing)
- **Cone 6**: 1222°C (mid-fire glaze range)
- **Cone 9**: 1280°C (high-fire stoneware)
- **Cone 14**: 1400°C (porcelain and high-fire applications)

## Critical Control Points
- **Ramp Rate Control**: Prevent thermal shock cracking
- **Moisture Removal**: Slow heating to 100°C for water evaporation
- **Bisque Temperature**: Achieve proper porosity for glazing
- **Glaze Maturation**: Peak temperature for glass formation
- **Cooling Rate**: Prevent stress cracking during cooldown

## Typical Firing Schedule
1. **Candling**: 0-100°C at 50°C/hour (moisture removal)
2. **Low Fire**: 100-500°C at 100°C/hour (chemical water removal)
3. **Medium Fire**: 500-900°C at 150°C/hour (vitrification)
4. **High Fire**: 900°C+ at 100°C/hour (maturation)
5. **Soak**: Hold peak temperature 15-60 minutes
6. **Natural Cool**: Passive cooling to <60°C before opening

## Quality Specifications
- **Temperature accuracy**: ±5°C at operating temperature
- **Ramp rate control**: ±10% of programmed rate
- **Data logging**: 1-minute intervals during firing
- **Thermocouple placement**: Multiple zones for large kilns

## Kiln Types and Applications
- **Electric Kilns**: Precise temperature control, even heating
- **Gas Kilns**: Atmospheric effects, reduction firing capability
- **Wood Kilns**: Traditional methods, ash glazing effects
- **Industrial Ovens**: Heat treatment, curing, drying processes

## Temperature Monitoring
- **Thermocouples**: Type K or Type S for high temperatures
- **Pyrometric Cones**: Visual/mechanical temperature indicators
- **Infrared Pyrometers**: Non-contact surface temperature
- **Data Loggers**: Continuous recording and analysis

## Safety Considerations
- **Ventilation**: Proper exhaust for combustion products
- **Thermal Protection**: Insulation and safety equipment
- **Emergency Shutdown**: Automatic safety systems
- **Cool-down Protocol**: Gradual cooling to prevent damage

## Common Applications
- **Ceramics**: Pottery, porcelain, technical ceramics
- **Glass**: Annealing, slumping, fusing operations
- **Metals**: Heat treatment, annealing, hardening
- **Composites**: Curing, consolidation processes
- **Laboratory**: Sample preparation, ashing procedures

## Notes
Dataset represents complete ceramic firing cycle from room temperature through peak firing to cool-down. Demonstrates importance of controlled heating rates, hold periods for chemical processes, and gradual cooling to prevent thermal stress. Temperature uniformity across kiln zones is critical for consistent results in production environments.