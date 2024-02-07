from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import discord
import icalendar
import recurring_ical_events
from discord.ext import commands, tasks

from .reports import Team

if TYPE_CHECKING:
    from .bot import MILBot


class EventType(Enum):
    GBM = "[GBM]"
    SUBTEAM = "[SUBTEAM]"
    OFFICE_HOURS = "[OH]"
    EVENT = "[EVENT]"
    TEAM_MEETING = "[MEETING]"

    def emoji(self) -> str:
        emojis = {
            EventType.GBM: "📢",
            EventType.SUBTEAM: "📋",
            EventType.OFFICE_HOURS: "🕒",
            EventType.EVENT: "📅",
            EventType.TEAM_MEETING: "📝",
        }
        return emojis.get(self, "❓")


class StatusChannelName(Enum):
    OPEN = "✅-lab-open"
    CLOSED = "❌-lab-closed"
    MAYBE = "🤔-lab-maybe-open"


@dataclass
class Event:
    title: str
    start: datetime.datetime
    end: datetime.datetime
    location: str
    type: EventType
    team: Team

    @staticmethod
    def get_type(title: str) -> tuple[EventType, str]:
        for event_type in EventType:
            if event_type.value in title:
                return event_type, title.replace(event_type.value, "")
        return EventType.EVENT, title

    @classmethod
    def from_ical_event(cls, event: icalendar.Event):
        # Make sure to parse vText too
        type, title = cls.get_type(event.get("summary").to_ical().decode("utf-8"))
        return cls(
            title=title,
            start=event.get("dtstart").dt,
            end=event.get("dtend").dt,
            location=event.get("location").to_ical().decode("utf-8"),
            type=type,
            team=Team.SOFTWARE,
        )

    def embed_str(self) -> str:
        return f"{self.type.emoji()} {discord.utils.format_dt(self.start, 't')} - {discord.utils.format_dt(self.end, 't')}: **{self.title}**"


class Calendar(commands.Cog):

    OPEN_HOURS = (datetime.time(9, 0), datetime.time(18, 0))

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.calendar.start()

    async def load_calendar(self, url: str) -> list[Event]:
        response = await self.bot.session.get(url)
        self.ics = icalendar.Calendar.from_ical(await response.read())
        today = datetime.date.today()
        end_of_week = today + datetime.timedelta(days=3)
        events = recurring_ical_events.of(self.ics).between(today, end_of_week)
        cal_events = []
        for event in events:
            cal_events.append(Event.from_ical_event(event))
        return cal_events

    def calendar_channel(self) -> discord.TextChannel:
        for value in StatusChannelName:
            channel = discord.utils.get(
                self.bot.active_guild.text_channels,
                name=value.value,
            )
            if channel:
                return channel
        raise ValueError("No calendar channel found!")

    async def update_channel_name(self, events: list[Event]) -> None:
        for event in events:
            if event.start < discord.utils.utcnow() < event.end:
                channel = self.calendar_channel()
                if channel.name != StatusChannelName.OPEN.value:
                    await channel.edit(name=StatusChannelName.OPEN.value)
                return
        channel = self.calendar_channel()
        if self.OPEN_HOURS[0] < datetime.datetime.now().time() < self.OPEN_HOURS[1]:
            if channel.name != StatusChannelName.MAYBE.value:
                await channel.edit(name=StatusChannelName.MAYBE.value)
        else:
            if channel.name != StatusChannelName.CLOSED.value:
                await channel.edit(name=StatusChannelName.CLOSED.value)

    @tasks.loop(minutes=5)
    async def calendar(self):
        await self.bot.wait_until_ready()
        embed = discord.Embed(
            title="📆 Lab Calendar",
            color=discord.Color.brand_red(),
            description="Here's the calendar for the upcoming week. If you have any questions, feel free to ask!",
        )
        channel = self.calendar_channel()
        events = []
        for calendar in self.CALENDARS:
            events += await self.load_calendar(calendar)
        events.sort(key=lambda x: x.start)
        today_events = [
            event for event in events if event.start.date() == datetime.date.today()
        ]
        if today_events:
            embed.add_field(
                name="__Today's Events__",
                value="\n".join([event.embed_str() for event in today_events]),
                inline=False,
            )
        tomorrow_events = [
            event
            for event in events
            if event.start.date() == datetime.date.today() + datetime.timedelta(days=1)
        ]
        if tomorrow_events:
            embed.add_field(
                name="__Tomorrow's Events__",
                value="\n".join([event.embed_str() for event in tomorrow_events]),
                inline=False,
            )
        # Date formatted: Feb 2, 2024 03:56PM
        date_formatted = datetime.datetime.now().strftime("%b %d, %Y %I:%M%p")
        embed.set_footer(text=f"Last refershed: {date_formatted}")
        last_message = [m async for m in channel.history(limit=1)]
        if not last_message:
            await channel.send(embed=embed)
        else:
            await last_message[0].edit(embed=embed)
        await self.update_channel_name(events)


async def setup(bot: MILBot):
    await bot.add_cog(Calendar(bot))
