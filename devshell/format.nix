{ pkgs }:

pkgs.runCommandNoCC "check-format"
  {
    buildInputs = with pkgs; [
      fd

      shellcheck

      nixfmt-rfc-style
      nodePackages.prettier
      sleek
      shfmt
      taplo
      treefmt
      # clang-tools contains clang-format
      clang-tools
    ];
  }
  ''
    treefmt \
      --allow-missing-formatter \
      --fail-on-change \
      --no-cache \
      --formatters prettier \
      --formatters clang-format \
      --formatters nix \
      --formatters shell \
      --formatters hcl \
      --formatters toml \
      --formatters sql-check \
      -C ${./..}

    # it worked!
    touch $out
  ''
