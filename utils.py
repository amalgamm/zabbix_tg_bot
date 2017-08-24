#!/usr/bin/python3.5
# -*- coding: utf-8 -*-

import redis
import re
import uuid
import sys

from queue import Queue
from config import redis_db, redis_server
from telebot import types
from app import send_to_chat
import json
from datetime import datetime
import threading

this = sys.modules[__name__]
pool = redis.ConnectionPool(host=redis_server, port=6379, db=redis_db, encoding='utf-8',
                            decode_responses=True)
r = redis.Redis(connection_pool=pool)

qbus = Queue()

main_menu = ["Подписаться", "Отписаться", "Активные подписки", "История событий"]
edit_menu = ['Посмотреть фильтр', 'Добавить фильтр', 'Редактировать фильтр', 'Удалить фильтр', 'Экспорт', 'Импорт']
cancel = ['Отмена']


class Parser(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self._queue = queue

    def run(self):
        while True:
            queue_item = self._queue.get()

            # Обрабатываем событие
            chat_id, title, body = queue_item[0], queue_item[1], queue_item[2]
            # Определяем к какой группе относится событие
            filters = sort(chat_id, title, body)
            for f in filters:
                # Запмсываем в буфер, получаем идентификатор
                id = to_buffer(chat_id, f, title, body)
                # Для всех пользователей у кого активен фильтр отправляем сообщение
                # for user in get_users():
                if check_filter(chat_id, f) is True:
                    send_to_chat(chat_id, title, id)
            continue


def build_worker_pool(task, queue, size):
    workers = []
    for _ in range(size):
        worker = task(queue)
        worker.start()
        workers.append(worker)
    return workers


# Сбрасываем все настройки пользователя
def reset_user(chat_id):
    for keys in r.keys("users:%s:*" % chat_id):
        r.delete(keys)
    for keys in r.keys("filter:%s:*" % chat_id):
        r.delete(keys)
    for keys in r.keys("buffer:%s:*" % chat_id):
        r.delete(keys)
    return


# Переключаем режим пользователя
def new_user(chat_id):
    for keys in r.keys("users:%s:*" % chat_id):
        r.delete(keys)
    toggle_mode(chat_id, 'track')
    r.set("filter:%s:Без категории" % chat_id, '')
    r.lpush("users:%s:active" % chat_id, 'Без категории')
    return


# Переключаем режим пользователя
def toggle_mode(chat_id, mode):
    r.set("users:%s:mode" % chat_id, mode)
    return


# Проверяем режим пользователя
def get_mode(chat_id):
    try:
        return r.get("users:%s:mode" % chat_id)
    except Exception:
        return None


def show_filter(chat_id, message_id):
    return gen_inl_filters('get_all_filters', chat_id, message_id)


# Получаем содержимое фильтра
def get_filter(chat_id, filter):
    return r.get("filter:%s:%s" % (chat_id, filter))


def get_filter_by_id(chat_id, event_id):
    keys = r.keys("buffer:%s:*:%s" % (chat_id, event_id))
    if len(keys) > 0:
        return keys[0].split(":")[2]
    else:
        return None


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
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, selective=False)
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
    if len(filters) == 0:
        return None
    # Генерим инлайн кнопки по списку
    markup = gen_inl_markup(filters, message_id, action)
    return markup


# Удаляем фильтр из базы
def delete_filter(chat_id, filter, category):
    if category == 'canceled':
        r.delete("new:%s:%s" % (chat_id, filter))
        r.delete("filter:%s:%s" % (chat_id, filter))
    elif category == 'new':
        r.delete("new:%s:%s" % (chat_id, filter))
    else:
        if filter == 'Без категории':
            return "Фильтр Без категории не может быть удален т.к. является фильтром по-умолчанию"
        entry = str(r.get("filter:%s:%s" % (chat_id, filter)))
        r.set("deleted:%s:%s" % (chat_id, filter), entry)
        r.delete("filter:%s:%s" % (chat_id, filter))
        r.delete("new:%s:%s" % (chat_id, filter))
        unset_filter(chat_id, filter)
    return "Фильтр %s удален" % filter


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
    r.lpush("users:%s:active" % chat_id, filter)
    return "Подписка \"%s\" включена" % filter


# Добавляем фильтр в неактивные
def unset_filter(chat_id, filter):
    r.lrem("users:%s:active" % chat_id, filter)
    return "Подписка \"%s\" отключена" % filter


# Получаем спосик активных фильтров
def get_active_filters(chat_id):
    chk = r.keys("users:%s:active" % chat_id)
    if len(chk) == 0:
        return []
    a_list = r.lrange("users:%s:active" % chat_id, 0, 100)
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


# Классифицируем сообщение под какой-либо шаблон
def sort(chat_id, title, body):
    filters = []
    for f in get_all_filters(chat_id):
        if f == 'Без категории':
            continue
        mask = r.get("filter:%s:%s" % (chat_id, f))
        if re.match(mask, title + body, re.MULTILINE | re.DOTALL) is not None:
            filters.append(f)
    if len(filters) > 0:
        return filters
    return ["Без категории"]


# Записываем сообщение в буфер, получаем идентификатор сообщения
def to_buffer(chat_id, filter, title, body):
    id = str(uuid.uuid4())[:13]
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
        # return {'title': 'Ой!', 'body': 'Сообщение было удалено из буфера по таймауту', 'time': 'Более 24 часов назад'}
        return None


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


# Получаем список фильтров пользователя и формируем сообщение для экспорта
def export_filters(chat_id):
    filters = get_all_filters(chat_id)
    export_data = {}
    for f in filters:
        export_data[f] = get_filter(chat_id, f)
    return (json.dumps(export_data))


def import_filter(chat_id, import_data):
    try:
        data = json.loads(import_data)
    except Exception:
        return "Некорректный формат строки импорта"
    result = {}
    for name, regex in data.items():
        if ":" in name or "_" in name:
            text = 'Использование символов \":\" и \"_\" в названии фильтра недопустимо'
        if isinstance(regex, str):
            try:
                re.compile(regex)
                is_valid = True
            except re.error:
                is_valid = False
            if is_valid is True:
                status = r.set("filter:%s:%s" % (chat_id, name), regex)
                if status is True:
                    result[name] = "ОК"
                else:
                    result[name] = "Ошибка при работе с базой"
            else:
                result[name] = "Некорректное регулярное выражение"
        else:
            result[name] = "Значение регулярного выражения не может иметь вложенную структуру"
    return result


def get_alarm_by_filter(chat_id, filter):
    return r.keys('buffer:%s:%s:*' % (chat_id, filter))
