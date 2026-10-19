# Deploying EAIRN on AWS EC2 with Caddy

EAIRN runs on the existing EC2 instance at **13.49.239.78**, next to the apps already served there,
at:

**https://enterprise-ai-readiness-navigator.13-49-239-78.sslip.io**

It follows the same pattern as
`https://fractional-ai-architecture-office.13-49-239-78.sslip.io`: one Caddy on the instance serves
every app on its own sslip.io hostname, each with its own HTTPS certificate.
[sslip.io](https://sslip.io) is a free DNS service that resolves any name containing an IP to that
IP, so no domain or DNS record is needed.

```
Internet ──443──▶ Caddy ─┬─▶ fractional-ai-architecture-office…  (existing, unchanged)
                         └─▶ enterprise-ai-readiness-navigator…  ──▶ Portal 127.0.0.1:3100
                                                                      └─▶ API 127.0.0.1:8100 ──▶ SQLite
```

EAIRN uses ports **3100** (Portal) and **8100** (API), bound to `127.0.0.1` only. That keeps it clear
of the default 3000/8000, which the existing app may already use. Only Caddy is reachable from
outside.

All commands are run in a **Session Manager** shell on the instance.

---

## 0. Check the instance

Session Manager logs you in as `ssm-user` in a basic `sh` shell. Switch to root so you can paste the
rest without `sudo`:

```bash
sudo -i
```

Confirm the two ports are free. This should print nothing:

```bash
ss -ltn | grep -E ':(3100|8100)\b'
```

If it prints a line, pick other ports and change every `3100`/`8100` below to match.

Check what is already installed:

```bash
head -2 /etc/os-release
python3 --version; node --version; caddy version
```

You need **Python ≥ 3.11** and **Node ≥ 20.9**. Caddy is already there, since it serves the existing
app. The security group already allows 80/443 for the same reason.

---

## 1. Install anything missing

Skip whatever step 0 showed is already installed at the right version.

**Ubuntu:**

```bash
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs
```

**Amazon Linux 2023:** its default `python3` is 3.9, which is too old. Install 3.11 and use
`python3.11` in place of `python3` in step 3:

```bash
dnf install -y python3.11 python3.11-pip git
curl -fsSL https://rpm.nodesource.com/setup_22.x | bash - && dnf install -y nodejs
```

The Next.js build needs about 1.5 GB of memory. On an instance with 1 GB of RAM (`free -h`), add swap
first:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

---

## 2. Get the code

```bash
useradd --system --create-home --shell /usr/sbin/nologin eairn
git clone https://github.com/CloudKatasani/Enterprise-AI-Readiness-Navigator.git /opt/eairn
```

If the repository is private, Git asks for a username and password: use your GitHub username and a
[personal access token](https://github.com/settings/tokens) (read-only "Contents" access is enough)
as the password.

---

## 3. Build the API and seed the demo data

```bash
cd /opt/eairn/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chown -R eairn:eairn /opt/eairn
sudo -u eairn .venv/bin/python -m eairn.seed.bootstrap
```

The bootstrap takes about a minute and prints each organisation as it scores. It creates
`/opt/eairn/backend/eairn.db`.

*Optional:* to let the AI Advisor draft narratives, create `/opt/eairn/backend/.env` containing
`EAIRN_ANTHROPIC_API_KEY=your-key`. Without it the advisor uses its built-in templates and everything
else works the same.

---

## 4. Build the Portal

The API address is compiled into the Portal at build time, so it is set on the build command:

```bash
cd /opt/eairn/frontend
sudo -u eairn npm ci
sudo -u eairn EAIRN_API_URL=http://127.0.0.1:8100 npm run build
```

---

## 5. Run both as services

```bash
cat > /etc/systemd/system/eairn-api.service <<'EOF'
[Unit]
Description=EAIRN API
After=network.target

[Service]
User=eairn
WorkingDirectory=/opt/eairn/backend
ExecStart=/opt/eairn/backend/.venv/bin/uvicorn eairn.main:app --host 127.0.0.1 --port 8100
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/eairn-portal.service <<'EOF'
[Unit]
Description=EAIRN Portal
After=network.target eairn-api.service

[Service]
User=eairn
WorkingDirectory=/opt/eairn/frontend
Environment=NODE_ENV=production
Environment=EAIRN_API_URL=http://127.0.0.1:8100
ExecStart=/usr/bin/npm start -- -H 127.0.0.1 -p 3100
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now eairn-api eairn-portal
```

Check both are answering:

```bash
curl -s http://127.0.0.1:8100/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3100    # expect 200
```

---

## 6. Add the site to Caddy

The Caddyfile already holds the existing app's site, so **add to it, don't replace it**. Take a
backup, then append the new site block:

```bash
cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak

cat >> /etc/caddy/Caddyfile <<'EOF'

enterprise-ai-readiness-navigator.13-49-239-78.sslip.io {
    encode gzip
    reverse_proxy 127.0.0.1:3100
}
EOF
```

Check the file, then reload. `reload` applies the change without dropping the existing site:

```bash
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy
```

If `validate` reports an error, put the backup back with
`cp /etc/caddy/Caddyfile.bak /etc/caddy/Caddyfile` and don't reload. If Caddy on this instance runs
from a different config file (`systemctl cat caddy` shows the path after `--config`), append to that
file instead.

Caddy gets a Let's Encrypt certificate for the new name on its own, within about a minute.

---

## 7. Open it

**https://enterprise-ai-readiness-navigator.13-49-239-78.sslip.io**

You should see the portfolio of 13 assessed organisations. The existing app at
`https://fractional-ai-architecture-office.13-49-239-78.sslip.io` keeps working as before.

---

## Updating to a new version

```bash
sudo -i
cd /opt/eairn && sudo -u eairn git pull
cd backend && sudo -u eairn .venv/bin/pip install -r requirements.txt
cd ../frontend && sudo -u eairn npm ci && sudo -u eairn EAIRN_API_URL=http://127.0.0.1:8100 npm run build
systemctl restart eairn-api eairn-portal
```

If the update changes the database schema and the API logs `no such table`, reset the demo data:
`systemctl stop eairn-api && rm /opt/eairn/backend/eairn.db && systemctl start eairn-api`, then
re-run the bootstrap from step 3.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Page says "The EAIRN API is not reachable" | `systemctl status eairn-api`, `journalctl -u eairn-api -n 50`. The URL it shows should end in `:8100`; if it says `:8000`, the build in step 4 missed `EAIRN_API_URL`. Rebuild and restart the portal. |
| Page says "No assessments yet" | The bootstrap in step 3 was not run (or ran as a different user). Re-run it. |
| `502 Bad Gateway` | Caddy is up but the Portal isn't: `systemctl status eairn-portal`. |
| HTTPS certificate error | `journalctl -u caddy -n 50` shows the Let's Encrypt error. |
| Portal service keeps restarting | `journalctl -u eairn-portal -n 50`. Usually the build in step 4 didn't finish. |
| `npm run build` killed / out of memory | Add swap (step 1). |
| Existing app broke after step 6 | `cp /etc/caddy/Caddyfile.bak /etc/caddy/Caddyfile && systemctl reload caddy`. |

Live logs: `journalctl -fu eairn-api -u eairn-portal -u caddy`.

---

## Notes

- **Keep the IP fixed.** The hostname contains `13-49-239-78`. If that is an Elastic IP it never
  changes. If it is not, the address changes every time the instance stops and starts. Attach an
  Elastic IP to avoid that.
- **SQLite is fine for a demo, not for real customer data.** For a real deployment set
  `EAIRN_DATABASE_URL` in `/opt/eairn/backend/.env` to a Postgres database (for example Amazon RDS);
  see [RUNNING.md](../RUNNING.md#configuration).
- **Backups:** with SQLite, the whole state is the one file `/opt/eairn/backend/eairn.db`. An EBS
  snapshot of the volume covers it.
- **The OpenAPI browser** (`/docs` on the API) is not exposed publicly. On the instance,
  `curl http://127.0.0.1:8100/openapi.json` returns the spec.
