# Cold Chain Storage Datasets

## Overview
This directory contains temperature monitoring datasets for cold storage facilities used in pharmaceutical and biologics storage. Data follows USP <659> and WHO guidelines for temperature-controlled storage.

## Datasets

### raw/cold_storage_monitoring.csv
**Source**: Representative dataset based on industry standards  
**Standard**: USP <659> (Packaging and Storage Requirements)  
**Parameters**: 
- Temperature: 2-8°C controlled range
- Relative humidity: 45-75% RH
- Door monitoring and alarm systems
- Emergency response protocols

**Columns**:
- `timestamp`: ISO 8601 formatted datetime
- `temperature_celsius`: Temperature readings (°C)
- `humidity_percent`: Relative humidity (%)
- `door_status`: Door position (open/closed)
- `alarm_status`: System alarm state
- `storage_zone`: Storage area identifier
- `product_category`: Type of stored products
- `notes`: Event annotations

**Storage Zones**:
- `zone_a`: Primary biologics storage (2-8°C)
- `zone_b`: Backup storage area
- `zone_c`: Quarantine/inspection area

**Alarm States**:
- `normal`: All parameters within specification
- `high_temp`: Temperature above 8°C
- `low_temp`: Temperature below 2°C
- `door_alarm`: Extended door open condition
- `power_failure`: Electrical supply interruption

## Critical Control Points
- Temperature range: 2-8°C continuous
- Maximum excursion: 15°C for less than 24 hours
- Recovery time: Return to 2-8°C within 2 hours
- Door open time: Maximum 3 minutes per access
- Humidity range: 45-75% RH

## Quality Specifications
- Data logging interval: 15 minutes (normal), 1 minute (alarm)
- Temperature accuracy: ±0.5°C
- Humidity accuracy: ±3% RH
- Calibration frequency: Quarterly with NIST-traceable standards

## Regulatory Compliance
- USP <659>: Packaging and storage requirements
- USP <1079>: Good storage and distribution practices
- WHO Technical Report Series 961: Temperature monitoring
- CFR 21 Part 211: cGMP requirements
- ICH Q1A: Stability testing guidelines

## Emergency Procedures
Dataset includes temperature excursion event demonstrating:
- Compressor failure at 11:00
- Temperature rise to 20.1°C (critical threshold)
- Backup system activation
- Product integrity assessment
- Recovery to specification within 2.5 hours

## Notes
Dataset represents typical pharmaceutical cold storage with planned access events and unplanned equipment failure. Demonstrates importance of redundant monitoring systems and rapid response protocols for maintaining product integrity.