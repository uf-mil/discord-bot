from logging import getLogger

from discord.ext.ipc import Client
from quart import Quart, request

from src.env import WEBHOOK_SERVER_PORT

app = Quart(__name__)
ipc = Client(secret_key="37")


logger = getLogger(__name__)


@app.route("/", methods=["POST"])
async def main():
    # Get headers
    data = await request.get_json()
    event_type = request.headers.get("X-GitHub-Event")
    logger.info(f"Received event of type {event_type}.")
    if event_type == "ping":
        print("I was pinged!")
    else:
        action = data.get("action")
        await ipc.request(
            f"{event_type}_{action}" if action else str(event_type),
            github_data=data,
        )
    return {"succeeded": True}


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(WEBHOOK_SERVER_PORT) if WEBHOOK_SERVER_PORT else None,
    )
