from discord.ext.ipc import Client
from quart import Quart, request

from src.env import WEBHOOK_SERVER_PORT

app = Quart(__name__)
ipc = Client(secret_key="37")


@app.route("/", methods=["POST"])
async def main():
    # Get headers
    data = await request.get_json()
    event_type = request.headers.get("X-GitHub-Event")
    if event_type == "ping":
        print("I was pinged!")
    elif event_type == "push":
        await ipc.request("commit_created", github_data=data)
    elif event_type == "issues" and data["action"] == "opened":
        await ipc.request("issue_opened", github_data=data)
    elif event_type == "issues" and data["action"] == "closed":
        await ipc.request("issue_closed", github_data=data)
    elif event_type == "star" and data["action"] == "created":
        await ipc.request("star_created", github_data=data)
    elif event_type == "organization" and data["action"] == "member_added":
        await ipc.request("organization_member_added", github_data=data)
    elif event_type == "organization" and data["action"] == "member_invited":
        await ipc.request("organization_member_invited", github_data=data)
    elif event_type == "pull_request" and data["action"] == "opened":
        await ipc.request("pull_request_opened", github_data=data)
    elif event_type == "pull_request" and data["action"] == "closed":
        await ipc.request("pull_request_closed", github_data=data)
    elif event_type == "pull_request_review" and data["action"] == "submitted":
        await ipc.request("pull_request_review_submitted", github_data=data)
    return {"succeeded": True}


if __name__ == "__main__":
    app.run(port=int(WEBHOOK_SERVER_PORT) if WEBHOOK_SERVER_PORT else None)
