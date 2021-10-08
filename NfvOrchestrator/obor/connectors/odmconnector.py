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
odmgr implements all the methods to interact with Order Manager
'''
__author__="Jechan Han"
__date__ ="$1-Sep-2016 11:19:29$"

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

from utils.config_manager import ConfigManager
DEFAULT_BASE_URL = "http://211.224.204.209:8081/orderMgr"

class odmconnector():
    def __init__(self, name, url=None, mydb=None, host=None, port=None, user=None, passwd=None, debug=True, config={}):
        '''using common constructor parameters. In this case 
        'url' is the ip address or ip address:port,
        ''' 
 
        self.name      = name
        if not url:
            log.debug("[HJC] No URL")
            self.url = self._get_default_url_from_config()
        else:
            log.debug("[HJC] URL: %s" %str(url))
            self.url = url
        
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
            self.mydb = value
        else:
            raise KeyError("Invalid key '%s'" %str(index))
    
    def _get_default_url_from_config(self):
        try:
            cfgManager = ConfigManager.get_instance()
            odm_config = cfgManager.get_config()
            
            return odm_config.get('odm_url', DEFAULT_BASE_URL)
        except Exception, e:
            log.exception("Failed to get the default URL of Order Manager: %s" %str(e))
            return DEFAULT_BASE_URL
        
    def get_base_url(self):
        if self.url is not None:
            return self.url
        else:
            return "http://%s:%s/orderMgr" %(self.host, self.port)
        
    def check_connection(self):
        URLrequest = self.get_base_url() + "/status"
        
        try:
            odm_response = requests.get(URLrequest, timeout=3, verify=False)
        except Exception, e:
            log.exception("failed to check connection due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        return self._parse_response(odm_response)
    
    def inform_onebox_status(self, onebox_id, onebox_status, e2e_log=None):
        
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/onebox/status"
        
        reqDict = {"onebox_id": onebox_id, "status": onebox_status}
        payload_req = json.dumps(reqDict)
        log.debug("Request Body: %s" %str(payload_req))
        
        try:
            noti_response = requests.put(URLrequest, headers = headers_req, data=payload_req, timeout=5, verify=False)
        except Exception, e:
            log.exception("failed to inform One-Box's status due to HTTP Error %s" %(str(e)))
            return -500, str(e)
        
        return self._parse_response(noti_response)
        
    def _parse_response(self, odm_response):
        try:
            log.debug("Response from Order Manager = %s" %str(odm_response.text))
            log.debug("Response HTTP Code from Order Manager = %s" %str(odm_response.status_code))
            
            content = odm_response.json()
            log.debug("_parse_response() response body: %s" %str(content))
        except Exception, e:
            log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'
            
        try:
            if odm_response.status_code == 200:
                return odm_response.status_code, content
            else:
                if 'error' in content:
                    return -odm_response.status_code, content['error'].get('description')
                else:
                    return -odm_response.status_code, "Invalid Response"                
        except (KeyError, TypeError) as e:
            log.exception("_parse_response() exception while parsing response %s" %str(e))
        
        return -HTTP_Internal_Server_Error, "Unknown Error"
    
    
if __name__ == '__main__':
    test_host = '211.224.204.209'
    test_port = 8081
    test_user = 'nfv'
    test_password = 'ohhberry3333'
    command = '/home/nfv/hjc_test.sh'
    test_args=['arg1','arg2']
    
    myOdm = odmconnector(name='testOdm', url='http://testurl', host=test_host, user=test_user, passwd=test_password)
    
    if myOdm != None:
        myOdm.check_connection()
    else:
        log.error("failed to get Order Manager Connector")
