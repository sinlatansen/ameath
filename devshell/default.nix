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

  nativeBuildInputs =
    with pkgs;
    [
      cargo-ext.cargo-build-all
      cargo-ext.cargo-clippy-all
      cargo-ext.cargo-doc-all
      cargo-ext.cargo-nextest-all
      cargo-ext.cargo-test-all
      cargo-nextest
      cargo-tauri
      cargo-xwin
      rustToolchain

      tokei

      jq

      hclfmt
      nixfmt-rfc-style
      prettier
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
    ]
    ++ lib.optionals stdenv.isLinux [
      # Tauri v2 Linux build/runtime dependencies
      webkitgtk_4_1
      gtk3
      libayatana-appindicator
      librsvg
    ]
    ++ lib.optionals stdenv.isDarwin [
      libiconv
      apple-sdk
    ]
    ++ lib.optionals (!stdenv.isDarwin) [
      cargo-llvm-cov
    ];

  shellHook = ''
    export NIX_PATH="nixpkgs=${pkgs.path}"
    export RUSTFMT="${rustToolchain}/bin/rustfmt"
  '';
}
