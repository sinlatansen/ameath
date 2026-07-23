{
  description = "Fleet Snowfluff";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    fenix = {
      url = "github:nix-community/fenix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    crane = {
      url = "github:ipetkov/crane";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      fenix,
      crane,
    }:
    let
      cargoToml = builtins.fromTOML (builtins.readFile ./Cargo.toml);
      name = "fleet-snowfluff";
    in
    (flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [
            self.overlays.default
            fenix.overlays.default
          ];
        };

        rustToolchain =
          with fenix.packages.${system};
          combine [
            stable.rustc
            stable.cargo
            stable.clippy
            stable.rust-src
            stable.rust-std

            default.rustfmt

            # Windows cross-compile target (justfile's `build-windows`):
            # only the std lib, not a full toolchain -- cargo-xwin
            # supplies the MSVC headers/libs/linker for the actual
            # cross-link, this just lets rustc compile for the triple
            # at all.
            targets.x86_64-pc-windows-msvc.stable.rust-std

            # Linux target's std lib -- lets `cargo check`/`clippy`
            # type-check Linux-specific code (platform/linux.rs) from
            # this devshell without needing the real Linux container.
            # Doesn't make a full `fleet-snowfluff` build possible here:
            # Tauri's Linux backend links against webkit2gtk/GTK, real
            # system libraries no rust-std target provides, so an
            # actual cross-compiled binary still needs the container
            # (justfile's `build-linux`), not this devshell.
            targets.x86_64-unknown-linux-gnu.stable.rust-std
          ];

        rustPlatform = pkgs.makeRustPlatform {
          cargo = rustToolchain;
          rustc = rustToolchain;
        };

        craneLib = (crane.mkLib pkgs).overrideToolchain rustToolchain;

        cargoArgs = [
          "--workspace"
          "--bins"
          "--examples"
          "--tests"
          "--benches"
          "--all-targets"
        ];

        unitTestArgs = [
          "--workspace"
        ];

        src = craneLib.cleanCargoSource (craneLib.path ./.);
        commonArgs = { inherit src; };
        cargoArtifacts = craneLib.buildDepsOnly commonArgs;
      in
      {
        formatter = pkgs.treefmt;

        devShells.default = pkgs.callPackage ./devshell {
          inherit rustToolchain cargoArgs unitTestArgs;
        };

        checks = {
          format = pkgs.callPackage ./devshell/format.nix { };

          rust-build = craneLib.cargoBuild (
            commonArgs
            // {
              inherit cargoArtifacts;
            }
          );
          rust-format = craneLib.cargoFmt { inherit src; };
          rust-clippy = craneLib.cargoClippy (
            commonArgs
            // {
              inherit cargoArtifacts;
              cargoClippyExtraArgs = pkgs.lib.strings.concatMapStrings (x: x + " ") cargoArgs;
            }
          );
          rust-nextest = craneLib.cargoNextest (
            commonArgs
            // {
              inherit cargoArtifacts;
              partitions = 1;
              partitionType = "count";
            }
          );
        };
      }
    ))
    // {
      overlays.default = final: prev: { };
    };
}
