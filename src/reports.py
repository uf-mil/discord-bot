from __future__ import annotations

import calendar
import datetime
import enum
import itertools
import logging
from dataclasses import dataclass
from enum import auto
from typing import TYPE_CHECKING

import discord
import gspread
import gspread_asyncio
from discord.ext import commands

from .tasks import run_on_weekday
from .utils import is_active
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class ReportsModal(discord.ui.Modal):
    name = discord.ui.TextInput(label="Name", placeholder="Albert Gator")
    ufid = discord.ui.TextInput(
        label="UFID",
        placeholder="86753099",
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
        if self.team.value.lower() not in ["electrical", "mechanical", "software"]:
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
            await main_worksheet.cell(name_cell.row, self.bot.reports_cog.UFID_COLUMN)
        ).value != self.ufid.value:
            await interaction.edit_original_response(
                content="❌ The UFID you entered does not match the one we have on file!",
                attachments=[],
            )
            return

        # Calculate column to log in.
        first_date = self.bot.reports_cog.FIRST_DATE
        today = datetime.date.today()
        week = self.bot.reports_cog.date_to_column(today)

        # Log a Y for their square
        if (
            await main_worksheet.cell(
                name_cell.row,
                week + self.bot.reports_cog.TOTAL_COLUMNS,
            )
        ).value:
            await interaction.edit_original_response(
                content="❌ You've already submitted a report for this week!",
                attachments=[],
            )
            return

        await main_worksheet.update_cell(
            name_cell.row,
            self.bot.reports_cog.TEAM_COLUMN,
            self.team.value.title(),
        )
        await main_worksheet.update_cell(
            name_cell.row,
            self.bot.reports_cog.DISCORD_NAME_COLUMN,
            str(interaction.user),
        )
        await main_worksheet.update_cell(
            name_cell.row,
            week + self.bot.reports_cog.TOTAL_COLUMNS,
            "Y",
        )

        # Add a comment with their full report in the cell
        a1_notation = gspread.utils.rowcol_to_a1(name_cell.row, week + self.bot.reports_cog.TOTAL_COLUMNS)  # type: ignore
        await main_worksheet.update(
            a1_notation,
            [
                [
                    f"{self.report.value} (submitted at {datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S')})",
                ],
            ],
        )

        week_date = first_date + datetime.timedelta(days=(week - 1) * 7)
        month_date_formatted = week_date.strftime("%B %d, %Y")
        receipt = discord.Embed(
            title="Weekly Report Receipt",
            description=f"Here's a copy of your report for the week of **{month_date_formatted}** for your records. If you need to make any changes, please contact your team leader.",
            color=discord.Color.blue(),
        )
        receipt.add_field(name="Name", value=self.name.value, inline=True)
        receipt.add_field(name="Team", value=self.team.value, inline=True)
        receipt.add_field(name="Report", value=self.report.value, inline=False)
        receipt.set_footer(text="Thank you for your hard work!")
        try:
            await interaction.user.send(embed=receipt)
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="✅ Your report was successfully submitted. However, you do not have direct messages enabled, so we were unable to send you a receipt.",
                attachments=[],
            )
        else:
            await interaction.edit_original_response(
                content="✅ Successfully logged your report! A receipt of your report has been sent to you through direct messages. Thank you!",
                attachments=[],
            )


class ReportsView(MILBotView):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Submit your report!",
        style=discord.ButtonStyle.green,
        custom_id="reports_view:submit",
    )
    async def submit(self, interaction: discord.Interaction, _: discord.ui.Button):
        # If button is triggered on Sunday or Monday, send error message
        if datetime.datetime.today().weekday() in [0, 1]:
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


class Team(enum.Enum):
    SOFTWARE = auto()
    ELECTRICAL = auto()
    MECHANICAL = auto()
    SYSTEMS = auto()

    @classmethod
    def from_str(cls, ss_str: str) -> Team:
        if "software" in ss_str.lower():
            return cls.SOFTWARE
        if "electrical" in ss_str.lower():
            return cls.ELECTRICAL
        if "mechanical" in ss_str.lower():
            return cls.MECHANICAL
        return cls.SYSTEMS

    def __str__(self) -> str:
        return self.name.title()


@dataclass
class Student:
    name: str
    discord_id: str
    member: discord.Member | None
    team: Team
    report: str

    @property
    def first_name(self) -> str:
        return str(self.name).split(" ")[0]

    @property
    def status_emoji(self) -> str:
        return "✅" if self.report else "❌"


