from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING, Literal

import discord
import github
import requests
from discord import app_commands
from discord.ext import commands
from github import Auth, AuthenticatedUser, Github
from github.Issue import Issue

from .env import GITHUB_TOKEN

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class GitHub(commands.Cog):
    def __init__(self, bot: MILBot):
        logging.info("Started GitHub initialization...")
        self.bot = bot
        self.github = Github(
            auth=Auth.Token(GITHUB_TOKEN),
        )
        self.mil_repo = self.github.get_repo("uf-mil/mil")
        self.mil_electrical_repos = []
        all_repos = self.github.get_user().get_repos(sort="pushed")
        for repo in all_repos:
            if "uf-mil-electrical" in repo.full_name:
                self.mil_electrical_repos.append(repo)
        logging.info("Completed GitHub initialization...")

    def get_commit(self, commit_hash: str) -> discord.Embed | None:
        logging.info(f"Getting commit info for hash {commit_hash}...")
        url = f"https://api.github.com/search/commits?q=hash:{commit_hash}+org:uf-mil+org:uf-mil-electrical"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.cloak-preview",  # Required for commit search
        }
        commit_response = requests.get(url, headers=headers)

        if commit_response.status_code == 200:
            commits = commit_response.json()["items"]
            if commits:
                commit = commits[0]
                org_name = commit["repository"]["owner"]["login"]
                repo_name = commit["repository"]["name"]
                branches_url = f"https://api.github.com/repos/{org_name}/{repo_name}/commits/{commit_hash}/branches-where-head"
                branches_response = requests.get(branches_url, headers=headers)
                branches = [branch["name"] for branch in branches_response.json()]

                # URL to get status and checks for the commit
                checks_url = f"https://api.github.com/repos/{org_name}/{repo_name}/commits/{commit_hash}/check-runs"
                checks_response = requests.get(
                    checks_url,
                    headers={
                        "Authorization": f"Bearer {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )

                embed = discord.Embed(
                    title=commit["sha"],
                    color=discord.Color.green(),
                    url=commit["html_url"],
                )
                embed.set_thumbnail(url=commit["repository"]["owner"]["avatar_url"])
                embed.set_author(
                    name=commit["author"]["login"],
                    url=commit["author"]["html_url"],
                    icon_url=commit["author"]["avatar_url"],
                )
                embed.add_field(
                    name="Repository",
                    value=f"[`{commit['repository']['full_name']}`]({commit['repository']['html_url']})",
                    inline=True,
                )
                iso_date = datetime.datetime.fromisoformat(
                    commit["commit"]["author"]["date"],
                )
                embed.add_field(
                    name="Committed at",
                    value=f"{discord.utils.format_dt(iso_date, style='F')} ({discord.utils.format_dt(iso_date, style='R')})",
                    inline=True,
                )
                embed.add_field(
                    name="Message",
                    value=commit["commit"]["message"][:1024],
                    inline=False,
                )
                embed.add_field(
                    name="Branches",
                    value=", ".join(
                        f"[`{branch}`]({commit['repository']['html_url']}/tree/{branch})"
                        for branch in branches
                    ),
                    inline=False,
                )
                embed.add_field(
                    name="Checks",
                    value="\n".join(
                        f"{'✅' if check['conclusion'] else '❌'} [{check['name']}]({check['html_url']})"
                        for check in checks_response.json()["check_runs"]
                    ),
                    inline=False,
                )
                return embed

        return None

    def get_issue_or_pull(self, issue: Issue):
        res = discord.Embed(
            title=f"{issue.title} (#{issue.number})",
            color=discord.Color.green(),
            url=issue.html_url,
            description=f"Details of this issue/pull request can be found [here]({issue.html_url}).",
        )
        res.set_author(
            name=issue.user.login,
            url=issue.user.html_url,
            icon_url=issue.user.avatar_url,
        )
        res.set_thumbnail(url=issue.user.avatar_url)
        res.add_field(
            name="Repository",
            value=f"[`{issue.repository.full_name}`]({issue.repository.html_url})",
            inline=True,
        )
        iso_date = issue.created_at
        res.add_field(
            name="Created at",
            value=f"{discord.utils.format_dt(iso_date, style='F')}\n({discord.utils.format_dt(iso_date, style='R')})",
            inline=True,
        )
        res.add_field(
            name="State",
            value=issue.state,
            inline=True,
        )
        res.add_field(
            name="Labels",
            value=", ".join(f"`{label.name}`" for label in issue.labels),
            inline=True,
        )
        res.add_field(
            name="Assignees",
            value=", ".join(
                f"[`{assignee.login}`]({assignee.html_url})"
                for assignee in issue.assignees
            ),
            inline=True,
        )
        res.add_field(
            name="Milestone",
            value=f"[`{issue.milestone.title}`]({issue.milestone.url})"
            if issue.milestone
            else "None",
            inline=True,
        )
        return res

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore own messages
        if message.author == self.bot.user:
            return

        hashes = re.findall(
            r"\b[0-9a-f]{5,40}(?!>)\b",
            message.content,
            re.IGNORECASE | re.MULTILINE,
        )
        if hashes:
            embeds = [self.get_commit(commit_hash) for commit_hash in hashes]
            if any(not e for e in embeds):
                pass
            else:
                await message.reply(
                    embeds=[e for e in embeds if isinstance(e, discord.Embed)],
                )

        # If a term is found starting with two hashtags followed by a number,
        # assume that this is referencing an issue or pull request in the main
        # repository. If this is found, send embeds for each issue or pull.
        DOUBLE_HASH_REGEX = r"\#\#(\d+)\b"
        matches = re.findall(
            DOUBLE_HASH_REGEX,
            message.content,
            re.IGNORECASE | re.MULTILINE,
        )
        if matches:
            for match in matches:
                issue = self.mil_repo.get_issue(int(match))
                await message.reply(embed=self.get_issue_or_pull(issue))

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def invite(
        self,
        interaction: discord.Interaction,
        username: str,
        org_name: Literal["uf-mil", "uf-mil-electrical"],
    ):
        """
        Invite a user to a MIL GitHub organization.

        Args:
            username: The username of the user to invite.
            org_name: The name of the organization to invite the user to.
        """
        # Use the Github class object to send an invite to the user
        if org_name == "uf-mil":
            org = self.github.get_organization("uf-mil")
        elif org_name == "uf-mil-electrical":
            org = self.github.get_organization("uf-mil-electrical")
        else:
            await interaction.response.send_message("Invalid organization name.")
            return

        # Ensure that the specified username is actually a GitHub user, and get
        # their user object
        try:
            user = self.github.get_user(username)
        except github.GithubException:
            await interaction.response.send_message(
                f"Failed to find user with username {username}.",
            )
            return

        if isinstance(user, AuthenticatedUser.AuthenticatedUser):
            await interaction.response.send_message(
                "Uh oh! I can't add a user who is already signed in.",
            )
            return

        try:
            # If the org is uf-mil, invite to the "Developers" team
            if org_name == "uf-mil":
                team = org.get_team_by_slug("developers")
                org.invite_user(user, teams=[team])
            else:
                org.invite_user(user)
            await interaction.response.send_message(
                f"Successfully invited {username} to {org_name}.",
            )
        except Exception:
            await interaction.response.send_message(
                f"Failed to invite {username} to {org_name}.",
            )
            logger.exception(f"Failed to invite username {username} to {org_name}.")


async def setup(bot: MILBot):
    await bot.add_cog(GitHub(bot))
