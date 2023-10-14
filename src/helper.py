import asyncio
import datetime
import logging
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


# Write a decorator which runs an async function the next instance of a weekday
# at a specific time
def run_on_weekday(day: int, hour: int, minute: int):
    _tasks = set()

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]):  # type: ignore
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Sleep until the next instance of the weekday
            # at the specified time
            now = datetime.datetime.now()
            next_day = now + datetime.timedelta(days=(day - now.weekday()) % 7)
            next_time = next_day.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
            if now > next_time:
                next_time += datetime.timedelta(days=7)
            logger.info(f"Scheduling {func.__name__} to run at: {next_time}")
            await asyncio.sleep((next_time - now).total_seconds())

            # Find next time to run the function (next week)
            _tasks.add(asyncio.create_task(wrapper(*args, **kwargs)))

            # Run the function
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    f"Exception occurred while running scheduled function {func.__name__}.",
                )
                raise e

        # If loop is running
        return wrapper

    return decorator
