from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import discord
import icalendar
import recurring_ical_events
from discord.ext import commands, tasks

from .constants import Team
from .env import (
    ELECTRICAL_MEETINGS_CALENDAR,
    ELECTRICAL_OH_CALENDAR,
    GENERAL_CALENDAR,
    LEADERS_CALENDAR,
    MECHANICAL_MEETINGS_CALENDAR,
    MECHANICAL_OH_CALENDAR,
    SOFTWARE_MEETINGS_CALENDAR,
    SOFTWARE_OH_CALENDAR,
)
from .utils import capped_str
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class EventType(Enum):
    GBM = "[GBM]"
    SUBTEAM = "[SUBTEAM]"
    OFFICE_HOURS = "[OH]"
    EVENT = "[EVENT]"
    SOCIAL = "[SOCIAL]"
    TEAM_MEETING = "[MEETING]"

    def emoji(self) -> str:
        emojis = {
            EventType.GBM: "📢",
            EventType.SUBTEAM: "👥",
            EventType.OFFICE_HOURS: "🕒",
            EventType.EVENT: "📅",
            EventType.TEAM_MEETING: "🤝",
            EventType.SOCIAL: "🎉",
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
    def from_ical_event(cls, event: icalendar.Event, team: Team):
        # Make sure to parse vText too
        event_type, title = cls.get_type(event.get("summary").to_ical().decode("utf-8"))
        return cls(
            title=title,
            start=event.get("dtstart").dt,
            end=event.get("dtend").dt,
            location=(
                event.get("location").to_ical().decode("utf-8")
                if event.get("location")
                else ""
            ),
            type=event_type,
            team=team,
        )

    @property
    def sanitized_location(self) -> str:
        return self.location.replace("\\n", ", ")

    # Herustic for finding recurring events
    def recurs_with(self, event: Event) -> bool:
        return (
            self.title == event.title
            and self.location == event.location
            and self.type == event.type
            and self.team == event.team
        )

    def at_mil(self) -> bool:
        return self.location in ("", "MALA 3001")

    def upcoming(self) -> bool:
        return self.end >= datetime.datetime.now().astimezone()

    def embed_str(self) -> str:
        location_str = (
            f"(location: {self.sanitized_location})" if not self.at_mil() else ""
        )
        res = f"{self.team.emoji if self.end >= datetime.datetime.now().astimezone() else self.team.old_emoji} {self.type.emoji()} {discord.utils.format_dt(self.start, 't')} - {discord.utils.format_dt(self.end, 't')}: **{self.title}** {location_str}"
        if self.end < datetime.datetime.now().astimezone():
            res = f"~~{res}~~"
        return res


@dataclass
class OutlookCalendar:
    url: str
    name: str
    protected: bool = False

    def __hash__(self):
        return hash(self.url) ^ hash(self.name)

    @property
    def ics_url(self) -> str:
        return f"{self.url}/calendar.ics" if self.url else ""

    @property
    def html_url(self) -> str:
        return f"{self.url}/calendar.html" if self.url else ""


class CalendarView(discord.ui.View):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Add calendars to your own calendar app!",
        style=discord.ButtonStyle.red,
        custom_id="calendarview:ics",
    )
    async def ics(self, interaction: discord.Interaction, button: discord.ui.Button):
        descriptions: dict[str, OutlookCalendar] = {
            "General Calendar (GBMs, socials, etc.)": OutlookCalendar(GENERAL_CALENDAR),
            "Software Meetings Calendar": OutlookCalendar(SOFTWARE_MEETINGS_CALENDAR),
            "Software Office Hours Calendar": OutlookCalendar(SOFTWARE_OH_CALENDAR),
            "Mechanical Meetings Calendar": OutlookCalendar(
                MECHANICAL_MEETINGS_CALENDAR,
            ),
            "Mechanical Office Hours Calendar": OutlookCalendar(MECHANICAL_OH_CALENDAR),
            "Electrical Meetings Calendar": OutlookCalendar(
                ELECTRICAL_MEETINGS_CALENDAR,
            ),
            "Electrical Office Hours Calendar": OutlookCalendar(ELECTRICAL_OH_CALENDAR),
        }
        formatted_descriptions = "\n".join(
            [f"* **{name}**: {cal.ics_url}" for name, cal in descriptions.items()],
        )
        message = f"""Here are the links to each MIL calendar.
{formatted_descriptions}
        """
        platform_help_view = MILBotView()
        platform_help_view.add_item(
            discord.ui.Button(
                label="Instructions for Google Calendar",
                url="https://support.google.com/calendar/answer/37100?hl=en&co=GENIE.Platform%3DDesktop",
            ),
        )
        platform_help_view.add_item(
            discord.ui.Button(
                label="Instructions for Apple Calendar",
                url="https://support.apple.com/guide/calendar/subscribe-to-calendars-icl1022/mac#:~:text=In%20the%20Calendar%20app%20on,an%20account%20for%20the%20subscription.",
            ),
        )
        platform_help_view.add_item(
            discord.ui.Button(
                label="Instructions for Outlook Calendar",
                url="https://support.microsoft.com/en-us/office/import-or-subscribe-to-a-calendar-in-outlook-com-or-outlook-on-the-web-cff1429c-5af6-41ec-a5b4-74f2c278e98c#:~:text=Sign%20in%20to%20Outlook.com.&text=In%20the%20navigation%20pane%2C%20select,the%20URL%20for%20the%20calendar.",
            ),
        )
        await interaction.response.send_message(
            message,
            ephemeral=True,
            view=platform_help_view,
        )


