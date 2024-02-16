from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from discord.ext import commands

from src.utils import DateTransformer, EmojiEmbed, TimeTransformer

from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


class TestingSignUpSelect(discord.ui.Select):
    def __init__(self, vehicle: str):
        options = [
            discord.SelectOption(label="I cannot come", value="no", emoji="❌"),
            discord.SelectOption(
                label="I can come, but need a ride",
                value="cannotdrive",
                emoji="🚶",
            ),
            discord.SelectOption(
                label="I can come, and will bring my car",
                value="candrive",
                emoji="🚗",
            ),
        ]
        if vehicle == "SubjuGator":
            options.append(
                discord.SelectOption(
                    label="I can come, and drive the sub",
                    value="candrivesub",
                    emoji="🤿",
                ),
            )
        super().__init__(
            custom_id="testing_signup:select",
            placeholder="Please respond with your availability...",
            max_values=1,
            options=options,
        )


class TestingSignUpView(MILBotView):
    def __init__(self, vehicle: str):
        super().__init__(timeout=None)
        self.add_item(TestingSignUpSelect(vehicle))


class TestingCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.has_role("Leaders")
    async def testing(
        self,
        interaction: discord.Interaction,
        vehicle: Literal["SubjuGator", "NaviGator", "Other"],
        date: app_commands.Transform[datetime.date, DateTransformer],
        location: str,
        arrive_time: app_commands.Transform[datetime.time, TimeTransformer],
        max_people: int = 10,
    ):
        embed = EmojiEmbed(
            title="Upcoming Testing: Are you going?",
            color=discord.Color.from_str("0x5BCEFA"),
            description="A leader has indicated that a testing is taking place soon. Having members come to testing is super helpful to streamlining the testing process, and for making the testing experience great for everyone. We'd appreciate if you could make it!",
        )
        arrive_dt = datetime.datetime.combine(date, arrive_time)
        prep_dt = arrive_dt - datetime.timedelta(minutes=60)
        date_str = f"{discord.utils.format_dt(arrive_dt, 'D')} ({discord.utils.format_dt(arrive_dt, 'R')})"
        embed.add_field(emoji="🚀", name="Vehicle", value=vehicle, inline=True)
        embed.add_field(emoji="📍", name="Location", value=location, inline=True)
        embed.add_field(
            emoji="👥",
            name="Max People",
            value=f"{max_people} people",
            inline=True,
        )
        embed.add_field(emoji="📅", name="Date", value=date_str, inline=True)
        embed.add_field(
            emoji="⏰",
            name="Prep Time",
            value=discord.utils.format_dt(prep_dt, "t"),
            inline=True,
        )
        embed.add_field(
            emoji="⏰",
            name="Testing Starts",
            value=discord.utils.format_dt(arrive_dt, "t"),
            inline=True,
        )
        mention = (
            self.bot.leaders_role.mention
            if interaction.channel == self.bot.leaders_channel
            else self.bot.egn4912_role
        )
        await interaction.response.send_message(
            mention,
            embed=embed,
            view=TestingSignUpView(vehicle),
        )


async def setup(bot: MILBot):
    await bot.add_cog(TestingCog(bot))
