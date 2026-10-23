# Email Triage: MVP in a Few Hours

A small script that, for your mailboxes, **sorts** incoming mail into categories (Gmail labels),
**prepares a draft reply** for suitable emails, and finally builds a **digest** for the
responsible person. Nothing is ever sent to customers; everything stays as a draft awaiting approval.

No database: what has already been processed is recognised by the label `Triage/Hotovo` ("Done").

---

## What you need

- Python 3.10+
- A **Google Cloud project** with the Gmail API enabled and an OAuth client (the `credentials.json` file)
- An **Anthropic API key** (environment variable `ANTHROPIC_API_KEY`)

Roughly 1-3 hours in total; most of the time goes into the one-off OAuth setup in Google Cloud.

---

## Step 1: Google Cloud / Gmail API (~30-45 min)

1. Go to https://console.cloud.google.com/ and create a project (e.g. "email-triage").
2. **APIs & Services → Library** → search for **Gmail API** → **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - choose type **External**, fill in a name and contact email,
   - in the **Test users** section add both email addresses you will process
     (while the app is in "Testing" mode this is enough and you do not need to go through Google verification).
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - application type **Desktop app**,
   - download the JSON and save it next to the script as **`credentials.json`**.

> One `credentials.json` (one OAuth client) is enough for both mailboxes. Sign-in is done
> separately for each one and saved to its own `token_*.json`.

## Step 2: Anthropic API key (~5 min)

1. Create an API key at https://console.anthropic.com/.
2. Set it in your environment:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```
   (To make it permanent, add it to `~/.zshrc` / `~/.bashrc`.)

## Step 3: Installation (~5 min)

```bash
cd email-triage
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Step 4: Edit `config.py`

- In `ACCOUNTS`, set the mailbox names and `digest_to` (where the digest should be sent).
- Go through `CATEGORIES`: rename or add categories and adjust their descriptions.
- For each category choose a template: `None` = digest only, text = the model writes a draft.
- `DIGEST_MODE`: `"draft"` (safe, recommended to start with) / `"send"` / `"file"`.

## Step 5: First run

```bash
python3 triage.py
```

On the first run a browser opens for each mailbox. Sign in with **the correct account**
and grant access. The token is saved, so the browser will not open next time.

> Tip for safe testing: temporarily set `LOOKBACK_DAYS = 1` and `MAX_PER_ACCOUNT = 5`
> in `config.py`, so you first try it on a few emails and check the labels and drafts
> before running it on everything.

---

## Step 6: Automatic runs (scheduler)

**macOS / Linux (cron):** run it e.g. every hour:

```bash
crontab -e
# every hour; adjust the absolute paths:
0 * * * * cd /path/to/email-triage && ./.venv/bin/python triage.py >> triage.log 2>&1
```

If you want a "digest once a week", you have two options:
- let the triage run often (e.g. daily) and generate the digest only on Mondays, which just
  means running cron once a week, or
- triage continuously (labels and drafts appear immediately) and handle `DIGEST_MODE` separately.

To start with, the simplest option is to run the whole script **once a day** in the morning.

---

## Costs (estimate)

At 10-100 emails per day, model costs are negligible.
Classification runs on Haiku 4.5 (~$1 / million input tokens), drafts on Sonnet 5.
Even at 100 emails/day we are talking about a few to tens of Czech crowns per month.
Exact prices: https://platform.claude.com/docs/en/about-claude/pricing

---

## How to scale it later

- **More mailboxes:** add an entry to `ACCOUNTS`; no new `credentials.json` is needed.
- **Real time instead of cron:** Gmail push notifications via Google Pub/Sub.
- **Persistent state / statistics:** a small database (SQLite) instead of the `Triage/Hotovo` label.
- **Better drafts:** refine the instructions in `CATEGORIES[...]["sablona"]` or move to
  a higher-quality model. Category definitions and templates stay unchanged.

---

## Security

- **Never upload** `credentials.json` and `token_*.json` (they grant access to the mailbox).
  Add them to `.gitignore`.
- Keep `ANTHROPIC_API_KEY` in the environment, not in the code.
- The script deliberately **does not send** replies to customers; it only prepares drafts.