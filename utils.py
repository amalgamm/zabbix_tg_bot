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
edit_menu = ['Посмотреть фильтр', 'Добавить фильтр', 'Редактировать фильтр', 'Удалить фильтр']
cancel = ['Отмена']


# Сбрасываем все настройки пользователя
def reset_user(chat_id):
    for keys in r.keys("users:" + str(chat_id) + ":*"):
        r.delete(keys)
    return

# Переключаем режим пользователя
def toggle_mode(chat_id, mode):
    r.set("users:" + str(chat_id) + ":mode", mode)
    return


# Проверяем режим пользователя
def get_mode(chat_id):
    try:
        return r.get("users:" + str(chat_id) + ":mode")
    except Exception:
        return None


def show_filter(chat_id, message_id):
    return gen_inl_filters('get_all_filters', chat_id, message_id)


# Получаем содержимое фильтра
def get_filter(chat_id, filter):
    return r.get("filter:%s:%s" % (chat_id, filter))


# Получаем список всех фильтров
def get_all_filters(chat_id=''):
    filters = []
    for f in r.keys("filter:%s:*" % chat_id):
        filter = f.split(':')[2]
        filters.append(filter)
    return filters


# Получаем список всех фильтров
def get_new_filters(chat_id=''):
    filters = []
    for f in r.keys("new:%s:*" % chat_id):
        filter = f.split(':')[2]
        filters.append(filter)
    return filters


# Генерим жесткие кнопки меню
def gen_markup(menu):
    # Формируем начальное навигационное меню
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, selective=True)
    row = []
    for i in menu:
        row.append(i)
    markup.add(*row)
    return markup


# Генерим инлайн кнопки
def gen_inl_markup(menu, message_id, action):
    markup = types.InlineKeyboardMarkup(row_width=2)
    row = []
    if isinstance(menu, dict):
        for t, d in menu.items():
            print(t, d)
            row.append(types.InlineKeyboardButton(text=t, callback_data='%s_%s_%s' % (d, message_id, action)))
    if isinstance(menu, list):
        for t in menu:
            row.append(types.InlineKeyboardButton(text=t, callback_data='%s_%s_%s' % (t, message_id, action)))
    if len(row) == 0:
        return None
    markup.add(*row)

    return markup


# Генерим инлайн кнопками список нужных фильтров
def gen_inl_filters(type, chat_id, message_id, action='none'):
    # Получаем кнопки, которые надо сгенерить определенному пользователю
    filters = getattr(this, type)(chat_id)
    # Генерим инлайн кнопки по списку
    markup = gen_inl_markup(filters, message_id, action)
    return markup


# Удаляем фильтр из базы
def delete_filter(chat_id, filter):
    if filter in get_new_filters(chat_id):
        r.delete("new:%s:%s" % (chat_id, filter))
        r.delete("filter:%s:%s" % (chat_id, filter))
    else:
        entry = str(r.get("filter:%s:%s" % (chat_id, filter)))
        r.set("deleted:%s:%s" % (chat_id, filter), entry)
        r.delete("filter:%s:%s" % (chat_id, filter))
        r.delete("new:%s:%s" % (chat_id, filter))
        unset_filter(chat_id, filter)
    return

# Изменяем фильтр
def edit_filter(chat_id, filter, regex):
    entry = str(r.get("filter:%s:%s" % (chat_id, filter)))
    r.set("edited:%s:%s" % (chat_id, filter), entry)
    r.set("filter:%s:%s" % (chat_id, filter), regex)
    return

# Создаем фильтрр
def create_filter(chat_id, filter):
    r.set("filter:%s:%s" % (chat_id, filter), '')
    r.set("new:%s:%s" % (chat_id, filter), '')
    return


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
    all_list = get_all_filters(chat_id)
    ina_list = list(set(all_list) - set(active_list))
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
def getAlarm(chat_id, title, body):
    # Определяем к какой группе относится событие
    filters = sort(chat_id, title)
    for f in filters:
        # Запмсываем в буфер, получаем идентификатор
        id = to_buffer(chat_id, f, title, body)
        # Для всех пользователей у кого активен фильтр отправляем сообщение
        for user in get_users():
            if check_filter(user, f) is True:
                send_to_chat(user, title, id)
    return


# Классифицируем сообщение под какой-либо шаблон
def sort(chat_id, title):
    filters = []
    for f in get_all_filters(chat_id):
        mask = r.get("filter:%s:%s" % (chat_id, f))
        if re.match(mask, title, re.MULTILINE | re.DOTALL) is not None:
            filters.append(f)
    if len(filters) > 0:
        return filters
    return ["other"]


# Записываем сообщение в буфер, получаем идентификатор сообщения
def to_buffer(chat_id, filter, title, body):
    id = str(uuid.uuid4())
    r.hmset('buffer:%s:%s:%s' % (chat_id, filter, id), {'title': title, 'body': body, 'time': datetime.now().strftime(
        '%Y-%m-%d %H:%M:%S')})
    r.expire('buffer:%s:%s:%s' % (chat_id, filter, id), 86400)
    return id


# Генерим кнопку для подробной информации об аларме
def get_event_data(event_id, message_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(text="Подробнее",
                                   callback_data='%s_%s_%s' % (event_id, message_id, 'show')))
    return keyboard


# Генерим кнопку для скрытия информации об аларме
def hide_event_data(event_id, message_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(text="Скрыть",
                                   callback_data='%s_%s_%s' % (event_id, message_id, 'hide')))
    return keyboard


# Получаем сообщение из буфера по id
def from_buffer(chat_id, id):
    try:
        path = r.keys('buffer:%s:*:%s' % (chat_id, id))
        return r.hgetall(path[0])
    except Exception:
        return {'title': 'Ой!', 'body': 'Сообщение было удалено из буфера по таймауту', 'time': 'Более 24 часов назад'}


# Получаем счетчики по всем фильтрам, формируем кнопки для них
def get_counter(chat_id, offset=0, filter=''):
    counters = {}
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if filter == '':
        buffer = r.keys('buffer:%s*' % chat_id)
        if len(buffer) == 0:
            return False
        for f in buffer:
            filter = f.split(':')[2]
            count = len(r.keys('buffer:%s:%s:*' % (chat_id, filter)))
            counters.update({filter: count - offset})
        for c in counters:
            keyboard.add(types.InlineKeyboardButton(text='%s (%s)' % (c, str(counters[c])),
                                                    callback_data='stat_%s_%s' % (offset, c)))
    else:
        keyboard.add(types.InlineKeyboardButton(text='Показать еще', callback_data='stat_%s_%s' % (offset, filter)))
    return keyboard


def get_alarm_by_filter(chat_id, filter):
    return r.keys('buffer:%s:%s:*' % (chat_id, filter))
