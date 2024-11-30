from __future__ import annotations

import calendar
import datetime
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import discord

from ..constants import Team, semester_given_date

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class Column(IntEnum):

    NAME_COLUMN = 1
    EMAIL_COLUMN = 2
    UFID_COLUMN = 3
    LEADERS_COLUMN = 4
    TEAM_COLUMN = 5
    CREDITS_COLUMN = 6
    DISCORD_NAME_COLUMN = 7
    SCORE_COLUMN = 8


# Effectively: [calendar.MONDAY, calendar.TUESDAY, ..., calendar.SUNDAY]
EVERYDAY = list(range(7))


@dataclass
class WeekColumn:
    """
    Represents a column for one week of the semester (which is used for storing
    student reports and associated scores).
    """

    report_column: int

    START_WEEKDAY = calendar.MONDAY

    @classmethod
    def _start_date(cls) -> datetime.date:
        semester = semester_given_date(datetime.datetime.now())
        if not semester:
            raise RuntimeError("No semester is occurring right now!")
        return semester[0]

    @classmethod
    def _end_date(cls) -> datetime.date:
        semester = semester_given_date(datetime.datetime.now())
        if not semester:
            raise RuntimeError("No semester is occurring right now!")
        return semester[1]

    def _date_to_index(self, date: datetime.date) -> int:
        return (date - self._start_date()).days // 7 + 1

    @property
    def week(self) -> int:
        return (self.report_column - len(Column) - 1) // 2

    @property
    def score_column(self) -> int:
        return self.report_column + 1

    @property
    def date_range(self) -> tuple[datetime.date, datetime.date]:
        """
        Inclusive date range for this column.
        """
        start_date = self._start_date() + datetime.timedelta(weeks=self.week)
        end_date = start_date + datetime.timedelta(days=6)
        return start_date, end_date

    @property
    def closes_at(self) -> datetime.datetime:
        return datetime.datetime.combine(
            self.date_range[1],
            datetime.time(23, 59, 59),
        )

    @classmethod
    def from_date(cls, date: datetime.date):
        col_offset = (date - cls._start_date()).days // 7
        # Each week has two columns: one for the report and one for the score
        # +1 because columns are 1-indexed
        return cls(
            (col_offset * 2) + 1 + len(Column),
        )

    @classmethod
    def first(cls):
        """
        The first week column of the semester.
        """
        return cls(len(Column) + 1)

    @classmethod
    def final(cls):
        """
        The final full week of the semester. Notably, if the semester ends on a
        day other than the final day of a week, this will not include the final
        day of the semester.
        """
        # Days from start
        total_days = (cls._end_date() - cls._start_date()).days
        total_days, _ = divmod(total_days, 7)
        return cls.from_date(
            cls._start_date() + datetime.timedelta(days=total_days - 1),
        )

    @classmethod
    def previous(cls):
        """
        The previous week.
        """
        return cls.from_date(datetime.date.today() - datetime.timedelta(days=7))

    @classmethod
    def current(cls):
        """
        The current week of the semester.
        """
        return cls.from_date(datetime.date.today())

    def __post_init__(self):
        weeks = (self._end_date() - self._start_date()).days // 7
        if self.report_column < len(Column) + 1 or self.report_column > len(
            Column,
        ) + 1 + (weeks * 2):
            raise ValueError(
                f"Cannot create report column with index {self.report_column}.",
            )


@dataclass
class PreviousWeekColumn(WeekColumn):
    """
    A week column in the previous semester, used for retrospective analysis, etc.
    """

    @classmethod
    def _start_date(cls) -> datetime.date:
        semester = semester_given_date(
            datetime.datetime.now(),
            prev_semester=True,
        )
        if not semester:
            raise RuntimeError("No semester is occurring right now!")
        return semester[0]

    @classmethod
    def _end_date(cls) -> datetime.date:
        semester = semester_given_date(
            datetime.datetime.now(),
            prev_semester=True,
        )
        if not semester:
            raise RuntimeError("No semester is occurring right now!")
        return semester[1]


@dataclass
class Student:
    name: str
    discord_id: str
    member: discord.Member | None
    email: str
    team: Team
    report: str | None
    report_score: float | None
    total_score: float
    credits: int | None
    row: int

    @property
    def first_name(self) -> str:
        return str(self.name).split(" ")[0]

    @property
    def status_emoji(self) -> str:
        return "✅" if self.report else "❌"

    @property
    def hours_commitment(self) -> int | None:
        return self.credits * 3 + 3 if self.credits is not None else None
