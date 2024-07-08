from __future__ import annotations

import calendar
import datetime
import itertools
import logging
import random
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import discord
import gspread
import gspread_asyncio
from discord.ext import commands

from .constants import SCHWARTZ_EMAIL, Team, semester_given_date
from .email import Email
from .tasks import run_on_weekday
from .utils import is_active, ordinal
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


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


@dataclass
class WeekColumn:
    """
    Represents a column for one week of the semester (which is used for storing
    student reports and associated scores).
    """

    report_column: int

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
        return cls((col_offset * 2) + 1 + len(Column))

    @classmethod
    def first(cls):
        """
        The first week column of the semester.
        """
        return cls(len(Column) + 1)

    @classmethod
    def last_week(cls):
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


class ReportReviewButton(discord.ui.Button):
    def __init__(
        self,
        bot: MILBot,
        student: Student,
        *,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        label: str | None = None,
        emoji: str | None = None,
        row: int | None = None,
    ):
        self.bot = bot
        self.student = student
        super().__init__(style=style, label=label, emoji=emoji, row=row)

    async def respond_early(self, interaction: discord.Interaction, content: str):
        assert self.view is not None
        for children in self.view.children:
            children.disabled = True
        await interaction.response.edit_message(content=content, view=self.view)

    async def log_score(self, score: float) -> None:
        """
        Logs the report score to the spreadsheet.
        """
        sh = await self.bot.sh.get_worksheet(0)
        col = WeekColumn.last_week().score_column
        row = self.student.row
        await sh.update_cell(row, col, score)


class NegativeReportButton(ReportReviewButton):
    def __init__(self, bot: MILBot, student: Student):
        self.bot = bot
        self.student = student
        super().__init__(
            bot,
            student,
            label="Little/no work attempted",
            emoji="🛑",
            style=discord.ButtonStyle.red,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        await self.respond_early(
            interaction,
            f"{self.bot.loading_emoji} Logging score and sending email to student...",
        )
        # 1. Log score to spreadsheet
        await self.log_score(1)
        # Determine action for student based on their current score
        new_score = self.student.total_score + 1

        # Notify necessary people
        if new_score > 4:
            # Student needs to be fired
            email = FiringEmail(self.student)
            await self.bot.leaders_channel.send(
                f"🔥 {self.student.name} has been removed from the lab due to excessive missing reports.",
            )
            await email.send()
        else:
            email = PoorReportEmail(self.student)
            await email.send()
        self.view.stop()


class WarningReportButton(ReportReviewButton):
    def __init__(self, bot: MILBot, student: Student):
        self.bot = bot
        self.student = student
        yellow_label = f"~{student.hours_commitment // 3 if student.hours_commitment else 0}+ hours of effort"
        super().__init__(
            bot,
            student,
            label=yellow_label,
            emoji="⚠️",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.respond_early(
            interaction,
            f"{self.bot.loading_emoji} Logging score and sending email to student...",
        )
        # 1. Log score to spreadsheet
        await self.log_score(0.5)
        # Determine action for student based on their current score
        new_score = self.student.total_score + 0.5

        # Notify necessary people
        if new_score > 4:
            # Student needs to be fired
            email = FiringEmail(self.student)
            await self.bot.leaders_channel.send(
                f"🔥 {self.student.name} has been removed from the lab due to excessive missing reports.",
            )
            await email.send()
        else:
            email = InsufficientReportEmail(self.student)
            await email.send()
        assert self.view is not None
        self.view.stop()


class GoodReportButton(ReportReviewButton):
    def __init__(self, bot: MILBot, student: Student):
        self.bot = bot
        self.student = student
        green_label = f"~{student.hours_commitment}+ hours of effort"
        super().__init__(
            bot,
            student,
            label=green_label,
            emoji="✅",
            style=discord.ButtonStyle.green,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.respond_early(
            interaction,
            f"{self.bot.loading_emoji} Logging score and sending email to student...",
        )
        # 1. Log score to spreadsheet
        await self.log_score(0)
        # Send email
        email = SufficientReportEmail(self.student)
        await email.send()
        assert self.view is not None
        self.view.stop()


class SkipReportButton(ReportReviewButton):
    def __init__(self, bot: MILBot, student: Student):
        self.bot = bot
        self.student = student
        super().__init__(
            bot,
            student,
            label="Skip (no score)",
            emoji="⏩",
            style=discord.ButtonStyle.secondary,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        assert self.view is not None
        self.view.stop()


class ReportsReviewView(MILBotView):
    def __init__(self, bot: MILBot, student: Student):
        self.bot = bot
        self.student = student
        super().__init__()
        self.add_item(NegativeReportButton(bot, student))
        self.add_item(WarningReportButton(bot, student))
        self.add_item(GoodReportButton(bot, student))
        self.add_item(SkipReportButton(bot, student))


class StartReviewView(MILBotView):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Start Review",
        style=discord.ButtonStyle.green,
        custom_id="start_review:start",
    )
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button):
        # We can assume that this button was pressed in a X-leadership channel
        await interaction.response.send_message(
            f"{self.bot.loading_emoji} Thanks for starting this review! Pulling data...",
            ephemeral=True,
        )
        if not interaction.channel or isinstance(
            interaction.channel,
            discord.DMChannel,
        ):
            raise discord.app_commands.NoPrivateMessage

        team_name = str(interaction.channel.name).removesuffix("-leadership")
        team = Team.from_str(team_name)
        week = WeekColumn.last_week()
        column = week.report_column
        students = await self.bot.reports_cog.students_status(column)
        students = [s for s in students if s.team == team and s.report_score is None]
        if not len(students):
            await interaction.edit_original_response(
                content="All responses for last week have already been graded! Nice job being proactive! 😊",
                view=None,
            )
            return
        else:
            for student in students:
                view = ReportsReviewView(self.bot, student)
                await interaction.edit_original_response(
                    content=f"Please grade the report by **{student.name}**:\n> _{student.report}_"
                    if student.report
                    else f"❌ **{student.name}** did not submit a report.",
                    view=view,
                )
                await view.wait()
            await interaction.edit_original_response(
                content="✅ Nice work. All reports have been graded. Thank you for your help!",
                view=None,
                attachments=[await self.bot.good_job_gif()],
            )
        view = MILBotView()
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Review Complete",
                disabled=True,
            ),
        )
        assert isinstance(interaction.message, discord.Message)
        await interaction.message.edit(view=view)


