FROM python:3.11-slim

# Install system dependencies & git/node
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Install Hermes Agent Framework
RUN pip install --no-cache-dir hermes-agent

WORKDIR /app
COPY . .

RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 10000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]