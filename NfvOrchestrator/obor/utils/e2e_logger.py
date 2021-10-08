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
e2e_logger implements all the methods to interact with E2E Trace Log Manager for One-Box.
version: 0.1.1
'''
__author__="Jechan Han"
__date__ ="$30-Mar-2016 11:19:29$"

##################################  Python Modules   #####################################
import requests
import json
import sys
from httplib import HTTPException
from requests.exceptions import ConnectionError

##################################  One-Box Utils   #######################################
from utils.config_manager import ConfigManager

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

##################################  CONSTANT VARIABLES   ###################################
CONST_TRESULT_SUCC = "OK"
CONST_TRESULT_FAIL = "NOK"
CONST_TRESULT_NONE = "UNKNOWN"

HTTP_Bad_Request = 400
HTTP_Unauthorized = 401 
HTTP_Not_Found = 404 
HTTP_Method_Not_Allowed = 405 
HTTP_Request_Timeout = 408
HTTP_Conflict = 409
HTTP_Service_Unavailable = 503 
HTTP_Internal_Server_Error = 500 
############################################################################################

class e2elogger():
    def __init__(self, tname, tmodule, tid=None, tpath="", user="admin", ttag=None, extra=None, url=None):
        if not tname:
            raise TypeError, 'tname can not be NoneType'
        self.tname = tname
        
        if not tmodule:
            raise TypeError, 'tmodule can not be NoneType'
        self.tmodule = tmodule
        
        self.ttag = ttag
        self.extra = extra
        
        if not url:
            log.debug("[HJC] No URL")
            self.url = self._get_default_url_from_config()
            if not self.url:
                raise Exception("Failed to get e2e url")
        else:
            log.debug("[HJC] URL: %s" %str(url))
            self.url = url
        self.user = user
    
        if not tid:
            r, new_tid = self.create_transaction_log(self.tname, self.tmodule, self.ttag, self.extra)
            if r < 0:
                raise TypeError, new_tid
            self.tid = new_tid
            self.needtoclose = True
        else:
            self.tid = tid
            self.needtoclose = False
            
        self.tpath=tpath        
        
        self.jobid_map = {}
        
        self.debug  = self._get_default_debug_from_config()
        
    def __del__(self):
        if self.needtoclose == True:
            self.finish(CONST_TRESULT_FAIL)
    
    def __getitem__(self,index):
        if index=='tid':
            return self.tid
        elif index=='tpath':
            return self.tpath
        elif index=='tname':
            return self.tname
        elif index=='tmodule':
            return self.tmodule
        elif index=='ttag':
            return self.ttag
        elif index=='extra':
            return self.extra
        elif index=='url':
            return self.url
        elif index=='user':
            return self.user
        else:
            raise KeyError("Invalid key '%s'" %str(index))
        
    def __setitem__(self,index, value):
        if index=='tpath':
            self.tpath = value
        elif index=='tname':
            self.tname = value
        elif index=='ttag':
            self.ttag = value
        elif index=='extra':
            self.extra = value
        elif index=='url':
            if value is None:
                raise TypeError, 'url param can not be NoneType'
            self.url = value            
        else:
            raise KeyError("Invalid key '%s'" %str(index))

    def _get_default_url_from_config(self):
        try:
            cfgManager = ConfigManager.get_instance()
            obor_config = cfgManager.get_config()

            return obor_config.get('e2emgr_url', None)
        except Exception, e:
            log.exception("Failed to get the default URL of E2E Trace Log Manager: %s" %str(e))
            return None
    
    def _get_default_debug_from_config(self):
        try:
            cfgManager = ConfigManager.get_instance()
            obor_config = cfgManager.get_config()
            
            return obor_config.get('e2emgr_debug', True)
        except Exception, e:
            log.exception("Failed to get the default URL of E2E Trace Log Manager: %s" %str(e))
            return True
        
    def _parse_json_response(self, e2e_response):
        try:
            content = e2e_response.json()
        except Exception, e:
            log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'
        
        log.debug("_parse_json_response() response body = %s" %str(content))
        
        if e2e_response.status_code > 299 or content.get('tresult') != CONST_TRESULT_SUCC:
            log.error("Response HTTP Status: %s, tresult: %s" %(str(e2e_response.status_code), content.get('tresult')))
            if 'error' in content:
                return -HTTP_Internal_Server_Error, content['error'].get('description')
            else:
                return -HTTP_Internal_Server_Error, "Invalid Response"
                
        return 200, content
    
    def _insert_jobid(self, tmsg_name, jobid):
        if not tmsg_name or not jobid:
            return
        
        self.jobid_map[tmsg_name]=jobid
    
    def _get_jobid(self, tmsg_name):
        return self.jobid_map.get(tmsg_name)
    
    def _pop_jobid(self, tmsg_name):
        if not tmsg_name:
            return None
        
        return self.jobid_map.pop(tmsg_name)
        
    def create_transaction_log(self, tname, tmodule, ttag=None, extra=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.url + "/createTransactionLog"
        
        req_body = {'tname':tname, 'tmodule':tmodule}
        if ttag: req_body['ttag']=ttag
        if self.user: req_body['user']=self.user
        if extra: req_body['extra']=extra
        
        payload_req = json.dumps(req_body)
        
        try:
            e2e_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("Exception: %s" %str(e))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_json_response(e2e_response)
        if result < 0:
            log.error("Failed to create a transaction log: %d %s" %(result, str(content)))
            data = content
        else:
            data = content['tid']
            
        log.e2e("[%s] api_result: %d, api_data: %s, msg: %s" %(URLrequest, result, data, str(payload_req)))
            
        return result, data

    def finish(self, tresult, tresult_cause=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.url + "/closeTransactionLog"
        
        req_body = {'tid':self.tid, 'tresult':tresult}
        if tresult_cause: req_body['tresultCause'] = tresult_cause
        payload_req = json.dumps(req_body)
        
        try:
            e2e_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("Exception: %s" %str(e))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_json_response(e2e_response)
        if result < 0:
            log.error("Failed to close a transaction log: %d %s" %(result, str(content)))
            data = content
        else:
            data = content['tresult']
            self.needtoclose = False
        
        log.e2e("[%s] api_result: %d, api_data: %s, msg: %s" %(URLrequest, result, data, str(payload_req)))
        
        return result, data

    def job(self, tmsg_name, tresult=CONST_TRESULT_NONE, tmsg_body=None, tpath=None, tjobinfo=None, tresult_cause=None, jobid=None):
        if not self.debug:
            return 200, "Debug Off"
        
        if not jobid:
            jobid = self._get_jobid(tmsg_name)
        
        if jobid:
            return self.close_job_log(tmsg_name, tresult, tmsg_body, tpath, tjobinfo, tresult_cause, jobid)
        else:
            return self.create_job_log(tmsg_name, tresult, tmsg_body, tpath, tjobinfo, tresult_cause)

    def create_job_log(self, tmsg_name, tresult, tmsg_body=None, tpath=None, tjobinfo=None, tresult_cause=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        
        if tresult == CONST_TRESULT_NONE:
            URLrequest = self.url + "/createJobLog"
        else:
            URLrequest = self.url + "/addJobLog"
        
        req_body = {'tid':self.tid, 'tmodule':self.tmodule, 'tresult':tresult, 'tmsg_name':tmsg_name}
        if tpath:
            req_body['tpath']=tpath
        else:
            req_body['tpath']=self.tpath
        if tmsg_body: req_body['tmsg_body']=tmsg_body
        if tjobinfo: req_body['tjobinfo']=tjobinfo
        if tresult_cause: req_body['tresultCause']=tresult_cause
        
        payload_req = json.dumps(req_body)
        
        try:
            e2e_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("Exception: %s" %str(e))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_json_response(e2e_response)
        if result < 0:
            log.error("Failed to create or add a job log: %d %s" %(result, str(content)))
            data = content
        else:
            data = content.get('jobId')
        
        #log.e2e("[%s] api_result: %d, api_data: %s, msg: %s" %(URLrequest, result, data, str(payload_req)))
        
        if tresult == CONST_TRESULT_NONE:
            self._insert_jobid(tmsg_name, data)
        
        return result, data

    def close_job_log(self, tmsg_name, tresult, tmsg_body=None, tpath=None, tjobinfo=None, tresult_cause=None, jobid=None):
        if not jobid:
            return -HTTP_Internal_Server_Error, "No Job ID"
        
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.url + "/closeJobLog"
        
        req_body = {'tid':self.tid, 'jobId':jobid, 'tresult':tresult}
        if tmsg_body: req_body['tmsg_body']=tmsg_body
        if tjobinfo: req_body['tjobinfo']=tjobinfo
        if tresult_cause: req_body['tresultCause']=tresult_cause
        
        payload_req = json.dumps(req_body)
        
        try:
            e2e_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("Exception: %s" %str(e))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_json_response(e2e_response)
        if result < 0:
            log.error("Failed to close a job log: %d %s" %(result, str(content)))
            data = content
        else:
            data = content['tresult']
        
        # log.e2e("[%s] api_result: %d, api_data: %s, msg: %s" %(URLrequest, result, data, str(payload_req)))
        
        return result, data


                       