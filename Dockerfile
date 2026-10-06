FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ARG SIGNAL_CLI_VERSION=0.14.8

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install standalone GraalVM native release of signal-cli v0.14.8 (no Java required)
RUN curl -fL -o /tmp/signal-cli-native.tar.gz "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz" \
    && tar xf /tmp/signal-cli-native.tar.gz -C /opt \
    && ln -sf "/opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli" /usr/local/bin/signal-cli \
    && rm /tmp/signal-cli-native.tar.gz

# Install Hermes Agent Framework
RUN pip install --no-cache-dir hermes-agent

WORKDIR /app
COPY . .

RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 10000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]