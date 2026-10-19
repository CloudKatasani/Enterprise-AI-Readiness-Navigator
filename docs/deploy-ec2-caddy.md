# Deploying EAIRN on AWS EC2 behind Caddy (step by step)

This guide adds EAIRN to the **EC2 server that already runs Caddy** for your
other apps, the same way they were deployed:

- the code is cloned from GitHub with a plain HTTPS link (the repository is
  public, so no key is needed);
- the app runs as background services listening only on `127.0.0.1`;
- Caddy gets the HTTPS certificate and forwards a free `sslip.io` name to it.

You do everything in the **browser terminal** (EC2 console → your instance →
**Connect** → **EC2 Instance Connect** → **Connect**). Expect about 30
minutes.

EAIRN has two parts, so it runs as two services:

```
your browser ──HTTPS──▶ Caddy (already on the server)
                          └── enterprise-ai-readiness-navigator.<ip>.sslip.io
                                   │
                                   ▼
                         Portal (Next.js)  127.0.0.1:3010   ← the only part Caddy exposes
                                   │  server-side calls
                                   ▼
                         API (FastAPI)     127.0.0.1:8010   ← never exposed
                                   │
                         backend/eairn.db  (SQLite database)
```

The portal calls the API from the server, never from the browser, so only the
portal needs a public address.

> **Using the browser terminal.** Paste with **Ctrl+Shift+V** (Windows/Linux)
> or **Cmd+V** (Mac), or right-click → Paste. Paste one block at a time and
> wait for the `ubuntu@ip-...:~$` prompt before the next.

> **Ports.** Your server already uses `8000` for the Data Product
> Recommendation Engine, and likely `3000` for another app. This guide uses
> **8010** (API) and **3010** (portal). Step 1 checks they are free.

---

## Step 1. Check the server is ready

### 1.1 Ports 8010 and 3010 are free

```bash
sudo ss -ltnp | grep -E ':(8010|3010) ' || echo "ports 8010 and 3010 are free"
```

If it prints anything else, pick other numbers (e.g. 8020 and 3020) and use
them everywhere below instead of 8010 and 3010.

### 1.2 Node.js 20.9 or newer

```bash
node --version
```

- `v20.9` or higher (e.g. `v22.x`): good, continue.
- `command not found`, or lower than `v20.9`: install Node 22:

  ```bash
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
  node --version
  ```

  If your other app runs on an older Node version, ask for help first:
  upgrading Node affects every app that uses it.

### 1.3 Python and its virtual-environment tool

```bash
python3 --version
sudo apt-get update && sudo apt-get install -y python3-venv
```

Python must be 3.11 or newer (Ubuntu 24.04 has 3.12).

### 1.4 Enough memory to build the portal

Building the portal needs about 2 GB of memory, on top of your other running
apps. Check:

```bash
free -h
```

If the **available** column on the `Mem:` line is under 2.0Gi and the `Swap:`
line shows `0B`, add 2 GB of swap (disk space used as spare memory), once:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## Step 2. Download the code

```bash
cd ~
git clone https://github.com/CloudKatasani/Enterprise-AI-Readiness-Navigator.git
cd ~/Enterprise-AI-Readiness-Navigator
ls
```

You should see `backend`, `frontend`, `docs`, `README.md`.

## Step 3. Set up the API (backend)

```bash
cd ~/Enterprise-AI-Readiness-Navigator/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Load the 13 demo organisations into the database. This only needs doing once:

```bash
.venv/bin/python -m eairn.seed.bootstrap
```

It prints a table of organisations with scores (Northwind Financial, Anvil
Grid Utilities, ...). The database is the file `backend/eairn.db`.

**Optional: AI-written narratives.** Without an Anthropic API key, the AI
Advisor uses built-in templates and everything else works the same. To use a
key, create `backend/.env` (it is git-ignored):

```bash
nano ~/Enterprise-AI-Readiness-Navigator/backend/.env
```

Type `EAIRN_ANTHROPIC_API_KEY=your-key`, save with **Ctrl+O**, **Enter**,
exit with **Ctrl+X**, then run `chmod 600 ~/Enterprise-AI-Readiness-Navigator/backend/.env`.

## Step 4. Build the portal (frontend)

```bash
cd ~/Enterprise-AI-Readiness-Navigator/frontend
npm ci
EAIRN_API_URL=http://127.0.0.1:8010 npm run build
```

`npm ci` takes a minute or two. The build ends with a list of routes (`/`,
`/demo`, `/methodology`, ...).

**Keep `EAIRN_API_URL=http://127.0.0.1:8010` at the front of the build
command.** The portal writes the API address into the build itself, so if it
is missing, the portal looks for the API on port 8000, which is the other
app.

