from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from .github_types import SoftwareProjectStatus
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot
    from .github_types import SoftwareProject


class ProjectSelect(discord.ui.Select):
    def __init__(self, bot: MILBot, projects: list[SoftwareProject]):
        self.bot = bot
        options = []
        for project in projects:
            open_issues = [
                i for i in project.items if i.status != SoftwareProjectStatus.DONE
            ]
            unassigned_issues = [i for i in project.items if i.assignees == []]
            description = (
                f"{len(open_issues)} issues open ({len(unassigned_issues)} unassigned)"
            )
            options.append(
                discord.SelectOption(
                    label=f"#{project.title}",
                    value=project.title,
                    description=description,
                    emoji=project.emoji,
                ),
            )
        super().__init__(
            custom_id="softwareproject:projectname",
            placeholder="Choose a project to join/leave...",
            options=options,
            max_values=len(options),
        )

    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            return

        for value in self.values:
            role = discord.utils.get(self.bot.active_guild.roles, name=value)
            if role and role not in interaction.user.roles:
                await interaction.user.add_roles(role)
            elif role and role in interaction.user.roles:
                await interaction.user.remove_roles(role)

        await interaction.response.send_message("Updated your roles!", ephemeral=True)
        await interaction.message.edit()


class SoftwareProjectsView(MILBotView):
    def __init__(self, bot: MILBot, software_projects: list[SoftwareProject]):
        super().__init__(timeout=None)
        self.add_item(ProjectSelect(bot, software_projects))


class SoftwareProjects(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.update_projects.start()

    @tasks.loop(seconds=5)
    async def update_projects(self):
        await self.bot.wait_until_ready()
        embed = discord.Embed(
            title="Software Projects",
            color=discord.Color.teal(),
            description="Looking for a software project to join? Look no further! Here are some of the projects that are currently looking for contributors.\n\nRemember that you should always be working on at least one project, and optionally more if you're interested! Each project channel will be forwarded updates and notifications relevant to the specific project.",
        )
        software_projects = await self.bot.github.get_software_projects()
        for project in software_projects:
            embed.add_field(
                name=f"#{project.title}",
                value=f"{project.short_description}",
                inline=False,
            )
            channel = discord.utils.get(
                self.bot.active_guild.channels,
                name=project.title,
            )
            if not channel:
                role = await self.bot.active_guild.create_role(
                    name=project.title,
                    mentionable=False,
                )
                overwrites: dict[
                    discord.Role | discord.Member,
                    discord.PermissionOverwrite,
                ] = {
                    self.bot.active_guild.default_role: discord.PermissionOverwrite(
                        read_messages=False,
                    ),
                    self.bot.software_leads_role: discord.PermissionOverwrite(
                        read_messages=True,
                    ),
                    self.bot.bot_role: discord.PermissionOverwrite(read_messages=True),
                    role: discord.PermissionOverwrite(read_messages=True),
                }
                channel = await self.bot.active_guild.create_text_channel(
                    project.title,
                    category=self.bot.software_category_channel,
                    position=9999,
                    topic=project.short_description,
                    overwrites=overwrites,
                )
        view = SoftwareProjectsView(self.bot, software_projects)
        oldest = [
            m
            async for m in self.bot.software_projects_channel.history(
                limit=1,
                oldest_first=True,
            )
        ]
        if len(oldest) < 1:
            await self.bot.software_projects_channel.send(embed=embed, view=view)
        elif oldest[0].embeds[0] != embed:
            await oldest[0].edit(embed=embed, view=view)


async def setup(bot: MILBot):
    await bot.add_cog(SoftwareProjects(bot))
