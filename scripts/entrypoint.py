#!/usr/bin/env python3
import os
import sys
import time
import shutil
import socket
import glob
import tarfile
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

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

os.environ.pop("OPENROUTER_API_KEY", None)
os.environ["HERMES_PROVIDER"] = "custom"
os.environ["HERMES_MODEL"] = TARGET_MODEL
os.environ["OPENAI_BASE_URL"] = TARGET_BASE_URL
os.environ["OPENAI_API_KEY"] = GROQ_KEY

def bind_health_server_instantly():
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
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[+] Render health check HTTP server listening on 0.0.0.0:{port}", flush=True)

def run_cmd(cmd, check=False):
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)

def restore_state():
    print("[*] Restoring Bodhi memory state and Signal session from GitHub...", flush=True)
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
            print("[+] Memory and Signal session successfully restored.", flush=True)
        except Exception as e:
            print(f"[!] Tarball restore note: {e}", flush=True)
    else:
        print("[!] No backup repository found. Initializing clean slate.", flush=True)

def reset_signal_ratchet_session():
    """Triggers an explicit session reset to re-key Double Ratchet encryption with authorized users."""
    allowed_users = os.environ.get("SIGNAL_ALLOWED_USERS", "").split(",")
    for user in allowed_users:
        user = user.strip()
        if user:
            print(f"[*] Sending ratchet reset signal to {user} to establish fresh session...", flush=True)
            run_cmd(f'signal-cli -u "{SIGNAL_ACCOUNT}" send -m "[Bodhi] Encryption session re-established." --end-session "{user}"')

def configure_hermes():
    print("[*] Writing Hermes configuration and profile files...", flush=True)
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

def purge_stale_sessions():
    print("[*] Purging stale thread sessions and SQLite caches...", flush=True)
    stale_paths = [
        os.path.join(HERMES_DIR, "sessions"),
        os.path.join(HERMES_DIR, "threads"),
        os.path.join(HERMES_DIR, "cache"),
    ]
    for p in stale_paths:
        if os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True)
    
    for db_file in glob.glob(os.path.join(HERMES_DIR, "*.db*")):
        try:
            os.remove(db_file)
        except Exception:
            pass

def wait_for_signal_daemon():
    if not SIGNAL_ACCOUNT:
        return

    run_cmd("pkill -9 -f signal-cli || true")
    time.sleep(1)

    print(f"[+] Starting signal-cli daemon for account {SIGNAL_ACCOUNT}...", flush=True)
    subprocess.Popen(["signal-cli", "--account", SIGNAL_ACCOUNT, "daemon", "--http", "127.0.0.1:8080"])
    
    print("[*] Polling 127.0.0.1:8080 TCP socket until ready (up to 90s)...", flush=True)
    for elapsed in range(1, 91):
        try:
            with socket.create_connection(("127.0.0.1", 8080), timeout=1):
                print(f"[+] signal-cli daemon TCP socket connected on port 8080 after {elapsed}s!", flush=True)
                return
        except Exception:
            if elapsed % 5 == 0:
                print(f"[*] Waiting for signal-cli port 8080 ({elapsed}s elapsed)...", flush=True)
            time.sleep(1)
    print("[!] Warning: signal-cli daemon socket check timed out after 90 seconds.", flush=True)

def sync_to_github():
    if not GITHUB_TOKEN or not GITHUB_USER:
        return
    print("[*] Syncing Bodhi state snapshot to GitHub...", flush=True)
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
        print("[+] State push complete.", flush=True)
    except Exception as e:
        print(f"[!] State sync error: {e}", flush=True)

def periodic_sync_loop():
    while True:
        time.sleep(180)
        sync_to_github()

def main():
    bind_health_server_instantly()

    run_cmd('git config --global user.name "Bodhi Assistant"')
    run_cmd('git config --global user.email "bodhi@render.local"')

    restore_state()
    configure_hermes()
    purge_stale_sessions()

    # Issue session reset command prior to daemon boot
    reset_signal_ratchet_session()

    threading.Thread(target=periodic_sync_loop, daemon=True).start()

    wait_for_signal_daemon()

    print("[+] Launching Hermes Agent Gateway...", flush=True)
    os.execvp("hermes", ["hermes", "gateway"])

if __name__ == "__main__":
    main()