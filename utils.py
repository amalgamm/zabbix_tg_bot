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

start_menu = ["Меню"]
track_menu = ["Подписаться", "Отписаться", "Активные подписки", "История событий"]
edit_menu = ["Посмотреть фильтр", "Добавить фильтр", "Редактировать фильтр", "Удалить фильтр", "Экспорт", "Импорт"]
main_menu = ["Режим просмотра", "Режим настройки", "Сброс пользователя"]
reset_menu = ["Да, я уверен", "Нет"]
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
            rules = sort(chat_id, title, body)
            subscriptions = get_active_rules(chat_id)
            active = list(set(subscriptions).intersection(rules))
            event_ids = []
            for rule in rules:
                # Запмсываем в буфер, получаем идентификатор
                event_ids.append(to_buffer(chat_id, rule, title, "%s\n\n<b>Категории:\n%s</b>\n" % (body, active)))
            if len(active) > 0:
                send_to_chat(chat_id, title, event_ids[0])
            continue


def build_worker_pool(task, queue, size):
    workers = []
    for _ in range(size):
        worker = task(queue)
        worker.start()
        workers.append(worker)
    return workers


# Сбрасываем все настройки пользователя
def reset_user(chat_id, complete=True):
    if complete is True:
        for keys in r.keys("%s:*" % chat_id):
            r.delete(keys)
    else:
        for keys in r.keys("%s:active" % chat_id):
            r.delete(keys)
    return


# Переключаем режим пользователя
def new_user(chat_id):
    reset_user(chat_id, False)
    toggle_mode(chat_id, 'track')
    r.set("%s:filters:Без категории" % chat_id, '')
    r.lpush("%s:active" % chat_id, 'Без категории')
    return


# Переключаем режим пользователя
def toggle_mode(chat_id, mode):
    r.set("%s:mode" % chat_id, mode)
    return


# Проверяем режим пользователя
def get_mode(chat_id):
    try:
        return r.get("%s:mode" % chat_id)
    except Exception:
        return None


# Получаем содержимое фильтра
def get_rule_expr(chat_id, rule):
    return r.get("%s:filters:%s" % (chat_id, rule))


def get_rule_by_id(chat_id, event_id):
    keys = r.keys("%s:buffer:*:%s" % (chat_id, event_id))
    if len(keys) > 0:
        return keys[0].split(":")[2]
    else:
        return None


# Получаем список всех фильтров
def get_all_rules(chat_id=''):
    rules = []
    for f in r.keys("%s:filters:*" % chat_id):
        rule = f.split(':')[2]
        rules.append(rule)
    return rules


