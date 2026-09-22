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

## Phase 1 — tickets, boards, time, email

Adds on top of the Phase 0 schema, nothing removed:

- **Boards & statuses** — six boards seeded by migration: Triage, MS Board,
  Project Board, Alerts Board, Backups Board, Admin Board. Each has New →
  In Progress → Waiting → Resolved → Closed. Editing boards/statuses through
  the UI isn't built yet — for now, change the list at the top of
  `migrations/versions/0002_tickets.py` and re-run migrations.
- **Tickets** — numbered `YYNNN` (`26001`, `26002`... rolling to `27001` on
  Jan 1). The number is claimed atomically, so two tickets created at the
  same instant never collide.
- **Time entries** — logged in exact minutes, no rounding.
- **Email connector** — polls a shared mailbox (no license needed) for
  unread mail every 60 seconds. A new sender whose email matches a contact
  on file becomes a new ticket on the Triage board. A reply with the
  ticket's number in the subject — `[#26001]` — threads onto that ticket
  instead, and reopens it if it was closed. Mail from an address with no
  matching contact is logged but does not create a ticket; add the contact
  and it'll match on the next reply.

### Deploying this update

```
git pull   # already done if you pushed from your machine
```

On the QNAP:

```sh
docker exec -it psa-web-1 alembic upgrade head
docker restart psa-web-1 psa-worker-1
```

(The image already runs `alembic upgrade head` on boot, so a normal
`docker compose pull && up -d` after a new build handles this automatically.
The manual command above is only for applying the migration to already-
running containers without repulling.)

### Email connector setup (optional — the worker runs fine without it)

Entra ID app registrations and application permissions are free; nothing
here costs money. It's five steps in Azure Portal (entra.microsoft.com):

1. **Create the shared mailbox**, if you haven't: Microsoft 365 admin
   center → Teams & groups → Shared mailboxes → Add. `support@yourdomain.com`.
   Shared mailboxes don't consume a license.

2. **Register an app**: Entra ID → App registrations → New registration.
   Name it `psa-email-connector`. Single tenant. No redirect URI needed.

3. **Add the permission**: on the app, API permissions → Add a permission →
   Microsoft Graph → **Application permissions** → search `Mail.Read` →
   add it → **Grant admin consent**.

4. **Create a client secret**: Certificates & secrets → New client secret.
   Copy the *value* immediately — it's shown once.

5. **Scope it to only this mailbox.** `Mail.Read` as an application
   permission grants read access to every mailbox in the tenant by default.
   Lock it down to the one shared mailbox using Exchange Online PowerShell:

   ```powershell
   Connect-ExchangeOnline
   New-ApplicationAccessPolicy `
     -AppId "<the app's Application (client) ID>" `
     -PolicyScopeGroupId "support@yourdomain.com" `
     -AccessRight RestrictAccess `
     -Description "PSA email connector - support mailbox only"
   ```

Then fill in Container Station's environment variables (`GRAPH_TENANT_ID`,
`GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_MAILBOX`) and restart the
worker. Send yourself a test email and watch:

```sh
docker logs -f psa-worker-1
```

## Phase Doc-1 — documentation layer

Layered onto Companies, same as everything else:

- **Locations** — physical sites per client, address and phone.
- **Documents** — free-form text pages per company. Titles, an optional
  category (autocomplete, not enforced), pin-to-top for the stuff a tech
  needs first. No markdown rendering yet — plain text, whitespace preserved.
- **Credentials** — the password vault. Every secret is encrypted at rest
  with a Fernet key that lives only in the environment, never in the
  database or git. A credential can be linked to a Location, Configuration,
  or Contact so it shows up next to the thing it unlocks. Passwords are
  masked everywhere by default; clicking **Show** makes one request that
  decrypts and displays that one value — the decrypted password is never
  present in a normal page load.

**You must set `CREDENTIAL_ENCRYPTION_KEY` before using Credentials.**
Generate one and add it to Container Station's environment variables for
the `web` service:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Back this key up somewhere separate from your database backups — a
password manager, not the same Azure Blob container. If you lose it, every
stored credential is unrecoverable garbage; the database itself never held
the plaintext.

### Deploying this update

Same pattern as Phase 1:

```sh
docker pull ghcr.io/ahrace3/msp-psa:latest
```

Recreate the `psa` application in Container Station, adding
`CREDENTIAL_ENCRYPTION_KEY` to the environment variables first — migrations
run automatically on boot and create the three new tables.

## Phase 1.1 — workflow refinements

Adjustments made before anything above Phase 0 was ever deployed, so these
edit the Phase 1 / Doc-1 migrations and models directly rather than bolting
on more:

- **Note flags, not a note type.** A ticket note is Discussion, Internal, and
  Resolution as three independent checkboxes (Discussion checked by
  default), not a single exclusive choice — matching how ConnectWise notes
  actually work. A note can be both Internal and Resolution at once.
  Internal notes carry an `is_internal` flag that's the source of truth for
  keeping them out of any future client-facing view (portal, outbound
  email) — nothing reads that flag yet since neither exists, but the data
  is there when they do.
- **Note search.** The ticket search box (`/tickets`) now also matches text
  inside ticket notes, not just the subject/number/company. Finding "that
  printer's IP we wrote down somewhere" is a text search away.
