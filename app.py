"""
Gradio web interface and 24/7 runner for Hugging Face Spaces.
Runs XBot in the background while displaying a real-time status dashboard.
"""
import os
import sys
import asyncio
import threading
from datetime import datetime, timezone, timedelta

# Apply community patch before importing twikit
try:
    import patch_twikit
    patch_twikit.apply_patch()
except Exception as e:
    print(f"Patch notice: {e}")

import gradio as gr
import database
import config
from main import XBotMonitor, now_ist, format_clock_ist

# Global monitor reference
monitor_instance = None
bot_thread = None
IST = timezone(timedelta(hours=5, minutes=30))


def run_bot_in_background():
    """Runs the asyncio monitoring loop in a dedicated background thread."""
    global monitor_instance
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    monitor_instance = XBotMonitor()
    try:
        loop.run_until_complete(monitor_instance.start())
    except Exception as e:
        print(f"Bot background loop encountered error: {e}")


def start_service():
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=run_bot_in_background, daemon=True)
        bot_thread.start()
        print("XBot background monitoring thread launched.")


# Start bot automatically when Hugging Face Space starts
start_service()


def get_dashboard_status():
    """Returns real-time status information for the Gradio dashboard."""
    try:
        accounts = database.get_all_monitored_accounts()
    except Exception:
        accounts = []

    curr_time = format_clock_ist(now_ist())
    status_text = (
        f"### 🟢 System Status: **ACTIVE & MONITORING 24/7**\n\n"
        f"- **Current Time (IST):** `{curr_time} IST`\n"
        f"- **Check Interval:** Every `{config.CHECK_INTERVAL_MINUTES} minutes`\n"
        f"- **Active Monitored Accounts:** `{len(accounts)}`\n"
        f"- **Telegram Delivery:** Chat ID `{config.TELEGRAM_CHAT_ID}`\n"
        f"- **AI Analysis Engine:** Google Gemini (`{config.GEMINI_MODEL}`)\n\n"
        f"---\n"
        f"#### 📋 Monitored Handles ({len(accounts)}):\n"
        f"{', '.join(['@' + a for a in accounts])}"
    )
    return status_text


def trigger_manual_scan():
    """Triggers an on-demand scan across all monitored accounts."""
    if monitor_instance is not None:
        try:
            future = asyncio.run_coroutine_threadsafe(
                monitor_instance.run_cycle(manual_trigger=True),
                monitor_instance._scan_lock._loop if hasattr(monitor_instance, "_scan_lock") else asyncio.get_event_loop()
            )
            return "⏳ Manual scan triggered! Checking accounts and compiling roundup in Telegram..."
        except Exception as e:
            return f"⚠️ Triggered scan with notice: {e}"
    return "Bot is initializing. Please wait a moment."


# Gradio UI Design
with gr.Blocks(title="XBot Geopolitical & Financial Intelligence") as demo:
    gr.Markdown("# 🌐 XBot 24/7 Intelligence Monitor")
    gr.Markdown("Autonomous real-time tracking of breaking news, OSINT, defense, and macro accounts.")

    with gr.Row():
        with gr.Column(scale=3):
            status_display = gr.Markdown(value=get_dashboard_status)
        with gr.Column(scale=1):
            refresh_btn = gr.Button("🔄 Refresh Status", variant="secondary")
            scan_btn = gr.Button("⚡ Trigger Immediate Scan", variant="primary")
            action_result = gr.Textbox(label="Action Log", interactive=False)

    refresh_btn.click(fn=get_dashboard_status, outputs=status_display)
    scan_btn.click(fn=trigger_manual_scan, outputs=action_result)


if __name__ == "__main__":
    start_service()
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", 7860)), theme=gr.themes.Soft())