class ReportsModal(discord.ui.Modal):
    name = discord.ui.TextInput(
        label="Name",
        placeholder=random.choice(["Albert Gator", "Alberta Gator"]),
    )
    ufid = discord.ui.TextInput(
        label="UFID",
        placeholder="37014744",
        min_length=8,
        max_length=8,
    )
    team = discord.ui.TextInput(
        label="Team",
        placeholder="Electrical, Mechanical, or Software",
    )
    report = discord.ui.TextInput(
        label="Report",
        placeholder="1-2 sentences describing your progress this week",
        style=discord.TextStyle.long,
        max_length=1000,
    )

    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(title="Weekly Report")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"{self.bot.loading_emoji} Reviewing and validating your report before submitting...",
            ephemeral=True,
            file=await self.bot.reading_gif(),
        )

        # Validate input
        # Check that team is one of the three
        try:
            team = Team.from_str(self.team.value)
        except ValueError:
            await interaction.edit_original_response(
                content="❌ Please enter a valid team name! (`Electrical`, `Mechanical`, or `Software`)",
                attachments=[],
            )
            return

        # Find users name in the main sheet
        main_worksheet = await self.bot.sh.get_worksheet(0)
        name_cell = await main_worksheet.find(self.name.value)

        # If name not found, return
        if name_cell is None:
            await interaction.edit_original_response(
                content="❌ We couldn't find your name in the main spreadsheet. Are you registered for EGN4912?",
                attachments=[],
            )
            return

        # Ensure UFID matches
        if (
            await main_worksheet.cell(name_cell.row, Column.UFID_COLUMN)
        ).value != self.ufid.value:
            await interaction.edit_original_response(
                content="❌ The UFID you entered does not match the one we have on file!",
                attachments=[],
            )
            return

        # Calculate column to log in.
        cur_semester = semester_given_date(datetime.datetime.now())
        cur_semester[0] if cur_semester else datetime.date.today()
        week = WeekColumn.current()

        # Log a Y for their square
        if (
            await main_worksheet.cell(
                name_cell.row,
                week.report_column,
            )
        ).value:
            await interaction.edit_original_response(
                content="❌ You've already submitted a report for this week!",
                attachments=[],
            )
            return

        await main_worksheet.update_cell(
            name_cell.row,
            Column.TEAM_COLUMN,
            team.sheet_str,
        )
        await main_worksheet.update_cell(
            name_cell.row,
            Column.DISCORD_NAME_COLUMN,
            str(interaction.user),
        )

        # Add a comment with their full report in the cell
        a1_notation = gspread.utils.rowcol_to_a1(name_cell.row, week.report_column)  # type: ignore
        await main_worksheet.update(
            a1_notation,
            [
                [
                    f"{self.report.value} (submitted at {datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S')})",
                ],
            ],
        )

        month_date_formatted = week.date_range[0].strftime("%B %d, %Y")
        receipt = discord.Embed(
            title="Weekly Report Receipt",
            description=f"Here's a copy of your report for the week of **{month_date_formatted}** for your records. If you need to make any changes, please contact your team leader.",
            color=discord.Color.blue(),
        )
        diff = week.closes_at - datetime.datetime.now()
        hours, minutes = divmod(diff.total_seconds() // 60, 60)
        diff_str = f"{hours:.0f} hours" if hours > 0 else f"{minutes:.0f} minutes"
        submitted_at = f"{discord.utils.format_dt(discord.utils.utcnow(), 'F')} ({diff_str} before deadline)"
        receipt.add_field(
            name="📝 __Report__",
            value=f"```\n{self.report.value[:1000]}\n```",
            inline=False,
        )
        report_values = await self.bot.reports_cog.safe_col_values(
            main_worksheet,
            week.report_column,
        )
        report_values = report_values[2:]  # Skip header rows
        # Number of submitted reports:
        submitted_reports = len([rv for rv in report_values if rv])
        receipt.add_field(name="🕰️ __Submitted At__", value=submitted_at, inline=False)
        receipt.set_footer(
            text=f"Thank you for your hard work! You were the {ordinal(submitted_reports)} person to submit your report this week! (out of {len(report_values)})",
        )
        try:
            message = await interaction.user.send(embed=receipt)
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="✅ Your report was successfully submitted. However, you do not have direct messages enabled, so we were unable to send you a receipt.",
                attachments=[],
            )
        else:
            await interaction.edit_original_response(
                content=f"✅ Successfully logged your report! A [receipt]({message.jump_url}) of your report has been sent to you through direct messages. Thank you!",
                attachments=[],
            )