# Получаем список всех фильтров
def get_new_rules(chat_id=''):
    rules = []
    for f in r.keys("%s:new:*" % chat_id):
        rule = f.split(':')[2]
        rules.append(rule)
    return rules


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
def gen_inl_markup(menu, message_id, action, back=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    row = []
    if isinstance(menu, dict):
        for t, d in menu.items():
            row.append(types.InlineKeyboardButton(text=t, callback_data='%s_%s_%s' % (action, message_id, d)))
    if isinstance(menu, list):
        for t in menu:
            row.append(types.InlineKeyboardButton(text=t, callback_data='%s_%s_%s' % (action, message_id, t)))
    markup.add(*row)
    if back is not None:
        markup.add(types.InlineKeyboardButton(text='Назад', callback_data='%s_%s_%s' % ('menu', message_id, back)))
    return markup


# Генерим инлайн кнопками список нужных фильтров
def gen_inl_rules_markup(mark_func, chat_id, message_id, action, back=None):
    # Получаем кнопки, которые надо сгенерить определенному пользователю
    rules = getattr(this, mark_func)(chat_id)
    # Генерим инлайн кнопки по списку
    markup = gen_inl_markup(rules, message_id, action, back)

    return markup


# Удаляем фильтр из базы
def delete_rule(chat_id, rule, category):
    if category == 'canceled':
        r.delete("%s:new:%s" % (chat_id, rule))
        r.delete("%s:filters:%s" % (chat_id, rule))
    elif category == 'new':
        r.delete("%s:new:%s" % (chat_id, rule))
    else:
        if rule == 'Без категории':
            return "Фильтр Без категории не может быть удален т.к. является фильтром по-умолчанию"
        entry = str(r.get("rule:%s:%s" % (chat_id, rule)))
        r.set("%s:deleted:%s" % (chat_id, rule), entry)
        r.delete("%s:filters:%s" % (chat_id, rule))
        r.delete("%s:new:%s" % (chat_id, rule))
        unsubscribe(chat_id, rule)
    return "Фильтр %s удален" % rule


# Изменяем фильтр
def edit_rule(chat_id, rule, regex):
    entry = str(r.get("%s:filters:%s" % (chat_id, rule)))
    r.set("%s:edited:%s" % (chat_id, rule), entry)
    r.set("%s:filters:%s" % (chat_id, rule), regex)
    return


# Создаем фильтрр
def create_rule(chat_id, rule):
    r.set("%s:filters:%s" % (chat_id, rule), '')
    r.set("%s:new:%s" % (chat_id, rule), '')
    return


# Добавляем фильтр в активные
def subscribe(chat_id, rule):
    r.lpush("%s:active" % chat_id, rule)
    return "Подписка \"%s\" включена" % rule


# Добавляем фильтр в неактивные
def unsubscribe(chat_id, rule):
    r.lrem("%s:active" % chat_id, rule)
    return "Подписка \"%s\" отключена" % rule


# Получаем спосик активных фильтров
def get_active_rules(chat_id):
    chk = r.keys("%s:active" % chat_id)
    if len(chk) == 0:
        return []
    a_list = r.lrange("%s:active" % chat_id, 0, 100)
    return a_list


# Получаем список неактивных фильтров
def get_inactive_rules(chat_id):
    active_list = get_active_rules(chat_id)
    all_list = get_all_rules(chat_id)
    ina_list = list(set(all_list) - set(active_list))
    return ina_list


# Проверяем отслеживает ли пользователь данную категорию
def check_rule(chat_id, rule):
    a_list = get_active_rules(chat_id)
    ina_list = get_inactive_rules(chat_id)
    if rule in a_list and rule not in ina_list:
        return True


# Классифицируем сообщение под какой-либо шаблон
def sort(chat_id, title, body):
    rules = []
    for f in get_all_rules(chat_id):
        if f == 'Без категории':
            continue
        mask = r.get("%s:filters:%s" % (chat_id, f))
        if re.match(mask, title + body, re.MULTILINE | re.DOTALL) is not None:
            rules.append(f)
    if len(rules) > 0:
        return rules
    return ["Без категории"]


# Записываем сообщение в буфер, получаем идентификатор сообщения
def to_buffer(chat_id, rule, title, body):
    uid = str(uuid.uuid4())
    r.hmset('%s:buffer:%s:%s' % (chat_id, rule, uid), {'title': title, 'body': body, 'time': datetime.now().strftime(
        '%Y-%m-%d %H:%M:%S')})
    r.expire('%s:buffer:%s:%s' % (chat_id, rule, uid), 86400)
    return uid


# Генерим кнопку для подробной информации об аларме
def get_event_data(event_id, message_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(text="Подробнее",
                                   callback_data='%s_%s_%s' % ('show', message_id, event_id)))
    return keyboard


# Генерим кнопку для скрытия информации об аларме
def hide_event_data(event_id, message_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(text="Скрыть",
                                   callback_data='%s_%s_%s' % ('hide', message_id, event_id)))
    return keyboard


# Получаем сообщение из буфера по id
def from_buffer(chat_id, event_id):
    try:
        path = r.keys('%s:buffer:*:%s' % (chat_id, event_id))
        return r.hgetall(path[0])
    except Exception:
        return None


# Получаем счетчики по всем фильтрам, формируем кнопки для них
def get_counter(chat_id, offset=0, rule=''):
    counters = {}
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if rule == '':
        buffer = r.keys('%s:buffer:*' % chat_id)
        if len(buffer) == 0:
            return False
        for f in buffer:
            rule = f.split(':')[2]
            count = len(r.keys('%s:buffer:%s:*' % (chat_id, rule)))
            counters.update({rule: count - offset})
        for c in counters:
            keyboard.add(types.InlineKeyboardButton(text='%s (%s)' % (c, str(counters[c])),
                                                    callback_data='stat_%s_%s' % (offset, c)))
    else:
        keyboard.add(types.InlineKeyboardButton(text='Показать еще', callback_data='stat_%s_%s' % (offset, rule)))
    return keyboard


# Получаем список фильтров пользователя и формируем сообщение для экспорта
def export_rules(chat_id):
    rules = get_all_rules(chat_id)
    export_data = {}
    for f in rules:
        export_data[f] = get_rule_expr(chat_id, f)
    return json.dumps(export_data)


def import_rules(chat_id, import_data):
    try:
        data = json.loads(import_data)
    except Exception:
        return "Некорректный формат строки импорта"
    result = {}
    for name, regex in data.items():
        if len(name) > 20:
            return 'Длина имени фильтра не должна превышать 20 знаков'
        elif ":" in name or "_" in name:
            return 'Использование символов \":\" и \"_\" в названии фильтра недопустимо'
        if isinstance(regex, str):
            try:
                re.compile(regex)
                is_valid = True
            except re.error:
                is_valid = False
            if is_valid is True:
                status = r.set("%s:filters:%s" % (chat_id, name), regex)
                if status is True:
                    result[name] = "ОК"
                else:
                    result[name] = "Ошибка при работе с базой"
            else:
                result[name] = "Некорректное регулярное выражение"
        else:
            result[name] = "Значение регулярного выражения не может иметь вложенную структуру"
    return result


def get_events_by_rule(chat_id, rule):
    return r.keys('%s:buffer:%s:*' % (chat_id, rule))
