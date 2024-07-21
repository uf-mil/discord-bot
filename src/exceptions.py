from __future__ import annotations

import contextlib
import datetime
import logging
import sys
import traceback
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.ipc.errors import NoEndpointFound

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .bot import MILBot


class MILException(Exception):
    """
    Base class for all exceptions handled by the bot.
    """


class ResourceNotFound(MILException):
    """
    The bot attempted to grab a resource that should exist, but the resource could not be found.
    """


class MILBotErrorHandler:
    """
    General error handler for the bot. Handles command errors, interaction errors,
    and errors with events. Can be instantitated infinite times, although using
    MILBotView and MILBotModal will take care of the error handling
    for most interactions.
    """

    def error_message(self, error: BaseException) -> tuple[str, float | None]:
        """
        Returns the error message and the delay, if any.
        """
        delay = None

        # Handle our failures first
        if isinstance(error, app_commands.CommandInvokeError):
            return (
                f"This command experienced a general error of type `{error.original.__class__}`.",
                delay,
            )
        elif isinstance(error, app_commands.CommandOnCooldown):
            next_time = discord.utils.utcnow() + datetime.timedelta(
                seconds=error.retry_after,
            )
            message = (
                "Time to _chill out_ - this command is on cooldown! "
                f"Please try again **{discord.utils.format_dt(next_time, 'R')}.**"
                "\n\n"
                "For future reference, this command is currently limited to "
                f"being executed **{error.cooldown.rate} times every {error.cooldown.per} seconds**."
            )
            delay = error.retry_after
            return message, delay
        elif isinstance(error, app_commands.MissingRole | app_commands.MissingAnyRole):
            return str(error), delay

        error_messages: dict[type[BaseException], str] = {
            # Custom messages
            ResourceNotFound: "Oops, I couldn't find that resource. Please try again.",
            # Application commands or Interactions
            app_commands.NoPrivateMessage: "Sorry, but this command does not work in private message. Please hop on over to the server to use the command!",
            app_commands.MissingPermissions: "Hey pal, you don't have the necessary permissions to run this command.",
            app_commands.BotMissingPermissions: "Hmm, looks like I don't have the permissions to do that. Something went wrong. You should definitely let someone know about this.",
            app_commands.CommandLimitReached: "Oh no! I've reached my max command limit. Please contact a developer.",
            app_commands.TransformerError: "This command experienced a transformer error.",
            app_commands.CommandAlreadyRegistered: "This command was already registered.",
            app_commands.CommandSignatureMismatch: "This command is currently out of sync.",
            app_commands.CheckFailure: "A check failed indicating you are not allowed to perform this action at this time.",
            app_commands.CommandNotFound: "This command could not be found.",
            app_commands.MissingApplicationID: "This application needs an application ID.",
            discord.InteractionResponded: "An exception occurred because I tried responding to an already-completed user interaction.",
            # General
            discord.LoginFailure: "Failed to log in.",
            discord.Forbidden: "An exception occurred because I tried completing an operation that I don't have permission to do.",
            discord.NotFound: "An exception occurred because I tried completing an operation that doesn't exist.",
            discord.DiscordServerError: "An exception occurred because of faulty communication with the Discord API server.",
        }
        return (
            error_messages.get(
                error.__class__,
                f"Oops, an unhandled error occurred: `{error.__class__}`.",
            ),
            delay,
        )

    async def handle_event_exception(
        self,
        event: str,
        client: MILBot,
    ):
        e_type, error, tb = sys.exc_info()
        if error:
            logger.exception(f"{e_type}: {error} occurred in `{event}` event.")
            exc_format = "".join(traceback.format_exception(e_type, error, tb, None))
            await client.errors_channel.send(
                f"**{error.__class__.__name__}** occurred in a `{event}` event:\n"
                f"```py\n{exc_format}\n```",
            )

    async def handle_command_exception(
        self,
        ctx: commands.Context[MILBot],
        error: Exception,
    ):
        message, _ = self.error_message(error)
        logger.exception(f"{error.__class__.__name__}: {error} occurred.")
        if isinstance(error, commands.CommandInvokeError):
            error = error.original
        try:
            raise error
        except Exception:
            await ctx.bot.errors_channel.send(
                f"**{error.__class__.__name__}** occurred in a command:\n"
                f"```py\n{traceback.format_exc()}\n```",
            )
            await ctx.reply(message)

    async def handle_ipc_exception(
        self,
        bot: MILBot,
        endpoint: str,
        error: Exception,
    ):
        try:
            raise error
        except NoEndpointFound:
            return
        except Exception:
            logger.exception(
                f"{error.__class__.__name__} occurred in `{endpoint}` endpoint.",
            )
        exc_format = "".join(
            traceback.format_exception(type(error), error, error.__traceback__),
        )
        await bot.errors_channel.send(
            f"**{error.__class__.__name__}** occurred in `{endpoint}` ipc endpoint:\n"
            f"```py\n{exc_format}\n```",
        )

    async def handle_interaction_exception(
        self,
        interaction: discord.Interaction[MILBot],
        error: Exception,
    ) -> None:
        # For commands on cooldown, delete message after delay
        message, delay = self.error_message(error)

        if interaction.response.is_done() and interaction.response.type not in (
            discord.InteractionResponseType.deferred_message_update,
            discord.InteractionResponseType.deferred_channel_message,
        ):
            msg = await interaction.edit_original_response(content=message)
        else:
            await interaction.response.defer(ephemeral=True)
            msg = await interaction.followup.send(message, ephemeral=True, wait=True)

        if delay is not None:
            await msg.delete(delay=delay)

        logger.exception(f"{error.__class__.__name__}: {error} occurred.")

        channel_name = None
        if interaction.channel:
            if isinstance(interaction.channel, discord.DMChannel):
                channel_name = f"DM with {interaction.channel.recipient}"
            elif isinstance(interaction.channel, discord.GroupChannel):
                channel_name = f"DM with {interaction.channel.recipients}"
            else:
                channel_name = interaction.channel.mention

        # Attempt to log to channel, but only log errors not from our code
        if error.__class__.__module__ != __name__:
            with contextlib.suppress():
                await interaction.client.errors_channel.send(
                    f"**{error.__class__.__name__}** occurred in {channel_name} interaction by {interaction.user.mention}:\n"
                    f"```py\n{traceback.format_exc()}```",
                )
