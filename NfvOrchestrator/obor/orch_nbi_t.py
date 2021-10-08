# -*- coding: utf-8 -*-

##
# kt GiGA One-Box Orchestrator version 1.0
#
# Copyright 2016 kt corp. All right reserved
#
# This is a proprietary software of kt corp, and you may not use this file
# except in compliance with license agreement with kt corp.
#
# Any redistribution or use of this software, with or without modification
# shall be strictly prohibited without prior written approval of kt corp,
# and the copyright notice above does not evidence any actual or intended
# publication of such software.
##

"""
HTTP server implementing the orchestrator API using the Tornado. It will answer to POST, PUT, GET methods in the appropriate URLs
and will use the nfvo.py module to run the appropriate method.
Every YAML/JSON file is checked against a schema in openmano_schemas.py module.  
"""
__author__="Jechan Han"
__date__ ="$30-oct-2015 09:07:15$"

import threading
import os

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application

import utils.log_manager as log_manager
from handlers_t import license_handler
from handlers_t import nfv_nsr_handler
from handlers_t import nfv_onboarding_handler
from handlers_t import roadshow_handler
from handlers_t import server_handler
from handlers_t import serviceorder_handler
from handlers_t import swrepo_handler
from handlers_t import user_handler

from engine import event_manager

# HA handler
from handlers_t import ha_handler

# test handler
from handlers_t import pnf_test_handler

# wf handler
from handlers_t import wf_handler


log = log_manager.LogManager.get_instance()

# global mydb
# global url_base
# url_base="/orch"

def makeApp(plugins):
    urls = []
    
    urls += user_handler.url()
    urls += server_handler.url(plugins)
    urls += roadshow_handler.url()
    urls += nfv_onboarding_handler.url(plugins)
    urls += nfv_nsr_handler.url(plugins)
    urls += swrepo_handler.url()
    urls += license_handler.url()
    urls += serviceorder_handler.url(plugins)

    # HA handler (2020.01.17 Bong)
    urls += ha_handler.url()

    # test handler
    urls += pnf_test_handler.url()

    # Work Flow Handler (2019.02.15 Bong)
    urls += wf_handler.url(plugins)

    log.info("[NBI-Tornado] URLs = %s" %str(urls))
    app = Application(urls)

    return app

def get_ssl_options():
    ssl_opt_dict = None
    OB_SSL_CERT_FILEPATH = "/var/onebox/key/svr_crt.pem"
    OB_SSL_KEY_FILEPATH = "/var/onebox/key/svr_key.pem"
    
    DEFAULT_SSL_CERT_FILEPATH = str(os.getcwd()) + "/ssl/default_ssl_crt.pem"
    DEFAULT_SSL_KEY_FILEPATH = str(os.getcwd()) + "/ssl/default_ssl_key.pem"
        
    if os.path.exists(OB_SSL_CERT_FILEPATH) == True and os.path.exists(OB_SSL_KEY_FILEPATH) == True:
        log.debug("Use One-Box SSL CERT and KEY")
        ssl_opt_dict = {"certfile": OB_SSL_CERT_FILEPATH, "keyfile": OB_SSL_KEY_FILEPATH}
    elif os.path.exists(DEFAULT_SSL_CERT_FILEPATH) == True and os.path.exists(DEFAULT_SSL_KEY_FILEPATH) == True:
        log.debug("Use Default SSL CERT and KEY")
        ssl_opt_dict = {"certfile": DEFAULT_SSL_CERT_FILEPATH, "keyfile": DEFAULT_SSL_KEY_FILEPATH}
    else:
        log.debug("No SSL Certifcate and Key File exist")

    return ssl_opt_dict

class httpserver(threading.Thread):
    def __init__(self, host, port, proc_num, ssl_enable =True, plugins=None):
        threading.Thread.__init__(self)
        
        self.host = host
        self.port = port
        self.proc_num = proc_num
        
        self.ssl_opt = get_ssl_options()

        if ssl_enable is False or self.ssl_opt is None:
            log.info("API Server: HTTP")
            self.svr = HTTPServer(makeApp(plugins))
        else:
            log.info("API Server: HTTPS")

            # self.ssl_opt["ssl_version"] = ssl.OP_NO_SSLv3
            self.ssl_opt["ciphers"] = "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-DSS-AES128-GCM-SHA256:kEDH+AESGCM:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-ECDSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-DSS-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-DSS-AES256-SHA:DHE-RSA-AES256-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK"

            self.svr = HTTPServer(makeApp(plugins), ssl_options=self.ssl_opt, max_buffer_size=(1024*1024*1024*2))
        
        self.svr.bind(self.port)
        self.svr.start(self.proc_num)

        log.info("Tornado httpserver is created!")
        
    def run(self):
        log.info("Tornado httpserver started!")
        IOLoop.current().start()
