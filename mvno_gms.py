#!/usr/bin/python3.5
# -*- coding: utf-8 -*-

import telebot
import sys
import utils

from listener import start_listener
from config import token
from threading import Thread
from operator import itemgetter
from datetime import datetime

bot = telebot.TeleBot(token, skip_pending=True, threaded=True)


# Ловим команду для старта
@bot.message_handler(commands=['start'])
def start(message):
    print("bot started with user " + str(message.chat.username) + " " + str(message.chat.id))
    bot.send_message(218944903, "Новый пользователь " + str(message.chat.username) + " " + str(message.chat.id))
    if utils.is_allowed(message.chat.id) is False:
        return bot.send_message(message.chat.id, "Вы не имеете прав на использование бота")
    utils.create_user(message.chat.id)
    bot.send_message(message.chat.id, "Перед использованием настройте фильтры",
                     reply_markup=utils.gen_markup(utils.main_menu))


@bot.message_handler(func=lambda message: True, content_types=["text"])
def buttons(message):
    # Текст и кнопки по умолчанию
    markup = None
    text = "..."
    # Печатаем сообщение которое будем изменять
    request = bot.send_message(message.chat.id, text, reply_markup=markup)
    # Если хотим активировать фильтр
    if message.text == 'Активировать фильтр':
        markup = utils.gen_inl_filter('get_inactive_filters', message.chat.id, request.message_id)
        if markup is None:
            text = "Нет доступных фильтров"
        else:
            text = "Выберите фильтр"
    # Если хотим деактивировать фильтр
    elif message.text == 'Деактивировать фильтр':
        markup = utils.gen_inl_filter('get_active_filters', message.chat.id, request.message_id)
        if markup is None:
            text = "Нет активных фильтров"
        else:
            text = "Выберите фильтр"
    # Если хотим посмотреть активные фильры

    elif message.text == 'Активные фильтры':
        text = ''
        filters = utils.get_active_filters(message.chat.id)
        if len(filters) == 0:
            text = 'Нет активных фильтров'
        else:
            for f in filters:
                text += f + '\n'

    elif message.text == 'История событий':
        markup = utils.get_counter()
        if markup is False:
            text = "За последний час не произошло ни одного события"
        else:
            text = 'Статистика по всем фильтрам\n'
    # Если не знаем кнопки, то ничего не делаем
    else:
        text = 'Неизвестная команда'
    # Собираем сообщение и отправляем в чат
    bot.edit_message_text(chat_id=request.chat.id, text=text.format(text),
                          message_id=request.message_id, reply_markup=markup)


# Активируем или деактивируем фильтр
@bot.callback_query_handler(func=lambda call: call.data.split('_')[0] in utils.get_all_filters())
def control_filter(call):
    data, message_id = call.data.split('_')
    reply = bot.send_message(chat_id=call.message.chat.id, text='...')
    # Если фильтр есть в неактивных, то включаем его
    if data in utils.get_inactive_filters(call.message.chat.id):
        text = utils.set_filter(call.message.chat.id, data)
        markup = utils.gen_inl_filter('get_inactive_filters', call.message.chat.id, reply.message_id)
    # Если фильтр есть в активных, то выключаем его
    elif data in utils.get_active_filters(call.message.chat.id):
        text = utils.unset_filter(call.message.chat.id, data)
        markup = utils.gen_inl_filter('get_active_filters', call.message.chat.id, reply.message_id)
    # Какой-то некорректный фильтр
    else:
        text = "Некорректное имя фильтра"
        markup = None
    # Собираем сообщение и изменяем первое сообщение
    bot.edit_message_text(chat_id=call.message.chat.id, text=text,
                          message_id=message_id)

    bot.edit_message_text(chat_id=call.message.chat.id, text="Выберите фильтр",
                          message_id=reply.message_id, reply_markup=markup)


# Обработка запросов на получение статистики:
@bot.callback_query_handler(func=lambda call: call.data[:4] == 'stat')
def get_stat(call):
    offset = int(call.data.split('_')[1])
    filter = call.data.split('_')[2]
    alarms = utils.get_alarm_by_filter(filter)
    raw_alarms = []
    for a in alarms:
        id = str(a.split(':')[2])
        buffer = utils.from_buffer(id)
        buffer['id'] = id
        raw_alarms.append(buffer)
    sorted_alarms = sorted(raw_alarms, key=itemgetter('time'),reverse=True)
    for s in reversed(sorted_alarms[offset:offset+5]):
        time = datetime.strptime(s["time"],'%Y-%m-%d %H:%M:%S')
        title = s["time"] + '\n' + s["title"]
        send_to_chat(call.message.chat.id, title, s['id'])
    remains = len(sorted_alarms)-(offset+5)
    if remains > 0:
        bot.send_message(call.message.chat.id, "Осталось сообщений: %s"%(remains),reply_markup=utils.get_counter(offset+5,filter))



# Обработка запросов на получение подробной информации:
@bot.callback_query_handler(func=lambda call: True)
def show_body(call):
    # Извлекаем id сообщения в zabbix
    id = str(call.data).split('_')[0]
    # Извлекаем id сообщения в телеграм
    msg = str(call.data).split('_')[1]
    buffer = utils.from_buffer(id)
    title = buffer["time"] + '\n' + buffer["title"]
    body = buffer["body"]
    text = title + "\n" + body
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=int(msg), text=text)


# Отправляем заголовок сообщения в нужный чат
def send_to_chat(chatid, title, id):
    text = title + "\n"
    first = bot.send_message(chatid, text)
    bot.edit_message_reply_markup(chat_id=chatid, message_id=first.message_id,
                                  reply_markup=utils.get_event_data(id, first.message_id))


# Функция для старта поллинга бота
def start_telebot():
    while True:
        try:
            print('Running telegram bot listener')
            bot.polling(none_stop=True)
        except Exception:
            continue


def queue_check():
    while True:
        msg = utils.qbus.get()
        utils.getAlarm(msg[0], msg[1], msg[2])


# Стартуем 2 потока: для поллинга и json-rpc сервер.
if __name__ == '__main__':
    t1 = Thread(target=start_telebot, daemon=True)
    t2 = Thread(target=start_listener, daemon=True)
    t3 = Thread(target=queue_check, daemon=True)
    try:
        t1.start()
        t2.start()
        t3.start()

        t1.join()
        t2.join()
        t3.join()
    except KeyboardInterrupt:
        sys.exit()