class SubmitButton(discord.ui.Button):
    def __init__(self, bot: MILBot):
        self.bot = bot
        if not is_active():
            super().__init__(
                label="Reports are not currently active.",
                style=discord.ButtonStyle.grey,
                disabled=True,
                custom_id="reports_view:submit",
            )
        elif datetime.datetime.today().weekday() in [calendar.MONDAY, calendar.TUESDAY]:
            super().__init__(
                label="Reports can only be submitted between Wednesday and Sunday.",
                style=discord.ButtonStyle.red,
                disabled=True,
                custom_id="reports_view:submit",
            )
        else:
            super().__init__(
                label="Submit your report!",
                style=discord.ButtonStyle.green,
                custom_id="reports_view:submit",
            )

    async def callback(self, interaction: discord.Interaction):
        # If button is triggered on Monday or Tuesday, send error message
        if datetime.datetime.today().weekday() in [calendar.MONDAY, calendar.TUESDAY]:
            return await interaction.response.send_message(
                ":x: Weekly reports should be submitted between Wednesday and Sunday. While occasional exceptions can be made if you miss a week—simply inform your team lead—this should not become a regular occurrence. Be aware that the submission window closes promptly at 11:59pm on Sunday.",
                ephemeral=True,
            )

        if not is_active():
            return await interaction.response.send_message(
                "❌ The weekly reports system is currently inactive due to the interim period between semesters. Please wait until next semester to document any work you have completed in between semesters. Thank you!",
                ephemeral=True,
            )
        # Send modal where user fills out report
        await interaction.response.send_modal(ReportsModal(self.bot))


