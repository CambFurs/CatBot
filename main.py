#!/usr/bin/env python3
import tomllib
import datetime
from dataclasses import dataclass
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, ChatJoinRequestHandler

# Configuration ################################################################

@dataclass(slots=True)
class Config:
    bot_token: str
    main_group_id: int
    admin_group_id: int
    waiting_room_group_id: int
    def __init__(self,filepath):
        with open(filepath,"rb") as file:
            cfg = tomllib.load(file)
        self.bot_token    = cfg['bot_token']
        self.main_group_id = cfg['main_group_id']
        self.admin_group_id = cfg['admin_group_id']
        self.waiting_room_group_id = cfg['waiting_room_group_id']

CONFIG = Config("config.toml")

# Utilities ####################################################################

async def get_admins(bot,group_id=CONFIG.main_group_id):
    chat_members = await bot.get_chat_administrators(CONFIG.main_group_id)
    return {chat_member.user.id for chat_member in chat_members}

async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def respond_success(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    await respond(update, context, f"✅ {message}")

async def respond_error(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    await respond(update, context, f"❌ {message}")

# Commands #####################################################################

COMMANDS = []


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start: prints help message"""
    command_docs = '\n'.join([cmd.__doc__ for cmd in COMMANDS])
    await respond(update, context, "Hewwo! I'm Catbot! Here's what I can do:\n"+command_docs)
COMMANDS.append(cmd_start)


async def cmd_say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/say: puts replied message into the main chat"""

    if not( update.message.chat.type=="private" or update.message.chat.id==CONFIG.admin_group_id):
        return

    admin_set = await get_admins(context.bot)
    if update.message.from_user.id not in admin_set:
        await respond_error(update,context,f"Only admins may use this command")
        return

    if update.message.reply_to_message==None:
        print(update.message)
        await respond_error(update,context,"Please respond to the message you wish to send")
        return

    text = update.message.reply_to_message.text
    message = await context.bot.send_message(chat_id=CONFIG.main_group_id, text=text)
    await respond_success(update,context,f"Sent! id: {message.id}")
COMMANDS.append(cmd_say)

APPROVED_JOIN_REQUESTS = {}

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/approve @username: send personalized invite link to user"""

    if not( update.message.chat.id==CONFIG.waiting_room_group_id ):
        return

    if update.message.from_user.username!="GroupAnonymousBot":
        await respond_error(update,context,"Only admins may use this command")
        return

    user = list(update.message.parse_entities(types=['mention']).values())
    if len(user)!=1:
        await respond_error(update,context,"Must specify a single user to approve")
        return
    user = user[0]

    global APPROVED_JOIN_REQUESTS
    if user in APPROVED_JOIN_REQUESTS:
        print("TODO: revoke previous link for user")

    minutes_valid = 5
    invite_link = await context.bot.create_chat_invite_link(
        CONFIG.main_group_id,
        creates_join_request=True,
        expire_date=datetime.datetime.now(datetime.UTC)+datetime.timedelta(minutes=minutes_valid))
    print(invite_link)
    APPROVED_JOIN_REQUESTS[user] = invite_link.invite_link

    await respond(update, context, f"Here's your invite link to the CambFurs group! This link is only valid for {user} for {minutes_valid} minutes\n\n{invite_link.invite_link}")
COMMANDS.append(cmd_approve)


async def join_request(update:Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def decline():
        await context.bot.decline_chat_join_request(update.chat_join_request.chat.id, update.chat_join_request.from_user.id)

    if update.chat_join_request.chat.id!=CONFIG.main_group_id:
        print("Received join request for chat other than main group. Declined")
        await decline()
        return

    username = f"@{update.chat_join_request.from_user.username}";
    print(username)

    global APPROVED_JOIN_REQUESTS
    if not( username in APPROVED_JOIN_REQUESTS and APPROVED_JOIN_REQUESTS[username] != update.chat_join_request.invite_link ):
        print("User not in approved join requests. Declined")
        await decline()
        return

    print(f"{username} successfully joined")
    del APPROVED_JOIN_REQUESTS[username]
    await context.bot.approve_chat_join_request(update.chat_join_request.chat.id, update.chat_join_request.from_user.id)
    await context.bot.revoke_chat_invite_link(update.chat_join_request.chat.id, update.chat_join_request.invite_link)
    await context.bot.send_message(CONFIG.main_group_id, text=f"Everyone welcome {username} to the chat!")
    print(update)

# Main #########################################################################

def main() -> None:
    app = ApplicationBuilder().token(CONFIG.bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("say",   cmd_say))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(ChatJoinRequestHandler(join_request))
    app.run_polling()

if __name__ == '__main__':
    main()

