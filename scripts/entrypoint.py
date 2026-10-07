#!/usr/bin/env python3
import os
import sys
import time
import json
import shutil
import socket
import glob
import tarfile
import subprocess
import threading
import traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

HERMES_DIR = "/root/.hermes"
SIGNAL_DIR = "/root/.local/share/signal-cli"
BACKUP_DIR = "/tmp/bodhi-state"

TARGET_MODEL = "gemini-2.0-flash"
AUXILIARY_MODEL = "gemini-2.0-flash"
TARGET_PROVIDER = "custom"
TARGET_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER = os.environ.get("GITHUB_USER", "")
BACKUP_REPO = os.environ.get("BACKUP_REPO", "bodhi-state")
SIGNAL_ACCOUNT = os.environ.get("SIGNAL_ACCOUNT", "")

os.environ.pop("OPENROUTER_API_KEY", None)
os.environ["HERMES_PROVIDER"] = TARGET_PROVIDER
os.environ["HERMES_MODEL"] = TARGET_MODEL
os.environ["OPENAI_BASE_URL"] = TARGET_BASE_URL
os.environ["OPENAI_API_KEY"] = GEMINI_KEY
os.environ["GEMINI_API_KEY"] = GEMINI_KEY
os.environ["HERMES_AUXILIARY_PROVIDER"] = TARGET_PROVIDER
os.environ["HERMES_AUXILIARY_MODEL"] = AUXILIARY_MODEL

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
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print(f"[+] Render health check HTTP server listening on 0.0.0.0:{port}", flush=True)
    except Exception as e:
        print(f"[!] Health server bind error: {e}", flush=True)

def run_cmd(cmd, check=False):
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)

def restore_state():
    print("[*] Restoring Bodhi memory state and Signal session from GitHub...", flush=True)
    os.makedirs(HERMES_DIR, exist_ok=True)
    os.makedirs(SIGNAL_DIR, exist_ok=True)
    
    if os.path.exists(BACKUP_DIR):
        run_cmd(f"rm -rf {BACKUP_DIR}")
        
    if GITHUB_TOKEN and GITHUB_USER:
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
            print("[!] No backup repository found or clone failed. Initializing clean slate.", flush=True)
    else:
        print("[!] GITHUB_TOKEN or GITHUB_USER missing. Skipping state restoration.", flush=True)

def purge_legacy_state():
    print("[*] Purging legacy session threads, databases, and OpenRouter config caches...", flush=True)
    protected_files = {"SOUL.md", "USER.md"}
    for root, dirs, files in os.walk(HERMES_DIR, topdown=False):
        for f in files:
            if f not in protected_files:
                filepath = os.path.join(root, f)
                try:
                    os.remove(filepath)
                except Exception:
                    pass
        for d in dirs:
            dirpath = os.path.join(root, d)
            try:
                shutil.rmtree(dirpath, ignore_errors=True)
            except Exception:
                pass

def configure_hermes():
    print("[*] Writing Hermes configuration, profiles, and model.json...", flush=True)
    os.makedirs(os.path.join(HERMES_DIR, "profiles"), exist_ok=True)
    
    soul_target = os.path.join(HERMES_DIR, "SOUL.md")
    soul_source = "/app/config/SOUL.md"
    if os.path.exists(soul_source):
        shutil.copy(soul_source, soul_target)
        print("[+] Synced /root/.hermes/SOUL.md from tracked config/SOUL.md.", flush=True)

    user_target = os.path.join(HERMES_DIR, "USER.md")
    user_source = "/app/config/USER.md"
    if not os.path.exists(user_target) and os.path.exists(user_source):
        shutil.copy(user_source, user_target)
        print("[+] Seeded /root/.hermes/USER.md from tracked config/USER.md.", flush=True)

    config_source = "/app/config/config.yaml"
    config_target = os.path.join(HERMES_DIR, "config.yaml")
    if os.path.exists(config_source):
        with open(config_source, "r", encoding="utf-8") as f:
            cfg_str = f.read()
        for k, v in os.environ.items():
            cfg_str = cfg_str.replace(f"${{{k}}}", v)
            cfg_str = cfg_str.replace(f"${k}", v)
        with open(config_target, "w", encoding="utf-8") as f:
            f.write(cfg_str)
        print("[+] Expanded environment variables in /root/.hermes/config.yaml.", flush=True)

    model_json_path = os.path.join(HERMES_DIR, "model.json")
    model_data = {
        "provider": TARGET_PROVIDER,
        "model": TARGET_MODEL,
        "base_url": TARGET_BASE_URL,
        "api_key": GEMINI_KEY,
        "auxiliary_provider": TARGET_PROVIDER,
        "auxiliary_model": AUXILIARY_MODEL,
        "auxiliary_base_url": TARGET_BASE_URL,
        "auxiliary_api_key": GEMINI_KEY
    }
    with open(model_json_path, "w", encoding="utf-8") as f:
        json.dump(model_data, f, indent=2)

    env_content = (
        f"HERMES_PROVIDER={TARGET_PROVIDER}\n"
        f"HERMES_MODEL={TARGET_MODEL}\n"
        f"OPENAI_BASE_URL={TARGET_BASE_URL}\n"
        f"OPENAI_API_KEY={GEMINI_KEY}\n"
        f"GEMINI_API_KEY={GEMINI_KEY}\n"
        f"HERMES_AUXILIARY_PROVIDER={TARGET_PROVIDER}\n"
        f"HERMES_AUXILIARY_MODEL={AUXILIARY_MODEL}\n"
    )
    with open(os.path.join(HERMES_DIR, ".env"), "w", encoding="utf-8") as f:
        f.write(env_content)
        
    profile_content = f"""name: personal
provider: {TARGET_PROVIDER}
model: {TARGET_MODEL}
base_url: {TARGET_BASE_URL}
api_key: {GEMINI_KEY}
max_tokens: 2048
"""
    with open(os.path.join(HERMES_DIR, "profiles", "personal.yaml"), "w", encoding="utf-8") as f:
        f.write(profile_content)
    with open(os.path.join(HERMES_DIR, "profiles", "default.yaml"), "w", encoding="utf-8") as f:
        f.write(profile_content)

def wait_for_signal_daemon():
    if not SIGNAL_ACCOUNT:
        print("[!] SIGNAL_ACCOUNT environment variable not set. Skipping signal-cli daemon.", flush=True)
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
        # Sleep for 4 hours (14,400 seconds) between background GitHub state pushes
        time.sleep(14400)
        sync_to_github()

def run_hermes_supervisor():
    print("[+] Launching Hermes Agent Gateway under supervisor loop...", flush=True)
    while True:
        try:
            proc = subprocess.run(["hermes", "gateway"])
            print(f"[!] Hermes Gateway process exited with code {proc.returncode}. Restarting in 5s...", flush=True)
        except Exception as e:
            print(f"[!] Exception launching hermes gateway: {e}. Retrying in 10s...", flush=True)
            time.sleep(10)
        time.sleep(5)

def main():
    bind_health_server_instantly()

    try:
        run_cmd('git config --global user.name "Bodhi Assistant"')
        run_cmd('git config --global user.email "bodhi@render.local"')

        restore_state()
        purge_legacy_state()
        configure_hermes()

        threading.Thread(target=periodic_sync_loop, daemon=True).start()

        wait_for_signal_daemon()

        run_hermes_supervisor()

    except Exception as e:
        print(f"[FATAL] Uncaught error in entrypoint.py: {e}", flush=True)
        traceback.print_exc()
        print("[!] Keeping health server running for inspection...", flush=True)
        while True:
            time.sleep(60)

if __name__ == "__main__":
    main()