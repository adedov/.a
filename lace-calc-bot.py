import json
import logging
import math
import os
import prettytable as pt

from telegram import (
    Bot,
    ParseMode,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update
)

from telegram.ext import (
    Dispatcher,
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)

TOKEN = os.environ["TG_BOT_TOKEN"] 

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

CHOOSING, TYPING_REPLY, TYPING_CHOICE = range(3)
DONE = "Расчитать"

param_names = {
    "skirt_form"    : "Форма юбки",
    "skirt_len"     : "Высота юбки, см",
    "waist_len"     : "Обхват талии, см",
    "density_st"    : "Плотность в петлях",
    "density_row"   : "Плотность в рядах" 
}

skirt_forms = {
    "sun":      "Солнце",
    "semisun":  "Полусолнце",
    "bell":     "Колокол",
    "yoke":     "Круглая кокетка"
}

reply_keyboard = [
    [ param_names["skirt_form"] ],
    [ param_names["skirt_len"], param_names["waist_len"] ],
    [ param_names["density_st"], param_names["density_row"] ],
    [ DONE ],
]
mainkb_markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)


def curr_params_str(user_data):
    curr = [f'{param_names[key]}: \t{value}' for key, value in user_data.items()]
    return "\n".join(curr).join(['\n', '\n'])


def find_param(text, mp):
    for k,v in mp.items():
        if v == text:
            return k


def start(update, context):
    update.message.reply_text(
        "Давайте расчитаем юбочку для вас!",
        reply_markup=mainkb_markup
    )

    return CHOOSING


def error_handler(update, context):
    logger.error(msg="Exception handler:", exc_info=context.error)
    update.message.reply_text(
        "Что-то пошло не так, давайте попробуем еще раз...",
        reply_markup=mainkb_markup
    )
    return CHOOSING


def regular_choice(update, context):
    def skirt_form_choice():
        skirt_form_keyboard = [
            [ x for x in skirt_forms.values() ]
        ]

        return ReplyKeyboardMarkup(skirt_form_keyboard, one_time_keyboard=True)


    text = update.message.text
    choice = find_param(text, param_names)

    if not choice:
        return CHOOSING

    context.user_data['choice'] = choice

    markup = None
    if choice == "skirt_form":
        markup = skirt_form_choice()

    update.message.reply_text(f'Укажите "{text.lower()}":', reply_markup=markup)

    return TYPING_REPLY


def received_information(update, context):
    user_data = context.user_data
    text = update.message.text
    param = user_data['choice']
    user_data[param] = text
    del user_data['choice']

    update.message.reply_text(
        "Текущие параметры:\n"
        f"{curr_params_str(user_data)}",
        reply_markup=mainkb_markup,
    )

    return CHOOSING


def calculate(user_data):
    H = int(user_data["skirt_len"])
    OT = int(user_data["waist_len"])
    den_st = int(user_data["density_st"])
    den_row = int(user_data["density_row"])
    reduces = [ [2, 1], [3, 2], [4, 3], "symm" ]

    k_vals = {
        "sun": 1.0,
        "semisun": 0.5,
        "bell": 0.25,
        "yoke": 0.6
    }

    K = k_vals[ find_param(user_data["skirt_form"], skirt_forms) ] # TODO
    r = OT / (2*math.pi*K)
    R = r+H

    text = f"""*Общая информация*
Сколько петель набирать: \t{round((2*math.pi*R*den_st*K)*0.1)}
Петель в обхвате талии: \t{round(OT*den_st*0.1)}
Высота юбки в рядах: \t{round(H*den_row*0.1)}

*Таблица убавлений*
"""

    for rr in reduces:
        height_list = []
        height_list_r = []

        if rr == "symm":
            title = "Вертикальная симметрия"
            layers = math.floor(H / r)

            for n in range(1, layers+1):
                n_height = (R / (layers+1))*n
                height_list.append( round(n_height, 2) )
                height_list_r.append( round(n_height*den_row*0.1) )
        else:
            title = f"{rr[0]} -> {rr[1]}"
            layers = math.floor( math.log(R/r) / math.log(rr[0]/rr[1]) )

            for n in range(1, layers+1):
                n_height = R * (1 - math.pow(rr[1]/rr[0], n))
                height_list.append( round(n_height,2) )
                height_list_r.append( round(n_height*den_row*0.1) )


        text += f"Убавления: `{title}`\n"
        text += f"Количество ярусов: `{layers}`\n"
        text += "Выстота ярусов:\n"
        table = pt.PrettyTable(border=False)
        table.add_column("Cм.", height_list, align='l')
        table.add_column("Ряды", height_list_r, align='l')
        text += f"```\n{table}\n```\n"

    return text


def done(update, context):
    user_data = context.user_data
    text = calculate(user_data)

    update.message.reply_markdown_v2(
        text,
        reply_markup=ReplyKeyboardRemove(),
    )

    user_data.clear()
    return ConversationHandler.END


def setup(dispatcher):
    conv_handler = ConversationHandler(
        entry_points=[ CommandHandler('start', start) ],
        states = {
            CHOOSING: [
                MessageHandler(
                    Filters.text & ~(Filters.command | Filters.regex(f'^{DONE}$')), regular_choice
                )
            ],
            TYPING_CHOICE: [
                MessageHandler(
                    Filters.text & ~(Filters.command | Filters.regex(f'^{DONE}$')), regular_choice
                )
            ],
            TYPING_REPLY: [
                MessageHandler(
                    Filters.text & ~(Filters.command | Filters.regex(f'^{DONE}$')),
                    received_information,
                )
            ],
        },
        fallbacks=[MessageHandler(Filters.regex(f'^{DONE}$'), done)],
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_error_handler(error_handler)


def webhook(event, context):
    global bot
    global dispatcher

    if event.get('httpMethod') == 'POST' and event.get('body'): 
        logger.info('Message received')
        update = Update.de_json(json.loads(event.get('body')), bot)
        dispatcher.process_update(update)

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps('ok')
    }


if __name__ == '__main__':
    updater = Updater(TOKEN)
    setup(updater.dispatcher)
    updater.start_polling()
    updater.idle()
else:
    bot = Bot(TOKEN)
    dispatcher = Dispatcher(bot, None, workers=0)
    setup(dispatcher)
