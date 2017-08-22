#!/usr/bin/python3.5
# -*- coding: utf-8 -*-

import telebot
import sys
import utils

from listener import start_listener
from config import token
from threading import Thread
from operator import itemgetter
import re

bot = telebot.TeleBot(token, skip_pending=True, threaded=True)


# Ловим команду для старта
@bot.message_handler(commands=['start'])
def start(message):
    print("bot started with %s %s" % (message.chat.username, message.chat.id))
    utils.toggle_mode(message.chat.id, 'track')
    bot.send_message(message.chat.id,
                     "Перед использованием настройте фильтры\nДля просмотра команд наберите /help",
                     reply_markup=utils.gen_markup(utils.main_menu))


@bot.message_handler(commands=['help'])
def start(message):
    bot.send_message(message.chat.id,
                     "/start - начать работу с ботом\n/reset - удалить все свои настройки\n"
                     "/edit - войти в режим редактирования фильтров\n/track - войти в режим получения уведомлений\n"
                     "/help - посмотреть список команд")


# Ловим команду для ресета
@bot.message_handler(commands=['reset'])
def reset(message):
    utils.reset_user(message.chat.id)
    bot.send_message(message.chat.id,
                     "Перед использованием настройте фильтры\nДля входа в режим редактирования наберите /edit",
                     reply_markup=utils.types.ReplyKeyboardRemove)


# Ловим команду для входа в режим редактирования
@bot.message_handler(commands=['edit'])
def reset(message):
    markup = None
    markup = utils.gen_markup(utils.edit_menu)
    utils.toggle_mode(message.chat.id, 'edit')
    text = 'Вы вошли в режим редактирования\nДля возврата в режим просмотра наберите /track'
    bot.send_message(message.chat.id, text, reply_markup=markup)


# Ловим команду для входа в режим просмотра
@bot.message_handler(commands=['track'])
def reset(message):
    markup = None
    markup = utils.gen_markup(utils.main_menu)
    utils.toggle_mode(message.chat.id, 'track')
    text = 'Вы вошли в режим просмотра\nДля входа в режим редактирования наберите /edit'
    bot.send_message(message.chat.id, text, reply_markup=markup)


# Работа с текстом в режиме ввода имени фильтра
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'input_name', content_types=["text"])
def input_regex(message):
    markup = None
    if message.text == 'Отмена':
        utils.toggle_mode(message.chat.id, 'edit')
        text = 'Создание отменено'
        markup = utils.gen_markup(utils.edit_menu)
    else:
        filter = message.text
        if filter not in utils.get_all_filters(message.chat.id):
            utils.create_filter(message.chat.id, filter)
            utils.toggle_mode(message.chat.id, filter)
            text = 'Введите регулярное выражение для фильтра %s' % filter
        else:
            text = 'Фильтр %s уже существует, выберите другое имя' % filter
    bot.send_message(message.chat.id, text, reply_markup=markup)


# Работа с текстом в режиме ввода регулярного выражения
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) in utils.get_all_filters(message.chat.id),
                     content_types=["text"])
def input_regex(message):
    if message.text == 'Отмена':
        filter = utils.get_mode(message.chat.id)
        utils.toggle_mode(message.chat.id, 'edit')
        if filter in utils.get_new_filters():
            utils.delete_filter(message.chat.id, filter)
        text = 'Изменение отменено'
        markup = utils.gen_markup(utils.edit_menu)
    else:
        try:
            re.compile(message.text)
            is_valid = True
        except re.error:
            is_valid = False
        if is_valid is True:
            filter = utils.get_mode(message.chat.id)
            utils.edit_filter(message.chat.id, filter, message.text)
            utils.toggle_mode(message.chat.id, 'edit')
            if filter in utils.get_new_filters(message.chat.id):
                utils.delete_filter(message.chat.id, filter)
                text = 'Фильтр %s успешно создан' % filter
            else:
                text = 'Фильтр %s успешно изменен' % filter
            markup = utils.gen_markup(utils.edit_menu)
        else:
            text = 'Некорректное регулярное выражение, введите корректное значение'
            markup = None
    bot.send_message(message.chat.id, text, reply_markup=markup)


