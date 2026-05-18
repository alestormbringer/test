import asyncio
import signal
import sys
from loguru import logger
from app.core.logger import setup_logger
from app.core.engine import TradingEngine


def main():
    setup_logger()
    engine = TradingEngine()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        loop.run_until_complete(engine.stop())
        loop.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        loop.run_until_complete(engine.start())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
        loop.run_until_complete(engine.stop())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
