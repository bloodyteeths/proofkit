#!/usr/bin/env python3
"""
ProofKit Metrics Export Script

Collects and exports daily metrics to CSV format for monitoring and analytics.
Appends daily metrics including visitors, uploads, processing results, and file sizes.

Usage:
    python scripts/metrics_export.py
    python scripts/metrics_export.py --date 2025-08-05
    python scripts/metrics_export.py --output custom_metrics.csv
"""

import os
import sys
import csv
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import glob
import subprocess

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
METRICS_FILE = BASE_DIR / "metrics.csv"
LOG_DIR = BASE_DIR / "logs"

# GA4 API configuration (if available)
GA4_PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID")
GA4_CREDENTIALS = os.environ.get("GA4_CREDENTIALS_PATH")


class MetricsCollector:
    """Collect and export ProofKit operational metrics."""
    
    def __init__(self, storage_dir: Path = STORAGE_DIR, metrics_file: Path = METRICS_FILE):
        self.storage_dir = storage_dir
        self.metrics_file = metrics_file
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        
    def get_ga4_visitors(self, date: str) -> Optional[int]:
        """
        Get visitor count from Google Analytics 4.
        
        Args:
            date: Date string in YYYY-MM-DD format
            
        Returns:
            Number of unique visitors or None if unavailable
        """
        if not GA4_PROPERTY_ID or not GA4_CREDENTIALS:
            logger.info("GA4 not configured, skipping visitor metrics")
            return None
            
        try:
            # Try to use Google Analytics Reporting API
            # This is a simplified implementation - in production you'd use the official client
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
            
            client = BetaAnalyticsDataClient.from_service_account_file(GA4_CREDENTIALS)
            
            request = RunReportRequest(
                property=f"properties/{GA4_PROPERTY_ID}",
                dimensions=[Dimension(name="date")],
                metrics=[Metric(name="totalUsers")],
                date_ranges=[DateRange(start_date=date, end_date=date)],
            )
            
            response = client.run_report(request)
            
            if response.rows:
                return int(response.rows[0].metric_values[0].value)
            else:
                return 0
                
        except ImportError:
            logger.warning("Google Analytics client not available")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch GA4 data: {e}")
            return None
    
    def analyze_storage_files(self, target_date: str) -> Dict[str, any]:
        """
        Analyze storage directory for daily metrics.
        
        Args:
            target_date: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with file analysis metrics
        """
        metrics = {
            'uploads': 0,
            'passes': 0,
            'fails': 0,
            'pdf_mb': 0.0,
            'zip_mb': 0.0,
            'total_files': 0
        }
        
        if not self.storage_dir.exists():
            logger.warning(f"Storage directory not found: {self.storage_dir}")
            return metrics
        
        # Parse target date
        try:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {target_date}")
            return metrics
        
        # Scan storage directory
        for item in self.storage_dir.rglob("*"):
            if not item.is_file():
                continue
                
            try:
                # Check file modification date
                file_date = datetime.fromtimestamp(item.stat().st_mtime).date()
                if file_date != target_dt:
                    continue
                
                metrics['total_files'] += 1
                file_size_mb = item.stat().st_size / (1024 * 1024)
                
                # Analyze by file type and content
                if item.name.endswith('.csv'):
                    metrics['uploads'] += 1
                elif item.name.endswith('.pdf'):
                    metrics['pdf_mb'] += file_size_mb
                elif item.name.endswith('.zip'):
                    metrics['zip_mb'] += file_size_mb
                    
                    # Try to determine pass/fail from decision.json in zip
                    try:
                        import zipfile
                        with zipfile.ZipFile(item, 'r') as zf:
                            if 'outputs/decision.json' in zf.namelist():
                                decision_data = json.loads(zf.read('outputs/decision.json'))
                                if decision_data.get('pass', False):
                                    metrics['passes'] += 1
                                else:
                                    metrics['fails'] += 1
                    except Exception:
                        # If we can't read the zip, don't crash
                        pass
                        
            except Exception as e:
                logger.debug(f"Error analyzing file {item}: {e}")
                continue
        
        # Round file sizes to 2 decimal places
        metrics['pdf_mb'] = round(metrics['pdf_mb'], 2)
        metrics['zip_mb'] = round(metrics['zip_mb'], 2)
        
        return metrics
    
    def check_application_logs(self, target_date: str) -> Dict[str, int]:
        """
        Parse application logs for additional metrics.
        
        Args:
            target_date: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with log-based metrics
        """
        metrics = {
            'api_requests': 0,
            'errors': 0,
            'compilation_success': 0,
            'compilation_failure': 0
        }
        
        if not LOG_DIR.exists():
            logger.debug("Log directory not found")
            return metrics
        
        # Look for log files from target date
        log_pattern = f"*{target_date}*.log"
        log_files = list(LOG_DIR.glob(log_pattern)) + list(LOG_DIR.glob("app.log"))
        
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if target_date not in line:
                            continue
                            
                        # Count API requests
                        if '"POST /' in line or '"GET /' in line:
                            metrics['api_requests'] += 1
                        
                        # Count errors
                        if 'ERROR' in line or 'error' in line.lower():
                            metrics['errors'] += 1
                        
                        # Count compilation results
                        if 'compilation success' in line.lower():
                            metrics['compilation_success'] += 1
                        elif 'compilation fail' in line.lower():
                            metrics['compilation_failure'] += 1
                            
            except Exception as e:
                logger.debug(f"Error reading log file {log_file}: {e}")
        
        return metrics
    
    def collect_system_metrics(self) -> Dict[str, any]:
        """
        Collect system-level metrics.
        
        Returns:
            Dictionary with system metrics
        """
        metrics = {
            'disk_usage_mb': 0.0,
            'storage_files': 0,
            'uptime_hours': 0.0
        }
        
        try:
            # Calculate storage directory size
            if self.storage_dir.exists():
                total_size = sum(f.stat().st_size for f in self.storage_dir.rglob('*') if f.is_file())
                metrics['disk_usage_mb'] = round(total_size / (1024 * 1024), 2)
                metrics['storage_files'] = len(list(self.storage_dir.rglob('*')))
        except Exception as e:
            logger.debug(f"Error calculating disk usage: {e}")
        
        try:
            # Get system uptime (Linux/Unix)
            result = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
            if result.returncode == 0:
                uptime_str = result.stdout.strip()
                # Parse uptime string (basic implementation)
                if 'day' in uptime_str:
                    days = int(uptime_str.split('day')[0].split()[-1])
                    metrics['uptime_hours'] = days * 24
                elif 'hour' in uptime_str:
                    hours = int(uptime_str.split('hour')[0].split()[-1])
                    metrics['uptime_hours'] = hours
        except Exception:
            # Uptime not critical, continue without it
            pass
        
        return metrics
    
    def export_daily_metrics(self, target_date: str = None) -> bool:
        """
        Export daily metrics to CSV file.
        
        Args:
            target_date: Date string in YYYY-MM-DD format (defaults to today)
            
        Returns:
            True if export successful, False otherwise
        """
        if target_date is None:
            target_date = self.date_str
        
        logger.info(f"Collecting metrics for {target_date}")
        
        # Collect all metrics
        visitors = self.get_ga4_visitors(target_date)
        storage_metrics = self.analyze_storage_files(target_date)
        log_metrics = self.check_application_logs(target_date)
        system_metrics = self.collect_system_metrics()
        
        # Prepare CSV row
        row = {
            'date': target_date,
            'visitors': visitors or 0,
            'uploads': storage_metrics['uploads'],
            'passes': storage_metrics['passes'],
            'fails': storage_metrics['fails'],
            'pdf_mb': storage_metrics['pdf_mb'],
            'zip_mb': storage_metrics['zip_mb'],
            'total_files': storage_metrics['total_files'],
            'api_requests': log_metrics['api_requests'],
            'errors': log_metrics['errors'],
            'disk_usage_mb': system_metrics['disk_usage_mb'],
            'storage_files': system_metrics['storage_files'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Write to CSV
        try:
            file_exists = self.metrics_file.exists()
            
            with open(self.metrics_file, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = list(row.keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Write header if file is new
                if not file_exists:
                    writer.writeheader()
                    logger.info(f"Created new metrics file: {self.metrics_file}")
                
                writer.writerow(row)
                logger.info(f"Exported metrics for {target_date}: {row}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return False
    
    def get_latest_metrics(self) -> Optional[Dict[str, any]]:
        """
        Get the most recent metrics from CSV file.
        
        Returns:
            Dictionary with latest metrics or None if unavailable
        """
        if not self.metrics_file.exists():
            return None
        
        try:
            with open(self.metrics_file, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                if rows:
                    return rows[-1]  # Return last row
        except Exception as e:
            logger.error(f"Failed to read metrics file: {e}")
        
        return None
    
    def cleanup_old_metrics(self, keep_days: int = 90):
        """
        Clean up old metrics entries.
        
        Args:
            keep_days: Number of days to retain
        """
        if not self.metrics_file.exists():
            return
        
        cutoff_date = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        
        try:
            # Read all metrics
            with open(self.metrics_file, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = [row for row in reader if row['date'] >= cutoff_date]
            
            # Write back filtered metrics
            if rows:
                with open(self.metrics_file, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = rows[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                
                logger.info(f"Cleaned up metrics older than {keep_days} days")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")


def main():
    """Main entry point for metrics export."""
    parser = argparse.ArgumentParser(description='Export ProofKit daily metrics')
    parser.add_argument('--date', help='Target date (YYYY-MM-DD), defaults to today')
    parser.add_argument('--output', help='Output CSV file path')
    parser.add_argument('--cleanup', type=int, help='Clean up metrics older than N days')
    parser.add_argument('--show-latest', action='store_true', help='Show latest metrics')
    
    args = parser.parse_args()
    
    # Configure output file
    metrics_file = Path(args.output) if args.output else METRICS_FILE
    
    # Initialize collector
    collector = MetricsCollector(metrics_file=metrics_file)
    
    try:
        if args.show_latest:
            latest = collector.get_latest_metrics()
            if latest:
                print("Latest metrics:")
                for key, value in latest.items():
                    print(f"  {key}: {value}")
            else:
                print("No metrics available")
                
        elif args.cleanup:
            collector.cleanup_old_metrics(args.cleanup)
            
        else:
            # Export daily metrics
            target_date = args.date
            success = collector.export_daily_metrics(target_date)
            
            if success:
                print(f"✅ Metrics exported successfully for {target_date or 'today'}")
                sys.exit(0)
            else:
                print("❌ Failed to export metrics")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\n⏸️  Export interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"💥 Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()