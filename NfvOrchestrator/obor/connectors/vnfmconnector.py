# coding=utf-8
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
    vnfmconnector implements all the methods to interact with VNFM in One-Boxes.
"""
__author__="Jechan Han"
__date__ ="$19-Oct-2015 11:19:29$"

import requests
import json
import time
import sys
import copy
from httplib import HTTPException
from requests.exceptions import ConnectionError

from db.orch_db import HTTP_Bad_Request, HTTP_Not_Found, HTTP_Unauthorized, HTTP_Conflict, HTTP_Internal_Server_Error
import db.orch_db_manager as orch_dbm
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

CLIENT_ORCH_CRT = '/var/onebox/key/client_orch.crt'
CLIENT_ORCH_KEY = '/var/onebox/key/client_orch.key'



class vnfmconnector():


    def __init__(self, id, name, url, mydb, host=None, port=None, user=None, passwd=None, debug=True, config={}):
        """
        using common constructor parameters. In this case 'url' is the ip address or ip address:port,
        """
 
        self.id        = id
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
            raise KeyError("Invalid key '%s'" %str(index))


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
        elif index=='url':
            self.reload_client=True
            self.url = value
            if value is None:
                raise TypeError, 'url param can not be NoneType'
        elif index=='mydb':
            self.mydb = value
        else:
            raise KeyError("Invalid key '%s'" %str(index))


    def refresh_vnfm(self):

        result, content = orch_dbm.get_server_id(self.mydb, self.id)
        if result < 0:
            log.error("refresh_vnfm error %d %s" % (result, content))
            return result, content
        elif result==0:
            log.error("refresh_vnfm not found a valid VNFM info with the input params " + str(self.id))
            return -HTTP_Not_Found, "VNFM not found for " +  str(self.id)
        
        self.url = content['vnfm_base_url']
        
        log.debug("[HJC] VNFM Info Refreshed to %s" %str(self.url))
        
        return 200, "OK"    


    def get_base_url(self):

        if self.url:
            return self.url
        else:
            return "https://%s:%s/ktvnfm/v1" %(self.host, self.port)


    def check_connection(self):

        URLrequest = self.get_base_url() + "/status"
        
        try:
            vnfm_response = requests.get(URLrequest, verify=False, timeout=30, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))

        except Exception, e:
            log.exception("failed to check connection due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        return self._parse_response(vnfm_response)


    def check_progress(self, job_name, e2e_log=None):

        if job_name is None:
            return -HTTP_Bad_Request, "No Job Name"
        
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/"+job_name+"/progress"
        
        try:
            vnfm_response = requests.get(URLrequest, headers = headers_req, verify=False, timeout=30, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to init_config_vnf due to HTTP Error %s" %str(e))
            return -500, "UNKNOWN"
        
        result, content = self._parse_response(vnfm_response)
        if result < 0:
            log.error("Failed to VNFM Request - Check the progress: %d %s" %(result, content))
            content_result = "UNKNOWN"
        else:
            content_result = content.get("result", "UNKNOWN")
            if content_result != "DOING" and content_result != "DONE":
                result = -HTTP_Internal_Server_Error
        
        return result, content_result        


    def init_config_vnf(self, vnf_dict, e2e_log=None, bonding=None):

        log.debug("[INIT_CONFIG_VNF] IN ***********************")
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/action"
        
        vnf_dict['action'] = 'INIT'
        
        if e2e_log:
            vnf_dict['tid'] = e2e_log['tid']
            vnf_dict['tpath'] = e2e_log['tpath']
        else:
            vnf_dict['tid']='test-tid'
            vnf_dict['tpath']='test-tpath'

        if bonding is True:
            log.debug('=========    bonding : %s    #################' %str(bonding))

        # log.debug('vnf_dict = %s' %str(vnf_dict))

        if bonding:
            vnf_dict['scripts'] = self._set_bonding_script(vnf_dict)
            
        payload_req = json.dumps(vnf_dict)
        try:
            log.debug("[*****INIT_CONFIG_VNF*******] post request = %s" %str(payload_req))
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=60, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
            log.debug("[*****INIT_CONFIG_VNF*******] post response = %s" %str(vnfm_response))
        except Exception, e:
            log.exception("failed to init_config_vnf due to HTTP Error %s" %str(e))
            return -500, str(e)

        result, content = self._parse_response(vnfm_response)
        if result < 0:
            log.error("Failed to VNFM Request: %d %s" %(result, content))
            return result, content
        elif content.get('result', "UNKOWN") == "DOING" and content.get("job_name") is not None:

            log.debug("[*****INIT_CONFIG_VNF*******] parse response content = %s" %str(content))
            content_result = content.get('result', "UNKNOWN")
            check_count = 0
            while content_result == "DOING" or content_result == "UNKNOWN":
                if check_count >= 25:
                    log.error("Failed to check if the progress finish: check count = %d" % check_count)
                    return -500, "Failed to init config over checking count = %d" % check_count
                try:
                    log.debug("[INIT_CONFIG_VNF] Check count %d START" %check_count)
                    time.sleep(30)
                    self.refresh_vnfm()
                    log.debug("[INIT_CONFIG_VNF] Check count %d ING" %check_count)
                    result, content_result = self.check_progress(content['job_name'])
                    log.debug("[INIT_CONFIG_VNF] check count = %d END, check_result = %s" %(check_count, str(content_result)))
                except Exception, e:
                    log.exception("[INIT_CONFIG_VNF] Check count %d, Exception: %s" %(check_count, str(e)))

                check_count += 1                
        else:
            log.debug("No more progress: %d %s" %(result, str(content)))
        return result, content


    def init_config_vnf_intval(self, vnf_dict, e2e_log=None, bonding=None, intval=30):

        log.debug("[INIT_CONFIG_VNF] IN ***********************")
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/action"

        vnf_dict['action'] = 'INIT'

        if e2e_log:
            vnf_dict['tid'] = e2e_log['tid']
            vnf_dict['tpath'] = e2e_log['tpath']
        else:
            vnf_dict['tid'] = 'test-tid'
            vnf_dict['tpath'] = 'test-tpath'

        log.debug('=========    bonding : %s    #################' % str(bonding))
        # log.debug('vnf_dict = %s' %str(vnf_dict))

        if bonding:
            vnf_dict['scripts'] = self._set_bonding_script(vnf_dict)

        payload_req = json.dumps(vnf_dict)
        try:
            log.debug("[*****INIT_CONFIG_VNF*******] post request = %s" % str(payload_req))
            vnfm_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False, timeout=60, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
            log.debug("[*****INIT_CONFIG_VNF*******] post response = %s" % str(vnfm_response))
        except Exception, e:
            log.exception("failed to init_config_vnf due to HTTP Error %s" % str(e))
            return -500, str(e)

        result, content = self._parse_response(vnfm_response)
        if result < 0:
            log.error("Failed to VNFM Request: %d %s" % (result, content))
            return result, content
        elif content.get('result', "UNKOWN") == "DOING" and content.get("job_name") is not None:

            log.debug("[*****INIT_CONFIG_VNF*******] parse response content = %s" % str(content))
            content_result = content.get('result', "UNKNOWN")
            check_count = 0
            while content_result == "DOING" or content_result == "UNKNOWN":
                if check_count >= 25:
                    log.error("Failed to check if the progress finish: check count = %d" % check_count)
                    return -500, "Failed to init config over checking count = %d" % check_count
                try:
                    log.debug("[INIT_CONFIG_VNF] Check count %d START" % check_count)
                    time.sleep(intval)
                    self.refresh_vnfm()
                    log.debug("[INIT_CONFIG_VNF] Check count %d ING" % check_count)
                    result, content_result = self.check_progress(content['job_name'])
                    log.debug("[INIT_CONFIG_VNF] check count = %d END, check_result = %s" % (check_count, str(content_result)))
                except Exception, e:
                    log.exception("[INIT_CONFIG_VNF] Check count %d, Exception: %s" % (check_count, str(e)))

                check_count += 1
        else:
            log.debug("No more progress: %d %s" % (result, str(content)))
        return result, content

    # 본딩 구성 요청일 경우
    def _set_bonding_script(self, req_info):
        log.debug('-----------  _set_bonding_script ----------------- : bonding script change')

        tmp_scripts_uplink = []
        tmp_scripts_route = []

        origin_scripts = copy.deepcopy(req_info.get('scripts'))

        for sc in origin_scripts:
            if sc.get('name').find('uplink') > 0:
                tmp_scripts_uplink.append(sc)
            elif sc.get('name').find('route') > 0:
                tmp_scripts_route.append(sc)
            else:
                continue

        # 1. 라우팅 정보 제거 스크립트 추가
        cp_tmp_scripts_route = copy.deepcopy(tmp_scripts_route)
        cp_tmp_scripts_uplink = copy.deepcopy(tmp_scripts_uplink)

        for rsc in tmp_scripts_route:
            rsc['body'] = rsc['body'].replace('ip route', 'no ip route')

        # 2. interface 정보 제거 스크립트 추가
        default_route_list = []
        for usc in tmp_scripts_uplink:
            tmp_interface_name = None
            default_gw = usc.get('body_args')[2]
            tmp_body_int = usc.get('body').split('\\n')

            for b in tmp_body_int:
                if b.find('interface') < 0:
                    continue

                tmp_b = b.split(' ')
                tmp_interface_name = tmp_b[1]
                break

            drl_dict = {}
            drl_dict['interface'] = tmp_interface_name
            drl_dict['default_gw'] = default_gw

            if len(default_route_list) > 0:
                for dr_list in default_route_list:
                    if dr_list.get('default_gw') == default_gw:
                        continue

                    default_route_list.append(drl_dict)
            else:
                default_route_list.append(drl_dict)

            usc['body'] = usc['body'].replace('ip address', 'no ip address')

            if tmp_interface_name == 'eth5':
                usc['body'] = usc['body'].replace(' %s/%s', '')
                del usc['body_args'][0]
                del usc['body_args'][0]
                log.debug('interface_body = %s' %str(usc['body']))
                log.debug('body_args = %s' %str(usc['body_args']))

            usc['body'] = usc['body'].replace('ip gateway', 'no ip gateway')
            usc['body'] = usc['body'].replace('link-check', 'no link-check')
            # usc['body'] = usc['body'].replace('no shutdown', 'no security-zone\\nshutdown')
            usc['body'] = usc['body'].replace('no shutdown', 'no security-zone\\nno shutdown')

        # 2-1. 디폴트 라우팅 스크립트 추가
        default_route_list_append = []
        default_gw_list = []
        default_gw_ip = None
        for drl in default_route_list:
            if default_gw_ip != drl.get('default_gw'):
                default_gw_ip = drl.get('default_gw')
                default_gw_list.append(default_gw_ip)

            for cptsr in cp_tmp_scripts_route:
                cptsr_body = cptsr.get('body').split('\\n')
                cptsr_body_route = cptsr_body[1].split(' ')

                if cptsr_body_route[3] != drl.get('interface'):
                    continue

                tmp_cptsr_route = cptsr_body_route[0] + ' ' + cptsr_body_route[1] + ' ' + cptsr_body_route[2] + ' ' + drl.get('default_gw')
                cptsr['body'] = cptsr_body[0] + '\\n' + tmp_cptsr_route + '\\n' + cptsr_body[2]
                default_route_list_append.append(cptsr)
                break

        # 3. bonding 스크립트 추가
        tmp_default_gw_ip = None
        for dgw in default_gw_list:
            if tmp_default_gw_ip is None:
                tmp_default_gw_ip = dgw
            else:
                tmp_default_gw_ip += ' ' + dgw

        sc_tmp = {}
        body = "cmd=configure terminal\\ninterface bond0\\nbonding mode active-backup primary-reselect always arp-validate all\\n" \
               "bonding link-check arp-interval 1 arp-ip-target %s\\n" %str(tmp_default_gw_ip)
               # "bonding link-check miimon 1\\n"
        primary_interface = None
        ip_addr = None

        cp_scripts = copy.deepcopy(req_info.get('scripts'))

        for sc in cp_tmp_scripts_uplink:
            interface_name = None
            tmp_body = sc.get('body').split('\\n')

            for b in tmp_body:
                if b.find('interface') < 0:
                    continue

                tmp_b = b.split(' ')
                interface_name = tmp_b[1]
                break

            body += "bonding slave %s\\n" % str(interface_name)

            if sc.get('name') == 'set_nic_uplink_static':
                sc_tmp = sc
                primary_interface = interface_name
                ip_addr = sc.get('body_args')[0] + '/' + sc.get('body_args')[1]

            if sc.get('name') == 'set_nic_uplinkR1_static':
                body += "bonding primary %s\\n" % str(primary_interface)
                body += "ip address %s\\n" % str(ip_addr)
                body += "ip address %s secondary\\n" % str(sc.get('body_args')[0] + '/' + sc.get('body_args')[1])

        body += "security-zone uplink_main\\nno shutdown\\nend"

        # log.debug('body = %s' % str(body))

        sc_tmp['body'] = body
        sc_tmp['body_args'] = []

        # log.debug('sc_tmp = %s' %str(sc_tmp))

        return_scripts = []

        for scripts in req_info.get('scripts'):
            # write_config 가 아닐때 기본 scripts 우선 append
            if scripts.get('name') != 'write_config':
                return_scripts.append(scripts)
                continue

            # default route 정보 제거 scripts append
            for tsr in tmp_scripts_route:
                return_scripts.append(tsr)

            # default interface 정보 제거 scripts append
            for tsu in tmp_scripts_uplink:
                return_scripts.append(tsu)

            # default route gateway 정보 scripts append : 이게 있어야 통신이 된다
            for drla in default_route_list_append:
                return_scripts.append(drla)

            # bonding 구성 scripts append
            return_scripts.append(sc_tmp)

            # 마지막으로 write_config 넣어준다
            return_scripts.append(scripts)

        # log.debug('return_scripts = %s' % str(return_scripts))

        return return_scripts

    
    def update_config_vnf(self, vnf_dict, e2e_log=None):

        log.debug("[UPDATE_CONFIG_VNF] IN ***************************")
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/action"

        vnf_dict['action'] = 'UPDATE'

        if e2e_log:
            vnf_dict['tid'] = e2e_log['tid']
            vnf_dict['tpath'] = e2e_log['tpath']
        else:
            vnf_dict['tid']='test-tid'
            vnf_dict['tpath']='test-tpath'

        payload_req = json.dumps(vnf_dict)
        try:
            log.debug("[*****UPDATE_CONFIG_VNF*******] post request = %s" %str(payload_req))
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=60, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
            log.debug("[*****UPDATE_CONFIG_VNF*******] post response = %s" %str(vnfm_response))
        except Exception, e:
            log.exception("failed to update_config_vnf due to HTTP Error %s" %str(e))
            return -500, str(e)
        result, content = self._parse_response(vnfm_response)
        if result < 0:
            log.error("Failed to VNFM Request: %d %s" %(result, content))
            return result, content
        elif content.get('result', "UNKOWN") == "DOING" and content.get("job_name") is not None:
            log.debug("[*****UPDATE_CONFIG_VNF*******] parse response content = %s" %str(content))
            content_result = content.get('result', "UNKNOWN")
            check_count = 0
            while content_result == "DOING" or content_result == "UNKNOWN":
                time.sleep(30)
                self.refresh_vnfm()
                log.debug("[UPDATE_CONFIG_VNF] Check count %d" %check_count)
                if check_count >= 25:
                    log.error("Failed to check if the progress finish: check count = %d" %check_count)
                    break
                result, content_result = self.check_progress(content['job_name'])
                log.debug("[UPDATE_CONFIG_VNF] check count = %d, check_result = %s" %(check_count, str(content_result)))

                check_count += 1
        else:
            log.debug("No more progress: %d %s" %(result, str(content)))
        return result, content


    def get_vnf_settings(self, vnf_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/action"
        
        vnf_dict['action'] = 'GET_SETTINGS'
        
        if e2e_log:
            vnf_dict['tid'] = e2e_log['tid']
            vnf_dict['tpath'] = e2e_log['tpath']
        else:
            vnf_dict['tid']='test-tid'
            vnf_dict['tpath']='test-tpath'
        
        payload_req = json.dumps(vnf_dict)
        
        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to init_config_vnf due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        result, content = self._parse_response(vnfm_response)
        if result < 0:
            return result, content
        
        log.debug("[GET_VNF_SETTINGS] result = %s" %(str(content)))
        output_list = []
        content_result = content.get('result')
        if content_result and len(content_result) > 0:
            for cr in content_result:
                if cr.get('result') != "OK": continue
                if cr.get('output') and len(cr['output']) > 0:
                    for oitem in cr['output']:
                        output_list.append(oitem)
        
        return 200, output_list


    def finish_vnf(self, vnf_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/action"
        
        vnf_dict['action'] = 'FIN'
        
        if e2e_log:
            vnf_dict['tid'] = e2e_log['tid']
            vnf_dict['tpath'] = e2e_log['tpath']
        else:
            vnf_dict['tid']='test-tid'
            vnf_dict['tpath']='test-tpath'
            
        payload_req = json.dumps(vnf_dict)
        log.debug("[FINISH_VNF] Request: %s" % payload_req)
        
        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to init_config_vnf due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        result, content = self._parse_response(vnfm_response)
        if result < 0:
            log.error("Failed to VNFM Request: %d %s" %(result, content))
            return result, content
        elif content.get('result', "UNKOWN") == "DOING" and content.get("job_name", None):
            content_result = content.get('result', "UNKNOWN")
            check_count = 0
            while content_result == "DOING" or content_result == "UNKNOWN":
                time.sleep(10)
                self.refresh_vnfm()
                log.debug("[FINISH_VNF] Check count %d" %check_count)
                if check_count >= 18:
                    log.error("Failed to check if the progress finish: check count = %d" %check_count)
                    break
                
                result, content_result = self.check_progress(content['job_name'])
                log.debug("[FINISH_VNF] check count = %d, check_result = %s" %(check_count, str(content_result)))
                
                check_count += 1                
        else:
            log.debug("No more progress: %d %s" %(result, str(content)))
        
        return result, content


    def test_vnf(self, vnf_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/action"
        
        vnf_dict['action'] = 'TEST'
        
        if e2e_log:
            vnf_dict['tid'] = e2e_log['tid']
            vnf_dict['tpath'] = e2e_log['tpath']
        else:
            vnf_dict['tid']='test-tid'
            vnf_dict['tpath']='test-tpath'
            
        payload_req = json.dumps(vnf_dict)
        
        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=60, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to test_vnf due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        return self._parse_response(vnfm_response)


    def backup_vdu(self, req_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/%s/backup" %(req_dict['vnf_name'])
        log.debug("[BACKUP_VDU] request URL: %s" % URLrequest)
        
        #req_dict['action']='BACKUP'
        vnfmReqDict = {'vnf_name':req_dict['vnf_name'], 'local_mgmt_ip':req_dict['ip'], 'backup_server_ip':req_dict['backup_server']}
        vnfmReqDict['vnfd_name'] = req_dict['vnfd_name']
        vnfmReqDict['vnfd_version'] = req_dict['vnfd_version']

        if e2e_log:
            vnfmReqDict['tid']=e2e_log['tid']
            vnfmReqDict['tpath']=e2e_log['tpath']
        else:
            vnfmReqDict['tid']='test-tid'
            vnfmReqDict['tpath']='test-tpath'
        
        payload_req = json.dumps(vnfmReqDict)
        log.debug("[BACKUP_VDU] request body = %s" % str(payload_req))
        
        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=80, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to backup VNF VDU due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        return self._parse_response(vnfm_response)


    def restore_vdu(self, req_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/%s/restore" %(req_dict['vnf_name'])
        
        #req_dict['action']='RESTORE'
        vnfmReqDict = {'vnf_name':req_dict['vnf_name'], 'local_mgmt_ip':req_dict['ip'], 'backup_server_ip':req_dict['backup_server']}
        vnfmReqDict['vnfd_name'] = req_dict['vnfd_name']
        vnfmReqDict['vnfd_version'] = req_dict['vnfd_version']
        if 'type' in req_dict: vnfmReqDict['type'] = req_dict['type']
        if 'backup_location' in req_dict: vnfmReqDict['remote_location'] = req_dict['backup_location']
        if 'backup_local_location' in req_dict: vnfmReqDict['local_location'] = req_dict['backup_local_location']
        if 'needWanSwitch' in req_dict: vnfmReqDict['needWanSwitch'] = req_dict['needWanSwitch']
        
        if e2e_log:
            vnfmReqDict['tid']=e2e_log['tid']
            vnfmReqDict['tpath']=e2e_log['tpath']
        else:
            vnfmReqDict['tid']='test-tid'
            vnfmReqDict['tpath']='test-tpath'
            
        payload_req = json.dumps(vnfmReqDict)
        log.debug("[RESTORE_VDU] request body = %s" % str(payload_req))
        
        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=30, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to restore VNF VDU due to HTTP Error %s" % str(e))
            return -505, str(e)
        
        return self._parse_response(vnfm_response)


    def check_vdu_status(self, req_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        self.refresh_vnfm()
        URLrequest = self.get_base_url() + "/vnfs/%s/status" %(req_dict['vnf_name'])
        
        vnfmReqDict = {'vnf_name':req_dict['vnf_name'], 'local_mgmt_ip':req_dict['ip']}
        vnfmReqDict['vnfd_name'] = req_dict['vnfd_name']
        vnfmReqDict['vnfd_version'] = req_dict['vnfd_version']

        if e2e_log:
            vnfmReqDict['tid']=e2e_log['tid']
            vnfmReqDict['tpath']=e2e_log['tpath']
        else:
            vnfmReqDict['tid']='test-tid'
            vnfmReqDict['tpath']='test-tpath'
        
        payload_req = json.dumps(vnfmReqDict)
        log.debug("[CHECK_VDU_STATUS] request body = %s" % str(payload_req))
        
        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, timeout=10, verify=False, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to check the status VNF VDU due to HTTP Error %s" %str(e))
            return -500, str(e)
        
        return self._parse_response(vnfm_response)


    def get_vnfm_version(self):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/version"

        try:
            vnfm_response = requests.get(URLrequest, headers=headers_req, verify=False, timeout=10, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to get vnfm version due to HTTP Error %s" %str(e))
            return -500, str(e)

        if vnfm_response.status_code == 200:
            version_res = vnfm_response.json()
            vers = version_res["version"].split(".")
            if int(vers[0]) >= 1:
                kind = "NEW"
            else:
                kind = "OLD"
            return 200, {"version":version_res["version"], "kind":kind}
        elif vnfm_response.status_code == 404:
            return 200, {"version":"NOTSUPPORTED", "kind":"OLD"}
        else:
            return -vnfm_response.status_code, "Invalid Response"


    def get_deployed_images(self):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/image"

        try:
            vnfm_response = requests.get(URLrequest, headers=headers_req, verify=False, timeout=10, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to test_vnf due to HTTP Error %s" %str(e))
            return -500, str(e)

        return self._parse_response(vnfm_response)


    def deploy_image(self, req_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/image"

        vnfmReqDict = {'name':req_dict['name'], 'location':req_dict['location']}
        vnfmReqDict['filesize'] = req_dict.get('filesize')
        vnfmReqDict['checksum'] = req_dict.get('checksum')
        vnfmReqDict['metadata'] = req_dict.get('metadata')

        if e2e_log:
            vnfmReqDict['tid'] = e2e_log['tid']
            vnfmReqDict['tpath'] = e2e_log['tpath']
        else:
            vnfmReqDict['tid']='test-tid'
            vnfmReqDict['tpath']='test-tpath'

        payload_req = json.dumps(vnfmReqDict)
        log.debug("[DEPLOY_IMAGE] request body = %s" % str(payload_req))

        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=60, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to test_vnf due to HTTP Error %s" %str(e))
            return -500, str(e)

        return self._parse_response(vnfm_response)


    def regist_vnfd_info(self, req_dict):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfd"

        vnfmReqDict = {'name':req_dict['name'], 'version':req_dict['version'], 'repo_filepath':req_dict['repo_filepath']}

        payload_req = json.dumps(vnfmReqDict)
        log.debug("[REGIST_VNFD_INFO] request body = %s" % str(payload_req))
        try:
            vnfm_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=10, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to regist_vnfd_info due to HTTP Error %s" %str(e))
            return -500, str(e)

        return self._parse_response(vnfm_response)


    ###################################### 2017-08-30 HJC ##############################################
    def get_default_ns_info(self, default_ns_id):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/ns/default/%s" %str(default_ns_id)
        log.debug("[GET_DEFAULT_NS_INFO] IN: %s" % URLrequest)
        try:
            vnfm_response = requests.get(URLrequest, headers = headers_req, verify=False, timeout=10, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to get default ns info from One-Box VNFM due to HTTP Error %s" %str(e))
            return -500, str(e)

        log.debug("[GET_DEFAULT_NS_INFO] response : %s" % vnfm_response)
        return self._parse_response(vnfm_response)
    ###################################### 2017-08-30 HJC ##############################################


    def get_vnf_version(self, req_dict, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.get_base_url() + "/vnfs/action"

        req_dict['action'] = 'GET_VERSION'

        if e2e_log:
            req_dict['tid'] = e2e_log['tid']
            req_dict['tpath'] = e2e_log['tpath']
        else:
            req_dict['tid']='test-tid'
            req_dict['tpath']='test-tpath'

        payload_req = json.dumps(req_dict)
        log.debug("[GET_VNF_VERSION] request body = %s" % str(payload_req))

        try:
            vnf_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False, timeout=10, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
        except Exception, e:
            log.exception("failed to get vnf version data due to HTTP Error %s" %str(e))
            return -500, str(e)

        log.debug("[GET_VNF_VERSION] vnf_response.status_code = %s " % vnf_response.status_code)

        if vnf_response.status_code == 200:
            version_res = vnf_response.json()
            log.debug("[GET_VNF_VERSION] version_res = %s " % version_res)
            return 200, {"status":"SUPPORTED", "vnf_sw_version":version_res["vnf_sw_version"], "vnf_image_version":version_res["vnf_image_version"]}
        elif vnf_response.status_code == 404:
            return 200, {"status":"NOTSUPPORTED_VNFM"}
        elif vnf_response.status_code == 501:
            return 200, {"status":"NOTSUPPORTED_VNF"}
        else:
            return -vnf_response.status_code, "Invalid Response"


    def _parse_json_response(self, vnfm_response):

        content = vnfm_response.json()
        log.debug("_parse_json_response() response body = %s" % str(content))
        if vnfm_response.status_code==200:
            result = 200
        else:
            result = -vnfm_response.status_code
            return result, content['error']['description']
        
        return result, content


    def _parse_response(self, vnfm_response):
        try:
            log.debug("__________ vnfm_response = %s" % vnfm_response)
            content = vnfm_response.json()
        except Exception, e:
            log.error("Exception: [%s] %s" %(str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'

        try:
            if vnfm_response.status_code == 200:
                return vnfm_response.status_code, content
            else:
                if 'error' in content:
                    return -vnfm_response.status_code, content['error']['description']
                else:
                    return -vnfm_response.status_code, "Invalid Response"
        except (KeyError, TypeError) as e:
            log.exception("_parse_response() exception while parsing response %s" %str(e))

        return -HTTP_Internal_Server_Error, "Unknown Error"

