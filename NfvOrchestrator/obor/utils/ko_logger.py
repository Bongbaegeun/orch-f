#!/usr/bin/env python
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

'''
KT One-Box Logger implementing the logging methods using python-logging library. 
It supports 4 basic levels, debug, info, warning, error, critical, and 
1 custom level, e2e which is for recording E-to-E trace logs about the main workflow of KT One-Box Orchestrator and has the highest level number.
To record e2e logs, call the method, .ete().
'''
__author__="Jechan Han"
__date__ ="$27-aug-2015 09:40:15$"

import sys, os
import inspect
import logging
from logging import handlers
from utils.cloghandler import ConcurrentRotatingFileHandler

# add a custom log level for e2e trace logs
E2E_LOG_LEVEL_NUMBER = 100
E2E_LOG_LEVEL_NAME = "E2E"

logging.addLevelName(E2E_LOG_LEVEL_NUMBER, "E2E")
def e2e(self, message, *args, **kws):
    self._log(E2E_LOG_LEVEL_NUMBER, message, args, **kws)
logging.Logger.e2e=e2e


def singleton(klass):
    if not klass._instance:
        klass._instance = klass()
        
    return klass._instance

class ko_logger():
    _instance = None
    
    def __init__(self, tag="orch", logdir="/var/log/onebox/", loglevel="debug", logConsole=False):
        self.tag    = tag
        self.logdir = logdir
        self.loglevel = loglevel
        
        self.log_fname = "%s.log" % (self.tag)
        self.errlog_fname = "%s.err" % (self.tag)
        self.e2e_fname = "%s.e2e" % (self.tag)

        #script_dir = os.path.dirname(inspect.stack()[-1][1])
        #logdir = os.path.join(script_dir, 'log')

        if os.path.exists(self.logdir):
            self.filelog_file_path = os.path.join(self.logdir, self.log_fname)
            self.errlog_file_path  = os.path.join(self.logdir, self.errlog_fname)
            self.e2elog_file_path = os.path.join(self.logdir, self.e2e_fname)
        else:
            try:
                os.makedirs(self.logdir)
            except Exception, err:
                self.logdir = "/var/log/"

            self.filelog_file_path = os.path.join(self.logdir, self.log_fname)
            self.errlog_file_path  = os.path.join(self.logdir, self.errlog_fname)
            self.e2elog_file_path = os.path.join(self.logdir, self.e2e_fname)
        
        self.logger = logging.getLogger(self.tag)

        if self.loglevel == "debug":
            self.logger.setLevel(logging.DEBUG)
        elif self.loglevel == "info":
            self.logger.setLevel(logging.INFO)
        elif self.loglevel == "warning":
            self.logger.setLevel(logging.WARN)
        elif self.loglevel == "error":
            self.logger.setLevel(logging.ERROR)
        elif self.loglevel == "critical":
            self.logger.setLevel(logging.CRITICAL)
        else:
            self.logger.setLevel(logging.INFO)

        self._set_error_log_env(self.errlog_file_path)
        self._set_file_log_env(self.filelog_file_path)
        self._set_e2e_log_env(self.e2elog_file_path)

        if logConsole:
            self._set_console_log_env()

    def get_instance(self):
        return self.logger

    def _set_error_log_env(self, logfile):

        errfmt = logging.Formatter("%(asctime)s [%(process)s/%(threadName)s/%(funcName)s:%(lineno)03d] %(levelname)-5s: %(message)s")

        maxbytes = 1024 * 1024 * 100  # 100MB
        error_handler = ConcurrentRotatingFileHandler(logfile, maxBytes=maxbytes, backupCount=5)
        # error_handler = handlers.RotatingFileHandler(logfile, maxBytes=maxbytes, backupCount=5)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(errfmt)

        self.logger.addHandler(error_handler)

    def _set_e2e_log_env(self, logfile):

        e2efmt = logging.Formatter("%(asctime)s %(levelname)-5s: %(message)s")

        maxbytes = 1024 * 1024 * 500  # 100MB
        e2e_handler = ConcurrentRotatingFileHandler(logfile, maxBytes=maxbytes, backupCount=5)
        # e2e_handler = handlers.RotatingFileHandler(logfile, maxBytes=maxbytes, backupCount=5)
        e2e_handler.setLevel(E2E_LOG_LEVEL_NUMBER)
        e2e_handler.setFormatter(e2efmt)

        self.logger.addHandler(e2e_handler)

    def _set_file_log_env(self, logfile):
        if self.loglevel == "debug":
            stdfmt = logging.Formatter("%(asctime)s [%(process)s/%(threadName)s-%(filename)s/%(funcName)s:%(lineno)03d] %(levelname)-5s: %(message)s")
        else:
            stdfmt = logging.Formatter("%(asctime)s %(levelname)-5s %(filename)s: %(message)s")
            
        maxbytes = 1024 * 1024 * 100  # 100MB
        filelog_handler = ConcurrentRotatingFileHandler(logfile, maxBytes=maxbytes, backupCount=10)
        # filelog_handler = handlers.RotatingFileHandler(logfile, maxBytes=maxbytes, backupCount=10)
        #filelog_handler = handlers.TimedRotatingFileHandler(logfile, when="midnight", backupCount=10)
        filelog_handler.setFormatter(stdfmt)

        self.logger.addHandler(filelog_handler)

    def _set_console_log_env(self):
        stdfmt = logging.Formatter("%(asctime)s %(levelname)-5s: %(message)s")
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(stdfmt)
        self.logger.addHandler(stdout_handler)

if __name__ == '__main__':

    #log = ko_logger(tag='orch_test', logdir='./log', loglevel='debug', logConsole=True).get_instance()
    #log = singleton(ko_logger(tag='orch_test', logdir='./log', loglevel='debug', logConsole=True)).get_instance()
    log = singleton(ko_logger).get_instance()

    log.debug("debug message %s" % "test msg for debug")
    log.info("info message %s" % "test msg for info")
    log.e2e("E-to-E message %s" % "[NA][NA] test msg for E2E")
    log.propagate = False
    log.error("error message %s" % "test msg for error")
    log.propagate = True
    log.error("error message %s" % "test msg for error2")
    kw = {'key':'val','key1':'val2'}
    log.debug("debug kw %s", kw)
