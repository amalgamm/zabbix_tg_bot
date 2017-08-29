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
this = sys.modules[__name__]


# Ловим команду для старта
@bot.message_handler(commands=['start'])
def start(message):
    print("bot started with %s %s" % (message.chat.username, message.chat.id))
    utils.new_user(message.chat.id)
    bot.send_message(message.chat.id,
                     "Ваш ID:\n%s" % message.chat.id,
                     reply_markup=utils.gen_markup(utils.start_menu))
    main_message = bot.send_message(chat_id=message.chat.id, text="Перед использованием настройте фильтры")
    markup = utils.gen_inl_markup(utils.main_menu, main_message.message_id, "menu")
    bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=main_message.message_id, reply_markup=markup)


# Работа с текстом в режиме ввода имени фильтра
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'input_name', content_types=["text"])
def input_name(message):
    main_message = bot.send_message(message.chat.id, '...')
    markup = None
    if message.text == 'Отмена':
        utils.toggle_mode(message.chat.id, 'track')
        text = 'Создание отменено'
        markup = utils.gen_inl_markup(utils.edit_menu, main_message.message_id, "edit-menu", "Назад")
    else:
        rule = message.text
        if len(rule) > 20:
            text = 'Длина имени фильтра не должна превышать 20 знаков'
        elif ":" in rule or "_" in rule:
            text = 'Использование символов \":\" и \"_\" в названии фильтра недопустимо'
        else:
            if rule not in utils.get_all_rules(message.chat.id):
                utils.create_rule(message.chat.id, rule)
                utils.toggle_mode(message.chat.id, rule)
                text = 'Введите регулярное выражение для фильтра %s\n' \
                       'https://devaka.ru/wp-content/uploads/2014/06/1599.png' % rule
            else:
                text = 'Фильтр %s уже существует, выберите другое имя' % rule
    bot.edit_message_text(chat_id=message.chat.id, text=text, message_id=main_message.message_id, reply_markup=markup)


# Работа с текстом в режиме ввода регулярного выражения
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) in utils.get_all_rules(message.chat.id),
                     content_types=["text"])
def input_regex(message):
    if message.text == 'Отмена':
        rule = utils.get_mode(message.chat.id)
        utils.toggle_mode(message.chat.id, 'track')
        if rule in utils.get_new_rules(message.chat.id):
            utils.delete_rule(message.chat.id, rule, 'canceled')
        text = 'Изменение отменено'
    else:
        try:
            re.compile(message.text)
            is_valid = True
        except re.error:
            is_valid = False
        if is_valid is True:
            rule = utils.get_mode(message.chat.id)
            utils.edit_rule(message.chat.id, rule, message.text)
            utils.toggle_mode(message.chat.id, 'track')
            if rule in utils.get_new_rules(message.chat.id):
                utils.delete_rule(message.chat.id, rule, 'new')
                text = 'Фильтр %s успешно создан' % rule
            else:
                text = 'Фильтр %s успешно изменен' % rule
        else:
            text = 'Некорректное регулярное выражение, введите корректное значение'
    bot.send_message(message.chat.id, text, reply_markup=utils.gen_markup(utils.start_menu))
    main_message = bot.send_message(message.chat.id, '...')
    markup = utils.gen_inl_markup(utils.edit_menu, main_message.message_id, "edit-menu", "Назад")
    bot.edit_message_text(chat_id=message.chat.id, text='Выберите действие', message_id=main_message.message_id,
                          reply_markup=markup)


# Работа с текстом в режиме импорта фильтров
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) == 'import', content_types=["text"])
def import_state(message):
    if message.text == 'Отмена':
        utils.toggle_mode(message.chat.id, 'track')
        text = 'Импорт отменен'
    else:
        import_data = message.text
        result = utils.import_rules(message.chat.id, import_data)
        if isinstance(result, dict):
            text = "Статус операции импорта по фильтрам:\n"
            for name, status in result.items():
                text += '%s: %s\n' % (name, status)
        else:
            text = result
        utils.toggle_mode(message.chat.id, 'track')
    bot.send_message(message.chat.id, text, reply_markup=utils.gen_markup(utils.start_menu))
    main_message = bot.send_message(message.chat.id, '...')
    markup = utils.gen_inl_markup(utils.edit_menu, main_message.message_id, "edit-menu", "Назад")
    bot.edit_message_text(chat_id=message.chat.id, text='Выберите действие', message_id=main_message.message_id,
                          reply_markup=markup)