# Работа с кнопками в режиме просмотра
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'edit', content_types=["text"])
def buttons(message):
    # Текст и кнопки по умолчанию
    markup = None
    text = "..."
    # Печатаем сообщение которое будем изменять
    request = bot.send_message(message.chat.id, text, reply_markup=markup)
    # Если хотим активировать фильтр
    if message.text == 'Посмотреть фильтр':
        markup = utils.gen_inl_filters('get_all_filters', message.chat.id, request.message_id, 'show')
        if markup is None:
            text = "Нет доступных фильтров"
        else:
            text = "Выберите фильтр для просмотра"

    # Если хотим деактивировать фильтр
    elif message.text == 'Добавить фильтр':
        utils.toggle_mode(message.chat.id, 'input_name')
        text = "Cоздание нового фильтра"
        text2 = "Введите имя фильтра"

    # Если хотим посмотреть активные фильры
    elif message.text == 'Редактировать фильтр':
        markup = utils.gen_inl_filters('get_all_filters', message.chat.id, request.message_id, 'edit')
        if markup is None:
            text = "Нет доступных фильтров"
        else:
            text = "Выберите фильтр для редактирования"

    # Если хотим посмотреть историю событий
    elif message.text == 'Удалить фильтр':
        markup = utils.gen_inl_filters('get_all_filters', message.chat.id, request.message_id, 'delete')
        if markup is None:
            text = "Нет доступных фильтров"
        else:
            text = "Выберите фильтр для удаления"

    # Если не знаем кнопки, то ничего не делаем
    else:
        text = 'Неизвестная команда'
    # Собираем сообщение и отправляем в чат
    bot.edit_message_text(chat_id=request.chat.id, text=text.format(text),
                          message_id=request.message_id, reply_markup=markup)
    if message.text == 'Добавить фильтр':
        bot.send_message(message.chat.id, text=text2, reply_markup=utils.gen_markup(utils.cancel))

        # Работа с кнопками в режиме просмотра


# Работа с кнопками в режиме просмотра
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'track', content_types=["text"])
def buttons(message):
    # Текст и кнопки по умолчанию
    markup = None
    text = "..."
    # Печатаем сообщение которое будем изменять
    request = bot.send_message(message.chat.id, text, reply_markup=markup)
    # Если хотим активировать фильтр
    if message.text == 'Активировать фильтр':
        markup = utils.gen_inl_filters('get_inactive_filters', message.chat.id, request.message_id)
        if markup is None:
            text = "Нет доступных фильтров"
        else:
            text = "Выберите фильтр"


    # Если хотим деактивировать фильтр
    elif message.text == 'Деактивировать фильтр':
        markup = utils.gen_inl_filters('get_active_filters', message.chat.id, request.message_id)
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

    # Если хотим посмотреть историю событий
    elif message.text == 'История событий':
        markup = utils.get_counter(message.chat.id)
        if markup is False:
            text = "За последние сутки не произошло ни одного события"
        else:
            text = 'Статистика по всем фильтрам за последние 24 часа:\n'

    # Если не знаем кнопки, то ничего не делаем
    else:
        text = 'Неизвестная команда'
    # Собираем сообщение и отправляем в чат
    bot.edit_message_text(chat_id=request.chat.id, text=text.format(text),
                          message_id=request.message_id, reply_markup=markup)


# Получаем тело фильра
@bot.callback_query_handler(func=lambda call: (
        call.data.split('_')[0] in utils.get_all_filters(call.message.chat.id) and utils.get_mode(
            call.message.chat.id) == 'edit'))
def get_filter(call):
    data, message_id, action = call.data.split('_')
    text = '...'
    text2 = 'Выберите фильтр'
    markup = None
    reply = bot.send_message(chat_id=call.message.chat.id, text='...')
    if action == 'show':
        text = "Фильтр %s:\n%s" % (data, utils.get_filter(call.message.chat.id, data))
        text2 = 'Выберите фильтр для просмотра'
        markup = utils.gen_inl_filters('get_all_filters', call.message.chat.id, reply.message_id, action)
    elif action == 'delete':
        utils.delete_filter(call.message.chat.id, data)
        text = "Фильтр %s удален" % data
        text2 = 'Выберите фильтр для удаления'
        markup = utils.gen_inl_filters('get_all_filters', call.message.chat.id, reply.message_id, action)
    elif action == 'edit':
        utils.toggle_mode(call.message.chat.id, data)
        text = "Редактирование фильтра %s\nТекущее значение:\n%s" % (data, utils.get_filter(call.message.chat.id, data))
        text2 = "Введите регулярное выражение\nhttp://www.exlab.net/files/tools/sheets/regexp/regexp.pdf"

    if action in ['show', 'delete']:
        bot.edit_message_text(chat_id=call.message.chat.id, text=text2,
                              message_id=reply.message_id, reply_markup=markup)

        bot.edit_message_text(chat_id=call.message.chat.id, text=text,
                              message_id=message_id)
    elif action == "edit":
        bot.edit_message_text(chat_id=call.message.chat.id, text=text,
                              message_id=reply.message_id, reply_markup=markup)
        bot.send_message(call.message.chat.id, text=text2, reply_markup=utils.gen_markup(utils.cancel))