class ReportsCog(commands.Cog):

    NAME_COLUMN = 1
    EMAIL_COLUMN = 2
    UFID_COLUMN = 3
    LEADERS_COLUMN = 4
    TEAM_COLUMN = 5
    DISCORD_NAME_COLUMN = 6

    FIRST_DATE = datetime.date(2024, 1, 15)  # TODO: Make this automatically derived

    TOTAL_COLUMNS = 6

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.post_reminder.start(self)
        self.last_week_summary.start(self)
        self.individual_reminder.start(self)

    def date_to_column(self, date: datetime.date) -> int:
        """
        Converts a date to the relevant column number.

        The column number is the number of weeks since the first date.
        """
        return (date - self.FIRST_DATE).days // 7 + 1

    @run_on_weekday(calendar.FRIDAY, 12, 0, check=is_active)
    async def post_reminder(self):
        general_channel = self.bot.general_channel
        return await general_channel.send(
            f"{self.bot.egn4912_role.mention}\nHey everyone! Friendly reminder to submit your weekly progress reports by **Sunday night at 11:59pm**. You can submit your reports in the {self.bot.reports_channel.mention} channel. If you have any questions, please contact your leader. Thank you!",
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
        names = await self.safe_col_values(main_worksheet, self.NAME_COLUMN)
        discord_ids = await self.safe_col_values(
            main_worksheet,
            self.DISCORD_NAME_COLUMN,
        )
        teams = await self.safe_col_values(main_worksheet, self.TEAM_COLUMN)
        col_vals = await main_worksheet.col_values(column)
        students = list(itertools.zip_longest(names, discord_ids, teams, col_vals))

        res: list[Student] = []
        for name, discord_id, team, value in students[2:]:  # (skip header rows)
            member = self.bot.active_guild.get_member_named(str(discord_id))
            res.append(
                Student(name, discord_id, member, Team.from_str(team), str(value)),
            )
        res.sort(key=lambda s: s.first_name)
        return res

    @run_on_weekday(calendar.SUNDAY, 12, 0, check=is_active)
    async def individual_reminder(self):
        # Get all members who have not completed reports for the week
        await self.bot.sh.get_worksheet(0)
        today = datetime.date.today()
        week = self.date_to_column(today)
        column = week + self.TOTAL_COLUMNS

        students = await self.students_status(column)

        deadline_tonight = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time(23, 59, 59),
        )
        for student in students:
            if student.member and not student.report:
                try:
                    await student.member.send(
                        f"Hey **{student.first_name}**! It's your friendly uf-mil-bot here. I noticed you haven't submitted your weekly MIL report yet. Please submit it in the {self.bot.reports_channel.mention} channel by {discord.utils.format_dt(deadline_tonight, 't')} tonight. Thank you!",
                    )
                    logger.info(f"Sent individual report reminder to {student.member}.")
                except discord.Forbidden:
                    logger.info(
                        f"Could not send individual report reminder to {student.member}.",
                    )

    @run_on_weekday(calendar.MONDAY, 0, 0)
    async def last_week_summary(self):
        """
        Gives leaders a list of who submitted reports and who did not.
        """
        await self.bot.sh.get_worksheet(0)

        # Calculate the week number and get the column
        today = datetime.date.today()
        week = self.date_to_column(today)
        column = week + self.TOTAL_COLUMNS - 1  # -1 because the week has now passed

        # Get all members who have not completed reports for the week
        students = await self.students_status(column)

        # Generate embed
        first_day_of_week = self.FIRST_DATE + datetime.timedelta(days=(week - 1) * 7)
        last_day_of_week = first_day_of_week + datetime.timedelta(days=6)
        first = first_day_of_week.strftime("%B %-d, %Y")
        last = last_day_of_week.strftime("%B %-d, %Y")
        for team in Team:
            field_count = 0
            team_members = [s for s in students if s.team == team]
            if not team_members:
                continue
            while field_count < 25 and team_members:
                embed = discord.Embed(
                    title=f"Report Summary: `{first}` - `{last}`",
                    color=discord.Color.gold(),
                    description=f"Hola, {team}! Here's a summary of last week's reports. Please review progress of members from last week, including those who did not submit reports. Thank you!",
                )

                for next_member in team_members[:25]:
                    embed.add_field(
                        name=f"{next_member.status_emoji} `{next_member.name.title()}`",
                        value=f"{next_member.report or 'missing :('}",
                    )
                    team_members.remove(next_member)
                team_leads_ch = self.bot.team_leads_ch(team)
                await team_leads_ch.send(embed=embed)

    @commands.is_owner()
    @commands.command()
    async def reportview(self, ctx):
        embed = discord.Embed(
            title="Submit your Weekly Progress Report",
            description="In order to keep all members on track, we ask that you complete a weekly report detailing your trials/contributions for the previous week. This is required for all members on all teams.\n\nRemember that members signed up for zero credit hours are expected to work at least **three hours per week** in MIL to sustain their satisfactory grade. If you have any concerns, please contact a leader!",
            color=discord.Color.blue(),
        )
        questions = [
            {
                "question": "How long do our weekly reports need to be?",
                "answer": "Roughly one to two sentences is appropriate. We just want to know what you've been working on!",
            },
            {
                "question": "I was unable to work three hours this week.",
                "answer": "No worries, we understand that life happens. Please explain the circumstances in your report, and your leaders will be happy to work with you. If this becomes a recurring issue, please contact your leaders immediately to find an acceptable solution.",
            },
            {
                "question": "I'm not sure what to write in my report.",
                "answer": "If you're not sure what to write, try to answer the following questions:\n- What did you work on this week?\n- What did you learn this week?\n- What do you plan to work on next week?",
            },
            {
                "question": "How do we complete a report if we work on multiple teams?",
                "answer": "Please complete the report for the team you are most active with.",
            },
        ]
        for question in questions:
            embed.add_field(
                name=question["question"],
                value=question["answer"],
                inline=False,
            )
        await ctx.send(embed=embed, view=ReportsView(self.bot))


async def setup(bot: MILBot):
    await bot.add_cog(ReportsCog(bot))