- **Time entry timer.** The time entry form on a ticket has Start/Stop
  buttons that fill the Hours field automatically from elapsed wall-clock
  time. Purely client-side — nothing is persisted until you click Log time,
  so a forgotten tab doesn't silently bill four hours.
- **Type / Subtype / Item.** Tickets can optionally be categorized on a
  three-level tree (Hardware → Desktop/Laptop → Won't Power On, etc.),
  seeded with an ITIL-flavored default set oriented at day-to-day PC/MSP
  support work. Cascading selects on both the New Ticket form and the
  ticket detail side panel. The full seed list is in
  `migrations/versions/0002_tickets.py` (`CATEGORIES` dict) — edit it and
  re-run migrations to change the taxonomy; no admin UI for it yet.
- **Domain & SSL Certificate trackers.** Two of IT Glue's built-in flexible
  asset types, implemented as real structured data (not free-text
  Documents) specifically because their expiration dates need to be
  queryable — that's what feeds the Reports page below. Both live as panels
  on the Company page, same pattern as Locations/Documents/Credentials.
- **Reports page.** New top-level nav item. Open tickets by board, tickets
  opened/closed in the last 7/30 days, time logged this week by tech
  (total vs. billable), unbilled billable hours by company, and everything
  — domains, SSL certs, device warranties — expiring within 60 days.
  Nothing here is stored; every number is computed live.
- **Contacts and Configurations moved under Companies.** Removed from the
  top nav. They're unchanged otherwise — same routes, same forms, same
  data — but the only way to reach them now is through a company's page,
  same as Locations, Documents, and Credentials. If you want the old
  standalone search-across-everyone list back (useful for "which company
  has serial number X"), say so and it's a small change.

### Deploying this update

Same as always — nothing above Phase 0 has touched your live database yet,
so this is a clean `alembic upgrade head` with no migration-compatibility
concerns:

```sh
docker pull ghcr.io/ahrace3/msp-psa:latest
```

Recreate the `psa` application in Container Station. Migrations run
automatically on boot and create the new tables (`ticket_types`,
`ticket_subtypes`, `ticket_items`, `domains`, `ssl_certificates`) and the
new `ticket_notes` columns.

## Phase Doc-1.1 — bug fixes, Documentation hub, lookups, relations

Fixes and a real restructure, made because Doc-1 and Phase 1.1 had actually
been deployed by this point — 0001 through 0003 are live, so this ships as
a genuinely new migration (0004) rather than an edit to what's already run.

**Two real bugs, both found from your screenshots:**
- **Adding a credential 500'd.** Root cause: `CREDENTIAL_ENCRYPTION_KEY`
  wasn't set in the `web` service's environment variables, so the encrypt
  call threw and crashed the request. Now it catches that and shows a
  plain-English message telling you exactly what's missing, instead of a
  raw error page.
- **Reports 500'd.** A `GROUP BY` bug in the "open tickets by board" query
  — ordering by a column that wasn't in the grouped set, which Postgres
  rejects outright. Fixed.
- **Closed tickets were invisible on `/tickets`.** The board view had a
  "Show closed tickets" toggle; the main ticket list never did. Added.

**Documentation is now one nav item, not two.** `/documentation` is a hub
page listing Passwords, Documents, Locations, Domains, and SSL Certificates
— each with a real searchable list of its own (Locations, Domains, and SSL
Certificates didn't have global list pages before; only Documents and
Credentials did). Every "Add" button now works even when you haven't
already drilled into a company — pick one from a short list first, then
land on the real form.

**Domain and SSL Certificate trackers do real lookups now:**
- **Domains** — leave Registrar and Expires blank when adding one and a
  WHOIS lookup tries to fill in registrar, creation/update/expiration
  dates, name servers, and registry status. A **Refresh from WHOIS**
  button on the edit page re-runs it any time. WHOIS is inherently flaky —
  formats vary by TLD, some registrars redact fields, and servers
  rate-limit — so every field stays hand-editable regardless of where it
  came from, and a failed lookup never blocks saving the record.
- **SSL Certificates** — leave Issued By and Expires blank and a live TLS
  handshake against the domain fills in issuer, issued/expiry dates,
  serial number, signature algorithm, subject alternative names, and a
  SHA-256 fingerprint. Same **Refresh** pattern.
- Neither of these could be tested against a real WHOIS server or a real
  certificate from the sandbox this was built in — the code paths are
  exercised and the libraries confirmed working, but the first real lookup
  on your actual server is the real test. Try one on a domain you know the
  answer for and confirm it looks right.

**Related items.** Configurations, Credentials, Documents, Locations,
Domains, and SSL Certificates can now be linked to each other — a device
to the password that logs into it, a document to the site it describes,
whatever. Shows up as a "Related items" panel on each one's edit page with
a simple "link to..." picker and a Remove button per link.

### Deploying this update

```sh
docker pull ghcr.io/ahrace3/msp-psa:latest
```

Recreate the `psa` application in Container Station — migrations run
automatically and only add columns/tables (`related_items`, plus new
columns on `domains` and `ssl_certificates`); nothing existing is touched.

**If Credentials was still 500ing before this update, that's your
`CREDENTIAL_ENCRYPTION_KEY`.** Generate one if you haven't:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add it to the **`web`** service's environment variables in Container
Station (worker doesn't need it) and recreate.

## Roadmap

- ~~**Phase 1** — tickets, boards, statuses, time entries, inbound email via Graph~~ done
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
