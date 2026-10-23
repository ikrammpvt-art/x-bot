# 🤖 X (Twitter) Account Monitoring & Grok-Style Telegram Bot

An automatic X (Twitter) account monitoring bot that checks accounts every 15 minutes, extracts newly published posts, and delivers them directly to your Telegram chat or channel with **Grok-style explanations in simple English and deep context**.

Built specifically to use **100% FREE services** so you don't need to pay the expensive $100–$200/month X API fees or expensive AI subscriptions.

---

## 🌟 Key Features

- **Monitors 10+ X Accounts**: Configured in a clean text file (`accounts.txt`).
- **15-Minute Polling Schedule**: Checks every 15 minutes with human-like jitter between accounts to stay safe and polite.
- **Grok-Style AI Explanations**: Breaks down cryptic tweets, sarcasm, tech/crypto jargon, memes, and world events into:
  - 💡 **Plain English** translation.
  - 🔍 **Context & Background** (the backstory, news, or drama behind the tweet).
  - 🎯 **Why It Matters** (the takeaways and implications).
- **100% Free Stack**:
  - **Twitter Scraping**: Powered by `twikit` using session cookies (bypasses official API fees).
  - **AI Explanation**: Free Google Gemini 2.5 Flash (15 RPM / 1,500 RPD free forever) or Groq / Ollama.
  - **Telegram Bot**: 100% free via Telegram Bot API.
- **Smart Deduplication & Baselines**: SQLite database stores seen tweet IDs. On first launch, existing tweets are seeded so you never get flooded with old history.
- **Diagnostic Tool**: Includes `test_setup.py` to verify your tokens and credentials in 1 click.

---

## 🚀 Quick Start Guide

### 1. Requirements & Virtual Environment

From this folder (`/Users/ekramqureshi/Downloads/XBOT`), a virtual environment is already prepared. If you ever need to recreate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 2. Free Service Setup (Takes ~3 minutes)

Open your `.env` file and configure these 3 sections:

#### A. Telegram Bot (100% Free)
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, choose a name and username.
3. Copy the **HTTP API token** and paste it into `.env` as `TELEGRAM_BOT_TOKEN`.
4. To find your Chat ID:
   - Search for `@userinfobot` or `@raw_data_bot` on Telegram and click **Start**.
   - Copy your numeric ID and paste it into `.env` as `TELEGRAM_CHAT_ID`.
   - *(If sending to a Telegram channel: Add your bot as an Admin in the channel, and set `TELEGRAM_CHAT_ID=@your_channel_username`)*.

#### B. Free AI Engine (Grok Alternatives)

| Provider | Cost | Daily Limit | Link |
| :--- | :--- | :--- | :--- |
| **Google Gemini (Recommended)** | **FREE** (No Credit Card) | 1,500 requests/day | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| **Groq (Llama 3.3 70B)** | **FREE** | 14,400 requests/day | [Groq Console](https://console.groq.com/keys) |
| **Ollama** | **FREE** | Unlimited (Local Mac) | [Ollama.com](https://ollama.com) |

**For Google Gemini (Recommended):**
1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey) and click **"Create API Key"**.
2. Paste the key in `.env`:
   ```env
   AI_PROVIDER=gemini
   GEMINI_API_KEY=your_gemini_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ```

#### C. Twitter Authentication (100% Free — No $100/mo API)
To fetch timelines without paying X's expensive developer tier, grab your session cookies from any free secondary/burner Twitter account:
1. Log into X in Google Chrome, Brave, or Firefox.
2. Press `F12` (or Right-Click -> **Inspect**) to open Developer Tools.
3. Click the **Application** (or **Storage**) tab -> expand **Cookies** -> click `https://x.com`.
4. Copy the values of these two cookies:
   - `auth_token`
   - `ct0`
5. Paste them into `.env`:
   ```env
   TWITTER_AUTH_TOKEN=your_auth_token_value_here
   TWITTER_CT0=your_ct0_value_here
   ```

---

### 3. Customize Monitored Accounts

Edit `accounts.txt` to add your desired 10 accounts (one per line, without the `@` symbol):

```txt
elonmusk
OpenAI
sama
GoogleDeepMind
demishassabis
AnthropicAI
satyanadella
karpathy
ylecun
grok
```

---

### 4. Test Your Setup

Before running 24/7, run the diagnostic test script:

```bash
source .venv/bin/activate
python test_setup.py
```

It will:
1. Send a test message to your Telegram chat.
2. Generate a Grok-style AI breakdown on a sample tweet.
3. Test Twitter authentication and fetch a sample tweet.

---

### 5. Run the Monitor

Once all tests pass, start the monitoring bot:

```bash
source .venv/bin/activate
python main.py
```

#### Running in Background (24/7 on Mac/Linux)
To keep the bot running after closing the terminal:

```bash
# Using nohup:
nohup .venv/bin/python main.py > storage/bot.log 2>&1 &

# Check logs:
tail -f storage/bot.log

# To stop:
pkill -f "python main.py"
```

---

## 📁 Project Structure

```
XBOT/
├── .env.example          # Template with all configuration options
├── .env                  # Your private credentials (tokens, cookies, keys)
├── accounts.txt          # List of 10 X accounts to monitor
├── requirements.txt      # Python dependencies
├── config.py             # Loads and validates environment variables
├── database.py           # SQLite database for seen tweets & deduplication
├── twitter_fetcher.py    # Twikit client with session cookie auth & safe delays
├── ai_explainer.py       # Grok-like explanation engine (Gemini, Groq, Ollama)
├── telegram_notifier.py  # Telegram message formatting and delivery
├── test_setup.py         # 1-click diagnostic tool for Telegram, AI, and Twitter
└── main.py               # Main 15-minute polling loop
```

---

## 🛡️ Anti-Ban & Rate-Limit Protections

- **Polite Jitter**: Adds randomized 2.5–4.5 second delays between account requests.
- **SQLite ID Caching**: Caches user IDs so screen name resolution only happens once per account.
- **Session Persistence**: Saves your session in `storage/cookies.json` to prevent repetitive fresh logins.
- **Smart Baseline Seeding**: On first run, it records current tweets as already seen so you aren't spammed with past history.
