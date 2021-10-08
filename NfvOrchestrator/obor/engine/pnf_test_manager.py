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
import db.orch_db_manager as orch_dbm
from db.orch_db import HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()
import time, datetime

from engine.vim_manager import get_vim_connector
import paramiko
from scp import SCPClient
import requests
from httplib import HTTPException
from requests.exceptions import ConnectionError
import sys

import threading

#from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict
global global_config

def new_pnf_test_server(mydb, server_info, filter_data=None):
    """
    :param filter_data: server_id(=onebox_id)
    """

    # 2. tb_server 기본정보 update
    result, data = orch_dbm.pnftest_get_server_id(mydb, filter_data, "tb_server")

    if result < 0:
        log.error("[BG] Get data failed : %d : %s" % ("tb_server", filter_data))
        return result, data
    elif result == 0:
        log.error("[BG] No result data : %d : %s" % ("tb_server", filter_data))
        return result, data

    server_info['servername'] = filter_data  # server_id
    server_info['serverseq'] = data['serverseq']

    # 2-1. update 항목 체크
    chk_result, chk_data = _chk_data(server_info, data, "tb_server")

    if chk_result < 0:
        log.debug("[BG] No update tb_server")
    else:
        # tb_server update
        dttm = 'modify_dttm'

        chk_data[dttm] = datetime.datetime.now()

        up_result, up_data = orch_dbm.update_server(mydb, chk_data)

        if up_result < 0:
            log.error("[BG] Update Failed.")
            return up_result, up_data

        # log.debug("[BG] tb_server update : %s" % up_data)

    # 3. hw 정보 업데이트 : tb_onebox_hw
    hw_result, hw_data = orch_dbm.pnftest_get_server_id(mydb, server_info['serverseq'], "tb_onebox_hw")

    if hw_result < 0:
        log.error("[BG] Get data failed : %d : %s" % ("tb_onebox_hw", server_info['serverseq']))
        return hw_result, hw_data
    elif hw_result == 0:
        log.error("[BG] No result data : %d : %s" % ("tb_onebox_hw", server_info['serverseq']))
        return hw_result, hw_data

    # 3-1. update 항목 체크
    chk_result, chk_data = _chk_data(server_info['hardware'], hw_data, "tb_onebox_hw")

    if chk_result < 0:
        log.debug("[BG] No update tb_onebox_hw")
    else:
        # tb_onebox_hw update
        up_result, up_data = orch_dbm.pnftest_update(mydb, server_info['serverseq'], chk_data, "tb_onebox_hw")

        if up_result < 0:
            log.error("[BG] Update Failed : tb_onebox_hw")
            return up_result, up_data

    # 4. sw 정보 업데이트 : tb_onebox_sw
    sw_result, sw_data = orch_dbm.pnftest_get_server_id(mydb, server_info['serverseq'], "tb_onebox_sw")

    if sw_result < 0:
        log.error("[BG] Get data failed : %d : %s" % ("tb_onebox_sw", server_info['serverseq']))
        return sw_result, sw_data
    elif sw_result == 0:
        log.error("[BG] No result data : %d : %s" % ("tb_onebox_sw", server_info['serverseq']))
        return sw_result, sw_data

    # 3-1. update 항목 체크
    chk_result, chk_data = _chk_data(server_info, sw_data, "tb_onebox_sw")

    log.debug("[BG] software => server_info : %s" %server_info)
    log.debug("[BG] software => chk_data : %s" % chk_data)

    """
    if chk_result < 0:
        log.debug("[BG] No update tb_onebox_sw")
    else:
        # tb_onebox_hw update
        up_result, up_data = orch_dbm.pnftest_update(mydb, server_info['serverseq'], chk_data, "tb_onebox_sw")

        if up_result < 0:
            log.error("[BG] Update Failed : tb_onebox_sw")
            return up_result, up_data
    """

    # 5. network 정보 업데이트 : tb_onebox_nw

    # 6. lan_office/lan_server 정보 업데이트 : tb_server_vnet

    # 7. vim 정보 업데이트: tb_vim, tb_vim_tenant

    # 8. wan 정보 업데이트 : tb_server_wan
    #   8.1. wan 갯수가 다를때 처리
    #     - NS가 설치된 경우 : 새로 들어온 정보에 맞춘다.
    #     - NS가 설치되지 않은 경우 : 기존에 있는 항목만 체크한다.

    # 9. extra_wan 정보 업데이트 : tb_server_wan

    # 10. 모니터링 처리
    #   10.1. server state 가 'NOTSTART' 인 경우
    #     10.1.1. One-Box 모니터링을 시작한다. : start_onebox_monitor
    #     10.1.2. 모니터링이 정상적으로 시작되면 server state를 'RUNNING'으로 변경
    #     10.2. One-Box 모니터링을 업데이트 해야하는 경우 : update_onebox_monitor  (server state 가 'NOTSTART'가 아닐때)
    #     10.2.1. mgmt ip 가 변경된 경우
    #     10.2.2. port 정보가 변경된 경우 (wan, office, server) : tb_onebox_nw 에서 비교
    #        예> eth1 : wan 이 었는데 eth1 : office 로 바뀐 경우

    # 11. Port IP 변경 사항 처리 : 변경된 것이 있으면 제어시스템에 업데이트
    #   11.1. wan_list
    #     11.1.1. 업데이트 대상 : DB, RLT
    #     11.1.2. 업데이트 항목 : parameters 내용, web_url, cp ip
    #   11.2. lan_office/lan_server IP
    #     11.2.1. 업데이트 대상 : DB, RLT
    #     11.2.2. 업데이트 항목 : parameters 내용, cp ip

    # 최종 처리 결과 리턴
    return 200, server_info.get("serverseq", "NONE")

