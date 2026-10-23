# 🚀 24/7 Cloud Deployment Guide (100% Free Forever)

This guide shows you how to host XBot 24/7 in the cloud so it runs **even when your Mac is turned off or asleep**, without paying any subscriptions or knowing how to code.

---

## 🌟 Method 1: GitHub Actions (Easiest — 2 Minutes)

GitHub Actions will run your bot in the cloud every 15 minutes, completely free.

### Step 1: Create a Private GitHub Repository
1. Go to [github.com/new](https://github.com/new).
2. Name the repository: `xbot`
3. Select **Private** (to keep your settings safe).
4. Click **Create repository**.

### Step 2: Push your code from your Mac
In your Mac terminal (or simply tell Antigravity your repository URL and it will push for you):
```bash
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/xbot.git
git branch -M main
git push -u origin main
```

### Step 3: Add your 5 Secret Keys to GitHub
In your GitHub repository:
1. Click **Settings** (top right tab) → **Secrets and variables** → **Actions**.
2. Click **New repository secret** and add these 5 keys (copy the values from your local `.env`):

| Secret Name | Value |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Your Telegram Bot Token (`8617470174:...`) |
| `TELEGRAM_CHAT_ID` | Your Telegram Chat ID (`6847679250`) |
| `TWITTER_AUTH_TOKEN` | Your Twitter `auth_token` |
| `TWITTER_CT0` | Your Twitter `ct0` |
| `GEMINI_API_KEY` | Your Google Gemini API Key |

🎉 **Done!** GitHub Actions will now automatically wake up every 15 minutes, fetch tweets, generate your intelligence digest, and send it to your Telegram bot.

---

## ⚡ Method 2: Hugging Face Spaces (Runs Live Telegram Listener Too)

If you also want the interactive Telegram commands (`/add`, `/remove`, `/roundup`, `/status`) running live 24/7 in the cloud:

### Step 1: Create a Free Docker Space
1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Space Name: `xbot`
3. Space SDK: Select **Docker** → **Blank**.
4. Visibility: Select **Private**.
5. Click **Create Space**.

### Step 2: Add Secrets
In your Space:
1. Click **Settings** → **Variables and secrets**.
2. Click **New secret** and add:
   * `TELEGRAM_BOT_TOKEN`
   * `TELEGRAM_CHAT_ID`
   * `TWITTER_AUTH_TOKEN`
   * `TWITTER_CT0`
   * `GEMINI_API_KEY`

### Step 3: Connect your GitHub Repo or Push Code
Follow the quick commands provided by Hugging Face to push your repository, or link your GitHub repository with one click.
Hugging Face will automatically build your `Dockerfile` and keep your bot online 24/7/365 for **$0**.
