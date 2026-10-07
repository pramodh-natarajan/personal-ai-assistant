FROM openjdk:21-slim-bookworm

RUN apt-get update && apt-get install -y \
    curl \
    git \
    tar \
    python3 \
    python3-pip \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

ENV SIGNAL_CLI_VERSION=0.14.8
RUN curl -L -o /tmp/signal-cli.tar.gz https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz \
    && tar -xzf /tmp/signal-cli.tar.gz -C /opt/ \
    && ln -s /opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli /usr/local/bin/signal-cli \
    && rm /tmp/signal-cli.tar.gz

WORKDIR /app
COPY . /app

RUN pip3 install --no-cache-dir -r requirements.txt
RUN chmod +x /app/scripts/entrypoint.py

ENTRYPOINT ["python3", "/app/scripts/entrypoint.py"]