class ReportHistoryButton(discord.ui.Button):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="Report History",
            custom_id="reports_view:history",
        )

    def _embed_color(self, total_score: float) -> discord.Color:
        if total_score >= 4:
            return discord.Color.dark_red()
        elif total_score >= 3:
            return discord.Color.brand_red()
        elif total_score >= 2:
            return discord.Color.orange()
        elif total_score >= 1:
            return discord.Color.gold()
        return discord.Color.brand_green()

    async def callback(self, interaction: discord.Interaction):
        # Get the entire row for that member, parse it, and present it to the user
        await interaction.response.send_message(
            f"{self.bot.loading_emoji} Fetching your report history...",
            ephemeral=True,
        )
        main_worksheet = await self.bot.sh.get_worksheet(0)
        name_cell = await main_worksheet.find(
            interaction.user.name,
            in_column=Column.DISCORD_NAME_COLUMN.value,
        )
        if name_cell is None:
            await interaction.edit_original_response(
                content="❌ We couldn't find your name in the main spreadsheet. Are you registered for EGN4912 and have you submitted a report this semester?",
                attachments=[],
            )
            return

        # Get all values for this member
        row_values = await main_worksheet.row_values(name_cell.row)
        # Iterate through week columns
        week = WeekColumn.current()
        reports_scores = []
        start_column = len(Column) + 1
        end_column = len(row_values) + len(row_values) % 2
        # Loop through each week (two cols at a time)
        for week_i in range(start_column, end_column, 2):
            # Only add weeks which are before the current week
            if week_i <= week.report_column:
                reports_scores.append(
                    (
                        row_values[week_i - 1],
                        row_values[week_i] if week_i < len(row_values) else None,
                    ),
                )
            week.report_column += 2

        name = row_values[Column.NAME_COLUMN - 1]
        egn_credits = row_values[Column.CREDITS_COLUMN - 1]
        hours = float(egn_credits) * 3 + 3
        total_score = row_values[Column.SCORE_COLUMN - 1]
        embed_color = self._embed_color(float(total_score))
        embed = discord.Embed(
            title=f"Report History for `{name}`",
            color=embed_color,
            description=f"You currently have a missing score of `{total_score}`.",
        )
        emojis = {
            0: "✅",
            0.5: "⚠️",
            1: "❌",
        }
        column = WeekColumn.first()
        for report, score in reports_scores:
            emoji = emojis.get(float(score) if score else score, "❓")
            # Format: May 13
            start_date = column.date_range[0].strftime("%B %-d")
            capped_report = f"* {report}" if len(report) < 900 else f"* {report}..."
            if score and float(score):
                capped_report += (
                    f"\n* **This report added +{float(score)} to your missing score.**"
                )
            embed.add_field(
                name=f"{emoji} Week of `{start_date}`",
                value=capped_report,
                inline=False,
            )
            column.report_column += 2
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text=f"✅: {hours:.0f}+ hours demonstrated | ⚠️: 0-{hours // 3:.0f} hours demonstrated | ❌: Missing report/no work demonstrated",
        )
        await interaction.edit_original_response(content=None, embed=embed)


class ReportsView(MILBotView):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)
        self.add_item(SubmitButton(bot))
        self.add_item(ReportHistoryButton(bot))


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


class ReportsCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.post_reminder.start(self)
        self.last_week_summary.start(self)
        self.first_individual_reminder.start(self)
        self.second_individual_reminder.start(self)
        self.update_report_channel.start(self)

    @run_on_weekday(calendar.FRIDAY, 12, 0, check=is_active)
    async def post_reminder(self):
        general_channel = self.bot.general_channel
        return await general_channel.send(
            f"{self.bot.egn4912_role.mention}\nHey everyone! Friendly reminder to submit your weekly progress reports by **Sunday night at 11:59pm**. You can submit your reports in the {self.bot.member_services_channel.mention} channel. If you have any questions, please contact your leader. Thank you!",
        )

    async def safe_col_values(
        self,
        ws: gspread_asyncio.AsyncioGspreadWorksheet,
        column: int,
    ) -> list[str]:
        names = await ws.col_values(column)
        if not isinstance(names, list):
            raise RuntimeError("Column is missing!")
        return [n or "" for n in names]

    async def students_status(self, column: int) -> list[Student]:
        main_worksheet = await self.bot.sh.get_worksheet(0)
        names = await self.safe_col_values(main_worksheet, Column.NAME_COLUMN)
        discord_ids = await self.safe_col_values(
            main_worksheet,
            Column.DISCORD_NAME_COLUMN,
        )
        teams = await self.safe_col_values(main_worksheet, Column.TEAM_COLUMN)
        emails = await self.safe_col_values(main_worksheet, Column.EMAIL_COLUMN)
        reg_credits = await self.safe_col_values(main_worksheet, Column.CREDITS_COLUMN)
        scores = await self.safe_col_values(main_worksheet, Column.SCORE_COLUMN)
        col_vals = await main_worksheet.col_values(column)
        col_scores = await main_worksheet.col_values(column + 1)
        students = list(
            itertools.zip_longest(
                names,
                discord_ids,
                teams,
                emails,
                reg_credits,
                scores,
                col_vals,
                col_scores,
            ),
        )

        res: list[Student] = []
        for i, (
            name,
            discord_id,
            team,
            email,
            credit,
            total_score,
            report,
            report_score,
        ) in enumerate(
            students[2:],
        ):  # (skip header rows)
            member = self.bot.active_guild.get_member_named(str(discord_id))
            res.append(
                Student(
                    name,
                    discord_id,
                    member,
                    email,
                    Team.from_str(str(team)),
                    report if report else None,
                    float(report_score) if report_score else None,
                    float(total_score),
                    int(credit),
                    i + 3,
                ),
            )
        res.sort(key=lambda s: s.first_name)
        return res

    async def members_without_report(self) -> list[Student]:
        week = WeekColumn.current()
        students = await self.students_status(week.report_column)
        return [student for student in students if not student.report]

    @run_on_weekday(calendar.SUNDAY, 12, 0, check=is_active)
    async def first_individual_reminder(self):
        # Get all members who have not completed reports for the week
        students = await self.members_without_report()
        deadline_tonight = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time(23, 59, 59),
        )
        for student in students:
            if student.member:
                try:
                    await student.member.send(
                        f"Hey **{student.first_name}**! It's your friendly uf-mil-bot here. I noticed you haven't submitted your weekly MIL report yet. Please submit it in the {self.bot.member_services_channel.mention} channel by {discord.utils.format_dt(deadline_tonight, 't')} tonight. Thank you!",
                    )
                    logger.info(
                        f"Sent first individual report reminder to {student.member}.",
                    )
                except discord.Forbidden:
                    logger.info(
                        f"Could not send first individual report reminder to {student.member}.",
                    )

    @run_on_weekday(calendar.SUNDAY, 20, 0)
    async def second_individual_reminder(self):
        # Get all members who have not completed reports for the week
        students = await self.members_without_report()
        deadline_tonight = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time(23, 59, 59),
        )
        for student in students:
            if student.member:
                try:
                    await student.member.send(
                        f"Hey **{student.first_name}**! It's your friendly uf-mil-bot here again. I noticed you haven't submitted your report yet. There are only **four hours** remaining to submit your report! Please submit it in the {self.bot.member_services_channel.mention} channel by {discord.utils.format_dt(deadline_tonight, 't')} tonight. Thank you!",
                    )
                    logger.info(
                        f"Sent second individual report reminder to {student.member}.",
                    )
                except discord.Forbidden:
                    logger.info(
                        f"Could not send second individual report reminder to {student.member}.",
                    )

    @run_on_weekday(calendar.MONDAY, 0, 0)
    async def last_week_summary(self):
        """
        Gives leaders a list of who submitted reports and who did not.
        """
        await self.bot.sh.get_worksheet(0)

        # Calculate the week number and get the column
        column = WeekColumn.last_week()

        # Get all members who have not completed reports for the week
        students = await self.students_status(column.report_column)

        # Generate embed
        first_day_of_week = column.date_range[0]
        last_day_of_week = column.date_range[1]
        first = first_day_of_week.strftime("%B %-d, %Y")
        last = last_day_of_week.strftime("%B %-d, %Y")
        for team in Team:
            team_members = [s for s in students if s.team == team]
            if not team_members:
                continue
            team_leads_ch = self.bot.team_leads_ch(team)
            while team_members:
                embed = discord.Embed(
                    title=f"Report Summary: `{first}` - `{last}`",
                    color=discord.Color.gold(),
                    description=f"Hola, {team}! Here's a summary of last week's reports. Please review progress of members from last week, including those who did not submit reports. Thank you!",
                )

                for next_member in team_members[:25]:
                    embed.add_field(
                        name=f"{next_member.status_emoji} `{next_member.name.title()}`",
                        value=f"{next_member.report[:1024] if next_member.report else 'missing :('}",
                    )
                    if len(embed) > 6000:
                        embed.remove_field(-1)
                        break
                    team_members.remove(next_member)
                await team_leads_ch.send(embed=embed)
            grading_deadline = discord.utils.utcnow() + datetime.timedelta(days=3)
            review_embed = discord.Embed(
                title="Begin Report Review",
                color=discord.Color.brand_red(),
                description=f"In order to provide members with reliable feedback about their performance in MIL, please complete a brief review of each member's reports. Grading reports provides members a method of evaluating their current status in MIL.\n* Reports are graded on a scale of green-yellow-red (green indicating the best performance).\n* Please complete grading by {discord.utils.format_dt(grading_deadline, 'F')} ({discord.utils.format_dt(grading_deadline, 'R')}).",
            )
            await team_leads_ch.send(
                embed=review_embed,
                view=StartReviewView(self.bot),
            )

    @run_on_weekday([calendar.MONDAY, calendar.WEDNESDAY], 0, 0)
    async def update_report_channel(self):
        channel_history = [
            m
            async for m in self.bot.member_services_channel.history(
                limit=1,
            )
        ]
        if not channel_history:
            return

        last_message = channel_history[0]
        if last_message.author == self.bot.user:
            await last_message.edit(view=ReportsView(self.bot))

    @commands.is_owner()
    @commands.command()
    async def reportview(self, ctx):
        embed = discord.Embed(
            title="Submit your Weekly Progress Report",
            description="In order to keep all members on track, we ask that you complete a weekly report detailing your trials/contributions for the previous week. This is required for all members on all teams.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="📝 __How to Submit__",
            value="To submit your report, click the button below. In your report, aim for:\n1. **1-2 sentences** describing your progress this week.\n2. **Specific details** about what you worked on. Make sure to mention any specific tasks, projects, or people you worked with.",
            inline=False,
        )
        embed.add_field(
            name="📅 __Deadline__",
            value="Reports are due by **Sunday night at 11:59pm**. We cannot accept late reports.",
            inline=False,
        )
        embed.add_field(
            name="📊 __Grading__",
            value="Reports are graded on a scale of **green-yellow-red** (green indicating the best performance).\n* ✅ **Green**: Report demonstrated an actionable attempt at 3 hours of work.\n* ⚠️ **Yellow**: Report demonstrated 0-1 hours of work. (ie, installing a basic software package or reading a tutorial)\n* ❌ **Red**: Report was missing or no work was demonstrated.\nThese details are tracked over a semester using the **missing index**. A yellow report adds +0.5; a red report adds +1. Upon reaching 4, you will be automatically removed from MIL.",
            inline=False,
        )
        embed.add_field(
            name="🔍 __Review__",
            value="After submitting your report, a leader will review your report. If you were graded yellow or red, you will be notified via email.",
            inline=False,
        )
        embed.add_field(
            name="📈 __History__",
            value="To view your report history, click the button below.",
            inline=False,
        )
        embed.set_footer(text="If you have any questions, please contact a leader.")
        await ctx.send(embed=embed, view=ReportsView(self.bot))


async def setup(bot: MILBot):
    await bot.add_cog(ReportsCog(bot))
