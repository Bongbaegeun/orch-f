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

import os, yaml
import sys
from utils import auxiliary_functions as af
from orch_schemas import config_schema
from jsonschema import validate as js_v, exceptions as js_e

import utils.log_manager as log_manager
logger = log_manager.LogManager.get_instance()

class ConfigManager():
    _instance = None
    
    def __init__(self, config_file = ""):
        self.config_file = config_file
        (r, self.config) = self.load_configuration()
        
        if not r:
            logger.error("Error: %s" %str(self.config))
            exit(-1)
        
    def get_config(self):
        return self.config
        
    def load_configuration(self):
        default_tokens ={'http_port':9090, 'http_host':'localhost'}
        try:
            #Check config file exists
            if not os.path.isfile(self.config_file):
                return (False, "Error: Configuration file '"+self.config_file+"' does not exists.")
                
            #Read file
            (return_status, code) = af.read_file(self.config_file)
            if not return_status:
                return (return_status, "Error loading configuration file '"+self.config_file+"': "+code)
            #Parse configuration file
            try:
                config = yaml.load(code)
            except yaml.YAMLError, exc:
                error_pos = ""
                if hasattr(exc, 'problem_mark'):
                    mark = exc.problem_mark
                    error_pos = " at position: (%s:%s)" % (mark.line+1, mark.column+1)
                return (False, "Error loading configuration file '"+self.config_file+"'"+error_pos+": content format error: Failed to parse yaml format")
    
            #Validate configuration file with the config_schema
            try:
                js_v(config, config_schema)
            except js_e.ValidationError, exc:
                error_pos = ""
                if len(exc.path)>0: error_pos=" at '" + ":".join(map(str, exc.path))+"'"
                return False, "Error loading configuration file '"+self.config_file+"'"+error_pos+": "+exc.message 
            
            #Check default values tokens
            for k,v in default_tokens.items():
                if k not in config: config[k]=v
        
        except Exception,e:
            return (False, "Error loading configuration file '"+self.config_file+"': "+str(e))
                    
        return (True, config)
    
    @classmethod
    def get_instance(cls, config_file = "obord.cfg"):
        if not cls._instance:
            cls._instance = cls(config_file)
        return cls._instance