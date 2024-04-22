from __future__ import annotations

import datetime
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Literal

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from .env import GITHUB_TOKEN
from .github_types import (
    Branch,
    CheckRunsData,
    CommitSearchResults,
    Invitation,
    Issue,
    OrganizationTeam,
    Repository,
    SoftwareProject,
    User,
)

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class GitHub:
    def __init__(self, *, auth_token: str, bot: MILBot):
        self.auth_token = auth_token
        self.bot = bot

    async def fetch(
        self,
        url: str,
        *,
        method: Literal["GET", "POST"] = "GET",
        extra_headers: dict[str, str] | None = None,
        data: dict[str, Any] | str | None = None,
    ):
        """
        Fetches a URL with the given method and headers.

        Raises ClientResponseError if the response status is not 2xx.
        """
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
        }
        if extra_headers:
            headers.update(extra_headers)
        async with self.bot.session.request(
            method,
            url,
            headers=headers,
            data=data,
        ) as response:
            if not response.ok:
                logger.error(
                    f"Error fetching GitHub url {url}: {await response.json()}",
                )
            return await response.json()

    async def get_repo(self, repo_name: str) -> Repository:
        url = f"https://api.github.com/repos/{repo_name}"
        return await self.fetch(url)

    async def get_issue(self, repo_name: str, issue_number: int) -> Issue:
        url = f"https://api.github.com/repos/{repo_name}/issues/{issue_number}"
        return await self.fetch(url)

    async def get_branches_for_commit(self, repo_name: str, hash: str) -> list[Branch]:
        url = f"https://api.github.com/repos/{repo_name}/commits/{hash}/branches-where-head"
        return await self.fetch(url)

    async def get_checks(self, repo_name: str, hash: str) -> CheckRunsData:
        url = f"https://api.github.com/repos/{repo_name}/commits/{hash}/check-runs"
        extra_headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        return await self.fetch(url, extra_headers=extra_headers)

    async def search_commits(self, hash: str) -> CommitSearchResults:
        url = f"https://api.github.com/search/commits?q=hash:{hash}+org:uf-mil+org:uf-mil-electrical"
        headers = {
            "Accept": "application/vnd.github.cloak-preview",  # Required for commit search
        }
        return await self.fetch(url, extra_headers=headers)

    async def get_user(self, username: str) -> User:
        url = f"https://api.github.com/users/{username}"
        return await self.fetch(url)

    async def invite_user_to_org(
        self,
        user_id: int,
        org_name: str,
        team_id: int | None = None,
    ) -> Invitation:
        url = f"https://api.github.com/orgs/{org_name}/invitations"
        extra_headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        data: dict[str, Any] = {
            "invitee_id": user_id,
        }
        if team_id:
            data["team_ids"] = [team_id]
        str_data = json.dumps(data)
        return await self.fetch(
            url,
            method="POST",
            extra_headers=extra_headers,
            data=str_data,
        )

    async def get_team(self, org_name: str, team_name: str) -> OrganizationTeam:
        url = f"https://api.github.com/orgs/{org_name}/teams/{team_name}"
        return await self.fetch(url)

    async def get_software_projects(self) -> list[SoftwareProject]:
        query = """
            query {
              viewer {
                organization(login: "uf-mil") {
                  projectsV2(first: 15, query: "is:open") {
                    nodes {
                      title
                      number
                      shortDescription
                      items(first: 10) {
                        nodes {
                          type
                          id
                          content {
                            ... on Issue {
                              state
                              title
                              number
                            }
                          }
                          fieldValues(first: 5){
                            nodes {
                              ... on ProjectV2ItemFieldDateValue {
                                date
                                field {
                                  ... on ProjectV2Field {
                                    name
                                  }
                                }
                              }
                              ... on ProjectV2ItemFieldSingleSelectValue {
                                name
                                field {
                                  ... on ProjectV2SingleSelectField {
                                    name
                                  }
                                }
                              }
                              ... on ProjectV2ItemFieldUserValue {
                                users(first: 4) {
                                  nodes {
                                    login
                                    name
                                  }
                                }
                                field {
                                  ... on ProjectV2Field {
                                    name
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
              rateLimit {
                limit
                remaining
                used
                resetAt
              }
            }
        """
        properties = await self.fetch(
            "https://api.github.com/graphql",
            method="POST",
            data=json.dumps({"query": query}),
        )
        projects = []
        for project_node in properties["data"]["viewer"]["organization"]["projectsV2"][
            "nodes"
        ]:
            if (
                not project_node["title"]
                or "untitled" in project_node["title"]
                or not project_node["shortDescription"]
                or len(project_node["shortDescription"]) < 20
            ):
                continue
            project = SoftwareProject(project_node)
            projects.append(project)
        projects.sort(key=lambda p: p.title)
        return projects

    async def get_software_issues(
            self, 
            is_open = True, 
            updated_after: datetime.datetime | None = None,
            assignee: str | None = None,
            createdBy: str | None = None,
            labels: list[str] | None = None,
        ):
        
        query = """
            query {
                organization(login: "uf-mil") {
                    repositories (first: 5, hasIssuesEnabled: true) {
                        edges {
                            node {
                                name
                            }
                        }
                    }
                }
            }
        """
        
        software_issues = dict()
        response = await self.fetch(
            url = "https://api.github.com/graphql",
            method="POST",
            data=json.dumps({"query": query}),
        )
            
        for repo in response["data"]["organization"]["repositories"]["edges"]:
            issues = await self.bot.github.get_repo_issues(
                name = repo["node"]["name"],
                is_open = is_open,
                updated_after = updated_after,
                assignee = assignee,
                createdBy = createdBy,
                labels = labels,
            )
            software_issues.update({(repo["node"]["name"]): issues})

        return software_issues
    
    async def get_repo_issues(
            self,
            name: str,
            is_open = True, 
            updated_after: datetime.datetime | None = None,
            after: str = "",
            assignee: str | None = None,
            createdBy: str | None = None,
            labels: list[str] | None = None,
        ):

        query = f"""
            query {{ 
                organization(login: \"uf-mil\") {{
                    repository(name: \"{name}\") {{
                        issues( 
                            first: 100, 
                            states: {'OPEN' if is_open else 'CLOSED'},
                            after : \"{after}\", 
                            filterBy: {{
                                {'assignee : \"' + assignee + '\"' if assignee else ""},
                                {'createdBy : \"' + createdBy + '\"' if createdBy else ""},
                                {'labels : \"' + labels + '\"' if labels else "" },
                                {'since : \"' + datetime.datetime.isoformat(updated_after) + '\"' if updated_after else ""}
                            }}
                        ) {{
                            edges {{
                                node {{
                                    title
                                    id
                                    bodyText           
                                    createdAt
                                    updatedAt
                                    url
                                }}
                            }}
                
                            pageInfo {{
                                    endCursor
                                    hasNextPage
                            }}
                        }}
                    }}
                }}
            }}
        """
            
        response = await self.fetch(
            url = "https://api.github.com/graphql",
            method="POST",
            data= json.dumps({"query": query})
        )

        software_issues = list()
        for issue in response["data"]["organization"]["repository"]["issues"]["edges"]:
            software_issues.append(issue["node"])
            
        if response["data"]["organization"]["repository"]["issues"]["pageInfo"]["hasNextPage"]:
            software_issues.append(
                name = name,
                is_open = is_open,
                after = response["data"]["organization"]["repository"]["issues"]["pageInfo"]["endCursor"],
            )    
        
        return software_issues
    
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
        res.add_field(
            name="Repository",
            value=f"[`uf-mil/mil`]({issue['repository_url']})",
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
            value=f"[`{issue['milestone']['title']}`]({issue['milestone']['html_url']})"
            if issue["milestone"]
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
        if org_name not in ["uf-mil", "uf-mil-electrical"]:
            await interaction.response.send_message("Invalid organization name.")
            return

        # Ensure that the specified username is actually a GitHub user, and get
        # their user object
        try:
            user = await self.github.get_user(username)
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                await interaction.response.send_message(
                    f"Failed to find user with username {username}.",
                )
            raise e

        try:
            # If the org is uf-mil, invite to the "Developers" team
            if org_name == "uf-mil":
                team = await self.github.get_team(org_name, "developers")
                await self.github.invite_user_to_org(user["id"], org_name, team["id"])
            else:
                await self.github.invite_user_to_org(user["id"], org_name)
            await interaction.response.send_message(
                f"Successfully invited {username} to {org_name}.",
            )
        except Exception:
            await interaction.response.send_message(
                f"Failed to invite {username} to {org_name}.",
            )
            logger.exception(f"Failed to invite username {username} to {org_name}.")


async def setup(bot: MILBot):
    await bot.add_cog(GitHubCog(bot))
