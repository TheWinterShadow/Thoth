#!/usr/bin/env python3
"""Cloud Run log analyzer for thoth-ingestion-worker.

A CLI tool to fetch and analyze logs from Cloud Logging, identifying
common issues like liveness probe failures, 503 errors, and application errors.

Usage:
    python scripts/analyze_logs.py --help
    python scripts/analyze_logs.py --minutes 10
    python scripts/analyze_logs.py --minutes 30 --severity ERROR
    python scripts/analyze_logs.py --job-id <uuid>
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import re
import subprocess
import sys


@dataclass
class LogEntry:
    """Parsed log entry."""

    timestamp: datetime
    severity: str
    message: str
    text_payload: str
    http_status: int | None = None
    http_path: str | None = None
    http_latency: float | None = None
    trace_id: str | None = None
    job_id: str | None = None


@dataclass
class AnalysisResult:
    """Log analysis results."""

    total_entries: int = 0
    severity_counts: Counter = field(default_factory=Counter)
    error_categories: Counter = field(default_factory=Counter)
    http_status_counts: Counter = field(default_factory=Counter)
    failed_endpoints: Counter = field(default_factory=Counter)
    liveness_failures: int = 0
    connection_errors: int = 0
    firestore_errors: int = 0
    application_errors: list = field(default_factory=list)
    job_errors: dict = field(default_factory=lambda: defaultdict(list))
    timeline: list = field(default_factory=list)


def run_gcloud_logging(
    project: str,
    service: str,
    minutes: int,
    severity: str | None = None,
    job_id: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Fetch logs using gcloud CLI."""
    # Build filter
    filters = [
        'resource.type="cloud_run_revision"',
        f'resource.labels.service_name="{service}"',
    ]

    if severity:
        filters.append(f"severity>={severity}")

    if job_id:
        filters.append(f'jsonPayload.job_id="{job_id}"')

    filter_str = " AND ".join(filters)

    cmd = [
        "gcloud",
        "logging",
        "read",
        filter_str,
        f"--project={project}",
        f"--limit={limit}",
        f"--freshness={minutes}m",
        "--format=json",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else []
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(1)


def parse_log_entry(raw: dict) -> LogEntry:
    """Parse a raw log entry into a LogEntry object."""
    timestamp_str = raw.get("timestamp", "")
    try:
        # Parse ISO format timestamp
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        timestamp = datetime.now(UTC)

    severity = raw.get("severity", "DEFAULT")

    # Get message from jsonPayload or textPayload
    json_payload = raw.get("jsonPayload", {})
    message = json_payload.get("message", "")
    text_payload = raw.get("textPayload", "")

    # Extract HTTP request info
    http_request = raw.get("httpRequest", {})
    http_status = http_request.get("status")
    http_path = http_request.get("requestUrl", "")
    if http_path:
        # Extract just the path
        match = re.search(r"run\.app(/[^?]*)", http_path)
        if match:
            http_path = match.group(1)

    # Parse latency
    latency_str = http_request.get("latency", "")
    http_latency = None
    if latency_str:
        match = re.match(r"([\d.]+)s", latency_str)
        if match:
            http_latency = float(match.group(1))

    # Extract trace ID
    trace = raw.get("trace", "")
    trace_id = trace.split("/")[-1] if trace else None

    # Extract job_id from jsonPayload
    job_id = json_payload.get("job_id")

    return LogEntry(
        timestamp=timestamp,
        severity=severity,
        message=message,
        text_payload=text_payload,
        http_status=http_status,
        http_path=http_path,
        http_latency=http_latency,
        trace_id=trace_id,
        job_id=job_id,
    )


def categorize_error(entry: LogEntry) -> str | None:
    """Categorize an error log entry."""
    text = entry.text_payload or entry.message

    if "LIVENESS HTTP probe failed" in text:
        return "liveness_probe_failure"
    if "connection to the instance had an error" in text:
        return "connection_error"
    if "The query requires an index" in text:
        return "firestore_missing_index"
    if "Table" in text and "already exists" in text:
        return "lancedb_table_exists"
    if "Failed to process batch" in text:
        return "batch_processing_failed"
    if "Failed to get job status" in text:
        return "job_status_failed"
    if entry.http_status and entry.http_status >= 500:
        return f"http_{entry.http_status}"
    if entry.severity in ("ERROR", "CRITICAL"):
        return "application_error"

    return None


def analyze_logs(entries: list[LogEntry]) -> AnalysisResult:
    """Analyze parsed log entries."""
    result = AnalysisResult()
    result.total_entries = len(entries)

    for entry in entries:
        # Count by severity
        result.severity_counts[entry.severity] += 1

        # Count HTTP status codes
        if entry.http_status:
            result.http_status_counts[entry.http_status] += 1
            if entry.http_status >= 400 and entry.http_path:
                result.failed_endpoints[entry.http_path] += 1

        # Categorize errors
        if entry.severity in ("ERROR", "CRITICAL", "WARNING"):
            category = categorize_error(entry)
            if category:
                result.error_categories[category] += 1

                if category == "liveness_probe_failure":
                    result.liveness_failures += 1
                elif category == "connection_error":
                    result.connection_errors += 1
                elif category == "firestore_missing_index":
                    result.firestore_errors += 1

                # Track application errors with details
                if category == "application_error":
                    result.application_errors.append(
                        {
                            "timestamp": entry.timestamp.isoformat(),
                            "message": entry.message or entry.text_payload,
                            "job_id": entry.job_id,
                        }
                    )

                # Group errors by job_id
                if entry.job_id:
                    result.job_errors[entry.job_id].append(
                        {
                            "timestamp": entry.timestamp.isoformat(),
                            "category": category,
                            "message": entry.message or entry.text_payload[:100],
                        }
                    )

        # Build timeline of significant events
        if entry.severity in ("ERROR", "CRITICAL"):
            result.timeline.append(
                {
                    "timestamp": entry.timestamp.isoformat(),
                    "severity": entry.severity,
                    "summary": (entry.message or entry.text_payload)[:80],
                }
            )

    # Sort timeline by timestamp
    result.timeline.sort(key=lambda x: x["timestamp"])

    return result


def print_report(result: AnalysisResult, verbose: bool = False) -> None:
    """Print analysis report."""
    print("=" * 70)
    print("THOTH INGESTION WORKER - LOG ANALYSIS REPORT")
    print("=" * 70)
    print()

    # Summary
    print(f"Total log entries analyzed: {result.total_entries}")
    print()

    # Severity breakdown
    print("SEVERITY BREAKDOWN:")
    print("-" * 40)
    for severity, count in result.severity_counts.most_common():
        pct = (count / result.total_entries * 100) if result.total_entries else 0
        bar = "#" * min(int(pct / 2), 30)
        print(f"  {severity:12} {count:5}  ({pct:5.1f}%)  {bar}")
    print()

    # Error categories
    if result.error_categories:
        print("ERROR CATEGORIES:")
        print("-" * 40)
        for category, count in result.error_categories.most_common():
            print(f"  {category:30} {count:5}")
        print()

    # Key metrics
    print("KEY ISSUES DETECTED:")
    print("-" * 40)

    issues_found = False

    if result.liveness_failures > 0:
        issues_found = True
        print(f"  [CRITICAL] Liveness probe failures: {result.liveness_failures}")
        print("             -> Instances being killed due to unresponsive health checks")
        print("             -> Consider: increase timeout, disable CPU throttling")
        print()

    if result.connection_errors > 0:
        issues_found = True
        print(f"  [ERROR] Connection errors: {result.connection_errors}")
        print("          -> Requests failing due to instance termination")
        print()

    if result.firestore_errors > 0:
        issues_found = True
        print(f"  [ERROR] Firestore index errors: {result.firestore_errors}")
        print("          -> Missing composite index for query")
        print("          -> Run: terraform apply (firestore.tf updated)")
        print()

    if result.http_status_counts.get(503, 0) > 0:
        issues_found = True
        print(f"  [ERROR] HTTP 503 errors: {result.http_status_counts[503]}")
        print("          -> Service unavailable, likely from instance crashes")
        print()

    if not issues_found:
        print("  No critical issues detected.")
    print()

    # Failed endpoints
    if result.failed_endpoints:
        print("FAILED ENDPOINTS:")
        print("-" * 40)
        for endpoint, count in result.failed_endpoints.most_common(10):
            print(f"  {endpoint:40} {count:5} failures")
        print()

    # HTTP status codes
    if result.http_status_counts:
        print("HTTP STATUS CODES:")
        print("-" * 40)
        for status, count in sorted(result.http_status_counts.items()):
            status_type = "OK" if status < 400 else "ERROR"
            print(f"  {status} ({status_type}): {count}")
        print()

    # Job-specific errors
    if result.job_errors and verbose:
        print("ERRORS BY JOB ID:")
        print("-" * 40)
        for job_id, errors in list(result.job_errors.items())[:5]:
            print(f"  Job: {job_id}")
            for err in errors[:3]:
                print(f"    - [{err['category']}] {err['message'][:60]}...")
            if len(errors) > 3:
                print(f"    ... and {len(errors) - 3} more errors")
            print()

    # Recent error timeline
    if result.timeline and verbose:
        print("ERROR TIMELINE (last 10):")
        print("-" * 40)
        for event in result.timeline[-10:]:
            ts = event["timestamp"].split("T")[1][:8]
            print(f"  {ts} [{event['severity']}] {event['summary']}")
        print()

    # Recommendations
    print("RECOMMENDATIONS:")
    print("-" * 40)
    if result.liveness_failures > 0 or result.connection_errors > 0:
        print("  1. Apply Terraform changes to fix probe timeouts:")
        print("     cd terraform && terraform apply")
        print()
        print("  2. Changes include:")
        print("     - Disable CPU throttling (cpu_idle = false)")
        print("     - Increase liveness timeout (3s -> 10s)")
        print("     - Increase memory (2GB -> 4GB)")
        print("     - Increase CPU (1 -> 2 cores)")
    elif result.firestore_errors > 0:
        print("  1. Create the missing Firestore index:")
        print("     cd terraform && terraform apply")
    else:
        print("  No immediate action required.")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Cloud Run logs for thoth-ingestion-worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --minutes 10                    # Last 10 minutes, all severities
  %(prog)s --minutes 30 --severity ERROR   # Last 30 minutes, errors only
  %(prog)s --job-id <uuid>                 # Logs for specific job
  %(prog)s --minutes 60 --verbose          # Detailed output
        """,
    )
    parser.add_argument(
        "--project",
        default="thoth-dev-485501",
        help="GCP project ID (default: thoth-dev-485501)",
    )
    parser.add_argument(
        "--service",
        default="thoth-ingestion-worker",
        help="Cloud Run service name (default: thoth-ingestion-worker)",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=10,
        help="How many minutes of logs to fetch (default: 10)",
    )
    parser.add_argument(
        "--severity",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Minimum severity level to fetch",
    )
    parser.add_argument(
        "--job-id",
        help="Filter logs by specific job ID",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of log entries to fetch (default: 500)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output including timeline and job errors",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw analysis as JSON",
    )

    args = parser.parse_args()

    print(f"Fetching logs from last {args.minutes} minutes...", file=sys.stderr)

    # Fetch logs
    raw_logs = run_gcloud_logging(
        project=args.project,
        service=args.service,
        minutes=args.minutes,
        severity=args.severity,
        job_id=args.job_id,
        limit=args.limit,
    )

    if not raw_logs:
        print("No logs found for the specified criteria.", file=sys.stderr)
        sys.exit(0)

    print(f"Fetched {len(raw_logs)} log entries, analyzing...", file=sys.stderr)
    print(file=sys.stderr)

    # Parse and analyze
    entries = [parse_log_entry(raw) for raw in raw_logs]
    result = analyze_logs(entries)

    if args.json:
        # JSON output
        output = {
            "total_entries": result.total_entries,
            "severity_counts": dict(result.severity_counts),
            "error_categories": dict(result.error_categories),
            "http_status_counts": dict(result.http_status_counts),
            "failed_endpoints": dict(result.failed_endpoints),
            "liveness_failures": result.liveness_failures,
            "connection_errors": result.connection_errors,
            "firestore_errors": result.firestore_errors,
            "application_errors": result.application_errors[:20],
            "timeline": result.timeline[-20:],
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable report
        print_report(result, verbose=args.verbose)


if __name__ == "__main__":
    main()
