# Bodhi

Persistent Hermes Agent on Render, with Signal as the chat interface and Google AI Studio (`gemini-3.8-flash` / `gemini-3.5-flash-lite`) as the primary inference backend.

Bodhi restores memory and Signal session state from a private GitHub backup on boot, runs `signal-cli` as an HTTP daemon, and supervises `hermes gateway`. Snapshots are pushed back to GitHub every 4 hours.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Render container (Debian Bookworm + Docker)                     │
│                                                                 │
│  ┌────────────────────────┐     ┌────────────────────────────┐  │
│  │ Python supervisor      │     │ signal-cli v0.14.8         │  │
│  │ (scripts/entrypoint.py)│     │ OpenJDK 25                 │  │
│  │  - Health check :10000 ├────►│  HTTP API 127.0.0.1:8080   │  │
│  │  - Git sync every 3m   │     └──────────────▲─────────────┘  │
│  └───────────┬────────────┘                    │                │
│              │ launches                        │                │
│  ┌───────────▼────────────┐                    │                │
│  │ Hermes gateway         ├────────────────────┘                │
│  │ (hermes gateway)       │                                     │
│  └───────────┬────────────┘                                     │
│              │                                                  │
│              ▼                                                  │
│         Google AI Studio (OpenAI-compatible API)                │
└──────────────┬──────────────────────────────────────────────────┘
               │ latest.tar.gz every 3 minutes
               ▼
     GitHub repo (bodhi-state)
```

## Prerequisites

- [Render](https://render.com/) account for the Docker web service
- Google AI Studio API key from [aistudio.google.com](https://aistudio.google.com/)
- Signal account (dedicated number or secondary line)
- GitHub personal access token with `repo` scope for state backups

## 1. State backup (`bodhi-state`)

Render disks are ephemeral. Every 4 hours, `entrypoint.py` packs `/root/.hermes` and `/root/.local/share/signal-cli` into `latest.tar.gz` and force-pushes that archive to a private GitHub repo.

### Create the backup repository

1. Create a GitHub repository named `bodhi-state` (or match `BACKUP_REPO`).
2. Set visibility to **Private**.
3. Leave it empty: no README, `.gitignore`, or license.

### Create a GitHub PAT

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
2. Generate a classic token.
3. Note: `Render Bodhi State Sync`.
4. Scope: `repo`.
5. Copy the token (`ghp_...`) into Render as `GITHUB_TOKEN`.

## 2. Signal setup

`signal-cli` stores identity and ratchets under `/root/.local/share/signal-cli`. That directory is included in the GitHub snapshot.

### Link as a secondary device via Docker (Exact One-Liner)

To link Bodhi without installing local Java dependencies, run this interactive Python/Docker snippet to download `signal-cli` v0.14.8 natively, mount `~/.local/share/signal-cli`, and render the active QR code directly in your terminal:

```bash
docker run -it -v ~/.local/share/signal-cli:/root/.local/share/signal-cli python:3.11-slim bash -c '
  set -e
  echo "[*] Preparing signal-cli environment..."
  apt-get update && apt-get install -y curl qrencode > /dev/null 2>&1
  curl -fL -s -o /tmp/signal-cli-native.tar.gz "[https://github.com/AsamK/signal-cli/releases/download/v0.14.8/signal-cli-0.14.8-Linux-native.tar.gz](https://github.com/AsamK/signal-cli/releases/download/v0.14.8/signal-cli-0.14.8-Linux-native.tar.gz)"
  tar xf /tmp/signal-cli-native.tar.gz -C /opt
  SIGNAL_BIN=$(find /opt -name signal-cli -type f | head -n 1)

  python3 -c "
import subprocess

