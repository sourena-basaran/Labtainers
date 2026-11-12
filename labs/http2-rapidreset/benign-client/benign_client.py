#!/usr/bin/env python3
import argparse
import asyncio
import random
import time
import httpx


def percentile(sorted_data, p):
    if not sorted_data:
        return 0.0
    index = (len(sorted_data) - 1) * (p / 100.0)
    floorIndex = int(index)
    ceilingIndex = min(floorIndex + 1, len(sorted_data) - 1)
    return sorted_data[floorIndex] + (sorted_data[ceilingIndex] - sorted_data[floorIndex]) * (index - floorIndex)


async def single_request(client, url, cancel_prob, latencies, stats):
    start = time.perf_counter()
    task = asyncio.create_task(client.get(url))

    # Simulate natural browser navigation or gRPC deadline cancellation (2%-5%)
    if random.random() < cancel_prob:
        await asyncio.sleep(random.uniform(0.002, 0.008))
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                stats["cancelled"] += 1
                return

    try:
        resp = await task
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if resp.status_code == 200:
            latencies.append(elapsed_ms)
            stats["completed"] += 1
        else:
            stats["errors"] += 1
    except Exception:
        stats["errors"] += 1


async def run_traffic(args):
    url = f"https://{args.host}:{args.port}{args.path}"
    latencies = []
    stats = {"completed": 0, "cancelled": 0, "errors": 0}

    # Multiplex all concurrent streams over a single persistent HTTP/2 TLS connection
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
    async with httpx.AsyncClient(http2=True, verify=False, limits=limits, timeout=5.0) as client:
        end_time = float("inf") if args.continuous else (time.monotonic() + args.duration)
        try:
            while time.monotonic() < end_time:
                batch = [
                    single_request(client, url, args.cancel_rate, latencies, stats)
                    for _ in range(args.concurrency)
                ]
                await asyncio.gather(*batch)
                await asyncio.sleep(args.interval)
        except asyncio.CancelledError:
            pass

    latencies.sort()
    attempted = stats["completed"] + stats["errors"]
    comp_rate = (stats["completed"] / attempted * 100.0) if attempted > 0 else 0.0

    summary = (
        f"COMPLETED={stats['completed']} "
        f"CANCELLED={stats['cancelled']} "
        f"ERRORS={stats['errors']} "
        f"COMPLETION_RATE={comp_rate:.2f}% "
        f"P50_MS={percentile(latencies, 50):.2f} "
        f"P95_MS={percentile(latencies, 95):.2f} "
        f"P99_MS={percentile(latencies, 99):.2f}"
    )
    print(f"[BENIGN] {summary}", flush=True)
    with open("/home/ubuntu/benign_results.log", "w") as f:
        f.write(summary + "\n")


def main():
    parser = argparse.ArgumentParser(description="HTTP/2 Multiplexed Benign Traffic Generator")
    parser.add_argument("--host", default="192.168.10.2", help="Target reverse proxy IP")
    parser.add_argument("--port", type=int, default=8443, help="Target reverse proxy TLS port")
    parser.add_argument("--path", default="/api/data", help="Target endpoint path")
    parser.add_argument("--duration", type=int, default=15, help="Run duration in seconds")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent streams per batch")
    parser.add_argument("--interval", type=float, default=0.1, help="Pause between batches in seconds")
    parser.add_argument("--cancel-rate", type=float, default=0.03, help="Natural RST_STREAM probability")
    parser.add_argument("--continuous", action="store_true", help="Run until interrupted (Ctrl+C)")
    args = parser.parse_args()
    try:
        asyncio.run(run_traffic(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
