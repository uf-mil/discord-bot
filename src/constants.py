from __future__ import annotations

import datetime
import enum
from enum import auto

SEMESTERS = [
    (datetime.date(2023, 8, 23), datetime.date(2023, 12, 6)),
    (datetime.date(2024, 1, 8), datetime.date(2024, 4, 28)),
    (datetime.date(2024, 5, 20), datetime.date(2024, 7, 29)),
]
SCHWARTZ_EMAIL = "ems@ufl.edu"


def semester_given_date(
    date: datetime.datetime,
    *,
    next_semester: bool = False,
) -> tuple[datetime.date, datetime.date] | None:
    for semester in SEMESTERS:
        if semester[0] <= date.date() <= semester[1]:
            return semester
        if next_semester and date.date() < semester[0]:
            return semester
    return None


class Team(enum.Enum):
    SOFTWARE = auto()
    ELECTRICAL = auto()
    MECHANICAL = auto()
    GENERAL = auto()

    @classmethod
    def from_str(cls, ss_str: str) -> Team:
        if "software" in ss_str.lower() or "S" in ss_str:
            return cls.SOFTWARE
        elif "electrical" in ss_str.lower() or "E" in ss_str:
            return cls.ELECTRICAL
        elif "mechanical" in ss_str.lower() or "M" in ss_str:
            return cls.MECHANICAL
        raise ValueError(f"Invalid subteam string: {ss_str}")

    @property
    def sheet_str(self) -> str:
        return {
            self.ELECTRICAL: "E",
            self.SOFTWARE: "S",
            self.GENERAL: "G",
            self.MECHANICAL: "M",
        }[self]

    @property
    def emoji(self) -> str:
        emojis = {
            self.ELECTRICAL: "<:electrical:1205204504409153576>",
            self.SOFTWARE: "<:software:1205205120996999178>",
            self.GENERAL: "<:all:1205205136977432617>",
            self.MECHANICAL: "<:mechanical:1205205096506462279>",
        }
        return emojis.get(self, "❓")

    @property
    def old_emoji(self) -> str:
        emojis = {
            self.ELECTRICAL: "<:electricalold:1207801896891322428>",
            self.SOFTWARE: "<:softwareold:1207801920542998538>",
            self.GENERAL: "<:allold:1207801910665416804>",
            self.MECHANICAL: "<:mechanicalold:1207801690498273340>",
        }
        return emojis.get(self, "❓")

    def __str__(self) -> str:
        return self.name.title()
