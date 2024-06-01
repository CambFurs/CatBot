#!/usr/bin/env python3
import tomllib
import datetime
import httpx
import arrow
import ics
from dataclasses import dataclass
from telegram.constants import ChatMemberStatus, ParseMode
from telegram import Update, Bot
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

async def get_admins(bot:Bot):
    chat_members = await bot.get_chat_administrators(CONFIG.main_group_id)
    return {chat_member.user.id for chat_member in chat_members}

async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, **kwargs) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, **kwargs)

async def respond_success(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    await respond(update, context, f"✅ {message}")

async def respond_error(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    await respond(update, context, f"❌ {message}")

async def alert(bot:Bot, text:str) -> None:
    await bot.send_message(chat_id=CONFIG.admin_group_id, text=text)

def ordinal(n:int) -> str:
    return f"{n}th" if n//10==1 else \
           f"{n}st" if n %10==1 else \
           f"{n}nd" if n %10==2 else \
           f"{n}rd" if n %10==3 else \
           f"{n}th"

# Commands #####################################################################

COMMANDS : list = []

async def cmd_meet_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/meet_dates: list upcomming meet dates"""
    if not(update.message.chat.type=="private" or \
           update.message.chat.id==CONFIG.main_group_id or\
           update.message.chat.id==CONFIG.admin_group_id):
        return
    async with httpx.AsyncClient() as client:
        response = await client.get("https://calendar.cambfurs.co.uk")
        text = response.raise_for_status().text
    events = list(ics.Calendar(text).events)
    events.sort(key=lambda e:e.begin)
    now = arrow.utcnow()
    upcomming_events = filter(lambda e:now < e.end, events)
    ret = ["⭐ __*Upcoming meet dates*__ ⭐"]
    for event in upcomming_events:
        local = event.begin.to('Europe/London')
        month = arrow.locales.EnglishLocale.month_names[local.month]
        day = ordinal(local.day)
        ret.append(f"➡️ {month} {day} {event.description if event.description is not None else ''}")
    await respond(update,context, "\n".join(ret), parse_mode=ParseMode.MARKDOWN_V2)
COMMANDS.append(cmd_meet_dates)


async def initialize(app: Application) -> None:
    # exceptions escaping from the initialize function result in a silent crash
    # it's therefore important to wrap everything in a try/catch
    try:
        # place for any one-time initialization to be done
        pass
    except:
        await alert(app.bot, "🆘 CatBot failed to start")
        raise
    else:
        await alert(app.bot, "🟢 CatBot started")

async def finalize(app: Application) -> None:
    await alert(app.bot, "🆘 CatBot stopped")

async def chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.chat_member.chat.id != CONFIG.waiting_room_group_id:
        return
    old = update.chat_member.old_chat_member
    new = update.chat_member.new_chat_member
    if old.status==ChatMemberStatus.LEFT and new.status==ChatMemberStatus.MEMBER:
        await alert(context.bot, f"🆕 {new.user.first_name} {new.user.last_name} (@{new.user.username})")
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
    app.add_handler(CommandHandler("meet_dates", cmd_meet_dates))
    app.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatJoinRequestHandler(join_request))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
