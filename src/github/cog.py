from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord.ext import commands

from ..env import GITHUB_TOKEN
from .github import GitHub
from .types import (
    Issue,
)

if TYPE_CHECKING:
    from ..bot import MILBot


class GitHubCog(commands.Cog):
    def __init__(self, bot: MILBot):
        self.bot = bot
        self.github = GitHub(
            auth_token=GITHUB_TOKEN,
            bot=bot,
        )

    async def get_commit(self, commit_hash: str) -> discord.Embed | None:
        logging.info(f"Getting commit info for hash {commit_hash}...")
        try:
            commits = await self.github.search_commits(commit_hash)
        except aiohttp.ClientResponseError as e:
            if e.status == 422:
                return None
            else:
                raise

        commits = commits["items"]
        if commits:
            commit = commits[0]
            org_name = commit["repository"]["owner"]["login"]
            repo_name = commit["repository"]["name"]
            branches_response = await self.github.get_branches_for_commit(
                f"{org_name}/{repo_name}",
                commit_hash,
            )
            branches = [branch["name"] for branch in branches_response]

            # URL to get status and checks for the commit
            checks_response = await self.github.get_checks(
                f"{org_name}/{repo_name}",
                commit_hash,
            )

            embed = discord.Embed(
                title=commit["sha"],
                color=discord.Color.green(),
                url=commit["html_url"],
            )
            embed.set_thumbnail(url=commit["repository"]["owner"]["avatar_url"])
            if commit["author"]:
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
                    for check in checks_response["check_runs"]
                ),
                inline=False,
            )
            return embed

        return None

    def get_issue_or_pull(self, issue: Issue):
        res = discord.Embed(
            title=f"{issue['title']} (#{issue['number']})",
            color=discord.Color.green(),
            url=issue["html_url"],
            description=f"Details of this issue/pull request can be found [here]({issue['html_url']}).",
        )
        if issue["user"]:
            res.set_author(
                name=issue["user"]["login"],
                url=issue["user"]["html_url"],
                icon_url=issue["user"]["avatar_url"],
            )
            res.set_thumbnail(url=issue["user"]["avatar_url"])
        url_segments = issue["repository_url"].split("/")
        repository_name = f"{url_segments[-2]}/{url_segments[-1]}"
        res.add_field(
            name="Repository",
            value=f"[`{repository_name}`]({issue['repository_url']})",
            inline=True,
        )
        iso_date = issue["created_at"]
        iso_date = datetime.datetime.fromisoformat(iso_date)
        res.add_field(
            name="Created at",
            value=f"{discord.utils.format_dt(iso_date, style='F')}\n({discord.utils.format_dt(iso_date, style='R')})",
            inline=True,
        )
        res.add_field(
            name="State",
            value=issue["state"],
            inline=True,
        )
        res.add_field(
            name="Labels",
            value=", ".join(f"`{label['name']}`" for label in issue["labels"]),
            inline=True,
        )
        res.add_field(
            name="Assignees",
            value=", ".join(
                f"[`{assignee['login']}`]({assignee['html_url']})"
                for assignee in issue["assignees"]
            ),
            inline=True,
        )
        res.add_field(
            name="Milestone",
            value=(
                f"[`{issue['milestone']['title']}`]({issue['milestone']['html_url']})"
                if issue["milestone"]
                else "None"
            ),
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
            embeds = [await self.get_commit(commit_hash) for commit_hash in hashes]
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
                issue = await self.github.get_issue("uf-mil/mil", int(match))
                await message.reply(embed=self.get_issue_or_pull(issue))

        ELECTRICAL_SUB8_REGEX = r"\bs8\#(\d+)\b"
        matches = re.findall(
            ELECTRICAL_SUB8_REGEX,
            message.content,
            re.IGNORECASE | re.MULTILINE,
        )
        if matches:
            for match in matches:
                issue = await self.github.get_issue(
                    "uf-mil-electrical/SubjuGator8",
                    int(match),
                )
                await message.reply(embed=self.get_issue_or_pull(issue))

        ELECTRICAL_SUB9_REGEX = r"\bs9\#(\d+)\b"
        matches = re.findall(
            ELECTRICAL_SUB9_REGEX,
            message.content,
            re.IGNORECASE | re.MULTILINE,
        )
        if matches:
            for match in matches:
                issue = await self.github.get_issue(
                    "uf-mil-electrical/SubjuGator9",
                    int(match),
                )
                await message.reply(embed=self.get_issue_or_pull(issue))


async def setup(bot: MILBot):
    await bot.add_cog(GitHubCog(bot))
