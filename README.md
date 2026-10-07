# Bodhi

Persistent Hermes Agent on Render, with Signal as the chat interface and Groq (`openai/gpt-oss-120b` / `openai/gpt-oss-20b`) as the inference backend.

Bodhi restores memory and Signal session state from a private GitHub backup on boot, runs `signal-cli` as an HTTP daemon, and supervises `hermes gateway`. Snapshots are pushed back to GitHub every three minutes.

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
│         Groq (OpenAI-compatible API)                            │
└──────────────┬──────────────────────────────────────────────────┘
               │ latest.tar.gz every 3 minutes
               ▼
     GitHub repo (bodhi-state)
```

## Prerequisites

- [Render](https://render.com/) account for the Docker web service
- Groq API key from [console.groq.com](https://console.groq.com/)
- Signal account (dedicated number or secondary line)
- GitHub personal access token with `repo` scope for state backups

## 1. State backup (`bodhi-state`)

Render disks are ephemeral. On a schedule, `entrypoint.py` packs `/root/.hermes` and `/root/.local/share/signal-cli` into `latest.tar.gz` and force-pushes that archive to a private GitHub repo.

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

### Link as a secondary device (recommended)

```bash
signal-cli link -n "Bodhi-Render"
```

1. On your phone: Signal → **Settings** → **Linked devices** → **Link new device**.
2. Scan the QR code (or open the `tsdevice://` URL).
3. Archive `~/.local/share/signal-cli` into the first `bodhi-state` backup, or let the running container sync after a successful link.

### Register a standalone number

```bash
signal-cli -u +YOUR_NUMBER register
signal-cli -u +YOUR_NUMBER verify CODE
```

### Reconnecting after a phone change

If you reinstall Signal or switch handsets, sessions can desync (`InvalidMessageException`).

1. The entrypoint already drops leftover session databases on boot.
2. From a machine with `signal-cli` and the bot account:

   ```bash
   signal-cli -u +BOT_NUMBER send -m "[Session Reset]" --end-session +YOUR_NUMBER
   ```

3. Message Bodhi from the new phone so `signal-cli` can negotiate a new ratchet.

## 3. Configuration

Tracked templates live in `config/`. On boot, `scripts/entrypoint.py` expands environment variables and writes them into `/root/.hermes/`.

| File | Role |
| --- | --- |
| `config/config.yaml` | Hermes model, Groq endpoint, memory, curator, Signal gateway |
| `config/SOUL.md` | Agent identity; copied to `/root/.hermes/SOUL.md` on every boot |
| `config/USER.md` | Optional user-profile seed; copied only if `/root/.hermes/USER.md` is missing |

Hermes requires:

- a singular `model:` block (provider, default model id, Groq `base_url`)
- `custom_providers:` as a **YAML list** (`- name: groq`), not a mapping

Primary model is `openai/gpt-oss-120b`. Auxiliary work and fallback use `openai/gpt-oss-20b`. Groq retired `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` for free/developer accounts on 16 August 2026.

## 4. Deploy on Render

`render.yaml` is already in the repo. Required environment variables:

| Variable | Example | Purpose |
| --- | --- | --- |
| `PORT` | `10000` | HTTP health check bind port |
| `GROQ_API_KEY` | `gsk_...` | Groq API key |
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
  -e GROQ_API_KEY="gsk_..." \
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

### Render: no open ports detected

`signal-cli` can take more than 30 seconds to start. `scripts/entrypoint.py` binds `0.0.0.0:10000` in a background thread before any other work so the health check succeeds immediately.

### Groq `model_not_found` (HTTP 404)

`llama-3.3-70b-versatile` and `llama-3.1-8b-instant` are enterprise-only after Groq's 16 August 2026 shutdown. Use `openai/gpt-oss-120b` and `openai/gpt-oss-20b` (see `config/config.yaml`).

### OpenRouter 401 errors

Stale SQLite state or unexpanded `${GROQ_API_KEY}` can send traffic to OpenRouter. On boot the entrypoint purges legacy session files, expands variables into `/root/.hermes/config.yaml`, and points the custom provider at `https://api.groq.com/openai/v1`.
