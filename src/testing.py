from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from discord.ext import commands

from src.utils import DateTransformer, EmojiEmbed, TimeTransformer

from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


class MemberTestingAttendance(Enum):
    CANNOT = "cannot"
    CANNOTDRIVE = "cannotdrive"
    CANDRIVE = "candrive"
    CANDRIVESUB = "candrivesub"

    @property
    def english_title(self) -> str:
        return {
            self.CANNOT: "I cannot come",
            self.CANNOTDRIVE: "I can come, but need a ride",
            self.CANDRIVE: "I can come, and will bring my car",
            self.CANDRIVESUB: "I can come, and drive the sub",
        }[self]

    @property
    def emoji(self) -> str:
        return {
            self.CANNOT: "❌",
            self.CANNOTDRIVE: "🚶",
            self.CANDRIVE: "🚗",
            self.CANDRIVESUB: "🤿",
        }[self]


@dataclass
class TestingAttendance:
    cannot: list[discord.Member]
    cannotdrive: list[discord.Member]
    candrive: list[discord.Member]
    candrivesub: list[discord.Member]

    @property
    def attending(self) -> list[discord.Member]:
        return self.candrive + self.candrivesub + self.cannotdrive

    def members_with_state(
        self,
        state: MemberTestingAttendance,
    ) -> list[discord.Member]:
        return {
            MemberTestingAttendance.CANNOT: self.cannot,
            MemberTestingAttendance.CANNOTDRIVE: self.cannotdrive,
            MemberTestingAttendance.CANDRIVE: self.candrive,
            MemberTestingAttendance.CANDRIVESUB: self.candrivesub,
        }[state]


class TestingSignUpSelect(discord.ui.Select):
    def __init__(self, bot: MILBot, vehicle: str):
        self.bot = bot
        values = list(MemberTestingAttendance)
        if vehicle != "SubjuGator":
            values.remove(MemberTestingAttendance.CANDRIVESUB)
        options = []
        for value in values:
            options.append(
                discord.SelectOption(
                    label=value.english_title,
                    value=value.value,
                    emoji=value.emoji,
                ),
            )
        super().__init__(
            custom_id="testing_signup:select",
            placeholder="Please respond with your availability...",
            max_values=1,
            options=options,
        )

    async def parse_embed_field(
        self,
        embed: discord.Embed,
        field_name: str,
    ) -> list[discord.Member]:
        """
        Parses the value of the embed, assuming that it is a new-line Markdown
        bulleted list of member mentions.
        """
        value = self.get_field_named(embed, field_name)
        if value == "":
            return []
        raw_mentions = value.split("\n")
        ids = []
        for mention_str in raw_mentions:
            id = re.findall(r"<@!?(\d+)>", mention_str)
            if id:
                ids.append(int(id[0]))
        members = [await self.bot.get_member(id) for id in ids]
        return members

    def get_field_named(self, embed: discord.Embed, field_name: str) -> str:
        for field in embed.fields:
            if f"__{field_name}__" in str(field.name):
                return field.value or ""
        return ""

    def max_people(self, embed: discord.Embed) -> int:
        value = self.get_field_named(embed, "Max People")
        return int(re.findall(r"\d+", value)[0])

    async def parse_embed(self, embed: discord.Embed) -> TestingAttendance:
        cannot = await self.parse_embed_field(embed, "I cannot come")
        cannotdrive = await self.parse_embed_field(embed, "I can come, but need a ride")
        candrive = await self.parse_embed_field(
            embed,
            "I can come, and will bring my car",
        )
        candrivesub = await self.parse_embed_field(
            embed,
            "I can come, and drive the sub",
        )
        return TestingAttendance(cannot, cannotdrive, candrive, candrivesub)

    def replace_embed_value(
        self,
        embed: discord.Embed,
        field_name: str,
        new_value: str,
    ):
        for i, field in enumerate(embed.fields):
            if field_name in str(field.name):
                embed.set_field_at(i, name=field.name, value=new_value, inline=False)
                break

    def format_members(self, members: list[discord.Member]) -> str:
        if not members:
            return "_No members yet._"
        return "\n".join([f"* {member.mention}" for member in members])

    async def callback(self, interaction: discord.Interaction):
        message = interaction.message
        if message is None or not isinstance(interaction.user, discord.Member):
            return  # will never happen (component interaction)

        embed = message.embeds[0]
        attendance = await self.parse_embed(embed)

        value = self.values[0]
        state = MemberTestingAttendance(value)

        if state is not MemberTestingAttendance.CANNOT and len(
            attendance.attending,
        ) >= self.max_people(embed):
            await interaction.response.send_message(
                "Sorry, the maximum number of people have already signed up.",
                ephemeral=True,
            )
            return

        embed_field_name = state.english_title
        members_with_state = attendance.members_with_state(state)

        # If member already in list, remove them. Otherwise, add them.
        if interaction.user in members_with_state:
            members_with_state.remove(interaction.user)
            self.replace_embed_value(
                embed,
                embed_field_name,
                self.format_members(members_with_state),
            )
            await interaction.response.send_message(
                "You have been removed from the list.",
                ephemeral=True,
            )
        else:
            # If the user is already in another list, remove them from that list.
            for state in MemberTestingAttendance:
                cur_state = attendance.members_with_state(state)
                if interaction.user in cur_state:
                    cur_state.remove(interaction.user)
                    self.replace_embed_value(
                        embed,
                        state.english_title,
                        self.format_members(cur_state),
                    )

            members_with_state.append(interaction.user)
            self.replace_embed_value(
                embed,
                embed_field_name,
                self.format_members(members_with_state),
            )
            await interaction.response.send_message(
                "Your response was recorded!",
                ephemeral=True,
            )

        if not interaction.message:
            raise ValueError(
                "Interaction message is None. This should not happen for component interactions!",
            )
        await interaction.message.edit(embed=embed)


class TestingSignUpView(MILBotView):
    def __init__(self, bot: MILBot, vehicle: str):
        super().__init__(timeout=None)
        self.add_item(TestingSignUpSelect(bot, vehicle))


class TestingCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    @app_commands.command()
    @app_commands.describe(
        vehicle="The vehicle being tested",
        date="The date of the testing, formatted as YYYY-mm-dd",
        location="The location of the testing",
        arrive_time="The time we will arrive at the testing site, formatted as HH:MM PM",
        max_people="The maximum number of people who can attend",
    )
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
            description=f"{interaction.user.mention} has indicated that a testing is taking place soon. Having members come to testing is super helpful to streamlining the testing process, and for making the testing experience great for everyone. We'd appreciate if you could make it!",
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
        states = list(MemberTestingAttendance)
        if vehicle != "SubjuGator":
            states.remove(MemberTestingAttendance.CANDRIVESUB)
        for state in states:
            embed.add_field(
                emoji=state.emoji,
                name=state.english_title,
                value="_No members yet._",
                inline=False,
            )
        mention = (
            self.bot.leaders_role.mention
            if interaction.channel == self.bot.leaders_channel
            else self.bot.egn4912_role.mention
        )
        await interaction.response.send_message(
            mention,
            embed=embed,
            view=TestingSignUpView(self.bot, vehicle),
        )


async def setup(bot: MILBot):
    await bot.add_cog(TestingCog(bot))