def _chk_data(server_info, db_info, tbname='tb_server'):
    # 1. server_info와 db_info의 값을 비교하여 update할 컬럼 세팅
    # 1-1. server_info 와 db_info 의 값을 비교하기 위해 key를 맞춰준다
    update_dic = {}

    for k, v in db_info.items():
        if k == "serverseq" or k == "action" or k == "onebox_id" or k == "servername":
            continue

        if tbname == 'tb_server':
            if k == "vnfm_base_url":
                if server_info['vnfm']['base_url'] != v:
                    update_dic[k] = server_info['vnfm']['base_url']
            elif k == "obagent_base_url":
                if server_info['obagent']['base_url'] != v:
                    update_dic[k] = server_info['obagent']['base_url']
            elif k == "obagent_version":
                if server_info['obagent']['version'] != v:
                    update_dic[k] = server_info['obagent']['version']
            elif k == "publicmac":
                if server_info['wan']['mac'] != v:
                    update_dic[k] = server_info['wan']['mac']
        else:
            if server_info[k] != v:
                update_dic[k] = server_info[k]

    if len(update_dic) <= 0:
        return -1, "Not found update columns"
    else:
        return 1, update_dic



def nova_test(mydb, filter_data=None):
    result, data = orch_dbm.get_server_id(mydb, filter_data)

    # log.debug('data = %s' %str(data))

    # get wan list : server_wan > status = Active
    origin_ip = None
    result_wan, wan_list = orch_dbm.get_server_wan_list(mydb, data["serverseq"])
    if result_wan > 0:
        for w in wan_list:
            if w['status'] == "A":
                log.debug("Valid MAC Address because it mached with %s" % str(w))
                origin_ip = w.get('public_ip')
                break
    elif result_wan <= 0:
        log.debug("Failed to get WAN List for the One-Box: %s due to %d %s" % (data.get('onebox_id'), result_wan, str(wan_list)))

    # get nfr : nfseq
    nfr_result, nfr_data = orch_dbm.get_table_data(mydb, {'nsseq':data.get('nsseq')}, 'tb_nfr')

    # get vdu : uuid
    vdu_result, vdu_data = orch_dbm.get_table_data(mydb, {'nfseq':nfr_data.get('nfseq')}, 'tb_vdu')

    # log.debug('vdu_data = %s' %str(vdu_data))
    server_uuid = vdu_data.get('uuid')

    vim_result, vim_data = orch_dbm.get_vim_serverseq(mydb, data.get('serverseq'))

    # log.debug('vim_data = %s' %str(vim_data))

    result, vims = get_vim_connector(mydb, vim_data[0]['vimseq'])
    myvim = vims.values()[0]

    nova_result, nova_data = myvim.nova_test(server_uuid)

    log.debug('nova_data = %s' %str(nova_data))

    try:
        key_manager = AuthKeyDeployManager(mydb)
        key_manager.ssh_nova_tset(origin_ip, data.get('mgmtip'))
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    result, vims = get_vim_connector(mydb, vim_data[0]['vimseq'])
    myvim = vims.values()[0]

    nova_result, nova_data = myvim.nova_test(server_uuid)

    log.debug('nova_data = %s' %str(nova_data))

    return 200, "OK"



