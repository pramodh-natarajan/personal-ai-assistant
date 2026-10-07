#!/usr/bin/env python3
import os
import sys
import time
import json
import sqlite3
import tarfile
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

HERMES_DIR = "/root/.hermes"
SIGNAL_DIR = "/root/.local/share/signal-cli"
BACKUP_DIR = "/tmp/bodhi-state"

TARGET_MODEL = "llama-3.3-70b-versatile"
TARGET_BASE_URL = "https://api.groq.com/openai/v1"

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER = os.environ.get("GITHUB_USER", "")
BACKUP_REPO = os.environ.get("BACKUP_REPO", "bodhi-state")
SIGNAL_ACCOUNT = os.environ.get("SIGNAL_ACCOUNT", "")

# Remove OpenRouter key to prevent legacy auto-discovery
os.environ.pop("OPENROUTER_API_KEY", None)
os.environ["HERMES_PROVIDER"] = "custom"
os.environ["HERMES_MODEL"] = TARGET_MODEL
os.environ["OPENAI_BASE_URL"] = TARGET_BASE_URL
os.environ["OPENAI_API_KEY"] = GROQ_KEY

def run_cmd(cmd, check=False):
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)

def restore_state():
    print("[*] Restoring Bodhi memory state and Signal session from GitHub...")
    os.makedirs(HERMES_DIR, exist_ok=True)
    os.makedirs(SIGNAL_DIR, exist_ok=True)
    
    if os.path.exists(BACKUP_DIR):
        run_cmd(f"rm -rf {BACKUP_DIR}")
        
    repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{BACKUP_REPO}.git"
    res = run_cmd(f"git clone --depth 1 {repo_url} {BACKUP_DIR}")
    
    archive = os.path.join(BACKUP_DIR, "latest.tar.gz")
    if res.returncode == 0 and os.path.exists(archive):
        try:
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(path="/root")
            print("[+] Memory and Signal session successfully restored.")
        except Exception as e:
            print(f"[!] Tarball restore note: {e}")
    else:
        print("[!] No backup repository found. Initializing clean slate.")

def configure_hermes():
    print("[*] Writing Hermes configuration and profile files...")
    os.makedirs(os.path.join(HERMES_DIR, "profiles"), exist_ok=True)
    
    if os.path.exists("/app/config/config.yaml"):
        run_cmd(f"cp /app/config/config.yaml {HERMES_DIR}/config.yaml")
        
    env_content = (
        f"HERMES_PROVIDER=custom\n"
        f"HERMES_MODEL={TARGET_MODEL}\n"
        f"OPENAI_BASE_URL={TARGET_BASE_URL}\n"
        f"OPENAI_API_KEY={GROQ_KEY}\n"
    )
    with open(os.path.join(HERMES_DIR, ".env"), "w", encoding="utf-8") as f:
        f.write(env_content)
        
    profile_content = f"""name: personal
model: {TARGET_MODEL}
provider: custom
base_url: {TARGET_BASE_URL}
api_key: {GROQ_KEY}
max_tokens: 2048
"""
    with open(os.path.join(HERMES_DIR, "profiles", "personal.yaml"), "w", encoding="utf-8") as f:
        f.write(profile_content)

def sanitize_state_files():
    print("[*] Sanitizing session threads and SQLite state...")
    for root, _, files in os.walk(HERMES_DIR):
        for f in files:
            if f.endswith(".json"):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8") as jf:
                        data = json.load(jf)
                    if isinstance(data, dict):
                        updated = False
                        if data.get("model") != TARGET_MODEL:
                            data["model"] = TARGET_MODEL
                            updated = True
                        if data.get("provider") != "custom":
                            data["provider"] = "custom"
                            updated = True
                        if updated:
                            with open(path, "w", encoding="utf-8") as jf:
                                json.dump(data, jf, indent=2)
                except Exception:
                    pass

    for root, _, files in os.walk(HERMES_DIR):
        for f in files:
            if f.endswith((".db", ".sqlite", ".sqlite3")):
                path = os.path.join(root, f)
                try:
                    conn = sqlite3.connect(path)
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = [t[0] for t in cur.fetchall()]
                    for table in tables:
                        cur.execute(f"PRAGMA table_info({table});")
                        cols = [c[1] for c in cur.fetchall()]
                        if "model" in cols:
                            cur.execute(f"UPDATE {table} SET model = ?;", (TARGET_MODEL,))
                        if "provider" in cols:
                            cur.execute(f"UPDATE {table} SET provider = ?;", ("custom",))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

def sync_to_github():
    if not GITHUB_TOKEN or not GITHUB_USER:
        return
    print("[*] Syncing Bodhi state snapshot to GitHub...")
    repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{BACKUP_REPO}.git"
    archive = os.path.join(BACKUP_DIR, "latest.tar.gz")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    try:
        with tarfile.open(archive, "w:gz") as tar:
            if os.path.exists(HERMES_DIR):
                tar.add(HERMES_DIR, arcname=".hermes")
            if os.path.exists(SIGNAL_DIR):
                tar.add(SIGNAL_DIR, arcname=".local/share/signal-cli")
                
        run_cmd(f"cd {BACKUP_DIR} && git init -b main && git remote add origin {repo_url} || true")
        run_cmd(f"cd {BACKUP_DIR} && git add latest.tar.gz")
        run_cmd(f'cd {BACKUP_DIR} && git commit -m "Auto-sync Bodhi state [{time.strftime("%Y-%m-%dT%H:%M:%SZ")}]"')
        run_cmd(f"cd {BACKUP_DIR} && git push -u origin main --force")
        print("[+] State push complete.")
    except Exception as e:
        print(f"[!] State sync error: {e}")

def periodic_sync_loop():
    while True:
        time.sleep(600)
        sync_to_github()

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    class HealthHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bodhi Gateway Healthy")
        def log_message(self, format, *args):
            return
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def main():
    run_cmd('git config --global user.name "Bodhi Assistant"')
    run_cmd('git config --global user.email "bodhi@render.local"')

    restore_state()
    configure_hermes()
    sanitize_state_files()

    threading.Thread(target=periodic_sync_loop, daemon=True).start()
    threading.Thread(target=start_health_server, daemon=True).start()

    if SIGNAL_ACCOUNT:
        print(f"[+] Starting signal-cli daemon for account {SIGNAL_ACCOUNT}...")
        subprocess.Popen(["signal-cli", "--account", SIGNAL_ACCOUNT, "daemon", "--http", "127.0.0.1:8080"])
        time.sleep(4)

    print("[+] Launching Hermes Agent Gateway...")
    os.execvp("hermes", ["hermes", "gateway"])

if __name__ == "__main__":
    main()