# Если хотим выбрать меню
@bot.message_handler(func=lambda message: utils.get_mode(message.chat.id) in ['track', 'edit'], content_types=["text"])
def print_menu(message):
    if message.text == 'Меню':
        main_message = bot.send_message(chat_id=message.chat.id, text="Выберите действие")
        markup = utils.gen_inl_markup(utils.main_menu, main_message.message_id, "menu")
        bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=main_message.message_id, reply_markup=markup)


# Работа с кнопками в режиме настроек
def edit_menu(chat_id, data):
    action, message_id, menu = data.split('_')
    # Текст и кнопки по умолчанию
    text = 'Неизвестная команда'
    text2 = '...'
    markup = None
    # Печатаем сообщение которое будем изменять
    # Если хотим активировать фильтр
    if menu == 'Посмотреть фильтр':
        markup = utils.gen_inl_rules_markup('get_all_rules', chat_id, message_id, 'view', 'Режим настройки')
        if markup is None:
            text = "Нет доступных фильтров"
        else:
            text = "Выберите фильтр для просмотра"

    # Если хотим деактивировать фильтр
    elif menu == 'Добавить фильтр':
        utils.toggle_mode(chat_id, 'input_name')
        text = "Cоздание нового фильтра"
        text2 = "Введите имя фильтра (не более 20 символов)\n использование символов \":\" и \"_\" недопустимо"

    # Если хотим посмотреть активные фильры
    elif menu == 'Редактировать фильтр':
        markup = utils.gen_inl_rules_markup('get_all_rules', chat_id, message_id, 'edit', 'Режим настройки')
        if markup is None:
            text = "Нет доступных фильтров"
        else:
            text = "Выберите фильтр для редактирования"

    # Если хотим посмотреть историю событий
    elif menu == 'Удалить фильтр':
        markup = utils.gen_inl_rules_markup('get_all_rules', chat_id, message_id, 'delete', 'Режим настройки')
        if markup is None:
            text = "Нет доступных подписок"
        else:
            text = "Выберите фильтр для удаления"

    # Если экспортировать свои фильтры
    elif menu == 'Экспорт':
        text = 'Данные для эскпорта:\n'
        text += utils.export_rules(chat_id)
        markup = utils.gen_inl_markup([], message_id, "edit-menu", "Режим настройки")

        # Если импортировать фильтры
    elif menu == 'Импорт':
        text = 'Импорт фильтров'
        text2 = 'Введите данные для импорта в формате {"filer1":"regexp1","filter2":"regexp2"}'
        utils.toggle_mode(chat_id, 'import')

    bot.edit_message_text(chat_id=chat_id, text=text,
                          message_id=message_id, reply_markup=markup)
    if menu == 'Добавить фильтр' or menu == 'Импорт':
        bot.send_message(chat_id, text=text2, reply_markup=utils.gen_markup(utils.cancel))

        # Работа с кнопками в режиме просмотра


# Работа с кнопками в режиме просмотра
def track_menu(chat_id, data):
    action, message_id, menu = data.split('_')
    # Текст и кнопки по умолчанию
    text = 'Неизвестная команда'
    markup = None
    # Если хотим активировать фильтр
    if menu == 'Подписаться':
        markup = utils.gen_inl_rules_markup('get_inactive_rules', chat_id, message_id, 'control', 'Режим просмотра')
        if len(markup.to_dic()['inline_keyboard']) == 1:
            text = "Нет доступных подписок"
        else:
            text = "Выберите подписку"

    # Если хотим деактивировать фильтр
    elif menu == 'Отписаться':
        markup = utils.gen_inl_rules_markup('get_active_rules', chat_id, message_id, 'control', 'Режим просмотра')
        if len(markup.to_dic()['inline_keyboard']) == 1:
            text = "Нет активных подписок"
        else:
            text = "Выберите подписку"

    # Если хотим посмотреть активные фильры
    elif menu == 'Активные подписки':
        text = 'Активные подписки:\n'
        filters = utils.get_active_rules(chat_id)
        markup = utils.gen_inl_markup([], message_id, "track-menu", "Режим просмотра")
        if len(filters) == 0:
            text = 'Нет активных подписок'
        else:
            for f in filters:
                text += f + '\n'

    # Если хотим посмотреть историю событий
    elif menu == 'История событий':
        markup = utils.get_counter(chat_id)
        if markup is False:
            text = "За последние сутки не произошло ни одного события"
            markup = utils.gen_inl_markup([], message_id, "track-menu", "Режим просмотра")
        else:
            text = 'Статистика по всем фильтрам за последние 24 часа:\n'

    # Если не знаем кнопки, то ничего не делаем
    # Собираем сообщение и отправляем в чат
    bot.edit_message_text(chat_id=chat_id, text=text,
                          message_id=message_id, reply_markup=markup)


