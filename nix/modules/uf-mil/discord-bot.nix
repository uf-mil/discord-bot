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
    softwareMeetingNotesUrl = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The URL of the software meeting notes document.";
      default = null;
    };
    softwareOfficeHoursUrl = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The URL of the software office hours document.";
      default = null;
    };
    electricalMeetingNotesUrl = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The URL of the electrical meeting notes document.";
      default = null;
    };
    electricalOfficeHoursUrl = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The URL of the electrical office hours document.";
      default = null;
    };
    mechanicalMeetingNotesUrl = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The URL of the mechanical meeting notes document.";
      default = null;
    };
    mechanicalOfficeHoursUrl = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      description = "The URL of the mechanical office hours document.";
      default = null;
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
        ELECTRICAL_MEETINGS_CALENDAR = cfg.electricalMeetingNotesUrl;
        ELECTRICAL_OH_CALENDAR = cfg.electricalOfficeHoursUrl;
        EMAIL_USERNAME = cfg.emailUsername;
        EMAIL_PASSWORD = cfg.emailPassword;
        GITHUB_OAUTH_CLIENT_ID = cfg.githubOauthClientId;
        GITHUB_OAUTH_CLIENT_SECRET = cfg.githubOauthClientSecret;
        GITHUB_TOKEN = cfg.githubToken;
        GSPREAD_PRIVATE_KEY = cfg.gspreadPrivateKey;
        GSPREAD_PRIVATE_KEY_ID = cfg.gspreadPrivateKeyId;
        GSPREAD_SERVICE_ACCOUNT_EMAIL = cfg.gspreadServiceAccountEmail;
        GSPREAD_SPREADSHEET_NAME = cfg.gspreadSpreadsheetName;
        GSPREAD_TOKEN_URI = cfg.gspreadTokenUri;
        GUILD_ID = cfg.guildId;
        IPC_PORT = toString cfg.ipcPort;
        LEADERS_MEETING_NOTES_URL = cfg.meetingNotesUrl;
        LEADERS_MEETING_URL = cfg.meetingUrl;
        MECHANICAL_MEETINGS_CALENDAR = cfg.mechanicalMeetingNotesUrl;
        MECHANICAL_OH_CALENDAR = cfg.mechanicalOfficeHoursUrl;
        SOFTWARE_MEETINGS_CALENDAR = cfg.softwareMeetingNotesUrl;
        SOFTWARE_OH_CALENDAR = cfg.softwareOfficeHoursUrl;
        WEBHOOK_SERVER_PORT = toString cfg.webhookServer.port;
        WIKI_USERNAME = cfg.wikiUsername;
        WIKI_PASSWORD = cfg.wikiPassword;
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
