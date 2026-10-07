FROM python:3.11-slim-bookworm

# Install core build and system utilities
RUN apt-get update && apt-get install -y \
    curl \
    git \
    tar \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install OpenJDK 21 JRE directly from Adoptium binaries
RUN curl -L -o /tmp/openjdk.tar.gz https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.2%2B13/OpenJDK21U-jre_x64_linux_hotspot_21.0.2_13.tar.gz \
    && mkdir -p /usr/lib/jvm/openjdk-21 \
    && tar -xzf /tmp/openjdk.tar.gz -C /usr/lib/jvm/openjdk-21 --strip-components=1 \
    && rm /tmp/openjdk.tar.gz

ENV JAVA_HOME=/usr/lib/jvm/openjdk-21
ENV PATH="$JAVA_HOME/bin:$PATH"

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