## Step 5. Run both parts as background services

These start the API and the portal now, and again after every reboot.

**The API:**

```bash
sudo tee /etc/systemd/system/eairn-api.service > /dev/null <<EOF
[Unit]
Description=EAIRN API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Enterprise-AI-Readiness-Navigator/backend
ExecStart=/home/ubuntu/Enterprise-AI-Readiness-Navigator/backend/.venv/bin/uvicorn eairn.main:app --host 127.0.0.1 --port 8010
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**The portal.** This uses whichever Node your server has, so it also works if
Node was installed with `nvm`:

```bash
NODE=$(command -v node); echo "Using $NODE"
sudo tee /etc/systemd/system/eairn-portal.service > /dev/null <<EOF
[Unit]
Description=EAIRN Portal
After=network.target eairn-api.service
Wants=eairn-api.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Enterprise-AI-Readiness-Navigator/frontend
Environment=NODE_ENV=production
Environment=EAIRN_API_URL=http://127.0.0.1:8010
ExecStart=$NODE node_modules/next/dist/bin/next start -H 127.0.0.1 -p 3010
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

`Using ...` must show a path such as `/usr/bin/node`. If it is empty, Node is
not installed: go back to step 1.2.

**Start them:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now eairn-api eairn-portal
sleep 5
sudo systemctl status eairn-api eairn-portal --no-pager | grep -E "●|Active:"
```

Both must show **`active (running)`**. Check they answer on the server:

```bash
curl -s http://127.0.0.1:8010/health; echo
curl -s -o /dev/null -w "portal: %{http_code}\n" http://127.0.0.1:3010/
```

The first prints `{"status":"ok", ...}`; the second prints `portal: 200`.

## Step 6. Add the site to Caddy

Your other apps use free `sslip.io` names built from the server's IP, e.g.
`agentic-data-product-management.13-48-101-225.sslip.io`. Use the same
pattern:

```bash
sudo grep -nE '^[^#[:space:]].*\{' /etc/caddy/Caddyfile
```

Note the IP part of the existing names (e.g. `13-48-101-225`) and set the new
name with it:

```bash
NAME=enterprise-ai-readiness-navigator.13-48-101-225.sslip.io
```

Back up the Caddy config, then add the site to the end of it:

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.backup-$(date +%F-%H%M)
sudo tee -a /etc/caddy/Caddyfile > /dev/null <<EOF

# Enterprise AI Readiness Navigator (EAIRN)
$NAME {
	encode gzip
	reverse_proxy 127.0.0.1:3010
}
EOF
```

Check and apply:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

`validate` must end with **`Valid configuration`**. Reloading does not
interrupt your other apps.

## Step 7. Open it

Open `https://enterprise-ai-readiness-navigator.13-48-101-225.sslip.io` (your
name from step 6). The first visit can take up to a minute while Caddy gets
the certificate.

You should see the portfolio of 13 organisations grouped by industry. Try:

| Page | What it shows |
| --- | --- |
| `/` | The portfolio: click an organisation for its executive, architect and steward views |
| `/demo` | Assess a synthetic estate end to end |
| `/methodology` | The whole calculation, worked through one estate |
| `/api-docs` | How to connect real platforms |

**You are done.**

> **Anyone with the address can use it.** EAIRN has no sign-in of its own, and
> the demo page creates new assessments. To ask for a password, add a
> `basicauth` block to the site (see *Optional: require a password* below).

---

## Day-to-day commands

