#!/usr/bin/env python3
"""
Load testing script for RLCoach API.

Simulates concurrent users hitting various endpoints to test
system behavior under load.

Usage:
    python scripts/load_test.py --base-url http://localhost:8000 --users 10 --duration 60
    python scripts/load_test.py --base-url https://api.rlcoach.gg --users 50 --duration 120

Requirements:
    pip install httpx asyncio argparse
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RequestResult:
    """Result of a single request."""

    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    error: str | None = None


@dataclass
class LoadTestResults:
    """Aggregated load test results."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    latencies: list[float] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)
    status_codes: dict[int, int] = field(default_factory=dict)
    start_time: float = 0
    end_time: float = 0

    def add_result(self, result: RequestResult) -> None:
        """Add a request result to the aggregation."""
        self.total_requests += 1
        self.latencies.append(result.latency_ms)

        if result.status_code in self.status_codes:
            self.status_codes[result.status_code] += 1
        else:
            self.status_codes[result.status_code] = 1

        if result.status_code < 400:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if result.error:
                if result.error in self.errors:
                    self.errors[result.error] += 1
                else:
                    self.errors[result.error] = 1

    def summary(self) -> dict[str, Any]:
        """Generate summary statistics."""
        duration = self.end_time - self.start_time
        rps = self.total_requests / duration if duration > 0 else 0

        if self.latencies:
            sorted_latencies = sorted(self.latencies)
            p50 = sorted_latencies[len(sorted_latencies) // 2]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
            avg_latency = statistics.mean(self.latencies)
            min_latency = min(self.latencies)
            max_latency = max(self.latencies)
        else:
            p50 = p95 = p99 = avg_latency = min_latency = max_latency = 0

        return {
            "duration_seconds": round(duration, 2),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": round(self.successful_requests / max(self.total_requests, 1) * 100, 2),
            "requests_per_second": round(rps, 2),
            "latency_ms": {
                "avg": round(avg_latency, 2),
                "min": round(min_latency, 2),
                "max": round(max_latency, 2),
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2),
            },
            "status_codes": self.status_codes,
            "errors": self.errors,
        }


class LoadTester:
    """Load tester for RLCoach API."""

    # Endpoints to test (method, path, requires_auth, weight)
    ENDPOINTS = [
        ("GET", "/health", False, 10),
        ("GET", "/api/v1/health", False, 10),
        ("GET", "/api/v1/users/me", True, 5),
        ("GET", "/api/v1/replays", True, 15),
        ("GET", "/api/v1/replays/library", True, 10),
        ("GET", "/api/v1/analysis/trends", True, 5),
        ("GET", "/api/v1/analysis/benchmarks", True, 3),
    ]

    def __init__(
        self,
        base_url: str,
        num_users: int,
        duration_seconds: int,
        auth_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.num_users = num_users
        self.duration_seconds = duration_seconds
        self.auth_token = auth_token
        self.results = LoadTestResults()
        self._stop_event = asyncio.Event()

    async def _make_request(
        self,
        client: Any,  # httpx.AsyncClient
        method: str,
        path: str,
        requires_auth: bool,
    ) -> RequestResult:
        """Make a single HTTP request and measure latency."""
        url = f"{self.base_url}{path}"
        headers = {}

        if requires_auth and self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        start = time.perf_counter()
        try:
            response = await client.request(method, url, headers=headers, timeout=30.0)
            latency_ms = (time.perf_counter() - start) * 1000
            return RequestResult(
                endpoint=path,
                method=method,
                status_code=response.status_code,
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return RequestResult(
                endpoint=path,
                method=method,
                status_code=0,
                latency_ms=latency_ms,
                error=str(e)[:100],
            )

    def _select_endpoint(self) -> tuple[str, str, bool]:
        """Select a random endpoint based on weights."""
        total_weight = sum(e[3] for e in self.ENDPOINTS)
        r = random.uniform(0, total_weight)
        cumulative = 0
        for method, path, requires_auth, weight in self.ENDPOINTS:
            cumulative += weight
            if r <= cumulative:
                return method, path, requires_auth
        # Fallback
        return self.ENDPOINTS[0][:3]

    async def _user_simulation(self, user_id: int, client: Any) -> None:
        """Simulate a single user making requests."""
        while not self._stop_event.is_set():
            method, path, requires_auth = self._select_endpoint()

            # Skip auth-required endpoints if no token
            if requires_auth and not self.auth_token:
                continue

            result = await self._make_request(client, method, path, requires_auth)
            self.results.add_result(result)

            # Random think time between requests (100-500ms)
            await asyncio.sleep(random.uniform(0.1, 0.5))

    async def run(self) -> dict[str, Any]:
        """Run the load test."""
        try:
            import httpx
        except ImportError:
            print("Error: httpx is required. Install with: pip install httpx")
            sys.exit(1)

        print(f"Starting load test against {self.base_url}")
        print(f"  Users: {self.num_users}")
        print(f"  Duration: {self.duration_seconds}s")
        print(f"  Auth: {'enabled' if self.auth_token else 'disabled (public endpoints only)'}")
        print()

        self.results.start_time = time.time()

        async with httpx.AsyncClient() as client:
            # Create user tasks
            tasks = [
                asyncio.create_task(self._user_simulation(i, client))
                for i in range(self.num_users)
            ]

            # Run for specified duration
            await asyncio.sleep(self.duration_seconds)
            self._stop_event.set()

            # Wait for all tasks to complete (with timeout)
            await asyncio.gather(*tasks, return_exceptions=True)

        self.results.end_time = time.time()
        return self.results.summary()


def print_results(results: dict[str, Any]) -> None:
    """Print results in a formatted way."""
    print("\n" + "=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)

    print(f"\nDuration: {results['duration_seconds']}s")
    print(f"Total Requests: {results['total_requests']}")
    print(f"Successful: {results['successful_requests']}")
    print(f"Failed: {results['failed_requests']}")
    print(f"Success Rate: {results['success_rate']}%")
    print(f"Requests/sec: {results['requests_per_second']}")

    print("\nLatency (ms):")
    latency = results["latency_ms"]
    print(f"  Avg: {latency['avg']}")
    print(f"  Min: {latency['min']}")
    print(f"  Max: {latency['max']}")
    print(f"  P50: {latency['p50']}")
    print(f"  P95: {latency['p95']}")
    print(f"  P99: {latency['p99']}")

    print("\nStatus Codes:")
    for code, count in sorted(results["status_codes"].items()):
        print(f"  {code}: {count}")

    if results["errors"]:
        print("\nErrors:")
        for error, count in sorted(results["errors"].items(), key=lambda x: -x[1])[:5]:
            print(f"  {error}: {count}")

    print("\n" + "=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test RLCoach API")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--users",
        type=int,
        default=10,
        help="Number of concurrent users to simulate (default: 10)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--token",
        help="JWT auth token for authenticated endpoints",
    )
    parser.add_argument(
        "--output",
        help="Output results to JSON file",
    )

    args = parser.parse_args()

    tester = LoadTester(
        base_url=args.base_url,
        num_users=args.users,
        duration_seconds=args.duration,
        auth_token=args.token,
    )

    results = asyncio.run(tester.run())

    print_results(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
