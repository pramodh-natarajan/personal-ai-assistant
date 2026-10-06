FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies & headless Java JRE for signal-cli
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential ca-certificates default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Download and install the latest signal-cli release binary
RUN VERSION=$(curl -Ls -o /dev/null -w %{url_effective} https://github.com/AsamK/signal-cli/releases/latest | sed -e 's/^.*\/v//') \
    && curl -L -O "https://github.com/AsamK/signal-cli/releases/download/v${VERSION}/signal-cli-${VERSION}-Linux.tar.gz" \
    && tar xf "signal-cli-${VERSION}-Linux.tar.gz" -C /opt \
    && ln -sf "/opt/signal-cli-${VERSION}/bin/signal-cli" /usr/local/bin/signal-cli \
    && rm "signal-cli-${VERSION}-Linux.tar.gz"

# Install Hermes Agent Framework
RUN pip install --no-cache-dir hermes-agent

WORKDIR /app
COPY . .

RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 10000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]