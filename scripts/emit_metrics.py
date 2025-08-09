#!/usr/bin/env python3
"""
ProofKit Metrics Emission Script

Emits operational metrics for monitoring the three core metrics that matter:
- p95 compile time > 5s for 10m
- 5xx error rate > 1% for 5m  
- bundle_verify_error > 0.5% for 10m

This script is idempotent and can be run safely multiple times.

Usage:
    python scripts/emit_metrics.py
    python scripts/emit_metrics.py --format prometheus
    python scripts/emit_metrics.py --output /tmp/metrics.txt
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging
import subprocess
import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging import setup_logging, get_logger
from core.metrics import MetricsCollector, CompileMetric, ErrorMetric, BundleVerifyMetric

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent
METRICS_OUTPUT = BASE_DIR / "metrics.txt"
METRICS_JSON = BASE_DIR / "metrics.json"

# Environment variables
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
PROMETHEUS_PUSHGATEWAY = os.environ.get("PROMETHEUS_PUSHGATEWAY", "")
GRAFANA_API_KEY = os.environ.get("GRAFANA_API_KEY", "")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")

# Setup logging
setup_logging(level="INFO")
logger = get_logger(__name__)


class MetricsEmitter:
    """
    Emits operational metrics for ProofKit monitoring.
    
    Focuses on the three critical metrics:
    1. p95 compile time threshold monitoring
    2. 5xx error rate monitoring  
    3. bundle verification error rate monitoring
    """
    
    def __init__(self, metrics_file: Path = METRICS_OUTPUT):
        """
        Initialize metrics emitter.
        
        Args:
            metrics_file: Path to metrics output file
        """
        self.metrics_file = metrics_file
        self.collector = MetricsCollector()
        self.timestamp = datetime.now(timezone.utc)
        
    def collect_compile_metrics(self, window_minutes: int = 10) -> CompileMetric:
        """
        Collect compilation time metrics for p95 monitoring.
        
        Args:
            window_minutes: Time window to analyze
            
        Returns:
            CompileMetric with p95, average, count, and threshold breach info
        """
        logger.info(f"Collecting compile metrics for {window_minutes}m window")
        
        # Get compilation times from the last window_minutes
        start_time = self.timestamp - timedelta(minutes=window_minutes)
        compile_times = self.collector.get_compile_times(start_time)
        
        if not compile_times:
            logger.warning("No compile times found in window")
            return CompileMetric(
                p95_seconds=0.0,
                avg_seconds=0.0,
                count=0,
                breached_threshold=False,
                window_minutes=window_minutes
            )
        
        # Calculate p95
        sorted_times = sorted(compile_times)
        p95_index = int(0.95 * len(sorted_times))
        p95_time = sorted_times[p95_index] if sorted_times else 0.0
        avg_time = sum(compile_times) / len(compile_times)
        
        # Check if p95 > 5s threshold is breached
        threshold_breached = p95_time > 5.0
        
        metric = CompileMetric(
            p95_seconds=round(p95_time, 2),
            avg_seconds=round(avg_time, 2),
            count=len(compile_times),
            breached_threshold=threshold_breached,
            window_minutes=window_minutes
        )
        
        logger.info(f"Compile metrics: p95={metric.p95_seconds}s, count={metric.count}, breached={metric.breached_threshold}")
        return metric
    
    def collect_error_metrics(self, window_minutes: int = 5) -> ErrorMetric:
        """
        Collect 5xx error rate metrics.
        
        Args:
            window_minutes: Time window to analyze
            
        Returns:
            ErrorMetric with error rate, counts, and threshold breach info
        """
        logger.info(f"Collecting error metrics for {window_minutes}m window")
        
        # Get request counts from the last window_minutes
        start_time = self.timestamp - timedelta(minutes=window_minutes)
        total_requests, error_5xx_count = self.collector.get_request_counts(start_time)
        
        if total_requests == 0:
            logger.warning("No requests found in window")
            return ErrorMetric(
                error_rate_percent=0.0,
                error_count=0,
                total_requests=0,
                breached_threshold=False,
                window_minutes=window_minutes
            )
        
        # Calculate 5xx error rate
        error_rate = (error_5xx_count / total_requests) * 100
        threshold_breached = error_rate > 1.0  # 1% threshold
        
        metric = ErrorMetric(
            error_rate_percent=round(error_rate, 2),
            error_count=error_5xx_count,
            total_requests=total_requests,
            breached_threshold=threshold_breached,
            window_minutes=window_minutes
        )
        
        logger.info(f"Error metrics: rate={metric.error_rate_percent}%, errors={metric.error_count}/{metric.total_requests}, breached={metric.breached_threshold}")
        return metric
    
    def collect_bundle_verify_metrics(self, window_minutes: int = 10) -> BundleVerifyMetric:
        """
        Collect bundle verification error metrics.
        
        Args:
            window_minutes: Time window to analyze
            
        Returns:
            BundleVerifyMetric with error rate and threshold breach info
        """
        logger.info(f"Collecting bundle verify metrics for {window_minutes}m window")
        
        # Get bundle verification stats from the last window_minutes
        start_time = self.timestamp - timedelta(minutes=window_minutes)
        total_verifications, verify_errors = self.collector.get_bundle_verify_stats(start_time)
        
        if total_verifications == 0:
            logger.warning("No bundle verifications found in window")
            return BundleVerifyMetric(
                error_rate_percent=0.0,
                error_count=0,
                total_verifications=0,
                breached_threshold=False,
                window_minutes=window_minutes
            )
        
        # Calculate bundle verify error rate
        error_rate = (verify_errors / total_verifications) * 100
        threshold_breached = error_rate > 0.5  # 0.5% threshold
        
        metric = BundleVerifyMetric(
            error_rate_percent=round(error_rate, 2),
            error_count=verify_errors,
            total_verifications=total_verifications,
            breached_threshold=threshold_breached,
            window_minutes=window_minutes
        )
        
        logger.info(f"Bundle verify metrics: rate={metric.error_rate_percent}%, errors={metric.error_count}/{metric.total_verifications}, breached={metric.breached_threshold}")
        return metric
    
    def emit_prometheus_format(self, compile_metric: CompileMetric, error_metric: ErrorMetric, bundle_metric: BundleVerifyMetric) -> str:
        """
        Format metrics in Prometheus exposition format.
        
        Args:
            compile_metric: Compilation time metrics
            error_metric: 5xx error rate metrics
            bundle_metric: Bundle verification metrics
            
        Returns:
            Prometheus format metrics string
        """
        lines = []
        timestamp_ms = int(self.timestamp.timestamp() * 1000)
        
        # Compile time metrics
        lines.append(f'# HELP proofkit_compile_p95_seconds P95 compilation time in seconds')
        lines.append(f'# TYPE proofkit_compile_p95_seconds gauge')
        lines.append(f'proofkit_compile_p95_seconds{{environment="{ENVIRONMENT}"}} {compile_metric.p95_seconds} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_compile_avg_seconds Average compilation time in seconds')
        lines.append(f'# TYPE proofkit_compile_avg_seconds gauge')
        lines.append(f'proofkit_compile_avg_seconds{{environment="{ENVIRONMENT}"}} {compile_metric.avg_seconds} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_compile_count Total compilations in window')
        lines.append(f'# TYPE proofkit_compile_count gauge')
        lines.append(f'proofkit_compile_count{{environment="{ENVIRONMENT}"}} {compile_metric.count} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_compile_threshold_breached Compile time threshold breached (1=yes, 0=no)')
        lines.append(f'# TYPE proofkit_compile_threshold_breached gauge')
        lines.append(f'proofkit_compile_threshold_breached{{environment="{ENVIRONMENT}"}} {int(compile_metric.breached_threshold)} {timestamp_ms}')
        
        # Error rate metrics
        lines.append(f'# HELP proofkit_error_5xx_rate_percent 5xx error rate percentage')
        lines.append(f'# TYPE proofkit_error_5xx_rate_percent gauge')
        lines.append(f'proofkit_error_5xx_rate_percent{{environment="{ENVIRONMENT}"}} {error_metric.error_rate_percent} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_error_5xx_count Count of 5xx errors')
        lines.append(f'# TYPE proofkit_error_5xx_count gauge')
        lines.append(f'proofkit_error_5xx_count{{environment="{ENVIRONMENT}"}} {error_metric.error_count} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_requests_total Total requests in window')
        lines.append(f'# TYPE proofkit_requests_total gauge')
        lines.append(f'proofkit_requests_total{{environment="{ENVIRONMENT}"}} {error_metric.total_requests} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_error_threshold_breached 5xx error threshold breached (1=yes, 0=no)')
        lines.append(f'# TYPE proofkit_error_threshold_breached gauge')
        lines.append(f'proofkit_error_threshold_breached{{environment="{ENVIRONMENT}"}} {int(error_metric.breached_threshold)} {timestamp_ms}')
        
        # Bundle verify metrics
        lines.append(f'# HELP proofkit_bundle_verify_error_rate_percent Bundle verification error rate percentage')
        lines.append(f'# TYPE proofkit_bundle_verify_error_rate_percent gauge')
        lines.append(f'proofkit_bundle_verify_error_rate_percent{{environment="{ENVIRONMENT}"}} {bundle_metric.error_rate_percent} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_bundle_verify_error_count Bundle verification error count')
        lines.append(f'# TYPE proofkit_bundle_verify_error_count gauge')
        lines.append(f'proofkit_bundle_verify_error_count{{environment="{ENVIRONMENT}"}} {bundle_metric.error_count} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_bundle_verify_total Total bundle verifications')
        lines.append(f'# TYPE proofkit_bundle_verify_total gauge')
        lines.append(f'proofkit_bundle_verify_total{{environment="{ENVIRONMENT}"}} {bundle_metric.total_verifications} {timestamp_ms}')
        
        lines.append(f'# HELP proofkit_bundle_verify_threshold_breached Bundle verify error threshold breached (1=yes, 0=no)')
        lines.append(f'# TYPE proofkit_bundle_verify_threshold_breached gauge')
        lines.append(f'proofkit_bundle_verify_threshold_breached{{environment="{ENVIRONMENT}"}} {int(bundle_metric.breached_threshold)} {timestamp_ms}')
        
        return '\n'.join(lines) + '\n'
    
    def emit_json_format(self, compile_metric: CompileMetric, error_metric: ErrorMetric, bundle_metric: BundleVerifyMetric) -> str:
        """
        Format metrics in JSON format.
        
        Args:
            compile_metric: Compilation time metrics
            error_metric: 5xx error rate metrics
            bundle_metric: Bundle verification metrics
            
        Returns:
            JSON format metrics string
        """
        metrics = {
            "timestamp": self.timestamp.isoformat(),
            "environment": ENVIRONMENT,
            "compile": {
                "p95_seconds": compile_metric.p95_seconds,
                "avg_seconds": compile_metric.avg_seconds,
                "count": compile_metric.count,
                "threshold_breached": compile_metric.breached_threshold,
                "window_minutes": compile_metric.window_minutes
            },
            "error_5xx": {
                "rate_percent": error_metric.error_rate_percent,
                "error_count": error_metric.error_count,
                "total_requests": error_metric.total_requests,
                "threshold_breached": error_metric.breached_threshold,
                "window_minutes": error_metric.window_minutes
            },
            "bundle_verify": {
                "error_rate_percent": bundle_metric.error_rate_percent,
                "error_count": bundle_metric.error_count,
                "total_verifications": bundle_metric.total_verifications,
                "threshold_breached": bundle_metric.breached_threshold,
                "window_minutes": bundle_metric.window_minutes
            }
        }
        
        return json.dumps(metrics, indent=2)
    
    def push_to_prometheus(self, metrics_text: str, job_name: str = "proofkit") -> bool:
        """
        Push metrics to Prometheus Pushgateway.
        
        Args:
            metrics_text: Prometheus format metrics
            job_name: Job name for Pushgateway
            
        Returns:
            True if successful, False otherwise
        """
        if not PROMETHEUS_PUSHGATEWAY:
            logger.info("No Prometheus Pushgateway configured, skipping push")
            return True
        
        try:
            url = f"{PROMETHEUS_PUSHGATEWAY}/metrics/job/{job_name}/instance/{ENVIRONMENT}"
            
            response = requests.post(
                url,
                data=metrics_text,
                headers={"Content-Type": "text/plain"},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully pushed metrics to Prometheus Pushgateway")
                return True
            else:
                logger.error(f"Failed to push metrics to Pushgateway: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error pushing to Prometheus Pushgateway: {e}")
            return False
    
    def send_to_otlp(self, compile_metric: CompileMetric, error_metric: ErrorMetric, bundle_metric: BundleVerifyMetric) -> bool:
        """
        Send metrics to OpenTelemetry OTLP endpoint.
        
        Args:
            compile_metric: Compilation time metrics
            error_metric: 5xx error rate metrics
            bundle_metric: Bundle verification metrics
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # This would normally use the OpenTelemetry SDK
            # For now, just log that we would send to OTLP
            logger.info(f"Would send metrics to OTLP endpoint: {OTLP_ENDPOINT}")
            logger.info(f"Compile p95: {compile_metric.p95_seconds}s, Error rate: {error_metric.error_rate_percent}%, Bundle errors: {bundle_metric.error_rate_percent}%")
            return True
        except Exception as e:
            logger.error(f"Error sending to OTLP: {e}")
            return False
    
    def emit_metrics(self, output_format: str = "prometheus", output_file: Optional[Path] = None) -> bool:
        """
        Main method to collect and emit all metrics.
        
        Args:
            output_format: Format for metrics output ("prometheus" or "json")
            output_file: Optional file path for output
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Starting metrics emission in {output_format} format")
        
        try:
            # Collect all three critical metrics
            compile_metric = self.collect_compile_metrics(window_minutes=10)
            error_metric = self.collect_error_metrics(window_minutes=5)
            bundle_metric = self.collect_bundle_verify_metrics(window_minutes=10)
            
            # Format metrics
            if output_format.lower() == "json":
                formatted_metrics = self.emit_json_format(compile_metric, error_metric, bundle_metric)
                output_file = output_file or METRICS_JSON
            else:  # prometheus
                formatted_metrics = self.emit_prometheus_format(compile_metric, error_metric, bundle_metric)
                output_file = output_file or self.metrics_file
            
            # Write to file
            output_file.write_text(formatted_metrics, encoding='utf-8')
            logger.info(f"Metrics written to {output_file}")
            
            # Push to external systems
            success = True
            
            if output_format.lower() == "prometheus":
                success &= self.push_to_prometheus(formatted_metrics)
            
            success &= self.send_to_otlp(compile_metric, error_metric, bundle_metric)
            
            # Log any threshold breaches for alerting
            if compile_metric.breached_threshold:
                logger.warning(f"ALERT: P95 compile time threshold breached: {compile_metric.p95_seconds}s > 5s")
            
            if error_metric.breached_threshold:
                logger.warning(f"ALERT: 5xx error rate threshold breached: {error_metric.error_rate_percent}% > 1%")
            
            if bundle_metric.breached_threshold:
                logger.warning(f"ALERT: Bundle verify error threshold breached: {bundle_metric.error_rate_percent}% > 0.5%")
            
            logger.info("Metrics emission completed successfully")
            return success
            
        except Exception as e:
            logger.error(f"Failed to emit metrics: {e}", exc_info=True)
            return False
    
    def get_current_status(self) -> Dict[str, Any]:
        """
        Get current status summary of all metrics.
        
        Returns:
            Dictionary with current metric status
        """
        try:
            compile_metric = self.collect_compile_metrics(window_minutes=10)
            error_metric = self.collect_error_metrics(window_minutes=5)
            bundle_metric = self.collect_bundle_verify_metrics(window_minutes=10)
            
            return {
                "timestamp": self.timestamp.isoformat(),
                "healthy": not (compile_metric.breached_threshold or error_metric.breached_threshold or bundle_metric.breached_threshold),
                "compile": {
                    "p95_seconds": compile_metric.p95_seconds,
                    "threshold_5s_breached": compile_metric.breached_threshold,
                    "count": compile_metric.count
                },
                "errors": {
                    "rate_percent": error_metric.error_rate_percent,
                    "threshold_1pct_breached": error_metric.breached_threshold,
                    "total_requests": error_metric.total_requests
                },
                "bundle_verify": {
                    "error_rate_percent": bundle_metric.error_rate_percent,
                    "threshold_0_5pct_breached": bundle_metric.breached_threshold,
                    "total_verifications": bundle_metric.total_verifications
                }
            }
        except Exception as e:
            logger.error(f"Error getting current status: {e}")
            return {
                "timestamp": self.timestamp.isoformat(),
                "healthy": False,
                "error": str(e)
            }


def main():
    """Main entry point for metrics emission."""
    parser = argparse.ArgumentParser(description='Emit ProofKit operational metrics')
    parser.add_argument('--format', choices=['prometheus', 'json'], default='prometheus',
                        help='Output format for metrics')
    parser.add_argument('--output', type=Path, help='Output file path')
    parser.add_argument('--status', action='store_true', help='Show current status only')
    parser.add_argument('--no-push', action='store_true', help='Skip pushing to external systems')
    
    args = parser.parse_args()
    
    try:
        emitter = MetricsEmitter()
        
        if args.status:
            # Show current status
            status = emitter.get_current_status()
            print(json.dumps(status, indent=2))
            
            # Exit with error code if not healthy
            if not status.get('healthy', False):
                sys.exit(1)
        else:
            # Emit metrics
            success = emitter.emit_metrics(
                output_format=args.format,
                output_file=args.output
            )
            
            if success:
                print(f"✅ Metrics emitted successfully in {args.format} format")
                sys.exit(0)
            else:
                print("❌ Failed to emit metrics")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\n⏸️  Metrics emission interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"💥 Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()