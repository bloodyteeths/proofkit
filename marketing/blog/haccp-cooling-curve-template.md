# 135-70-41 HACCP Cooling Curve Template + Auto-Checker

Food safety compliance demands precise temperature monitoring, especially during the critical cooling phase where bacterial growth risk peaks. The HACCP cooling curve requirement—from 135°F to 70°F within 2 hours, then 70°F to 41°F within 4 hours—is non-negotiable for restaurant inspections and food manufacturing audits. ProofKit automates this validation, converting your data logger CSV into inspector-ready certificates.

## Understanding the HACCP 135-70-41 Rule

The FDA Food Code mandates a two-stage cooling process designed to minimize time in the "danger zone" (41°F-135°F) where pathogens multiply rapidly:

**Stage 1**: 135°F to 70°F in maximum 2 hours
**Stage 2**: 70°F to 41°F in maximum 4 hours (cumulative 6 hours total)

This rule applies to:
- Cooked foods being cooled for storage
- Hot-held foods at end of service
- Batch-prepared items in commissary kitchens
- Institutional food service operations

Traditional monitoring involves manual temperature checks every 30 minutes and paper logs—time-consuming and error-prone during busy service periods.

## How ProofKit Validates HACCP Cooling Curves

ProofKit implements the exact FDA algorithms with precision timing:

1. **Stage detection**: Automatically identifies when food crosses 135°F threshold
2. **Two-phase validation**: Separately tracks 135°F→70°F and 70°F→41°F transitions
3. **Time calculations**: Measures actual cooling duration vs. regulatory limits
4. **Temperature verification**: Confirms final temperature reaches safe storage zone
5. **Gap analysis**: Detects sensor disconnections or data logging failures

The system accounts for sensor uncertainty (typically ±1°F for food thermometers) and uses conservative thresholds to ensure compliance even with measurement variations.

**Input format**: timestamp, food_temp_F (or Celsius with automatic conversion)
**Output**: FDA-compliant certificate with pass/fail determination and detailed timing analysis

## Real-World Scenario: Restaurant Soup Cooling

A restaurant prepares a large batch of soup that must be cooled according to HACCP guidelines. A wireless probe thermometer logs temperatures every 5 minutes during the cooling process.

**Challenge**: Manual verification requires calculating time differences, checking against dual thresholds, and creating documentation for health inspectors.

**ProofKit solution**: Upload the CSV, receive instant validation showing:
- Stage 1 duration: 1.8 hours (PASS - under 2-hour limit)
- Stage 2 duration: 3.2 hours (PASS - under 4-hour limit)
- Total cooling time: 5.0 hours (PASS - under 6-hour limit)
- Final temperature: 38°F (PASS - below 41°F requirement)

The certificate includes a temperature curve plot clearly marking the critical transition points and time boundaries.

<details>
<summary>Download Resources</summary>

- [Sample HACCP Cooling CSV](../csv-examples/haccp-cooling-curve-135-70-41.csv) - Compliant cooling example
- [FDA Food Code Spec](../spec-examples/haccp-cooling-fda-foodcode.json) - Standard requirements
- [Restaurant Spec Template](../spec-examples/haccp-cooling-restaurant.json) - High-volume service

</details>

## Industries Using HACCP Cooling Validation

- **Restaurants**: End-of-service cooling compliance for inspections
- **Food Manufacturing**: Batch cooling documentation for HACCP plans
- **Institutional Kitchens**: Schools, hospitals, and cafeterias
- **Catering**: Off-site food preparation and transport verification
- **Food Trucks**: Mobile operation compliance documentation

## Advanced Features for Food Service

ProofKit Pro includes features specifically designed for food service operations:

- **Batch processing**: Validate multiple cooling cycles simultaneously
- **Temperature unit conversion**: Automatic Fahrenheit/Celsius handling
- **Custom hold requirements**: Support for modified cooling protocols
- **Integration ready**: API endpoints for POS and kitchen management systems

## Getting Started

Ready to automate your HACCP cooling curve validation? [Upload your temperature log](../../web/templates/index.html) and get FDA-compliant documentation in seconds. Perfect for health department inspections, HACCP audits, and daily compliance monitoring.

*Keywords: haccp cooling curve, FDA food code, 135-70-41 rule, food safety compliance, temperature monitoring, restaurant inspection*