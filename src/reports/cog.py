from __future__ import annotations

import calendar
import datetime
import itertools
import logging
from typing import TYPE_CHECKING

import discord
import gspread
import gspread_asyncio
from discord.ext import commands, tasks

from ..constants import Team, semester_given_date
from ..tasks import run_on_weekday
from ..utils import is_active
from .member_services import ReportsView
from .review import StartReviewView
from .sheets import Column, Student, WeekColumn

if TYPE_CHECKING:
    from ..bot import MILBot


logger = logging.getLogger(__name__)


class ReportsCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.post_reminder.start(self)
        self.last_week_summary.start(self)
        self.ensure_graded.start(self)
        self.first_individual_reminder.start(self)
        self.second_individual_reminder.start(self)
        self.update_report_channel.start(self)
        self.regular_refresh.start()
        self.final_refresh.start(self)

    @run_on_weekday(calendar.FRIDAY, 12, 0, check=is_active)
    async def post_reminder(self):
        general_channel = self.bot.general_channel
        return await general_channel.send(
            f"{self.bot.egn4912_role.mention}\nHey everyone! Friendly reminder to make at least one GitHub contribution or status update by **Sunday night at 11:59pm**. If you have any questions, please contact your team leader. Thank you!",
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

    def _format_issue_comment_str(self, payload: dict) -> str:
        no_newline_body = payload["bodyText"].replace("\n", " / ")
        no_newline_body = (
            no_newline_body[:300] + "..."
            if len(no_newline_body) > 300
            else no_newline_body
        )
        return f"* {payload['repository']['nameWithOwner']}#{payload['issue']['number']} (\"{payload['issue']['title']}\"): \"{no_newline_body}\""

    def _format_issue_str(self, payload: dict) -> str:
        return f"* {payload['repository']['nameWithOwner']}#{payload['number']} (\"{payload['title']}\")"

    def _format_commit_str(self, payload: dict) -> str:
        format_dt = discord.utils.format_dt(
            datetime.datetime.fromisoformat(payload["commit"]["author"]["date"]),
            "F",
        )
        no_newline_message = payload["commit"]["message"].replace("\n", " / ")
        no_newline_message = (
            no_newline_message[:100] + "..."
            if len(no_newline_message) > 100
            else no_newline_message
        )
        return f"* {format_dt} {payload['repository']['full_name']} @ {payload['sha'][:8]} ({no_newline_message})"

    def _format_commit_str_from_all_branches(self, payload: dict) -> str:
        format_dt = discord.utils.format_dt(
            datetime.datetime.fromisoformat(payload["author"]["date"]),
            "F",
        )
        no_newline_message = payload["message"].replace("\n", " / ")
        no_newline_message = (
            no_newline_message[:100] + "..."
            if len(no_newline_message) > 100
            else no_newline_message
        )
        return f"* {format_dt} {payload['repository']['nameWithOwner']} @ {payload['oid'][:8]} ({no_newline_message})"

    def _format_wiki_contrib(self, payload: dict) -> str:
        format_dt = discord.utils.format_dt(
            datetime.datetime.fromisoformat(payload["timestamp"]),
            "F",
        )
        return f"* {format_dt}: {payload['title']} ({payload['sizediff']} bytes)"

    async def refresh_sheet(self, previous_week: bool = False) -> None:
        main_worksheet = await self.bot.sh.get_worksheet(0)
        cur_semester = semester_given_date(datetime.datetime.now())
        cur_semester[0] if cur_semester else datetime.date.today()
        week = WeekColumn.current() if not previous_week else WeekColumn.previous()
        previous_monday_midnight = (
            datetime.datetime.now().astimezone()
            - datetime.timedelta(
                days=datetime.datetime.now().weekday(),
            )
        )
        previous_monday_midnight = previous_monday_midnight.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        if previous_week:
            previous_monday_midnight -= datetime.timedelta(weeks=1)
        async with self.bot.db_factory() as db:
            for member in await db.authenticated_members():
                logger.info(f"Fetching contributions for {member.discord_id}...")
                token = str(member.access_token)
                try:
                    contributions = await self.bot.github.get_user_contributions(
                        token,
                        start=previous_monday_midnight,
                    )
                except Exception:
                    logger.exception(
                        f"Error fetching contributions for {member.discord_id}",
                    )
                    continue
                try:
                    discord_member = await self.bot.get_or_fetch_member(
                        member.discord_id,
                    )
                except discord.NotFound:
                    logger.info(
                        f"Could not find member with ID {member.discord_id}.",
                    )
                    continue
                electrical_role = discord.utils.get(
                    self.bot.active_guild.roles,
                    name="EGN4912 Electrical",
                )
                if not electrical_role:
                    raise RuntimeError("Could not find EGN4912 Electrical role.")
                is_electrical_member = electrical_role in discord_member.roles
                summaries = {}
                if contributions.issue_comments:
                    summaries["Comments"] = [
                        self._format_issue_comment_str(payload)
                        for payload in contributions.issue_comments
                    ]
                if contributions.issues:
                    summaries["Issues Opened"] = [
                        self._format_issue_str(payload)
                        for payload in contributions.issues
                    ]
                if contributions.pull_requests:
                    summaries["Pull Requests Opened"] = [
                        self._format_issue_str(payload)
                        for payload in contributions.pull_requests
                    ]
                if contributions.commits and not is_electrical_member:
                    summaries["Commits"] = [
                        self._format_commit_str(payload)
                        for payload in contributions.commits
                    ]
                wiki_contributions = await self.bot.wiki.get_user_contributions(
                    discord_member.display_name.title(),
                    start=previous_monday_midnight,
                )
                if wiki_contributions:
                    total_bytes = sum(
                        abs(int(payload["sizediff"]))
                        for payload in wiki_contributions
                        if payload["sizediff"]
                    )
                    most_valuable_contributions = sorted(
                        wiki_contributions,
                        key=lambda x: abs(int(x["sizediff"])),
                        reverse=True,
                    )[:5]
                    if total_bytes > 750:
                        summaries["Wiki Contributions"] = [
                            self._format_wiki_contrib(payload)
                            for payload in most_valuable_contributions
                        ]
                if is_electrical_member:
                    try:
                        commits = await self.bot.github.commits_across_branches(token)
                        if commits:
                            summaries["Commits"] = [
                                self._format_commit_str_from_all_branches(payload)
                                for payload in commits
                            ]
                    except Exception:
                        logger.exception(
                            f"Error fetching commits across branches for user {member.discord_id}",
                        )
                summary_str = "\n\n".join(
                    f"**{k}**:\n" + "\n".join(v) for k, v in summaries.items()
                )
                id_cell = await main_worksheet.find(discord_member.name)
                if id_cell is None:
                    logger.info(f"Could not find cell for {discord_member.name}.")
                    continue
                a1_notation = gspread.utils.rowcol_to_a1(id_cell.row, week.report_column)  # type: ignore
                summary_str = summary_str.strip()
                # Just in case, google sheets cells are limited to 50,000 characters
                summary_str = summary_str[:50000]
                if not summary_str:
                    continue
                await main_worksheet.update(
                    a1_notation,
                    [
                        [
                            summary_str,
                        ],
                    ],
                )

    @tasks.loop(hours=2)
    async def regular_refresh(self) -> None:
        await self.bot.wait_until_ready()
        await self.refresh_sheet()
        logger.info(
            f"Refreshed contributions. Next running time: {self.regular_refresh.next_iteration}",
        )

    @run_on_weekday(calendar.MONDAY, 0, 0)
    async def final_refresh(self) -> None:
        await self.refresh_sheet(True)
        logger.info("Final refresh for the previous week completed.")

    async def students_status(
        self,
        column: int,
        *,
        refresh: bool = True,
    ) -> list[Student]:
        if refresh:
            await self.refresh_sheet()
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
        await self.refresh_sheet()
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
        async with self.bot.db_factory() as db:
            authenticated_discord_users = {
                user.discord_id for user in await db.authenticated_members()
            }
        for student in students:
            if student.member:
                if student.member.id not in authenticated_discord_users:
                    await student.member.send(
                        f"Hey **{student.first_name}**! It's your friendly uf-mil-bot here. I noticed you haven't connected your GitHub account yet. GitHub is a platform that your team uses to track progress of tasks. Please remember that at least one contribution to GitHub is required each week. This week's contribution is due in **twelve hours.** If you have questions about this, please see the {self.bot.member_services_channel.mention} channel or message your team lead. Thank you!",
                    )
                    logger.info(
                        f"Sent first individual reminder (to join GitHub) to {student.member}.",
                    )
                    continue
                try:
                    await student.member.send(
                        f"Hey **{student.first_name}**! It's your friendly uf-mil-bot here. I noticed you haven't provided a contribution or status update through GitHub this week. Please create it by {discord.utils.format_dt(deadline_tonight, 't')} tonight. Thank you!",
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
        async with self.bot.db_factory() as db:
            authenticated_discord_users = {
                user.discord_id for user in await db.authenticated_members()
            }
        for student in students:
            if student.member:
                if student.member.id not in authenticated_discord_users:
                    await student.member.send(
                        f"Hey **{student.first_name}**! It's your friendly uf-mil-bot here. I noticed you haven't connected your GitHub account yet. GitHub is a platform that your team uses to track progress of tasks. Please remember that at least one contribution to GitHub is required each week. This week's contribution is due in **four hours.** If you have questions about this, please see the {self.bot.member_services_channel.mention} channel or message your team lead. Thank you!",
                    )
                    logger.info(
                        f"Sent second individual reminder (to join GitHub) to {student.member}.",
                    )
                    continue
                try:
                    await student.member.send(
                        f"Hey **{student.first_name}**! It's your friendly uf-mil-bot here again. I noticed you haven't created your contribution or status update for this week yet. There are only **four hours** remaining to create your contribution! Please submit it through GitHub by {discord.utils.format_dt(deadline_tonight, 't')} tonight. Thank you!",
                    )
                    logger.info(
                        f"Sent second individual report reminder to {student.member}.",
                    )
                except discord.Forbidden:
                    logger.info(
                        f"Could not send second individual report reminder to {student.member}.",
                    )

    @run_on_weekday(calendar.MONDAY, 0, 0, check=is_active)
    async def last_week_summary(self):
        """
        Gives leaders a list of who submitted reports and who did not.
        """
        for team in Team:
            team_leads_ch = self.bot.team_leads_ch(team)
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

    @run_on_weekday(
        [calendar.THURSDAY, calendar.FRIDAY, calendar.SATURDAY, calendar.SUNDAY],
        8,
        0,
    )
    async def ensure_graded(self):
        """
        If any students are not graded, prompts the leaders to review reports again.
        """
        days_since_monday = (datetime.datetime.now().weekday() - 0) % 7
        week = WeekColumn.previous()
        column = week.report_column
        students = await self.bot.reports_cog.students_status(column, refresh=False)
        for team in Team:
            # no general team reports
            if team == Team.GENERAL:
                continue

            team_students = [
                s for s in students if s.team == team and s.report_score is None
            ]
            # print(team)
            # print([s for s in students if s.team == team])
            team_leads_ch = self.bot.team_leads_ch(team)

            # skip teams who are done grading
            if not len(team_students):
                continue

            message = f"Hello, {team!s} team! It has been {days_since_monday} days since the start of the week and there are {len(team_students)} students who are waiting on grades for their weekly reports. If you have a moment, please grade their reports. Thank you!"
            await team_leads_ch.send(
                message,
                view=StartReviewView(self.bot),
            )

    @run_on_weekday([calendar.MONDAY, calendar.WEDNESDAY], 0, 0)
    async def update_report_channel(self):
        # member-services messages:
        #   channel_history[0] --> anonymous report message
        #   channel_history[1] --> report view message
        channel_history = [
            m
            async for m in self.bot.member_services_channel.history(
                oldest_first=True,
                limit=2,
            )
        ]
        if not channel_history:
            return

        reports_message = channel_history[1]
        await reports_message.edit(view=ReportsView(self.bot))

    @commands.is_owner()
    @commands.command()
    async def reportview(self, ctx):
        embed = discord.Embed(
            title="Setup Automatic Progress Reports",
            description="In order to keep all members on track, we review the progress of each member each week. This process is automated using GitHub. All members are required to connect their GitHub account below to participate in our laboratory.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="📍 __What is a Contribution?__",
            value="Contributions include any activity on your team's task tracker or the MIL Wiki. This includes:\n* Opening issues\n* Writing comments on issues\n* Creating pull requests\n* Creating commits on the default branch\n* Adding 750 bytes of content (~150-200 words) to the MIL Wiki\nIf you have more questions about how your activity will be assessed, don't hesitate to ask your team lead.",
            inline=False,
        )
        embed.add_field(
            name="📅 __Deadline__",
            value="Reports are collected at **Sunday night at 11:59pm**. We cannot accept late contributions.",
            inline=False,
        )
        embed.add_field(
            name="📊 __Grading__",
            value="Reports are graded on a scale of **green-yellow-red** (green indicating the best performance).\n* ✅ **Green**: Report demonstrated an actionable attempt of at least 3 or 5 hours of work.\n* ⚠️ **Yellow**: Report demonstrated 0-1 hours of work. (ie, installing a basic software package or reading a tutorial)\n* ❌ **Red**: Report was missing or no work was demonstrated.\nThese details are tracked over a semester using the **missing index**. A yellow report adds +0.5; a red report adds +1. Upon reaching 4, you will be automatically removed from MIL.",
            inline=False,
        )
        embed.add_field(
            name="🔍 __Review__",
            value="A leader will review your report before the following Thursday to provide feedback on your work. If you were graded yellow or red, you will be notified via email.",
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
