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

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found,\
    HTTP_Conflict
import db.orch_db_manager as orch_dbm

from engine.license_status import LicenseStatus

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

####################################################    for KT One-Box Service   #############################################
def new_license(mydb, license_info, filter_data=None):
    log.debug("IN")
    log.debug("new_license: %s" %str(license_info))
    
    license_dict = {}
    
    license_dict['name'] = license_info['name']
    license_dict['nfcatseq'] = license_info['vnfd_id']
    license_dict['status'] = LicenseStatus.AVAIL
    license_dict['type'] = license_info.get('type', "key")
    if 'vendor' in license_info: license_dict['vendor'] = license_info['vendor']
    
    req_num = len(license_info['values'])
    add_num = 0
    for value in license_info['values']:
        
        #TODO: use request value
        if len(value) < 20:
            value = af.create_uuid()
        license_dict['value'] = value
        
        result, lp_id = orch_dbm.insert_license_pool(mydb, license_dict)
        if result < 0:
            log.error("failed to insert a record for new license: %d %s" %(result, lp_id))
        else:
            add_num += 1
    
    log.debug("new_license OUT: reqeusted no = %d, added no = %d" %(req_num, add_num))
    
    return 200, add_num

def get_license_list(mydb, condition=None):
    filter_dict={}
    if condition:
        if type(condition) is int or type(condition) is long:
            filter_dict['nfcatseq'] = condition
        elif type(condition) is str and condition.isdigit():
            filter_dict['nfcatseq'] = condition
        elif type(condition) is str:
            log.debug("[HJC] get_license_list condition 3 = %s" %str(condition))
            filter_dict['name'] = condition
        else:
            log.error("Invalid Identifier: %s, Use NFCatalog Seq." %str(condition))
            return -HTTP_Bad_Request, "Invalid Identifier: Use NFCatalog Seq."
    
    result, data = orch_dbm.get_license_pool(mydb, filter_dict)
    if result < 0:
        log.error("Failed to get License Data: %d, %s" %(result, data))
    elif result == 0:
        return -HTTP_Not_Found, "No License Found"
    
    return result, data
    
def get_license_of_value(mydb, value):
    filter_dict = {'value': value}
    
    result, data = orch_dbm.get_license_pool(mydb, filter_dict)
    if result < 0:
        log.error("Failed to get License Data: %d, %s" %(result, data))
    elif result == 0:
        return -HTTP_Not_Found, "No License Found"
    
    return result, data[0]

def get_license_list_of_nfr(mydb, nfseq):
    filter_dict = {'nfseq': nfseq}
    
    result, data = orch_dbm.get_license_pool(mydb, filter_dict)
    if result < 0:
        log.error("Failed to get License Data: %d, %s" %(result, data))
    elif result == 0:
        return -HTTP_Not_Found, "No License Found"
    
    return result, data

# def get_license_list_of_nfd(mydb, nfcatseq):
#     filter_dict = {'nfcatseq': nfcatseq}
#
#     result, data = orch_dbm.get_license_pool(mydb, filter_dict)
#     if result < 0:
#         log.error("Failed to get License Data: %d, %s" %(result, data))
#     elif result == 0:
#         return -HTTP_Not_Found, "No License Found"
#
#     return result, data

def _update_license(mydb, license_info):
    result, data = orch_dbm.update_license_pool(mydb, license_info)
    
    return result, data

def take_license(mydb, license_info):
    license_info['status'] = LicenseStatus.USED
    
    return _update_license(mydb, license_info)

def return_license(mydb, license):
    result, data = get_license_of_value(mydb, license)
    
    if result < 0:
        log.error("Failed to get License Info. %d %s" %(result, data))
        return result, data
    
    data['status'] = LicenseStatus.AVAIL
    data['nfseq'] = None
    return _update_license(mydb, data)
        
    
def check_license(mydb, license):    
    result, data = get_license_of_value(mydb, license)
    if result > 0: # and data.get('status') == LicenseStatus.USED:
        return True
    
    return False

def update_license(mydb, license, update_info):
    result, target_license = get_license_of_value(mydb, license)
    if result < 0:
        log.error("Failed to get License Data: %d, %s" %(result, target_license))
        return -HTTP_Internal_Server_Error, "Failed to get license data from DB"
    elif result == 0:
        return -HTTP_Not_Found, "No license found for the VNF "
    
    if 'nfseq' in update_info:
        target_license['nfseq'] = update_info['nfseq']
    if 'nfcatseq' in update_info:
        target_license['nfcatseq'] = update_info['nfcatseq']
    if 'status' in update_info:
        target_license['status'] = update_info['status']
    
    result, content = _update_license(mydb, target_license)
    if result < 0:
        log.error("failed to update license info: %d %s" %(result, str(content)))
    
    return result, content

def get_license_available(mydb, condition):
    result, data = get_license_list(mydb, condition)
    if result < 0:
        log.error("Failed to get License Data: %d, %s" %(result, data))
        return -HTTP_Internal_Server_Error, "Failed to get license data from DB"
    elif result == 0:
        return -HTTP_Not_Found, "No license found for the VNF "
    
    for lk in data:
        if lk['status'] == LicenseStatus.AVAIL:
            return 200, lk
    
    return -HTTP_Not_Found, "No avaiable license found"
    
def delete_license(mydb, license):
    filter_dict = {'seq': license}
    result, data = orch_dbm.get_license_pool(mydb, filter_dict)
    if result < 0:
        log.error("failed to delete the license %s" %data)
        return result, data

    result, lp_id = orch_dbm.delete_license_pool(mydb, data['seq'])
    if result < 0:
        log.error("failed to delete the DB record for %s" %license)
        return result, lp_id
    
    data={"license":data['seq']}
    return 200, data