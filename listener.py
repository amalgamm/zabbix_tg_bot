#!/usr/bin/python3.5
# -*- coding: utf-8 -*-
import logging
import utils

from werkzeug.wrappers import Request, Response
from werkzeug.serving import run_simple
from jsonrpc import JSONRPCResponseManager, dispatcher
from config import listen_port, listen_int


@dispatcher.add_method
def sendAlarm(group='Empty group', title='Empty title', body='Empty body'):
    msg = [group, title, body]
    logging.warning((msg))
    utils.qbus.put(msg)
    return "OK"


manager = JSONRPCResponseManager()


@Request.application
def application(request):
    response = manager.handle(request.get_data(cache=False, as_text=True), dispatcher)
    return Response(response.json, mimetype='application/json')


def start_listener():
    while True:
        try:
            run_simple(hostname=listen_int, port=listen_port, application=application, threaded=True)
        except Exception:
            continue
