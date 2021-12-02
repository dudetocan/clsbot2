#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Dispatcher and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import logging
import os
import re

import redis
import requests
import telegram
from bs4 import BeautifulSoup
from forex_python.converter import CurrencyRates
from telegram import ParseMode
from telegram.ext import (
    CommandHandler,
    Filters,
    InlineQueryHandler,
    MessageHandler,
    Updater,
)

from mwt import MWT

PORT = int(os.environ.get("PORT", 8443))

token = os.environ.get("TOKEN")

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

logger = logging.getLogger(__name__)


r = redis.from_url(os.environ.get("REDIS_URL"))


@MWT(timeout=60 * 60)
def get_admin_ids(bot, chat_id):
    """Returns a list of admin IDs for a given chat. Results are cached for 1 hour."""
    return [admin.user.id for admin in bot.get_chat_administrators(chat_id)]


"""
Check Permission of user is Admin
"""


def checkPermission(update, context):
    if not update.effective_user.id in get_admin_ids(context.bot, update.message.chat_id):
        update.message.reply_text(f"你唔係院長/副院長！唔俾用🤪")
        return False
    return True


# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.
def start(update, context):
    """Send a message when the command /start is issued."""
    update.message.reply_text("Hi!")


"""
Show helpful links
"""


def help(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text("Help!")
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text="\
    <a href='https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/hong-kong-residents-permanent-residence/eligibility.html'>Stream A/B 傳送門</a>\n<a href='https://applications.wes.org/createaccount/home/select-eval-type?ln=1'>學歷認證</a> （ECA Application for IRCC）\n<a href='https://www.cic.gc.ca/english/contacts/web-form.asp'>Webform</a>\n<a href='https://docs.google.com/spreadsheets/d/1O1AaJHe0Xem0q_x1Q-65BIqw-pPQ157W0ujtVNf11h0/edit?usp=sharing'>Canada Income Tax Calculator (custom)</a>\n<a href='https://docs.google.com/spreadsheets/d/1aXMUpCB_I_VVQxsJUtEZqLULdGpG6EpbYCjaj23dSFg/edit?usp=sharing'>Stream B Hours Calculator</a> (File -> Make a copy)\n<a href='https://linktr.ee/hkcaowpinfo'>加拿大救生艇資訊整合</a>\n",
        parse_mode=ParseMode.HTML,
    )


"""
Adjust a user's points
"""


def adjustPoints(update, context):
    if not checkPermission(update, context):
        return

    # get list of admins
    admin_list = context.bot.get_chat_administrators(update.message.chat_id)
    admin_title = "院長"  # default title
    for admin in admin_list:
        if update.effective_user.id == admin.user.id:
            if admin.custom_title is not None:
                admin_title = admin.custom_title

    user_name_str = [str(i) for i in context.args[:-1]]
    user_name = "cls:" + str(" ".join(user_name_str))

    while True:
        try:
            points = int(context.args[-1])
            break
        except ValueError:
            update.message.reply_text(f"唔該輸入一個有效嘅數字\n指令參考：/adjust @username 100")
            return

    if r.exists(user_name):
        # update the current points
        cur_points = int(r.get(user_name).decode("utf-8"))
        new_points = cur_points + points
        r.set(user_name, new_points)

    else:
        r.set(user_name, points)

    user_name_str = " ".join(user_name_str)

    if points < 0:
        update.message.reply_text(
            f"嗱！依家{admin_title}大發慈悲，扣住你 {user_name_str} {-points}分先，下次唔好喇～\n {user_name_str} 而家嘅CLS分數係 {r.get(user_name).decode('utf-8')}分！"
        )
    else:
        update.message.reply_text(
            f"多謝{admin_title}嘅大恩大德🙇‍♂️🙇‍♀️！繼續努力🤗！加你 {user_name_str} {points}分！\n {user_name_str} 而家嘅CLS分數係 {r.get(user_name).decode('utf-8')}分！"
        )


"""
Get a user's points
"""


def showPoints(update, context):
    if not context.args:
        update.message.reply_text("唔該輸入正確嘅指令：/show @username")
        return
    user_name_str = [str(i) for i in context.args]
    user_name = "cls:" + str(" ".join(user_name_str))

    # points = context.user_data.get(user_name, 0)
    if r.exists(user_name):
        points = r.get(user_name).decode("utf-8")
    else:
        update.message.reply_text("冇呢個人喎...一係你打錯名，一係呢個人未有分🤔")
        return

    update.message.reply_text(f"\"{' '.join(user_name_str)}\" 嘅CLS分數係：{points}")


"""
Reset a user's points to 0
"""


def resetPoints(update, context):
    if not checkPermission(update, context):
        return
    if not context.args:
        update.message.reply_text("唔該輸入正確嘅指令：/reset @username")
        return

    user_name_str = [str(i) for i in context.args]
    user_name = "cls:" + str(" ".join(user_name_str))
    r.set(user_name, 0)
    update.message.reply_text(f"\"{' '.join(user_name_str)}\" 嘅分數已經歸零喇！多謝院長😊🙏！")


"""
Points by rank
"""


