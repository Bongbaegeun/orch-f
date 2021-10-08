# -*- coding: utf-8 -*-

from sbpm.plugin_spec.oba.GeneralObaSpec import GeneralObaSpec

import requests
import json
import sys
import time

import db.dba_manager as orch_dbm

from httplib import HTTPException
from requests.exceptions import ConnectionError
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


CLIENT_ORCH_CRT = '/var/onebox/key/client_orch.crt'
CLIENT_ORCH_KEY = '/var/onebox/key/client_orch.key'


class GeneralOba(GeneralObaSpec):
    def __init__(self):
        # self.id = None
        self.name = None
        # self.user = None
        # self.passwd = None
        self.host = None
        self.port = None
        self.url = None
        # self.config = None
        # self.debug = None
        # self.reload_client = True

    def __getitem__(self,index):
        if index=='name':
            return self.name
        # elif index=='id':
        #     return self.id
        # elif index=='user':
        #     return self.user
        # elif index=='passwd':
        #     return self.passwd
        elif index=='host':
            return self.host
        elif index=='port':
            return self.port
        elif index=='url':
            return self.url
        # elif index=='config':
        #     return self.config
        # elif index=='debug':
        #     return self.debug
        # elif index=='reload_client':
        #     return self.reload_client
        else:
            raise KeyError("Invalid key '%s'" % str(index))

    def __setitem__(self,index, value):
        """
        Set individuals parameters
        """
        if index=='name':
            self.name = value
        # elif index=='id':
        #     self.id = value
        # elif index=='user':
        #     self.reload_client=True
        #     self.user = value
        # elif index=='passwd':
        #     self.reload_client=True
            self.passwd = value
        elif index=='host':
            self.reload_client=True
            self.host=value
        elif index=='port':
            self.reload_client=True
            self.port=value
        # elif index=='config':
        #     self.reload_client=True
        #     self.port=value
        # elif index=='debug':
        #     self.reload_client=True
        #     self.port=value
        # elif index=='reload_client':
        #     self.reload_client=True
        #     self.port=value
        elif index=='url':
            self.reload_client=True
            self.url = value
            if value is None:
                raise TypeError, 'url param can not be NoneType'
        else:
            raise KeyError("Invalid key '%s'" % str(index))

    def get_version(self):
        log.debug("IN get_version()")
        return 1, "v0.0.1"

    def get_status(self):
        log.debug("IN get_status()")
        return 0, "Not Supported"

    def get_onebox_info(self, req_dict=None, tid=None, tpath=None):
        # log.debug("[SBPM - obconnector] get_onebox_info: %s" % (str(req_dict)))

        retry = 3
        try_cnt = 0
        ob_response = None

        while True:
            # URLrequest = self._get_base_url() + "/onebox_info"
            if 'obagent_base_url' in req_dict:
                if req_dict.get('obagent_base_url') is None:
                    URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/onebox_info"
                else:
                    URLrequest = req_dict.get('obagent_base_url') + "/onebox_info"
            else:
                URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/onebox_info"

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

    def onebox_backup(self, req_info):
        # log.debug("IN backup_onbox()")
        log.debug("[Action :: Backup] backup_onebox: %s" % (str(req_info)))

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}

        if 'obagent_base_url' in req_info:
            if req_info.get('obagent_base_url') is None:
                URLrequest = self._get_base_url(req_info.get('onebox_id')) + "/backup"
            else:
                URLrequest = req_info.get('obagent_base_url') + "/backup"
        else:
            URLrequest = self._get_base_url(req_info.get('onebox_id')) + "/backup"

        log.debug("Backup request URL: %s" % URLrequest)

        # reqDict = {'backup_server_ip': req_info['backup_server']}
        # reqDict['backup_server_port'] = 9922
        # reqDict['remote_location'] = req_info['remote_location']
        # reqDict['local_location'] = req_info['local_location']

        # if req_info['tid']: reqDict['tid'] = req_info['tid']
        # if req_info['tpath']: reqDict['tpath'] = req_info['tpath']

        reqDict = {}
        payload_req = json.dumps(reqDict)
        # log.debug("Backup request body = %s" % str(payload_req))

        try:
            ob_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to backup One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to backup One-Box : %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(ob_response)


    # restore
    def onebox_restore(self, req_dict, tid=None, tpath=None):

        log.debug("[HJC] restore_onebox: %s" % (str(req_dict)))

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}

        # URLrequest = self._get_base_url() + "/restore"
        if 'obagent_base_url' in req_dict:
            if req_dict.get('obagent_base_url') is None:
                URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/restore"
            else:
                URLrequest = req_dict.get('obagent_base_url') + "/restore"
        else:
            URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/restore"

        log.debug("Request request URL: %s" % URLrequest)

        # reqDict = {'backup_server_ip': req_dict['backup_server']}
        reqDict = {}
        # if 'backup_location' in req_dict: reqDict['remote_location'] = req_dict['backup_location']
        if 'backup_local_location' in req_dict: reqDict['local_location'] = req_dict['backup_local_location']
        if 'backup_file' in req_dict: reqDict['backup_file'] = req_dict['backup_file']

        if tid: reqDict['tid'] = tid
        if tpath: reqDict['tpath'] = tpath

        payload_req = json.dumps(reqDict)
        log.debug("Request body = %s" % str(payload_req))

        try:
            ob_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to restore One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to restore One-Box : %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(ob_response)


    # reboot agent call
    def onebox_reboot(self, req_dict, tid=None, tpath=None):

        log.debug("[WF - Reboot] obconnector > reboot_onebox: %s" % (str(req_dict)))

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        # URLrequest = self._get_base_url() + "/reboot"

        if 'obagent_base_url' in req_dict:
            if req_dict.get('obagent_base_url') is None:
                URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/reboot"
            else:
                URLrequest = req_dict.get('obagent_base_url') + "/reboot"
        else:
            URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/reboot"

        log.debug("Request request URL: %s" % URLrequest)

        try:
            ob_response = requests.post(URLrequest, headers=headers_req, data=None, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to restore One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to restore One-Box : %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(ob_response)


    # One-Box Agent 진행 상태 조회
    def wf_check_onebox_agent_progress(self, progress_dict, request_type=None, transaction_id=None):

        log.debug("[HJC] check_onebox_agent_progress")

        if 'obagent_base_url' in progress_dict:
            if progress_dict.get('obagent_base_url') is None:
                get_base_url = self._get_base_url(progress_dict.get('onebox_id'))
            else:
                get_base_url = progress_dict.get('obagent_base_url')
        else:
            get_base_url = self._get_base_url(progress_dict.get('onebox_id'))

        if request_type:  # "restore", "reboot"
            if request_type == "restore":
                URLrequest = get_base_url + "/" + request_type + "/progress"
            else:   # reboot
                # URLrequest = self._get_base_url() + "/version"
                URLrequest = get_base_url + "/onebox_info"
        else:
            URLrequest = get_base_url + "/progress"

        # 초소형인 경우 transaction_id 필요없음
        if transaction_id:
            URLrequest = URLrequest + "?transaction_id=" + transaction_id

        log.debug("Request request URL: %s" % URLrequest)

        try:
            ob_response = requests.get(URLrequest, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY), timeout=30)
            log.debug('wf_check_onebox_agent_progress : ob_response = %s' %str(ob_response))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to check the agent-progress of One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to check the agent-progress of One-Box : %s" % str(e))
            return -500, str(e)
        # except requests.Timeout as timeout_error:
        #     log.exception("failed to check the agent-progress of One-Box agent connection timeout HTTP Error %s" % str(timeout_error))
        #     return -500, str(timeout_error)

        return self._parse_json_response(ob_response)

    # 동작 점검
    def connection_check(self, req_info=None):
        return self._get_onebox_net_mode(req_info, timeout_value=5)

    def _get_onebox_net_mode(self, req_info, tid=None, tpath=None, timeout_value=30):

        if 'obagent_base_url' in req_info:
            if req_info.get('obagent_base_url') is None:
                URLrequest = self._get_base_url(req_info.get('onebox_id')) + "/wanmonitor"
            else:
                URLrequest = req_info.get('obagent_base_url') + "/wanmonitor"
        else:
            URLrequest = self._get_base_url(req_info.get('onebox_id')) + "/wanmonitor"

        log.debug("Request request URL: %s" % URLrequest)

        try:
            ob_response = requests.get(URLrequest, verify=False, timeout=timeout_value, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("Failed to get the network mode of One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(ob_response)


    def provisionning_arm(self, req_dict=None):

        log.debug("[WF - provisionning] obconnector > provisionning_arm: %s" % (str(req_dict)))

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        # URLrequest = self._get_base_url() + "/reboot"

        if 'obagent_base_url' in req_dict:
            if req_dict.get('obagent_base_url') is None:
                URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/vnf/set"
            else:
                URLrequest = req_dict.get('obagent_base_url') + "/vnf/set"
        else:
            URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/vnf/set"

        log.debug("Request request URL: %s" % URLrequest)

        reqDict = {}
        reqDict['image_name'] = req_dict.get('image_name')

        payload_req = json.dumps(reqDict)
        log.debug("Request body = %s" % str(payload_req))

        try:
            ob_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to restore One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to restore One-Box : %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(ob_response)


    def delete_arm(self, req_dict=None):

        log.debug("[WF - delete] obconnector > delete_arm: %s" % (str(req_dict)))

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        # URLrequest = self._get_base_url() + "/reboot"

        if 'obagent_base_url' in req_dict:
            if req_dict.get('obagent_base_url') is None:
                URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/vnf/unset"
            else:
                URLrequest = req_dict.get('obagent_base_url') + "/vnf/unset"
        else:
            URLrequest = self._get_base_url(req_dict.get('onebox_id')) + "/vnf/unset"

        log.debug("Request request URL: %s" % URLrequest)

        try:
            ob_response = requests.post(URLrequest, headers=headers_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to restore One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to restore One-Box : %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(ob_response)


    def prov_check_onebox_agent_progress_arm(self, progress_dict, request_type=None, transaction_id=None):
        log.debug("[BBG] prov_check_onebox_agent_progress_arm")

        if 'obagent_base_url' in progress_dict:
            if progress_dict.get('obagent_base_url') is None:
                get_base_url = self._get_base_url(progress_dict.get('onebox_id'))
            else:
                get_base_url = progress_dict.get('obagent_base_url')
        else:
            get_base_url = self._get_base_url(progress_dict.get('onebox_id'))

        if request_type:  # "restore", "reboot"
            if request_type == "restore":
                URLrequest = get_base_url + "/vnf"
            else:  # reboot
                # URLrequest = self._get_base_url() + "/version"
                URLrequest = get_base_url + "/vnf"
        else:
            URLrequest = get_base_url + "/vnf"

        # 초소형인 경우 transaction_id 필요없음
        if transaction_id:
            URLrequest = URLrequest + "?transaction_id=" + transaction_id

        log.debug("Request request URL: %s" % URLrequest)

        reqDict = {}
        reqDict['order'] = progress_dict.get('order')

        payload_req = json.dumps(reqDict)
        log.debug("Request body = %s" % str(payload_req))

        try:
            ob_response = requests.post(URLrequest, data=payload_req, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY), timeout=30)
            log.debug('wf_check_onebox_agent_progress : ob_response = %s' % str(ob_response))
        except (HTTPException, ConnectionError), e:
            log.exception("failed to check the agent-progress of One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to check the agent-progress of One-Box : %s" % str(e))
            return -500, str(e)
        # except requests.Timeout as timeout_error:
        #     log.exception("failed to check the agent-progress of One-Box agent connection timeout HTTP Error %s" % str(timeout_error))
        #     return -500, str(timeout_error)

        return self._parse_json_response(ob_response)



    def _get_base_url(self, onebox_id=None):
        self._refresh_ob(onebox_id)
        if self.url:
            return self.url
        else:
            return "https://%s:%s/v1" %(self.host, self.port)

    def _parse_json_response(self, ob_response):
        try:
            if "backup_data" not in ob_response:
                log.debug("Response from One-Box Agent = %s" % str(ob_response.text))
            log.debug("Response HTTP Code from One-Box Agent = %s" % str(ob_response.status_code))
            # if ob_response.status_code == 200:
            content = ob_response.json()
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'

        if ob_response.status_code == 200:
            result = 200
        else:
            result = -ob_response.status_code
            # return result, content['error']['description']
            return result, content['error_desc']

        return result, content

    def _refresh_ob(self, onebox_id=None):

        if onebox_id is None:
            name = self.name
        else:
            name = onebox_id

        result, content = orch_dbm.get_server_id(name)
        if result < 0:
            log.error("refresh_ob error %d %s" % (result, content))
            return result, content
        elif result==0:
            log.error("refresh_ob not found a valid server info with the input params " + str(name))
            return -HTTP_Not_Found, "server not found for " +  str(name)

        self.url = content['obagent_base_url']

        log.debug("[HJC] obagent Info Refreshed to %s" %str(self.url))

        return 200, "OK"

