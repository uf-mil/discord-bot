from __future__ import annotations

import calendar
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from .github_types import SoftwareProjectStatus
from .reports import Team
from .tasks import run_on_weekday
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
                f"{len(open_issues)} issues ({len(unassigned_issues)} unassigned)"
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
        if interaction.message:
            await interaction.message.edit()


class SoftwareProjectsView(MILBotView):
    def __init__(self, bot: MILBot, software_projects: list[SoftwareProject]):
        super().__init__(timeout=None)
        self.add_item(ProjectSelect(bot, software_projects))


class SoftwareProjects(commands.Cog):

    software_projects_cache: list[SoftwareProject]

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.update_projects.start()
        self.software_projects_cache = []
        self.remind_to_join_project.start(self)
        self.whosonwhat.start(self)

    @run_on_weekday([calendar.MONDAY, calendar.THURSDAY], 0, 0)
    async def remind_to_join_project(self):
        await self.bot.wait_until_ready()
        assigned = set()
        for project in self.software_projects_cache:
            for item in project.items:
                if item.assignees:
                    assigned.update([i.name.lower() for i in item.assignees])
        unassigned_members = [
            m
            for m in self.bot.software_projects_channel.members
            if self.bot.egn4912_role in m.roles
            and m.display_name.lower() not in assigned
        ]
        for member in unassigned_members:
            embed = discord.Embed(
                title="Looking for a Software Project?",
                color=discord.Color.teal(),
                description="**Our records indicate you are not currently placed onto a software task.** Looking for a software project to join? Look no further! Here are some of the projects that are currently looking for contributors.\n\nRemember that you should always be working on at least one project, and optionally more if you're interested! Each project channel will be forwarded updates and notifications relevant to the specific project.",
            )
            for project in self.software_projects_cache:
                embed.add_field(
                    name=f"#{project.title}",
                    value=f"{project.short_description}\n**{len(project.unassigned_items)} unassigned tasks**",
                    inline=False,
                )
            embed.set_footer(
                text="If you are receiving this message accidentally, ensure that you are still assigned a task in Github and that your name on Discord and GitHub match.",
            )
            view = MILBotView()
            view.add_item(
                discord.ui.Button(
                    label="Go to #software-projects",
                    url=self.bot.software_projects_channel.jump_url,
                ),
            )
            await member.send(embed=embed, view=view)

    @run_on_weekday([calendar.MONDAY, calendar.THURSDAY], 0, 0)
    async def whosonwhat(self):
        embed = discord.Embed(
            title="Who's on what?",
            description="List of current assignments.",
            color=discord.Color.teal(),
        )
        assignments: dict[discord.Member, list[str]] = {}
        members = [
            m
            for m in self.bot.software_projects_channel.members
            if self.bot.egn4912_role in m.roles
        ]
        for member in members:
            assignments[member] = []
        for project in self.software_projects_cache:
            for item in project.items:
                if item.assignees and item.status != SoftwareProjectStatus.DONE:
                    for assignee in item.assignees:
                        member = discord.utils.find(
                            lambda m: m.display_name.lower() == assignee.name.lower(),
                            members,
                        )
                        if member:
                            assignments[member].append(
                                f"**#{project.title}** - {item.issue_number}",
                            )

        while assignments:
            field_text = ""
            first_letter = next(iter(assignments.keys())).display_name[0].upper()
            member = next(iter(assignments.keys()))
            while assignments:
                next_member = next(iter(assignments.keys()))
                status_emoji = "✅" if assignments[next_member] else "❌"
                additional_text = f"{status_emoji} `{next_member.display_name}:` {' | '.join(assignments[next_member]) if assignments[next_member] else 'missing :('}\n"
                if len(field_text) + len(additional_text) < 1024:
                    assignments.pop(next_member)
                    field_text += additional_text
                else:
                    break
            embed.add_field(
                name=f"Members {first_letter} - {member.display_name[0].upper()}",
                value=field_text,
                inline=False,
            )

        await self.bot.team_leads_ch(Team.SOFTWARE).send(embed=embed)

    @tasks.loop(seconds=5)
    async def update_projects(self):
        await self.bot.wait_until_ready()
        embed = discord.Embed(
            title="Software Projects",
            color=discord.Color.teal(),
            description="Looking for a software project to join? Look no further! Here are some of the projects that are currently looking for contributors.\n\nRemember that you should always be working on at least one project, and optionally more if you're interested! Each project channel will be forwarded updates and notifications relevant to the specific project.\n\nNote that GitHub Projects and Discord projects are separate - joining a project channel on Discord is distinct from the tasks on GitHub.",
        )
        software_projects = await self.bot.github.get_software_projects()
        self.software_projects_cache = software_projects
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
