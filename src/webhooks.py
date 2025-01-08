from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING, ClassVar

import discord
from discord.ext import commands
from discord.ext.ipc.objects import ClientPayload
from discord.ext.ipc.server import Server

from src.env import IPC_PORT

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


class Webhooks(commands.Cog):

    SECURE_TEAM_NAMES: ClassVar[list[str]] = [
        "autopushers",
        "lead",
    ]

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.ipc = Server(
            bot,
            standard_port=int(IPC_PORT) if IPC_PORT else 1025,
            secret_key="37",
        )
        # Map from github username to real name
        self._real_names: dict[str, tuple[str, datetime.datetime]] = {}
        # Change dates - records the original date of a project item
        # so that we can compare it to the new date and send a message
        self._project_v2_item_change_dates: dict[str, datetime.datetime | None] = {}

    async def cog_load(self):
        await self.ipc.start()

    async def cog_unload(self):
        await self.ipc.stop()

    async def real_name(self, username: str) -> str:
        cache = self._real_names.get(username)
        if not cache or cache[1] > datetime.datetime.now() + datetime.timedelta(
            hours=4,
        ):
            # Call API
            user = await self.bot.github.get_user(username)
            self._real_names[username] = (
                user["name"] or user["login"],
                datetime.datetime.now(),
            )
        return self._real_names[username][0]

    @Server.route()
    async def ping(self, payload: ClientPayload):
        return "Pong!"

    def url(self, obj: dict[str, str], html=False) -> str:
        return f"<{obj['url']}>" if not html else f"<{obj['html_url']}>"

    def safe_index(self, text: str, index: str) -> int:
        try:
            return text.index(index)
        except ValueError:
            return 100000

    def format_github_body(self, text: str) -> str:
        # Wrap text to 1000 characters, or wherever is natural first (aka, the
        # first newline)

        # Find all cross-references to issues (user/repo#number) and replace them with links
        cross_issues = re.findall(r"([a-zA-Z0-9-_]+\/[a-zA-Z0-9-_]+)#([0-9]+)", text)
        for cross_issue in cross_issues:
            user_repo, number = cross_issue
            text = text.replace(
                f"{user_repo}#{number}",
                f"[{user_repo}#{number}](<https://github.com/{user_repo}/issues/{number}>)",
            )

        # Find all cross-references to commits (user/repo@commit) and replace them with links
        cross_commits = re.findall(
            r"([a-zA-Z0-9-_]+\/[a-zA-Z0-9-_]+)@([0-9a-zA-Z]{7,})",
            text,
        )
        for cross_commit in cross_commits:
            user_repo, commit = cross_commit
            text = text.replace(
                f"{user_repo}@{commit}",
                f"[{user_repo}@{commit}](<https://github.com/{user_repo}/commit/{commit}>)",
            )

        # Find all usernames and replace them with links
        usernames = re.findall(r"(?:^|\s+)@[a-zA-Z0-9-_]+", text)
        for username in usernames:
            # [1:] to remove @
            text = text.replace(
                username.strip(),
                f"[{username.strip()}](<https://github.com/{username.strip()[1:]}>)",
            )

        if "\n" in text:
            split_index = min(
                self.safe_index(text, "\n"),
                self.safe_index(text, "\r"),
                1000,
            )
            return text[:split_index] + "..."
        return text[:1000]

    def updates_channel(self, repository_or_login: dict | str) -> discord.TextChannel:
        login = (
            repository_or_login
            if isinstance(repository_or_login, str)
            else repository_or_login["owner"]["login"]
        )
        if (
            isinstance(repository_or_login, dict)
            and "full_name" in repository_or_login
            and (repository_or_login["full_name"] == "uf-mil/sw-leadership")
        ):
            return self.bot.software_leaders_channel
        if (
            isinstance(repository_or_login, dict)
            and "full_name" in repository_or_login
            and (repository_or_login["full_name"] == "uf-mil-mechanical/leadership")
        ):
            return self.bot.mechanical_leaders_channel
        if login.startswith("uf-mil-electrical"):
            return self.bot.electrical_github_channel
        if login.startswith("uf-mil-mechanical"):
            return self.bot.mechanical_github_channel
        if login.startswith("uf-mil-leadership"):
            return self.bot.leads_github_channel
        return self.bot.software_github_channel

    def leaders_channel(self, repository_or_login: dict | str) -> discord.TextChannel:
        login = (
            repository_or_login
            if isinstance(repository_or_login, str)
            else repository_or_login["owner"]["login"]
        )
        if login.startswith("uf-mil-electrical"):
            return self.bot.electrical_leaders_channel
        if login.startswith("uf-mil-mechanical"):
            return self.bot.mechanical_leaders_channel
        if login.startswith("uf-mil-leadership"):
            return self.bot.leads_github_channel
        return self.bot.software_leaders_channel

    def category_channel(self, login: str) -> discord.CategoryChannel:
        if login.startswith("uf-mil-electrical"):
            return self.bot.electrical_category_channel
        if login.startswith("uf-mil-mechanical"):
            return self.bot.mechanical_category_channel
        if login.startswith("uf-mil-leadership"):
            return self.bot.leads_category_channel
        return self.bot.software_category_channel

    def notify_channels(self, labels: list[dict]) -> list[discord.TextChannel]:
        notify_channel_names = [
            label["name"][:-7] for label in labels if label["name"].endswith("-notify")
        ]
        return [
            c
            for c in self.bot.active_guild.text_channels
            if c.name in notify_channel_names
        ]

    @Server.route()
    async def push(self, payload: ClientPayload):
        gh = payload.github_data
        # If push to master, send message to github-updates in the form of:
        # [User A](link) [pushed](commit_url) 1 commit to [branch_name](link) in [repo_name](link): "commit message"

        # Ignore branch deletions
        if gh["head_commit"] is None:
            return
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pushed = (
            f"[{'force-' if gh['forced'] else ''}pushed]({self.url(gh['head_commit'])})"
        )
        branch_url = f"https://github.com/{gh['repository']['full_name']}/tree/{gh['ref'].split('/')[-1]}"
        branch = f"[{gh['ref'].split('/')[-1]}](<{branch_url}>)"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        compare = f"[diff]({gh['compare']})"
        commit_count = len(gh["commits"])
        updates_channel = self.updates_channel(gh["repository"])
        # Every commit in an electrical repository should be sent out
        is_electrical = gh["repository"]["full_name"].startswith("uf-mil-electrical")
        if (
            gh["ref"] == "refs/heads/master"
            or gh["ref"] == "refs/heads/main"
            or is_electrical
        ):
            if commit_count == 1:
                if gh["head_commit"]["author"]["username"] == gh["sender"]["login"]:
                    by_statement = ""
                else:
                    author = (
                        f"[{await self.real_name(gh['head_commit']['author']['username'])}](<https://github.com/{gh['head_commit']['author']['username']}>)"
                        if "username" in gh["head_commit"]["author"]
                        else gh["head_commit"]["author"]["name"]
                    )
                    by_statement = f" by {author}"
                message = f"\"{self.format_github_body(gh['head_commit']['message'])}\""
                await updates_channel.send(
                    f"{name} {pushed} a commit{by_statement} to {branch} in {repo} ({compare}): {message}",
                )
            # ignore webhooks with zero commits
            elif commit_count > 1:
                preamble = f"{name} {pushed} {commit_count} commits to {branch} in {repo} ({compare}):\n"
                ellipsis = f"* ... _and {commit_count - 1} more commits_"
                formatted_commits = []
                for commit in gh["commits"]:
                    message = f"* [`{commit['id'][:7]}`]({self.url(commit)}): \"{self.format_github_body(commit['message'])[:100]}\""
                    if (
                        sum(len(line) + 1 for line in formatted_commits)
                        + len(message)
                        + len(preamble)
                        + len(ellipsis)
                        < 2000
                    ):
                        formatted_commits.append(message)
                    else:
                        break
                ellipsis = (
                    f"* ... _and {commit_count - len(formatted_commits) - 1} more commits_"
                    if len(formatted_commits) < commit_count - 1
                    else ""
                )
                formatted_commits.append(ellipsis)
                formatted_commits_str = "\n".join(formatted_commits)
                await updates_channel.send(
                    f"{preamble}{formatted_commits_str}",
                )

    @Server.route()
    async def star_created(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) starred [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'],html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} added a star to {repo}")

    @Server.route()
    async def issues_opened(self, payload: ClientPayload):
        # Send a message to github-updates in the form of:
        # [User A](link) opened issue [#XXX](link) in [repo_name](link): "issue title"
        gh = payload.github_data
        name = (
            f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'])})"
        )
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['issue']['title']}\""
        updates_channel = self.updates_channel(gh["repository"])
        message = f"{name} opened issue {issue} in {repo}: {title}"
        await updates_channel.send(message)
        for channel in self.notify_channels(gh["issue"]["labels"]):
            await channel.send(message)

    @Server.route()
    async def issues_closed(self, payload: ClientPayload):
        # Send a message to github-updates in the form of:
        # [User A](link) closed issue [#XXX](link) as "completed/not-planned" in [repo_name](link): "issue title"
        gh = payload.github_data
        name = (
            f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'])})"
        )
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        state = (
            "completed"
            if gh["issue"]["state_reason"] != "not_planned"
            else "not planned"
        )
        title = f"\"{gh['issue']['title']}\""
        updates_channel = self.updates_channel(gh["repository"])
        message = f"{name} closed issue {issue} as {state} in {repo}: {title}"
        await updates_channel.send(message)
        for channel in self.notify_channels(gh["issue"]["labels"]):
            await channel.send(message)

    @Server.route()
    async def organization_member_invited(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to software-leadership in the form of:
        # [User A](link) invited [User B](link) to [organization_name](link) in the following teams: {Team A, Team B}
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        invited = (
            f"[{await self.real_name(gh['user']['login'])}]({self.url(gh['user'], html=True)})"
            if "user" in gh
            else gh["email"]
        )
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        teams_resp = await self.bot.github.fetch(
            gh["invitation"]["invitation_teams_url"],
        )
        teams = ", ".join(
            [f"[{team['name']}]({self.url(team, html=True)})" for team in teams_resp],
        )
        updates_channel = self.leaders_channel(gh["organization"]["login"])
        await updates_channel.send(
            f"{name} invited {invited} to {org} in the following teams: {{{teams}}}",
        )

    @Server.route()
    async def organization_member_removed(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to software-leadership in the form of:
        # [User A](link) was removed from [organization_name](link)
        name = f"[{await self.real_name(gh['membership']['user']['login'])}]({self.url(gh['membership']['user'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        updates_channel = self.leaders_channel(gh["organization"]["login"])
        await updates_channel.send(f"{name} was removed from {org}")

    @Server.route()
    async def pull_request_opened(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) opened pull request [#XXX](link) in [repo_name](link): "pull request title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['pull_request']['title']}\""
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(
            f"{name} opened pull request {pr} in {repo}: {title}",
        )

    @Server.route()
    async def pull_request_closed(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) closed/merged pull request [#XXX](link) [by [User B](link)] as "completed/not-planned" in [repo_name](link): "pull request title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['pull_request']['title']}\""
        by = f"[{await self.real_name(gh['pull_request']['user']['login'])}]({self.url(gh['pull_request']['user'], html=True)})"
        by_statement = (
            f" by {by}"
            if gh["pull_request"]["user"]["login"] != gh["sender"]["login"]
            else ""
        )
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(
            f"{name} {'merged' if gh['pull_request']['merged'] else 'closed'} pull request {pr}{by_statement} in {repo}: {title}",
        )

    @Server.route()
    async def pull_request_review_requested(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) requested a review from [User B](link) on pull request [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        requested = f"[{await self.real_name(gh['requested_reviewer']['login'])}]({self.url(gh['requested_reviewer'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(
            f"{name} requested a review from {requested} on pull request {pr} in {repo}",
        )

    @Server.route()
    async def pull_request_review_submitted(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) submitted a review on pull request [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        action_statement = "submitted a review on"
        if gh["review"]["state"] == "changes_requested":
            action_statement = "requested changes on"
        elif gh["review"]["state"] == "approved":
            action_statement = "approved"
        elif gh["review"]["state"] == "commented":
            action_statement = "commented on"

        await updates_channel.send(
            f"{name} {action_statement} pull request {pr} in {repo}",
        )

    @Server.route()
    async def commit_comment(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) commented on commit [commit_sha](link) in [repo_name](link): "comment"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        commit = f"[`{gh['comment']['commit_id'][:7]}`]({self.url(gh['comment'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        comment = f"\"{self.format_github_body(gh['comment']['body'])}\""
        commented = f"[commented]({self.url(gh['comment'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(
            f"{name} {commented} on commit {commit} in {repo}: {comment}",
        )

    @Server.route()
    async def issues_comment_created(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) commented on issue [#XXX](link) in [repo_name](link): "comment"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        comment = f"\"{self.format_github_body(gh['comment']['body'])}\""
        commented = f"[commented]({self.url(gh['comment'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(
            f"{name} {commented} on issue {issue} in {repo}: {comment}",
        )

    @Server.route()
    async def issues_assigned(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) assigned [User B](link) to issue [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        assigned = f"[{await self.real_name(gh['assignee']['login'])}]({self.url(gh['assignee'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        issue_title = f"\"{gh['issue']['title']}\""
        # If the issue has a *-notify label, send a message to the relevant channel
        message = (
            f"{name} self-assigned issue {issue} in {repo}: {issue_title}"
            if gh["assignee"]["login"] == gh["sender"]["login"]
            else f"{name} assigned {assigned} to issue {issue} in {repo}: {issue_title}"
        )
        await updates_channel.send(message)

    @Server.route()
    async def issues_unassigned(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) unassigned [User B](link) from issue [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        unassigned = f"[{await self.real_name(gh['assignee']['login'])}]({self.url(gh['assignee'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        issue_title = f"\"{gh['issue']['title']}\""
        message = (
            f"{name} unassigned themself from issue {issue} in {repo}: {issue_title}"
            if gh["assignee"]["login"] == gh["sender"]["login"]
            else f"{name} unassigned {unassigned} from issue {issue} in {repo}: {issue_title}"
        )
        await updates_channel.send(message)

    @Server.route()
    async def pull_request_edited(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) edited the title of pull request [#XXX](link) in [repo_name](link) to "new title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['pull_request']['title']}\""
        updates_channel = self.updates_channel(gh["repository"])
        if "title" in gh["changes"] and gh["changes"]["title"]:
            await updates_channel.send(
                f"{name} edited the title of pull request {pr} in {repo} to {title}",
            )

    @Server.route()
    async def membership_added(self, payload: ClientPayload):
        gh = payload.github_data
        # If the user is being added to a team with the 'lead' word in the name, notify leads channel
        # Send a message to software-leadership in the form of:
        # [User A](link) added [User B](link) to [team_name](link) in [organization_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        added = f"[{await self.real_name(gh['member']['login'])}]({self.url(gh['member'], html=True)})"
        team = f"[{gh['team']['name']}]({self.url(gh['team'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        leaders_channel = self.leaders_channel(gh["organization"]["login"])
        if any(team_name in team.lower() for team_name in self.SECURE_TEAM_NAMES):
            await leaders_channel.send(
                f"{name} added {added} to {team} in {org}",
            )

    @Server.route()
    async def membership_removed(self, payload: ClientPayload):
        gh = payload.github_data
        # If the user is being removed from a team with the 'lead' word in the name, notify leads channel
        # Send a message to leads channel in the form of:
        # [User A](link) removed [User B](link) from [team_name](link) in [organization_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        removed = f"[{await self.real_name(gh['member']['login'])}]({self.url(gh['member'], html=True)})"
        team = f"[{gh['team']['name']}]({self.url(gh['team'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        leaders_channel = self.leaders_channel(gh["organization"]["login"])
        if any(team_name in team.lower() for team_name in self.SECURE_TEAM_NAMES):
            await leaders_channel.send(
                f"{name} removed {removed} from {team} in {org}",
            )

    @Server.route()
    async def public(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) made [repo_name](link) public
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} made {repo} public")

    @Server.route()
    async def repository_created(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) created [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} created {repo}")

    @Server.route()
    async def repository_deleted(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) deleted [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} deleted {repo}")

    @Server.route()
    async def repository_archived(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) archived [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} archived {repo}")

    @Server.route()
    async def repository_unarchived(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) unarchived [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} unarchived {repo}")

    @Server.route()
    async def issue_comment_created(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) commented on issue [#XXX](link) ("title") in [repo_name](link): "comment"

        # Ignore uf-mil-bot comments (which are automated and not useful to notify on)
        if gh["sender"]["login"] == "uf-mil-bot":
            return

        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        comment = f"\"{self.format_github_body(gh['comment']['body'])}\""
        commented = f"[commented]({self.url(gh['comment'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        issue_title = f"\"{gh['issue']['title']}\""

        # Forwarding
        # in the form of body containing:
        # > (forward to: #channel-name)
        FORWARD_REGEX = r"\s*\(forward to: #([A-Za-z\-0-9]+)\)\s*"
        forward_match = re.search(FORWARD_REGEX, gh["comment"]["body"])
        if forward_match:
            channel_name = forward_match.group(1)
            channel = discord.utils.get(
                self.bot.active_guild.text_channels,
                name=channel_name,
            )
            comment = comment.replace(forward_match.group(0), "")
            if channel:
                their_comment = f"[their comment]({self.url(gh['comment'], html=True)})"
                quoted_comment = "> " + comment.replace("\n", "\n> ")
                await channel.send(
                    f"{name} forwarded {their_comment} on issue {issue} ({issue_title}) in {repo} to this Discord channel:\n{quoted_comment}",
                )
        await updates_channel.send(
            f"{name} {commented} on issue {issue} ({issue_title}) in {repo}: {comment}",
        )

    @Server.route()
    async def check_suite_completed(self, payload: ClientPayload):
        gh = payload.github_data
        # If a fail occurs on the head branch, send a message to software-leadership in the form of:
        # 1 job ([link](link)) failed on commit [commit_sha](link) by [User A](link) in [repo_name](link) failed on [head branch name](link)
        if (
            gh["check_suite"]["conclusion"] == "failure"
            and gh["check_suite"]["head_branch"] == gh["repository"]["default_branch"]
        ):
            check_runs = await self.bot.github.fetch(
                gh["check_suite"]["check_runs_url"],
            )
            failed = [
                run
                for run in check_runs["check_runs"]
                if run["conclusion"] == "failure"
            ]
            failed_count = f"{len(failed)} job{'s' if len(failed) != 1 else ''}"
            failed_links = [
                f"[link {i+1}]({self.url(run, html=True)})"
                for i, run in enumerate(failed)
            ]
            failed_links_str = ", ".join(failed_links)
            name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
            commit = f"[`{gh['check_suite']['head_sha'][:7]}`](<https://github.com/{gh['repository']['full_name']}/commit/{gh['check_suite']['head_sha']}>)"
            repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
            branch = f"`{gh['check_suite']['head_branch']}`"
            leaders_channel = self.leaders_channel(gh["repository"])
            await leaders_channel.send(
                f"{failed_count} failed ({failed_links_str}) on commit {commit} by {name} in {repo} on {branch}",
            )

    @Server.route()
    async def label_created(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) created label "label_name" in [repo_name](link)

        # Ignore *-notify labels
        if gh["label"]["name"].endswith("-notify"):
            return

        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        label = f"\"{gh['label']['name']}\""
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} created label {label} in {repo}")

    @Server.route()
    async def label_deleted(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) deleted label "label_name" in [repo_name](link)

        # Ignore *-notify labels
        if gh["label"]["name"].endswith("-notify"):
            return

        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        label = f"\"{gh['label']['name']}\""
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        updates_channel = self.updates_channel(gh["repository"])
        await updates_channel.send(f"{name} deleted label {label} in {repo}")

    @Server.route()
    async def projects_v2_item_created(self, payload: ClientPayload):
        gh = payload.github_data
        # This item is queued so that quick updates don't spam channels
        # Send a message to the relevant project channels in the form of:
        # [User A](link) added a task to [project_name](link): "task name"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        proj_title, proj_url, proj_org = await self.bot.github.pvt_title_url_org(
            gh["projects_v2_item"]["project_node_id"],
        )
        project = f"[{proj_title}](<{proj_url}>)"
        (
            title,
            number,
            url,
        ) = await self.bot.github.project_item_content_title_number_url(
            gh["projects_v2_item"]["content_node_id"],
        )
        task = f"[#{number}](<{url}>)"
        item = f'"{title}"'
        updates_channel = discord.utils.get(
            self.category_channel(proj_org).text_channels,
            name=proj_title.lower().replace(" ", "-"),
        )
        if not updates_channel:
            return

        async def _post_coro():
            await updates_channel.send(
                f"{name} added a task ({task}) to {project}: {item}",
            )

        item_id = gh["projects_v2_item"]["node_id"]
        self.bot.tasks.run_in(
            datetime.timedelta(seconds=4),
            f"add_project_item_{item_id}",
            _post_coro,
        )

    @Server.route()
    async def projects_v2_item_edited(self, payload: ClientPayload):
        gh = payload.github_data
        # This event is queued so that quick updates don't spam channels
        # Date format: August 13
        # Send a message to github-updates in the form of:
        # - if end date was updated:
        #   [User A](link) updated the due date of a task (#21) from <prev date> to <new date> in [project_name](link): "task name"

        # Ensure that the end date was updated
        if gh["changes"]["field_value"]["field_name"] != "End date":
            return

        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        proj_title, proj_url, proj_org = await self.bot.github.pvt_title_url_org(
            gh["projects_v2_item"]["project_node_id"],
        )
        project = f"[{proj_title}](<{proj_url}>)"
        (
            title,
            number,
            url,
        ) = await self.bot.github.project_item_content_title_number_url(
            gh["projects_v2_item"]["content_node_id"],
        )
        task = f"[#{number}](<{url}>)"
        item = f'"{title}"'
        updates_channel = self.updates_channel(gh["organization"]["login"])

        to_dt = (
            datetime.datetime.fromisoformat(
                gh["changes"]["field_value"]["to"],
            ).strftime("%B %d")
            if gh["changes"]["field_value"]["to"]
            else "<not set>"
        )
        orig_date = (
            datetime.datetime.fromisoformat(gh["changes"]["field_value"]["from"])
            if gh["changes"]["field_value"]["from"]
            else None
        )

        async def _post_coro():
            orig_date = self._project_v2_item_change_dates[node_id]
            prev_dt = (
                orig_date.strftime("%B %d") if orig_date else "<not previously set>"
            )
            if orig_date == to_dt:
                return
            # examples: +7d, -2d
            day_diff = (
                (
                    datetime.datetime.fromisoformat(gh["changes"]["field_value"]["to"])
                    - orig_date
                ).days
                if gh["changes"]["field_value"]["to"] and orig_date
                else None
            )
            day_diff_str = (
                f" ({'+' if day_diff > 0 else ''}{day_diff}d)" if day_diff else ""
            )
            await updates_channel.send(
                f"{name} updated the due date of a task ({task}) in {project} from {prev_dt} to {to_dt}{day_diff_str}: {item}",
            )
            self._project_v2_item_change_dates.pop(node_id)

        node_id = gh["projects_v2_item"]["node_id"]
        if node_id not in self._project_v2_item_change_dates:
            self._project_v2_item_change_dates[node_id] = orig_date

        self.bot.tasks.run_in(
            datetime.timedelta(seconds=10),
            f"post_project_item_{node_id}",
            _post_coro,
        )

    @Server.route()
    async def projects_v2_item_deleted(self, payload: ClientPayload):
        gh = payload.github_data
        # This item is queued so that quick updates don't spam channels
        # Send a message to the relevant project channels in the form of:
        # [User A](link) removed a task to [project_name](link): "task name"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        proj_title, proj_url, proj_org = await self.bot.github.pvt_title_url_org(
            gh["projects_v2_item"]["project_node_id"],
        )
        project = f"[{proj_title}](<{proj_url}>)"
        (
            title,
            number,
            url,
        ) = await self.bot.github.project_item_content_title_number_url(
            gh["projects_v2_item"]["content_node_id"],
        )
        item = f'"{title}"'
        task = f"[#{number}](<{url}>)"
        updates_channel = discord.utils.get(
            self.category_channel(proj_org).text_channels,
            name=proj_title.lower().replace(" ", "-"),
        )
        if not updates_channel:
            return

        async def _post_coro():
            await updates_channel.send(
                f"{name} removed a task ({task}) from {project}: {item}",
            )

        item_id = gh["projects_v2_item"]["node_id"]
        self.bot.tasks.run_in(
            datetime.timedelta(seconds=30),
            f"deleted_project_item_{item_id}",
            _post_coro,
        )

    @Server.route()
    async def projects_v2_created(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) created a project [project_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        url = f"https://github.com/orgs/{gh['projects_v2']['owner']['login']}/projects/{gh['projects_v2']['number']}"

        # All projects_v2_created webhooks have the project title listed as
        # @user's untitled project, so we should wait a little bit of time
        # and then fetch the title later
        async def _post_coro():
            title = await self.bot.github.project_v2_node_title(
                gh["projects_v2"]["node_id"],
            )
            title = f"[{title}](<{url}>)"
            updates_channel = self.updates_channel(gh["organization"]["login"])
            await updates_channel.send(f"{name} created a project {title}")

        self.bot.tasks.run_in(
            datetime.timedelta(seconds=2),
            f"post_project_{gh['projects_v2']['node_id']}",
            _post_coro,
        )

    @Server.route()
    async def projects_v2_deleted(self, payload: ClientPayload):
        gh = payload.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) deleted a project [project_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        title = f"\"{gh['projects_v2']['title']}\""
        updates_channel = self.updates_channel(gh["organization"]["login"])
        await updates_channel.send(f"{name} deleted a project {title}")


async def setup(bot: MILBot):
    await bot.add_cog(Webhooks(bot))
