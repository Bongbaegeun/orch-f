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
NFVO engine, implementing all the methods for the creation, deletion and management of vnfs, scenarios and instances
'''
__author__="Jechan Han"
__date__ ="$05-Nov-2015 22:05:01$"

import json
import yaml
import os
import uuid as myUuid
import time, datetime
import sys
import threading

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found,\
    HTTP_Conflict
import db.orch_db_manager as orch_dbm

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

global global_config

####################################################    for KT One-Box Service   #############################################
def new_sw(mydb, sw_info, filter_data=None):
    log.debug("IN")
    log.debug("new_sw: %s" %str(sw_info))
    
    if 'metadata' in sw_info and type(sw_info.get('metadata')) != str:
        #TODO: transfer to String
        pass
    result, sw_id = orch_dbm.insert_swrepo_sw(mydb, sw_info) 
    if result < 0:
        log.error("failed to insert a S/W into Software Repository: %d %s" %(result, sw_id))
    
    return result, sw_id

def get_sw_list(mydb):
    result, content = orch_dbm.get_swrepo_sw_list(mydb)
    
    if result < 0:
        log.error("Failed to get S/W List from Software Repository: %d, %s" %(result, content))
    elif result == 0:
        return -HTTP_Not_Found, "No S/W Found"
    
    return result, content

def get_sw_id(mydb, sw_id):
    result, data = orch_dbm.get_swrepo_sw_id(mydb, sw_id)
    
    if result < 0:
        log.error("Failed to get S/W Info from Software Repository: %d, %s" %(result, data))
    elif result == 0:
        return -HTTP_Not_Found, "The S/W Not Found"
    
    return result, data
    
def delete_sw_id(mydb, sw_id):
    result, data = get_sw_id(mydb, sw_id)
    if result < 0:
        log.error("failed to delete the S/W: %d %s" %(result, data))
        return result, data

    result, sw_id = orch_dbm.delete_swrepo_sw_id(mydb, data['seq'])
    if result < 0:
        log.error("failed to delete the DB record: %s" %sw_id)
        return result, sw_id
    
    return 200, data['seq']