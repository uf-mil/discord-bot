import json

import aiohttp
import pytest
import pytest_asyncio

from src.env import GITHUB_TOKEN
from src.github import GitHub
from src.webhooks import MembershipRemoved, StarCreated

SOFTWARE_LEADERS_CHANNEL = "software-leads"
ELECTRICAL_LEADERS_CHANNEL = "electrical-leads"
MECHANICAL_LEADERS_CHANNEL = "mechanical-leads"
SOFTWARE_GITHUB_CHANNEL = "software-github"
ELECTRICAL_GITHUB_CHANNEL = "electrical-github"
MECHANICAL_GITHUB_CHANNEL = "mechanical-github"
LEADERS_GITHUB_CHANNEL = "leadership-github"


@pytest_asyncio.fixture
async def fake_bot():
    class FakeBot:
        def __init__(self):
            self.session = aiohttp.ClientSession()
            self.github = GitHub(auth_token=GITHUB_TOKEN, bot=self)
            self.software_leaders_channel = SOFTWARE_LEADERS_CHANNEL
            self.electrical_leaders_channel = ELECTRICAL_LEADERS_CHANNEL
            self.mechanical_leaders_channel = MECHANICAL_LEADERS_CHANNEL
            self.software_github_channel = SOFTWARE_GITHUB_CHANNEL
            self.electrical_github_channel = ELECTRICAL_GITHUB_CHANNEL
            self.mechanical_github_channel = MECHANICAL_GITHUB_CHANNEL
            self.leads_github_channel = LEADERS_GITHUB_CHANNEL

    fake_bot = FakeBot()
    yield fake_bot
    await fake_bot.session.close()


@pytest.mark.asyncio
async def test_membership_removed(fake_bot):
    with open("payloads/membership_removed.json") as f:
        payload = json.loads(f.read())

    webhook_response = MembershipRemoved(payload, fake_bot)
    assert (
        await webhook_response.message()
        == "[cameron brown](<https://github.com/cbrxyz>) removed [uf-mil-bot](<https://github.com/uf-mil-bot>) from [software-leads](<https://github.com/orgs/uf-mil/teams/software-leads>) in [uf-mil](<https://api.github.com/orgs/uf-mil>)"
    )


@pytest.mark.asyncio
async def test_star_created(fake_bot):
    names_channels = {
        "mechanical": ("mechanical", MECHANICAL_GITHUB_CHANNEL),
        "software": ("mil2", SOFTWARE_GITHUB_CHANNEL),
        "leadership": ("leadership", LEADERS_GITHUB_CHANNEL),
    }
    for name, (repo_name, channel) in names_channels.items():
        with open(f"payloads/star_created_{name}.json") as f:
            payload = json.loads(f.read())

        webhook_response = StarCreated(payload, fake_bot)
        assert (
            await webhook_response.message()
            == f"[cameron brown](<https://github.com/cbrxyz>) starred [uf-mil/{repo_name}](<https://github.com/uf-mil/{repo_name}>)"
        )
        assert webhook_response.targets() == [channel]

    with open("payloads/star_created_electrical.json") as f:
        payload = json.loads(f.read())

    webhook_response = StarCreated(payload, fake_bot)
    assert (
        await webhook_response.message()
        == "[cameron brown](<https://github.com/cbrxyz>) starred [uf-mil-electrical/NaviGator](<https://github.com/uf-mil-electrical/NaviGator>)"
    )
    assert webhook_response.targets() == [ELECTRICAL_GITHUB_CHANNEL]
