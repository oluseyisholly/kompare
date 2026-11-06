"""Run the durable ingestion worker; no API authentication secret is needed."""

import argparse
import asyncio
import signal

from app.services.ingestion_worker import run_worker


async def main(once=False):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    # Graceful shutdown lets the current job finish while its lease is renewed.
    await run_worker(stop=stop, once=once)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    asyncio.run(main(parser.parse_args().once))
