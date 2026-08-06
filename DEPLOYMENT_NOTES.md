# Deploy playbook

Keep this short. Ship from `main` only.

## Architecture

| Surface | URL | On box |
|---------|-----|--------|
| Website + API app root | https://theservicesexchange.com · API https://rse-api.com:5003 | `/var/www/theservicesexchange` |
| Server | `root@143.110.131.237` | SSH key `~/.ssh/id_ed25519` |
| Service | `theservicesexchange.service` | gunicorn on `:5004` (nginx terminates TLS) |

Same tree serves HTML and API. `config.py` is **gitignored** — never commit it; edit on the server (or scp) if secrets change.

## Before you deploy (laptop)

```bash
# 1. Clean working tree on main
git status
git checkout main
git pull origin main

# 2. Commit what you intend to ship
git add -A
git commit -m "Short why-this-change message"
git push origin main

# 3. Quick quality gate (fail = do not deploy)
python3 -m py_compile api_server.py handlers.py utils.py
# optional: python3 int_tests.py   # hits live/local API; skip if offline
```

## Deploy (one command)

```bash
./deploy.sh
```

What it does:

1. Optional `.env` scp  
2. Server: `git pull origin main` (stashes local dirty files like `config.py`)  
3. Restart `theservicesexchange.service`  
4. Smoke: `/ping` + optional Grok “next features” note  

## Manual deploy (if you skip the script)

```bash
ssh -i ~/.ssh/id_ed25519 root@143.110.131.237
cd /var/www/theservicesexchange
git pull origin main
systemctl restart theservicesexchange.service
systemctl is-active theservicesexchange.service
curl -sS https://rse-api.com:5003/ping
```

## After deploy — check

- Site: https://theservicesexchange.com  
- API: `curl -sS https://rse-api.com:5003/stats | head`  
- Logs: `journalctl -u theservicesexchange.service -n 50 --no-pager`

## Quality habits (simple)

- Prefer **commit → push → `./deploy.sh`**. Avoid scp-of-random-files as the normal path (breaks git history on prod).  
- If you hot-fixed on the server, copy the fix back to git ASAP (`git diff` on server, apply locally, commit, pull).  
- Do not commit: `config.py`, secrets, `auth.json`, large `node_modules/`.  
- One deploy = one intentional `main` tip; don’t leave uncommitted product work only on prod.

## Grok Build job (optional, small)

Suggests **3 next features** from the current tree. Safe: read-only tools, no edits.

```bash
# laptop or prod (needs grok on PATH + auth)
./scripts/prod/suggest_next_features.sh
```

Output: `data/next_features.md` (local) and stdout. On prod you can cron weekly:

```cron
0 5 * * 1 /var/www/theservicesexchange/scripts/prod/suggest_next_features.sh >> /var/log/rse-next-features.log 2>&1
```

## Related ops (not every deploy)

| Job | When |
|-----|------|
| Robot catalog weekly | cron Mon 04:15 — `scripts/catalog/run_weekly_catalog_update.sh` |
| Auto-bid processor | cron every 30m — `scripts/prod/process_due_auto_bids.sh` |
| Grok CLI install | once — `scripts/prod/install_grok_build.sh` |

## Config / secrets

- **Laptop:** `config.py` from `config_example.py`  
- **Prod:** keep server `config.py` out of git; pull never overwrites it if untracked/stashed  
- **Grok on prod:** `/root/.grok/auth.json` or `XAI_API_KEY` in `/etc/rse/catalog.env`
