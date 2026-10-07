#!/usr/bin/env bash
set -e

HERMES_DIR="/root/.hermes"
SIGNAL_DIR="/root/.local/share/signal-cli"
BACKUP_DIR="/tmp/bodhi-state"
REPO_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${BACKUP_REPO:-bodhi-state}.git"

# 1. Kill OpenRouter auto-discovery and redirect default OpenAI client to Groq
unset OPENROUTER_API_KEY
export OPENAI_API_KEY="${GROQ_API_KEY}"
export OPENAI_BASE_URL="https://api.groq.com/openai/v1"
export OPENAI_MODEL="llama-3.3-70b-versatile"
export HERMES_MODEL="llama-3.3-70b-versatile"
export MODEL="llama-3.3-70b-versatile"

mkdir -p "${HERMES_DIR}" "${SIGNAL_DIR}"

git config --global user.name "Bodhi Assistant"
git config --global user.email "bodhi@render.local"

# 2. Restore state from private GitHub repo
echo "[*] Restoring Bodhi memory state and Signal session from GitHub..."
rm -rf "${BACKUP_DIR}"
if git clone --depth 1 "${REPO_URL}" "${BACKUP_DIR}" > /dev/null 2>&1; then
    if [ -f "${BACKUP_DIR}/latest.tar.gz" ]; then
        tar -xzf "${BACKUP_DIR}/latest.tar.gz" -C /root/
        echo "[+] Memory and Signal session successfully restored."
    fi
else
    echo "[!] No existing state repository found. Initializing clean slate for Bodhi."
    mkdir -p "${BACKUP_DIR}"
    cd "${BACKUP_DIR}"
    git init -b main
    git remote add origin "${REPO_URL}" || true
fi

# 3. Strip all openrouter references from python site-packages and configs
echo "[*] Unsetting OpenRouter across python environment..."
python3 -c "
import site, os

for sp in site.getsitepackages():
    for root, _, files in os.walk(sp):
        for f in files:
            if f.endswith(('.py', '.yaml', '.json')):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                        content = file.read()
                    if 'openrouter' in content or 'z-ai/glm-5.2' in content:
                        new_content = content.replace('z-ai/glm-5.2', 'llama-3.3-70b-versatile').replace('openrouter', 'openai')
                        with open(path, 'w', encoding='utf-8') as file:
                            file.write(new_content)
                except Exception:
                    pass
"

# 4. Purge legacy thread sessions and profile caches
rm -rf /root/.hermes/sessions /root/.hermes/threads /root/.hermes/profiles /root/.hermes/cache /root/.hermes/*.db* /root/.hermes/*.sqlite* 2>/dev/null || true

# 5. Re-initialize clean config pointing strictly to Groq OpenAI endpoint
mkdir -p /root/.hermes/profiles
cp /app/config/config.yaml /root/.hermes/config.yaml

cat <<EOF > /root/.hermes/profiles/personal.yaml
name: personal
model: llama-3.3-70b-versatile
provider: openai
base_url: https://api.groq.com/openai/v1
api_key: ${GROQ_API_KEY}
max_tokens: 2048
EOF

# Function to save state and push to GitHub
sync_to_github() {
    echo "[*] Syncing Bodhi state snapshot to GitHub..."
    tar -czf "${BACKUP_DIR}/latest.tar.gz" -C /root/ .hermes .local/share/signal-cli 2>/dev/null || true
    cd "${BACKUP_DIR}"
    git add latest.tar.gz
    git commit -m "Auto-sync Bodhi state [$(date -u +'%Y-%m-%dT%H:%M:%SZ')]" || true
    git push -u origin main --force > /dev/null 2>&1 || true
    echo "[+] State push complete."
}

# 6. Background periodic sync every 10 minutes
(
    while true; do
        sleep 600
        sync_to_github
    done
) &

# 7. Trap container shutdown signals
trap 'echo "[*] Container stopping! Saving final Bodhi state..."; sync_to_github; exit 0' SIGTERM SIGINT

# 8. Start signal-cli HTTP daemon
if [ -n "$SIGNAL_ACCOUNT" ]; then
    echo "[+] Starting signal-cli daemon for account ${SIGNAL_ACCOUNT}..."
    signal-cli --account "${SIGNAL_ACCOUNT}" daemon --http 127.0.0.1:8080 &
    sleep 3
fi

# 9. Start background HTTP health check server for Render
python3 -c "
import http.server, socketserver, os
port = int(os.environ.get('PORT', 10000))
class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bodhi Gateway Healthy')
    def log_message(self, format, *args):
        return
socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.TCPServer(('0.0.0.0', port), HealthHandler)
httpd.serve_forever()
" &

# 10. Launch Bodhi Agent Gateway
echo "[+] Launching Bodhi Personal AI Assistant..."
exec hermes gateway