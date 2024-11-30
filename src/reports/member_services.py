from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ..views import MILBotView
from .github_oauth import OauthSetupButton
from .sheets import Column, PreviousWeekColumn, WeekColumn

if TYPE_CHECKING:
    from ..bot import MILBot


logger = logging.getLogger(__name__)


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
        previous_semester = False
        try:
            week = WeekColumn.current()
        except RuntimeError:
            # current() was out of range; semester is over so let's use the final
            # week
            week = PreviousWeekColumn.final()
            previous_semester = True
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
        column = PreviousWeekColumn.first()
        for report, score in reports_scores:
            emoji = emojis.get(float(score) if score else score, "❓")
            # Format: May 13
            start_date = column.date_range[0].strftime("%B %-d")
            # 6000 is max embed size, and add one extra report to acct for other text
            max_report_size = int(6000 / (len(reports_scores) + 1))
            capped_report = (
                f"* {report}"
                if len(report) < max_report_size
                else f"* {report[:max_report_size]}..."
            )
            if score and float(score):
                capped_report += (
                    f"\n* **This report added +{float(score)} to your missing score.**"
                )
            is_current_week = (
                column == WeekColumn.current() if not previous_semester else False
            )
            header = f"{emoji} Week of `{start_date}`"
            if is_current_week:
                next_iteration = self.bot.reports_cog.regular_refresh.next_iteration
                if next_iteration is None:
                    raise RuntimeError("No next iteration found.")
                next_iteration_formatted = next_iteration.astimezone().strftime(
                    "%A, %B %d at %I:%M %p",
                )
                header = (
                    f"{emoji} Current Week (next refresh: {next_iteration_formatted})"
                )
            embed.add_field(
                name=header,
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
        self.add_item(OauthSetupButton(bot))
        self.add_item(ReportHistoryButton(bot))
