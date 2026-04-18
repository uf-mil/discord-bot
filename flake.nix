{
  description = "A Discord bot framework for the uf-mil discord bot";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";
  };

  outputs = {
    self,
    nixpkgs,
    systems,
  }:
  let
    lib = nixpkgs.lib;
    forEachSystem =
    fn:
    nixpkgs.lib.genAttrs (import systems) (
      system:
      fn (
        import nixpkgs {
          inherit system;
          config = {
            allowUnfree = true;
          };
        }
      )
    );
  in
  {
    nixosModules = ./modules;

    packages = forEachSystem (
      pkgs:
      {
        discord-bot = pkgs.callPackage ./nix/pkgs/discord-bot.nix { inherit pkgs ; };
      }
    );
  };
}