# Получаем тело фильра
def get_filter(chat_id, data):
    action, message_id, rule = data.split('_')
    if rule not in utils.get_all_rules(chat_id):
        text = "Выбранный фильтр не существует"
        bot.edit_message_text(chat_id=chat_id, text=text,
                              message_id=message_id)
    else:
        text = '...'
        text2 = 'Выберите фильтр'

        # Шлем сообщение, которое будем изменять
        reply = bot.send_message(chat_id=chat_id, text=text)
        if action == 'delete':
            text = utils.delete_rule(chat_id, rule, 'purged')
            text2 = 'Выберите фильтр для удаления'
            markup = utils.gen_inl_rules_markup('get_all_rules', chat_id, reply.message_id, action, 'Режим настройки')
        elif action == 'edit':
            markup = None
            if rule == 'Без категории':
                text = 'Вы не можете редактировать значение фильтра по умолчанию'
                utils.toggle_mode(chat_id, 'track')
            else:
                utils.toggle_mode(chat_id, rule)
                text2 = "Редактирование фильтра \"%s\"\n\nТекущее значение:\n%s" % (
                    rule, utils.get_rule_expr(chat_id, rule))
                text = "Введите регулярное выражение\nhttps://devaka.ru/wp-content/uploads/2014/06/1599.png"
        else:
            text = "Фильтр %s:\n%s" % (rule, utils.get_rule_expr(chat_id, rule))
            text2 = 'Выберите фильтр для просмотра'
            markup = utils.gen_inl_rules_markup('get_all_rules', chat_id, reply.message_id, action, 'Режим настройки')

        if action in ['view', 'delete']:
            bot.edit_message_text(chat_id=chat_id, text=text2,
                                  message_id=reply.message_id, reply_markup=markup)

            bot.edit_message_text(chat_id=chat_id, text=text,
                                  message_id=message_id)
        elif action == "edit":
            bot.edit_message_text(chat_id=chat_id, text=text,
                                  message_id=reply.message_id, reply_markup=markup)
            if rule != 'Без категории':
                bot.send_message(chat_id, text=text2, reply_markup=utils.gen_markup(utils.cancel))
    return


# Активируем или деактивируем фильтр
def control_filter(chat_id, data):
    action, message_id, rule = data.split('_')
    if rule not in utils.get_all_rules(chat_id):
        text = "Выбранная подписка не существует"
        bot.edit_message_text(chat_id=chat_id, text=text,
                              message_id=message_id)
    else:
        reply = bot.send_message(chat_id=chat_id, text='...')
        # Если фильтр есть в неактивных, то включаем его
        if rule in utils.get_active_rules(chat_id):
            text = utils.unsubscribe(chat_id, rule)
            mark_func = 'get_active_rules'
            text2 = "Нет активных подписок"
        else:
            text = utils.subscribe(chat_id, rule)
            mark_func = 'get_inactive_rules'
            text2 = "Нет доступных подписок"
        markup = utils.gen_inl_rules_markup(mark_func, chat_id, reply.message_id, 'control', 'Режим просмотра')
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
    offset = int(data.split('_')[1])
    rule = data.split('_')[2]
    alarms = utils.get_events_by_rule(chat_id, rule)
    raw_alarms = []
    for a in alarms:
        event_id = a.split(':')[3]
        buffer = utils.from_buffer(chat_id, event_id)
        buffer['id'] = event_id
        raw_alarms.append(buffer)
    sorted_alarms = sorted(raw_alarms, key=itemgetter('time'),reverse=True)
    for s in sorted_alarms[offset:offset + 5]:
        title = '%s\n%s' % (s["time"], s["title"])
        send_to_chat(chat_id, title, s['id'])
    remains = len(sorted_alarms) - (offset + 5)
    if remains > 0:
        bot.send_message(chat_id, "Осталось сообщений: %s" % remains,
                         reply_markup=utils.get_counter(chat_id, offset + 5, rule))
    return


