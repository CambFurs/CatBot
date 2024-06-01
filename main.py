#!/usr/bin/env python3
import tomllib
import datetime
from dataclasses import dataclass
from telegram.constants import ChatMemberStatus
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CommandHandler, ChatJoinRequestHandler, ChatMemberHandler

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

async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, **kwargs) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, **kwargs)

async def respond_success(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    await respond(update, context, f"✅ {message}")

async def respond_error(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    await respond(update, context, f"❌ {message}")

# Commands #####################################################################

COMMANDS : list[str] = []

async def initialize(app: Application) -> None:
    await app.bot.send_message(chat_id=CONFIG.admin_group_id, text="🟢 CatBot started")

async def finalize(app: Application) -> None:
    await app.bot.send_message(chat_id=CONFIG.admin_group_id, text="🆘 CatBot stopped")

async def chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.chat_member.chat.id != CONFIG.waiting_room_group_id:
        return
    old = update.chat_member.old_chat_member
    new = update.chat_member.new_chat_member
    if old.status==ChatMemberStatus.LEFT and new.status==ChatMemberStatus.MEMBER:
        print("join event")
        await context.bot.send_message(chat_id=CONFIG.admin_group_id, text=
            f"🆕 {new.user.first_name} {new.user.last_name} (@{new.user.username})")
        await context.bot.send_message(chat_id=CONFIG.waiting_room_group_id, text=
            f"Hi {new.user.first_name}! An admin will be with you shortly to get you in the main chat.\n\nPlease read the rules at rules.cambfurs.co.uk and let us know and whether you agree.")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start: initiate a CatBot conversation"""
    if update.message.chat.type!="private":
        return
    admin_set = await get_admins(context.bot)
    if update.message.from_user.id not in admin_set:
        await respond(update, context, "Meow!")
        return
    command_docs = '\n'.join([cmd.__doc__ for cmd in COMMANDS])
    await respond(update, context, f"Hewwo! I'm Catbot! These are the things I can do:\n{command_docs}", protect_content=True)
COMMANDS.append(cmd_start)


async def cmd_say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/say: puts replied message into the main chat"""

    if not( update.message.chat.type=="private" or update.message.chat.id==CONFIG.admin_group_id):
        return

    admin_set = await get_admins(context.bot)
    if update.message.from_user.id not in admin_set:
        await respond_error(update,context,"Only admins may use this command")
        return

    if update.message.reply_to_message is None:
        print(update.message)
        await respond_error(update,context,"Please respond to the message you wish to send")
        return

    text = update.message.reply_to_message.text
    message = await context.bot.send_message(chat_id=CONFIG.main_group_id, text=text)
    await respond_success(update,context,f"Sent! id: {message.id}")
COMMANDS.append(cmd_say)

APPROVED_JOIN_REQUESTS = {}

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/approve @username: create invite link for user"""

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
        await context.bot.revoke_chat_invite_link(CONFIG.main_group_id, APPROVED_JOIN_REQUESTS[user])
        del APPROVED_JOIN_REQUESTS[user]

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
    user_id = update.chat_join_request.from_user.id
    chat_id = update.chat_join_request.chat.id

    if chat_id!=CONFIG.main_group_id:
        print("Received join request for chat other than main group. Declined")
        await context.bot.decline_chat_join_request(chat_id, user_id)
        return

    username = f"@{update.chat_join_request.from_user.username}"

    global APPROVED_JOIN_REQUESTS
    if not( username in APPROVED_JOIN_REQUESTS and APPROVED_JOIN_REQUESTS[username] != update.chat_join_request.invite_link ):
        print(f"{username} not in approved join requests. Declined")
        await context.bot.decline_chat_join_request(chat_id, user_id)
        return

    print(f"{username} successfully joined")
    del APPROVED_JOIN_REQUESTS[username]
    await context.bot.approve_chat_join_request(chat_id, user_id)
    await context.bot.revoke_chat_invite_link(chat_id, update.chat_join_request.invite_link)
    await context.bot.send_message(CONFIG.main_group_id, text=f"Everyone welcome {username} to the chat!")
    await context.bot.ban_chat_member(CONFIG.waiting_room_group_id, user_id)
    print(update)

# Main #########################################################################

def main() -> None:
    app = ApplicationBuilder()\
        .token(CONFIG.bot_token)\
        .post_init(initialize)\
        .post_stop(finalize)\
        .build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("say",   cmd_say))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatJoinRequestHandler(join_request))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
