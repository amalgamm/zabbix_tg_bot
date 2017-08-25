#!/usr/bin/python3.5
# -*- coding: utf-8 -*-

import telebot
import sys
import utils
import re

from listener import start_listener
from config import token
from threading import Thread
from operator import itemgetter

bot = telebot.TeleBot(token, skip_pending=True, threaded=True)


# Ловим команду для старта
@bot.message_handler(commands=['start'])
def start(message):
    print("bot started with %s %s" % (message.chat.username, message.chat.id))
    utils.new_user(message.chat.id)
    bot.send_message(message.chat.id,
                     "Ваш ID %s\nПеред использованием настройте фильтры\n"
                     "Для просмотра доступных команд наберите /help" % message.chat.id,
                     reply_markup=utils.gen_markup(utils.main_menu))


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
        if ":" in filter or "_" in filter:
            text = 'Использование символов \":\" и \"_\" в названии фильтра недопустимо'
        else:
            if filter not in utils.get_all_filters(message.chat.id):
                utils.create_filter(message.chat.id, filter)
                utils.toggle_mode(message.chat.id, filter)
                text = 'Введите регулярное выражение для фильтра %s\n' \
                       'http://www.exlab.net/files/tools/sheets/regexp/regexp.pdf' % filter
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
        if filter in utils.get_new_filters(message.chat.id):
            utils.delete_filter(message.chat.id, filter, 'canceled')
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
                utils.delete_filter(message.chat.id, filter, 'new')
                text = 'Фильтр %s успешно создан' % filter
            else:
                text = 'Фильтр %s успешно изменен' % filter
            markup = utils.gen_markup(utils.edit_menu)
        else:
            text = 'Некорректное регулярное выражение, введите корректное значение'
            markup = None
    bot.send_message(message.chat.id, text, reply_markup=markup)


# Работа с текстом в режиме импорта фильтров
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'import', content_types=["text"])
def input_regex(message):
    markup = utils.gen_markup(utils.edit_menu)
    if message.text == 'Отмена':
        utils.toggle_mode(message.chat.id, 'edit')
        text = 'Импорт отменен'
        markup = utils.gen_markup(utils.edit_menu)
    else:
        import_data = message.text
        result = utils.import_filter(message.chat.id, import_data)
        if isinstance(result, dict):
            text = "Статус операции импорта по фильтрам:\n"
            for name, status in result.items():
                text += '%s: %s\n' % (name, status)
        else:
            text = result
        utils.toggle_mode(message.chat.id, 'edit')

    bot.send_message(message.chat.id, text, reply_markup=markup)


# Работа с кнопками в режиме просмотра
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'edit', content_types=["text"])
def buttons(message):
    # Текст и кнопки по умолчанию
    markup = None
    text = "..."
    text2 = "..."
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
        text2 = "Введите имя фильтра\n использование символов \":\" и \"_\" недопустимо"

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
            text = "Нет доступных подписок"
        else:
            text = "Выберите фильтр для удаления"

    # Если экспортировать свои фильтры
    elif message.text == 'Экспорт':
        text = 'Данные для эскпорта:\n'
        text += utils.export_filters(message.chat.id)

        # Если импортировать фильтры
    elif message.text == 'Импорт':
        text = 'Импорт фильтров'
        text2 = 'Введите данные для импорта в формате {"filer1":"regexp1","filter2":"regexp2"}'
        utils.toggle_mode(message.chat.id, 'import')

        # Если хотим выбрать меню
    elif message.text == 'Меню':
        markup = utils.gen_inl_markup(utils.mode_menu, request.message_id, "menu")
        text = 'Выберите действие'

    # Если не знаем кнопки, то ничего не делаем
    else:
        text = 'Неизвестная команда'
    # Собираем сообщение и отправляем в чат
    bot.edit_message_text(chat_id=request.chat.id, text=text,
                          message_id=request.message_id, reply_markup=markup)
    if message.text == 'Добавить фильтр' or message.text == 'Импорт':
        bot.send_message(message.chat.id, text=text2, reply_markup=utils.gen_markup(utils.cancel))

        # Работа с кнопками в режиме просмотра


