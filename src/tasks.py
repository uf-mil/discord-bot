"""
Functionality related to asynchronous task management.
"""
from __future__ import annotations

import asyncio
import datetime
import inspect
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .bot import MILBot

from discord.utils import maybe_coroutine

T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_on_weekday(
    day: int | list[int],
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

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]):  # type: ignore
        return RecurringTask(
            func,
            day,
            hour,
            minute,
            shift,
            check,
        )

    return decorator


class RecurringTask:

    bot: MILBot | None

    def __init__(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        day: int | list[int],
        hour: int,
        minute: int,
        shift: datetime.timedelta | None = None,
        check: Callable[[], bool | Awaitable[bool]] | None = None,
    ):
        self._func = func
        self._day = day
        self._hour = hour
        self._minute = minute
        self._shift = shift
        self._check = check
        self._task = None

    def next_time(self) -> datetime.datetime:
        now = datetime.datetime.now()

        # If multiple days, choose the next day
        if isinstance(self._day, list):
            actual_day = min(self._day, key=lambda d: (d - now.weekday()) % 7)
        else:
            actual_day = self._day

        next_day = now + datetime.timedelta(
            days=(actual_day - now.weekday()) % 7,
        )
        next_time = next_day.replace(
            hour=self._hour,
            minute=self._minute,
            second=0,
            microsecond=0,
        )
        if self._shift:
            next_time += self._shift
        if now > next_time:
            next_time += datetime.timedelta(days=7)
        return next_time

    def start(self, *args):
        self._args = args

    async def run(self):
        # Wait
        next_time = self.next_time()
        logger.info(f"Scheduling {self._func.__name__} for {next_time}.")
        await asyncio.sleep((next_time - datetime.datetime.now()).total_seconds())

        # Schedule the next instance
        self.schedule()

        # Run
        if self._check and not await maybe_coroutine(self._check):
            logger.info(
                f"Skipping {self._func.__name__} until next week because check failed.",
            )
            return

        try:
            return await self._func(*self._args)
        except Exception as e:
            logger.exception(
                f"Exception occurred while running scheduled function {self._func.__name__}.",
            )
            raise e

    async def run_immediately(self):
        if self._task:
            self._task.cancel()
        await self._func(*self._args)
        self.schedule()

    def schedule(self):
        if self.bot:
            self._task = self.bot.tasks.create_task(self.run())
        else:
            raise RuntimeError("Cannot schedule task without bot.")

    def __str__(self) -> str:
        return f"RecurringTask({self._func.__name__}, {self._day}, {self._hour}, {self._minute}, {self._shift}, {self._check})"

    __repr__ = __str__


class TaskManager:

    _pending_tasks: set[asyncio.Task]

    def __init__(self, bot: MILBot):
        self.bot = bot
        self._pending_tasks = set()

    def create_task(
        self,
        coro: Coroutine[Any, Any, T],
    ) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.remove)
        return task

    def run_at(self, when: datetime.datetime, coro: Coroutine) -> asyncio.Task:
        async def _run_at():
            await asyncio.sleep((when - datetime.datetime.now()).total_seconds())
            await coro

        return self.create_task(_run_at())

    def run_in(self, delay: datetime.timedelta, coro: Coroutine) -> asyncio.Task:
        async def _run_in():
            await asyncio.sleep(delay.total_seconds())
            await coro

        return self.create_task(_run_in())

    def shutdown(self):
        for task in self._pending_tasks:
            task.cancel()

        self._pending_tasks.clear()

    def recurring_tasks(self) -> list[RecurringTask]:
        tasks = []
        for cog_name in self.bot.cogs:
            cog = self.bot.get_cog(cog_name)
            cog_tasks = inspect.getmembers(
                cog,
                lambda m: isinstance(m, RecurringTask),
            )
            tasks.extend([t[1] for t in cog_tasks])
        return tasks
