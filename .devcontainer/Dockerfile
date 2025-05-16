FROM python:3.12-slim

ARG USER_ID=1000
ARG GROUP_ID=1000


# Install common development tools.
RUN apt-get update && apt-get install -y -q --allow-unauthenticated \
    build-essential \
    procps \
    file \
    git \
    curl \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libxext6 \
    libx11-6 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    x11-apps \
    xauth \
    zsh \
    ripgrep \
    fzf \
    ugrep \
    tmux \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LO https://github.com/neovim/neovim/releases/latest/download/nvim-linux-x86_64.tar.gz && \
                rm -rf /opt/nvim && \
                tar -C /opt -xzf nvim-linux-x86_64.tar.gz
RUN rm nvim-linux-x86_64.tar.gz
RUN ln -s /opt/nvim-linux-x86_64/bin/nvim /usr/local/bin/nvim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ADD https://astral.sh/ruff/install.sh /ruff-installer.sh
RUN sh /ruff-installer.sh && rm /ruff-installer.sh

ADD https://starship.rs/install.sh /starship-installer.sh
RUN sh /starship-installer.sh --yes && rm /starship-installer.sh

WORKDIR /workspace

RUN useradd -m devuser
RUN chown -R devuser:devuser /workspace
RUN chown -R devuser:devuser /opt
RUN chmod -R 755 /workspace
USER devuser 

RUN mkdir -p ~/.config/fish


RUN echo 'export PATH="$PATH:/opt/nvim-linux-x86_64/bin"' >> ~/.bashrc
RUN echo 'eval "$(uv generate-shell-completion bash)"' >> ~/.bashrc
RUN echo 'eval "$(uv generate-shell-completion zsh)"' >> ~/.zshrc
RUN echo 'eval "$(starship init bash)"' >> ~/.bashrc
RUN echo 'eval "$(starship init zsh)"' >> ~/.zshrc

RUN echo 'starship init fish | source' >> ~/.config/fish/config.fish
