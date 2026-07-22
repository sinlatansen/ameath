# Builds the Linux binary natively inside a real Linux container --
# not a cross-compile from macOS. Tauri's Linux backend links directly
# against webkit2gtk/GTK, which aren't practical to cross-build from
# macOS via Nix (would need the whole GTK/WebKit stack cross-built for
# x86_64-linux); a container with the real libraries sidesteps that
# entirely. See justfile's `build-linux` and README's cross-platform
# build section.
FROM rust:bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libwebkit2gtk-4.1-dev \
    libgtk-3-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev \
    libxdo-dev \
    libssl-dev \
    libasound2-dev \
    patchelf \
    pkg-config \
    file \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Debian bookworm's own `nodejs` package (18.x) is too old for Vite 8
# (needs node:util's styleText, added in Node 20+) -- NodeSource's
# build is the standard way to get a current LTS on Debian.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @tauri-apps/cli

WORKDIR /workspace
