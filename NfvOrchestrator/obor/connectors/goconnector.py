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
goconnector implements all the methods to interact with GiGA Office System.
'''
__author__="Jechan Han"
__date__ ="$15-Jun-2016 11:19:29$"

import requests
import json
import yaml
import time
import sys
from httplib import HTTPException
from requests.exceptions import ConnectionError

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Bad_Request, HTTP_Not_Found, HTTP_Unauthorized, HTTP_Conflict, HTTP_Internal_Server_Error
import db.orch_db_manager as orch_dbm
from utils.e2e_logger import CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

GIGASTORAGE_AUTH_BASE64 = 'bmZ2LWFkbWluOm5mdmFkbWluOTkwMCYmKio='
GIGASTORAGE_QUOTA_ID = 'CABeAAEAAADaBwAAAAAAEAUAAAAAAAAA'
SDNSWITCH_CUSTOMER_ID = 'cst1'

class goconnector():
    def __init__(self, name, url, mydb=None, host=None, port=None, user=None, passwd=None, debug=True, config={}):
        '''using common constructor parameters. In this case 
        'url' is the ip address or ip address:port,
        ''' 
 
        self.name      = name
        self.url       = url
        if not url:
            raise TypeError, 'url can not be NoneType'
        self.host = host
        self.port = port
        self.user      = user
        self.passwd    = passwd
        self.config              = config
        self.debug               = debug
        self.reload_client       = True
        self.mydb = mydb
    
    def __getitem__(self,index):
        if index=='name':
            return self.name
        elif index=='user':
            return self.user
        elif index=='passwd':
            return self.passwd
        elif index=='host':
            return self.host
        elif index=='port':
            return self.port
        elif index=='url':
            return self.url
        elif index=='config':
            return self.config
        elif index=='mydb':
            return self.mydb
        else:
            raise KeyError("Invalid key '%s'" %str(index))
        
    def __setitem__(self,index, value):
        '''Set individuals parameters 
        '''
        if index=='name':
            self.name = value
        elif index=='user':
            self.reload_client=True
            self.user = value
        elif index=='passwd':
            self.reload_client=True
            self.passwd = value
        elif index=='host':
            self.reload_client=True
            self.host=value
        elif index=='port':
            self.reload_client=True
            self.port=value
        elif index=='url':
            self.reload_client=True
            self.url = value
            if value is None:
                raise TypeError, 'url param can not be NoneType'
        elif index=='mydb':
            self.mydb = mydb
        else:
            raise KeyError("Invalid key '%s'" %str(index))
    
    def get_base_url(self):
        if self.url:
            return self.url
        else:
            return "http://%s:%s/goapi/v1" %(self.host, self.port)
        
    def check_connection(self):
        URLrequest = self.get_base_url() + "/status"
        
        try:
            go_response = requests.get(URLrequest, timeout=3)
        except Exception, e:
            log.exception("failed to check connection due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        return self._parse_response(go_response)
    
    def check_progress(self, job_name, e2e_log=None):
        if job_name == None:
            return -HTTP_Bad_Request, "No Job Name"
        
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/"+job_name+"/progress"
        
        try:
            go_response = requests.get(URLrequest, headers = headers_req, timeout=3)
        except Exception, e:
            log.exception("failed to check progress of the job %s due to HTTP Error %s" %(str(job_name), str(e)))
            return -500, "UNKNOWN"
        
        result, content = self._parse_response(go_response)
        if result < 0:
            log.error("Failed to check the progress: %d %s" %(result, content))
            content_result = "UNKNOWN"
        else:
            content_result = content.get("result", "UNKNOWN")
            if content_result != "DOING" and content_result != "DONE":
                result = -HTTP_Internal_Server_Error
        
        return result, content_result        
    
    def start_pc(self):
        return 200, "OK"
    
    def finish_pc(self):
        return 200, "OK"
    
    def get_pc(self):
        return 200, "OK"
    
    def start_server(self):
        return 200, "OK"
    
    def finish_server(self):
        return 200, "OK"
    
    def get_server(self):
        return 200, "OK"
    
    def start_storage(self, storage_amount=107374182400, quota_id = GIGASTORAGE_QUOTA_ID):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json', 'Authorization':'Basic %s' %GIGASTORAGE_AUTH_BASE64}
        URLrequest = self.get_base_url() + "/quota/quotas/" + quota_id
        
        reqDict = {"thresholds":{"advisory":None, "hard":storage_amount, "soft":None, "soft_grace":None}}
        payload_req = json.dumps(reqDict)
        log.debug("start_storage() request body = %s" %str(payload_req))
        
        try:
            #requests.packages.urllib3.disable_warnings()
            respDict = requests.put(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=5)
            log.debug("start_storage() response body = %s" %str(respDict))
        except Exception, e:
            log.exception("failed to start Storage %s" %str(e))
            return -500, str(e)
        
        if respDict.status_code == 200 or respDict.status_code == 204:
            return 200, "OK"
        else:
            return -HTTP_Internal_Server_Error, "Response Code: %s" %str(respDict.status_code)
    
    def update_storage(self, new_storage, quota_id= GIGASTORAGE_QUOTA_ID):
        return self.start_storage(new_storage, quota_id)
    
    def finish_storage(self, quota_id= GIGASTORAGE_QUOTA_ID):
        return self.start_storage(107374182400, quota_id)
    
    def get_storage(self, quota_id= GIGASTORAGE_QUOTA_ID):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json', 'Authorization':'Basic %s' %GIGASTORAGE_AUTH_BASE64}
        URLrequest = self.get_base_url() + "/quota/quotas/" + quota_id
        
        try:
            #requests.packages.urllib3.disable_warnings()
            respDict = requests.get(URLrequest, headers = headers_req, verify=False, timeout=5)
            log.debug("get_storage() response body = %s" %str(respDict))
        except Exception, e:
            log.exception("failed to get Storage %s" %str(e))
            return -500, str(e)
        
        result, content = self._parse_response(respDict)
        if result < 0:
            log.error("Response: %d %s" %(result, content))
            return result, content
        else:
            data = {'usage': content['quotas'][0]['usage']['logical'], 'capacity': content['quotas'][0]['thresholds']['hard']}
            return result, data
    
    def start_sdnswitch(self, id=SDNSWITCH_CUSTOMER_ID, bw=100):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/bandwidth/%s" %(id)
        
        reqDict = {'bw_mod': {'bandwidth':str(bw)}}
            
        payload_req = json.dumps(reqDict)
        log.debug("start_sdnswitch() request body = %s" %str(payload_req))
        
        try:
            respDict = requests.post(URLrequest, headers = headers_req, data=payload_req, timeout=3)
            log.debug("start_sdnswitch() response body = %s" %str(respDict))
        except Exception, e:
            log.exception("failed to start SDN Switch %s" %str(e))
            return -500, str(e)
        
        return self._parse_response(respDict)
    
    def finish_sdnswitch(self):
        result, content = self.start_sdnswitch(bw=100)
        
        return result, content
    
    def get_sdnswitch(self, id=SDNSWITCH_CUSTOMER_ID):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/bandwidth/%s" %(id)
        
        try:
            respDict = requests.get(URLrequest, headers = headers_req, timeout=5)
        except Exception, e:
            log.exception("failed to get SDN Switch Info %s" %str(e))
            return -500, str(e)
        
        result, content = self._parse_response(respDict)
        if result < 0:
            log.error("Response: %d %s" %(result, content))
            return result, content
        else:
            data = {'usage': content['BandwidthInfo']['usage'], 'bandwidth': content['BandwidthInfo']['bandwidth']}
            return result, data
    
    def update_sdnswitch(self, new_bw, id=SDNSWITCH_CUSTOMER_ID):
        result, content = self.start_sdnswitch(id, new_bw)
        
        return result, content
    
    def _parse_response(self, go_response):
        try:
            content = go_response.json()
            log.debug("_parse_response() response body: %s" %str(content))
        except Exception, e:
            log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'
            
        try:
            if go_response.status_code == 200:
                return go_response.status_code, content
            else:
                if 'error' in content:
                    return -go_response.status_code, content['error'].get('description')
                else:
                    return -go_response.status_code, "Invalid Response"                
        except (KeyError, TypeError) as e:
            log.exception("_parse_response() exception while parsing response %s" %str(e))
        
        return -HTTP_Internal_Server_Error, "Unknown Error"
    
    
if __name__ == '__main__':
    test_host = '211.224.204.205'
    test_port = 22
    test_user = 'nfv'
    test_password = 'ohhberry3333'
    command = '/home/nfv/hjc_test.sh'
    test_args=['arg1','arg2']
    
    myGO = goconnector(name='testVnfm', url='http://testurl', host=test_host, user=test_user, passwd=test_password)
    
    if myGO != None:
        myGO.check_connection()
    else:
        log.error("failed to get GiGA Office Connector")