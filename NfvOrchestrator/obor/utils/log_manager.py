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
Created on Jan 30, 2016

@author: ngkim
'''

import sys

from utils.ko_logger import ko_logger

def singleton(klass):
    if not klass._instance:
        klass._instance = klass()
        
    return klass._instance

TITLE="NFV-ORCH-F"
LOG_DIR = "/var/log/onebox"

class LogManager():
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = ko_logger(tag=TITLE, logdir=LOG_DIR, loglevel="debug", logConsole=False).get_instance()
        return cls._instance

if __name__ == '__main__':
    pass