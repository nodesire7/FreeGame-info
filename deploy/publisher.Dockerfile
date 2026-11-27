FROM nodesire77/game_info:v1.67
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client rsync util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/publisher-loop.sh /usr/local/bin/freegame-publisher
ENTRYPOINT ["/bin/bash", "/usr/local/bin/freegame-publisher"]
