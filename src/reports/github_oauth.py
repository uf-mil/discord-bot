from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import TYPE_CHECKING, ClassVar

import discord

from ..views import MILBotView, YesNo

if TYPE_CHECKING:
    from ..bot import MILBot


logger = logging.getLogger(__name__)


class OauthSetupButton(discord.ui.Button):

    _github_oauth_responses: ClassVar[
        dict[discord.Member, tuple[dict, datetime.datetime]]
    ] = {}
    _task_id: ClassVar[int] = 0

    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__(
            label="Connect/Re-connect your GitHub account",
            style=discord.ButtonStyle.green,
            custom_id="reports_view:oauth_connect",
            emoji=discord.PartialEmoji(name="github", id=1279957990882939010),
        )

    async def callback(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)
        if (
            self.bot.egn4912_role not in interaction.user.roles
            and self.bot.leaders_role not in interaction.user.roles
        ):
            await interaction.response.send_message(
                "❌ You must be an active member of EGN4912 to connect your GitHub account.",
                ephemeral=True,
            )
            return

        needs_new_headshot = True
        headshot_exists = os.path.exists(f"headshots/{interaction.user.id}.png")
        if headshot_exists:
            view = YesNo(interaction.user)
            await interaction.response.send_message(
                "Let's reconnect your GitHub account! Would you still like to use this profile picture?",
                view=view,
                file=discord.File(f"headshots/{interaction.user.id}.png"),
                ephemeral=True,
            )
            await view.wait()
            needs_new_headshot = not view.value
        if needs_new_headshot:
            if not interaction.user.dm_channel:
                await interaction.user.create_dm()
            dms_open = True
            try:
                await interaction.user.send(
                    "Feel free to send me a new headshot here! Just the image is fine.",
                )
            except discord.Forbidden:
                dms_open = False
            text = (
                "Let's get your GitHub connected! First, please **message me** a headshot of your face. This will be associated your account for when team leaders review your work for the previous week. For best results, please use a **square** (or roughly square) photo."
                + (
                    f" [You can click here to message me!]({interaction.user.dm_channel.jump_url})"
                    if interaction.user.dm_channel and dms_open
                    else ""
                )
            )
            if headshot_exists:
                await interaction.edit_original_response(
                    content=text,
                    attachments=[],
                    view=None,
                )
            else:
                await interaction.response.send_message(text, ephemeral=True)
            try:
                while True:
                    message = await self.bot.wait_for(
                        "message",
                        check=lambda m: m.author == interaction.user and m.attachments,
                        timeout=300,
                    )
                    assert isinstance(message, discord.Message)
                    if message.attachments[0].content_type and not message.attachments[
                        0
                    ].content_type.startswith("image"):
                        await message.reply("❌ Please send me an image file.")
                        continue
                    with open(f"headshots/{interaction.user.id}.png", "wb") as f:
                        await message.attachments[0].save(f)
                    await message.reply(
                        f"Thank you! Please return to the original message to continue connecting your GitHub account ([you can click here to get there faster!]({(await interaction.original_response()).jump_url})).",
                    )
                    break
            except asyncio.TimeoutError:
                await interaction.edit_original_response(
                    content="❌ You took too long to send me your headshot. Please try again.",
                    view=None,
                )
                return

        if (
            interaction.user in self._github_oauth_responses
            and datetime.datetime.now()
            < self._github_oauth_responses[interaction.user][1]
        ):
            device_code_response = self._github_oauth_responses[interaction.user][0]
            expires_in_dt = self._github_oauth_responses[interaction.user][1]
        else:
            device_code_response = await self.bot.github.get_oauth_device_code()
            logger.info(
                f"Generated new device code for {interaction.user}: {device_code_response['device_code'][:3]}...",
            )
            expires_in_dt = datetime.datetime.now() + datetime.timedelta(
                seconds=device_code_response["expires_in"],
            )
            self._github_oauth_responses[interaction.user] = (
                device_code_response,
                expires_in_dt,
            )
        code, device_code = (
            device_code_response["user_code"],
            device_code_response["device_code"],
        )
        button = discord.ui.Button(
            label="Authorize GitHub",
            url="https://github.com/login/device",
        )
        view = MILBotView()
        view.add_item(button)
        await interaction.edit_original_response(
            content=f"Thanks! To authorize your GitHub account, please visit the link below using the button and enter the following code:\n`{code}`\n\n* Please note that it may take a few seconds after authorizing in your browser to appear in Discord, due to GitHub limitations.\n* This authorization attempt will expire {discord.utils.format_dt(expires_in_dt, 'R')}.",
            view=view,
            attachments=[],
        )
        access_token = None
        resp = {}
        OauthSetupButton._task_id += 1
        id = self._task_id
        while not access_token and datetime.datetime.now() < expires_in_dt:
            await asyncio.sleep(
                (
                    resp["interval"]
                    if "interval" in resp
                    else device_code_response["interval"]
                ),
            )
            # Only use the latest response, otherwise we are going to get continuous slow_down responses
            if id != self._task_id:
                return
            resp = await self.bot.github.get_oauth_access_token(device_code)
            if "access_token" in resp:
                access_token = resp["access_token"]
            if "error" in resp and resp["error"] == "access_denied":
                logger.info(
                    f"When authorizing GitHub, {interaction.user} denied access.",
                )
                await interaction.edit_original_response(
                    content="❌ Authorization was denied (did you hit cancel?). Please try again.",
                    view=None,
                )
                return
        if access_token:
            async with self.bot.db_factory() as db:
                await db.add_github_oauth_member(
                    interaction.user.id,
                    device_code,
                    access_token,
                )
            logger.info(f"Successfully authorized GitHub for {interaction.user}.")
            await interaction.edit_original_response(
                content="Thanks! Your GitHub account has been successfully connected.",
                view=None,
            )
        else:
            logger.info(
                f"Attempting GitHub authorization for {interaction.user} expired.",
            )
            await interaction.edit_original_response(
                content="❌ Authorization expired. Please try again.",
                view=None,
            )
