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


def capped_str(parts: list[str], cap: int = 1024) -> str:
    """
    Joins the most parts possible with a new line between them. If the resulting
    length is greater than the cap length, then the remaining parts are truncated.

    If the parts are capped, "_... (truncated)_" is appended to the end.
    """
    result = ""
    for part in parts:
        if len(result) + len(part) + len("\n... (truncated)") > cap:
            result += "_... (truncated)_"
            break
        result += part + "\n"
    return result.strip()