| Task | Command |
| --- | --- |
| Are they running? | `sudo systemctl status eairn-api eairn-portal --no-pager \| grep -E "●\|Active:"` |
| API logs | `sudo journalctl -u eairn-api -n 100 --no-pager` |
| Portal logs | `sudo journalctl -u eairn-portal -n 100 --no-pager` |
| Restart both | `sudo systemctl restart eairn-api eairn-portal` |
| Reload demo data | `cd ~/Enterprise-AI-Readiness-Navigator/backend && .venv/bin/python -m eairn.seed.bootstrap` |

Running the bootstrap again adds a **new** snapshot per organisation instead of
overwriting, so the executive trend line gets a second point.

## Updating to a new version

```bash
cd ~/Enterprise-AI-Readiness-Navigator && git pull
cd backend && .venv/bin/pip install -r requirements.txt
cd ../frontend && npm ci && EAIRN_API_URL=http://127.0.0.1:8010 npm run build
sudo systemctl restart eairn-api eairn-portal
```

If the update changes the database layout and pages show `no such table`,
reset the demo database (this deletes all assessments):

```bash
sudo systemctl stop eairn-api
rm ~/Enterprise-AI-Readiness-Navigator/backend/eairn.db
sudo systemctl start eairn-api
cd ~/Enterprise-AI-Readiness-Navigator/backend && .venv/bin/python -m eairn.seed.bootstrap
```

## Backups

All data is in `~/Enterprise-AI-Readiness-Navigator/backend/eairn.db`. A safe
copy while the app runs:

```bash
python3 -c "import sqlite3; s=sqlite3.connect('/home/ubuntu/Enterprise-AI-Readiness-Navigator/backend/eairn.db'); d=sqlite3.connect('/home/ubuntu/eairn-$(date +%F).db'); s.backup(d); d.close()"
ls -lh ~/eairn-*.db
```

SQLite is fine for a demo server. For real customer data, the project
recommends Postgres (`EAIRN_DATABASE_URL`, see `RUNNING.md`).

## Optional: require a password

Your Caddy is version 2.6, which spells the directive `basicauth`.

1. Create a password hash: `caddy hash-password` (type the password twice;
   it prints a line starting with `$2a$`. Select and copy it).
2. Open the config: `sudo nano /etc/caddy/Caddyfile`
3. In the EAIRN site block, above `reverse_proxy`, add:

   ```
   	basicauth {
   		yourname <pasted hash>
   	}
   ```

4. Save (**Ctrl+O**, **Enter**, **Ctrl+X**), then run the validate and reload
   commands from step 6.

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `Command 'python' not found` | Use `python3`. |
| `The virtual environment was not created successfully because ensurepip is not available` | Run `sudo apt-get install -y python3-venv`, then delete the half-made folder with `rm -rf ~/Enterprise-AI-Readiness-Navigator/backend/.venv` and repeat step 3. |
| `npm: command not found` or Node older than 20.9 | Step 1.2. |
| Build stops with `JavaScript heap out of memory` or `Killed` | Not enough memory: add swap (step 1.4) and build again. |
| Page says **"The EAIRN API is not reachable"** | The API is down (`sudo systemctl restart eairn-api`, check its logs), or the portal was built without `EAIRN_API_URL=http://127.0.0.1:8010`: rebuild as in step 4, then `sudo systemctl restart eairn-portal`. |
| Page says **"No assessments yet"** | The database is empty: run the bootstrap (step 3). |
| A service is not `active (running)` | `sudo journalctl -u eairn-api -n 50 --no-pager` (or `eairn-portal`) shows why. `Address already in use` means the port is taken: pick another (step 1.1). |
| `caddy validate` fails | Usually `NAME` was not set in this terminal tab, so the site line is empty. Restore the backup (`sudo ls /etc/caddy/` to find it, then `sudo cp /etc/caddy/Caddyfile.backup-<date> /etc/caddy/Caddyfile`), set `NAME=...` again and repeat step 6. |
| *Your connection is not private* | The name in the browser differs from the one in the Caddyfile, or Caddy has not got the certificate yet. Check `sudo journalctl -u caddy --since "10 min ago" --no-pager \| grep -i enterprise-ai` for errors. |
| `502 Bad Gateway` | Caddy cannot reach the portal: `sudo systemctl restart eairn-portal` and check its logs. |
