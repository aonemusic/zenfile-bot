# Deploy ZENFILE on Koyeb

This guide describes deploying the included Dockerfile from GitHub as a Telegram bot worker using polling. Koyeb's dashboard labels and worker capabilities can change; verify the available service types, instance sizes, prices, quotas, and scale behavior in your account before creating a service. Local tests have been run, but the project has not been built or deployed on Koyeb.

## 1. Publish the project to GitHub

1. Review the source and confirm the bot entry point and application modules are included.
2. Ensure `.env` and all real tokens are excluded. Keep `.env.example` free of credentials.
3. Create a GitHub repository and upload/push reviewed project files. One local workflow is:

   ```bash
   cd /home/ubuntu/zenfile-bot
   git init
   git add README.md Dockerfile render.yaml .env.example .gitignore .dockerignore requirements.txt docs
   git add bot.py config.py handlers converters utils  # include existing source files/directories
   git commit -m "Prepare ZENFILE deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
   git push -u origin main
   ```

   Adjust the source paths to match the actual reviewed tree. Use GitHub's current authentication flow rather than putting credentials in a remote URL.

## 2. Create a Docker deployment

1. In Koyeb, create an app/service from the GitHub repository and grant access only to the intended repository.
2. Choose the Dockerfile/container build option and set the build context to the repository root, where `Dockerfile` and `requirements.txt` are located. If asked for the Dockerfile path, use `Dockerfile`.
3. Run it as a **worker/background process** when the account and service type offer that option. Polling does not require an inbound HTTP route or exposed port. If the available service type requires a web service, check current provider guidance and configure the process appropriately; do not activate webhook mode unless the bot has a reachable webhook handler.
4. Configure environment variables in the Koyeb service settings:
   - `BOT_TOKEN`: required; store as a secret.
   - `ADMIN_ID`: optional single numeric Telegram user ID for admin commands; leave unset or use `0` if no admin is configured.
   - `MAX_INPUT_MB`: `18`.
   - `MAX_OUTPUT_MB`: `49`.
   - `MAX_CONCURRENT_JOBS`: `2`.
   - `JOB_TIMEOUT_SECONDS`: `300`.
   - `TEMP_DIR`: `/tmp/zenfile`.
   - `LOG_LEVEL`: `INFO`.
   - `BOT_MODE`: `polling`.
5. Select an instance and scaling/availability configuration suited to the conversion workload. Review limits and expected costs; FFmpeg, LibreOffice, and PDF/image rendering can use substantial memory, CPU, and temporary disk.
6. Deploy and inspect build/runtime logs. Resolve missing modules, build errors, or Telegram authentication errors before announcing the bot as available. Do not run two polling deployments against the same token.

## 3. Create the Telegram bot

1. In Telegram, use the verified `@BotFather` account and `/newbot` to create a bot.
2. Store the generated token only in the platform's secret environment-variable facility as `BOT_TOKEN`. Never commit it. Revoke and replace a leaked token through BotFather.
3. If using admin-only commands, set `ADMIN_ID` to one verified numeric Telegram user ID. The current configuration does not accept usernames or multiple IDs in that setting.

## Polling and webhook notes

Polling is the default. Webhook mode requires `BOT_MODE=webhook`, a public HTTPS `WEBHOOK_URL`, a reachable listener on `PORT`, correct routing for `WEBHOOK_PATH`, and a strong `WEBHOOK_SECRET`. Confirm the implementation and Koyeb service type support it before enabling. Do not activate both polling and webhook for one token. The Render Blueprint and this guide's default setup use polling.

## Reliability, files, and cost

- Telegram's standard Bot API allows downloads around 20 MB and uploads around 50 MB in the usual bot flow. ZENFILE's defaults are 18 MB input and 49 MB output. Confirm limits for the exact Bot API path.
- Temporary conversion files use local container storage and should be removed after processing. Local storage, sessions, and in-memory runtime statistics can disappear during restarts, redeploys, or instance replacement.
- Free tiers can sleep or scale to zero and do not promise a continuously available process. Update handling may pause or be delayed during downtime. Check current Koyeb plan behavior, limits, and quotas rather than assuming 24/7 availability.
- Ensure the selected instance can support the workload. Limit job concurrency and duration, clean temporary files, and review logs without recording tokens or user file contents.
- The presence of FFmpeg, LibreOffice, Poppler, or a Python library in the image does not prove that a specific format route is implemented or available.
