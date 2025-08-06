# ProofKit Production Monitoring Guide

This document provides production-ready monitoring configurations for ProofKit deployment on Fly.io.

## Overview

ProofKit monitoring covers:
- **Application health** via `/health` endpoint
- **Service availability** via BetterUptime probes
- **System metrics** via Grafana and OTLP
- **Alert management** via automated rules
- **Smoke testing** via GitHub Actions

## BetterUptime Configuration

### Probe Setup

Create monitors in BetterUptime dashboard using the following configurations:

#### 1. Main Health Check

```json
{
  "monitor": {
    "name": "ProofKit Health Check",
    "url": "https://proofkit-prod.fly.dev/health",
    "method": "GET",
    "check_frequency": 30,
    "request_timeout": 10,
    "request_headers": {
      "User-Agent": "BetterUptime/1.0"
    },
    "expected_status_codes": [200],
    "expected_body_regex": "\"status\":\\s*\"healthy\"",
    "regions": ["us", "eu"],
    "monitor_group_id": null,
    "pronounceable_name": "ProofKit Health",
    "recovery_period": 60,
    "confirmation_period": 30,
    "paused": false,
    "maintenance_from": null,
    "maintenance_to": null
  }
}
```

#### 2. API Compile Endpoint

```json
{
  "monitor": {
    "name": "ProofKit API Availability",
    "url": "https://proofkit-prod.fly.dev/api/presets",
    "method": "GET",
    "check_frequency": 300,
    "request_timeout": 15,
    "request_headers": {
      "User-Agent": "BetterUptime/1.0",
      "Accept": "application/json"
    },
    "expected_status_codes": [200],
    "expected_body_regex": "\"powder\":",
    "regions": ["us", "eu"],
    "monitor_group_id": null,
    "pronounceable_name": "ProofKit API",
    "recovery_period": 180,
    "confirmation_period": 60,
    "paused": false
  }
}
```

#### 3. Application Performance

```json
{
  "monitor": {
    "name": "ProofKit Performance",
    "url": "https://proofkit-prod.fly.dev/",
    "method": "GET",
    "check_frequency": 600,
    "request_timeout": 30,
    "request_headers": {
      "User-Agent": "BetterUptime/1.0"
    },
    "expected_status_codes": [200],
    "response_time_threshold": 5000,
    "regions": ["us"],
    "monitor_group_id": null,
    "pronounceable_name": "ProofKit Performance",
    "recovery_period": 300,
    "confirmation_period": 120,
    "paused": false
  }
}
```

### Alert Configuration

```json
{
  "policy": {
    "name": "ProofKit Production Alerts",
    "repeat_call_times": [0, 5, 15, 30],
    "team_wait": 180,
    "recovery_period": 0,
    "escalation_policy": {
      "escalation_rules": [
        {
          "escalation_timeout": 0,
          "targets": [
            {
              "type": "email",
              "email_address": "ops@proofkit.com"
            }
          ]
        },
        {
          "escalation_timeout": 5,
          "targets": [
            {
              "type": "sms",
              "phone_number": "+1234567890"
            }
          ]
        }
      ]
    }
  }
}
```

## Grafana OTLP Configuration

### Dashboard Configuration

ProofKit exports metrics via OpenTelemetry. Configure Grafana to collect these metrics:

#### Data Source Configuration

```yaml
apiVersion: 1
datasources:
  - name: ProofKit OTLP
    type: prometheus
    access: proxy
    url: http://fly-prometheus:9090
    isDefault: false
    editable: true
    jsonData:
      timeInterval: "30s"
      httpMethod: "POST"
    secureJsonData: {}
```

#### Application Metrics Dashboard

```json
{
  "dashboard": {
    "title": "ProofKit Application Metrics",
    "tags": ["proofkit", "production"],
    "timezone": "UTC",
    "refresh": "30s",
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total{app=\"proofkit\"}[5m])",
            "legendFormat": "{{method}} {{status_code}}"
          }
        ],
        "yAxes": [
          {
            "label": "Requests/sec",
            "min": 0
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{app=\"proofkit\"}[5m]))",
            "legendFormat": "95th percentile"
          },
          {
            "expr": "histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{app=\"proofkit\"}[5m]))",
            "legendFormat": "50th percentile"
          }
        ],
        "yAxes": [
          {
            "label": "Seconds",
            "min": 0
          }
        ]
      },
      {
        "title": "Error Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total{app=\"proofkit\",status_code=~\"4..|5..\"}[5m]) / rate(http_requests_total{app=\"proofkit\"}[5m])",
            "legendFormat": "Error Rate"
          }
        ],
        "yAxes": [
          {
            "label": "Error Rate",
            "min": 0,
            "max": 1
          }
        ]
      },
      {
        "title": "Memory Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "process_resident_memory_bytes{app=\"proofkit\"}",
            "legendFormat": "Memory Usage"
          }
        ],
        "yAxes": [
          {
            "label": "Bytes"
          }
        ]
      }
    ]
  }
}
```

### OTLP Exporter Configuration

Add to `fly.toml` or environment configuration:

```toml
[env]
  # OpenTelemetry configuration
  OTEL_EXPORTER_OTLP_ENDPOINT = "https://fly-otel-collector:4317"
  OTEL_EXPORTER_OTLP_PROTOCOL = "grpc"
  OTEL_SERVICE_NAME = "proofkit"
  OTEL_RESOURCE_ATTRIBUTES = "service.name=proofkit,service.version=0.1.0,deployment.environment=production"
```

## Alert Rules Configuration

### Prometheus Alert Rules

