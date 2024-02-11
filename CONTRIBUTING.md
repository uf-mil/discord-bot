# CONTRIBUTING.md

Welcome to the Machine Intelligence Laboratory's Discord Bot Repository!

### About

The lab's bot serves as a hub for the Machine Intelligence Laboratory (MIL). It facilitates communication, collaboration, and organization within the lab. Key features include:

- Integration with Google Sheets for easy access to shared resources.
- Notifications for upcoming meetings and events, linked to various Google Calendars.
- Automation of routine tasks to enhance productivity and focus on innovation.
- Providing quick access to important links, such as meeting notes and project repositories.

### Setting Up Your Own Instance

To contribute to the development or setup your own instance of the MIL Discord bot, follow these steps:

1. **Clone the Repository**: Start by cloning this repository to your local machine or development environment.

```bash
git clone https://github.com/uf-mil/discord-bot
cd discord-bot
```

2. **Environment Setup**:
   - Ensure you have Python installed.
   - Install necessary dependencies by running `pip` in your terminal.
   - Setup the `pre-commit` hooks for this repository. If you do not have `pre-commit`, you will need to install it (`pip3 install pre-commit`).
   - Create a `.env` file at the root of your project directory.

```bash
pip3 install -r requirements.txt
pre-commit install
```

3. **Setting up Discord**:
   - For Discord integration, create a new Discord bot through the Discord Developer Portal and obtain your bot token. You will then need to invite the bot to your testing server.
   - First, create your bot account through the Discord Developer Portal. The instructions can be found in the discord.py docs [here](https://discordpy.readthedocs.io/en/stable/discord.html).
   - Second, create your testing server. You can do this by asking one of the software leads for the server template. This server should have all the necessary channels and roles for testing your bot, so you shouldn't need to do much more setup beyond this.
   - Third, invite the bot to your testing server. The instructions for generating an invite link for your bot can be found in the discord.py docs linked above.

4. **Setting up Google Sheets:**
   - Make a copy of [this Google Sheet](https://docs.google.com/spreadsheets/d/1BTPLrs3Lr6J7030cHikgecBoWK1iVkkHlqKv4_yXcXk/edit?usp=sharing). This sheet has the format we use for our weekly reports.
   - You'll need to create a Google Cloud project and set up a service account with access to the Google Sheets API. Download the JSON credentials file for your service account. Good documentation on this can be found [here, in the `gspread` documentation](https://docs.gspread.org/en/v6.0.0/oauth2.html#for-bots-using-service-account).
   - Populate your `.env` file with the necessary environment variables as shown in the provided code snippet. This includes credentials for Google Sheets and your Discord bot token, among others.

5. **Setting up GitHub:**
    - You will need to create a GitHub personal access token for the bot to use for GitHub-related commands. Documentation on adding a PAT can be found [here](https://docs.github.com/en/enterprise-server@3.9/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-personal-access-token)

6. **Set up your `.env`:**
   - Create a `.env` file in your `src` folder for storing credentials.

`.env` file format:
```
DISCORD_TOKEN=          # your bot's token
GUILD_ID=               # your testing server ID
GSPREAD_PRIVATE_KEY_ID= # from JSON credentials file
GSPREAD_PRIVATE_KEY=
GSPREAD_SERVICE_ACCOUNT_EMAIL=
GSPREAD_TOKEN_URI=https://oauth2.googleapis.com/token
GSPREAD_SS_NAME=        # your testing spreadsheet name
GITHUB_TOKEN=           # github token
MEETING_NOTES_URL=      # leaders notes URL (can be any URL for testing purposes)
MEETING_URL=            # leaders meeting URL (can be any URL for testing purposes)

# These are optional and do not need to be added:
GENERAL_CALENDAR=
SOFTWARE_MEETINGS_CALENDAR=
SOFTWARE_OH_CALENDAR=
MECHANICAL_OH_CALENDAR=
MECHANICAL_MEETINGS_CALENDAR=
ELECTRICAL_OH_CALENDAR=
ELECTRICAL_MEETINGS_CALENDAR=
```

7. **Running the Bot**:
   - Run `python3 -m src.bot` to run your bot. Make sure your bot is connected to your Discord server.

### Contributing

Your contributions are what make the community amazing. We encourage you to be bold in your contributions and engage with the community to discuss improvements, features, and bug fixes. Whether it's coding, documentation, or ideas, your input is valued.

Let's work together to make the MIL Discord bot even better!
