from __future__ import annotations

import asyncio
import datetime
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from ..env import GITHUB_OAUTH_CLIENT_ID
from .types import (
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
    from ..bot import MILBot


logger = logging.getLogger(__name__)


@dataclass
class UserContributions:
    issue_comments: list[dict[str, Any]]
    pull_requests: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    commits: list[dict[str, Any]]


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
        user_access_token: str | None = None,
    ):
        """
        Fetches a URL with the given method and headers.

        Raises ClientResponseError if the response status is not 2xx.
        """
        headers = {
            "Authorization": f"Bearer {user_access_token or self.auth_token}",
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
            response.raise_for_status()
            return await response.json()

    async def get_oauth_device_code(self) -> dict[str, Any]:
        url = "https://github.com/login/device/code"
        extra_headers = {
            "Accept": "application/json",
        }
        data = {"client_id": GITHUB_OAUTH_CLIENT_ID}
        response = await self.fetch(
            url,
            method="POST",
            extra_headers=extra_headers,
            data=data,
        )
        return response

    async def get_oauth_access_token(self, device_code: str) -> dict[str, str]:
        url = "https://github.com/login/oauth/access_token"
        extra_headers = {
            "Accept": "application/json",
        }
        data = {
            "client_id": GITHUB_OAUTH_CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
        response = await self.fetch(
            url,
            method="POST",
            extra_headers=extra_headers,
            data=data,
        )
        return response

    async def get_repo(self, repo_name: str) -> Repository:
        url = f"https://api.github.com/repos/{repo_name}"
        return await self.fetch(url)

    async def get_issue(self, repo_name: str, issue_number: int) -> Issue:
        url = f"https://api.github.com/repos/{repo_name}/issues/{issue_number}"
        return await self.fetch(url)

    async def get_branches_for_commit(self, repo_name: str, hash: str) -> list[Branch]:
        url = f"https://api.github.com/repos/{repo_name}/commits/{hash}/branches-where-head"
        return await self.fetch(url)

    async def pvti_team_name(self, node_id: str) -> str | None:
        """
        Returns the team name for a PVTI node id.
        """
        query = f"""
        {{
          node(id: \"{node_id}\") {{
            ... on ProjectV2Item {{
              fieldValueByName(name: "Team") {{
                ... on ProjectV2ItemFieldSingleSelectValue {{
                  name
                }}
              }}
            }}
          }}
        }}
        """
        properties = await self.fetch(
            "https://api.github.com/graphql",
            method="POST",
            data=json.dumps({"query": query}),
        )
        field_value_by_name = properties["data"]["node"]["fieldValueByName"]
        if not field_value_by_name:
            return None
        return field_value_by_name["name"]

    async def pvt_title_url_org(self, id: str) -> tuple[str, str, str]:
        """
        Title and URL for a PVT node id.
        """
        query = f"""
        {{
          node(id: \"{id}\") {{
            ... on ProjectV2 {{
              url
              title
              owner {{
                ... on Organization {{
                  login
                }}
              }}
            }}
          }}
        }}
        """
        properties = await self.fetch(
            "https://api.github.com/graphql",
            method="POST",
            data=json.dumps({"query": query}),
        )
        return (
            properties["data"]["node"]["title"],
            properties["data"]["node"]["url"],
            properties["data"]["node"]["owner"]["login"],
        )

    async def commits_across_branches(
        self,
        user_token: str,
        *,
        organization: str = "uf-mil-electrical",
    ) -> list[dict[str, Any]]:
        previous_monday_midnight = (
            datetime.datetime.now().astimezone()
            - datetime.timedelta(
                days=datetime.datetime.now().weekday(),
            )
        )
        previous_monday_midnight = previous_monday_midnight.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        previous_monday_format = previous_monday_midnight.isoformat()
        query = f"""
        {{
            organization(login: "{organization}") {{
            repositories(first: 10, orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
              nodes {{
                refs(first: 30, refPrefix: "refs/heads/") {{
                  nodes {{
                    ... on Ref {{
                      name
                      target {{
                        ... on Commit {{
                          history(first: 10, since: "{previous_monday_format}") {{
                            nodes {{
                              ... on Commit {{
                                author {{
                                  date
                                  email
                                  user {{
                                    login
                                  }}
                                }}
                                oid
                                message
                                repository {{
                                  nameWithOwner
                                }}
                              }}
                            }}
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        [properties, user_properties] = await asyncio.gather(
            self.fetch(
                "https://api.github.com/graphql",
                method="POST",
                data=json.dumps({"query": query}),
            ),
            self.fetch(
                "https://api.github.com/graphql",
                method="POST",
                data=json.dumps({"query": "{ viewer { login } }"}),
                user_access_token=user_token,
            ),
        )
        commits = []
        login = user_properties["data"]["viewer"]["login"]
        for repo in properties["data"]["organization"]["repositories"]["nodes"]:
            for branch in repo["refs"]["nodes"]:
                for commit in branch["target"]["history"]["nodes"]:
                    if commit["author"]["user"]["login"] == login:
                        commits.append(commit)
        commits.sort(
            key=lambda commit: datetime.datetime.fromisoformat(
                commit["author"]["date"],
            ),
            reverse=True,
        )
        return commits

    async def project_item_content_title_number_url(
        self,
        id: str,
    ) -> tuple[str, int, str]:
        """
        Returns the title for a particular project item, presunably either an issue
        or pull request.

        Args:
            id(str): Example: I_kwDOMh6AdM6SllQd
        """
        query = f"""
        query {{
            node(id: \"{id}\") {{
                ... on Issue {{
                    title
                    number
                    url
                }}
                ... on PullRequest {{
                    title
                    number
                    url
                }}
            }}
        }}
        """
        properties = await self.fetch(
            "https://api.github.com/graphql",
            method="POST",
            data=json.dumps({"query": query}),
        )
        return (
            properties["data"]["node"]["title"],
            properties["data"]["node"]["number"],
            properties["data"]["node"]["url"],
        )

    async def project_v2_node_title(self, node_id: str) -> str:
        """
        Returns the title of a project node.

        Args:
            node_id(str): Example: PVT_kwDOCpvu5c4AmagB
        """
        query = f"""
        query {{
          node(id: \"{node_id}\") {{
            ... on ProjectV2 {{
              title
            }}
          }}
        }}
        """
        properties = await self.fetch(
            "https://api.github.com/graphql",
            method="POST",
            data=json.dumps({"query": query}),
        )
        return properties["data"]["node"]["title"]

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
        user_access_token: str | None = None,
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
            user_access_token=user_access_token,
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
                or "on hold" in project_node["shortDescription"]
            ):
                continue
            project = SoftwareProject(project_node)
            projects.append(project)
        projects.sort(key=lambda p: p.title)
        return projects

    async def get_user_contributions(
        self,
        user_token: str,
        start: datetime.datetime,
        end: datetime.datetime | None = None,
    ) -> UserContributions:
        if not end:
            end = datetime.datetime.now().astimezone()
        start = start.astimezone()
        start_format = start.isoformat()

        username = (
            await self.fetch(
                "https://api.github.com/graphql",
                method="POST",
                data=json.dumps({"query": "{ viewer { login } }"}),
                user_access_token=user_token,
            )
        )["data"]["viewer"]["login"]

        query = f"""query {{
          rateLimit {{
            remaining
            limit
            used
            cost
          }}
          user(login: "{username}") {{
            login
            issueComments(first: 100, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
              nodes {{
                bodyText
                createdAt
                issue {{
                  title
                  number
                }}
                repository {{
                  nameWithOwner
                  name
                  owner {{
                    login
                  }}
                }}
              }}
            }}
            pullRequests(last: 100) {{
              nodes {{
                title
                number
                createdAt
                author {{
                  login
                }}
                repository {{
                    nameWithOwner
                    name
                    owner {{
                        login
                    }}
                }}
              }}
            }}
            issues(first: 100, filterBy: {{since: "{start_format}"}}) {{
              nodes {{
                title
                createdAt
                number
                author {{
                  login
                }}
                repository {{
                  nameWithOwner
                  name
                  owner {{
                    login
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        properties = await self.fetch(
            "https://api.github.com/graphql",
            method="POST",
            data=json.dumps({"query": query}),
        )
        filtered_issue_comments = [
            comment
            for comment in properties["data"]["user"]["issueComments"]["nodes"]
            if end > datetime.datetime.fromisoformat(comment["createdAt"]) > start
            and comment["repository"]["owner"]["login"].startswith("uf-mil")
        ]
        filtered_issue_comments.sort(
            key=lambda comment: datetime.datetime.fromisoformat(comment["createdAt"]),
            reverse=True,
        )
        filtered_pull_requests = [
            pr
            for pr in properties["data"]["user"]["pullRequests"]["nodes"]
            if pr["author"]["login"] == username
            and pr["repository"]["owner"]["login"].startswith("uf-mil")
            and end > datetime.datetime.fromisoformat(pr["createdAt"]) > start
        ]
        filtered_pull_requests.sort(
            key=lambda pr: datetime.datetime.fromisoformat(pr["createdAt"]),
            reverse=True,
        )
        filtered_issues = [
            issue
            for issue in properties["data"]["user"]["issues"]["nodes"]
            if issue["author"]["login"] == username
            and issue["repository"]["owner"]["login"].startswith("uf-mil")
            and end > datetime.datetime.fromisoformat(issue["createdAt"]) > start
        ]

        commits_call = (
            "https://api.github.com"
            + "/search/commits?q=author:"
            + username
            + "+org:uf-mil+org:uf-mil-electrical+org:uf-mil-mechanical+committer-date:>="
            + start_format
        )
        commits = await self.fetch(commits_call)
        commits = commits["items"]
        commits.sort(
            key=lambda commit: datetime.datetime.fromisoformat(
                commit["commit"]["author"]["date"],
            ),
            reverse=True,
        )
        # For commits to count, they must be in the main branch of the repository
        return UserContributions(
            issue_comments=filtered_issue_comments,
            pull_requests=filtered_pull_requests,
            issues=filtered_issues,
            commits=commits,
        )
