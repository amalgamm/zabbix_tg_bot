#!/usr/bin/python3.5
# -*- coding: utf-8 -*-

import redis
import re
import uuid
import sys

from queue import Queue
from config import redis_db, redis_server
from telebot import types
from mvno_gms import send_to_chat

from datetime import datetime

this = sys.modules[__name__]
pool = redis.ConnectionPool(host=redis_server, port=6379, db=redis_db, encoding='utf-8',
                            decode_responses=True)
r = redis.Redis(connection_pool=pool)

qbus = Queue()

main_menu = ["Активировать фильтр", "Деактивировать фильтр", "Активные фильтры", "История событий"]


# Создаем нового пользователя
def create_user(chat_id):
    for keys in r.keys("users:" + str(chat_id) + ":*"):
        r.delete(keys)


# Получаем список всех фильтров
def get_all_filters():
    filters = []
    for f in r.keys("filter:*"):
        filter = f.split(':')[1]
        filters.append(filter)
    return filters


def gen_markup(menu):
    # Формируем начальное навигационное меню
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, selective=True)
    if len(menu) % 2 == 0:
        for i in range(0, len(menu), 2):
            markup.add(menu[i], menu[i + 1])
    else:
        for i in range(0, len(menu) - 1, 2):
            markup.add(menu[i], menu[i + 1])
        markup.add(menu[-1])
    return markup


# Генерим инлайн кнопками список неактивных фильтров
def gen_inl_filter(type, chat_id, message_id):
    # Формируем inline кнопки для конкретного меню
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    filters = getattr(this, type)(chat_id)
    if filters == []:
        return None
    if len(filters) % 2 == 0:
        for i in range(0, len(filters), 2):
            keyboard.add(
                types.InlineKeyboardButton(text=filters[i], callback_data='%s_%s' % (filters[i], message_id)),
                types.InlineKeyboardButton(text=filters[i + 1], callback_data='%s_%s' % (filters[i + 1], message_id)))
    else:
        for i in range(0, len(filters) - 1, 2):
            keyboard.add(
                types.InlineKeyboardButton(text=filters[i], callback_data='%s_%s' % (filters[i], message_id)),
                types.InlineKeyboardButton(text=filters[i + 1], callback_data='%s_%s' % (filters[i + 1], message_id)))
        keyboard.add(types.InlineKeyboardButton(text=filters[-1], callback_data='%s_%s' % (filters[-1], message_id)))
    return keyboard


# Добавляем фильтр в активные
def set_filter(chat_id, filter):
    r.lpush("users:" + str(chat_id) + ":active", filter)
    return "Фильтр " + filter + " активирован"


# Добавляем фильтр в неактивные
def unset_filter(chat_id, filter):
    r.lrem("users:" + str(chat_id) + ":active", filter)
    return "Фильтр " + filter + " деактивирован"


# Получаем спосик активных фильтров
def get_active_filters(chat_id):
    chk = r.keys("users:" + str(chat_id) + ':active')
    if len(chk) == 0:
        return []
    a_list = r.lrange("users:" + str(chat_id) + ":active", 0, 100)
    return a_list


# Получаем список неактивных фильтров
def get_inactive_filters(chat_id):
    active_list = get_active_filters(chat_id)
    all_list = get_all_filters()
    ina_list = list (set(all_list) - set(active_list))
    return ina_list


# Проверяем отслеживает ли пользователь данную категорию
def check_filter(chat_id, filter):
    a_list = get_active_filters(chat_id)
    ina_list = get_inactive_filters(chat_id)
    if filter in a_list and filter not in ina_list:
        return True


# Получаем список всех пользователей
def get_users():
    users = []
    for k in r.keys('users:*'):
        user = k.split(':')[1]
        if user in users:
            continue
        else:
            users.append(user)
    return users


# Обрабатываем событие
def getAlarm(group, title, body):
    # Определяем к какой группе относится событие
    filter = sort(title)
    # Запмсываем в буфер, получаем идентификатор
    id = to_buffer(filter, title, body)
    # Для всех пользователей у кого активен фильтр отправляем сообщение
    for user in get_users():
        if check_filter(user, filter) is True:
            send_to_chat(user, title, id)
    return


# Классифицируем сообщение под какой-либо шаблон
def sort(title):
    for f in get_all_filters():
        mask = r.get("filter:" + f)
        if re.match(mask, title, re.MULTILINE | re.DOTALL) is not None:
            return f
    return "other"


# Записываем сообщение в буфер, получаем идентификатор сообщения
def to_buffer(filter, title, body):
    id = str(uuid.uuid4())
    r.hmset('buffer:' + filter + ":" + id, {'title': title, 'body': body, 'time': datetime.now().strftime(
        '%Y-%m-%d %H:%M:%S')})
    r.expire('buffer:' + filter + ":" + id, 10800)
    return id


# Генерим кнопку для подробной информации об аларме
def get_event_data(event_id, message_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(types.InlineKeyboardButton(text="Подробнее", callback_data=event_id + '_' + str(message_id)))
    return keyboard


# Получаем сообщение из буфера по id
def from_buffer(id):
    try:
        path = r.keys('buffer:*:' + id)
        return r.hgetall(path[0])
    except Exception:
        return {'title': 'Ой!', 'body': 'Сообщение было удалено из буфера по таймауту', 'time': 'Более 3 часов назад'}


# Получаем счетчики по всем фильтрам, формируем кнопки для них
def get_counter():
    counters = {}
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    buffer = r.keys('buffer:*')
    if len(buffer) == 0:
        return False
    for f in buffer:
        filter = f.split(':')[1]
        count = len(r.keys('buffer:' + filter + ':*'))
        counters.update({filter: count})
    for c in counters:
        keyboard.add(types.InlineKeyboardButton(text='%s (%s)'%(c,str(counters[c])), callback_data='stat_' + c))
    return keyboard




def is_allowed(chatid):
    if str(chatid) in r.lrange('whitelist', 0, -1):
        return True
    else:
        return False


def get_alarm_by_filter(filter):
    return r.keys('buffer:' + filter + ':*')
