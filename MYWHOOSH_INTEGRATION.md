# Native MyWhoosh integration for FitTrackee

This source tree adds MyWhoosh as a native FitTrackee connection. It is based
on FitTrackee `v1.4.x` at commit `131e3a58c1557d5f634dda6bb94031297e9f1638`
(`1.4.0b1`).

## What is included

- A **Connections** tab in the FitTrackee profile.
- One-time MyWhoosh sign-in. The password is sent to MyWhoosh and is never
  stored by FitTrackee.
- Encryption at rest for the MyWhoosh access token, derived from
  `APP_SECRET_KEY`.
- Direct FIT import through FitTrackee's internal workout creation service.
- Import as the built-in `Cycling (Virtual)` sport, including the user's
  default equipment and visibility preferences.
- Manual synchronization and optional automatic synchronization.
- A persistent import ledger that prevents duplicate workouts, including
  after disconnecting and reconnecting an account.
- A 30-minute stale-lock recovery to prevent overlapping synchronizations.
- FIT download size limits and validation of MyWhoosh's pre-signed download
  host.

MyWhoosh does not currently publish an official public OAuth flow for this
use case. This integration therefore uses the unofficial endpoints documented
by `mywhoosh-community/mywhoosh-api`. If MyWhoosh changes them, the connection
may need to be updated.

## Installation with Docker Compose

Back up the PostgreSQL database and the uploads directory first.

Set `APP_SECRET_KEY` and `POSTGRES_PASSWORD` in the environment-variable
section of your stack manager. A physical `.env` file is not required.
`APP_SECRET_KEY` must remain stable: changing it invalidates stored MyWhoosh
tokens and requires users to reconnect.

Build and start the customized image plus the native synchronization runner:

```bash
docker compose up -d --build
```

The normal FitTrackee entrypoint runs the new database migration automatically.

Open **Profile → Connections**, enter the MyWhoosh credentials, then select
**Synchronize now**. After the first successful import, automatic
synchronization can be enabled on the same page.

## Synchronization interval

The automatic runner checks enabled accounts every 10 minutes. To change the
interval, define a value in seconds in the stack environment, for example:

```env
MYWHOOSH_SYNC_INTERVAL=1800
```

The command can also be run manually:

```bash
docker compose exec fittrackee ftcli integrations mywhoosh-sync
```

To limit it to one FitTrackee account:

```bash
docker compose exec fittrackee ftcli integrations mywhoosh-sync --username USERNAME
```

## Removal

Stop the scheduler and return to the upstream FitTrackee image only after
disabling automatic synchronization. The database migration can be downgraded
with:

```bash
docker compose run --rm fittrackee ftcli db downgrade 28a548e58b3f
```

Downgrading deletes the MyWhoosh connection and import ledger tables. It does
not delete workouts that were already imported.

## Recovery from incomplete FIT event messages

If synchronization fails with `field "event" (idx #0) not found in message
"event"`, update the source and rebuild **both** the web application and the
scheduler. Restarting containers alone keeps the old parser:

```bash
git pull --ff-only
docker compose up -d --build fittrackee fittrackee-mywhoosh-scheduler
```

For a Git-managed stack, pull/redeploy the latest `main` revision and rebuild
the image for both services in the stack manager instead.

Then choose **Profile → Connections → Synchronize now**. Failed imports are
retried automatically when they are within the configured synchronization
window; already imported activities are skipped. Do not delete the import
ledger or reset the database.

The parser now ignores event messages without `event` or `event_type` while
preserving GPS records and valid timer stop events. The separate warning
`EMAIL_URL is not provided, email sending is deactivated` only means outgoing
email is disabled and does not cause this FIT parsing failure.
