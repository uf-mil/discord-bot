from __future__ import annotations

import calendar
import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from .github_types import Issue
from .reports import Team
from .tasks import run_on_weekday
from .views import MILBotView

if TYPE_CHECKING:
    from .bot import MILBot
    

class StaleSelect(discord.ui.Select):
    def __init__(self, stale_issues: dict):
        self.issues = stale_issues
        self.index = 0
        self.cache = dict()
        self.buttons = MILBotView()
        self.embed =  discord.Embed(
            title="Potentially Stale Issue",
            color=discord.Color.teal(),
            description= "" 
        )
        
        options = []
        for repo in stale_issues:
            options.append(
                discord.SelectOption(
                    label = repo,
                    value = repo,
                    description = f"{len(stale_issues[repo])} issues to review.",
                ),
            )
            
        super().__init__(
            #custom_id="softwareproject:projectname",
            placeholder="Choose a repo to review...",
            options=options,
            max_values=len(options),
        )
        
    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            return

        for value in self.values:
            self.cache.update({interaction.user.name : value})
            
            self.buttons.add_item(
                self.StaleButton(
                    label="Dismiss",
                    style=discord.ButtonStyle.green,
                    custom_id="issue_stale:dismiss",
                    stale = self
                )
            )
            
            self.buttons.add_item(
                self.StaleButton(
                    label="Close",
                    style=discord.ButtonStyle.red,
                    custom_id="issue_stale:close",
                    stale = self
                )
            )
            
            repo = self.cache[interaction.user.name]
            self.buttons.add_item(
                discord.ui.Button(
                    label="Link",
                    url=self.issues[repo][self.index]['url'],
                )
            )
            
            self.update_embed(interaction)
            await interaction.response.send_message(embed=self.embed, view=self.buttons, ephemeral=True)   
            
    def update_embed(self, interaction: discord.Interaction):
        repo = self.cache[interaction.user.name]
        limit = 800 #embed char limit = 1024
        limit -= len(self.issues[repo][self.index]['title']) - len(self.issues[repo][self.index]['id'])
        body = (self.issues[repo][self.index]['bodyText'][:limit] + "...") if len(self.issues[repo][self.index]['bodyText']) > limit else self.issues[repo][self.index]['bodyText']

        self.embed.description = f"Issue {self.index + 1} of {len(self.issues[repo])}."
        self.embed.clear_fields()
        self.embed.add_field(
            name=f"#{self.issues[repo][self.index]['title']}",
            value=f"ID: {self.issues[repo][self.index]['id']}\nDescription: {body}\n",
            inline=False,
        )
        self.buttons.children[2].url = self.issues[repo][self.index]['url']
    
    class StaleButton(discord.ui.Button):
        def __init__(self, stale: StaleSelect, style: discord.ButtonStyle, label: str, custom_id: str, emoji: str | None = None):
            self.stale = stale
            super().__init__(
                style=style,
                label=label,
                custom_id = custom_id,
                emoji=emoji,
            )
        
        async def callback(self, interaction: discord.Interaction):
            self.stale.index += 1
            
            repo = self.stale.cache[interaction.user.name]
            if self.stale.index == len(self.stale.issues[repo]):
                await interaction.response.send_message(f"Thank you for reviewing these issues.", ephemeral=True)
            
            else:
                self.stale.update_embed(interaction)
                await interaction.response.defer()
                await interaction.edit_original_response(embed = self.stale.embed, view = self.stale.buttons)

                #if  self.label == "Close":
                    #TODO Close functionality
                              
           

class SoftwareIssuesView(MILBotView):
    def __init__(self, stale_issues: list[dict]):
        super().__init__(timeout=None)
        self.add_item(StaleSelect(stale_issues))                      
             
class SoftwareIssues(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.get_old_issues.start()
            
    @run_on_weekday(calendar.MONDAY, 0, 0)
    #@tasks.loop(seconds=600)
    async def get_old_issues(self):
        await self.bot.wait_until_ready()
        open_issues = await self.bot.github.get_software_issues() 
        
        stale_issues: dict[list] = dict()
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(weeks=4)
        for repo in open_issues.keys():
            if len(open_issues[repo]) == 0:
                continue
            
            issues = []
            for issue in open_issues[repo]:
                if datetime.datetime.fromisoformat(issue["updatedAt"]) < past:
                    issues.append(issue)
            
            if len(issues) != 0:
                stale_issues[repo] = issues
        
        if (len(stale_issues) == 0):
            return
         
        embed = discord.Embed(
            title="Potentially Stale Topics for Review",
            color=discord.Color.teal(), 
            description= f"These issues have not been updated since {datetime.datetime.isoformat(past, timespec = "minutes")}.",
        )
        
        view = SoftwareIssuesView(stale_issues)
        await self.bot.team_leads_ch(Team.SOFTWARE).send(embed=embed, view=view)
                        
async def setup(bot: MILBot):
    await bot.add_cog(SoftwareIssues(bot))
      