# Работа с кнопками в режиме просмотра
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'track', content_types=["text"])
def buttons(message):
    # Текст и кнопки по умолчанию
    markup = None
    text = "..."
    # Печатаем сообщение которое будем изменять
    request = bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')
    # Если хотим активировать фильтр
    if message.text == 'Подписаться':
        markup = utils.gen_inl_filters('get_inactive_filters', message.chat.id, request.message_id, 'control')
        if markup is None:
            text = "Нет доступных подписок"
        else:
            text = "Выберите подписку"


    # Если хотим деактивировать фильтр
    elif message.text == 'Отписаться':
        markup = utils.gen_inl_filters('get_active_filters', message.chat.id, request.message_id, 'control')
        if markup is None:
            text = "Нет активных подписок"
        else:
            text = "Выберите подписку"

    # Если хотим посмотреть активные фильры
    elif message.text == 'Активные подписки':
        text = ''
        filters = utils.get_active_filters(message.chat.id)
        if len(filters) == 0:
            text = 'Нет активных подписок'
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

    # Если хотим выбрать меню
    elif message.text == 'Меню':
        markup = utils.gen_inl_markup(utils.mode_menu, request.message_id, "menu")
        text = 'Выберите действие'

    # Если не знаем кнопки, то ничего не делаем
    else:
        text = 'Неизвестная команда'
    # Собираем сообщение и отправляем в чат
    bot.edit_message_text(chat_id=request.chat.id, text=text,
                          message_id=request.message_id, reply_markup=markup)


# Получаем тело фильра
def get_filter(chat_id, data):
    action, message_id, filter = data.split('_')
    if filter not in utils.get_all_filters(chat_id):
        text = "Выбранный фильтр не существует"
        bot.edit_message_text(chat_id=chat_id, text=text,
                              message_id=message_id)
    else:
        text = '...'
        text2 = 'Выберите фильтр'

        # Шлем сообщение, которое будем изменять
        reply = bot.send_message(chat_id=chat_id, text=text)
        if action == 'delete':
            text = utils.delete_filter(chat_id, filter, 'purged')
            text2 = 'Выберите фильтр для удаления'
            markup = utils.gen_inl_filters('get_all_filters', chat_id, reply.message_id, action)
        elif action == 'edit':
            markup = None
            if filter == 'Без категории':
                text = 'Вы не можете редактировать значение фильтра по умолчанию'
                utils.toggle_mode(chat_id, 'edit')
            else:
                utils.toggle_mode(chat_id, filter)
                text = "Редактирование фильтра %s\nТекущее значение:\n%s" % (
                    filter, utils.get_filter(chat_id, filter))
                text2 = "Введите регулярное выражение\nhttps://devaka.ru/wp-content/uploads/2014/06/1599.png"
        else:
            text = "Фильтр %s:\n%s" % (filter, utils.get_filter(chat_id, filter))
            text2 = 'Выберите фильтр для просмотра'
            markup = utils.gen_inl_filters('get_all_filters', chat_id, reply.message_id, action)

        if action in ['show', 'delete']:
            bot.edit_message_text(chat_id=chat_id, text=text2,
                                  message_id=reply.message_id, reply_markup=markup)

            bot.edit_message_text(chat_id=chat_id, text=text,
                                  message_id=message_id)
        elif action == "edit":
            bot.edit_message_text(chat_id=chat_id, text=text,
                                  message_id=reply.message_id, reply_markup=markup)
            if filter != 'Без категории':
                bot.send_message(chat_id, text=text2, reply_markup=utils.gen_markup(utils.cancel))
    return


# Активируем или деактивируем фильтр
def control_filter(chat_id, data):
    action, message_id, filter = data.split('_')
    if filter not in utils.get_all_filters(chat_id):
        text = "Выбранная подписка не существует"
        bot.edit_message_text(chat_id=chat_id, text=text,
                              message_id=message_id)
    else:
        reply = bot.send_message(chat_id=chat_id, text='...')
        # Если фильтр есть в неактивных, то включаем его
        if filter in utils.get_active_filters(chat_id):
            text = utils.unset_filter(chat_id, filter)
            mark_func = 'get_active_filters'
            text2 = "Нет активных подписок"
        else:
            text = utils.set_filter(chat_id, filter)
            mark_func = 'get_inactive_filters'
            text2 = "Нет доступных подписок"
        markup = utils.gen_inl_filters(mark_func, chat_id, reply.message_id, 'control')
        if markup is not None:
            text2 = "Выберите подписку"

        # Собираем сообщение и изменяем первое сообщение
        bot.edit_message_text(chat_id=chat_id, text=text2,
                              message_id=reply.message_id, reply_markup=markup)

        bot.edit_message_text(chat_id=chat_id, text=text,
                              message_id=message_id)
    return


