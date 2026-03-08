#!/usr/bin/env python3
import argparse
import asyncio

from app.core.db import create_client, get_db
from app.services.media import process_next_media_asset


async def _process_one(db, *, backend: str) -> bool:
    asset = await process_next_media_asset(db, backend=backend)
    if not asset:
        return False

    print(f"Processed media asset: {asset['_id']} status={asset['status']}")
    return True


async def _run(backend: str, *, loop: bool, interval_seconds: float, max_jobs: int | None) -> int:
    client = create_client()
    db = get_db(client)

    processed = 0
    try:
        while True:
            try:
                did_work = await _process_one(db, backend=backend)
            except Exception as exc:
                print(f"Worker error: {exc}")
                return 1

            if did_work:
                processed += 1
                if max_jobs is not None and processed >= max_jobs:
                    print(f"Reached max jobs ({max_jobs}).")
                    return 0
                continue

            print("No planned media assets.")
            if not loop:
                return 0

            await asyncio.sleep(interval_seconds)
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process planned media assets")
    parser.add_argument("--backend", default="local", help="Media backend to process (default: local)")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running and poll for new planned assets",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="Poll interval in loop mode (default: 5)",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Optional maximum number of assets to process before exit",
    )
    args = parser.parse_args()

    if args.interval_seconds <= 0:
        raise SystemExit("--interval-seconds must be > 0")
    if args.max_jobs is not None and args.max_jobs <= 0:
        raise SystemExit("--max-jobs must be > 0")

    code = asyncio.run(
        _run(
            args.backend,
            loop=args.loop,
            interval_seconds=args.interval_seconds,
            max_jobs=args.max_jobs,
        )
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