# Активируем или деактивируем фильтр
@bot.callback_query_handler(func=lambda call: (
        call.data.split('_')[0] in utils.get_all_filters(call.message.chat.id) and utils.get_mode(
            call.message.chat.id) == 'track'))
def control_filter(call):
    data, message_id, action = call.data.split('_')
    reply = bot.send_message(chat_id=call.message.chat.id, text='...')
    # Если фильтр есть в неактивных, то включаем его
    if data in utils.get_inactive_filters(call.message.chat.id):
        text = utils.set_filter(call.message.chat.id, data)
        markup = utils.gen_inl_filters('get_inactive_filters', call.message.chat.id, reply.message_id)
    # Если фильтр есть в активных, то выключаем его
    elif data in utils.get_active_filters(call.message.chat.id):
        text = utils.unset_filter(call.message.chat.id, data)
        markup = utils.gen_inl_filters('get_active_filters', call.message.chat.id, reply.message_id)
    # Какой-то некорректный фильтр
    else:
        text = "Некорректное имя фильтра"
        markup = None
    # Собираем сообщение и изменяем первое сообщение

    bot.edit_message_text(chat_id=call.message.chat.id, text="Выберите фильтр",
                          message_id=reply.message_id, reply_markup=markup)

    bot.edit_message_text(chat_id=call.message.chat.id, text=text,
                          message_id=message_id)


# Обработка запросов на получение статистики:
@bot.callback_query_handler(
    func=lambda call: (call.data[:4] == 'stat') and utils.get_mode(call.message.chat.id) == 'track')
def get_stat(call):
    offset = int(call.data.split('_')[1])
    filter = call.data.split('_')[2]
    alarms = utils.get_alarm_by_filter(call.message.chat.id, filter)
    raw_alarms = []
    for a in alarms:
        id = str(a.split(':')[3])
        buffer = utils.from_buffer(call.message.chat.id, id)
        buffer['id'] = id
        raw_alarms.append(buffer)
    sorted_alarms = sorted(raw_alarms, key=itemgetter('time'), reverse=True)
    for s in reversed(sorted_alarms[offset:offset + 5]):
        # time = datetime.strptime(s["time"], '%Y-%m-%d %H:%M:%S')
        title = s["time"] + '\n' + s["title"]
        send_to_chat(call.message.chat.id, title, s['id'])
    remains = len(sorted_alarms) - (offset + 5)
    if remains > 0:
        bot.send_message(call.message.chat.id, "Осталось сообщений: %s" % remains,
                         reply_markup=utils.get_counter(offset + 5, filter))


# Обработка запросов на получение подробной информации:
@bot.callback_query_handler(func=lambda call: utils.get_mode(call.message.chat.id) == 'track')
def show_body(call):
    # Извлекаем id сообщения в zabbix
    id, msg, action = str(call.data).split('_')
    buffer = utils.from_buffer(call.message.chat.id, id)
    title = buffer["time"] + '\n' + buffer["title"]
    body = buffer["body"]

    if action == 'show':
        text = title + "\n" + body
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=int(msg), text=text,
                              reply_markup=utils.hide_event_data(id, msg))
    if action == 'hide':
        text = title
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=int(msg), text=text,
                              reply_markup=utils.get_event_data(id, msg))


# Отправляем заголовок сообщения в нужный чат
def send_to_chat(chatid, title, id):
    if utils.get_mode(chatid) != 'track':
        return
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
        try:
            msg = utils.qbus.get()
            utils.getAlarm(msg[0], msg[1], msg[2])
        except Exception:
            continue


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
