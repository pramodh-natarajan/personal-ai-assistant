#!/usr/bin/env bash
set -e

HERMES_DIR="/root/.hermes"
SIGNAL_DIR="/root/.local/share/signal-cli"
BACKUP_DIR="/tmp/bodhi-state"
REPO_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${BACKUP_REPO:-bodhi-state}.git"

# Force model override at process level
export HERMES_MODEL="meta-llama/llama-3.3-70b-instruct:free"

mkdir -p "${HERMES_DIR}" "${SIGNAL_DIR}"

# Configure git credentials
git config --global user.name "Bodhi Assistant"
git config --global user.email "bodhi@render.local"

# 1. Restore state from private GitHub repo
echo "[*] Restoring Bodhi memory state and Signal session from GitHub..."
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

# 2. Enforce free model across runtime config and restored profiles
echo "[*] Enforcing free model on Hermes runtime..."
mkdir -p /root/.hermes
cp /app/config/config.yaml /root/.hermes/config.yaml

# Replace lingering cached references to z-ai/glm-5.2 or paid models in restored files
find /root/.hermes -type f \( -name "*.yaml" -o -name "*.json" \) -exec sed -i 's|z-ai/glm-5.2|meta-llama/llama-3.3-70b-instruct:free|g' {} + 2>/dev/null || true

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

# 3. Background periodic sync every 10 minutes
(
    while true; do
        sleep 600
        sync_to_github
    done
) &

# 4. Trap container shutdown signals
trap 'echo "[*] Container stopping! Saving final Bodhi state..."; sync_to_github; exit 0' SIGTERM SIGINT

# 5. Start signal-cli HTTP daemon
if [ -n "$SIGNAL_ACCOUNT" ]; then
    echo "[+] Starting signal-cli daemon for account ${SIGNAL_ACCOUNT}..."
    signal-cli --account "${SIGNAL_ACCOUNT}" daemon --http 127.0.0.1:8080 &
    sleep 3
fi

# 6. Start background HTTP health check server for Render
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

# 7. Launch Bodhi Agent Gateway
echo "[+] Launching Bodhi Personal AI Assistant..."
exec hermes gateway