#!/usr/bin/env python3
from dataclasses import dataclass
import tomllib
import datetime
import arrow # arrow is used by ICS instead of datetime
import ics
import asyncio # used by telegram
import httpx # used by telegram
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
ICAL_URL = 'https://calendar.cambfurs.co.uk'
LOCAL_TZ = 'Europe/London'

# Utilities ####################################################################

async def get_admin_set(bot:Bot) -> set[int]:
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

async def get_upcoming_meet_events(ical_url:str=ICAL_URL, local_tz:str=LOCAL_TZ, now=arrow.utcnow()) -> list[ics.Event]:
    """returns sorted list of events that have not yet ended"""
    async with httpx.AsyncClient() as client:
        response = await client.get(ical_url)
        text = response.raise_for_status().text
    events = list(ics.Calendar(text).events)
    events.sort(key=lambda e:e.begin)
    ret = []
    for event in filter(lambda e:now < e.end, events):
        event.begin = event.begin.to(local_tz)
        event.end   = event.end.to(local_tz)
        ret.append(event)
    return ret

# Commands #####################################################################

COMMANDS = []

async def cmd_meet_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/meet_dates: list upcoming meet dates"""
    if not(update.message.chat.type=="private" or \
           update.message.chat.id==CONFIG.main_group_id or \
           update.message.chat.id==CONFIG.admin_group_id):
        return
    upcoming_events = await get_upcoming_meet_events()
    ret = ["⭐ __*Upcoming meet dates*__ ⭐"]
    for event in upcoming_events:
        month = arrow.locales.EnglishLocale.month_names[event.begin.month]
        day = ordinal(event.begin.day)
        maybe_description = ' '+event.description if event.description is not None else ''
        ret.append(f"➡️ {month} {day}{maybe_description}")
    await respond(update,context, "\n".join(ret), parse_mode=ParseMode.MARKDOWN_V2)
COMMANDS.append(cmd_meet_dates)

def choose_meet_announcement(now: arrow.Arrow, next_events: list[ics.Event]) -> str:
    if not next_events:
        return ""
    next_event = next_events[0]

    # round current time to nearest hour, this accounts for all kinds of imprecision
    now = now.shift(minutes=30).floor('hours')

    if now==next_event.begin:
        return "started"
    elif now.hour == 10 and now.shift(days=1).date() == next_event.begin.date():
        return "tomorrow"
    elif now.hour == 10 and now.shift(days=7).date() == next_event.begin.date():
        return "next_week"
    else:
        return ""

async def hourly_callback(bot, now, next_events):
    match choose_meet_announcement(now, next_events):
        case "started":
            await bot.send_message(chat_id=CONFIG.main_group_id, text="meet has started!")
        case "tomorrow":
            await bot.send_message(chat_id=CONFIG.main_group_id, text="meet is tomorrow!")
        case "next_week":
            await bot.send_message(chat_id=CONFIG.main_group_id, text="meet is next week!")
        case "":
            pass

async def periodic_callback_generator(bot: Bot):
    while True:
        now = arrow.utcnow()
        await asyncio.sleep( (now.ceil('hours')-now).total_seconds() )
        now = arrow.utcnow()
        next_events = await get_upcoming_meet_events(now=now)
        await hourly_callback(bot, now, next_events)

def test_choose_meet_announcement():
    event_begin = arrow.Arrow(2024, 10, 25, 12, 0, 0, tzinfo=LOCAL_TZ)
    event = ics.Event(begin=event_begin, end=event_begin.shift(hours=8), description="test event")

    now_meet_start    = event_begin.clone().shift(minutes=2)
    if "started"!=choose_meet_announcement( now_meet_start, [event] ):
        print("event started: failed")
    if ""!=choose_meet_announcement( now_meet_start.shift(hours=-1), [event] ):
        print("event started-1h: failed")
    if ""!=choose_meet_announcement( now_meet_start.shift(hours=1), [event] ):
        print("event started+1h: failed")

    now_meet_tomorrow = event_begin.floor('day').shift(days=-1).shift(hours=10)
    if "tomorrow"!=choose_meet_announcement( now_meet_tomorrow, [event] ):
        print("event tomorrow: failed")
    if ""!=choose_meet_announcement( now_meet_tomorrow.shift(hours=-1), [event] ):
        print("event tomorrow-1h: failed")
    if ""!=choose_meet_announcement( now_meet_tomorrow.shift(hours=1), [event] ):
        print("event tomorrow+1h: failed")

    now_meet_next_week = event_begin.floor('day').shift(days=-7).shift(hours=10)
    if "next_week"!=choose_meet_announcement( now_meet_next_week, [event] ):
        print("event next week: failed")
    if ""!=choose_meet_announcement( now_meet_next_week.shift(hours=-1), [event] ):
        print("event next week-1h: failed")
    if ""!=choose_meet_announcement( now_meet_next_week.shift(hours=1), [event] ):
        print("event next week+1h: failed")
    
    print("choose_meet_announcement tests success")


async def initialize(app: Application) -> None:
    # exceptions escaping from the initialize function result in a silent crash
    # it's therefore important to wrap everything in a try block
    try:
        app.create_task(periodic_callback_generator(app.bot))
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
    admin_set = await get_admin_set(context.bot)
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

    admin_set = await get_admin_set(context.bot)
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
    test_choose_meet_announcement()
    main()
