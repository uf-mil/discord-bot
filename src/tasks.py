from __future__ import annotations

import asyncio
import contextlib
import datetime
import inspect
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .bot import MILBot

    if sys.version_info >= (3, 12):
        from calendar import Day


from discord.utils import maybe_coroutine

T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_on_weekday(
    day: int | list[int] | list[Day],
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
        day: int | list[int] | list[Day],
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

    def _dt_from_weekday(
        self,
        day: int | Day,
        starting_point: datetime.datetime | None = None,
    ) -> datetime.datetime:
        now = starting_point if starting_point else datetime.datetime.now()
        next_day = now + datetime.timedelta(
            days=(day - now.weekday()) % 7,
        )
        dt = next_day.replace(
            hour=self._hour,
            minute=self._minute,
            second=0,
            microsecond=0,
        )
        # Add the shift to the datetime if one was requested
        if self._shift:
            dt += self._shift
        # If the task was scheduled before the current time (likely because the
        # weekday requested is today's weekday), then let's use next week
        if now > dt:
            dt += datetime.timedelta(days=7)
        return dt

    def next_time(self) -> datetime.datetime:
        now = datetime.datetime.now()

        # If multiple days, choose the next day
        if isinstance(self._day, list):
            actual_day = min(self._day, key=lambda d: self._dt_from_weekday(d) - now)
        else:
            actual_day = self._day

        return self._dt_from_weekday(actual_day)

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

    _meta_task: asyncio.Task
    _tasks: dict[str, asyncio.Task]
    _lock: asyncio.Lock
    _task_queue: asyncio.Queue[
        tuple[Coroutine[Any, Any, Any], str | None, asyncio.Event | None]
    ]

    def __init__(self, bot: MILBot):
        self._tasks = {}
        self._lock = asyncio.Lock()
        self._task_queue = asyncio.Queue()
        self.bot = bot

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()
        self.stop()

    def start(self):
        self._meta_task = asyncio.create_task(self._handle_task_creation())

    def stop(self):
        self._meta_task.cancel()

    def unique_id(self) -> str:
        return str(uuid.uuid4())

    def create_task(self, coro: Coroutine, *, name: str | None = None) -> None:
        self._task_queue.put_nowait((coro, name, None))

    async def create_task_and_wait(
        self,
        coro: Coroutine,
        *,
        name: str | None = None,
    ) -> asyncio.Task:
        task_created_event = asyncio.Event()
        if not name:
            name = self.unique_id()
        self._task_queue.put_nowait((coro, name, task_created_event))
        await task_created_event.wait()
        task = self.get_task(name)
        if not task:
            raise ValueError(
                f"Task with name {name} not found. This should not happen, since this function should wait for the task!",
            )
        return task

    async def _handle_task_creation(self):
        while True:
            coro, name, task_event = await self._task_queue.get()
            await self._async_create_task(coro, name=name, event=task_event)

    async def _async_create_task(
        self,
        coro: Coroutine,
        *,
        name: str | None = None,
        event: asyncio.Event | None = None,
    ) -> asyncio.Task:
        async with self._lock:
            task_name = name or self.unique_id()
            if task_name in self._tasks:
                logger.warning(
                    f"Task with name {task_name} already exists, quietly removing it...",
                )
                self.remove_task(task_name)

            task = asyncio.create_task(coro)
            self._tasks[task_name] = task

            task.add_done_callback(
                lambda task_ref: (
                    self._tasks.pop(task_name, None)
                    if self._tasks.get(task_name or "") == task_ref
                    else None
                ),
            )
            if event:
                event.set()
            return task

    def get_task(self, name: str) -> asyncio.Task | None:
        return self._tasks.get(name)

    def remove_task(self, name: str) -> None:
        task = self._tasks.get(name, None)
        self.create_task(self._async_remove_task(task))

    async def _async_remove_task(
        self,
        task: asyncio.Task | None,
    ) -> asyncio.Task | None:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        return task

    def run_at(
        self,
        when: datetime.datetime,
        name: str,
        coro: Callable[..., Coroutine[Any, Any, Any]],
        *args,
        **kwargs,
    ) -> None:
        delay = when.astimezone() - datetime.datetime.now().astimezone()
        return self.run_in(delay, name, coro, *args, **kwargs)

    def run_in(
        self,
        delay: datetime.timedelta,
        name: str,
        coro: Callable[..., Coroutine[Any, Any, Any]],
        *args,
        **kwargs,
    ) -> None:
        if delay.total_seconds() <= 0:
            raise ValueError("The specified delay is in the past")

        async def _run_in():
            try:
                await asyncio.sleep(delay.total_seconds())
                await coro(*args, **kwargs)
            except asyncio.CancelledError:
                pass

        return self.create_task(_run_in(), name=name)

    async def shutdown(self):
        tasks = list(self._tasks.values())
        logger.info(f"Shutting down {len(tasks)} tasks in the task manager...")
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

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
