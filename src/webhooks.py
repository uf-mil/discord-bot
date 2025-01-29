from __future__ import annotations

import abc
import datetime
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import discord
from discord.ext import commands
from discord.ext.ipc.objects import ClientPayload
from discord.ext.ipc.server import Server

from src.env import IPC_PORT

if TYPE_CHECKING:
    from .bot import MILBot


logger = logging.getLogger(__name__)


@dataclass
class WebhookResponse:
    github_data: dict[str, Any]
    # Bot
    bot: MILBot
    # Seconds to delay from posting, useful if successive updates to a resource
    # might make someone not want to post the first message
    delay_sec: int = 0
    # Map from github username to real name
    _real_names: ClassVar[dict[str, tuple[str, datetime.datetime]]] = {}
    # Change dates - records the original date of a project item
    # so that we can compare it to the new date and send a message
    _project_v2_item_change_dates: ClassVar[dict[str, datetime.datetime | None]] = {}

    @property
    def concurrency_id(self) -> str:
        return self.bot.tasks.unique_id()

    def after_send(self) -> None:
        pass

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

    def url(self, obj: dict[str, str], html=False) -> str:
        return f"<{obj['url']}>" if not html else f"<{obj['html_url']}>"

    def safe_index(self, text: str, index: str) -> int:
        try:
            return text.index(index)
        except ValueError:
            return 100000

    async def format_github_body(self, text: str) -> str:
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
            no_at = username.strip()[1:]
            text = text.replace(
                username.strip(),
                f"[@{await self.real_name(no_at)}](<https://github.com/{no_at}>)",
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

    async def ignore(self) -> bool:
        raise False

    @abc.abstractmethod
    def targets(self) -> list[discord.TextChannel]:
        raise NotImplementedError

    @abc.abstractmethod
    async def message(self) -> str:
        raise NotImplementedError


@dataclass
class Push(WebhookResponse):
    __multicast__ = True

    async def ignore(self) -> bool:
        is_electrical = self.github_data["repository"]["full_name"].startswith(
            "uf-mil-electrical",
        )
        return self.github_data["head_commit"] is None or (
            self.github_data["ref"] != "refs/heads/master"
            and self.github_data["ref"] != "refs/heads/main"
            and not is_electrical
        )

    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # If push to master, send message to github-updates in the form of:
        # [User A](link) [pushed](commit_url) 1 commit to [branch_name](link) in [repo_name](link): "commit message"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pushed = (
            f"[{'force-' if gh['forced'] else ''}pushed]({self.url(gh['head_commit'])})"
        )
        branch_url = f"https://github.com/{gh['repository']['full_name']}/tree/{gh['ref'].split('/')[-1]}"
        branch = f"[{gh['ref'].split('/')[-1]}](<{branch_url}>)"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        compare = f"[diff]({gh['compare']})"
        commit_count = len(gh["commits"])
        # Every commit in an electrical repository should be sent out
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
            message = (
                f"\"{await self.format_github_body(gh['head_commit']['message'])}\""
            )
            return f"{name} {pushed} a commit{by_statement} to {branch} in {repo} ({compare}): {message}"
        # ignore webhooks with zero commits
        else:
            preamble = f"{name} {pushed} {commit_count} commits to {branch} in {repo} ({compare}):\n"
            ellipsis = f"* ... _and {commit_count - 1} more commits_"
            formatted_commits = []
            for commit in gh["commits"]:
                message = f"* [`{commit['id'][:7]}`]({self.url(commit)}): \"{(await self.format_github_body(commit['message']))[:100]}\""
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
            return f"{preamble}{formatted_commits_str}"


@dataclass
class StarCreated(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) starred [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} starred {repo}"


