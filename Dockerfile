FROM python:3.11-slim-bookworm

# Install core build tools and system utilities
RUN apt-get update && apt-get install -y \
    curl \
    git \
    tar \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Oracle OpenJDK 25 (Java class version 69.0 required by signal-cli v0.14.8)
RUN curl -fsSL -o /tmp/openjdk25.tar.gz https://download.oracle.com/java/25/archive/jdk-25.0.2_linux-x64_bin.tar.gz \
    && mkdir -p /usr/lib/jvm/openjdk-25 \
    && tar -xzf /tmp/openjdk25.tar.gz -C /usr/lib/jvm/openjdk-25 --strip-components=1 \
    && rm /tmp/openjdk25.tar.gz

ENV JAVA_HOME=/usr/lib/jvm/openjdk-25
ENV PATH="$JAVA_HOME/bin:$PATH"

# Install signal-cli v0.14.8
ENV SIGNAL_CLI_VERSION=0.14.8
RUN curl -fsSL -o /tmp/signal-cli.tar.gz https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz \
    && tar -xzf /tmp/signal-cli.tar.gz -C /opt/ \
    && ln -s /opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli /usr/local/bin/signal-cli \
    && rm /tmp/signal-cli.tar.gz

EXPOSE 10000

WORKDIR /app
COPY . /app

RUN pip3 install --no-cache-dir -r requirements.txt
RUN chmod +x /app/scripts/entrypoint.py

ENTRYPOINT ["python3", "/app/scripts/entrypoint.py"]