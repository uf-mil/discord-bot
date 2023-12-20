from __future__ import annotations

import calendar
import datetime
import itertools
import logging
from typing import TYPE_CHECKING

import discord
import gspread
from discord.ext import commands

from .helper import run_on_weekday
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

    NAME_COLUMN = 1
    UFID_COLUMN = 2
    LEADERS_COLUMN = 3
    TEAM_COLUMN = 4
    DISCORD_NAME_COLUMN = 5

    TOTAL_COLUMNS = 5

    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(title="Weekly Report")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"{self.bot.loading_emoji} Attempting to save your report...",
            ephemeral=True,
        )

        # Validate input
        # Check that team is one of the three
        if self.team.value.lower() not in ["electrical", "mechanical", "software"]:
            await interaction.edit_original_response(
                content="❌ Please enter a valid team name! (`Electrical`, `Mechanical`, or `Software`)",
            )
            return

        # Find users name in the main sheet
        main_worksheet = await self.bot.sh.get_worksheet(0)
        name_cell = await main_worksheet.find(self.name.value)

        # If name not found, return
        if name_cell is None:
            await interaction.edit_original_response(
                content="❌ We couldn't find your name in the main spreadsheet. Are you registered for EGN4912?",
            )
            return

        # Ensure UFID matches
        if (await main_worksheet.cell(name_cell.row, 2)).value != self.ufid.value:
            await interaction.edit_original_response(
                content="❌ The UFID you entered does not match the one we have on file!",
            )
            return

        # Calculate column to log in.
        first_date = datetime.date(2023, 9, 24)
        today = datetime.date.today()
        week = (today - first_date).days // 7 + 1

        # Log a Y for their square
        if (
            await main_worksheet.cell(name_cell.row, week + self.TOTAL_COLUMNS)
        ).value == "Y":
            await interaction.edit_original_response(
                content="❌ You've already submitted a report for this week!",
            )
            return

        await main_worksheet.update_cell(
            name_cell.row,
            self.TEAM_COLUMN,
            self.team.value.title(),
        )
        await main_worksheet.update_cell(
            name_cell.row,
            self.DISCORD_NAME_COLUMN,
            str(interaction.user),
        )
        await main_worksheet.update_cell(name_cell.row, week + self.TOTAL_COLUMNS, "Y")

        # Add a comment with their full report
        a1_notation = gspread.utils.rowcol_to_a1(name_cell.row, week + self.TOTAL_COLUMNS)  # type: ignore
        await main_worksheet.insert_note(
            a1_notation,
            f"{self.report.value}\n\n(submitted at {datetime.datetime.now().strftime('%m/%d/%Y %H:%M:%S')})",
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
            )
        else:
            await interaction.edit_original_response(
                content="✅ Successfully logged your report! A receipt of your report has been sent to you through direct messages. Thank you!",
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
        if datetime.datetime.today().weekday() in [6, 0]:
            return await interaction.response.send_message(
                ":x: Weekly reports should be submitted between Tuesday and Saturday. While occasional exceptions can be made if you miss a week—simply inform your team lead—this should not become a regular occurrence. Be aware that the submission window closes promptly at 11:59pm on Saturday.",
                ephemeral=True,
            )

        if not is_active():
            return await interaction.response.send_message(
                "❌ The weekly reports system is currently inactive due to the interim period between semesters. Please wait until next semester to document any work you have completed in between semesters. Thank you!",
                ephemeral=True,
            )

        # Send modal where user fills out report
        await interaction.response.send_modal(ReportsModal(self.bot))


class ReportsCog(commands.Cog):

    TOTAL_COLUMNS = 5

    def __init__(self, bot: MILBot):
        self.bot = bot
        self._tasks = set()
        self._tasks.add(self.bot.loop.create_task(self.post_reminder()))
        self._tasks.add(self.bot.loop.create_task(self.add_no()))
        self._tasks.add(self.bot.loop.create_task(self.individual_reminder()))

    @run_on_weekday(calendar.FRIDAY, 12, 0, check=is_active)
    async def post_reminder(self):
        general_channel = self.bot.general_channel
        return await general_channel.send(
            f"{self.bot.egn4912_role.mention}\nHey everyone! Friendly reminder to submit your weekly progress reports by **tomorrow night at 11:59pm**. You can submit your reports in the {self.bot.reports_channel.mention} channel. If you have any questions, please contact your leader. Thank you!",
        )

    @run_on_weekday(calendar.SATURDAY, 12, 0, check=is_active)
    async def individual_reminder(self):
        # Get all members who have not completed reports for the week
        main_worksheet = await self.bot.sh.get_worksheet(0)
        first_date = datetime.date(2023, 9, 24)
        today = datetime.date.today()
        week = (today - first_date).days // 7 + 1
        column = week + self.TOTAL_COLUMNS

        names = await main_worksheet.col_values(1)
        discord_ids = await main_worksheet.col_values(5)
        col_vals = await main_worksheet.col_values(column)
        students = list(itertools.zip_longest(names, discord_ids, col_vals))

        deadline_tonight = datetime.datetime.combine(
            datetime.date.today(),
            datetime.time(23, 59, 59),
        )
        for name, discord_id, value in students:
            member = self.bot.active_guild.get_member_named(str(discord_id))
            first_name = str(name).split(" ")[0]
            if member and value != "Y":
                try:
                    await member.send(
                        f"Hey **{first_name}**! It's your friendly uf-mil-bot here. I noticed you haven't submitted your weekly MIL report yet. Please submit it in the {self.bot.reports_channel.mention} channel by {discord.utils.format_dt(deadline_tonight, 't')} tonight. Thank you!",
                    )
                    logger.info(f"Sent individual report reminder to {member}.")
                except discord.Forbidden:
                    logger.info(
                        f"Could not send individual report reminder to {member}.",
                    )

    @run_on_weekday(calendar.SUNDAY, 0, 0, check=is_active)
    async def add_no(self):
        main_worksheet = await self.bot.sh.get_worksheet(0)

        # Calculate the week number and get the column
        first_date = datetime.date(2023, 9, 24)
        today = datetime.date.today()
        week = (today - first_date).days // 7 + 1
        column = week + self.TOTAL_COLUMNS - 1  # -1 because the week has now passed

        # Add a "N" to all rows that do not currently have a value
        names = await main_worksheet.col_values(1)
        col_vals = await main_worksheet.col_values(column)
        name_vals = list(itertools.zip_longest(names, col_vals))
        new_cells: list[gspread.Cell] = []
        for i, (name, val) in enumerate(name_vals):
            # Skip header row
            if (i + 1) < 3:
                continue
            if name and not val:
                new_cells.append(gspread.Cell(i + 1, column, "N"))
            elif val:
                new_cells.append(gspread.Cell(i + 1, column, val))
        await main_worksheet.update_cells(new_cells)

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
