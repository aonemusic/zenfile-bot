# Deploy ZENFILE on Render

The included [`render.yaml`](../render.yaml) describes a Docker Web Service using Telegram webhooks. It binds to Render's injected `PORT`; the app uses `RENDER_EXTERNAL_URL` as the webhook base URL if `WEBHOOK_URL` is unset. Local unit/conversion tests have been run, but the image and webhook deployment must still be validated in Render.

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
2. Create or update the Render service as a Docker **Web Service** using `Dockerfile`. The included Blueprint declares `type: web` and `plan: free` to match the intended setup; confirm the current price and free-tier limits in your account.
3. Add `BOT_TOKEN` and `WEBHOOK_SECRET` as private environment variables. `WEBHOOK_URL` may be left unset because the app uses Render's `RENDER_EXTERNAL_URL`; set `WEBHOOK_PATH=zenfile-webhook` if it is not already configured.
4. Set `BOT_MODE=webhook`. Keep Render's injected `PORT` unchanged; the app binds the Tornado webhook server to it. Set `ADMIN_ID` only to one verified numeric Telegram user ID if admin commands are needed.
5. Review the defaults: `MAX_INPUT_MB=18`, `MAX_OUTPUT_MB=49`, `MAX_CONCURRENT_JOBS=2`, and `JOB_TIMEOUT_SECONDS=300`.
6. Deploy and inspect build and application logs. Do not run polling and webhook delivery at once for the same token.

## 3. Set up BotFather and an admin ID

1. In Telegram, open the verified `@BotFather` account, create the bot with `/newbot`, and follow its prompts.
2. Copy the generated token directly into Render's `BOT_TOKEN` secret field. Never paste it into source code, a GitHub issue, or public logs. If exposed, revoke and replace it using BotFather.
3. For `ADMIN_ID`, obtain the intended administrator's numeric Telegram user ID using a trusted method and verify it before granting privileges. Do not use a username as an authorization identifier.
4. Publish a suitable usage/privacy description before inviting users to send files.

## Polling versus webhook

This Web Service must use `BOT_MODE=webhook`. It binds to Render's `PORT` and uses `WEBHOOK_URL` or `RENDER_EXTERNAL_URL` plus `WEBHOOK_PATH` to register the webhook with Telegram. Set a strong `WEBHOOK_SECRET`. Do not run a second polling process for the same bot token. Render's free Web Services may sleep when idle, so webhook delivery can experience cold-start delays; check the current plan behavior and costs before relying on uninterrupted availability.

## Operations and caveats

- The standard Telegram Bot API generally limits bot downloads to about 20 MB and uploads to about 50 MB; app defaults are 18 MB and 49 MB. Confirm limits for the exact Bot API path in use.
- Temporary files use local ephemeral storage. They may disappear after restart, replacement, or redeploy; do not use this storage as an archive.
- Admin counts, active jobs, sessions, and runtime statistics are in memory and reset on process restart. No database or durable analytics is configured.
- A long-running worker consumes resources and may be billable. Free tiers can sleep, pause, or scale to zero and do not guarantee uninterrupted 24/7 availability. Check current Render plan behavior and quotas in the dashboard.
- Conversion availability depends on implemented handlers and installed codec/filter support. A successful image build does not prove every format route works.
- Review logs/resource usage, limit conversion concurrency and runtime, and do not record tokens or user file contents.
