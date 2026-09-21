# MSP PSA — Phase 0

A self-hosted PSA modeled on ConnectWise Manage, sized for a small MSP and
running on a QNAP TS-1253U-RP via Container Station.

Phase 0 covers the foundation everything else attaches to: authentication,
Companies, Contacts, Configurations, a Postgres-backed job queue, and backups.
Tickets, agreements, billing and the NinjaRMM / Microsoft 365 / Google
Workspace integrations arrive in later phases against this same schema.

## What runs

Three containers, roughly 1.2 GB of RAM total:

| Container | Job |
|---|---|
| `postgres` | Postgres 16, tuned small. Data and job queue. |
| `web` | FastAPI + Jinja + HTMX on port 8090. Runs migrations on boot. |
| `worker` | Claims jobs from Postgres. Heartbeat now, syncs later. |

No Redis. The job queue lives in Postgres using `FOR UPDATE SKIP LOCKED`,
which is plenty at MSP volume and one less container to keep alive.

## Architecture notes

**Everything is outbound-only.** Nothing is port-forwarded to the NAS.
NinjaRMM alerts are polled rather than pushed, and inbound email is pulled
from Microsoft Graph. If the NAS is offline, mail stays in the mailbox and
Ninja keeps its alert history, so the next poll catches up. Delayed tickets,
never lost tickets.

**Remote access is Tailscale, not a firewall rule.** Install the Tailscale
container on the QNAP and reach the PSA at `http://<nas>:8090` over the
tailnet from anywhere.

## Deploy on the QNAP

1. **Add RAM first.** The box has one free SODIMM slot and reports 3.73 GB
   usable. A second 4 GB DDR3L stick gives real headroom. This runs without
   it, but with nothing to spare.

2. **Create the folders.** File Station, inside the `Container` share:

   ```
   /share/Container/psa/pgdata
   /share/Container/psa/attachments
   /share/Container/psa/backups
   /share/Container/psa/scripts
   ```

3. **Build the image.** Push this repo to a private GitHub repo. The Actions
   workflow builds `linux/amd64` and pushes to
   `ghcr.io/<you>/msp-psa:latest`. Never build on the J1900; it will take
   most of an hour.

4. **Make the package pullable.** On the GHCR package page set visibility, or
   add a read-only PAT to Container Station under Registries.

5. **Create the application.** Container Station > Applications > Create.
   Name it `psa`, paste `docker-compose.yml`, and add the environment
   variables from `.env.example` in the same dialog. Generate real secrets:

   ```
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

6. **Create your login.**

   ```
   docker exec -it psa-web-1 python -m app.cli create-admin you@yourdomain.com "Your Name"
   ```

7. **Sign in** at `http://<nas-ip>:8090`.

## Backups

`scripts/backup.sh` dumps Postgres, keeps 14 days locally, and pushes a
gzipped copy to Azure Blob (Cool tier) with a write-only SAS token. At this
data size it runs well under a dollar a month. Copy both scripts to
`/share/Container/psa/scripts/`, fill in the Azure values, and schedule the
backup daily in Control Panel > Task Scheduler.

Run `scripts/restore.sh` once against a throwaway database before you trust
any of it. An untested backup is a guess.

## Security

The NAS now holds client contact data. Before going live: disable the default
`admin` account, enable 2FA on your QTS login, keep QTS current, and confirm
the NAS is not reachable from the internet. Set `https_only=True` in
`app/main.py` once the app is behind Tailscale HTTPS or a reverse proxy.

## Layout

```
app/
  config.py        settings from environment
  db.py            engine, session, declarative base
  models.py        Phase 0 schema
  security.py      password hashing, session auth
  queue.py         Postgres job queue
  worker.py        job loop and handler registry
  cli.py           create-admin
  routes/          auth, companies, contacts, configurations
  templates/       Jinja + HTMX
migrations/        Alembic
scripts/           backup and restore
```

## Roadmap

- **Phase 1** — tickets, boards, statuses, time entries, inbound email via Graph
- **Phase 2** — NinjaRMM device sync, alert-to-ticket, self-healing auto-close
- **Phase 3** — Microsoft 365 and Google Workspace user and license sync
- **Phase 4** — agreements, billing run, invoice batches, CSV export
- **Phase 5** — QuickBooks Online push, reporting, client portal

## Adding a job handler

```python
@handler("ninja_device_sync")
def sync_devices(db, payload: dict) -> None:
    ...

RECURRING["ninja_device_sync"] = 1800
```

The worker re-enqueues recurring jobs after each run, so there is no separate
scheduler to keep alive.
