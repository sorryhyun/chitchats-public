# Network Load Testing

This script simulates multiple concurrent users to measure ChitChats' network performance under load.

## Quick Start

```bash
# Basic test: 10 users, 2 rooms each, 60 seconds
python scripts/testing/load_test_network.py --password "your_password"

# Custom configuration
python scripts/testing/load_test_network.py \
  --password "your_password" \
  --users 20 \
  --rooms 3 \
  --duration 120

# Use with remote server
python scripts/testing/load_test_network.py \
  --password "your_password" \
  --base-url "https://your-server.com" \
  --users 10 \
  --rooms 2 \
  --duration 60
```

## What It Tests

The script simulates realistic user behavior:
- **Message polling**: Checks for new messages every 4 seconds (`/rooms/{id}/messages/poll`)
- **Agent status polling**: Checks chatting agents every 4 seconds (`/rooms/{id}/chatting-agents`)
- **Concurrent connections**: Each user polls multiple rooms simultaneously
- **Rate limiting**: Tests against configured rate limits (60/min for messages, 120/min for agents)

## Metrics Collected

### Request Statistics
- Total requests sent
- Success/failure rates
- Rate limit hits
- Requests per second

### Latency
- Min/max/mean/median response times
- 95th and 99th percentile latencies
- Full distribution of response times

### Bandwidth
- Downstream/upstream data transfer
- Kilobits per second (kbps)
- Total bytes sent/received
- Projected hourly/daily usage

### Error Tracking
- Errors by HTTP status code
- Connection failures
- Rate limiting frequency

## Example Output

```
================================================================================
LOAD TEST RESULTS
================================================================================

Test Configuration:
  Users:              10
  Rooms per user:     2
  Total connections:  20
  Duration:           60.23 seconds

Request Statistics:
  Total requests:     1,200
  Successful:         1,195 (99.6%)
  Failed:             5 (0.4%)
  Rate limited:       0
  Requests/second:    19.92

Requests by Endpoint:
  /rooms/1/messages/poll                        300
  /rooms/1/chatting-agents                      300
  /rooms/2/messages/poll                        300
  /rooms/2/chatting-agents                      300

Latency (milliseconds):
  Min:                12.34 ms
  Mean:               45.67 ms
  Median:             42.12 ms
  95th percentile:    78.90 ms
  99th percentile:    95.23 ms
  Max:                123.45 ms

Bandwidth:
  Downstream:         48.50 kbps (6.06 KB/s)
  Upstream:           12.30 kbps (1.54 KB/s)
  Total:              60.80 kbps (7.60 KB/s)

Data Transfer:
  Total received:     458,240 bytes (0.44 MB)
  Total sent:         92,160 bytes (0.09 MB)

Projected Usage (based on test data):
  Per hour:           26.35 MB
  Per day:            632.40 MB

Recommendations:
  ✅ System performing well under this load
  ✅ Low latency, no errors, no rate limiting
================================================================================
```

## Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--password` | (required) | Authentication password |
| `--users` | 10 | Number of concurrent users |
| `--rooms` | 2 | Number of chatrooms per user |
| `--duration` | 60 | Test duration in seconds |
| `--base-url` | http://localhost:8001 | API base URL |
| `--no-cleanup` | false | Keep test rooms after completion |

## Interpreting Results

### Good Performance Indicators
- ✅ Error rate < 1%
- ✅ P95 latency < 500ms
- ✅ No rate limiting
- ✅ Consistent request/second rate

### Warning Signs
- ⚠️ Rate limiting detected → Increase rate limits or reduce poll frequency
- ⚠️ High latency (P95 > 1s) → Optimize queries or add caching
- ⚠️ Error rate > 1% → Check server logs

## Scaling Estimates

Based on test results, you can estimate:

**For N concurrent users with R rooms each:**
- Requests/second ≈ `(N × R × 2) / 4` (2 endpoints, 4-second interval)
- Bandwidth ≈ `requests/sec × avg_response_size`

**Example scaling:**
- 50 users × 2 rooms = 50 req/s, ~20 KB/s
- 100 users × 2 rooms = 100 req/s, ~40 KB/s
- 500 users × 2 rooms = 500 req/s, ~200 KB/s

## Requirements

```bash
pip install aiohttp
```

Or use the project's existing environment:
```bash
cd backend && uv sync
```

## Tips

1. **Run multiple tests**: Results can vary, run 3-5 times and average
2. **Test during peak**: Simulate your expected peak load + 20% buffer
3. **Monitor server**: Watch CPU, memory, and database during tests
4. **Gradual ramp-up**: Start with small load and increase gradually
5. **Test rate limits**: Intentionally exceed limits to verify they work

## Troubleshooting

### "Authentication failed"
Check that your password is correct and the server is running.

### "Connection refused"
Ensure the backend is running on the specified `--base-url`.

### High error rates
- Check server logs for errors
- Verify database connection pool size
- Monitor server resources (CPU, memory)

### Inconsistent results
- Server may be handling other traffic
- Try running test multiple times
- Ensure stable network connection
