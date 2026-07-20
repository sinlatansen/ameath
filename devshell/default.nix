{
  rustToolchain,
  cargoArgs,
  unitTestArgs,
  pkgs,
  lib,
  stdenv,
  darwin,
  ...
}:

let
  cargo-ext = pkgs.callPackage ./cargo-ext.nix { inherit cargoArgs unitTestArgs; };
in
pkgs.mkShell {
  name = "dev-shell";

  nativeBuildInputs = with pkgs; [
    cargo-ext.cargo-build-all
    cargo-ext.cargo-clippy-all
    cargo-ext.cargo-doc-all
    cargo-ext.cargo-nextest-all
    cargo-ext.cargo-test-all
    cargo-nextest
    cargo-tauri
    rustToolchain

    tokei

    jq

    hclfmt
    nixfmt-rfc-style
    nodePackages.prettier
    sleek
    shfmt
    taplo
    treefmt
    # clang-tools contains clang-format
    clang-tools

    shellcheck

    git
    pkg-config
    libgit2
  ];

  shellHook = ''
    export NIX_PATH="nixpkgs=${pkgs.path}"
    export RUSTFMT="${rustToolchain}/bin/rustfmt"
  '';
}
