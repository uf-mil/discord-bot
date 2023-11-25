import asyncio
import logging
import logging.handlers
import random
import traceback

import aiohttp
import discord
import gspread_asyncio
from discord.ext import commands
from discord.ext import tasks as ext_tasks
from google.auth import crypt
from google.oauth2.service_account import Credentials
from rich.logging import RichHandler

from .env import (
    DISCORD_TOKEN,
    GSPREAD_PRIVATE_KEY,
    GSPREAD_PRIVATE_KEY_ID,
    GSPREAD_SERVICE_ACCOUNT_EMAIL,
    GSPREAD_TOKEN_URI,
    GUILD_ID,
)
from .reports import ReportsView
from .roles import MechanicalRolesView, TeamRolesView
from .tasks import TaskManager
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


class MILBot(commands.Bot):

    # MIL server ref
    active_guild: discord.Guild
    # Channels
    leaders_channel: discord.TextChannel
    leave_channel: discord.TextChannel
    general_channel: discord.TextChannel
    reports_channel: discord.TextChannel
    # Emojis
    loading_emoji: str
    # Roles
    egn4912_role: discord.Role
    leaders_role: discord.Role
    sys_leads_role: discord.Role

    # Internal
    session: aiohttp.ClientSession
    tasks: TaskManager

    def __init__(self):
        super().__init__(
            command_prefix="!",
            case_insensitive=True,
            intents=intents,
        )
        self.tasks = TaskManager()

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

    async def setup_hook(self) -> None:
        # Load extensions
        extensions = (
            "src.logger",
            "src.github",
            "src.roles",
            "src.welcome",
            "src.reports",
            "src.leaders",
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

        agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)
        self.agc = await agcm.authorize()
        self.sh = await self.agc.open("MIL Fall 2023 Weekly Responses")

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

    async def on_message(self, message):
        # don't respond to ourselves
        if message.author == self.user:
            return

        if message.content == "ping":
            await message.channel.send("pong")

        await self.process_commands(message)

    async def on_member_join(self, member: discord.Member):
        role = discord.utils.get(member.guild.roles, name="New Member")
        assert isinstance(role, discord.Role)
        await member.add_roles(role)


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