class Calendar(commands.Cog):

    OPEN_HOURS = (datetime.time(9, 0), datetime.time(18, 0))
    calendars: dict[OutlookCalendar, Team]
    calendar_stores: dict[OutlookCalendar, list[Event] | None]

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.calendars = {
            OutlookCalendar(str(GENERAL_CALENDAR), "General"): Team.GENERAL,
            OutlookCalendar(
                str(SOFTWARE_MEETINGS_CALENDAR),
                "Software Meetings",
            ): Team.SOFTWARE,
            OutlookCalendar(
                str(SOFTWARE_OH_CALENDAR),
                "Software Office Hours",
            ): Team.SOFTWARE,
            OutlookCalendar(
                str(MECHANICAL_MEETINGS_CALENDAR),
                "Mechanical Meetings",
            ): Team.MECHANICAL,
            OutlookCalendar(
                str(MECHANICAL_OH_CALENDAR),
                "Mechanical Office Hours",
            ): Team.MECHANICAL,
            OutlookCalendar(
                str(ELECTRICAL_MEETINGS_CALENDAR),
                "Electrical Meetings",
            ): Team.ELECTRICAL,
            OutlookCalendar(
                str(ELECTRICAL_OH_CALENDAR),
                "Electrical Office Hours",
            ): Team.ELECTRICAL,
            OutlookCalendar(
                str(LEADERS_CALENDAR),
                "Leaders",
                protected=True,
            ): Team.GENERAL,
        }
        self.calendar_stores = {}
        for calendar in self.calendars:
            self.calendar_stores[calendar] = None
        self.calendar.start()

    async def load_calendar(self, calendar: OutlookCalendar, team: Team) -> list[Event]:
        if not calendar.url:
            logger.warn("Calendar URL is empty, not loading this calendar.")
            return []
        response = await self.bot.session.get(calendar.ics_url)
        ics = icalendar.Calendar.from_ical(await response.read())
        today = datetime.date.today()
        end_date = today + datetime.timedelta(days=90)
        events = recurring_ical_events.of(ics).between(today, end_date)
        cal_events: list[Event] = []
        for event in events:
            cal_events.append(Event.from_ical_event(event, team))

        # If we haven't stored the events yet, we can't check for changes, so
        # let's just store the events and return
        if not self.calendar_stores[calendar]:
            self.calendar_stores[calendar] = cal_events
            return cal_events

        # otherwise, check if we need to emit events
        store = self.calendar_stores[calendar]
        if store is not None:
            new_events = [
                event
                for event in cal_events
                if event not in self.calendar_stores[calendar]
            ]
            i = 1
            while i < len(new_events):
                if new_events[i].recurs_with(new_events[i - 1]):
                    del new_events[i]
                else:
                    i += 1
            removed_events = [event for event in store if event not in cal_events]
            i = 1
            while i < len(removed_events):
                if removed_events[i].recurs_with(removed_events[i - 1]):
                    del removed_events[i]
                else:
                    i += 1
            for event in new_events:
                # title change check: is there an event with the same start and end time, but different title?
                old_event = next(
                    (
                        e
                        for e in removed_events
                        if e.start == event.start
                        and e.end == event.end
                        and e.title != event.title
                    ),
                    None,
                )
                if old_event:
                    removed_events.remove(old_event)
                    self.bot.dispatch(
                        "calendar_event_title_modified",
                        event,
                        calendar,
                        team,
                        old_event.title,
                        event.title,
                    )
                    continue

                # time change check: is there an event with the same title, but different start and/or end time?
                old_event = next(
                    (
                        e
                        for e in removed_events
                        if e.title == event.title
                        and (e.start != event.start or e.end != event.end)
                    ),
                    None,
                )
                if old_event:
                    removed_events.remove(old_event)
                    self.bot.dispatch(
                        "calendar_event_time_modified",
                        event,
                        calendar,
                        team,
                        old_event.start,
                        old_event.end,
                        event.start,
                        event.end,
                    )
                    continue

                # location change check: is there an event with the same title, but different location?
                old_event = next(
                    (
                        e
                        for e in removed_events
                        if e.title == event.title
                        and e.start == event.start
                        and e.end == event.end
                    ),
                    None,
                )
                if old_event:
                    removed_events.remove(old_event)
                    self.bot.dispatch(
                        "calendar_event_location_modified",
                        event,
                        calendar,
                        team,
                        old_event.location,
                        event.location,
                    )
                    continue

                # new event
                self.bot.dispatch("calendar_event_added", event, calendar, team)

            for event in removed_events:
                self.bot.dispatch("calendar_event_deleted", event, calendar, team)
        self.calendar_stores[calendar] = cal_events
        return cal_events

    @commands.Cog.listener()
    async def on_calendar_event_added(
        self,
        event: Event,
        calendar: OutlookCalendar,
        team: Team,
    ):
        leads_channel = self.bot.team_leads_ch(team)
        await leads_channel.send(
            f'"{event.title}" was added to the "{calendar.name}" calendar.',
        )

    @commands.Cog.listener()
    async def on_calendar_event_title_modified(
        self,
        event: Event,
        calendar: OutlookCalendar,
        team: Team,
        old_name: str,
        new_name: str,
    ):
        leads_channel = self.bot.team_leads_ch(team)
        await leads_channel.send(
            f'"{old_name}" was renamed to "{new_name}" in the "{calendar.name}" calendar.',
        )

    @commands.Cog.listener()
    async def on_calendar_event_time_modified(
        self,
        event: Event,
        calendar: OutlookCalendar,
        team: Team,
        old_start: datetime.datetime,
        old_end: datetime.datetime,
        new_start: datetime.datetime,
        new_end: datetime.datetime,
    ):
        leads_channel = self.bot.team_leads_ch(team)
        await leads_channel.send(
            f'"{event.title}": time was changed from {discord.utils.format_dt(old_start, "t")} - {discord.utils.format_dt(old_end, "t")} to {discord.utils.format_dt(new_start, "t")} - {discord.utils.format_dt(new_end, "t")} in the "{calendar.name}" calendar.',
        )

    @commands.Cog.listener()
    async def on_calendar_event_location_modified(
        self,
        event: Event,
        calendar: OutlookCalendar,
        team: Team,
        old_location: str,
        new_location: str,
    ):
        leads_channel = self.bot.team_leads_ch(team)
        old_location_pretty = old_location.replace("\\n", ", ")
        new_location_pretty = new_location.replace("\\n", ", ")
        await leads_channel.send(
            f'"{event.title}": location was changed from "{old_location_pretty}" to "{new_location_pretty}" in the "{calendar.name}" calendar.',
        )

    @commands.Cog.listener()
    async def on_calendar_event_deleted(
        self,
        event: Event,
        calendar: OutlookCalendar,
        team: Team,
    ):
        leads_channel = self.bot.team_leads_ch(team)
        await leads_channel.send(
            f'"{event.title}" was deleted from the "{calendar.name}" calendar.',
        )

    def calendar_channel(self) -> discord.TextChannel:
        for value in StatusChannelName:
            channel = discord.utils.get(
                self.bot.active_guild.text_channels,
                name=value.value,
            )
            if channel:
                return channel
        raise ValueError("No calendar channel found!")

    def current_status(self, events: list[Event]) -> StatusChannelName:
        for event in events:
            if event.start < discord.utils.utcnow() < event.end and event.at_mil():
                return StatusChannelName.OPEN
        is_weekday = 0 <= datetime.datetime.now().weekday() <= 4
        is_open_range = (
            self.OPEN_HOURS[0] < datetime.datetime.now().time() < self.OPEN_HOURS[1]
        )
        if is_open_range and is_weekday:
            return StatusChannelName.MAYBE
        return StatusChannelName.CLOSED

    async def update_channel_name(self, events: list[Event]) -> None:
        channel = self.calendar_channel()
        if channel.name != (new_name := self.current_status(events).value):
            await channel.edit(name=new_name)

    def events_list_str(self, events: list[Event]) -> str:
        upcoming_events = [event for event in events if event.upcoming()]
        past_events = [event for event in events if not event.upcoming()]

        upcoming_strs = [event.embed_str() for event in upcoming_events]
        strs = upcoming_strs.copy()
        past_strs = [event.embed_str() for event in past_events][::-1]
        max_length = 1024 - len("_... (99 before)_") - len("\n".join(upcoming_strs))
        for event in past_strs:
            if max_length - len(event + "\n") > 0:
                max_length -= len(event + "\n")
                strs.insert(0, event)
            else:
                strs.insert(
                    0,
                    f"_... ({len(past_strs) - (len(strs) - len(upcoming_strs))} before)_",
                )

        return capped_str(strs) or "No events scheduled."

    @tasks.loop(minutes=3)
    async def calendar(self):
        await self.bot.wait_until_ready()
        start_time = time.monotonic()
        embed = discord.Embed(
            title="📆 Lab Calendar",
            color=discord.Color.brand_red(),
            description="Here's the calendar for the upcoming week. All events take place in the lab (`MALA 3001`) unless noted otherwise. If you have any questions, feel free to ask!",
        )
        channel = self.calendar_channel()
        events = []
        error = []
        for calendar, team in self.calendars.items():
            if calendar.protected:
                continue
            try:
                events += await self.load_calendar(calendar, team)
            except Exception:
                logger.exception(f"Failed to load calendar {calendar.name}")
                error.append(calendar)
        events.sort(key=lambda x: x.start)
        today_events = [
            event for event in events if event.start.date() == datetime.date.today()
        ]
        embed.add_field(
            name="__Today's Events__",
            value=self.events_list_str(today_events),
            inline=False,
        )
        tomorrow_events = [
            event
            for event in events
            if event.start.date() == datetime.date.today() + datetime.timedelta(days=1)
        ]
        embed.add_field(
            name="__Tomorrow's Events__",
            value=self.events_list_str(tomorrow_events),
            inline=False,
        )
        two_days = datetime.date.today() + datetime.timedelta(days=2)
        two_days_events = [event for event in events if event.start.date() == two_days]
        embed.add_field(
            name=f"__{two_days.strftime('%A')}'s Events__ (in 2 days)",
            value=self.events_list_str(two_days_events),
            inline=False,
        )
        three_days = datetime.date.today() + datetime.timedelta(days=3)
        three_days_events = [
            event for event in events if event.start.date() == three_days
        ]
        embed.add_field(
            name=f"__{three_days.strftime('%A')}'s Events__ (in 3 days)",
            value=self.events_list_str(three_days_events),
            inline=False,
        )
        four_days = datetime.date.today() + datetime.timedelta(days=4)
        four_days_events = [
            event for event in events if event.start.date() == four_days
        ]
        embed.add_field(
            name=f"__{four_days.strftime('%A')}'s Events__ (in 4 days)",
            value=self.events_list_str(four_days_events),
            inline=False,
        )
        # Date formatted: Feb 2, 2024 03:56PM
        date_formatted = datetime.datetime.now().strftime("%b %d, %Y %I:%M%p")
        time_taken = time.monotonic() - start_time
        error_str = f"(failed to load {len(error)} calendar(s))" if error else ""
        embed.set_footer(
            text=f"Last refreshed: {date_formatted} (took: {time_taken:.2f}s) {error_str}",
        )
        last_message = [m async for m in channel.history(limit=1, oldest_first=True)]
        if not last_message:
            await channel.send(embed=embed, view=CalendarView(self.bot))
        else:
            await last_message[0].edit(embed=embed, view=CalendarView(self.bot))
        await self.update_channel_name(events)


async def setup(bot: MILBot):
    await bot.add_cog(Calendar(bot))
