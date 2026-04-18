{
  lib,
  pkgs,
  buildPythonPackage,
  fetchPypi,
  setuptools,
  ...
}:
let
  better-ipc = buildPythonPackage (finalAttrs: {
    version = "2.0.3";
    pname = "better-ipc";
    src = fetchPypi {
      inherit (finalAttrs) pname version;
      hash = lib.fakeHash;
    };
    build-system = [
      setuptools
    ];
    dependencies = with pkgs.python3Packages; [
      websockets
    ];
  });
  gspread-asyncio = buildPythonPackage (finalAttrs: {
    version = "2.0.0";
    pname = "gspread-asyncio";
    src = fetchPypi {
      inherit (finalAttrs) pname version;
      hash = lib.fakeHash;
    };
    build-system = [
      setuptools
    ];
    dependencies = with pkgs.python3Packages; [
      cachetools
      certifi
      charset-normalizer
      google-auth
      google-auth-oauthlib
      gspread
      idna
      oauthlib
      pyasn1
      pyasn1-modules
      requests
      requests-oauthlib
      rsa
      strenum
      urllib3
    ];
  });
in
pkgs.dockerTools.buildLayeredImage {
  name = "discord-bot";
  tag = "latest";
  created = "now";
}
