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
monitorconnector implements all the methods to interact with Orch-M in One-Boxes.
'''
__author__="Jechan Han"
__date__ ="$12-Nov-2015 11:19:29$"

import requests
import json
import yaml
import time
import sys
import uuid as myUuid
from httplib import HTTPException
from requests.exceptions import ConnectionError

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Bad_Request, HTTP_Not_Found, HTTP_Unauthorized, HTTP_Conflict, HTTP_Internal_Server_Error
from utils.e2e_logger import CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

class monitorconnector():
    def __init__(self, name, host, port, uuid=None, user=None, passwd=None, url=None, debug=True, config={}):
        '''using common constructor parameters. In this case 
        'url' is the ip address or ip address:port,
        ''' 
 
        self.id        = uuid
        self.name      = name
        self.host = host
        if not host:
            raise TypeError, 'host param can not be NoneType'
        self.port = port
        self.url       = url
        self.user      = user
        self.passwd    = passwd
        self.config              = config
        self.debug               = debug
        self.reload_client       = True
    
    def __getitem__(self,index):
        if index=='id':
            return self.id
        elif index=='name':
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
        else:
            raise KeyError("Invalid key '%s'" %str(index))
        
    def __setitem__(self,index, value):
        '''Set individuals parameters 
        '''
        if index=='id':
            self.id = value
        elif index=='name':
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
        else:
            raise KeyError("Invalid key '%s'" %str(index))
        
    def check_connection(self):
        #TODO
        pass
    
    def get_monitor_vnf_target_seq(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/target/mapping" %(self.host, self.port)
        
        vdud_list = []

        for vdud in target_dict['vdus']:

            vdud_info = {'vdud_seq':vdud['vdudseq'], 'vdud_version':str(target_dict['version'])}
            vdud_info['vdud_type'] = target_dict.get('type')
            vdud_info['vdud_vendor'] = target_dict.get('vendor')
            
            if vdud['name'].find('UTM') > 0:
                if vdud_info['vdud_vendor'] is None:
                    vdud_info['vdud_vendor'] = "olleh"
            
            if vdud['name'].find('WAF') > 0:
                if vdud_info['vdud_vendor'] is None:
                    vdud_info['vdud_vendor'] = "pentas"
                
            if vdud['name'].find('WIMS') > 0:
                if vdud_info['vdud_vendor'] is None:
                    vdud_info['vdud_vendor'] = "olleh"
            
            if vdud['name'].find('XMS') > 0:
                if vdud_info['vdud_vendor'] is None:
                    vdud_info['vdud_vendor'] = "olleh"
                
            vdud_list.append(vdud_info)
        
        req_dict = {'vdud_list': vdud_list}
        
        if e2e_log:
            req_dict['tid']=e2e_log['tid']
            req_dict['tpath']=e2e_log['tpath']
        else:
            req_dict['tid']=str(myUuid.uuid1())
            
        payload_req = json.dumps(req_dict)
        log.debug("get_monitor_vnf_target_seq() request body = %s" %str(payload_req))
        
        try:
            response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("get_monitor_vnf_target_seq(): failed to get target seq for %s due to HTTP Error: %s" %(target_dict['name'], str(e)))
            return -500, str(e)
        
        result, content = self._parse_response(response)
        if result < 0:
            log.error("get_monitor_vnf_target_seq(): failed to get the target seq form the Orch-M: %d %s" %(result, content))
            return result, content
        else:
            for vdud in target_dict['vdus']:
                for target_data in content['target_list']:
                    if target_data['vdud_seq'] == vdud['vdudseq']:
                        vdud['monitor_target_seq'] = target_data['target_seq']
                        log.debug("get_monitor_vnf_target_seq(): target_seq = %s" %str(vdud['monitor_target_seq']))
        
        return result, content


    def start_monitor_nsr(self, target_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/server/target/add" %(self.host, self.port)
        
        # Step 1. request to setup monitor
        body_result, body_dict = self._compose_start_nsr_requestbody_tmp(target_dict, e2e_log)

        if body_result < 0:
            log.error("faild to compose request body for start monitor nsr")
            return body_result, body_dict
        
        payload_req = json.dumps(body_dict)
        log.debug("start_monitor_nsr() request body = %s" %str(payload_req))
        
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("start_monitor_nsr() failed to start monitor for %s due to HTTP Error: %s" %(target_dict['nsr_name'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.debug("start_monitor_nsr() failed to start monitor: %d %s" %(result, content))
            return result, content
        
        # Step 2. check the status of monitor
        check_count = 0

        while check_count < 10:

            time.sleep(10)

            check_URLrequest = "https://%s:%s/request/progress" %(self.host, self.port)
            check_req_dict = {'tid':body_dict['tid']}

            if e2e_log:
                check_req_dict['tpath'] = e2e_log['tpath']
            
            check_payload = json.dumps(check_req_dict)
            log.debug("start_monitor_nsr() check the progress: body = %s" %str(check_payload))
            
            try:
                check_response = requests.post(check_URLrequest, headers = headers_req, data=check_payload, verify=False)
                check_result, check_content = self._parse_response(check_response)
                
                if check_result < 0:
                    log.debug("start_monitor_nsr() failed to check the progress of the request for starting monitor: %d %s" %(check_result, check_content))
                else:
                    if check_content['status'] == "DONE":
                        log.debug("start_monitor_nsr(): completed to start monitor: %d %s" %(check_result, str(check_content)))
                        return 200, "OK"
                    elif check_content['status'] == "FAILED":
                        log.debug("start_monitor_nsr(): completed to start monitor: %d %s" %(check_result, str(check_content)))
                        return -HTTP_Internal_Server_Error, "NOK"

            except (HTTPException, ConnectionError), e:
                log.exception("start_monitor_nsr(): failed to check the progress for %s due to HTTP Exception: %s" %(target_dict['nsr_name'], str(e)))
            
            check_count += 1
            
        return -HTTP_Internal_Server_Error, "Cannot get the progress info from Orch-M"
    
    def stop_monitor_nsr(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/server/target/del" %(self.host, self.port)
        
        #body_result, body_dict = self._compose_stop_nsr_requestbody(tid, target_dict)
        body_result, body_dict = self._compose_stop_nsr_requestbody_tmp(target_dict, e2e_log)
        if body_result < 0:
            log.error("faild to compose request body for stop monitor nsr")
            return body_result, body_dict
        
        payload_req = json.dumps(body_dict)
        log.debug("stop_monitor_nsr() request body = %s" %str(payload_req))
                
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("stop_monitor_nsr(): failed to stop_monitor for %s due to HTTP Error: %s" %(target_dict['name'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.debug("stop_monitor_nsr() failed to stop monitor: %d %s" %(result, str(content)))
            return result, content
        else:
            log.debug("stop_monitor_nsr() response = %s" %str(content))
        
        return result, "OK"
    
    def suspend_monitor_nsr(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/monitor/suspend" %(self.host, self.port)
        
        #body_result, body_dict = self._compose_stop_nsr_requestbody(tid, target_dict)
        body_result, body_dict = self._compose_stop_nsr_requestbody_tmp(target_dict, e2e_log)
        if body_result < 0:
            log.error("faild to compose request body for suspend monitor nsr")
            return body_result, body_dict
        
        body_dict['type'] = "vnf"
        payload_req = json.dumps(body_dict)
        log.debug("suspend_monitor_nsr() request body = %s" %str(payload_req))
        
        if e2e_log:
            e2e_log.job('Orch-M API 호출 - Suspend', CONST_TRESULT_NONE,
                        tmsg_body="API_URL:%s\nAPI_Body:%s" %(URLrequest, payload_req))
                
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("suspend_monitor_nsr(): failed to suspend_monitor for %s due to HTTP Error: %s" %(target_dict['name'], str(e)))
            if e2e_log:
                e2e_log.job('Orch-M API 호출 - Suspend', CONST_TRESULT_FAIL,
                            tmsg_body="API_URL:%s\nAPI_Body:%s\nResult:Fail\nCause:%s" %(URLrequest, payload_req, str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("suspend_monitor_nsr() failed to suspend monitor: %d %s" %(result, str(content)))
            if e2e_log:
                e2e_log.job('Orch-M API 호출 - Suspend', CONST_TRESULT_FAIL,
                            tmsg_body="API_URL:%s\nAPI_Body:%s\nResult:Fail\nCause:%s" %(URLrequest, payload_req, str(content)))
            return result, content
        else:
            log.debug("suspend_monitor_nsr() response = %s" %str(content))
            if e2e_log:
                e2e_log.job('Orch-M API 호출 - Suspend', CONST_TRESULT_SUCC,
                            tmsg_body="API_URL:%s\nAPI_Body:%s\nAPI_Response:%s" %(URLrequest, payload_req, json.dumps(content, indent=4)))
        
        return result, "OK"
    
    def resume_monitor_nsr(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/monitor/resume" %(self.host, self.port)
        
        #body_result, body_dict = self._compose_start_nsr_requestbody(tid, target_dict)
        body_result, body_dict = self._compose_start_nsr_requestbody_tmp(target_dict, e2e_log, type="vnf")
        if body_result < 0:
            log.error("faild to compose request body for resume monitor nsr")
            return body_result, body_dict
        
        payload_req = json.dumps(body_dict)
        log.debug("resume_monitor_nsr() request body = %s" %str(payload_req))
        
        if e2e_log:
            e2e_log.job('Orch-M API 호출 - Resume', CONST_TRESULT_NONE, tmsg_body="API_URL:%s\nAPI_Body:%s" %(URLrequest, payload_req))
                
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("resume_monitor_nsr(): failed to resume_monitor for %s due to HTTP Error: %s" %(target_dict['nsr_name'], str(e)))
            if e2e_log:
                e2e_log.job('Orch-M API 호출 - Resume', CONST_TRESULT_FAIL,
                            tmsg_body="API_URL:%s\nAPI_Body:%s\nResult:Fail\nCause:%s" %(URLrequest, payload_req, str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("resume_monitor_nsr() failed to resume monitor: %d %s" %(result, str(content)))
            if e2e_log:
                e2e_log.job('Orch-M API 호출 - Resume', CONST_TRESULT_FAIL,
                            tmsg_body="API_URL:%s\nAPI_Body:%s\nResult:Fail\nCause:%s" %(URLrequest, payload_req, str(content)))
            return result, content
        else:
            log.debug("resume_monitor_nsr() response = %s" %str(content))
        
        if e2e_log:
            e2e_log.job('Orch-M API 호출 - Resume', CONST_TRESULT_SUCC,
                        tmsg_body="API_URL:%s\nAPI_Body:%s\nResult:Success\nCause:%s" %(URLrequest, payload_req, json.dumps(content, indent=4)))
        
        return result, "OK"

    def start_monitor_onebox(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/server" %(self.host, self.port)
        
        #body_result, body_dict = self._compose_start_nsr_requestbody(tid, target_dict)
        log.debug("______###_____ start_onebox_monitor target_dict : %s" % target_dict)
        body_result, body_dict = self._compose_start_onebox_requestbody(target_dict, e2e_log)
        log.debug("______###_____ start_onebox_monitor body_dict : %s" % body_dict)
        if body_result < 0:
            log.error("faild to compose request body for start monitor onebox")
            return body_result, body_dict
        #body_dict['type'] = "onebox"
        
        payload_req = json.dumps(body_dict)
        log.debug("start_monitor_onebox() request body = %s" %str(payload_req))
                
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("start_monitor_onebox(): failed to start_monitor for %s due to HTTP Error: %s" %(target_dict['server_id'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("start_monitor_onebox() failed to start monitor: %d %s" %(result, str(content)))
            return result, content
        else:
            log.debug("start_monitor_onebox() response = %s" %str(content))
        
        # Step 2. check the status of monitor
        check_count = 0
        while check_count < 10:
            time.sleep(10)
            check_URLrequest = "https://%s:%s/request/progress" %(self.host, self.port)
            
            check_req_dict = {'tid':body_dict['tid']}
            if e2e_log: check_req_dict['tpath']=e2e_log['tpath']
            
            check_payload = json.dumps(check_req_dict)
            log.debug("check the progress: body = %s" %str(check_payload))
            
            try:
                check_response = requests.post(check_URLrequest, headers = headers_req, data=check_payload, verify=False)
                check_result, check_content = self._parse_response(check_response)
                
                if check_result < 0:
                    log.debug("failed to check the progress of the request for starting monitor: %d %s" %(check_result, check_content))
                else:
                    if check_content['status'] == "DONE":
                        log.debug("completed to start monitor: %d %s" %(check_result, str(check_content)))
                        return 200, "OK"
                    elif check_content['status'] == "FAILED":
                        log.debug("completed to start monitor: %d %s" %(check_result, str(check_content)))
                        return -HTTP_Internal_Server_Error, "NOK"
            except (HTTPException, ConnectionError), e:
                log.exception("failed to check the progress for %s due to HTTP Exception: %s" %(target_dict['server_id'], str(e)))
            
            check_count += 1
            
        return -HTTP_Internal_Server_Error, "Cannot get the progress info from Orch-M"

    def update_monitor_onebox(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/server/mod" %(self.host, self.port)
        
        #body_result, body_dict = self._compose_start_nsr_requestbody(tid, target_dict)
        body_result, body_dict = self._compose_update_onebox_requestbody(target_dict, e2e_log)
        if body_result < 0:
            log.error("faild to compose request body for update monitor onebox")
            return body_result, body_dict
        #body_dict['type'] = "onebox"
        
        payload_req = json.dumps(body_dict)
        log.debug("request body = %s" %str(payload_req))
                
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("failed to update_monitor for %s due to HTTP Error: %s" %(target_dict['server_id'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("failed to update monitor: %d %s" %(result, str(content)))
            return result, content
        else:
            log.debug("response = %s" %str(content))
            
        return 200, "OK"

    def stop_monitor_onebox(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/server/del" %(self.host, self.port)
        
        body_result, body_dict = self._compose_stop_onebox_requestbody(target_dict, e2e_log)
        if body_result < 0:
            log.error("faild to compose request body for stop monitor onebox")
            return body_result, body_dict
        
        payload_req = json.dumps(body_dict)
        log.debug("request body = %s" %str(payload_req))
                
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("failed to stop_monitor for %s due to HTTP Error: %s" %(target_dict['server_id'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("failed to stop monitor: %d %s" %(result, str(content)))
            return result, content
        else:
            log.debug("response = %s" %str(content))
            
        return 200, "OK"

    def suspend_monitor_onebox(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/monitor/suspend" %(self.host, self.port)
        
        #body_result, body_dict = self._compose_stop_nsr_requestbody(tid, target_dict)
        #body_result, body_dict = self._compose_stop_nsr_requestbody_tmp(target_dict, e2e_log)
        body_result, body_dict = self._compose_stop_onebox_requestbody(target_dict, e2e_log)
        if body_result < 0:
            log.error("faild to compose request body for suspend monitor onebox")
            return body_result, body_dict
        body_dict['type'] = "onebox"

        payload_req = json.dumps(body_dict)
        log.debug("suspend_monitor_onebox() request body = %s" %str(payload_req))
                
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("suspend_monitor_onebox(): failed to suspend_monitor for %s due to HTTP Error: %s" %(target_dict['server_id'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("suspend_monitor_onebox() failed to suspend monitor: %d %s" %(result, str(content)))
            return result, content
        else:
            log.debug("suspend_monitor_onebox() response = %s" %str(content))
        
        return result, "OK"
    
    def resume_monitor_onebox(self, target_dict, e2e_log=None, include_ns=False):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/monitor/resume" %(self.host, self.port)
        
        #body_result, body_dict = self._compose_start_nsr_requestbody(tid, target_dict)
        if include_ns is True:
            body_result, body_dict = self._compose_start_nsr_requestbody_tmp(target_dict, e2e_log, type="onebox")
        else:
            body_result, body_dict = self._compose_start_onebox_requestbody(target_dict, e2e_log)

        if body_result < 0:
            log.error("faild to compose request body for resume monitor onebox")
            return body_result, body_dict
        
        if include_ns is False:
            body_dict['type']="onebox"

        payload_req = json.dumps(body_dict)
        log.debug("resume_monitor_onebox() request body = %s" %str(payload_req))
        
        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("resume_monitor_onebox(): failed to resume_monitor for %s due to HTTP Error: %s" %(target_dict['server_id'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)
        
        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("resume_monitor_onebox() failed to resume monitor: %d %s" %(result, str(content)))
            return result, content
        else:
            log.debug("resume_monitor_onebox() response = %s" %str(content))
        
        return result, "OK"


    def first_notify_monitor(self, target_dict, e2e_log=None):
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/oba/first_notify" %(self.host, self.port)

        body_result, body_dict = self._compose_first_notify_requestbody(target_dict, e2e_log)
        if body_result < 0:
            log.error("faild to compose request body for first_notify_monitor")
            return body_result, body_dict
        #body_dict['type'] = "onebox"

        payload_req = json.dumps(body_dict)
        log.debug("first_notify_monitor() request body = %s" %str(payload_req))

        try:
            monitor_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("first_notify_monitor(): failed to first_notify_monitor for %s due to HTTP Error: %s" %(target_dict['server_id'], str(e)))
            return -HTTP_Internal_Server_Error, str(e)

        result, content = self._parse_response(monitor_response)
        if result < 0:
            log.error("first_notify_monitor() failed to notify monitor: %d %s" %(result, str(content)))
            return result, content
        else:
            log.debug("first_notify_monitor() response = %s" %str(content))

        return result, "OK"

    
    def _compose_start_onebox_requestbody(self, target_dict, e2e_log=None):
        body = {}
        body['svr_info'] = {'seq':target_dict['server_id'], 'uuid':target_dict['server_uuid'], 'name':target_dict['server_name'], 'ip':target_dict['server_ip'], 'onebox_id':target_dict['onebox_id']}
        
        if target_dict.get('ob_service_number') is not None: body['ob_service_number'] = target_dict['ob_service_number']        
        
        if e2e_log:
            body['tid']=e2e_log['tid']
            body['tpath']=e2e_log['tpath']
        else:
            body['tid']=str(myUuid.uuid1())
            
        target_info_list = []
        
        target_info_hw = {'target_code':"hw", 'target_type':"svr"}
        if target_dict.get('hw_model') is None:
            return -HTTP_Internal_Server_Error, "No data : hw_model"
            # target_info_hw['vendor_code']="dell"
            # target_info_hw['target_model']="R420"
        else:
            hw_model_info = target_dict['hw_model'].split(" ")
            if len(hw_model_info) != 2:
                return -HTTP_Internal_Server_Error, "Format Error - hw_model : 'vendor_code target_model'. For example, 'NSA 3130'. Getted data:%s" % target_dict['hw_model']
                # target_info_hw['vendor_code']="dell"
                # target_info_hw['target_model']="R420"
            else:
                target_info_hw['vendor_code']=hw_model_info[0].lower()
                target_info_hw['target_model']=hw_model_info[1]
        
        log.debug("[HJC] target_info_hw: %s" %str(target_info_hw))
        target_info_list.append(target_info_hw)
        
        target_info_os = {'target_code':"os"}
        if target_dict.get('os_name') is None:
            target_info_os['target_type']="linux"
            target_info_os['vendor_code']="ubuntu"
            target_info_os['target_model']="trusty 14.04"
        elif target_dict['os_name'].lower().find("ubuntu") >= 0:
            target_info_os['target_type']="linux"
            target_info_os['vendor_code']="ubuntu"
            if target_dict.get('os_name', "trusty 14.04") == "Ubuntu 14.04.5 LTS":
                target_info_os['target_model']="trusty 14.04"
            else:
                target_info_os['target_model']=target_dict.get('os_name', "trusty 14.04")
        else:
            return -HTTP_Internal_Server_Error, "Not Supported OS: %s" %target_dict['os_name']

        # HA 구성이 있을경우 True
        is_ha_set = False

        target_info_os['cfg']={'svr_fs':['/']}
        if target_dict.get('svr_net') is None or len(target_dict['svr_net']) <= 0:
            target_info_os['cfg'] = {'svr_net':['p2p1','p2p2','p2p3','p2p4'], 'svr_fs':['/']}
            target_info_os['mapping'] = {'wan':'p2p1', 'server':'p2p3', 'office1':'p2p2', 'office2':'p2p4'}
        else:
            target_info_os['cfg']['svr_net']=[]
            target_info_os['mapping'] = {}

            for sn in target_dict['svr_net']:
                target_info_os['cfg']['svr_net'].append(sn['name'])
                # 회선이중화 : {"wan": "eth0, eth1", "office1": "eth2, eth3, eth4, eth5", "server": "eth6, eth7"}
                # 여러개일 경우 배열로 처리되로록 수정
                if sn['display_name'] in target_info_os['mapping']:
                    if type(target_info_os['mapping'][sn['display_name']]) is list:
                        target_info_os['mapping'][sn['display_name']].append(sn['name'])
                    elif type(target_info_os['mapping'][sn['display_name']]) is str:
                        val1 = target_info_os['mapping'][sn['display_name']]
                        target_info_os['mapping'][sn['display_name']] = [val1, sn['name']]

                    # HA 구성이 있을경우
                    if sn['display_name'] == "other":
                        is_ha_set = True
                else:
                    target_info_os['mapping'][sn['display_name']] = sn['name']
        
        target_info_list.append(target_info_os)
        
        target_info_vim = {'target_code':"vim"}
        if target_dict.get('vim_typecode') is None:
            target_info_vim['target_type'] = "openstack"
            target_info_vim['vendor_code'] = "openstack"
            target_info_vim['target_model'] = "kilo"
        elif target_dict['vim_typecode'].lower().find("openstack") >= 0:
            target_info_vim['target_type'] = "openstack"
            target_info_vim['vendor_code'] = "openstack"
            target_info_vim['target_model'] = target_dict['vim_version']
        else:
            return -HTTP_Internal_Server_Error, "Not Supported VIM: %s" %target_dict['vim_typecode']        
        
        target_info_vim['cfg']={'vim_auth_url':"http://"+target_dict['server_ip']+":35357/v3/auth/tokens"}
        #target_info_vim['cfg']['vim_auth_url']=target_dict.get("vim_auth_url", "http://"+target_dict['server_ip']+":35357/v3/auth/tokens")
        target_info_vim['cfg']['vim_id']=target_dict.get("vim_id", "admin")
        target_info_vim['cfg']['vim_passwd']=target_dict.get("vim_passwd", "ohhberry3333")
        target_info_vim['cfg']['vim_domain']=target_dict.get("vim_domain", "default")
        
        if target_dict.get('vim_net') and len(target_dict['vim_net']) > 0:
            target_info_vim['cfg']['vim_net']=[]
            for vn in target_dict['vim_net']:
                if vn.find('mgmt') >= 0:
                    log.debug("[HJC] vim_mgmt_net = %s" %vn)
                    target_info_vim['cfg']['vim_mgmt_net']=vn
                target_info_vim['cfg']['vim_net'].append(vn)
        else:
            target_info_vim['cfg']['vim_mgmt_net']="global_mgmt_net"
        
        # TODO: Get values from One-Box Info 
        #target_info_vim['cfg']['vim_net']=['global_mgmt_net','public_net', 'net_office', 'net_internet', 'net_server']
        target_info_vim['cfg']['vim_net']=['global_mgmt_net', 'net_office', 'net_server']

        # HA 구성이 있을 경우 'net_ha' 추가
        if is_ha_set is True:
            target_info_vim['cfg']['vim_net'].append('net_ha')

        target_info_vim['cfg']['vim_router']=["global_mgmt_router"]
        
        target_info_list.append(target_info_vim)
        
        body['target_info']=target_info_list
        
        return 200, body

    def _compose_update_onebox_requestbody(self, target_dict, e2e_log=None):
        body = {}
        if "server_id" in target_dict and "server_ip" in target_dict:
            body['svr_info'] = {'seq':target_dict['server_id'], 'new_ip':target_dict['server_ip']}
            body['svr_info']['mod_desc']="UPDATE"

            if 'ssh_port' in target_dict:
                body['new_port'] = target_dict.get('ssh_port')

        if "change_info" in target_dict:
            body['change_info'] = target_dict['change_info']
        
        if e2e_log:
            body['tid']=e2e_log['tid']
            body['tpath']=e2e_log['tpath']
        else:
            body['tid']=str(myUuid.uuid1())
        
        return 200, body
 
    def _compose_stop_onebox_requestbody(self, target_dict, e2e_log=None):
        body = {}
        body['svr_info'] = {'seq':target_dict['server_id'], 'ip':target_dict['server_ip'], 'onebox_id': target_dict['onebox_id']}
        
        if e2e_log:
            body['tid']=e2e_log['tid']
            body['tpath']=e2e_log['tpath']
        else:
            body['tid']=str(myUuid.uuid1())
        
        return 200, body

    def _compose_first_notify_requestbody(self, target_dict, e2e_log=None):
        body = {}
        body['svr_info'] = {'seq':target_dict['server_id'], 'ip':target_dict['server_ip'], 'onebox_id': target_dict['onebox_id']}

        if e2e_log:
            body['tid']=e2e_log['tid']
            body['tpath']=e2e_log['tpath']
        else:
            body['tid']=str(myUuid.uuid1())

        return 200, body
               
    def _parse_response(self, monitor_response):
        
        try:
            log.debug("[HJC] Monitor Response Raw Data: %s" %str(monitor_response))
            content = monitor_response.json()
            log.debug("_parse_response() response body: %s" %str(content))
        except Exception, e:
            log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'
            
        try:
            if monitor_response.status_code == 200:
                return monitor_response.status_code, content
            else:
                if 'error' in content:
                    return -monitor_response.status_code, content['error']['description']
                elif 'description' in content:
                    return -monitor_response.status_code, content['description']
                else:
                    return -monitor_response.status_code, "Invalid Response"                
        except (KeyError, TypeError) as e:
            log.exception("_parse_response() exception while parsing response %s" %str(e))
        
        return -HTTP_Internal_Server_Error, "Unknown Error"
    


    def _compose_start_nsr_requestbody_tmp(self, target_dict, e2e_log=None, type=None):
        target_info_list = []
        for vm in target_dict['vms']:
            target_info = {}
            target_info_vim_vms = []
            target_info_vim_vports = []
        
            target_info_vim_vms.append(vm['vm_name']) #vm_vim_name
        
            for cp in vm['vm_cps']:
                target_info_vim_vports.append(cp['cp_vim_name'])
            
            target_info['target_seq'] = vm.get('monitor_target_seq')
            target_info['vdudseq'] = vm.get('vdud_id')

            target_info['cfg'] = {}
            
            if vm.get('service_number') is not None:
                target_info['cfg']['service_number'] = vm.get('service_number')
            
            #target_info['cfg']['vim_auth_url']=target_dict.get("vim_auth_url", "http://"+target_dict['server_ip']+":35357/v3/auth/tokens")
            target_info['cfg']['vim_auth_url']="http://"+target_dict['server_ip']+":35357/v3/auth/tokens"
            target_info['cfg']['vim_id']=target_dict.get("vim_id", "admin")
            target_info['cfg']['vim_passwd']=target_dict.get("vim_passwd", "ohhberry3333")
            target_info['cfg']['vim_domain']=target_dict.get("vim_domain", "default")
            target_info['cfg']['vim_mgmt_net']="global_mgmt_net"
            target_info['cfg']['vim_vm']=target_info_vim_vms
            target_info['cfg']['vim_port']=target_info_vim_vports
            target_info['cfg']['vm_name'] = vm['vm_name']
            target_info['cfg']['vm_id'] = vm['vm_id']
            target_info['cfg']['vm_passwd'] = vm['vm_passwd']
            if 'vm_app_id' in vm: target_info['cfg']['vm_app_id'] = vm['vm_app_id']
            if 'vm_app_passwd' in vm: target_info['cfg']['vm_app_passwd'] = vm['vm_app_passwd']

            found_local = False
            for cp in vm['vm_cps']:
                if cp['cp_name'].find('blue') > 0 or cp['cp_name'].find('local') > 0:
                    log.debug("[HJC] local CP: %s" %str(cp))
                    target_info['cfg']['vm_ip'] = cp['cp_ip']
                    found_local = True
                    break

            if found_local == False:
                for cp in vm['vm_cps']:
                    if cp['cp_name'].find('mgmt') > 0:
                        log.debug("[HJC] mgmt CP: %s" %str(cp))
                        target_info['cfg']['vm_ip'] = cp['cp_ip']
                        break
            
            if ('vm_ip' in target_info['cfg']) == False:
                return -HTTP_Internal_Server_Error, "Cannot find IP Address of VNF for monitoring"
                
            # 회선이중화 : wan_if_num 추가
            wan_if_num = 0
            for cp in vm['vm_cps']:
                # wan_if_num counting
                if vm.get('nfsubcategory', "") == "UTM" and cp['cp_name'].find('red') > 0:
                    wan_if_num += 1

            if wan_if_num > 0:
                target_info['wan_if_num'] = wan_if_num

            target_info_list.append(target_info)
        
        body = {}
        body['svr_info'] = {'seq':target_dict['server_id'], 'uuid':target_dict['server_uuid'], 'ip':target_dict['server_ip'], 'onebox_id':target_dict['onebox_id']}
        body['target_info'] = target_info_list
        
        if e2e_log:
            body['tid']=e2e_log['tid']
            body['tpath']=e2e_log['tpath']
        else:
            body['tid']=str(myUuid.uuid1())
            
        if type: body['type'] = type
        
        return 200, body
    
    def _compose_stop_nsr_requestbody_tmp(self, target_dict, e2e_log=None):
        body = {}
        body['svr_info'] = {'seq':target_dict['server_id'], 'uuid':target_dict['server_uuid'], 'ip':target_dict['server_ip'], 'onebox_id':target_dict['onebox_id']}
        
        target_list = []
        for vm in target_dict['vms']:
            target_list.append({'target_seq':vm['monitor_target_seq']})
        
        body['target_info']=target_list
        
        if e2e_log:
            body['tid']=e2e_log['tid']
            body['tpath']=e2e_log['tpath']
        else:
            body['tid']=str(myUuid.uuid1())
                
        return 200, body
    
    
    def get_nsr_simple_data(self, onebox_id):
        if onebox_id == None:
            log.error("No One-Box ID Given")
            return -HTTP_Bad_Request, "No One-Box ID"
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/rs2016/monitor" %(self.host, self.port)
        
        req_dict = {'onebox_id': onebox_id}    
        payload_req = json.dumps(req_dict)
        log.debug("get_nsr_simple_data() request body = %s" %str(payload_req))
        
        try:
            response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("get_nsr_simple_data(): failed to get simple monitoring data: %s %s" %(onebox_id, str(e)))
            return -500, str(e)
        
        result, content = self._parse_response(response)
        if result < 0:
            log.error("get_nsr_simple_data(): failed to get simple monitoring data: %d %s" %(result, content))
            return result, content
        
        return result, content['nsr_mon']

    def check_monitor_target_seq(self, monitor_target_seq, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://%s:%s/target/checkid" %(self.host, self.port)

        req_dict = {"montargetcat_seq" : monitor_target_seq}
        if e2e_log:
            req_dict['tid']=e2e_log['tid']
            req_dict['tpath']=e2e_log['tpath']
        else:
            req_dict['tid']=str(myUuid.uuid1())

        payload_req = json.dumps(req_dict)
        log.debug("check_monitor_target_seq() request body = %s" %str(payload_req))

        try:
            response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
        except (HTTPException, ConnectionError), e:
            log.exception("check_monitor_target_seq(): failed to check target seq %s" % (str(e)))
            return -500, str(e)

        result, content = self._parse_response(response)
        if result < 0:
            log.error("check_monitor_target_seq(): failed to check the target seq form the Orch-M: %d %s" %(result, content))

        return result, content
