from typing import TypedDict


class User(TypedDict):
    login: str
    id: int
    node_id: str
    avatar_url: str
    gravatar_id: str
    url: str
    html_url: str
    followers_url: str
    following_url: str
    gists_url: str
    starred_url: str
    subscriptions_url: str
    organizations_url: str
    repos_url: str
    events_url: str
    received_events_url: str
    type: str
    site_admin: bool
    name: str | None
    company: str | None
    blog: str | None
    location: str | None
    email: str | None
    hireable: bool | None
    bio: str | None
    twitter_username: str | None
    public_repos: int
    public_gists: int
    followers: int
    following: int
    created_at: str
    updated_at: str


class Organization(TypedDict):
    login: str
    id: int
    node_id: str
    url: str
    repos_url: str
    events_url: str
    hooks_url: str
    issues_url: str
    members_url: str
    public_members_url: str
    avatar_url: str
    description: str
    name: str
    company: str
    blog: str
    location: str
    email: str
    is_verified: bool
    has_organization_projects: bool
    has_repository_projects: bool
    public_repos: int
    public_gists: int
    followers: int
    following: int
    html_url: str
    created_at: str
    updated_at: str
    type: str


class OrganizationTeam(TypedDict):
    id: int
    node_id: str
    url: str
    html_url: str
    name: str
    slug: str
    description: str
    privacy: str
    notification_setting: str
    permission: str
    members_url: str
    repositories_url: str
    parent: None
    members_count: int
    repos_count: int
    created_at: str
    updated_at: str
    organization: Organization


class Label(TypedDict):
    id: int
    node_id: str
    url: str
    name: str
    description: str
    color: str
    default: bool


class Milestone(TypedDict):
    url: str
    html_url: str
    labels_url: str
    id: int
    node_id: str
    number: int
    state: str
    title: str
    description: str
    creator: User
    open_issues: int
    closed_issues: int
    created_at: str
    updated_at: str
    closed_at: str | None
    due_on: str


class PullRequest(TypedDict):
    url: str
    html_url: str
    diff_url: str
    patch_url: str


class RepositoryPermissions(TypedDict):
    admin: bool
    push: bool
    pull: bool


class RepositorySecurityAndAnalysisItem(TypedDict):
    status: str


class RepositorySecurityAndAnalysis(TypedDict):
    advanced_security: RepositorySecurityAndAnalysisItem
    secret_scanning: RepositorySecurityAndAnalysisItem
    secret_scanning_push_protection: RepositorySecurityAndAnalysisItem


class Repository(TypedDict):
    id: int
    node_id: str
    name: str
    full_name: str
    owner: User
    private: bool
    html_url: str
    description: str | None
    fork: bool
    url: str
    archive_url: str
    assignees_url: str
    blobs_url: str
    branches_url: str
    collaborators_url: str
    comments_url: str
    commits_url: str
    compare_url: str
    contents_url: str
    contributors_url: str
    deployments_url: str
    downloads_url: str
    events_url: str
    forks_url: str
    git_commits_url: str
    git_refs_url: str
    git_tags_url: str
    git_url: str
    issue_comment_url: str
    issue_events_url: str
    issues_url: str
    keys_url: str
    labels_url: str
    languages_url: str
    merges_url: str
    milestones_url: str
    notifications_url: str
    pulls_url: str
    releases_url: str
    ssh_url: str
    stargazers_url: str
    statuses_url: str
    subscribers_url: str
    subscription_url: str
    tags_url: str
    teams_url: str
    trees_url: str
    clone_url: str
    mirror_url: str
    hooks_url: str
    svn_url: str
    homepage: str | None
    language: str | None
    forks_count: int
    stargazers_count: int
    watchers_count: int
    size: int
    default_branch: str
    open_issues_count: int
    is_template: bool
    topics: list[str]
    has_issues: bool
    has_projects: bool
    has_wiki: bool
    has_pages: bool
    has_downloads: bool
    has_discussions: bool
    archived: bool
    disabled: bool
    visibility: str
    pushed_at: str
    created_at: str
    updated_at: str
    permissions: RepositoryPermissions
    security_and_analysis: RepositorySecurityAndAnalysis


class Issue(TypedDict):
    id: int
    node_id: str
    url: str
    repository_url: str
    labels_url: str
    comments_url: str
    events_url: str
    html_url: str
    number: int
    state: str
    title: str
    body: str
    user: User
    labels: list[Label]
    assignee: User
    assignees: list[User]
    milestone: Milestone
    locked: bool
    active_lock_reason: str
    comments: int
    pull_request: PullRequest
    closed_at: str | None
    created_at: str
    updated_at: str
    closed_by: User | None
    author_association: str
    state_reason: str | None


class CheckRunOutput(TypedDict):
    title: str
    summary: str
    text: str
    annotations_count: int
    annotations_url: str


class CheckSuite(TypedDict):
    id: int


class App(TypedDict):
    id: int
    slug: str
    node_id: str
    owner: User
    name: str
    description: str
    external_url: str
    html_url: str
    created_at: str
    updated_at: str
    permissions: dict
    events: list[str]


class CheckRun(TypedDict):
    id: int
    head_sha: str
    node_id: str
    external_id: str
    url: str
    html_url: str
    details_url: str
    status: str
    conclusion: str
    started_at: str
    completed_at: str
    output: CheckRunOutput
    name: str
    check_suite: CheckSuite
    app: App
    pull_requests: list[PullRequest]


class CheckRunsData(TypedDict):
    total_count: int
    check_runs: list[CheckRun]


class CommitAuthor(TypedDict):
    date: str
    name: str
    email: str


class Tree(TypedDict):
    url: str
    sha: str


class Commit(TypedDict):
    url: str
    author: CommitAuthor
    committer: CommitAuthor
    message: str
    tree: Tree
    comment_count: int


class User(TypedDict):
    login: str
    id: int
    node_id: str
    avatar_url: str
    gravatar_id: str
    url: str
    html_url: str
    followers_url: str
    following_url: str
    gists_url: str
    starred_url: str
    subscriptions_url: str
    organizations_url: str
    repos_url: str
    events_url: str
    received_events_url: str
    type: str
    site_admin: bool


class ParentCommit(TypedDict):
    url: str
    html_url: str
    sha: str


class GitHubCommit(TypedDict):
    url: str
    sha: str
    html_url: str
    comments_url: str
    commit: Commit
    author: User | None  # This can be None if the user is not on GitHub anymore
    committer: User | None  # This can also be None
    parents: list[ParentCommit]
    repository: Repository


class CommitSearchResults(TypedDict):
    total_count: int
    incomplete_results: bool
    items: list[GitHubCommit]


class CommitPointer(TypedDict):
    sha: str
    url: str


class Branch(TypedDict):
    name: str
    commit: CommitPointer
    protected: bool


class Invitation(TypedDict):
    id: int
    login: str
    node_id: str
    email: str | None
    role: str
    created_at: str
    inviter: User
    team_count: int
    invitation_teams_url: str
    invitation_source: str