@dataclass
class IssuesOpened(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        notify_channels = self.notify_channels(self.github_data["issue"]["labels"])
        return [self.updates_channel(self.github_data["repository"]), *notify_channels]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) opened issue [#XXX](link) in [repo_name](link): "issue title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['issue']['title']}\""
        return f"{name} opened issue {issue} in {repo}: {title}"


@dataclass
class IssuesClosed(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        notify_channels = self.notify_channels(self.github_data["issue"]["labels"])
        return [self.updates_channel(self.github_data["repository"]), *notify_channels]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) closed issue [#XXX](link) as "completed/not-planned" in [repo_name](link): "issue title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        state = (
            "completed"
            if gh["issue"]["state_reason"] != "not_planned"
            else "not planned"
        )
        title = f"\"{gh['issue']['title']}\""
        return f"{name} closed issue {issue} as {state} in {repo}: {title}"


@dataclass
class OrganizationMemberInvited(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.leaders_channel(self.github_data["organization"]["login"])]

    async def message(self) -> str:
        gh = self.github_data
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
        return f"{name} invited {invited} to {org} in the following teams: {{{teams}}}"


@dataclass
class OrganizationMemberRemoved(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.leaders_channel(self.github_data["organization"]["login"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to software-leadership in the form of:
        # [User A](link) was removed from [organization_name](link)
        name = f"[{await self.real_name(gh['membership']['user']['login'])}]({self.url(gh['membership']['user'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        return f"{name} was removed from {org}"


@dataclass
class PullRequestOpened(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) opened pull request [#XXX](link) in [repo_name](link): "pull request title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['pull_request']['title']}\""
        return f"{name} opened pull request {pr} in {repo}: {title}"


@dataclass
class PullRequestClosed(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
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
        return f"{name} {'merged' if gh['pull_request']['merged'] else 'closed'} pull request {pr}{by_statement} in {repo}: {title}"


@dataclass
class PullRequestReviewRequested(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) requested a review from [User B](link) on pull request [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        requested = f"[{await self.real_name(gh['requested_reviewer']['login'])}]({self.url(gh['requested_reviewer'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return (
            f"{name} requested a review from {requested} on pull request {pr} in {repo}"
        )


@dataclass
class PullRequestReviewSubmitted(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) submitted a review on pull request [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        action_statement = "submitted a review on"
        if gh["review"]["state"] == "changes_requested":
            action_statement = "requested changes on"
        elif gh["review"]["state"] == "approved":
            action_statement = "approved"
        elif gh["review"]["state"] == "commented":
            action_statement = "commented on"
        return f"{name} {action_statement} pull request {pr} in {repo}"


@dataclass
class CommitComment(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) commented on commit [commit_sha](link) in [repo_name](link): "comment"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        commit = f"[`{gh['comment']['commit_id'][:7]}`]({self.url(gh['comment'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        comment = f"\"{await self.format_github_body(gh['comment']['body'])}\""
        commented = f"[commented]({self.url(gh['comment'], html=True)})"
        return f"{name} {commented} on commit {commit} in {repo}: {comment}"


@dataclass
class IssuesCommentCreated(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) commented on issue [#XXX](link) in [repo_name](link): "comment"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        comment = f"\"{await self.format_github_body(gh['comment']['body'])}\""
        commented = f"[commented]({self.url(gh['comment'], html=True)})"
        return f"{name} {commented} on issue {issue} in {repo}: {comment}"


@dataclass
class IssuesAssigned(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) assigned [User B](link) to issue [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        assigned = f"[{await self.real_name(gh['assignee']['login'])}]({self.url(gh['assignee'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        issue_title = f"\"{gh['issue']['title']}\""
        # If the issue has a *-notify label, send a message to the relevant channel
        message = (
            f"{name} self-assigned issue {issue} in {repo}: {issue_title}"
            if gh["assignee"]["login"] == gh["sender"]["login"]
            else f"{name} assigned {assigned} to issue {issue} in {repo}: {issue_title}"
        )
        return message


@dataclass
class IssuesUnassigned(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) unassigned [User B](link) from issue [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        unassigned = f"[{await self.real_name(gh['assignee']['login'])}]({self.url(gh['assignee'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        issue_title = f"\"{gh['issue']['title']}\""
        message = (
            f"{name} unassigned themself from issue {issue} in {repo}: {issue_title}"
            if gh["assignee"]["login"] == gh["sender"]["login"]
            else f"{name} unassigned {unassigned} from issue {issue} in {repo}: {issue_title}"
        )
        return message


@dataclass
class PullRequestEdited(WebhookResponse):
    async def ignore(self) -> bool:
        return not (
            "title" in self.github_data["changes"]
            and self.github_data["changes"]["title"]
        )

    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) edited pull request [#XXX](link) in [repo_name](link): "pull request title"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        pr = f"[#{gh['pull_request']['number']}]({self.url(gh['pull_request'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        title = f"\"{gh['pull_request']['title']}\""
        return f"{name} edited pull request {pr} in {repo}: {title}"


@dataclass
class MembershipAdded(WebhookResponse):
    async def ignore(self) -> bool:
        return not any(
            team_name in self.github_data["team"]["name"].lower()
            for team_name in self.SECURE_TEAM_NAMES
        )

    def targets(self) -> list[discord.TextChannel]:
        return [self.leaders_channel(self.github_data["organization"]["login"])]

    async def message(self) -> str:
        gh = self.github_data
        # If the user is being added to a team with the 'lead' word in the name, notify leads channel
        # Send a message to software-leadership in the form of:
        # [User A](link) added [User B](link) to [team_name](link) in [organization_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        added = f"[{await self.real_name(gh['member']['login'])}]({self.url(gh['member'], html=True)})"
        team = f"[{gh['team']['name']}]({self.url(gh['team'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        return f"{name} added {added} to {team} in {org}"


@dataclass
class MembershipRemoved(WebhookResponse):
    async def ignore(self) -> bool:
        return not any(
            team_name in self.github_data["team"]["name"].lower()
            for team_name in self.SECURE_TEAM_NAMES
        )

    def targets(self) -> list[discord.TextChannel]:
        return [self.leaders_channel(self.github_data["organization"]["login"])]

    async def message(self) -> str:
        gh = self.github_data
        # If the user is being added to a team with the 'lead' word in the name, notify leads channel
        # Send a message to software-leadership in the form of:
        # [User A](link) added [User B](link) to [team_name](link) in [organization_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        removed = f"[{await self.real_name(gh['member']['login'])}]({self.url(gh['member'], html=True)})"
        team = f"[{gh['team']['name']}]({self.url(gh['team'], html=True)})"
        org = f"[{gh['organization']['login']}]({self.url(gh['organization'])})"
        return f"{name} removed {removed} from {team} in {org}"


@dataclass
class Public(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) made [repo_name](link) public
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} made {repo} public"


@dataclass
class RepositoryCreated(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) created [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} created {repo}"


@dataclass
class RepositoryDeleted(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) deleted [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} deleted {repo}"


@dataclass
class RepositoryArchived(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) archived [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} archived {repo}"


@dataclass
class RepositoryUnarchived(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) unarchived [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} unarchived {repo}"


@dataclass
class IssueCommentCreated(WebhookResponse):
    async def ignore(self) -> bool:
        return self.github_data["sender"]["login"] == "uf-mil-bot"

    def targets(self) -> list[discord.TextChannel]:
        # Forwarding
        # in the form of body containing:
        # > (forward to: #channel-name)
        res = [self.updates_channel(self.github_data["repository"])]
        FORWARD_REGEX = r"\s*\(forward to: #([A-Za-z\-0-9]+)\)\s*"
        forward_match = re.search(FORWARD_REGEX, self.github_data["comment"]["body"])
        if forward_match:
            channel_name = forward_match.group(1)
            channel = discord.utils.get(
                self.bot.active_guild.text_channels,
                name=channel_name,
            )
            if channel:
                res.append(channel)
        return res

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) commented on issue [#XXX](link) ("title") in [repo_name](link): "comment"
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        comment = f"\"{await self.format_github_body(gh['comment']['body'])}\""
        commented = f"[commented]({self.url(gh['comment'], html=True)})"
        issue_title = f"\"{gh['issue']['title']}\""
        return (
            f"{name} {commented} on issue {issue} ({issue_title}) in {repo}: {comment}"
        )


@dataclass
class CheckSuiteCompleted(WebhookResponse):
    async def ignore(self) -> bool:
        return not (
            self.github_data["check_suite"]["conclusion"] == "failure"
            and self.github_data["check_suite"]["head_branch"]
            == self.github_data["repository"]["default_branch"]
        )

    def targets(self) -> list[discord.TextChannel]:
        return [self.leaders_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # If a fail occurs on the head branch, send a message to software-leadership in the form of:
        # 1 job ([link](link)) failed on commit [commit_sha](link) by [User A](link) in [repo_name](link) failed on [head branch name](link)
        check_runs = await self.bot.github.fetch(
            gh["check_suite"]["check_runs_url"],
        )
        failed = [
            run for run in check_runs["check_runs"] if run["conclusion"] == "failure"
        ]
        failed_count = f"{len(failed)} job{'s' if len(failed) != 1 else ''}"
        failed_links = [
            f"[link {i+1}]({self.url(run, html=True)})" for i, run in enumerate(failed)
        ]
        failed_links_str = ", ".join(failed_links)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        commit = f"[`{gh['check_suite']['head_sha'][:7]}`](<https://github.com/{gh['repository']['full_name']}/commit/{gh['check_suite']['head_sha']}>)"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        branch = f"`{gh['check_suite']['head_branch']}`"
        return f"{failed_count} failed ({failed_links_str}) on commit {commit} by {name} in {repo} on {branch}"


@dataclass
class LabeledCreated(WebhookResponse):
    async def ignore(self) -> bool:
        return self.github_data["label"]["name"].endswith("-notify")

    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) added label [label_name](link) to issue [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        label = f"[{gh['label']['name']}]({self.url(gh['label'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} added label {label} to issue {issue} in {repo}"


@dataclass
class LabelDeleted(WebhookResponse):
    async def ignore(self) -> bool:
        return self.github_data["label"]["name"].endswith("-notify")

    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) removed label [label_name](link) from issue [#XXX](link) in [repo_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        label = f"[{gh['label']['name']}]({self.url(gh['label'], html=True)})"
        issue = f"[#{gh['issue']['number']}]({self.url(gh['issue'], html=True)})"
        repo = f"[{gh['repository']['full_name']}]({self.url(gh['repository'], html=True)})"
        return f"{name} removed label {label} from issue {issue} in {repo}"


@dataclass
class ProjectsV2ItemCreated(WebhookResponse):
    pvt_done: bool = False

    async def pvt(self) -> None:
        if self.pvt_done:
            return
        (
            self.proj_title,
            self.proj_url,
            self.proj_org,
        ) = await self.bot.github.pvt_title_url_org(
            self.github_data["projects_v2_item"]["project_node_id"],
        )
        self.pvt_done = True

    async def ignore(self) -> bool:
        await self.pvt()
        updates_channel = discord.utils.get(
            self.category_channel(self.proj_org).text_channels,
            name=self.proj_title.lower().replace(" ", "-"),
        )
        return not updates_channel

    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["repository"])]

    async def message(self) -> str:
        gh = self.github_data
        # This item is queued so that quick updates don't spam channels
        # Send a message to the relevant project channels in the form of:
        # [User A](link) added a task to [project_name](link): "task name"
        await self.pvt()
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        project = f"[{self.proj_title}](<{self.proj_url}>)"
        (
            title,
            number,
            url,
        ) = await self.bot.github.project_item_content_title_number_url(
            gh["projects_v2_item"]["content_node_id"],
        )
        task = f"[#{number}](<{url}>)"
        item = f'"{title}"'
        return f"{name} added a task ({task}) to {project}: {item}"


@dataclass
class ProjectsV2ItemEdited(WebhookResponse):
    delay_sec: int = 30

    def __post_init__(self):
        self.node_id = self.github_data["projects_v2_item"]["node_id"]
        self.to_dt = (
            datetime.datetime.fromisoformat(
                self.github_data["changes"]["field_value"]["to"],
            ).strftime("%B %d")
            if self.github_data["changes"]["field_value"]["to"]
            else "<not set>"
        )
        self.orig_date = (
            datetime.datetime.fromisoformat(
                self.github_data["changes"]["field_value"]["from"],
            )
            if self.github_data["changes"]["field_value"]["from"]
            else None
        )
        self.to_dt = (
            datetime.datetime.fromisoformat(
                self.github_data["changes"]["field_value"]["to"],
            ).strftime("%B %d")
            if self.github_data["changes"]["field_value"]["to"]
            else "<not set>"
        )
        if self.node_id not in self._project_v2_item_change_dates:
            self._project_v2_item_change_dates[self.node_id] = self.orig_date

    @property
    def concurrency_id(self) -> str:
        return f"post_project_item_{self.node_id}"

    async def ignore(self) -> bool:
        self.team_name = await self.bot.github.pvti_team_name(self.node_id)
        return (
            self.github_data["changes"]["field_value"]["field_name"] != "End date"
            or self.orig_date == self.to_dt
        )

    def targets(self) -> list[discord.TextChannel]:
        channels = [self.updates_channel(self.github_data["organization"]["login"])]
        if self.team_name:
            mappings: dict[str, Literal["sub9", "navigator", "drone"]] = {
                "SubjuGator": "sub9",
                "NaviGator": "navigator",
                "Drone": "drone",
            }
            channels.append(self.bot.leads_project_channel(mappings[self.team_name]))
        return channels

    def after_send(self) -> None:
        self._project_v2_item_change_dates.pop(self.node_id)

    async def message(self) -> str:
        gh = self.github_data
        # This event is queued so that quick updates don't spam channels
        # Date format: August 13
        # Send a message to github-updates in the form of:
        # - if end date was updated:
        #   [User A](link) updated the due date of a task (#21) from <prev date> to <new date> in [project_name](link): "task name"

        # Ensure that the end date was updated
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

        orig_date = self._project_v2_item_change_dates[self.node_id]
        prev_dt = orig_date.strftime("%B %d") if orig_date else "<not previously set>"
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
        return f"{name} updated the due date of a task ({task}) in {project} from {prev_dt} to {self.to_dt}{day_diff_str}: {item}"


@dataclass
class ProjectsV2ItemDeleted(WebhookResponse):
    delay_sec: int = 30
    pvt_set: bool = False

    def __post_init__(self):
        self.node_id = self.github_data["projects_v2_item"]["node_id"]
        self.to_dt = (
            datetime.datetime.fromisoformat(
                self.github_data["changes"]["field_value"]["to"],
            ).strftime("%B %d")
            if self.github_data["changes"]["field_value"]["to"]
            else "<not set>"
        )
        self.orig_date = (
            datetime.datetime.fromisoformat(
                self.github_data["changes"]["field_value"]["from"],
            )
            if self.github_data["changes"]["field_value"]["from"]
            else None
        )
        self.to_dt = (
            datetime.datetime.fromisoformat(
                self.github_data["changes"]["field_value"]["to"],
            ).strftime("%B %d")
            if self.github_data["changes"]["field_value"]["to"]
            else "<not set>"
        )
        if self.node_id not in self._project_v2_item_change_dates:
            self._project_v2_item_change_dates[self.node_id] = self.orig_date

    async def pvt(self) -> None:
        if self.pvt_set:
            return
        (
            self.proj_title,
            self.proj_url,
            self.proj_org,
        ) = await self.bot.github.pvt_title_url_org(
            self.github_data["projects_v2_item"]["project_node_id"],
        )
        self.pvt_set = True

    @property
    def concurrency_id(self) -> str:
        return f"deleted_project_item_{self.node_id}"

    async def ignore(self) -> bool:
        await self.pvt()
        self.channels = discord.utils.get(
            self.category_channel(self.proj_org).text_channels,
            name=self.proj_title.lower().replace(" ", "-"),
        )
        return not self.channels

    def targets(self) -> list[discord.TextChannel]:
        assert isinstance(self.channels, list)
        return self.channels[0]

    async def message(self) -> str:
        gh = self.github_data
        # This event is queued so that quick updates don't spam channels
        # Date format: August 13
        # Send a message to github-updates in the form of:
        # - if end date was updated:
        #   [User A](link) updated the due date of a task (#21) from <prev date> to <new date> in [project_name](link): "task name"

        # Ensure that the end date was updated
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        project = f"[{self.proj_title}](<{self.proj_url}>)"
        (
            title,
            number,
            url,
        ) = await self.bot.github.project_item_content_title_number_url(
            gh["projects_v2_item"]["content_node_id"],
        )
        task = f"[#{number}](<{url}>)"
        item = f'"{title}"'
        return f"{name} removed a task ({task}) from {project}: {item}"


@dataclass
class ProjectsV2Created(WebhookResponse):
    # All projects_v2_created webhooks have the project title listed as
    # @user's untitled project, so we should wait a little bit of time
    # and then fetch the title later
    delay_sec: int = 3

    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["organization"]["login"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) created a project [project_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        url = f"https://github.com/orgs/{gh['projects_v2']['owner']['login']}/projects/{gh['projects_v2']['number']}"

        title = await self.bot.github.project_v2_node_title(
            gh["projects_v2"]["node_id"],
        )
        title = f"[{title}](<{url}>)"
        return f"{name} created a project {title}"


@dataclass
class ProjectsV2Deleted(WebhookResponse):
    def targets(self) -> list[discord.TextChannel]:
        return [self.updates_channel(self.github_data["organization"]["login"])]

    async def message(self) -> str:
        gh = self.github_data
        # Send a message to github-updates in the form of:
        # [User A](link) deleted a project [project_name](link)
        name = f"[{await self.real_name(gh['sender']['login'])}]({self.url(gh['sender'], html=True)})"
        title = f"\"{gh['projects_v2']['title']}\""
        return f"{name} deleted a project {title}"


class Webhooks(commands.Cog):

    def __init__(self, bot: MILBot):
        self.bot = bot
        self.ipc = Server(
            bot,
            standard_port=int(IPC_PORT) if IPC_PORT else 1025,
            secret_key="37",
        )
        # Construct routes
        for subcls in WebhookResponse.__subclasses__():
            name = self.title_to_snake_case(subcls.__name__)
            self.ipc.route(name=name)(self.response_factory(subcls))

    def title_to_snake_case(self, title: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", title).lower()

    def response_factory(
        self,
        response_type: type[WebhookResponse],
    ) -> Callable[[Any, ClientPayload], Any]:
        # _ is for the presupposed self parameter, but since this isn't in our
        # main class, we don't need it for anything
        async def response(_: Any, payload: ClientPayload):
            wh = response_type(payload.github_data, self.bot)

            async def _post_coro():
                if await wh.ignore():
                    return
                for channel in wh.targets():
                    await channel.send(await wh.message())
                wh.after_send()

            # if delay requested, use task instead
            if wh.delay_sec <= 0:
                await _post_coro()
            else:
                self.bot.tasks.run_in(
                    datetime.timedelta(seconds=wh.delay_sec),
                    name=wh.concurrency_id,
                    coro=_post_coro,
                )

        return response

    async def cog_load(self):
        await self.ipc.start()

    async def cog_unload(self):
        await self.ipc.stop()

    @Server.route()
    async def ping(self, payload: ClientPayload):
        return "Pong!"


async def setup(bot: MILBot):
    await bot.add_cog(Webhooks(bot))