proc = subprocess.Popen([\"$SIGNAL_BIN\", \"link\", \"-n\", \"Bodhi\"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

while True:
    line = proc.stdout.readline()
    if not line:
        break
    if \"sgnl://\" in line:
        uri = line.strip()
        print(\"\n============================================================\", flush=True)
        print(\"   SCAN THIS QR CODE IMMEDIATELY WITH YOUR SIGNAL APP       \", flush=True)
        print(\"============================================================\n\", flush=True)
        subprocess.run([\"qrencode\", \"-t\", \"UTF8\", uri])
        print(\"\n[*] QR code active! Waiting for phone pairing confirmation...\n\", flush=True)
    else:
        print(line, end=\"\", flush=True)

proc.wait()
"
'
```

1. On your phone: Signal → **Settings** → **Linked devices** → **Link new device**.
2. Scan the terminal QR code immediately before the ratchet link expires.
3. Once linked, compress `~/.local/share/signal-cli` into `latest.tar.gz` and push it to your private `bodhi-state` GitHub repo so Render can restore the active session on container boot.

### Reconnecting after a handset change

If you reinstall Signal or switch handsets, sessions can desync (`InvalidMessageException`).

1. The container entrypoint automatically purges stale thread and session databases on boot.
2. Reset the ratchet from a machine running signal-cli:

   ```bash
   signal-cli -u +BOT_NUMBER send -m "[Session Reset]" --end-session +YOUR_NUMBER
   ```

3. Send a new message to Bodhi from your handset so `signal-cli` can re-negotiate keys.

## 3. Configuration

Tracked templates live in `config/`. On boot, `scripts/entrypoint.py` expands environment variables and writes them into `/root/.hermes/`.

| File | Role |
| --- | --- |
| `config/config.yaml` | Hermes model, Groq endpoint, memory, curator, Signal gateway |
| `config/SOUL.md` | Agent identity; copied to `/root/.hermes/SOUL.md` on every boot |
| `config/USER.md` | Optional user-profile seed; copied only if `/root/.hermes/USER.md` is missing |

### Inference & Resilience Model Setup

- Primary Model: `gemini-3.8-flash` via Google AI Studio's OpenAI bridge(`https://generativelanguage.googleapis.com/v1beta/openai/`).
- Auxiliary & Fallback Model: `gemini-3.5-flash-lite`. Triggered automatically during primary capacity spikes (503s) or timeouts.
- Tool Optimization: Unused built-in tools (`browser`, `computer_use`, `kanban`, `vision`, etc.) are explicitly listed under `tools.disabled` in `config/config.yaml` to minimize prompt token overhead.

## 4. Deploy on Render

`render.yaml` is already in the repo. Required environment variables:

| Variable | Example | Purpose |
| --- | --- | --- |
| `PORT` | `10000` | HTTP health check bind port |
| `GEMINI_API_KEY` | `AIzaSy...` | Google AI Studio API key |
| `SIGNAL_ACCOUNT` | `+15555550100` | Number registered with Signal |
| `SIGNAL_ALLOWED_USERS` | `+15555550100` | Allowed Signal senders (comma-separated) |
| `SIGNAL_HTTP_URL` | `http://127.0.0.1:8080` | `signal-cli` daemon URL |
| `GITHUB_TOKEN` | `ghp_...` | PAT with `repo` write access |
| `GITHUB_USER` | `your-github-username` | GitHub username |
| `BACKUP_REPO` | `bodhi-state` | Private backup repository name |

### From the Render dashboard

1. **New** → **Web Service**.
2. Connect this GitHub repository.
3. Runtime: **Docker**.
4. Instance: Free or Starter.
5. Fill in the environment variables above (secrets stay in the dashboard, not in git).
6. Create the service.

## 5. Local Docker test

```bash
docker build -t bodhi-agent .

docker run -d \
  --name bodhi_container \
  -p 10000:10000 \
  -e PORT=10000 \
  -e GEMINI_API_KEY="AIzaSy..." \
  -e SIGNAL_ACCOUNT="+15555550100" \
  -e SIGNAL_ALLOWED_USERS="+15555550100" \
  -e GITHUB_TOKEN="ghp_..." \
  -e GITHUB_USER="your-username" \
  -e BACKUP_REPO="bodhi-state" \
  bodhi-agent
```

Health check: <http://localhost:10000/>.

## 6. Troubleshooting

### `InvalidMessageException` / decryption failures

Desync between local `signal-cli` session keys and Signal's servers. Confirm `SIGNAL_ALLOWED_USERS` is the full E.164 number (`+` and country code). Use the `--end-session` command in section 2 if errors continue.

### Google AI Studio `429 Quota Exceeded` (RPM Limits)

Free accounts enforce strict Requests Per Minute (RPM) burst limits. If multi-step agent operations trigger back-to-back calls, requests will temporarily hit 429. Bodhi will back off and retry or pass through fallback channels. Upgrading to Pay-As-You-Go in Google Cloud Console increases RPM limits while retaining free token allowances.

### Base URL 404 Endpoint Routing Errors

Ensure `base_url` retains its trailing slash (`https://generativelanguage.googleapis.com/v1beta/openai/`). Omitting the trailing slash causes underlying HTTP clients to strip the `/openai` path segment, incorrectly targeting Google's native REST endpoint instead of the OpenAI bridge.
