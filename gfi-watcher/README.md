# good-first-issue watcher

Polls a curated list of well-known repos (Docker/Kubernetes/containerization/
SQL/system-design ecosystem) every 15 minutes for open, **unassigned**
`good first issue` tickets with low comment counts. When it finds new ones,
it **opens an issue in this same repo** listing them — so you get notified
through GitHub itself (web bell icon + push notification on the GitHub
mobile app), no email required.

## Setup (5 minutes)

1. **Create a new repo on GitHub** (private is fine), e.g. `gfi-watcher`.
2. Push these files to it exactly as structured:
   ```
   .github/workflows/watch.yml
   scripts/check_issues.py
   state/seen_issues.json
   README.md
   ```
   No secrets need to be added — `GITHUB_TOKEN` is provided automatically by
   GitHub Actions and is enough to create issues in this same repo.
3. **Enable Actions** on the repo if prompted (Settings → Actions → General →
   Allow all actions).
4. **Turn on push notifications** so alerts reach you instantly:
   - Install the **GitHub Mobile app** and sign in.
   - On github.com: click your profile photo → **Settings** →
     **Notifications** → under "Web and Mobile", make sure **Issues** is
     checked (Participating and @mentions is enough, since you'll be the
     issue creator/watcher on your own repo). You can leave "Email" boxes
     unchecked entirely.
5. Test it immediately: go to the **Actions** tab → "Watch good-first-issues"
   → **Run workflow** (this is the `workflow_dispatch` trigger). If matches
   exist, check the **Issues** tab — a new issue listing them should appear,
   and you should get a push notification.

From here it runs automatically every 15 minutes. The first run will treat
every currently-open matching issue as "already seen" (so you don't get a
backlog dumped on you) — only genuinely *new* issues filed after that first
run will trigger an alert issue.

## Tuning

- **Repo list**: edit the `REPOS` list at the top of
  `scripts/check_issues.py` — add or remove any project.
- **Comment threshold**: change `MAX_COMMENTS` in `watch.yml` (currently 3 —
  lower it to `0` if you only want completely untouched issues).
- **Frequency**: change the `cron` line in `watch.yml`. GitHub's minimum
  practical interval is about 5 minutes, though under load it can lag by a
  few extra minutes — this is a GitHub-side limitation, not something you can
  tune around.

## Why this approach

I can't run a persistent background process myself between our
conversations, so this repo *is* the "notify me immediately" mechanism —
GitHub's own infrastructure runs the check for you, for free, indefinitely.
