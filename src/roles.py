from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .env import GUILD_ID
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class GroupButton(discord.ui.Button):
    def __init__(
        self,
        label: str,
        bot: MILBot,
        *,
        emoji: str | None = None,
        role_name: str | None = None,
    ):
        self.bot = bot
        self.role_name = role_name
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label,
            custom_id=f"roles_{label.lower()}",
            emoji=emoji,
        )

    async def callback(self, interaction: discord.Interaction):
        logger.info(f"User {interaction.user} requested {self.label} role")
        assert isinstance(interaction.user, discord.Member)  # buttons in guild only
        role_name = self.role_name or self.label
        role = discord.utils.get(self.bot.active_guild.roles, name=role_name)
        if role is None:
            return await interaction.response.send_message(
                f"Role {role_name} not found. Please contact an admin.",
                ephemeral=True,
            )

        # Make sure user removing role will not cause user to have no roles
        if role in interaction.user.roles and len(interaction.user.roles) == 2:
            return await interaction.response.send_message(
                "Sorry, you cannot remove your last role. Please try adding another role, and then try removing this role.",
                ephemeral=True,
            )

        # If user has New Member role, remove it
        new_member_role = discord.utils.get(
            self.bot.active_guild.roles,
            name="New Member",
        )
        if new_member_role in interaction.user.roles:
            await interaction.user.remove_roles(new_member_role)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"Removed your `{role_name}` role.",
                ephemeral=True,
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"Assigned you the `{role_name}` role.",
                ephemeral=True,
            )


class TeamRolesView(MILBotView):
    def __init__(self, bot: MILBot):
        super().__init__(timeout=None)
        self.add_item(GroupButton(label="Mechanical", bot=bot, emoji="🔧"))
        self.add_item(GroupButton(label="Electrical", bot=bot, emoji="🔋"))
        self.add_item(GroupButton(label="Software", bot=bot, emoji="💻"))


class MechanicalRolesView(MILBotView):
    def __init__(self, bot: MILBot):
        super().__init__(timeout=None)
        self.add_item(GroupButton(label="Structures and Manufacturing", bot=bot))
        self.add_item(GroupButton(label="Mechanisms and Testing", bot=bot))
        self.add_item(GroupButton(label="Dynamics and Controls", bot=bot))


class SummerRolesView(MILBotView):
    def __init__(self, bot: MILBot):
        super().__init__(timeout=None)
        self.add_item(
            GroupButton(
                label="I'm interested!",
                bot=bot,
                emoji="🤿",
                role_name="Interested in Summer 24",
            ),
        )


class RolesCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def teamroles(self, ctx):
        embed = discord.Embed(
            title="Team Selection",
            description="Want to learn more about a specific subteam in MIL? Please use the buttons below to join the appropriate channels. In those channels, you can get connected with team members working on projects in specific domains.",
            color=discord.Color.light_gray(),
        )
        view = TeamRolesView(self.bot)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    @commands.is_owner()
    async def mechroles(self, ctx):
        embed = discord.Embed(
            title="Subteam Selection",
            description="Interested in joining a mechanical subteam? Please use the buttons below to select a subteam that best suits your profile. Each button will allow you to see messages for one or more subteams that you may want to participate in.",
            color=discord.Color.orange(),
        )
        view = MechanicalRolesView(self.bot)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    @commands.is_owner()
    async def summer(self, ctx):
        embed = discord.Embed(
            title="🤿  Dive into MIL this summer!",
            color=discord.Color.gold(),
            description="As the sun shines brighter and the days grow longer, we are thrilled to extend an invitation to those looking to dive deeper into the world of robotics with us this summer of 2024. This season offers a unique opportunity for our members to soak up knowledge, take the helm of projects, and make waves in our community, given the slower pace of Gainesville during these months.\n\nThe summer season at MIL is not just about basking in the sun; it's a chance to ignite your passion, steer groundbreaking projects, and leave a lasting footprint in the sands of innovation. With a smaller crew on deck, you'll have the space to spread your wings, lead with gusto, and contribute to charting the course of our lab's research and development endeavors.\n\nPlease signal your readiness to jump into the summer adventure by joining the summer channel using the button below. This channel is your pier, where you'll catch all the exclusive announcements and discussions tailored to our upcoming summer semester.",
        )
        view = SummerRolesView(self.bot)
        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # If a user is given @Alumni, send a message welcoming them to alumni channel
        alumni_added = (
            self.bot.alumni_role in after.roles
            and self.bot.alumni_role not in before.roles
        )
        if not alumni_added:
            return

        entry = await self.bot.fetch_audit_log_targeting(
            after.id,
            [discord.AuditLogAction.role_update],
        )
        author = entry.user.mention if entry else "A user"
        await self.bot.alumni_channel.send(
            f"{author} gave {after.mention} the alumni role. Please welcome them to this channel! :wave:",
        )

    def _get_guild(self):
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            guild = self.bot.fetch_guild(GUILD_ID)
        assert isinstance(guild, discord.Guild)
        return guild

    def _get_text_channel(self, name, category=None):
        attrs = {
            "name": name,
        }
        if category:
            attrs["category"] = category
        channel = discord.utils.get(
            self.bot.active_guild.text_channels,
            **attrs,
        )
        if not channel:
            raise ValueError(
                f'Channel "#{name}" not found in guild {self.bot.active_guild.name}',
            )
        return channel

    def _get_category(self, name):
        category = discord.utils.get(self.bot.active_guild.categories, name=name)
        if not category:
            raise ValueError(
                f'Category "{name}" not found in guild {self.bot.active_guild.name}',
            )
        return category

    def _get_role(self, name):
        role = discord.utils.get(self.bot.active_guild.roles, name=name)
        assert isinstance(role, discord.Role)
        return role

    def _load_channels(self):
        text_channels = {
            "leave_channel": "leave-log",
            "general_channel": "general",
            "member_services_channel": "member-services",
            "alumni_channel": "alumni",
            "leaders_channel": "leads",
            "operations_leaders_channel": "operations-leadership",
            "software_leaders_channel": "software-leadership",
            "electrical_leaders_channel": "electrical-leadership",
            "mechanical_leaders_channel": "mechanical-leadership",
            "message_log_channel": "message-log",
            "errors_channel": "bot-errors",
            "software_projects_channel": "software-projects",
        }

        for attr, name in text_channels.items():
            setattr(self.bot, attr, self._get_text_channel(name))

    def _load_categories(self):
        categories = {
            "software_category_channel": "Software",
            "electrical_category_channel": "Electrical",
            "leads_category_channel": "Leadership",
            "mechanical_category_channel": "Mechanical",
        }

        for attr, name in categories.items():
            setattr(self.bot, attr, self._get_category(name))

        # Github channels that depend on categories
        self.bot.software_github_channel = self._get_text_channel(
            "github-updates",
            self.bot.software_category_channel,
        )
        self.bot.electrical_github_channel = self._get_text_channel(
            "github-updates",
            self.bot.electrical_category_channel,
        )
        self.bot.mechanical_github_channel = self._get_text_channel(
            "github-updates",
            self.bot.mechanical_category_channel,
        )
        self.bot.leads_github_channel = self._get_text_channel(
            "github-wiki-updates",
            self.bot.leads_category_channel,
        )

    def _load_roles(self):
        roles = {
            "egn4912_role": "EGN4912",
            "leaders_role": "Leaders",
            "sys_leads_role": "Systems Leadership",
            "software_leads_role": "Software Leadership",
            "bot_role": "Bot",
            "alumni_role": "Alumni",
            "new_grad_role": "New Graduate",
            "away_role": "Away from MIL",
        }

        for attr, name in roles.items():
            setattr(self.bot, attr, self._get_role(name))

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Fetches guild and role information.
        """
        self.bot.active_guild = self._get_guild()
        self._load_channels()
        self._load_categories()
        self._load_roles()


async def setup(bot: MILBot):
    await bot.add_cog(RolesCog(bot))
