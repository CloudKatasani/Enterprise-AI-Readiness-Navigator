# Deploying EAIRN on AWS EC2 with Caddy

The simplest production setup: one EC2 instance runs the API and the Portal as systemd services,
and Caddy sits in front of them, serving HTTPS on port 443 with a certificate it obtains and renews
itself.

No domain is needed. The site is served at
`https://enterprise-ai-readiness-navigator.<public-ip>.sslip.io`.
[sslip.io](https://sslip.io) is a free public DNS service that resolves any name containing an IP
address to that IP, so `enterprise-ai-readiness-navigator.3.91.20.15.sslip.io` points at
`3.91.20.15`. That gives Caddy a real hostname to get a Let's Encrypt certificate for.

```
Internet ──443/80──▶ Caddy ──▶ Portal (127.0.0.1:3000) ──▶ API (127.0.0.1:8000) ──▶ SQLite
```

Only Caddy is reachable from outside. The Portal calls the API server-side over loopback, so the API
never needs a public port.

These steps assume **Ubuntu 24.04** and a shell opened through **AWS Systems Manager → Session
Manager**. If you are on Amazon Linux 2023, see the [note at the end](#amazon-linux-2023).

---

## 0. Before you start (AWS console)

1. **Instance size:** `t3.small` (2 GB RAM) or larger. The Next.js build needs more memory than a
   `t3.micro` has; if you use a micro, do the swap step in section 1.
2. **Disk:** 20 GB is plenty.
3. **Security group inbound rules:** allow **TCP 80** and **TCP 443** from `0.0.0.0/0`.
   Session Manager needs no inbound port, so you do not need to open 22.
4. **Elastic IP (strongly recommended):** allocate one and associate it with the instance. The
   site's address contains the IP, so without an Elastic IP the address changes every time the
   instance is stopped and started.

No DNS records to create: sslip.io handles that.

---

## 1. Become root and install the prerequisites

Session Manager logs you in as `ssm-user` in a basic `sh` shell. Switch to root so you can paste the
rest without `sudo`:

```bash
sudo -i
```

Install Python, Git and Node.js 22:

```bash
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
```

Check the versions (Python ≥ 3.11, Node ≥ 20.9):

```bash
python3 --version && node --version
```

*Optional, only on a `t3.micro`:* add 2 GB of swap so the build does not run out of memory.

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

```bash
cd /opt/eairn/frontend
sudo -u eairn npm ci
sudo -u eairn npm run build
```

---

## 5. Run both as services

Create the two service files:

```bash
cat > /etc/systemd/system/eairn-api.service <<'EOF'
[Unit]
Description=EAIRN API
After=network.target

[Service]
User=eairn
WorkingDirectory=/opt/eairn/backend
ExecStart=/opt/eairn/backend/.venv/bin/uvicorn eairn.main:app --host 127.0.0.1 --port 8000
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
ExecStart=/usr/bin/npm start -- -H 127.0.0.1 -p 3000
Restart=always

[Install]
WantedBy=multi-user.target
EOF
```

Start them, and have them start on every boot:

```bash
systemctl daemon-reload
systemctl enable --now eairn-api eairn-portal
```

Check both are answering:

```bash
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000    # expect 200
```

---

## 6. Install Caddy and point it at the Portal

```bash
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy
```

Work out the site's hostname from the instance's public IP. This asks the EC2 metadata service, so
there is nothing to type in:

```bash
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
SITE="enterprise-ai-readiness-navigator.${PUBLIC_IP}.sslip.io"
echo "$SITE"
```

The `echo` should print something like `enterprise-ai-readiness-navigator.3.91.20.15.sslip.io`. If
the IP part is empty, the instance has no public IP: attach an Elastic IP (step 0) and run the block
again.

Write the Caddyfile and reload Caddy:

```bash
cat > /etc/caddy/Caddyfile <<EOF
${SITE} {
    encode gzip
    reverse_proxy 127.0.0.1:3000
}
EOF
cat /etc/caddy/Caddyfile
systemctl reload caddy
```

Caddy gets a Let's Encrypt certificate for that name on its own, within about a minute. Ports 80
and 443 must be open in the security group (step 0), because Let's Encrypt checks the instance over
them.

---

## 7. Open it

Browse to the address the `echo` printed, with `https://` in front:

```
https://enterprise-ai-readiness-navigator.<public-ip>.sslip.io
```

You should see the portfolio of 13 assessed organisations. If you need the address again later, run
`head -1 /etc/caddy/Caddyfile` on the instance.

**If the IP changes** (no Elastic IP and the instance was restarted), re-run the whole step 6 block
from `TOKEN=` onward. Caddy fetches a certificate for the new name and the old address stops
working.

---

## Updating to a new version

```bash
sudo -i
cd /opt/eairn && sudo -u eairn git pull
cd backend && sudo -u eairn .venv/bin/pip install -r requirements.txt
cd ../frontend && sudo -u eairn npm ci && sudo -u eairn npm run build
systemctl restart eairn-api eairn-portal
```

If the update changes the database schema and the API logs `no such table`, reset the demo data:
`systemctl stop eairn-api && rm /opt/eairn/backend/eairn.db && systemctl start eairn-api`, then
re-run the bootstrap from step 3.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Page says "The EAIRN API is not reachable" | `systemctl status eairn-api` and `journalctl -u eairn-api -n 50` |
| Page says "No assessments yet" | The bootstrap in step 3 was not run (or ran as a different user). Re-run it. |
| Browser can't connect at all | Security group allows 80/443? `systemctl status caddy` |
| HTTPS certificate error | Ports 80 and 443 open? Does `cat /etc/caddy/Caddyfile` show the instance's *current* public IP? `journalctl -u caddy -n 50` shows the Let's Encrypt error. |
| `dig +short <site-name>` doesn't return the IP | Some company networks block sslip.io. Try from a phone on mobile data. |
| `npm run build` killed / out of memory | Add swap (section 1) or use a larger instance. |
| Portal service keeps restarting | `journalctl -u eairn-portal -n 50` — usually the build in step 4 did not finish. |

Live logs for everything: `journalctl -fu eairn-api -u eairn-portal -u caddy`.

---

## Notes

- **SQLite is fine for a demo, not for real customer data.** For a real deployment set
  `EAIRN_DATABASE_URL` in `/opt/eairn/backend/.env` to a Postgres database (for example Amazon RDS)
  — see [RUNNING.md](../RUNNING.md#configuration).
- **Backups:** with SQLite, the whole state is the one file `/opt/eairn/backend/eairn.db`. An EBS
  snapshot of the volume covers it.
- **The OpenAPI browser** (`/docs` on the API) is not exposed publicly. To view it, run
  `curl http://127.0.0.1:8000/openapi.json` on the instance, or use a Session Manager port forward.

### Amazon Linux 2023

Only section 1 and section 6 differ. Replace the prerequisites with:

```bash
sudo -i
dnf install -y python3.11 python3.11-pip git
curl -fsSL https://rpm.nodesource.com/setup_22.x | bash -
dnf install -y nodejs
```

and use `python3.11` instead of `python3` in step 3. In step 2, the `nologin` shell is at
`/sbin/nologin`. Caddy has no AL2023 package, so install the official binary:

```bash
curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=amd64" -o /usr/bin/caddy   # arch=arm64 on Graviton
chmod +x /usr/bin/caddy
groupadd --system caddy
useradd --system --gid caddy --create-home --home-dir /var/lib/caddy --shell /sbin/nologin caddy
mkdir -p /etc/caddy
curl -fsSL https://raw.githubusercontent.com/caddyserver/dist/master/init/caddy.service -o /etc/systemd/system/caddy.service
```

Then run the step 6 block from `TOKEN=` onward, but use `systemctl daemon-reload && systemctl enable --now caddy`
in place of `systemctl reload caddy`.
