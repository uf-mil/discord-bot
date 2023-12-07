import asyncio
import datetime
import logging
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

from discord.utils import maybe_coroutine

T = TypeVar("T")
logger = logging.getLogger(__name__)


# Write a decorator which runs an async function the next instance of a weekday
# at a specific time
def run_on_weekday(
    day: int,
    hour: int,
    minute: int,
    shift: datetime.timedelta | None = None,
    check: Callable[[], bool | Awaitable[bool]] | None = None,
):
    """
    Runs the decorated function on the next instance of the specified weekday.

    Arguments:
        day (int): The day of the week to run the function on.
        hour (int): The hour of the day to run the function on.
        minute (int): The minute of the hour to run the function on.
        shift (datetime.timedelta, optional): The amount of time to shift the
            scheduled time by. If provided, the shift is added to the default time.
            Defaults to None.
    """
    _tasks = set()

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]):  # type: ignore
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T | None:
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
            if shift:
                next_time += shift
            if now > next_time:
                next_time += datetime.timedelta(days=7)
            logger.info(f"Scheduling {func.__name__} to run at: {next_time}")
            await asyncio.sleep((next_time - now).total_seconds())

            # Find next time to run the function (next week)
            _tasks.add(asyncio.create_task(wrapper(*args, **kwargs)))

            # Check if the function should be run again
            if check and not await maybe_coroutine(check):
                logger.info(
                    f"Skipping {func.__name__} until next week because check failed.",
                )
                return

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
