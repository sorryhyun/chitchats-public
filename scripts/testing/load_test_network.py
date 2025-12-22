#!/usr/bin/env python3
"""
Load Test Script for ChitChats Network Usage Analysis

Simulates multiple concurrent users polling chatrooms to measure:
- Network bandwidth usage
- Request/response latency
- Error rates and rate limiting
- Server performance under load

Usage:
    python load_test_network.py --password "your_password" --users 10 --rooms 2 --duration 60

    # With custom configuration
    python load_test_network.py --password "your_password" --users 20 --rooms 3 --duration 120 --base-url http://localhost:8000
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp


@dataclass
class Metrics:
    """Stores performance metrics for the load test"""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_requests: int = 0
    total_bytes_received: int = 0
    total_bytes_sent: int = 0
    response_times: List[float] = field(default_factory=list)
    errors_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    requests_by_endpoint: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def record_request(
        self,
        endpoint: str,
        success: bool,
        response_time: float,
        bytes_sent: int,
        bytes_received: int,
        status_code: Optional[int] = None,
    ):
        """Record a request's metrics"""
        self.total_requests += 1
        self.requests_by_endpoint[endpoint] += 1
        self.response_times.append(response_time)
        self.total_bytes_sent += bytes_sent
        self.total_bytes_received += bytes_received

        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if status_code == 429:
                self.rate_limited_requests += 1
            error_type = f"HTTP_{status_code}" if status_code else "connection_error"
            self.errors_by_type[error_type] += 1

    def get_duration(self) -> float:
        """Get test duration in seconds"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def get_requests_per_second(self) -> float:
        """Calculate requests per second"""
        duration = self.get_duration()
        return self.total_requests / duration if duration > 0 else 0.0

    def get_bandwidth_stats(self) -> Dict[str, float]:
        """Calculate bandwidth statistics"""
        duration = self.get_duration()
        if duration == 0:
            return {"downstream_kbps": 0, "upstream_kbps": 0, "total_kbps": 0}

        downstream_kbps = (self.total_bytes_received * 8) / (duration * 1000)
        upstream_kbps = (self.total_bytes_sent * 8) / (duration * 1000)

        return {
            "downstream_kbps": downstream_kbps,
            "upstream_kbps": upstream_kbps,
            "total_kbps": downstream_kbps + upstream_kbps,
        }

    def get_latency_stats(self) -> Dict[str, float]:
        """Calculate latency statistics"""
        if not self.response_times:
            return {"min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0, "p99": 0}

        sorted_times = sorted(self.response_times)
        return {
            "min": min(sorted_times),
            "max": max(sorted_times),
            "mean": statistics.mean(sorted_times),
            "median": statistics.median(sorted_times),
            "p95": sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else 0,
            "p99": sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else 0,
        }


class LoadTestUser:
    """Simulates a single user polling multiple chatrooms"""

    def __init__(self, user_id: int, base_url: str, api_key: str, room_ids: List[int], poll_interval: float = 4.0):
        self.user_id = user_id
        self.base_url = base_url
        self.api_key = api_key
        self.room_ids = room_ids
        self.poll_interval = poll_interval
        self.is_running = False
        self.last_message_ids: Dict[int, int] = {room_id: 0 for room_id in room_ids}

    async def poll_messages(self, session: aiohttp.ClientSession, room_id: int, metrics: Metrics) -> None:
        """Poll for new messages in a room"""
        endpoint = f"/rooms/{room_id}/messages/poll"
        url = f"{self.base_url}{endpoint}"

        # Add since_id if we have a last message
        if self.last_message_ids[room_id] > 0:
            url += f"?since_id={self.last_message_ids[room_id]}"

        headers = {"X-API-Key": self.api_key, "ngrok-skip-browser-warning": "true"}

        start = time.time()
        bytes_sent = len(json.dumps(headers).encode())

        try:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                bytes_received = len(json.dumps(data).encode())
                response_time = time.time() - start

                success = response.status == 200
                metrics.record_request(
                    endpoint=endpoint,
                    success=success,
                    response_time=response_time,
                    bytes_sent=bytes_sent,
                    bytes_received=bytes_received,
                    status_code=response.status,
                )

                # Update last message ID
                if success and data and len(data) > 0:
                    self.last_message_ids[room_id] = data[-1].get("id", self.last_message_ids[room_id])

        except Exception:
            response_time = time.time() - start
            metrics.record_request(
                endpoint=endpoint,
                success=False,
                response_time=response_time,
                bytes_sent=bytes_sent,
                bytes_received=0,
                status_code=None,
            )

    async def poll_chatting_agents(self, session: aiohttp.ClientSession, room_id: int, metrics: Metrics) -> None:
        """Poll for chatting agent status in a room"""
        endpoint = f"/rooms/{room_id}/chatting-agents"
        url = f"{self.base_url}{endpoint}"

        headers = {"X-API-Key": self.api_key, "ngrok-skip-browser-warning": "true"}

        start = time.time()
        bytes_sent = len(json.dumps(headers).encode())

        try:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                bytes_received = len(json.dumps(data).encode())
                response_time = time.time() - start

                metrics.record_request(
                    endpoint=endpoint,
                    success=response.status == 200,
                    response_time=response_time,
                    bytes_sent=bytes_sent,
                    bytes_received=bytes_received,
                    status_code=response.status,
                )
        except Exception:
            response_time = time.time() - start
            metrics.record_request(
                endpoint=endpoint,
                success=False,
                response_time=response_time,
                bytes_sent=bytes_sent,
                bytes_received=0,
                status_code=None,
            )

    async def run_polling_loop(self, session: aiohttp.ClientSession, metrics: Metrics, duration: int) -> None:
        """Run the polling loop for all rooms"""
        self.is_running = True
        end_time = time.time() + duration

        while self.is_running and time.time() < end_time:
            # Poll all rooms
            tasks = []
            for room_id in self.room_ids:
                tasks.append(self.poll_messages(session, room_id, metrics))
                tasks.append(self.poll_chatting_agents(session, room_id, metrics))

            # Execute all polls concurrently
            await asyncio.gather(*tasks, return_exceptions=True)

            # Wait for next poll interval
            await asyncio.sleep(self.poll_interval)

        self.is_running = False

    def stop(self):
        """Stop the polling loop"""
        self.is_running = False


async def authenticate(base_url: str, password: str) -> str:
    """Authenticate and get API key"""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/auth/login", json={"password": password}) as response:
            if response.status != 200:
                raise Exception(f"Authentication failed: {response.status}")
            data = await response.json()
            return data["api_key"]


async def create_test_rooms(base_url: str, api_key: str, count: int) -> List[int]:
    """Create test chatrooms"""
    room_ids = []
    headers = {"X-API-Key": api_key}

    async with aiohttp.ClientSession() as session:
        for i in range(count):
            async with session.post(
                f"{base_url}/rooms", json={"name": f"Load Test Room {i + 1}"}, headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    room_ids.append(data["id"])
                    print(f"Created room {data['id']}: {data['name']}")
                else:
                    print(f"Failed to create room {i + 1}: {response.status}")

    return room_ids


async def cleanup_test_rooms(base_url: str, api_key: str, room_ids: List[int]) -> None:
    """Delete test chatrooms"""
    headers = {"X-API-Key": api_key}

    async with aiohttp.ClientSession() as session:
        for room_id in room_ids:
            try:
                async with session.delete(f"{base_url}/rooms/{room_id}", headers=headers) as response:
                    if response.status == 200:
                        print(f"Deleted room {room_id}")
                    else:
                        print(f"Failed to delete room {room_id}: {response.status}")
            except Exception as e:
                print(f"Error deleting room {room_id}: {e}")


def print_metrics_report(metrics: Metrics, num_users: int, num_rooms_per_user: int):
    """Print comprehensive metrics report"""
    duration = metrics.get_duration()
    bandwidth = metrics.get_bandwidth_stats()
    latency = metrics.get_latency_stats()

    print("\n" + "=" * 80)
    print("LOAD TEST RESULTS")
    print("=" * 80)

    print("\nTest Configuration:")
    print(f"  Users:              {num_users}")
    print(f"  Rooms per user:     {num_rooms_per_user}")
    print(f"  Total connections:  {num_users * num_rooms_per_user}")
    print(f"  Duration:           {duration:.2f} seconds")

    print("\nRequest Statistics:")
    print(f"  Total requests:     {metrics.total_requests:,}")
    print(
        f"  Successful:         {metrics.successful_requests:,} ({metrics.successful_requests / metrics.total_requests * 100:.1f}%)"
    )
    print(
        f"  Failed:             {metrics.failed_requests:,} ({metrics.failed_requests / metrics.total_requests * 100:.1f}%)"
    )
    print(f"  Rate limited:       {metrics.rate_limited_requests:,}")
    print(f"  Requests/second:    {metrics.get_requests_per_second():.2f}")

    print("\nRequests by Endpoint:")
    for endpoint, count in sorted(metrics.requests_by_endpoint.items()):
        print(f"  {endpoint:45s} {count:,}")

    print("\nLatency (milliseconds):")
    print(f"  Min:                {latency['min'] * 1000:.2f} ms")
    print(f"  Mean:               {latency['mean'] * 1000:.2f} ms")
    print(f"  Median:             {latency['median'] * 1000:.2f} ms")
    print(f"  95th percentile:    {latency['p95'] * 1000:.2f} ms")
    print(f"  99th percentile:    {latency['p99'] * 1000:.2f} ms")
    print(f"  Max:                {latency['max'] * 1000:.2f} ms")

    print("\nBandwidth:")
    print(
        f"  Downstream:         {bandwidth['downstream_kbps']:.2f} kbps ({bandwidth['downstream_kbps'] / 8:.2f} KB/s)"
    )
    print(f"  Upstream:           {bandwidth['upstream_kbps']:.2f} kbps ({bandwidth['upstream_kbps'] / 8:.2f} KB/s)")
    print(f"  Total:              {bandwidth['total_kbps']:.2f} kbps ({bandwidth['total_kbps'] / 8:.2f} KB/s)")

    print("\nData Transfer:")
    print(
        f"  Total received:     {metrics.total_bytes_received:,} bytes ({metrics.total_bytes_received / 1024 / 1024:.2f} MB)"
    )
    print(f"  Total sent:         {metrics.total_bytes_sent:,} bytes ({metrics.total_bytes_sent / 1024 / 1024:.2f} MB)")

    # Extrapolate to hourly/daily
    hours_multiplier = 3600 / duration if duration > 0 else 0
    days_multiplier = hours_multiplier * 24

    print("\nProjected Usage (based on test data):")
    print(f"  Per hour:           {metrics.total_bytes_received * hours_multiplier / 1024 / 1024:.2f} MB")
    print(f"  Per day:            {metrics.total_bytes_received * days_multiplier / 1024 / 1024:.2f} MB")

    if metrics.errors_by_type:
        print("\nErrors by Type:")
        for error_type, count in sorted(metrics.errors_by_type.items(), key=lambda x: x[1], reverse=True):
            print(f"  {error_type:30s} {count:,}")

    print("\n" + "=" * 80)

    # Recommendations
    print("\nRecommendations:")
    if metrics.rate_limited_requests > 0:
        print(f"  ⚠️  Rate limiting detected ({metrics.rate_limited_requests} requests)")
        print("      Consider increasing rate limits or reducing poll frequency")

    if latency["p95"] > 1.0:  # Over 1 second
        print(f"  ⚠️  High latency detected (p95: {latency['p95'] * 1000:.0f}ms)")
        print("      Consider optimizing database queries or adding more caching")

    error_rate = metrics.failed_requests / metrics.total_requests if metrics.total_requests > 0 else 0
    if error_rate > 0.01:  # Over 1% error rate
        print(f"  ⚠️  High error rate: {error_rate * 100:.2f}%")
        print("      Investigate server logs for errors")

    if error_rate == 0 and latency["p95"] < 0.5 and metrics.rate_limited_requests == 0:
        print("  ✅ System performing well under this load")
        print("  ✅ Low latency, no errors, no rate limiting")

    print("=" * 80 + "\n")


async def run_load_test(
    base_url: str, password: str, num_users: int, num_rooms_per_user: int, duration: int, cleanup: bool = True
):
    """Run the complete load test"""
    print(f"\n{'=' * 80}")
    print("Starting Load Test")
    print("=" * 80)
    print("Configuration:")
    print(f"  Base URL:           {base_url}")
    print(f"  Users:              {num_users}")
    print(f"  Rooms per user:     {num_rooms_per_user}")
    print(f"  Duration:           {duration} seconds")
    print(f"  Total connections:  {num_users * num_rooms_per_user}")
    print("=" * 80 + "\n")

    # Authenticate
    print("Authenticating...")
    api_key = await authenticate(base_url, password)
    print("✅ Authentication successful\n")

    # Create test rooms (each user will use the same rooms for simplicity)
    print(f"Creating {num_rooms_per_user} test rooms...")
    room_ids = await create_test_rooms(base_url, api_key, num_rooms_per_user)
    if len(room_ids) != num_rooms_per_user:
        print(f"⚠️  Warning: Only created {len(room_ids)} out of {num_rooms_per_user} rooms")
    print()

    # Initialize metrics and users
    metrics = Metrics()
    users = []

    for i in range(num_users):
        user = LoadTestUser(user_id=i, base_url=base_url, api_key=api_key, room_ids=room_ids, poll_interval=4.0)
        users.append(user)

    # Start all users
    print(f"Starting {num_users} concurrent users...")
    metrics.start_time = time.time()

    # Create sessions and run polling loops
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [user.run_polling_loop(session, metrics, duration) for user in users]

        # Monitor progress
        print(f"Running test for {duration} seconds...\n")
        start = time.time()

        # Show progress every 10 seconds
        async def show_progress():
            while time.time() - start < duration:
                await asyncio.sleep(10)
                elapsed = time.time() - start
                print(f"  Progress: {elapsed:.0f}s / {duration}s - {metrics.total_requests:,} requests")

        progress_task = asyncio.create_task(show_progress())

        # Wait for all users to complete
        await asyncio.gather(*tasks, progress_task, return_exceptions=True)

    metrics.end_time = time.time()

    print("\n✅ Test completed\n")

    # Print results
    print_metrics_report(metrics, num_users, num_rooms_per_user)

    # Cleanup
    if cleanup:
        print("Cleaning up test rooms...")
        await cleanup_test_rooms(base_url, api_key, room_ids)
        print("✅ Cleanup completed\n")


def main():
    parser = argparse.ArgumentParser(
        description="Load test ChitChats network usage", formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--password", required=True, help="Password for authentication")
    parser.add_argument("--users", type=int, default=10, help="Number of concurrent users (default: 10)")
    parser.add_argument("--rooms", type=int, default=2, help="Number of rooms per user (default: 2)")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds (default: 60)")
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="Base URL of the API (default: http://localhost:8000)"
    )
    parser.add_argument("--no-cleanup", action="store_true", help="Don't delete test rooms after completion")

    args = parser.parse_args()

    # Run the load test
    asyncio.run(
        run_load_test(
            base_url=args.base_url,
            password=args.password,
            num_users=args.users,
            num_rooms_per_user=args.rooms,
            duration=args.duration,
            cleanup=not args.no_cleanup,
        )
    )


if __name__ == "__main__":
    main()