def status_check(mydb, filter_data=None):
    result, data = orch_dbm.get_server_id(mydb, filter_data)

    log.debug('data = %s' %str(data))

    ping_result, ping_data = _ping(data.get('mgmtip'))

    log.debug('ping_result = %d, ping_data = %s' %(ping_result, str(ping_data)))

    pyping_result, pyping_data = _pyping()
    log.debug('pyping_result = %d, pyping_data = %s' % (pyping_result, str(pyping_data)))

    return 200, "OK"


def _ping(Host):
    """
    Returns True if Host responds to a ping request
    """
    import subprocess, platform

    # log.debug('host = %s' %str(Host))
    Host = '211.224.204.209'
    log.debug('host = %s' %str(Host))

    # Ping parameters as function of OS
    ping_str = "-n 1" if  platform.system().lower()=="windows" else "-c 1"
    args = "ping " + " " + ping_str + " " + Host
    need_sh = False if  platform.system().lower()=="windows" else True

    # Ping
    return 200, subprocess.call(args, shell=need_sh) == 0

def _pyping():
    import pyping

    Host = '211.224.204.209'

    r = pyping.ping(Host)

    return 200, r.ret_code


def odroid_reset(mydb, filter_data=None):

    result, data = orch_dbm.get_server_id(mydb, filter_data)

    log.debug('[odroid_set] data = %s' %str(data))

    if result < 0:
        log.error("failed to get One-Box Info from DB: %d %s" % (result, data))
        ret_result = -HTTP_Internal_Server_Error
    elif result == 0:
        pass
    else:
        onebox_id = data.get('onebox_id')

    reset_dict = {}
    reset_dict['onebox_id'] = onebox_id
    reset_dict['serverseq'] = data.get('serverseq')
    reset_dict['nsseq'] = data.get('nsseq')
    update_result, update_data = orch_dbm.odroid_reset(mydb, reset_dict)

    log.debug('update_result = %d, update_data = %s' % (update_result, str(update_data)))

    return 200, "OK"


def odroid_set(mydb, filter_data=None):
    ret_msg = None
    onebox_id = None

    result, data = orch_dbm.get_server_id(mydb, filter_data)

    log.debug('[odroid_set] data = %s' %str(data))

    if result < 0:
        log.error("failed to get One-Box Info from DB: %d %s" % (result, data))
        ret_result = -HTTP_Internal_Server_Error
        ret_msg += "\n DB Error로 One-Box 정보 검증이 실패하였습니다."
    elif result == 0:
        pass
    else:
        onebox_id = data.get('onebox_id')

    try:
        # install : http://175.213.170.65:5553/install
        # check : http://175.213.170.65:5553/check

        request_data = {}
        request_data['set_url'] = 'http://%s:5553/install' %str(data.get('mgmtip'))
        request_data['status_url'] = 'http://%s:5553/check' %str(data.get('mgmtip'))

        log.debug('[odroid_set] request_data = %s' %str(request_data))

        th = threading.Thread(target=_odroid_set_thread, args=(mydb, data, request_data))
        th.start()

        return_data = {"result": "OK", "status": "DOING"}
    except Exception, e:
        # log.warning("Exception: %s" % str(e))

        return -HTTP_Internal_Server_Error, "Odroid 설치가 실패하였습니다. 원인: %s" % str(e)

    return 200, return_data

