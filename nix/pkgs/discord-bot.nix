{
  lib,
  pkgs,
  fetchPypi,
  fetchFromGitHub,
  ...
}:
let
  python3Packages = pkgs.python3Packages;
  buildPythonPackage = python3Packages.buildPythonPackage;
  better-ipc = buildPythonPackage (finalAttrs: {
    version = "2.0.3";
    pname = "better-ipc";
    src = fetchFromGitHub {
      owner = "MiroslavRosenov";
      repo = "better-ipc";
      rev = "main";
      hash = "sha256-M1n+1FCUlg6QoYxpFkPmPWGkbu2iUTvU5JOya4Bc/E0=";
    };
    doCheck = false;
    pyproject = true;
    build-system = [
      python3Packages.setuptools
    ];
    dependencies = with python3Packages; [
      websockets
    ];
  });

  # gspread-asyncio requires gspread==6.0.*
  gspread_6_0_2 = python3Packages.gspread.overrideAttrs (oldAttrs: {
    version = "6.0.2";
    src = fetchFromGitHub {
      owner = "burnash";
      repo = "gspread";
      tag = "v6.0.2";
      sha256 = "sha256-NY6Q45/XuidDUeBG0QfVaStwp2+BqMSgefDifHu2erU=";
    };
  });

  gspread-asyncio = buildPythonPackage (finalAttrs: {
    version = "2.0.0";
    pname = "gspread-asyncio";
    src = fetchFromGitHub {
      owner = "dgilman";
      repo = "gspread_asyncio";
      rev = "b08fe1901fbd2c7947ef02a92c44fb477b3b76d1";
      hash = "sha256-pOkJu56zqbAQqXFNWP4E5FEdjnrp/wLiLr1pzTVNqp4=";
    };
    doCheck = false;
    pyproject = true;
    build-system = [
      python3Packages.setuptools
    ];
    dependencies = with python3Packages; [
      cachetools
      certifi
      charset-normalizer
      google-auth
      google-auth-oauthlib
      gspread_6_0_2
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
buildPythonPackage rec {
  version = "1.0.0";
  pname = "discord-bot";
  src = ../../.;

  buildInputs = with python3Packages; [
    discordpy
    aiohttp
    icalendar
    recurring-ical-events
    greenlet
    aiosmtplib
    better-ipc
    sqlalchemy
    aiosqlite
    gspread-asyncio
    rich
    python-dotenv
    pytest
    pytest-asyncio
    quart
    cairosvg
  ];

  doCheck = false;
  pyproject = true;
  build-system = [
    python3Packages.setuptools
  ];
}
