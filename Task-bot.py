import datetime  # Module for working with dates and times
import discord   # Discord API wrapper
import os        # Module for interacting with the operating system
from discord.ext import commands  # Extension that aids in bot creation
from discord import app_commands  # Extension for registering slash commands

# Fetching the Discord bot token from environment variables
token = os.getenv("DISCORD_TOKEN")

# Creating a bot instance with command prefix '!' and all intents enabled
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# Defining a client class for the bot
class Task(discord.Client):

    def __init__(self):
        super().__init__(intents=discord.Intents.default())  # Initializing the parent class
        self.synced = False  # Flag to indicate whether syncing is done

    # Event handler for bot becoming ready
    async def on_ready(self):
        await tree.sync(guild=discord.Object(id=1223020880779809040))  # Syncing slash commands
        self.synced = True  # Setting sync flag to True
        print("Bot is online")  # Printing message when bot is online

# Creating an instance of the client class
bot = Task()

# Creating a CommandTree for registering slash commands
tree = app_commands.CommandTree(bot)

# Defining a slash command named "task"
@tree.command(name="task", description="Creates A Task", guild=discord.Object(id=1223020880779809040))
async def create_task(interaction: discord.Interaction, assignment: str, status: str, member: discord.Member):
    response = ["Task created"]  # Placeholder response
    
    time = datetime.datetime.today()  # Getting current date and time
    
    # Creating an embed for task details
    embed = discord.Embed(title="\U0001F4DD Task Details: ", description="", color=discord.Colour.random())
    embed.set_footer(text=f'{time}')  # Setting footer with current time
    embed.add_field(name=f'Task: assigned to {member.name}', value=f"INFO:\n{assignment} ", inline=False)
    embed.add_field(name=f"Status:", value=f'{status}', inline=True)
    embed.set_thumbnail(url=member.avatar)  # Setting thumbnail to member's avatar

    # Sending the embed as a response to the slash command
    await interaction.response.send_message(embed=embed)

# Running the bot with the provided token
bot.run(token)
