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
Created on Jan 28, 2016

@author: ngkim
'''

import sys

from db import orch_db

from utils.config_manager import ConfigManager
import utils.log_manager as log_manager
from utils.aes_chiper import AESCipher
logger = log_manager.LogManager.get_instance()

class DBConnectionManager:
    _instance = None
    
    def __init__(self, config_file = ""):
        
        # Initialize DB connection
        cfgManager = ConfigManager.get_instance()
        global_config = cfgManager.get_config()

        cipher = AESCipher.get_instance()
        db_passwd = cipher.decrypt(global_config['db_passwd'])
        
        self.dbconn = orch_db.orch_db(global_config['db_host'], global_config['db_user'], db_passwd, global_config['db_name'], global_config['db_port'])

        # if self.dbconn.connect(global_config['db_host'], global_config['db_user'], global_config['db_passwd'], global_config['db_name'], global_config['db_port']) == -1:
        #     logger.error("Error connecting to database %s at %s(%s) @ %s:%s" % (global_config['db_name'], global_config['db_user'], global_config['db_passwd'], global_config['db_host'], global_config['db_port']))
        #     exit(-1)
    
    def getConnection(self):
        return self.dbconn
    
    @classmethod
    def get_instance(cls, config_file = ""):
        if not cls._instance:
            cls._instance = cls(config_file)
        return cls._instance

if __name__ == '__main__':
    pass