```yaml
groups:
  - name: proofkit.rules
    rules:
      # High error rate alert
      - alert: ProofKitHighErrorRate
        expr: (rate(http_requests_total{app="proofkit",status_code=~"5.."}[5m]) / rate(http_requests_total{app="proofkit"}[5m])) > 0.05
        for: 2m
        labels:
          severity: critical
          service: proofkit
        annotations:
          summary: "ProofKit has high error rate"
          description: "ProofKit error rate is {{ $value | humanizePercentage }} for the last 5 minutes"

      # High response time alert
      - alert: ProofKitHighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{app="proofkit"}[5m])) > 5
        for: 3m
        labels:
          severity: warning
          service: proofkit
        annotations:
          summary: "ProofKit has high response time"
          description: "ProofKit 95th percentile response time is {{ $value }}s"

      # Service down alert
      - alert: ProofKitDown
        expr: up{app="proofkit"} == 0
        for: 1m
        labels:
          severity: critical
          service: proofkit
        annotations:
          summary: "ProofKit service is down"
          description: "ProofKit has been down for more than 1 minute"

      # High memory usage alert
      - alert: ProofKitHighMemory
        expr: (process_resident_memory_bytes{app="proofkit"} / (1024 * 1024 * 1024)) > 0.4
        for: 5m
        labels:
          severity: warning
          service: proofkit
        annotations:
          summary: "ProofKit high memory usage"
          description: "ProofKit memory usage is {{ $value | humanize }}GB"

      # Low disk space alert
      - alert: ProofKitLowDiskSpace
        expr: (1 - (node_filesystem_free_bytes{mountpoint="/app/storage"} / node_filesystem_size_bytes{mountpoint="/app/storage"})) > 0.85
        for: 5m
        labels:
          severity: warning
          service: proofkit
        annotations:
          summary: "ProofKit low disk space"
          description: "ProofKit storage volume is {{ $value | humanizePercentage }} full"

      # Rate limiting alert
      - alert: ProofKitRateLimitHit
        expr: increase(rate_limit_exceeded_total{app="proofkit"}[1h]) > 10
        for: 0m
        labels:
          severity: info
          service: proofkit
        annotations:
          summary: "ProofKit rate limiting active"
          description: "ProofKit has hit rate limits {{ $value }} times in the last hour"
```

### AlertManager Configuration

```yaml
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@proofkit.com'

route:
  group_by: ['alertname']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  receiver: 'proofkit-ops'

receivers:
  - name: 'proofkit-ops'
    email_configs:
      - to: 'ops@proofkit.com'
        subject: '[ProofKit] {{ .GroupLabels.alertname }}'
        body: |
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          Instance: {{ .Labels.instance }}
          Severity: {{ .Labels.severity }}
          Time: {{ .StartsAt }}
          {{ end }}

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'service']
```

## Health Check Endpoints

ProofKit provides several endpoints for monitoring:

### Primary Health Check

- **URL**: `/health`
- **Method**: `GET`
- **Response**: JSON with status information
- **Expected**: `{"status": "healthy", "service": "proofkit", "version": "0.1.0"}`
- **Timeout**: 10 seconds

### API Readiness Check

- **URL**: `/api/presets`
- **Method**: `GET`
- **Response**: JSON with available presets
- **Expected**: Contains industry presets
- **Timeout**: 15 seconds

### Application Availability

- **URL**: `/`
- **Method**: `GET`
- **Response**: HTML marketing page
- **Expected**: 200 status code
- **Timeout**: 30 seconds

## Monitoring Best Practices

### Alert Thresholds

1. **Error Rate**: Alert when > 5% for 2+ minutes
2. **Response Time**: Alert when 95th percentile > 5 seconds for 3+ minutes
3. **Service Availability**: Alert immediately when service is down
4. **Memory Usage**: Alert when > 400MB for 5+ minutes
5. **Disk Space**: Alert when > 85% full

### Escalation Policy

1. **Immediate**: Email to ops team
2. **5 minutes**: SMS to on-call engineer
3. **15 minutes**: Call to primary engineer
4. **30 minutes**: Call to engineering manager

### Monitoring Intervals

- **Health checks**: Every 30 seconds
- **API availability**: Every 5 minutes
- **Performance checks**: Every 10 minutes
- **System metrics**: Every 15 seconds

### Data Retention

- **Metrics**: 30 days high resolution, 1 year downsampled
- **Logs**: 7 days for debugging, 30 days for compliance
- **Alerts**: 90 days for analysis

## Troubleshooting

### Common Issues

1. **False Positives**: Adjust thresholds based on baseline performance
2. **Alert Fatigue**: Group related alerts and set appropriate severity levels
3. **Missing Metrics**: Verify OTLP configuration and network connectivity
4. **High Response Times**: Check Fly.io region performance and scaling

### Debug Commands

```bash
# Check application health
curl -s https://proofkit-prod.fly.dev/health | jq

# Test API endpoints
curl -s https://proofkit-prod.fly.dev/api/presets | jq keys

# View Fly.io logs
flyctl logs --app proofkit-prod

# Check scaling status
flyctl scale show --app proofkit-prod

# View volume usage
flyctl volumes list --app proofkit-prod
```

## Implementation Checklist

- [ ] Configure BetterUptime monitors
- [ ] Set up Grafana dashboards
- [ ] Deploy Prometheus alert rules
- [ ] Configure AlertManager notifications
- [ ] Test all alert thresholds
- [ ] Implement smoke testing pipeline
- [ ] Document runbook procedures
- [ ] Set up on-call rotation

## Contact Information

- **Operations Team**: ops@proofkit.com
- **Engineering Team**: dev@proofkit.com
- **Escalation**: +1-555-PROOFKIT

---

*This monitoring configuration ensures comprehensive coverage of ProofKit production environment with appropriate alerting and escalation procedures.*