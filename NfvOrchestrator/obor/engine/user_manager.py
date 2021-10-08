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

################################## Data Class ##################################
# NBI Name       Object Name     DB Name
# account_id      account_id     userid
# account_pw      account_pw     password
# name            name           username
# description     desc           description
# auth            auth           userauth
# org_name        org            orgnamescode
# cust_id         cust_id        customerseq
# role_id         role_id        role_id
# fail_count      fail_count     failcount
# fail_time       fail_time      failtime
#                                use_flag
#                                company_name
#                                company_num
#                                hp_num
#                                email
#                                dept_id
#                                dept_name
#                                emp_no
#                                birthdate
#                                address
#                                address_num
#                                company_gubun_flag
#                                detail_address
#                                modify_userid
################################## Data Schema ##################################





####################################################    for KT One-Box Service   #############################################
def new_user(mydb, user_dict):
    log.debug("IN")
    log.debug("new_user: %s" %str(user_dict))
    
    result, user_id = orch_dbm.insert_user(mydb, user_dict)
    if result < 0:
        log.error("failed to insert a record for new user: %s %s" %(result, user_id))
        return result, user_id
    
    log.debug("new_user OUT: %d %s" %(result, str(user_dict)))
    return 200, user_id

def delete_user(mydb, user):
    result, user_dict = orch_dbm.get_user_id(mydb, user)
    
    if result < 0:
        log.error("failed to delete the user %s. No record found" %user)
        return result, user_dict

    result, user_id = orch_dbm.delete_user_id(mydb, user_dict['userid'])
    if result < 0:
        log.error("failed to delete the record for the user %s" %user_dict['userid'])
        return result, user_id
    return 200, user_id