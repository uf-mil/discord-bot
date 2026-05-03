{
  pkgs,
  ...
}:
let
in
pkgs.testers.runNixOSTest {
  name = "discord-bot-test";
  nodes = {
    bot-machine = {...}: {
      imports = [
        ../modules/uf-mil/discord-bot.nix
      ];
      uf-mil.discord-bot = {
        enable = true;
        discordToken = builtins.getEnv "DISCORD_TOKEN";
        guildId = builtins.getEnv "GUILD_ID";
        gspreadPrivateKey = builtins.getEnv "GSPREAD_PRIVATE_KEY";
        gspreadPrivateKeyId = builtins.getEnv "GSPREAD_PRIVATE_KEY_ID";
        gspreadServiceAccountEmail = builtins.getEnv "GSPREAD_SERVICE_ACCOUNT_EMAIL";
        gspreadTokenUri = builtins.getEnv "GSPREAD_TOKEN_URI";
        gspreadSpreadsheetName = builtins.getEnv "GSPREAD_SPREADSHEET_NAME";
        githubToken = builtins.getEnv "GITHUB_TOKEN";
        meetingNotesUrl = builtins.getEnv "LEADERS_MEETING_NOTES_URL";
        meetingUrl = builtins.getEnv "LEADERS_MEETING_URL";
      };
    };
  };
  testScript = {...}: ''
    machine.wait_for_unit("default.target")
    machine.wait_for_unit("discord-bot.service")
  '';
}
