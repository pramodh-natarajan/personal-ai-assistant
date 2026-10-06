#!/usr/bin/env bash
set -e

HERMES_DIR="/root/.hermes"
SIGNAL_DIR="/root/.local/share/signal-cli"
BACKUP_DIR="/tmp/bodhi-state"
REPO_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${BACKUP_REPO:-bodhi-state}.git"

export HERMES_MODEL="meta-llama/llama-3.3-70b-instruct:free"
export MODEL="meta-llama/llama-3.3-70b-instruct:free"

mkdir -p "${HERMES_DIR}" "${SIGNAL_DIR}"

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

# 2. Overwrite Hermes config with repository config.yaml
echo "[*] Applying repository config.yaml to Hermes runtime..."
mkdir -p /root/.hermes
cp /app/config/config.yaml /root/.hermes/config.yaml

# 3. Python state sanitizer (purges paid model references in text & SQLite databases)
python3 -c "
import os, sqlite3

hermes_dir = '/root/.hermes'
target = 'meta-llama/llama-3.3-70b-instruct:free'

for root, _, files in os.walk(hermes_dir):
    for f in files:
        path = os.path.join(root, f)
        # Clean text & JSON/YAML files
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            if 'glm-5.2' in content or 'z-ai' in content:
                new_content = content.replace('z-ai/glm-5.2', target).replace('glm-5.2', target)
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f'[+] Purged model override in text file: {path}')
        except Exception:
            pass
            
        # Clean SQLite database files
        if f.endswith(('.db', '.sqlite', '.sqlite3')) or 'db' in f:
            try:
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table';\")
                tables = cursor.fetchall()
                for table in tables:
                    tname = table[0]
                    cursor.execute(f'PRAGMA table_info({tname});')
                    cols = [c[1] for c in cursor.fetchall()]
                    for col in cols:
                        try:
                            cursor.execute(f\"UPDATE {tname} SET {col} = REPLACE({col}, 'z-ai/glm-5.2', '{target}') WHERE {col} LIKE '%glm-5.2%';\")
                        except Exception:
                            pass
                conn.commit()
                conn.close()
                print(f'[+] Purged model override in SQLite DB: {path}')
            except Exception:
                pass
"

# Force Hermes CLI model setting if available
hermes model set meta-llama/llama-3.3-70b-instruct:free 2>/dev/null || hermes config set model meta-llama/llama-3.3-70b-instruct:free 2>/dev/null || true

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

# 4. Background periodic sync every 10 minutes
(
    while true; do
        sleep 600
        sync_to_github
    done
) &

# 5. Trap container shutdown signals
trap 'echo "[*] Container stopping! Saving final Bodhi state..."; sync_to_github; exit 0' SIGTERM SIGINT

# 6. Start signal-cli HTTP daemon
if [ -n "$SIGNAL_ACCOUNT" ]; then
    echo "[+] Starting signal-cli daemon for account ${SIGNAL_ACCOUNT}..."
    signal-cli --account "${SIGNAL_ACCOUNT}" daemon --http 127.0.0.1:8080 &
    sleep 3
fi

# 7. Start background HTTP health check server for Render
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

# 8. Launch Bodhi Agent Gateway
echo "[+] Launching Bodhi Personal AI Assistant..."
exec hermes gateway