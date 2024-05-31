#!/usr/bin/env python3
import tomllib
from dataclasses import dataclass
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Configuration ################################################################

@dataclass(slots=True)
class Config:
    bot_token: str
    main_chat_id: int
    admin_chat_id: int
    waiting_room_chat_id: int
    def __init__(self,filepath):
        with open(filepath,"rb") as file:
            cfg = tomllib.load(file)
        self.bot_token    = cfg['bot_token']
        self.main_chat_id = cfg['main_chat_id']
        self.admin_chat_id = cfg['admin_chat_id']
        self.waiting_room_chat_id = cfg['waiting_room_chat_id']

CONFIG = Config("config.toml")

# Utilities ####################################################################

async def get_admins(bot):
    chat_members = await bot.get_chat_administrators(CONFIG.main_chat_id)
    return {chat_member.user.id for chat_member in chat_members}

async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def respond_success(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    await respond(update, context, f"✅ {message}")

async def respond_error(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    await respond(update, context, f"❌ {message}")

# Commands #####################################################################

COMMANDS = []

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start prints help message"""
    command_docs = '\n'.join([cmd.__doc__ for cmd in COMMANDS])
    await respond(update, context, "Hewwo! I'm Catbot! Here's what I can do:\n"+command_docs)
COMMANDS.append(cmd_start)

async def cmd_say(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/say puts replied message into the main chat"""
    admin_set = await get_admins(context.bot)
    if update.message.from_user.id not in admin_set:
        await respond_error(update,context,f"Only admins may use this command");
    elif update.message.reply_to_message==None:
        await respond_error(update,context,"Please respond to the message you wish to send");
    else:
        text = update.message.reply_to_message.text
        message = await context.bot.send_message(chat_id=CONFIG.main_chat_id, text=text)
        await respond_success(update,context,f"Sent! id: {message.id}")
COMMANDS.append(cmd_say)

# Main #########################################################################

def main() -> None:
    app = ApplicationBuilder().token(CONFIG.bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("say", cmd_say))
    app.run_polling()

if __name__ == '__main__':
    main()

