from __future__ import annotations

import asyncio
import datetime
import logging
import logging.handlers
import os
import random
import traceback
from io import BytesIO
from typing import Literal

import aiohttp
import discord
import gspread_asyncio
from discord import app_commands
from discord.ext import commands
from google.auth import crypt
from google.oauth2.service_account import Credentials
from rich.logging import RichHandler
from sqlalchemy.ext.asyncio import create_async_engine

from .anonymous import AnonymousReportView
from .calendar import CalendarView
from .constants import Team
from .db import Base, DatabaseFactory
from .emoji import EmojiRegistry
from .env import (
    DATABASE_ENGINE_URL,
    DISCORD_TOKEN,
    GITHUB_TOKEN,
    GSPREAD_PRIVATE_KEY,
    GSPREAD_PRIVATE_KEY_ID,
    GSPREAD_SERVICE_ACCOUNT_EMAIL,
    GSPREAD_SS_NAME,
    GSPREAD_TOKEN_URI,
)
from .exceptions import MILBotErrorHandler, ResourceNotFound
from .github import GitHub
from .github.views import GitHubInviteView
from .leaders import AwayView
from .projects import SoftwareProjectsView
from .reports.cog import ReportsCog
from .reports.member_services import ReportsView
from .reports.review import StartReviewView
from .roles import MechanicalRolesView, SummerRolesView, TeamRolesView
from .tasks import TaskManager
from .testing import TestingSignUpView
from .verification import Verifier
from .welcome import WelcomeView
from .wiki import MILWiki


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
    active_emoji_guild: discord.Guild

    # Channels
    leaders_channel: discord.TextChannel
    leave_channel: discord.TextChannel
    general_channel: discord.TextChannel
    member_services_channel: discord.TextChannel
    alumni_channel: discord.TextChannel
    errors_channel: discord.TextChannel
    software_github_channel: discord.TextChannel
    electrical_github_channel: discord.TextChannel
    mechanical_github_channel: discord.TextChannel
    leads_github_channel: discord.TextChannel
    software_projects_channel: discord.TextChannel
    mechanical_category_channel: discord.CategoryChannel
    electrical_category_channel: discord.CategoryChannel
    leads_category_channel: discord.CategoryChannel
    software_category_channel: discord.CategoryChannel
    operations_leaders_channel: discord.TextChannel
    software_leaders_channel: discord.TextChannel
    electrical_leaders_channel: discord.TextChannel
    mechanical_leaders_channel: discord.TextChannel
    message_log_channel: discord.TextChannel

    # Emojis
    loading_emoji: str

    # Roles
    egn4912_role: discord.Role
    leaders_role: discord.Role
    sys_leads_role: discord.Role
    software_leads_role: discord.Role
    bot_role: discord.Role
    alumni_role: discord.Role
    new_grad_role: discord.Role
    away_role: discord.Role

    # Cogs
    reports_cog: ReportsCog

    # Internal
    session: aiohttp.ClientSession
    _setup: asyncio.Event
    tasks: TaskManager
    github: GitHub
    verifier: Verifier
    db_factory: DatabaseFactory
    emoji_registry: EmojiRegistry

    def __init__(self):
        super().__init__(
            command_prefix="!",
            case_insensitive=True,
            intents=intents,
            tree_cls=MILBotCommandTree,
        )
        self.tasks = TaskManager(self)
        self._setup = asyncio.Event()
        self.verifier = Verifier()
        self.emoji_registry = EmojiRegistry(self)

    async def sync_emojis(self):
        emojis = await self.active_emoji_guild.fetch_emojis()
        missing_emojis = await self.emoji_registry.upload(emojis)
        for missing_emoji in missing_emojis:
            logger.info(f"Synchronized missing emoji: {missing_emoji.name}")
            await self.active_emoji_guild.create_custom_emoji(
                name=missing_emoji.name,
                image=missing_emoji.image,
                reason="Syncing emojis from registry",
            )
        self.emoji_registry.store_emojis(await self.active_emoji_guild.fetch_emojis())

    async def on_ready(self):
        print("Logged on as", self.user)
        self.loading_emoji = "<a:loading:1154245561680138240>"
        self.tasks.start()
        engine = create_async_engine(DATABASE_ENGINE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db_factory = DatabaseFactory(bot=self, engine=engine)
        await self.sync_emojis()
        await self.fetch_vars()
        self.wiki = MILWiki(self)
        await self.wiki.login()

    async def close(self):
        await self.session.close()
        await self.db_factory.close()
        await super().close()

    async def get_or_fetch_member(self, user_id: int) -> discord.Member:
        """
        Gets a member from the active guild, fetching them if necessary.

        Raises:
            NotFound: The member was not in the guild.
        """
        member = self.active_guild.get_member(user_id)
        if not member:
            member = await self.active_guild.fetch_member(user_id)
        return member

    async def fetch_audit_log_targeting(
        self,
        target_id: int,
        actions: list[discord.AuditLogAction],
    ) -> discord.AuditLogEntry | None:
        entry = [
            x
            async for x in self.active_guild.audit_logs(
                limit=1,
                after=discord.utils.utcnow() - datetime.timedelta(seconds=5),
            )
            if x.action
            in [
                discord.AuditLogAction.member_role_update,
            ]
            and x.target is not None
            and x.target.id == target_id
        ]
        return entry[0] if entry else None

    async def setup_hook(self) -> None:
        # Load extensions
        extensions = (
            "src.admin",
            "src.calendar",
            "src.fun",
            "src.github.cog",
            "src.leaders",
            "src.logger",
            "src.projects",
            "src.reports.cog",
            "src.roles",
            "src.testing",
            "src.webhooks",
            "src.welcome",
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
        self.add_view(SummerRolesView(self))
        self.add_view(AnonymousReportView(self))
        self.add_view(GitHubInviteView(self))
        self.add_view(AwayView(self))
        self.add_view(StartReviewView(self))

        agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)
        self.agc = await agcm.authorize()
        self.sh = await self.agc.open(GSPREAD_SS_NAME)

    async def fetch_vars(self) -> None:
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
        if team == Team.GENERAL:
            return self.leaders_channel
        ch = discord.utils.get(
            self.active_guild.text_channels,
            name=f"{team.name.lower()}-leadership",
        )
        if not ch:
            raise ResourceNotFound("Channel not found.")
        return ch

    def leads_project_channel(
        self,
        name: Literal["sub9", "navigator", "drone"],
    ) -> discord.TextChannel:
        ch = discord.utils.get(
            self.active_guild.text_channels,
            name=f"{name}-leads",
        )
        if not ch:
            raise ResourceNotFound("Channel not found.")
        return ch

    def get_headshot(self, member: discord.Member) -> discord.File | None:
        if os.path.exists(f"headshots/{member.id}.png"):
            return discord.File(
                f"headshots/{member.id}.png",
                filename=f"{member.id}.png",
            )

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

    async def good_job_gif(self) -> discord.File:
        gifs = [
            "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExb3BqbnlzaXBmODdxMzRkeHFxYWg1N3NoM3A4czh3aGo2NHhmNGRtYSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ktfInKGOVkdQtwJy9h/giphy.gif",
            "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExdjRyOGJjY3cxdTUzb2gycXlmcW1lZ2ZsYXh3aGxjaDY1cTNyMzRnNiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/UjCXeFnYcI2R2/giphy.gif",
            "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExMXo1dHdxem04N2M4ZXJhaTlnb25mYTZsMmtjMGFyMWJweDFleG03ZCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/8pR7lPuRZzTXVtWlTF/giphy.gif",
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

    async def on_ipc_error(self, endpoint, error):
        self.handler = MILBotErrorHandler()
        await self.handler.handle_ipc_exception(self, endpoint, error)

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