# Обработка запросов на получение статистики:
def get_stat(chat_id, data):
    offset = int(data('_')[1])
    filter = data('_')[2]
    alarms = utils.get_alarm_by_filter(chat_id, filter)
    raw_alarms = []
    for a in alarms:
        event_id = a.split(':')[3]
        buffer = utils.from_buffer(chat_id, event_id)
        buffer['id'] = event_id
        raw_alarms.append(buffer)
    sorted_alarms = sorted(raw_alarms, key=itemgetter('time'), reverse=True)
    for s in reversed(sorted_alarms[offset:offset + 5]):
        title = '%s\n%s' % (s["time"], s["title"])
        send_to_chat(chat_id, title, s['id'])
    remains = len(sorted_alarms) - (offset + 5)
    if remains > 0:
        bot.send_message(chat_id, "Осталось сообщений: %s" % remains,
                         reply_markup=utils.get_counter(chat_id, offset + 5, filter))
    return


# Обработка запросов на получение подробной информации:
def show_body(chat_id, data):
    # Извлекаем действие, id события и id сообщения для обновления
    action, event_id, msg_id = str(data).split('_')
    msg_id = int(msg_id)
    # Получаем имя фильтра по id сообщения
    filter = utils.get_filter_by_id(chat_id, event_id)
    # Выгружаем из буфера сообщение с нужным id
    buffer = utils.from_buffer(chat_id, event_id)
    # Если сообщение с искомым id еще находится в буфере, то формируем тело сообщение согласно action
    if buffer is not None:
        title = ('%s\n%s') % (buffer["time"], buffer["title"])
        body = buffer["body"]

        if action == 'show':
            markup = utils.hide_event_data(event_id, msg_id)
            text = "<b>%s</b>\n%s\n%s" % (filter, title, body)
        else:
            markup = utils.get_event_data(event_id, msg_id)
            text = "<b>%s</b>\n%s\n" % (filter, title)
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML',
                              reply_markup=markup)
    # Если сообщения было удалено из буфера, то генерим соответсвующий ответ
    else:
        bot.send_message(chat_id, 'Сообщение было удалено по таймауту', reply_to_message_id=msg_id)
    return


def show_menu(chat_id, data):
    action, message_id, menu = data.split('_')
    text = '...'
    if menu == 'Режим просмотра':
        markup = utils.gen_markup(utils.main_menu)
        utils.toggle_mode(chat_id, 'track')
        text = 'Вы вошли в режим просмотра'
    elif menu == 'Режим настройки':
        markup = utils.gen_markup(utils.edit_menu)
        utils.toggle_mode(chat_id, 'edit')
        text = 'Вы вошли в режим редактирования'
    elif menu == 'Сброс настроек':
        utils.reset_user(chat_id)
        text = "/start - начать работу с ботом"
        markup = telebot.types.ReplyKeyboardRemove(selective=False)
    bot.delete_message(chat_id=chat_id, message_id=message_id)
    bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    return


# Обработка всех вызовов от инлайн кнопок
@bot.callback_query_handler(func=lambda call: True)
def sort_call(call):
    action = str(call.data).split('_')[0]
    chat_id = call.message.chat.id
    mode = utils.get_mode(chat_id)
    if mode == 'track':
        if action in ['show', 'hide']:
            show_body(chat_id, call.data)
        elif action == 'stat':
            get_stat(chat_id, call.data)
        elif action == 'control':
            control_filter(chat_id, call.data)
        elif action == 'menu':
            show_menu(chat_id, call.data)
    elif mode == 'edit':
        if action in ['show', 'edit', 'delete']:
            get_filter(chat_id, call.data)
        elif action == 'menu':
            show_menu(chat_id, call.data)


# Отправляем заголовок сообщения в нужный чат
def send_to_chat(chatid, title, event_id):
    filter = utils.get_filter_by_id(chatid, event_id)
    if utils.get_mode(chatid) != 'track':
        return
    text = "<b>%s</b>\n%s\n" % (filter, title)
    first = bot.send_message(parse_mode='HTML', chat_id=chatid, text=text)
    bot.edit_message_reply_markup(chat_id=chatid, message_id=first.message_id,
                                  reply_markup=utils.get_event_data(id, first.message_id))
    return


# Функция для старта поллинга бота
def start_telebot():
    while True:
        # try:
        print('Running telegram bot listener')
        bot.polling(none_stop=True)
        # except Exception:
        #   continue


# Обрабатываем очередь в пуле в 10 потоков
def queue_check():
    while True:
        try:
            queue = utils.qbus
            parser_threads = utils.build_worker_pool(utils.Parser, queue, 10)

            for worker in parser_threads:
                worker.join()

        except Exception:
            print("error")
            continue


# Стартуем 3 потока: для поллинга телеграм API,json-rpc сервер и обработки очередей.
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
