from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .roles import TeamRolesView

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class ChangeUsernameModal(discord.ui.Modal):
    username_input = discord.ui.TextInput(
        label="Full Name",
        placeholder="Albert Gator",
        min_length=3,
        max_length=32,
    )

    def __init__(self, bot: MILBot):
        super().__init__(timeout=180, title="Set Name")
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)
        await interaction.user.edit(nick=self.username_input.value)
        view = TeamRolesView(self.bot)
        logger.info(
            f"Confirmed {interaction.user} with requested name {self.username_input.value}.",
        )
        await interaction.response.send_message(
            f"Nice! Your name has been set to {self.username_input.value}. Now, choose which role best describes you! This will allow you to see chats relevant to your specific team. If you aren't associated with a specific team, please choose one and we will update your roles manually later.",
            view=view,
            ephemeral=True,
        )


class ChangeUsernameView(discord.ui.View):
    def __init__(self, bot: MILBot):
        self.bot = bot
        super().__init__()

    @discord.ui.button(label="Proceed", style=discord.ButtonStyle.green)
    async def change_username(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(ChangeUsernameModal(self.bot))


class WelcomeView(discord.ui.View):
    def __init__(self, bot: MILBot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Enter the server",
        style=discord.ButtonStyle.green,
        emoji="✅",
        custom_id="welcome:enter_server",
    )
    async def enter_server(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_message(
            "At this time, please use the button below to update your nickname in the server to your full chosen name, so it is easier for lab members to identify you. After joining the server, you will be unable to change your display name, and users without a full name will be removed from the server.",
            view=ChangeUsernameView(self.bot),
            ephemeral=True,
        )


class Welcome(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def preparewelcome(self, ctx):
        await ctx.message.delete()
        mil_emoji = discord.utils.get(self.bot.emojis, name="mil")
        links = "\n".join(
            (
                "* **Website:** https://mil.ufl.edu/",
                "* **SubjuGator:** https://subjugator.org/",
                "* **NaviGator:** https://navigatoruf.org/",
            ),
        )
        embed = discord.Embed(
            title=f"{mil_emoji} Welcome to the MIL Discord Server!",
            color=discord.Color.blue(),
            description=f"Welcome to the Discord chat server for the **Machine Intelligence Laboratory at the University of Florida**! All lab members, alumni, and interested members are welcome to join and participate in discussion. All lab activities will be coordinated through this server.\n\nWant to learn more about the Machine Intelligence Lab? Check out some of our links below:\n{links}\n\nTo gain access to all channels in the server, please click the button below.",
        )
        embed.set_image(
            url="https://media.discordapp.net/attachments/1141952429064204368/1155354222687158322/52512511915_33b25137dd_k.jpg?width=1602&height=1068",
        )
        embed.set_footer(
            text="Image shows three MILers on the dock of the Sydney Regatta centre at the 2022 RobotX competition in Penrith, NSW, Australia.",
        )
        view = WelcomeView(self.bot)
        await ctx.send(embed=embed, view=view)


async def setup(bot: MILBot):
    await bot.add_cog(Welcome(bot))
