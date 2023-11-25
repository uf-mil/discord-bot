"""
Functionality related to asynchronous task management.
"""
import asyncio
import datetime
from collections.abc import Coroutine


class TaskManager:
    _pending_tasks: set[asyncio.Task]

    def __init__(self):
        self._pending_tasks = set()

    def create_task(self, coro: Coroutine) -> asyncio.Task:
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
