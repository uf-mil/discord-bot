from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from .github_types import Issue
from .tasks import run_on_weekday
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot
   
   #discord.ui.Select
class SoftwareIssues(commands.Cog):
    
    software_issues_cache: list[Issue]
    
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.update_issues.start()
        software_issues_cache = []
    
    @run_on_weekday([calendar.MONDAY, calendar.THURSDAY], 0, 0)
    async def get_old_issues(self):
        await self.bot.wait_until_ready()
        past = datetime.today() - datetime.timedelta(weeks=2)
        stale_issues = set()
        for issue in self.software_issues_cache:
            if issue.created_at <= past:
                stale_issues.add(issue)
        
        software_leaders = [
            m
            for m in self.bot.software_projects_channel.members
            if self.bot.sys_leads_role in m.roles
        ]
        for leader in software_leaders:
            embed = discord.Embed(
                title="Potentially Stale Issues",
                color=discord.Color.teal(),
                description="These issues were created 2 weeks prior to " + datetime.today().isoformat(),
            )
                      
            for issue in stale_issues:
                embed.add_field(
                    name=f"#{issue.title}",
                    value=f"ID: {issue.id}\n{issue.short_description}\n",
                    inline=False,
                )
            
            await leader.send(embed=embed)
            
            
    @tasks.loop(seconds=5)
    async def update_issues(self):
        await self.bot.wait_until_ready()
        software_issues = await self.bot.github.UNFINISHED()    
        software_issues_cache = software_issues
    
async def setup(bot: MILBot):
    await bot.add_cog(SoftwareIssues(bot))
      