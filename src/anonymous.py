from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import discord

from .constants import SCHWARTZ_EMAIL
from .email import Email
from .views import MILBotModal, MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


IntendedTargets = Literal["schwartz", "operations", "leaders"]


@dataclass
class SchwartzAnonymousEmail(Email):
    def __init__(self, report: str):
        html = f"""A new anonymous report has been submitted. The report is as follows:

        <blockquote>{report}</blockquote>

        Replies to this email will not be received. Please address any concerns with the appropriate leadership team."""
        text = f"""A new anonymous report has been submitted. The report is as follows:

        {report}

        Replies to this email will not be received. Please address any concerns with the appropriate leadership team."""
        super().__init__(
            receiver_emails=[SCHWARTZ_EMAIL],
            subject="New Anonymous Report Received",
            html=html,
            text=text,
        )


class AnonymousReportModal(MILBotModal):

    report = discord.ui.TextInput(
        label="Report",
        placeholder="Enter your report here",
        style=discord.TextStyle.long,
        max_length=2000,
    )

    def __init__(self, bot: MILBot, target: IntendedTargets):
        self.bot = bot
        self.target = target
        super().__init__(title="Submit an Anonymous Report")

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="New Anonymous Report",
            color=discord.Color.light_gray(),
            description=self.report.value,
        )
        embed.set_footer(text="Submitted by an anonymous user")
        if self.target == "schwartz":
            await SchwartzAnonymousEmail(self.report.value).send()
        elif self.target == "operations":
            await self.bot.operations_leaders_channel.send(embed=embed)
        elif self.target == "leaders":
            await self.bot.leaders_channel.send(embed=embed)
        await interaction.response.send_message(
            "Your report has been submitted. Your input is invaluable, and we are committed to making MIL a better place for everyone. Thank you for helping us improve.",
            embed=embed,
            ephemeral=True,
        )


class AnonymousTargetSelect(discord.ui.Select):
    def __init__(self, bot: MILBot):
        self.bot = bot
        options = [
            discord.SelectOption(label="Dr. Schwartz", emoji="👨‍🏫", value="schwartz"),
            discord.SelectOption(
                label="Operations Leadership",
                emoji="👷",
                value="operations",
            ),
            discord.SelectOption(label="Leaders", emoji="👑", value="leaders"),
        ]
        super().__init__(
            placeholder="Select the target of your report",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        await interaction.response.send_modal(AnonymousReportModal(self.bot, target))  # type: ignore


class AnonymousReportView(MILBotView):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Submit an anonymous report",
        style=discord.ButtonStyle.red,
        custom_id="anonymous_report:submit",
    )
    async def submit_anonymous_report(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        view = MILBotView()
        view.add_item(AnonymousTargetSelect(self.bot))
        await interaction.response.send_message(
            "Select the target of your report.",
            view=view,
            ephemeral=True,
        )
