import datetime

from .constants import SEMESTERS


def is_active() -> bool:
    """
    Whether the reports system is active.
    """
    for semester in SEMESTERS:
        if semester[0] <= datetime.date.today() <= semester[1]:
            return True
        if datetime.date.today() <= semester[0]:
            return False
    return False
