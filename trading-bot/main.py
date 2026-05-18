import asyncio
import signal
import sys
from loguru import logger
from app.core.logger import setup_logger
from app.core.engine import TradingEngine


async def run():
    engine = TradingEngine()

    loop = asyncio.get_running_loop()

    def shutdown_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(engine.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    await engine.start()


def main():
    setup_logger()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
