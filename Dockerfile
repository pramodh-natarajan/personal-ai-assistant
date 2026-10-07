FROM python:3.11-slim-bookworm

# Install OpenJDK 21 for signal-cli alongside base build tools
RUN apt-get update && apt-get install -y \
    openjdk-21-jre-headless \
    curl \
    git \
    tar \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install signal-cli v0.14.8
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