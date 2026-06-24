# joyjoy "fat" sandbox image v3: multi-language code-interpreter + headless
# browser + common CLI / data / media / document tooling in one.
#
# OpenSandbox runs ARBITRARY shell via execd (`POST /command`), so the IMAGE —
# not the platform — decides which languages/tools the agent's `execute` tool can
# use. v1 was Python-only (Playwright base + a few pip libs); v2 added Node.js,
# Java, Go, C/C++ build tools, media/doc CLIs; v3 adds Rust (rustc/cargo).
#
# Rebuild:  docker build -t joyjoy/sandbox-fat:3 sandbox-image/
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DEBIAN_FRONTEND=noninteractive

# OS packages: build tools, Java (JDK 17), data/text CLIs, media + doc tooling,
# and Node.js 20 LTS from NodeSource (jammy's apt node is too old for modern npm).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
        build-essential \
        openjdk-17-jdk-headless \
        jq ripgrep git unzip \
        ffmpeg imagemagick \
        libreoffice poppler-utils \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Go toolchain (official build; jammy's apt Go is too old for modern modules).
RUN curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# Rust toolchain (rustup → SYSTEM location so rustc/cargo work for any sandbox
# user, root or not; a+w lets cargo write its registry cache at runtime).
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH="/usr/local/cargo/bin:${PATH}"
RUN curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs \
        | sh -s -- -y --no-modify-path --profile minimal --default-toolchain stable \
    && chmod -R a+w "$RUSTUP_HOME" "$CARGO_HOME"

# Python libs: playwright client + data / document analysis.
RUN pip install --no-cache-dir \
    "playwright==1.49.0" \
    pandas numpy matplotlib openpyxl python-pptx pillow requests

# Build-time sanity: every runtime + key tool resolves.
RUN python -c "import playwright, pandas, numpy, matplotlib; print('py deps OK')" \
    && node --version && npm --version \
    && java -version \
    && go version \
    && rustc --version && cargo --version \
    && gcc --version | head -1 \
    && jq --version && rg --version | head -1 \
    && ffmpeg -version | head -1 \
    && libreoffice --version \
    && echo "fat image v3 OK"
