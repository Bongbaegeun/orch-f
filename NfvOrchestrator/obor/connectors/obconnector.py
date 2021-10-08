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

"""
    obconnector implements all the methods to interact with the One-Box Agent in One-Boxes.
"""
#from test.test_xmlrpc import URL
__author__="Jechan Han"
__date__ ="$25-Feb-2016 11:19:29$"

import requests
import json
import yaml
import time
import sys
from httplib import HTTPException
from requests.exceptions import ConnectionError

import db.orch_db_manager as orch_dbm
from utils import auxiliary_functions as af
from db.orch_db import HTTP_Bad_Request, HTTP_Not_Found, HTTP_Unauthorized, HTTP_Conflict, HTTP_Internal_Server_Error
from utils.e2e_logger import CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

CLIENT_ORCH_CRT = '/var/onebox/key/client_orch.crt'
CLIENT_ORCH_KEY = '/var/onebox/key/client_orch.key'



class obconnector():

    def __init__(self, name, url, host=None, port=None, uuid=None, user=None, passwd=None, debug=True, config={}, mydb=None):
        """
        using common constructor parameters. In this case 'url' is the ip address or ip address:port,
        """
 
        self.id     = uuid
        self.name   = name
        self.url    = url
        if not url:
            raise TypeError, 'url can not be NoneType'
        self.host   = host
        self.port   = port
        self.user   = user
        self.passwd = passwd
        self.config = config
        self.debug  = debug
        self.reload_client  = True
        self.mydb   = mydb


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
        elif index=='mydb':
            return self.mydb
        else:
            raise KeyError("Invalid key '%s'" % str(index))


    def __setitem__(self,index, value):
        """
        Set individuals parameters
        """
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
        elif index=='mydb':
            self.mydb=value
        elif index=='url':
            self.reload_client=True
            self.url = value
            if value is None:
                raise TypeError, 'url param can not be NoneType'
        else:
            raise KeyError("Invalid key '%s'" % str(index))


    def get_base_url(self):
        self.refresh_ob()
        if self.url:
            return self.url
        else:
            return "https://%s:%s/v1" %(self.host, self.port)


    def check_connection(self):
        return self.get_onebox_net_mode(self, timeout_value=5)


    def get_onebox_net_mode(self, tid=None, tpath=None, timeout_value = 30):

        URLrequest = self.get_base_url() + "/wanmonitor"
        log.debug("Request request URL: %s" % URLrequest)
        
        try:
            ob_response = requests.get(URLrequest, verify=False, timeout=timeout_value, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("Failed to get the network mode of One-Box due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        return self._parse_json_response(ob_response)


    def backup_onebox(self, req_dict, tid=None, tpath=None):

        log.debug("[HJC] backup_onebox: %s" % (str(req_dict)))
        
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/backup"
        log.debug("Backup request URL: %s" %URLrequest)
        
        reqDict = {'backup_server_ip':req_dict['backup_server']}
        
        if tid: reqDict['tid']=tid
        if tpath: reqDict['tpath']=tpath
        
        payload_req = json.dumps(reqDict)
        log.debug("Backup request body = %s" % str(payload_req))
        
        try:
            ob_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to backup One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to backup One-Box : %s" % str(e))
            return -500, str(e)
        
        return self._parse_json_response(ob_response)

        
    def restore_onebox(self, req_dict, tid=None, tpath=None):

        log.debug("[HJC] restore_onebox: %s" % (str(req_dict)))
        
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/restore"
        log.debug("Request request URL: %s" % URLrequest)
        
        reqDict = {'backup_server_ip':req_dict['backup_server']}
        if 'backup_location' in req_dict: reqDict['remote_location'] = req_dict['backup_location']
        if 'backup_local_location' in req_dict: reqDict['local_location'] = req_dict['backup_local_location']
        if 'backup_data' in req_dict: reqDict['backup_data'] = req_dict['backup_data']
        
        if tid: reqDict['tid'] = tid
        if tpath: reqDict['tpath'] = tpath
        
        payload_req = json.dumps(reqDict)
        log.debug("Request body = %s" % str(payload_req))
        
        try:
            ob_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to restore One-Box due to HTTP Error %s" %str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to restore One-Box : %s" % str(e))
            return -500, str(e)
        
        return self._parse_json_response(ob_response)

    
    # def freset_onebox(self, req_dict, tid=None, tpath=None):
    #
    #     log.debug("[HJC] freset_onebox: %s"%(str(req_dict)))
    #
    #     headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
    #     URLrequest = self.get_base_url() + "/reset"
    #     log.debug("Request request URL: %s" %URLrequest)
    #
    #     #reqDict = {'onebox_id':req_dict['onebox_id']}
    #     reqDict = {'backup_server_ip':req_dict['backup_server']}
    #
    #     if tid: reqDict['tid']=tid
    #     if tpath: reqDict['tpath']=tpath
    #
    #     payload_req = json.dumps(reqDict)
    #     log.debug("Request body = %s" %str(payload_req))
    #
    #     try:
    #         ob_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, tiemout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
    #     except (HTTPException, ConnectionError), e:
    #         log.exception("failed to factory reset One-Box due to HTTP Error %s" %str(e))
    #         return -500, str(e)
    #     except Exception, e:
    #         log.error("Failed to factory reset One-Box : %s" % str(e))
    #         return -500, str(e)
    #
    #     return self._parse_json_response(ob_response)


    def check_onebox_agent_progress(self, request_type = None, transaction_id=None):

        log.debug("[HJC] check_onebox_agent_progress")

        if request_type:    # "restore"
            URLrequest = self.get_base_url() + "/" + request_type + "/progress"
        else:
            URLrequest = self.get_base_url() + "/progress"
            
        if transaction_id:
            URLrequest = URLrequest + "?transaction_id=" + transaction_id
        log.debug("Request request URL: %s" % URLrequest)
        
        try:
            ob_response = requests.get(URLrequest, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to check the agent-progress of One-Box due to HTTP Error %s" %str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to check the agent-progress of One-Box : %s" % str(e))
            return -500, str(e)
        
        return self._parse_json_response(ob_response)


    def get_onebox_info(self, req_dict, tid=None, tpath=None):

        log.debug("[HJC] get_onebox_info: %s" % (str(req_dict)))

        retry = 3
        try_cnt = 0
        ob_response = None

        while True:
            URLrequest = self.get_base_url() + "/onebox_info"
            log.debug("Request request URL: %s" %URLrequest)
            try:
                try_cnt += 1
                ob_response = requests.get(URLrequest, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
            except Exception, e:
                if try_cnt < retry:
                    time.sleep(3)
                    log.debug("Retry calling API to get onebox info : %d" % try_cnt)
                    continue
                else:
                    log.error("failed to get one-box info due to HTTP Error %s" %str(e))
                    return -500, str(e)
            break

        return self._parse_json_response(ob_response)


    # def check_onebox_status(self, req_dict, tid=None, tpath=None):
    #
    #     log.debug("[HJC] check_onebox_status: %s" % (str(req_dict)))
    #
    #     URLrequest = self.get_base_url() + "/status"
    #     log.debug("Request request URL: %s" % URLrequest)
    #
    #     try:
    #         ob_response = requests.get(URLrequest, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
    #     except (HTTPException, ConnectionError), e:
    #         log.exception("failed to check the status of One-Box due to HTTP Error %s" %str(e))
    #         return -500, str(e)
    #     except Exception, e:
    #         log.error("Failed to check the status of One-Box : %s" % str(e))
    #         return -500, str(e)
    #
    #     return self._parse_json_response(ob_response)


    # def check_onebox_action_status(self, action, req_dict, tid=None, tpath=None):
    #
    #     log.debug("[HJC] check_onebox_action_status: %s"%(str(req_dict)))
    #
    #     param_tid = "?transaction_id=" + req_dict['tid']
    #
    #     URLrequest = None
    #     if action == "backup":
    #         URLrequest = self.get_base_url() + "/backupstatus" + param_tid
    #     elif action == "restore":
    #         URLrequest = self.get_base_url() + "/restorestatus" + param_tid
    #     elif action == "freset":
    #         URLrequest = self.get_base_url() + "/resetstatus" + param_tid
    #     else:
    #         pass
    #
    #     log.debug("Request request URL: %s" % URLrequest)
    #
    #     try:
    #         ob_response = requests.get(URLrequest, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
    #     except (HTTPException, ConnectionError), e:
    #         log.exception("failed to check the action-status of One-Box due to HTTP Error %s" %str(e))
    #         return -500, str(e)
    #     except Exception, e:
    #         log.error("Failed to check the action-status of One-Box : %s" % str(e))
    #         return -500, str(e)
    #
    #     return self._parse_json_response(ob_response)


    def refresh_ob(self):

        result, content = orch_dbm.get_server_id(self.mydb, self.name)
        if result < 0:
            log.error("refresh_ob error %d %s" % (result, content))
            return result, content
        elif result==0:
            log.error("refresh_ob not found a valid server info with the input params " + str(self.name))
            return -HTTP_Not_Found, "server not found for " +  str(self.name)

        self.url = content['obagent_base_url']

        log.debug("[HJC] obagent Info Refreshed to %s" %str(self.url))

        return 200, "OK"


    def do_switch_wan(self, type, vdu_name, vm_local_ip, time_interval = 3, e2e_log=None):
        # 1. compose request body
        if e2e_log:
            e2e_tid = e2e_log['tid']
            e2e_tpath = e2e_log['tpath']
        else:
            e2e_tid = "Test-TID-SWITCHWAN-001"
            e2e_tpath = "orch-f"    
        
        job_id = af.create_uuid()
        req_dict = {'job_id':job_id, 'direction':type, 'local_ip':vm_local_ip}
        
        # 2. switch wan
        result, content = self.switch_wan(req_dict, e2e_tid, e2e_tpath)
        if result < 0:
            log.error("Failed to switch_wan: %d %s" %(result, content))
            content={'status':"UNKNOWN", 'msg': str(content)}
            #return result, content
        
        job_progress = content.get('status', "UNKNOWN")
        check_num = 0
        max_check_num = 12
        
        while job_progress == "DOING" or job_progress == "UNKNOWN":
            time.sleep(20)

            log.debug("[HJC] Check number: %d" %check_num)
            check_result, check_content = self.check_job_progress(job_id)
            if check_result < 0:
                log.warning("Failed to check the job progress: %d %s" %(check_result, check_content))
                if check_content == "FAIL":
                    job_progress = "FAIL"
                else:
                    job_progress = "UNKNOWN"
            else:
                job_progress = check_content.get('status', "UNKNOWN")

            log.debug("%d Check Result: %s" %(check_num, job_progress))

            check_num += 1

            if check_num >= max_check_num:
                break

        if job_progress != "DONE":
            log.error("Failed to switch wan: result = %s" %job_progress)
            return -500, job_progress
        
        # 3. test wan
        time.sleep(time_interval)

        job_id = af.create_uuid()
        req_dict['job_id'] = job_id
        result, content = self.test_network_ready(req_dict, e2e_tid, e2e_tpath)
        
        if result < 0:
            log.error("Failed to test wan: %d %s" %(result, content))
            return result, content
        
        job_progress = content.get('status', "UNKNOWN")
        check_num = 0
        max_check_num = 12
        
        while job_progress == "DOING" or job_progress == "UNKOWN":
            time.sleep(10)
            log.debug("[HJC] Check number: %d" %check_num)
            check_result, check_content = self.check_job_progress(job_id)
            if check_result < 0:
                log.warning("Failed to check the job progress: %d %s" %(check_result, check_content))
                if check_content == "FAIL":
                    job_progress = "FAIL"
                else:
                    job_progress = "UNKNOWN"
            else:
                job_progress = check_content.get('status', "UNKOWN")

            log.debug("%d Check Result: %s" %(check_num, job_progress))

            check_num += 1

            if check_num >= max_check_num:
                break        
    
        log.debug("[HJC] switch_wan - result = %s" %job_progress)

        if job_progress == "DONE":
            return 200, job_progress
        else:
            return -500, job_progress


    def switch_wan(self, req_dict, tid=None, tpath=None):
        if 'job_id' not in req_dict:
            log.error("Error: No Job ID")
            return -500, "Error: No Job ID"
        
        if 'local_ip' not in req_dict:
            log.error("Error: No Local IP Address")
            return -500, "Error: No Local IP Address"

        direction = req_dict.get('direction')
        if direction is None:
            log.error("Error: No Direction")
            return -500, "Error: No Direction"
        elif direction != "host2vm" and direction != "vm2host":
            log.error("Error: Invalid Direction: %s" %str(direction))
            return -500, "Error: Invalid Direction: %s" %str(direction)

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/wanswitch"
        log.debug("Request request URL: %s" %URLrequest)

        reqDict = {'job_id':req_dict['job_id'], 'direction':direction, 'local_ip':req_dict['local_ip'], "vnf_name":"NONE"}
        
        if tid: reqDict['tid']=tid
        if tpath: reqDict['tpath']=tpath

        payload_req = json.dumps(reqDict)
        log.debug("Request body = %s" %str(payload_req))

        try:
            oba_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.error("failed to move IP address from host to VM due to HTTP Error %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(oba_response)


    def test_network_ready(self, req_dict, tid=None, tpath=None):
        if 'job_id' not in req_dict:
            log.error("Error: No Job ID")
            return -500, "Error: No Job ID"

        if 'local_ip' not in req_dict:
            log.error("Error: No Local IP Address")
            return -500, "Error: No Local IP Address"

        direction = req_dict.get('direction')
        if direction is None:
            log.error("Error: No Direction")
            return -500, "Error: No Direction"
        elif direction != "host2vm" and direction != "vm2host":
            log.error("Error: Invalid Direction: %s" % str(direction))
            return -500, "Error: Invalid Direction: %s" % str(direction)


        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/wanswitch/test"
        log.debug("Request request URL: %s" %URLrequest)

        reqDict = {'job_id':req_dict['job_id'], 'direction':direction, 'local_ip':req_dict['local_ip'], "vnf_name":"NONE"}
        if 'vnf_name' in req_dict: reqDict['vnf_name'] = req_dict['vnf_name']

        if tid: reqDict['tid']=tid
        if tpath: reqDict['tpath']=tpath

        payload_req = json.dumps(reqDict)
        log.debug("Request body = %s" % str(payload_req))
        
        try:
            oba_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.error("Failed to check if the One-Box network is ready due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to check if the One-Box network is ready due to any Exception : %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(oba_response)


    def check_job_progress(self, job_id=None, tid=None):

        if job_id is None:
            log.error("No Job ID")
            return -500, "No Job TID"

        URL_request = self.get_base_url() + "/wanswitch/jobprogress/" + job_id

        log.debug("URL_request = %s" % URL_request)

        try:
            oba_response = requests.get(URL_request, timeout=10, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.error("failed to check progress for %s due to HTTP Error %s" %(job_id, str(e)))
            return -500, str(e)

        return self._parse_json_response(oba_response)


    # def suspend_monitor_wan(self, vdu_name, vm_local_ip, vnf_name=None, tid=None, tpath=None):
    #
    #     URLrequest = self.get_base_url() + "/wanmonitor/pause"
    #     log.debug("Request request URL: %s" % URLrequest)
    #
    #     try:
    #         oba_response = requests.get(URLrequest, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
    #     except (HTTPException, ConnectionError), e:
    #         log.error("failed to suspend monitoring WAN of One-Box Agent %s" %str(e))
    #         return -500, str(e)
    #
    #     return self._parse_json_response(oba_response)


    def resume_monitor_wan(self, vdu_name=None, vm_local_ip=None, vnf_name=None, tid=None, tpath=None):

        URLrequest = self.get_base_url() + "/wanmonitor/resume"
        log.debug("Request request URL : %s" % URLrequest)

        try:
            oba_response = requests.get(URLrequest, verify=False, timeout=30, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.error("Failed to resume monitoring WAN of One-Box Agent %s" %str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to resume monitoring WAN of One-Box Agent : %s" %str(e))
            return -500, str(e)
        return self._parse_json_response(oba_response)


    def _parse_json_response(self, ob_response):
        try:
            log.debug("Response from One-Box Agent = %s" %str(ob_response.text))
            log.debug("Response HTTP Code from One-Box Agent = %s" %str(ob_response.status_code))
            #if ob_response.status_code == 200:
            content = ob_response.json()
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'
            
        if ob_response.status_code==200:
            result = 200
        else:
            result = -ob_response.status_code
            return result, content['error']['description']
        
        return result, content


    def _parse_response(self, ob_response):
        try:
            content = ob_response.json()
            log.debug("_parse_response() response body: %s" % str(content))
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'
            
        try:
            if ob_response.status_code == 200:
                return ob_response.status_code, content
            else:
                if 'error' in content:
                    return -ob_response.status_code, content['error']['description']
                else:
                    return -ob_response.status_code, "Invalid Response"                
        except (KeyError, TypeError) as e:
            log.exception("_parse_response() exception while parsing response %s" % str(e))
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
        
        return -HTTP_Internal_Server_Error, "Unknown Error" 