def rank(update, context):
    ranks = {}
    for key in r.scan_iter("cls:*"):
        ranks[key] = r.get(key).decode("utf-8")

    # title
    title = []
    title.append("***CLS分數龍虎榜***\n\n")

    # positive
    ranks = dict(sorted(ranks.items(), key=lambda item: -int(item[1])))
    positive = []
    positive.append("TOP 10：\n")
    for idx, (user_name, points) in enumerate(ranks.items()):
        if idx >= 10 or int(points) <= 0:
            break
        user_name = user_name[4:].decode("utf-8")
        while user_name[0] == "@":
            user_name = user_name[1:]
        positive.append(f"{idx+1}: {user_name} | {points}\n")
    if len(positive) == 1:
        positive.append("冇人上榜~\n")

    # negative
    ranks = dict(sorted(ranks.items(), key=lambda item: int(item[1])))
    negative = []
    negative.append("\n負TOP 10：\n")
    for idx, (user_name, points) in enumerate(ranks.items()):
        if idx >= 10 or int(points) >= 0:
            break
        user_name = user_name[4:].decode("utf-8")
        while user_name[0] == "@":
            user_name = user_name[1:]
        negative.append(f"{idx+1}: {user_name} | {points}\n")
    if len(negative) == 1:
        negative.append("冇人上榜~\n")

    result = title + positive + negative

    update.message.reply_text("".join(result))


"""
Points by rank (viewall)
"""


def rankall(update, context):
    ranks = {}
    for key in r.scan_iter("cls:*"):
        ranks[key] = r.get(key).decode("utf-8")

    # title
    title = []
    title.append("***CLS分數龍虎榜***\n\n")

    # all points
    ranks = dict(sorted(ranks.items(), key=lambda item: -int(item[1])))
    rank = []
    for idx, (user_name, points) in enumerate(ranks.items()):
        if int(points) == 0:
            continue
        user_name = user_name[4:].decode("utf-8")
        while user_name[0] == "@":
            user_name = user_name[1:]
        rank.append(f"{len(rank)+1}: {user_name} | {points}\n")
    if len(rank) == 0:
        rank.append("冇人上榜~\n")

    result = title + rank

    update.message.reply_text("".join(result))


"""
Delete key from redis
"""


def delete(update, context):
    if not checkPermission(update, context):
        return
    if not context.args:
        update.message.reply_text("唔該輸入正確嘅指令：/delete @username")
        return

    user_name_str = [str(i) for i in context.args]
    user_name = "cls:" + str(" ".join(user_name_str))

    if not r.exists(user_name):
        update.message.reply_text("未adjust呢個人嘅分數！麻煩adjust咗先再delete！")
        return

    r.delete(user_name)
    update.message.reply_text(f"剷咗\"{' '.join(user_name_str)}\"")


"""
Check existing users in redis
"""


def users(update, context):
    if not checkPermission(update, context):
        return

    result = []
    for key in r.scan_iter("cls:*"):
        key = key[4:]
        result.append(f"{key.decode('utf-8')}\n")

    update.message.reply_text("".join(result))


"""Currency from CAD to HKD"""


@MWT(timeout=10)
def _currency():
    URL = "https://www.x-rates.com/table/?from=HKD&amount=1"
    page = requests.get(URL)

    soup = BeautifulSoup(page.content, "html.parser")

    for a in soup.find_all("a", href=True):
        if "https://www.x-rates.com/graph/?from=CAD" in a["href"]:
            return a.get_text()


def currency(update, context):
    rate = _currency()
    update.message.reply_text(f"而家加幣兑港幣嘅匯率係：{rate}\n資訊由www.x-rates.com提供")


"""mewe link"""


def mewe(update, context):
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text="<a href='https://mewe.com/group/5ff9a6101bcba57ee4e70263'>院長MEWE</a>",
        parse_mode=ParseMode.HTML,
    )


"""Instagram"""


def ig(update, context):
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text="<a href='https://www.instagram.com/letsbeginwithabc/'>院長IG</a>",
        parse_mode=ParseMode.HTML,
    )


"""wake bot"""


def callback_minute(context: telegram.ext.CallbackContext):
    code = requests.get("https://clsbotcls.herokuapp.com/")
    status_code = code.status_code
    context.bot.send_message(chat_id="-595176127", text=status_code)


def echo(update, context):
    """Echo the user message."""
    update.message.reply_text(update.message.text)


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(token, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("adjust", adjustPoints))
    dp.add_handler(CommandHandler("show", showPoints))
    dp.add_handler(CommandHandler("reset", resetPoints))
    dp.add_handler(CommandHandler("rank", rank))
    dp.add_handler(CommandHandler("rankall", rankall))
    dp.add_handler(CommandHandler("delete", delete))
    dp.add_handler(CommandHandler("users", users))
    dp.add_handler(CommandHandler("currency", currency))
    dp.add_handler(CommandHandler("mewe", mewe))
    dp.add_handler(CommandHandler("ig", ig))

    # schedule job
    job = updater.job_queue
    job_minute = job.run_repeating(callback_minute, interval=60 * 30, first=10)

    # on noncommand i.e message - echo the message on Telegram
    # dp.add_handler(MessageHandler(Filters.text, echo))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_webhook(
        listen="0.0.0.0", port=int(PORT), url_path=token, webhook_url=os.environ.get("WEBHOOK_URL") + token
    )

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == "__main__":
    main()
