import os
import random
import asyncio
import aiohttp
from datetime import datetime, timedelta
from bip_utils import Bip39MnemonicValidator, Bip39SeedGenerator, Bip44, Bip44Coins, Bip39Languages
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= CONFIG ==================
TELEGRAM_TOKEN = "8397343895:AAHj3ahA4yayTeJ2ugcrCxF7wF2_SS2RF-E"
YOUR_CHAT_ID = 6844620434
MNEMONIC_FILE = "generated_mnemonics.txt"
BAL_FILE = "ball.txt"
WORDLIST_FILE = "english.txt"
MAX_GENERATE = 10000

# ================= GLOBALS =================
bot_status = "Idle"
wordlist = []
active_chats = set()
last_start_time = {}
lock = asyncio.Lock()

# ================= HELPERS =================
def load_wordlist():
    global wordlist
    if not wordlist:
        with open(WORDLIST_FILE, "r", encoding="utf-8") as f:
            wordlist = [w.strip() for w in f if w.strip()]
    return wordlist

def generate_mnemonic(wordlist):
    while True:
        words = random.sample(wordlist, 12)
        mnemonic = " ".join(words)
        try:
            if Bip39MnemonicValidator(Bip39Languages.ENGLISH).Validate(mnemonic):
                return mnemonic
        except:
            continue

async def check_btc_balance(mnemonic):
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    bip44_masters = {
        "Legacy": Bip44.FromSeed(seed_bytes, Bip44Coins.BITCOIN),
    }
    balances = {}
    async with aiohttp.ClientSession() as session:
        for name, bip44 in bip44_masters.items():
            addr = bip44.Purpose().Coin().Account(0).Change(0).AddressIndex(0).PublicKey().ToAddress()
            url = f"https://blockchain.info/q/addressbalance/{addr}?confirmations=6"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        sat = int(await resp.text())
                        balances[name] = sat / 1e8
                    else:
                        balances[name] = 0.0
            except:
                balances[name] = 0.0
    total_btc = sum(balances.values())
    return total_btc, balances

async def send_to_me(context: ContextTypes.DEFAULT_TYPE, text: str):
    await context.bot.send_message(chat_id=YOUR_CHAT_ID, text=text)

# ================= COMMANDS =================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now = datetime.now()
    if chat_id in last_start_time and now - last_start_time[chat_id] < timedelta(seconds=10):
        return
    last_start_time[chat_id] = now

    if chat_id in active_chats:
        await update.message.reply_text("Bot already started ✅")
        return

    active_chats.add(chat_id)
    keyboard = [
        ["/generate n", "/check"],
        ["/startcheck", "/delete"],
        ["/status"]
    ]
    await update.message.reply_text(
        "Crypto Bot started!",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def generate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_status
    async with lock:
        bot_status = "Generating"
        try:
            n = int(context.args[0])
        except:
            await update.message.reply_text("Usage: /generate n")
            bot_status = "Idle"
            return

        if n > MAX_GENERATE:
            n = MAX_GENERATE

        wl = load_wordlist()
        mnemonics = [generate_mnemonic(wl) for _ in range(n)]

        with open(MNEMONIC_FILE, "a", encoding="utf-8") as f:
            for m in mnemonics:
                f.write(m + "\n")

        await update.message.reply_text(f"Generated {n} mnemonics.")
        bot_status = "Idle"

async def check_generated_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_status
    async with lock:
        bot_status = "Checking"
        if not os.path.exists(MNEMONIC_FILE):
            await update.message.reply_text("No mnemonics found.")
            bot_status = "Idle"
            return

        with open(MNEMONIC_FILE, "r", encoding="utf-8") as f:
            mnemonics = [line.strip() for line in f if line.strip()]

        for m in mnemonics:
            total_btc, _ = await check_btc_balance(m)
            if total_btc > 0:
                with open(BAL_FILE, "a", encoding="utf-8") as bf:
                    bf.write(m + "\n")
                await send_to_me(context, f"Balance found!\n{m}\nBTC: {total_btc}")
            await asyncio.sleep(0.3)

        await update.message.reply_text("Check complete.")
        bot_status = "Idle"

async def startcheck_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Continuous checking started.")
    await check_generated_cmd(update, context)

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for file in [MNEMONIC_FILE, BAL_FILE]:
        if os.path.exists(file):
            os.remove(file)
    await update.message.reply_text("Files deleted.")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Status: {bot_status}")

# ================= MAIN ==================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("generate", generate_cmd))
    app.add_handler(CommandHandler("check", check_generated_cmd))
    app.add_handler(CommandHandler("startcheck", startcheck_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    print("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()
