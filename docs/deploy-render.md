# Deploy ZENFILE on Render

The included [`render.yaml`](../render.yaml) describes a Docker background worker intended for one Telegram bot process using polling. It does not create a webhook endpoint. Local unit/conversion tests have been run, but the project has not been built or deployed on Render; review the current implementation and provider settings before release.

## 1. Prepare the GitHub repository

1. Review the project files in `/home/ubuntu/zenfile-bot` and confirm the bot entry point and application modules are included.
2. Ensure `.env` and all real credentials are excluded. Commit `.env.example` only with blank/placeholder values.
3. Create a GitHub repository and push the project, or upload reviewed files through GitHub's interface. A local Git workflow is:

   ```bash
   cd /home/ubuntu/zenfile-bot
   git init
   git add README.md Dockerfile render.yaml .env.example .gitignore .dockerignore requirements.txt docs
   git add bot.py config.py handlers converters utils  # include existing source directories/files
   git commit -m "Prepare ZENFILE deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
   git push -u origin main
   ```

   Adjust the `git add` paths to match the actual reviewed source tree. If Git prompts for authentication, use GitHub's current recommended flow; do not embed a password or token in the remote URL.

## 2. Create the Render service

1. Sign in to Render and connect the GitHub account/repository containing ZENFILE.
2. Create a Blueprint deployment from the repository and review the proposed service. The Blueprint defines a Docker **worker** using `Dockerfile`.
3. The manifest sets `plan: starter` as an explicit worker configuration; it is not a free-tier promise. Review current Render prices, quotas, and availability before creating the service.
4. Add `BOT_TOKEN` as a secret environment variable in the service settings. Set `ADMIN_ID` to one verified numeric Telegram user ID if you want to allow that administrator's admin commands. The current configuration expects one ID, not a username or comma-separated list; omit the setting or use `0` for no configured admin.
5. Review the defaults: `MAX_INPUT_MB=18`, `MAX_OUTPUT_MB=49`, `MAX_CONCURRENT_JOBS=2`, and `JOB_TIMEOUT_SECONDS=300`. `BOT_MODE=polling` is explicit in the manifest.
6. Start/redeploy the service and inspect its logs. Do not run a second active polling service against the same bot token.

## 3. Set up BotFather and an admin ID

1. In Telegram, open the verified `@BotFather` account, create the bot with `/newbot`, and follow its prompts.
2. Copy the generated token directly into Render's `BOT_TOKEN` secret field. Never paste it into source code, a GitHub issue, or public logs. If exposed, revoke and replace it using BotFather.
3. For `ADMIN_ID`, obtain the intended administrator's numeric Telegram user ID using a trusted method and verify it before granting privileges. Do not use a username as an authorization identifier.
4. Publish a suitable usage/privacy description before inviting users to send files.

## Polling versus webhook

The included service is a polling worker. `BOT_MODE=polling` is the configured default. Webhook mode requires setting `BOT_MODE=webhook`, a public HTTPS `WEBHOOK_URL`, a reachable HTTP service on the configured `PORT` and `WEBHOOK_PATH`, and a strong `WEBHOOK_SECRET`. This Blueprint is a worker and does not provide public webhook ingress; do not merely set the URL here and assume a handler is reachable. Use only one update-delivery mode per token.

## Operations and caveats

- The standard Telegram Bot API generally limits bot downloads to about 20 MB and uploads to about 50 MB; app defaults are 18 MB and 49 MB. Confirm limits for the exact Bot API path in use.
- Temporary files use local ephemeral storage. They may disappear after restart, replacement, or redeploy; do not use this storage as an archive.
- Admin counts, active jobs, sessions, and runtime statistics are in memory and reset on process restart. No database or durable analytics is configured.
- A long-running worker consumes resources and may be billable. Free tiers can sleep, pause, or scale to zero and do not guarantee uninterrupted 24/7 availability. Check current Render plan behavior and quotas in the dashboard.
- Conversion availability depends on implemented handlers and installed codec/filter support. A successful image build does not prove every format route works.
- Review logs/resource usage, limit conversion concurrency and runtime, and do not record tokens or user file contents.