def _odroid_set_thread(mydb, ob_data, request_data):
    # 설치 요청

    log.debug('[_odroid_set_thread] 설치 시작........')

    odr_result, odr_data = _request_odroid(request_data.get('set_url'))

    log.debug('odr_result = %d, odr_data = %s' %(odr_result, str(odr_data)))

    if odr_result < 0:
        return odr_result, odr_data
    else:
        # 설치 요청이 끝나고, 상태체크
        action = "restore"
        trial_no = 1
        pre_status = "UNKNOWN"

        log.debug("[_odroid_set_thread - %s] Wait for restore One-Box by Agent" %(ob_data['onebox_id']))
        time.sleep(10)

        while trial_no < 10:
            log.debug("[_odroid_set_thread - %s] Checking the progress of restore (%d):" % (ob_data.get('onebox_id'), trial_no))

            check_status_url = ""

            result, check_status = _request_odroid(request_data.get('status_url'))

            # log.debug('check_data = %s' %str(type(check_status)))

            if check_status[1].get('status') != "DOING":
                log.debug("Completed to setting Odroid by Agent")
                break
            else:
                log.debug("Setting in Progress")

            trial_no += 1
            time.sleep(10)

        # db update
        update_dict = {}
        update_dict['onebox_id'] = ob_data.get('onebox_id')
        update_dict['serverseq'] = ob_data.get('serverseq')
        update_dict['nsseq'] = ob_data.get('nsseq')
        update_dict['action'] = 'RUNNING'
        update_dict['status'] = 'N__IN_SERVICE'
        update_dict['ns_name'] = 'KT-Ubuntu'

        update_result, update_data = orch_dbm.odroid_update(mydb, update_dict)

        log.debug('update_result = %d, update_data = %s' %(update_result, str(update_data)))

    return 200, "OK"

# request : set
def _request_odroid(url=None):
    try:
        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}

        ob_response = requests.post(url, headers = headers_req, timeout=120, verify=False)
    except (HTTPException, ConnectionError), e:
        log.exception("failed to install Odroid due to HTTP Error %s" % str(e))
        return -500, str(e)
    except Exception, e:
        log.error("Failed to install One-Box : %s" % str(e))
        return -500, str(e)

    return 200, _parse_json_response(ob_response)

def _parse_json_response(ob_response):
    try:
        # log.debug('Response headers = %s' %str(ob_response.headers))
        # log.debug('Response headers = %s' %str(ob_response.encoding))
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
        return result, content['error']['description']

    return result, content


class AuthKeyDeployManager(object):

    def __init__(self, mydb):
        self.mydb = mydb
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.load_system_host_keys()

        # nova endpoint url update 변수
        self.sc_path="/var/onebox/tmp"
        self.sc_fn="endpoint.sh"

    def __del__(self):
        if self.ssh is not None:
            # self.ssh.close()
            self.ssh = None


    def scp_nova_test(self, publickey_path):
        scp = None
        try:
            # 파일 전송
            scp = SCPClient(self.ssh.get_transport())
            scp.put(publickey_path, "/var/onebox/tmp/")
        except Exception, e:
            log.error(str(e))
            raise Exception("authorized_keys 생성실패 : %s" % str(e))
        finally:
            if scp is not None:
                scp.close()

    def ssh_nova_tset(self, origin_ip, mgmt_ip):

        try:
            self.ssh.connect(mgmt_ip, port=9922, timeout=5)
        except Exception, e:
            raise Exception("One-Box SSH접속 실패 : %s" % str(e))

        # mysql update(keystone.endpoint) : nova endpoint url update
        try:
            # 1. update 할 스크립트 배포
            self.scp_nova_test("/var/onebox/novaurl_update/endpoint.sh")

            ssh_cmd = "ls -a %s | grep -wc %s" %(str(self.sc_path), str(self.sc_fn))
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)

            if output[0].find("1") >= 0:
                # 권한 설정
                ssh_cmd = "chmod 700 %s/%s" %(str(self.sc_path), str(self.sc_fn))
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)

                # script 실행
                ssh_cmd = "sh %s/%s %s %s" % (str(self.sc_path), str(self.sc_fn), str(origin_ip), str(mgmt_ip))
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)

                # script 파일 삭제
                ssh_cmd = "rm -f %s/%s" %(str(self.sc_path), str(self.sc_fn))
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)

        except Exception, e:
            log.error("Failed to update nova endpoint url in the One-Box : %s" % str(e))
            raise Exception(str(e))

        finally:
            if self.ssh is not None:
                self.ssh.close()

