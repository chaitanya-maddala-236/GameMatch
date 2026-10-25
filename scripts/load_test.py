from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psutil


async def run(url: str, requests_count: int, concurrency: int, server_pid: int | None = None) -> dict[str, object]:
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(20.0, connect=5.0)
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    statuses: list[int] = []
    errors: list[str] = []
    server_process = psutil.Process(server_pid) if server_pid is not None else None
    server_rss = [server_process.memory_info().rss] if server_process else []
    stop_sampling = asyncio.Event()

    async def sample_server_rss() -> None:
        while not stop_sampling.is_set():
            try:
                server_rss[0] = max(server_rss[0], server_process.memory_info().rss)
            except psutil.Error:
                return
            await asyncio.sleep(0.1)

    async with httpx.AsyncClient(base_url=url.rstrip("/"), timeout=timeout, limits=limits) as client:
        sampler = asyncio.create_task(sample_server_rss()) if server_process else None
        sample = await client.get("/v1/games", params={"limit": 3})
        sample.raise_for_status()
        game_ids = [str(game["id"]) for game in sample.json()["items"]]
        payload = {"positive_game_ids": game_ids, "n": 10}

        async def one_request() -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post("/v1/recommendations", json=payload)
                    statuses.append(response.status_code)
                    response.raise_for_status()
                except (httpx.HTTPError, ValueError) as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                finally:
                    latencies.append((time.perf_counter() - started) * 1000)

        wall_started = time.perf_counter()
        await asyncio.gather(*(one_request() for _ in range(requests_count)))
        wall_seconds = time.perf_counter() - wall_started
        stop_sampling.set()
        if sampler:
            await sampler
    sorted_latencies = sorted(latencies)
    percentile = lambda fraction: sorted_latencies[min(len(sorted_latencies) - 1, int(fraction * (len(sorted_latencies) - 1)))] if sorted_latencies else None
    result = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "target": url,
        "method": "POST /v1/recommendations with three returned catalog game IDs",
        "requested": requests_count,
        "completed_responses": len(statuses),
        "concurrency": concurrency,
        "wall_seconds": round(wall_seconds, 3),
        "throughput_requests_per_second": round(len(statuses) / wall_seconds, 3) if wall_seconds else 0.0,
        "latency_ms_p50": round(percentile(0.50), 3) if percentile(0.50) is not None else None,
        "latency_ms_p95": round(percentile(0.95), 3) if percentile(0.95) is not None else None,
        "latency_ms_mean": round(statistics.mean(latencies), 3) if latencies else None,
        "status_counts": {str(code): statuses.count(code) for code in sorted(set(statuses))},
        "errors": errors[:20],
        "client_process_rss_mib_after": round(psutil.Process().memory_info().rss / (1024**2), 2),
        "interpretation": "One local run measures only this host, request mix, model artifact, and concurrency. It is not a production capacity guarantee.",
    }
    if server_process:
        try:
            result["api_server_process_rss_mib_after"] = round(server_process.memory_info().rss / (1024**2), 2)
        except psutil.Error:
            result["api_server_process_rss_mib_after"] = None
        result["api_server_process_rss_mib_peak_sampled"] = round(max(server_rss) / (1024**2), 2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure API recommendation latency with a bounded async client.")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--server-pid", type=int, help="Optional local API process ID for sampled server RSS.")
    parser.add_argument("--output", type=Path, help="Optional path for the machine-readable benchmark record.")
    args = parser.parse_args()
    if not 1 <= args.requests <= 10000 or not 1 <= args.concurrency <= 100:
        parser.error("--requests must be 1..10000 and --concurrency must be 1..100")
    result = asyncio.run(run(args.url, args.requests, args.concurrency, args.server_pid))
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
