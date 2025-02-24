from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import discord

from ..constants import Team
from ..views import MILBotView
from .emails import (
    FiringEmail,
    InsufficientReportEmail,
    PoorReportEmail,
    SufficientReportEmail,
)
from .sheets import Student, WeekColumn

if TYPE_CHECKING:
    from ..bot import MILBot


logger = logging.getLogger(__name__)


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
        disabled: bool = False,
    ):
        self.bot = bot
        self.student = student
        super().__init__(
            style=style,
            label=label,
            emoji=emoji,
            row=row,
            disabled=disabled,
        )

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
        col = WeekColumn.previous().score_column
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
        logger.info(f"{interaction.user} graded {self.student.name} as Red/Negative.")
        await self.respond_early(
            interaction,
            f"{self.bot.loading_emoji} Logging score and sending email to student...",
        )
        # 1. Log score to spreadsheet
        await self.log_score(1)
        # Determine action for student based on their current score
        new_score = self.student.total_score + 1

        # Notify necessary people
        if new_score >= 4:
            # Student needs to be fired
            logger.warning(
                f"Sending firing email for {self.student} (new score: {new_score} > 4)...",
            )
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
        logger.info(f"{interaction.user} graded {self.student.name} as Yellow.")
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
            logger.warning(
                f"Sending firing email for {self.student} (new score: {new_score} > 4)...",
            )
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
    def __init__(self, bot: MILBot, student: Student, disabled: bool = False):
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
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"{interaction.user} graded {self.student.name} as Green/Good.")
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
        logger.info(f"{interaction.user} skipped {self.student.name}.")
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
        self.add_item(GoodReportButton(bot, student, disabled=not self.student.report))
        self.add_item(SkipReportButton(bot, student))


class StartReviewView(MILBotView):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)

    def _add_issue_links(self, content: str) -> str:
        return re.sub(
            r"([a-zA-Z._-]+)\/([a-zA-Z._-]+)\#(\d+)",
            r"[\1/\2#\3](https://github.com/\1/\2/issues/\3)",
            content,
        )

    def _parsed_report_embed(
        self,
        content: str,
        student: Student,
        color: discord.Color,
    ) -> tuple[discord.Embed, discord.File | None]:
        """
        Parses a str in the format of (any of the fields could be missing):

        **Comments:**
        * owner/repo#num ("title"): "comment"

        **Issues Opened:**
        * owner/repo#num ("title")

        **Pull Requests Opened:**
        * owner/repo#num ("title")

        **Commits:**
        * <discord_time> owner/repo @ sha (message)
        """
        embed = discord.Embed(
            title=f"{student.name}",
            color=color,
        )
        file = None
        if student.member:
            file = self.bot.get_headshot(student.member)
            if file:
                embed.set_thumbnail(url=f"attachment://{file.filename}")
        included_fields = content.split("\n\n")
        field_emojis = {
            "**Commits**:": "🔨",
            "**Issues Opened**:": "📥",
            "**Pull Requests Opened**:": "📤",
            "**Comments**:": "💬",
            "**Wiki Contributions**:": "📖",
        }
        for field in included_fields:
            if not field:
                continue
            field_name, *field_content = field.split("\n")
            field_emoji = field_emojis.get(field_name, "❓")
            max_entries_before_limit = []
            page = 1
            while field_content:
                entry = field_content.pop(0)
                entry = self._add_issue_links(entry)
                if len("\n".join([*max_entries_before_limit, entry])) > 1024:
                    # Make sure that the last entry isn't skipped
                    page_name = (
                        f"{field_emoji} {field_name} (page {page})"
                        if page > 1
                        else f"{field_emoji} {field_name}"
                    )
                    entry_content = "\n".join(max_entries_before_limit)
                    # Replace repo/owner#number with links
                    embed.add_field(
                        name=page_name,
                        value=entry_content,
                        inline=False,
                    )
                    max_entries_before_limit = []
                    page += 1
                max_entries_before_limit.append(entry)
            if max_entries_before_limit:
                page_name = (
                    f"{field_emoji} {field_name} (page {page})"
                    if page > 1
                    else f"{field_emoji} {field_name}"
                )
                entry_content = "\n".join(max_entries_before_limit)
                embed.add_field(
                    name=page_name,
                    value=entry_content,
                    inline=False,
                )
            if not field_content:
                continue
            embed.add_field(name=field_name, value=field_content[:1024], inline=False)
        return embed, file

    @discord.ui.button(
        label="Start Review",
        style=discord.ButtonStyle.green,
        custom_id="start_review:start",
    )
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button):
        # We can assume that this button was pressed in a X-leadership channel
        logger.info(f"{interaction.user} started the weekly report review process.")
        await interaction.response.send_message(
            f"{self.bot.loading_emoji} Thanks for starting this review! Pulling data...",
            ephemeral=True,
        )
        async with self.bot.db_factory() as db:
            connected_ids = [m.discord_id for m in await db.authenticated_members()]
        if not interaction.channel or isinstance(
            interaction.channel,
            discord.DMChannel,
        ):
            raise discord.app_commands.NoPrivateMessage

        team_name = str(interaction.channel.name).removesuffix("-leadership")
        team = Team.from_str(team_name)
        week = WeekColumn.previous()
        column = week.report_column
        students = await self.bot.reports_cog.students_status(column, refresh=False)
        students = [s for s in students if s.team == team and s.report_score is None]
        if not len(students):
            await interaction.edit_original_response(
                content="All responses for last week have already been graded! Nice job being proactive! 😊",
                view=None,
            )
            return
        else:
            for i, student in enumerate(students):
                logger.info(f"{interaction.user} is grading {student.name}...")
                view = ReportsReviewView(self.bot, student)
                color_percent = int(i / len(students) * 255)
                color = discord.Color.from_rgb(
                    color_percent,
                    color_percent,
                    color_percent,
                )
                embed, file = (
                    self._parsed_report_embed(student.report, student, color)
                    if student.report
                    else (None, None)
                )
                message = f"Please grade the report by **{student.name}**:"
                if not student.report:
                    message = f"❌ **{student.name}** did not complete any activity last week."
                if student.member.id not in connected_ids:
                    logger.warn(
                        f"{student.name} is not in list of connected GitHub IDs: {student.member.id} not in {connected_ids[:100]} (len: {len(connected_ids)})",
                    )
                    message = f"🚨 **{student.name}** has not connected their GitHub with the bot. Please reach out to them."
                await interaction.edit_original_response(
                    content=message,
                    view=view,
                    embed=embed,
                    attachments=[file] if file else [],
                )
                await view.wait()
            await interaction.edit_original_response(
                content="✅ Nice work. All reports have been graded. Thank you for your help!",
                view=None,
                embed=None,
                attachments=[await self.bot.good_job_gif()],
            )
        view = MILBotView()
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"Review completed by {interaction.user.display_name}",
                disabled=True,
            ),
        )
        assert isinstance(interaction.message, discord.Message)
        await interaction.message.edit(view=view)
