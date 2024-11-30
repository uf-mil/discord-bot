from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..constants import SCHWARTZ_EMAIL
from ..email import Email
from .sheets import Student

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class FiringEmail(Email):
    """
    Email to Dr. Schwartz + team lead about needing to fire someone
    """

    def __init__(self, student: Student):
        html = f"<p>Hello,<br><br>A student currently in the Machine Intelligence Laboratory needs to be fired for continually failing to submit required weekly reports despite consistent reminders. This member has failed to produce their sufficient workload for at least several weeks, and has received several Discord messages and emails about this.<br><br>Name: {student.name}<br>Team: {student.team}<br>Discord Username: {student.discord_id}<br><br>For more information, please contact the appropriate team leader.</p>"
        super().__init__(
            [SCHWARTZ_EMAIL],
            "Member Removal Needed",
            html,
        )


class InsufficientReportEmail(Email):
    def __init__(self, student: Student):
        html = f"<p>Hello,<br><br>This email is to inform you that your most recent report has been graded as: <b>Insufficient (yellow)</b>. As a reminder, you are expected to fulfill your commitment of {student.hours_commitment} hours each week you are in the lab.<br><br>While an occasional lapse is understandable, frequent occurrences may result in your removal from the laboratory. If you anticipate any difficulties in completing your future reports, please contact your team lead immediately.<br><br>Your current missing report count is: {student.total_score + 0.5}. Please note that once your count reaches 4, you will be automatically removed from our lab.</p>"
        super().__init__([student.email], "Insufficient Report Notice", html)


class PoorReportEmail(Email):
    def __init__(self, student: Student):
        html = f"<p>Hello,<br><br>This email is to inform you that your most recent report has been graded as: <b>Low/No Work Done (red)</b>. As a reminder, you are expected to fulfill your commitment of {student.hours_commitment} hours per week.<br><br>While an occasional lapse is understandable, frequent occurrences may result in your removal from the laboratory. If you anticipate any difficulties in completing your future reports, please contact your team lead immediately.<br><br>Your current missing report count is: {student.total_score + 1}. Please note that once your count reaches 4, you will be automatically removed from our lab.</p>"
        super().__init__([student.email], "Unsatisfactory Report Notice", html)


class SufficientReportEmail(Email):
    def __init__(self, student: Student):
        html = f"<p>Hello {student.first_name},<br><br>This email is to inform you that your most recent report has been graded as: <b>Sufficient (green)</b>. Keep up the good work.<br><br>If you have any questions or concerns, please feel free to reach out to your team lead.<br><br>Thank you for your hard work!</p>"
        super().__init__([student.email], "Satisfactory Report Notice", html)
