from __future__ import annotations

import asyncio
import logging
import logging.handlers
import random
import traceback
from io import BytesIO

import aiohttp
import discord
import gspread_asyncio
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks as ext_tasks
from google.auth import crypt
from google.oauth2.service_account import Credentials
from rich.logging import RichHandler

from .calendar import CalendarView
from .constants import Team
from .env import (
    DISCORD_TOKEN,
    GITHUB_TOKEN,
    GSPREAD_PRIVATE_KEY,
    GSPREAD_PRIVATE_KEY_ID,
    GSPREAD_SERVICE_ACCOUNT_EMAIL,
    GSPREAD_SS_NAME,
    GSPREAD_TOKEN_URI,
    GUILD_ID,
)
from .exceptions import MILBotErrorHandler, ResourceNotFound
from .github import GitHub
from .projects import SoftwareProjectsView
from .reports import ReportsCog, ReportsView
from .roles import MechanicalRolesView, TeamRolesView
from .tasks import TaskManager
from .testing import TestingSignUpView
from .welcome import WelcomeView


def get_creds():
    signer = crypt.RSASigner.from_service_account_info(
        {
            "private_key": GSPREAD_PRIVATE_KEY,
            "private_key_id": GSPREAD_PRIVATE_KEY_ID,
        },
    )
    creds = Credentials(
        signer=signer,
        service_account_email=GSPREAD_SERVICE_ACCOUNT_EMAIL,
        token_uri=GSPREAD_TOKEN_URI,
    )
    scoped = creds.with_scopes(
        [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return scoped


logger = logging.getLogger(__name__)
intents = discord.Intents.all()


class MILBotCommandTree(app_commands.CommandTree):
    def __init__(self, client: MILBot):
        super().__init__(client)
        self.handler = MILBotErrorHandler()

    async def on_error(
        self,
        interaction: discord.Interaction[MILBot],
        error: app_commands.AppCommandError,
    ) -> None:
        await self.handler.handle_interaction_exception(interaction, error)


class MILBot(commands.Bot):

    # MIL server ref
    active_guild: discord.Guild

    # Channels
    leaders_channel: discord.TextChannel
    leave_channel: discord.TextChannel
    general_channel: discord.TextChannel
    reports_channel: discord.TextChannel
    errors_channel: discord.TextChannel
    software_projects_channel: discord.TextChannel
    software_category_channel: discord.CategoryChannel

    # Emojis
    loading_emoji: str

    # Roles
    egn4912_role: discord.Role
    leaders_role: discord.Role
    sys_leads_role: discord.Role
    software_leads_role: discord.Role
    bot_role: discord.Role

    # Cogs
    reports_cog: ReportsCog

    # Internal
    session: aiohttp.ClientSession
    _setup: asyncio.Event
    tasks: TaskManager
    github: GitHub

    def __init__(self):
        super().__init__(
            command_prefix="!",
            case_insensitive=True,
            intents=intents,
            tree_cls=MILBotCommandTree,
        )
        self.tasks = TaskManager(self)
        self._setup = asyncio.Event()

    async def on_ready(self):
        print("Logged on as", self.user)
        self.loading_emoji = "<a:loading:1154245561680138240>"
        if not self.change_status.is_running():
            self.change_status.start()
        await self.fetch_vars()

    async def close(self):
        await self.session.close()
        await super().close()

    @ext_tasks.loop(hours=1)
    async def change_status(self):
        activities: list[discord.Activity] = [
            discord.Activity(type=discord.ActivityType.watching, name="ROS tutorials"),
            discord.Activity(type=discord.ActivityType.playing, name="with SubjuGator"),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="VRX submissions",
            ),
            discord.Activity(
                type=discord.ActivityType.playing,
                name="with soldering irons",
            ),
            discord.Activity(
                type=discord.ActivityType.playing,
                name="ML Image Labeler",
            ),
            discord.Activity(
                type=discord.ActivityType.playing,
                name="SolidWorks",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="robotics lectures",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="underwater pings",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="feedback from members",
            ),
            discord.Activity(type=discord.ActivityType.watching, name="for new PRs"),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="mechanical Tech Talks",
            ),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="students get internships",
            ),
            discord.Activity(
                type=discord.ActivityType.watching,
                name="the DSIT building open",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="alumni advice",
            ),
        ]
        await self.change_presence(activity=random.choice(activities))

    async def get_member(self, user_id: int) -> discord.Member:
        """
        Gets a member from the active guild, fetching them if necessary.
        """
        member = self.active_guild.get_member(user_id)
        if not member:
            member = await self.active_guild.fetch_member(user_id)
        return member

    async def setup_hook(self) -> None:
        # Load extensions
        extensions = (
            "src.calendar",
            "src.github",
            "src.leaders",
            "src.logger",
            "src.projects",
            "src.reports",
            "src.roles",
            "src.welcome",
            "src.testing",
        )
        for i, extension in enumerate(extensions):
            try:
                await self.load_extension(extension)
                logger.info(f"Enabled extension: {extension} {i + 1}/{len(extensions)}")
            except commands.ExtensionError:
                logger.error(f"Failed to load extension {extension}!")
                traceback.print_exc()

        # Register views
        self.add_view(TeamRolesView(self))
        self.add_view(MechanicalRolesView(self))
        self.add_view(ReportsView(self))
        self.add_view(WelcomeView(self))
        self.add_view(SoftwareProjectsView(self, []))
        self.add_view(CalendarView(self))
        self.add_view(TestingSignUpView(self, ""))

        agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)
        self.agc = await agcm.authorize()
        self.sh = await self.agc.open(GSPREAD_SS_NAME)

    async def fetch_vars(self) -> None:
        # Guilds
        guild = self.get_guild(GUILD_ID)
        if not guild:
            guild = self.fetch_guild(GUILD_ID)
        assert isinstance(guild, discord.Guild)
        self.active_guild = guild

        # Channels
        leave_channel = discord.utils.get(
            self.active_guild.text_channels,
            name="leave-log",
        )
        assert isinstance(leave_channel, discord.TextChannel)
        self.leave_channel = leave_channel

        general_channel = discord.utils.get(
            self.active_guild.text_channels,
            name="general",
        )
        assert isinstance(general_channel, discord.TextChannel)
        self.general_channel = general_channel

        reports_channel = discord.utils.get(
            self.active_guild.text_channels,
            name="reports",
        )
        assert isinstance(reports_channel, discord.TextChannel)
        self.reports_channel = reports_channel

        leaders_channel = discord.utils.get(
            self.active_guild.text_channels,
            name="leads",
        )
        assert isinstance(leaders_channel, discord.TextChannel)
        self.leaders_channel = leaders_channel

        errors_channel = discord.utils.get(
            self.active_guild.text_channels,
            name="bot-errors",
        )
        assert isinstance(errors_channel, discord.TextChannel)
        self.errors_channel = errors_channel

        software_projects_channel = discord.utils.get(
            self.active_guild.text_channels,
            name="software-projects",
        )
        assert isinstance(software_projects_channel, discord.TextChannel)
        self.software_projects_channel = software_projects_channel

        software_category_channel = discord.utils.get(
            self.active_guild.categories,
            name="Software",
        )
        assert isinstance(software_category_channel, discord.CategoryChannel)
        self.software_category_channel = software_category_channel

        # Roles
        egn4912_role = discord.utils.get(
            self.active_guild.roles,
            name="EGN4912",
        )
        assert isinstance(egn4912_role, discord.Role)
        self.egn4912_role = egn4912_role

        leaders_role = discord.utils.get(
            self.active_guild.roles,
            name="Leaders",
        )
        assert isinstance(leaders_role, discord.Role)
        self.leaders_role = leaders_role

        sys_leads_role = discord.utils.get(
            self.active_guild.roles,
            name="Systems Leadership",
        )
        assert isinstance(sys_leads_role, discord.Role)
        self.sys_leads_role = sys_leads_role

        software_leads_role = discord.utils.get(
            self.active_guild.roles,
            name="Software Leadership",
        )
        assert isinstance(software_leads_role, discord.Role)
        self.software_leads_role = software_leads_role

        bot_role = discord.utils.get(
            self.active_guild.roles,
            name="Bot",
        )
        assert isinstance(bot_role, discord.Role)
        self.bot_role = bot_role

        reports_cog = self.get_cog("ReportsCog")
        if not reports_cog:
            raise ResourceNotFound("Reports cog not found.")
        self.reports_cog = reports_cog  # type: ignore

        for task in self.tasks.recurring_tasks():
            task.bot = self
            task.schedule()

        self.github = GitHub(auth_token=GITHUB_TOKEN, bot=bot)
        self._setup.set()

    def team_leads_ch(self, team: Team) -> discord.TextChannel:
        ch = discord.utils.get(
            self.active_guild.text_channels,
            name=f"{team.name.lower()}-leadership",
        )
        if not ch:
            raise ResourceNotFound("Channel not found.")
        return ch

    async def reading_gif(self) -> discord.File:
        gifs = [
            "https://media1.tenor.com/m/ogsH7Ailje8AAAAd/cat-funny-cat.gif",
            "https://media1.giphy.com/media/h6AMD4GXFxO2k/giphy.gif",
            "https://media1.tenor.com/m/CtS49WH3D0AAAAAd/roomba-riding.gif",
        ]
        async with self.session.get(random.choice(gifs)) as resp:
            if resp.status != 200:
                raise ResourceNotFound("Cat gif not found.")
            return discord.File(BytesIO(await resp.read()), filename="cat.gif")

    async def on_message(self, message):
        # don't respond to ourselves
        if message.author == self.user:
            return

        await self.process_commands(message)

    async def on_member_join(self, member: discord.Member):
        role = discord.utils.get(member.guild.roles, name="New Member")
        assert isinstance(role, discord.Role)
        await member.add_roles(role)

    async def on_error(self, event, *args, **kwargs):
        self.handler = MILBotErrorHandler()
        await self.handler.handle_event_exception(event, self)

    async def on_command_error(self, ctx, error):
        self.handler = MILBotErrorHandler()
        await self.handler.handle_command_exception(ctx, error)

    async def wait_until_ready(self):
        await self._setup.wait()
        await super().wait_until_ready()


bot = MILBot()


@bot.command()
@commands.is_owner()
async def sync(ctx):
    reply = await ctx.reply(f"{bot.loading_emoji} Syncing...")
    commands = await bot.tree.sync()
    command_names = [f"`/{c.name}` (`{c.id}`)" for c in commands]
    new_line_names = "\n".join(command_names)
    await reply.edit(
        content=f"Done syncing! Synced the following commands: {new_line_names}",
    )


async def main():
    KB = 1024
    MB = 1024 * KB
    handler = logging.handlers.RotatingFileHandler(
        filename="mil-bot.log",
        encoding="utf-8",
        maxBytes=32 * MB,
        backupCount=5,
    )
    discord.utils.setup_logging(handler=handler)

    logger = logging.getLogger()
    logger.addHandler(RichHandler(rich_tracebacks=True))

    async with bot, aiohttp.ClientSession() as session:
        bot.session = session
        await bot.start(token=DISCORD_TOKEN)


asyncio.run(main())