# Обработка запросов на получение подробной информации:
def show_body(chat_id, data):
    # Извлекаем действие, id события и id сообщения для обновления
    action, message_id, event_id = str(data).split('_')
    message_id = int(message_id)
    # Выгружаем из буфера сообщение с нужным id
    buffer = utils.from_buffer(chat_id, event_id)
    print(buffer)
    # Если сообщение с искомым id еще находится в буфере, то формируем тело сообщение согласно action
    if buffer is not None:
        title = '%s\n%s' % (buffer["time"], buffer["title"])
        body = buffer["body"]

        if action == 'show':
            markup = utils.hide_event_data(event_id, message_id)
            text = "%s\n%s" % (title, body)
        else:
            markup = utils.get_event_data(event_id, message_id)
            text = "%s" % title
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode='HTML',
                              reply_markup=markup)
    # Если сообщения было удалено из буфера, то генерим соответсвующий ответ
    else:
        bot.send_message(chat_id, 'Сообщение было удалено по таймауту', reply_to_message_id=message_id)
    return


def show_menu(chat_id, data):
    action, message_id, menu = data.split('_')
    text = '...'
    markup = None
    if menu == 'Режим просмотра':
        markup = utils.gen_inl_markup(utils.track_menu, message_id, "track-menu", "Назад")
        utils.toggle_mode(chat_id, 'track')
        text = 'Вы вошли в режим просмотра'
    elif menu == 'Режим настройки':
        markup = utils.gen_inl_markup(utils.edit_menu, message_id, "edit-menu", "Назад")
        utils.toggle_mode(chat_id, 'track')
        text = 'Вы вошли в режим редактирования'
    elif menu == 'Сброс пользователя':
        text = "Сброс повлечет за собой полное удаление всех настроенных фильтров и истории сообщений\n" \
               "Вы уверены, что хотите произвести сброс?"
        markup = utils.gen_inl_markup(utils.reset_menu, message_id, "reset")
    elif menu == 'Назад':
        markup = utils.gen_inl_markup(utils.main_menu, message_id, "menu")
        text = 'Выберите действие'
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
    return


# Обработка всех вызовов от инлайн кнопок
@bot.callback_query_handler(func=lambda call: True)
def sort_call(call):
    action = str(call.data).split('_')[0]
    chat_id = call.message.chat.id
    actions = {
        'show': 'show_body',
        'hide': 'show_body',
        'stat': 'get_stat',
        'control': 'control_filter',
        'view': 'get_filter',
        'edit': 'get_filter',
        'delete': 'get_filter',
        'menu': 'show_menu',
        'track-menu': 'track_menu',
        'edit-menu': 'edit_menu',
        'reset': 'reset_user'
    }
    getattr(this, actions[action])(chat_id, call.data)
    return


def send_to_chat(chat_id, title, event_id):
    if utils.get_mode(chat_id) not in 'track':
        return
    text = "%s\n" % title
    first = bot.send_message(parse_mode='HTML', chat_id=chat_id, text=text)
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=first.message_id,
                                  reply_markup=utils.get_event_data(event_id, first.message_id))
    return


def remove_markup(chat_id):
    rm_id = bot.send_message(chat_id, '...',
                             reply_markup=telebot.types.ReplyKeyboardRemove(selective=False)).message_id
    bot.delete_message(chat_id, rm_id)


def reset_user(chat_id, data):
    action, message_id, choice = data.split('_')
    markup = None
    if choice == 'Да, я уверен':
        utils.reset_user(chat_id)
        text = "/start - начать работу с ботом"
        remove_markup(chat_id)
    else:
        markup = utils.gen_inl_markup(utils.main_menu, message_id, "menu")
        text = 'Выберите действие'
    bot.edit_message_text(chat_id=chat_id, text=text, message_id=message_id, reply_markup=markup)


# Функция для старта поллинга бота
def start_telebot():
    while True:
       # try:
            print('Running telegram bot listener')
            bot.polling(none_stop=True)
        #except Exception:
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
