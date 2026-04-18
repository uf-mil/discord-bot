{
  lib,
  pkgs,
  discord-bot,
  ...
}:
let
  python3Packages = pkgs.python3Packages;
  buildPythonPackage = python3Packages.buildPythonPackage;
in
pkgs.dockerTools.buildLayeredImage {
  name = "discord-bot";
  tag = "latest";
  contents = [
    discord-bot
  ];
  config = {
    Cmd = [ "${discord-bot}/bin/discord-bot" ];
    WorkingData = "/app";
    Volumes = { "/app" = {}; };
  };
}
