{
  config,
  lib
}:
let
  cfg = config.uf-mil.discord-bot;
  webhookServerOptions = {
    enable = lib.mkEnableOption "Whether to enable the webhook server for responding to incoming webhooks.";
    port = lib.mkOption {
      type = lib.types.int;
      default = 8087;
      description = "The port on which the webhook server should listen.";
    };
  };
in
{
  options.uf-mil.discord-bot = {
    enable = lib.mkEnableOption "Whether to enable the Discord Bot.";
    user = lib.mkOption {
      type = lib.types.str;
      default = "uf-mil-bot";
      description = "The user under which the Discord bot will run.";
    };
    group = lib.mkOption {
      type = lib.types.str;
      default = "uf-mil-bot";
      description = "The group under which the Discord bot will run.";
    };
    discordToken = lib.mkOption {
      type = lib.types.str;
      description = "The token for the Discord bot.";
    };
    guildId = lib.mkOption {
      type = lib.types.str;
      description = "The ID of the Discord guild (server) the bot will operate in.";
    };
    gspreadPrivateKey = lib.mkOption {
      type = lib.types.str;
      description = "The private key for Google Sheets API authentication.";
    };
    gspreadPrivateKeyId = lib.mkOption {
      type = lib.types.str;
      description = "The private key ID for Google Sheets API authentication.";
    };
    gspreadServiceAccountEmail = lib.mkOption {
      type = lib.types.str;
      description = "The service account email for Google Sheets API authentication.";
    };
    gspreadTokenUri = lib.mkOption {
      type = lib.types.str;
      description = "The token URI for Google Sheets API authentication.";
    };
    gspreadSpreadsheetName = lib.mkOption {
      type = lib.types.str;
      description = "The name of the Google Sheets spreadsheet to interact with.";
    };
    githubToken = lib.mkOption {
      type = lib.types.str;
      description = "The token for GitHub API authentication.";
    };
    meetingNotesUrl = lib.mkOption {
      type = lib.types.str;
      description = "The URL of the meeting notes document.";
    };
    meetingUrl = lib.mkOption {
      type = lib.types.str;
      description = "The URL of the meeting.";
    };
    emailUsername = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The username for email notifications.";
      default = null;
    };
    emailPassword = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The password for email notifications.";
      default = null;
    };
    ipcPort = lib.mkOption {
      type = lib.types.nullOr lib.types.int;
      description = "The port on which the IPC communication takes place between the bot and the webhook server.";
      default = null;
    };
    githubOauthClientId = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The client ID for GitHub OAuth authentication.";
      default = null;
    };
    githubOauthClientSecret = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The client secret for GitHub OAuth authentication.";
      default = null;
    };
    databaseEngineUrl = lib.mkOption {
      type = lib.types.str;
      description = "The URL for the database engine (e.g., PostgreSQL) used by the bot.";
    };
    wikiUsername = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The username for wiki authentication.";
      default = null;
    };
    wikiPassword = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The password for wiki authentication.";
      default = null;
    };
    webhookServer = lib.mkOption {
      type = lib.types.submodule webhookServerOptions;
      description = "Options for the webhook server.";
      default = {};
    };
  };
  config = lib.mkIf cfg.enable {
    systemd.services.discord-bot = {
      description = "Discord Bot Service";
      after = [ "network.target" ];
      wants = [ "network.target" ];
      environment = {
        DISCORD_TOKEN = cfg.discordToken;
        GUILD_ID = cfg.guildId;
      };
      serviceConfig = {
        ExecStart = "${config.uf-mil.discord-bot.package}/bin/discord-bot";
        Restart = "always";
        User = cfg.user;
        Group = cfg.group;
      };
    };
    systemd.services.discord-bot-webhook-server = lib.mkIf cfg.webhookServer.enable {
      description = "Discord Bot Webhook Server";
      after = [ "network.target" ];
      wants = [ "network.target" ];
      environment = {
        IPC_PORT = toString cfg.ipcPort;
      };
      serviceConfig = {
        ExecStart = "${config.uf-mil.discord-bot.package}/bin/discord-bot-webhook-server";
        Restart = "always";
        User = cfg.user;
        Group = cfg.group;
      };
    };
    networking.firewall.allowedTCPPorts = lib.mkIf cfg.webhookServer.enable [ cfg.webhookServer.port ];
  };
}
