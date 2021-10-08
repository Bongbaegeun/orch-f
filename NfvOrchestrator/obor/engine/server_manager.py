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
import sys
import uuid as myUuid
import time, datetime
import threading
import netaddr
import requests
import paramiko

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict
import db.orch_db_manager as orch_dbm

from connectors import monitorconnector
from connectors import obconnector
from connectors import vnfmconnector
from connectors import accountconnector
from connectors.haconnector import ssh_connector

import orch_core as nfvo

from engine.server_status import SRVStatus
from engine.action_status import ACTStatus
from engine.nsr_status import NSRStatus
from engine.action_type import ActionType

from engine.vim_manager import get_vim_connector, vim_action
from engine.nsr_manager import handle_default_nsr

from utils.e2e_logger import e2elogger, CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()
import common_manager

global global_config

####################################################    for KT One-Box Service   #############################################

def new_onebox_flavor(mydb, flavor_info, filter_data=None):
    log.debug("IN")
    log.debug("new_onebox_flavor: %s" %str(flavor_info))

    result, flavor_id = orch_dbm.insert_onebox_flavor(mydb, flavor_info)
    if result < 0:
        log.error("failed to insert an One-Box flavor: %d %s" %(result, flavor_id))

    return result, flavor_id

def get_onebox_flavor_list(mydb):
    try:
        result, content = orch_dbm.get_onebox_flavor_list(mydb)

        if result < 0:
            log.error("Failed to get One-Box flavor List: %d, %s" %(result, content))
            return result, content
        elif result == 0:
            return -HTTP_Not_Found, "No One-Box flavor Found"

        return result, content

    except Exception, e:
        log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
        return -HTTP_Internal_Server_Error, "One-Box 버전 종류를 가지고 오는데 실패하였습니다."

def get_onebox_flavor_id(mydb, flavor_id):
    result, data = orch_dbm.get_onebox_flavor_id(mydb, flavor_id)

    if result < 0:
        log.error("Failed to get One-Box flavor: %d, %s" %(result, data))
    elif result == 0:
        return -HTTP_Not_Found, "The One-Box flavor Not Found"

    return result, data

def delete_onebox_flavor_id(mydb, flavor_id):
    result, data = get_onebox_flavor_id(mydb, flavor_id)
    if result < 0:
        log.error("failed to delete the One-Box flavor: %d %s" %(result, data))
        return result, data

    # 추가(2019.03.25) : 해당 버전을 사용중인 원박스가 있다면 삭제 불가
    chk_result, chk_data = orch_dbm.get_onebox_hw_model(mydb, data['hw_model'])
    log.debug('delete_onebox_flavor_id : chk_result = %d, chk_data = %s' %(chk_result, str(chk_data)))
    if chk_result >= 1:
        return -406, "%s 모델을 사용중인 원박스가 존재하여 삭제가 불가능 합니다." % str(data['hw_model'])

    result, flavor_id = orch_dbm.delete_onebox_flavor_id(mydb, data['seq'])
    if result < 0:
        log.error("failed to delete the DB record: %s" %flavor_id)
        return result, flavor_id

    return 200, data['seq']

# def _generate_server_name(mydb, customerename, customer_id):
#     filter_dict = {'customerseq': customer_id}
#
#     result, data = orch_dbm.get_server_filters(mydb, filter_dict)
#     if result < 0:
#         return result, data
#
#     ob_index = result + 1
#     server_name = str(customerename)+".OB"+str(ob_index)
#
#     return 200, server_name


def new_server(mydb, server_info, filter_data=None, use_thread=True, forced=False, is_wad=False, managers=None):
    """
    OneBox Agent / Onebox 복구 / reset_mac - 서버정보 업데이트 처리.
    :param server_info: request body정보
    :param filter_data: server_id(=onebox_id)
    :param use_thread: restore_onebox처리시 False
    :param forced: restore_onebox처리시 True
    :param is_wad: nic_modify 함수에서 호출한 경우 True:WAN Port 관련 부분은 nic_modify에서 처리하도록 new_server 에서는 제외하고 처리한다.(WAN Add or Delete)
    :param managers: wfm/sbpm plugin 정보(2019.08.09 - 현재 redis plugin 만 사용)
    :return: serverseq
    """

    old_info = {}
    # log.debug("[TEMP-HJC **********] server_info = %s" %str(server_info))
    # check if already reqistered server or not
    check_result, check_data = _check_existing_servers(mydb, server_info, filter_data)

    if check_result < 0:
        log.error("new_server() failed to check the registered servers %d %s" % (check_result, check_data))
        return check_result, check_data
    elif check_result == 0:
        return -HTTP_Bad_Request, "No Server : %s" % str(filter_data)
    elif check_result > 1:
        log.error("new_server() there are two or more servers.")
        return -HTTP_Bad_Request, "Cannot Identify Server : %s" % str(filter_data)
    elif check_result == 1:

        # redis 에 noti 데이터 저장
        if managers:
            redis_key = check_data[0]['onebox_id']
            redis_data = server_info
            redis_msg = "Redis save server data"

            # log.debug('redis_data = %s' %str(redis_data))

            wf_redis = managers.get('wf_redis')
            res, cont = wf_redis.redis_set(redis_key, redis_data, redis_msg)

        server_info['serverseq']=check_data[0]['serverseq']
        server_info['status']=check_data[0]['status']
        server_info['state']=check_data[0]['state'] # monitor state
        server_info['customerseq']=check_data[0]['customerseq']
        server_info['org_name']=check_data[0]['orgnamescode']
        server_info['onebox_id']=check_data[0]['onebox_id']
        server_info['serveruuid']=check_data[0]['serveruuid']
        server_info['action']=check_data[0]['action']

        # # Arm-Box 구분하기 위해 추가 : ex) nfsubcategory = OneBox or KtPnf or KtArm
        # server_info['nfsubcategory']=check_data[0]['nfsubcategory']

        # 복구중일때 agent call은 생략한다. (action = RS & forced = False)
        # action = RS & forced = True 인 경우는 복구 프로세스에서 강제 호출한 경우 : 생락안함.
        # if server_info['action'] == "RS" and forced is False:
        #     log.info("Pass processes by this API this time because The One-Box is restoring.")
        #     return 200, server_info['serverseq']

        if 'mgmt_ip' not in server_info and check_data[0].get('mgmtip') is not None:
            server_info['mgmt_ip'] = check_data[0]['mgmtip']

        server_info['nsseq']=check_data[0]['nsseq']
        server_info['onebox_flavor'] = check_data[0]['onebox_flavor']

        old_info = {"mgmt_ip": check_data[0]['mgmtip'], "public_ip": check_data[0]['publicip']
                  , "public_mac": check_data[0]['publicmac'], "ipalloc_mode_public": check_data[0]['ipalloc_mode_public']}

        if check_data[0].get('publicgwip') is not None:
            old_info['publicgwip'] = check_data[0].get('publicgwip')
        if check_data[0].get('publiccidr') is not None:
            old_info['publiccidr'] = check_data[0].get('publiccidr')

        # 회선이중화 : 기존 wan list가 존재하는 경우
        if check_data[0].get('wan_list') is not None:
            old_info['wan_list'] = check_data[0].get('wan_list')
        if check_data[0].get('extra_wan_list') is not None:
            old_info['extra_wan_list'] = check_data[0].get('extra_wan_list')

        log.debug("===== OBA Call ===== [%s] DB Info : %s" % (server_info['onebox_id'],str(old_info)))

    try:
        # # Arm-Box 분기처리
        # if server_info.get('nfsubcategory') == "KtArm":
        #     th = threading.Thread(target=_new_server_thread_armbox, args=(mydb, server_info, old_info, forced, is_wad))
        #     th.start()
        # else:
        #     if use_thread:
        #         th = threading.Thread(target=_new_server_thread, args=(mydb, server_info, old_info, forced, is_wad))
        #         th.start()
        #     else:
        #         return _new_server_thread(mydb, server_info, old_info, forced, is_wad)

        if use_thread:
            th = threading.Thread(target=_new_server_thread, args=(mydb, server_info, old_info, forced, is_wad))
            th.start()
        else:
            return _new_server_thread(mydb, server_info, old_info, forced, is_wad)
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "One-Box 서버 등록이 실패하였습니다. 원인: %s" %str(e)

    return 200, server_info.get("serverseq", "NONE")


def _new_server_thread(mydb, server_info, old_info, forced=False, is_wad=False):
    log.debug('[VNF : %s] _new_server_thread START!!!' %str(server_info.get('onebox_id')))

    if 'serverseq' in server_info:

        # Step 1. Parsing Input Data
        server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict = _parse_server_info(mydb, server_info)

        # Step 2. Check Valid of the input info.
        check_result, check_data = _check_server_validation(mydb, server_dict, hardware_dict, network_list, software_dict, mac_check = not forced)

        if check_result < 0:
            log.warning("Invalid One-Box Info: %s" %str(check_data))
            ob_status = server_info['status']
            if server_info['status'].find("I__") >= 0 or server_info['status'].find("E__") >= 0:
                if not forced and server_info["action"] == "RS":
                    pass
                else:
                    ob_status = SRVStatus.ERR

            server_dict = {'serverseq': server_info['serverseq'], 'onebox_id': server_info['onebox_id'], 'status': ob_status, 'description': str(check_data)}

            result, data = orch_dbm.update_server(mydb, server_dict)
            if result < 0:
                log.error("new_server() failed to DB Update for Server")
                return result, data
            log.debug("Invalid Server Info. update just status and description of server:%s" % server_dict)
            return 200, str(check_data)

        else:
            server_dict['description'] = check_data

        # Step 3. Update DB Data for the One-Box

        # 3.0. 초기상태에 따라 뒷단 프로세스 수행 여부 결정
        is_monitor_process = False
        is_change_process = False
        # "I__LINE_WAIT" : 변경점 없고 모니터링은 수행
        if server_info["status"] == SRVStatus.LWT: # server_info["status"] 는 조정되지 않은 원래 상태값.
            is_monitor_process = True
            is_change_process = False
        elif server_dict['status'].find("N__") >= 0 or server_dict['status'].find("E__") >= 0:
            is_monitor_process = True
            is_change_process = True
        elif is_wad:    # WAN 추가/삭제 프로세스.
            is_monitor_process = True
            is_change_process = True

        # 3.1. 서버정보 업데이트 : status 는 제외

        # update_server 전에 처리
        # update_server 에서 tb_onebox_nw 데이타 삭제하기 전에 기존 데이타 따로 담아놓는다. > port 변경사항 체크해서 모니터 업데이트 처리 필요
        result, nw_list_old = orch_dbm.get_onebox_nw_serverseq(mydb, server_dict["serverseq"])
        if result < 0:
            log.error("Failed to get onebox network info.")
            return result, nw_list_old

        # 설변체크 ########################################
        # #### One-Box 복구 동작중일때는 생략한다.
        chg_port_result, chg_port_dict = 0, None
        if server_info["action"] == "RS":
            is_change_process = False
            pass
        else:

            chg_port_result, chg_port_dict = common_manager.check_chg_port(mydb, server_dict["serverseq"], nw_list_old, network_list)

            is_config_changed = False   # 설변에 관련된 사항이 있는지 체크하는 flag --> 설변이면 backup_history ood_flag를 True로 처리해야한다.
            # 설변체크 1. wan/office/server 변경체크
            if chg_port_result > 0:
                is_config_changed = True

            # 설변체크 2. vnet ip 변경 체크
            if vnet_dict and not is_config_changed:
                result, vnet_old = orch_dbm.get_server_vnet(mydb, server_dict["serverseq"])
                if result <= 0:
                    log.warning("Failed to get vnet info.")
                else:
                    if vnet_dict.get("vnet_office_ip", "") != vnet_old.get("vnet_office_ip", ""):
                        is_config_changed = True
                    if vnet_dict.get("vnet_server_ip", "") != vnet_old.get("vnet_server_ip", ""):
                        is_config_changed = True

                    # HA 구성일 경우
                    # if vnet_dict.get("vnet_ha_ip", "") != vnet_old.get("vnet_ha_ip", ""):
                    #     is_config_changed = True

            # 설변체크 3. wan이 STATIC인데 IP가 변경된 경우
            old_wan_list = old_info.get("wan_list", None)
            new_wan_list = server_dict.get("wan_list", None)
            if new_wan_list and old_wan_list and not is_config_changed:
                for new_wan in new_wan_list:
                    if new_wan.get('ipalloc_mode_public') == "STATIC":
                        for old_wan in old_wan_list:
                            if old_wan["nic"] == new_wan.get('nic'):
                                if old_wan["public_ip"] != new_wan.get('public_ip'):
                                    is_config_changed = True
                                break

                # 설변체크 4. wan의 ipalloc_mode_public 가 변경된 경우
                for new_wan in new_wan_list:
                    for old_wan in old_wan_list:
                        if new_wan.get('nic') == old_wan["nic"]:
                            if new_wan.get('ipalloc_mode_public') != old_wan["ipalloc_mode_public"]:
                                is_config_changed = True
                            break

            if is_config_changed:
                # 기존 백업정보 OOD 변경
                result, content = orch_dbm.update_backup_history(mydb, {"ood_flag":"TRUE"}, {"serverseq":server_info['serverseq']})

            # 설변체크 END ########################################

        # server의 status 가 변경되지 않도록 status 항목을 제거한다.
        status_bak = server_dict['status']
        del server_dict['status']

        ############ WAN Update시 처리 관련 항목 정리 [update_server] ###################
        # NS 설치여부 필요 (nsseq 있으면 설치된 것으로 함.)
        if server_info["nsseq"] is not None:
            server_dict["nsseq"] = server_info["nsseq"]
        # WAN 추가/삭제 동작중에는 wan_list 저장 안함.
        server_dict["is_wad"] = is_wad
        ############ WAN Update시 처리 관련 항목 정리 END ###################

        result, data = orch_dbm.update_server_oba(mydb, server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict)
        if result < 0:
            log.error("new_server() failed to DB Update for Server")
            return result, data
        # log.debug("********* HJC: result of update server: %d, %s" %(result, str(data)))
        # status 복구
        server_dict['status'] = status_bak
        # if "nsseq" in server_dict:
        #     del server_dict["nsseq"]

        # 3.2. 서버 status 정리 및 update

        # server 또는 NSR 이 action 중 일때는 update_server_status 함수를 호출하지 않는다.
        is_update_server_status = False
        nsr_data = None

        # 1. check server action
        server_action = server_info.get("action", None)
        if server_action is None or len(server_action) == 0 or server_action.endswith("E"):

            if server_info['nsseq'] is not None:
                nsr_result, nsr_data = orch_dbm.get_nsr_general_info(mydb, server_info['nsseq'])
                if nsr_result < 0:
                    log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
                    return -HTTP_Internal_Server_Error, nsr_data

                nsr_action = nsr_data["action"]
                if nsr_action is None or len(nsr_action) == 0 or nsr_action.endswith("E"):
                    is_update_server_status = True
                else:   # NSR이 동작중
                    is_update_server_status = False
                    log.debug("__________ DO NOT update server status. The action of NSR is %s" % nsr_action)
            else:
                is_update_server_status = True

        else:   # server가 동작중
            is_update_server_status = False
            log.debug("__________ DO NOT update server status. The action of Server is %s " % server_action)

        is_handle_default_nsr = False
        if is_update_server_status:
            if server_dict["status"] == SRVStatus.RDS or server_dict["status"] == SRVStatus.LWT or server_dict["status"] == SRVStatus.LPV:
                if "default_ns_id" in server_info and server_info["default_ns_id"] == "RESERVED":
                    server_dict["status"] = SRVStatus.LPV
                elif "default_ns_id" in server_info and server_info["default_ns_id"] == "ERROR":
                    server_dict["status"] = SRVStatus.RDS
                elif "default_ns_id" in server_info and af.check_valid_uuid(server_info["default_ns_id"]):
                    # update_server 후에 handle_default_nsr 처리하고 상태값을 최종 변경한다. 설치완료 전까지는 "N__LOCAL_PROVISIONING" 상태로 변경해놓는다.
                    log.debug("__________ default_ns_id : %s, status : %s --> %s" % (server_info["default_ns_id"], server_dict["status"], SRVStatus.LPV))
                    server_dict["status"] = SRVStatus.LPV
                    is_handle_default_nsr = True
                    if nsr_data is not None: # 이런 경우는 사실 없어야 한다. --> NSR이 존재한다면 서버 status가 INS/ERR 중 하나가 되어서 이부분 로직을 타지 않아야한다.
                        is_handle_default_nsr = False
                        log.warning("__________ 서버 상태가 정상적인지 확인 필요... server_info:%s, server_dict:%s, nsr:%s " % (server_info["status"], server_dict["status"], nsr_data["status"]))
            if server_info["status"] != server_dict["status"]:
                common_manager.update_server_status(mydb, server_dict, e2e_log = None)
                log.debug("__________ The actions of Server and NSR are NORMAL. Update server status : %s" % server_dict["status"])

        # note 처리
        try:
            if "note" in server_dict:
                log.debug("********* HJC: start pasring note")
                result, memo_r = orch_dbm.get_memo_info(mydb, {'serverseq': server_dict['serverseq']})
                if result < 0:
                    log.error("Failed to get memo : serverseq = %s" % server_dict['serverseq'])
                    return result, memo_r
                elif result == 0:
                    memo_dict = {"serverseq":server_dict['serverseq']}
                    memo_dict["contents"] = server_dict["note"]
                    result, memoseq = orch_dbm.insert_memo(mydb, memo_dict)
                    if result < 0:
                        log.error("Failed to insert memo : serverseq = %s" % server_dict['serverseq'])
                        return result, memoseq
                else:
                    contents = memo_r[0]["contents"]
                    contents += server_dict["note"]
                    memo_r[0]["contents"] = contents
                    result, update_msg = orch_dbm.update_memo(mydb, memo_r[0])
                    if result < 0:
                        log.error("Failed to update memo : memoseq = %s" % memo_r[0]['memoseq'])
                        return result, update_msg
                log.debug("********* HJC: end pasring note")
        except Exception, e:
            log.exception("for Note, Exception: %s" %str(e))

    else:
        # Create Case: Not supported for One-Box Service
        log.error("Not found One-Box Info registered to Orchestrator")
        return -HTTP_Bad_Request, "Not found One-Box Info registered to Orchestrator"

    if is_monitor_process:
        try:
            # Step 4. 모니터링 처리 및 vim,image 현행화
            if server_dict.get('mgmtip') is not None:

                update_body_dict = {}

                if server_dict.get('state', "NOTSTART") == "NOTSTART":
                    log.debug("Starts monitor One-Box[%s]" %server_dict['onebox_id'])

                    monitor_result, monitor_data = start_onebox_monitor(mydb, server_dict['serverseq'])
                    if monitor_result >= 0:
                        us_result, us_data = orch_dbm.update_server(mydb, {'serverseq':server_dict['serverseq'], 'state':"RUNNING"})
                    else:
                        # defalut_ns 설치케이스인 경우 One-Box 모니터링이 실패했으면 어차피 실패되므로 설치 생략.
                        if is_handle_default_nsr:
                            is_handle_default_nsr = False
                            log.warning("__________ Skip install Default NS for the Failure of One-Box monitoring start.")
                else:
                    if old_info.get("mgmt_ip") != server_dict.get('mgmtip'):
                        log.debug("DO update_onebox_monitor() - One-Box MGMT IP Addresses are changed: \n  - One-Box ID: %s\n  - Old MGMT IP:%s\n  - New MGMT IP:%s"
                                  % (server_dict['onebox_id'], str(old_info.get('mgmt_ip')), str(server_dict.get('mgmtip'))))

                        update_body_dict['server_id'] = server_dict['serverseq']
                        update_body_dict['server_ip'] = server_dict['mgmtip']

                    # 기존 데이타와 현재 데이타가 변경된 부분이 있는지 체크한다.
                    if chg_port_result > 0:
                        log.debug("__________ 변경된 Port 정보 : %s" % chg_port_dict)
                        update_body_dict["change_info"] = chg_port_dict["change_info"]

                    # mgmt_ip가 변경되었거나, vPort 가 변경되었을때 One-Box monitoring을 update 해준다.
                    if update_body_dict:
                        log.debug("__________ 모니터링 업데이트 처리 : update_body_dict = %s" % update_body_dict)
                        monitor_result, monitor_data = update_onebox_monitor(mydb, update_body_dict)

                if old_info.get("mgmt_ip") != server_dict.get('mgmtip'):
                    _new_server_update_vim(mydb, server_dict)
                    common_manager.sync_image_for_server(mydb, server_dict['serverseq'])

            # default_ns 설치 처리.
            if is_handle_default_nsr:

                result, server_db = orch_dbm.get_server_id(mydb, server_dict['serverseq'])
                if server_db["status"] != server_dict["status"]:
                    # 이 경우 다른 프로세스(아마도 다른 타이밍의 new_server호출)에 의해서 서버의 상태값이 바뀐 경우이다. 다른 프로세스에 맡기고 모든 처리를 중단한다.
                    log.warning("DEFAULT NS 설치 생략 : Changed the server status : [%s] %s ==> %s" %(server_dict['serverseq'], server_dict["status"], server_db["status"]))
                    return 200, "OK"

                result, content = handle_default_nsr(mydb, customer_id=server_dict["customerseq"], onebox_id=server_dict['servername']
                                                     , default_ns_id=server_info["default_ns_id"], server_dict=server_dict, tid=None, tpath="")
                if result < 0:
                    if result == -404:
                        # One-Box에 VM이 삭제되서 vnfm이 default NS 정보를 넘겨줄 수 없는 경우. --> 제어시스템에서 설치할 수 있도록 "N__READY_SERVICE" 상태로...
                        server_dict["status"] = SRVStatus.RDS
                    else:
                        # vnfm에서 default NS를 설치중이어서 정보를 줄수 없거나, 에러가 난 경우. --> 다시 시도할 수 있도록 "N__LOCAL_PROVISIONING" 상태로...
                        server_dict["status"] = SRVStatus.LPV
                else:
                    server_dict["status"] = SRVStatus.INS
                # default ns 작업 후 상태를 다시 업데이트한다.
                common_manager.update_server_status(mydb, server_dict, e2e_log = None)

            # Step 5. 변경사항 처리
            if is_change_process:

                # NSR이 없거나, NSR이 존재하고 NSR 상태가 정상일때 wan 변경사항 처리.
                is_check = False

                lan_office = None
                lan_server = None
                if server_info.get("nsseq", None):
                    nsr_result, nsr_data = orch_dbm.get_nsr_general_info(mydb, server_info['nsseq'])
                    if nsr_result < 0:
                        log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
                        return -HTTP_Internal_Server_Error, nsr_data
                    elif nsr_result > 0:
                        if nsr_data['status'].find("N__") >= 0 or nsr_data['status'].find("E__") >= 0:
                            is_check = True
                            # office IP 변경여부 체크
                            if vnet_dict:
                                lan_office, lan_server = common_manager.check_chg_lan_info(mydb, server_info["nsseq"], vnet_dict)
                else:
                    is_check = True

                chg_port_info = {}
                chg_wan_info = None
                chg_extra_wan_info = None

                if is_check:

                    if not is_wad:  # wan add/delete 작업 중이면 wan 변경사항 체크 생략
                        chg_wan_info = common_manager.check_chg_wan_info(mydb, server_dict['serverseq']
                                                                         , old_info.get("wan_list", None), server_dict.get("wan_list", None)
                                                                         , is_wan_count_changed=server_dict.get("is_wan_count_changed"))
                    # extra_wan_list 의 변경체크
                    if server_dict.get("extra_wan_list", None):
                        chg_extra_wan_info = common_manager.check_chg_extra_wan_info(mydb, server_dict['serverseq']
                                                                         , old_info.get("extra_wan_list", None), server_dict.get("extra_wan_list", None)
                                                                         , is_wan_count_changed=server_dict.get("is_extra_wan_count_changed"))
                    if chg_wan_info and chg_wan_info.get("parm_count", 0) > 0:
                        chg_port_info["wan"] = chg_wan_info
                    if chg_extra_wan_info and chg_extra_wan_info.get("parm_count", 0) > 0:
                        chg_port_info["extra_wan"] = chg_extra_wan_info

                    if lan_office:
                        chg_port_info["lan_office"] = lan_office
                        log.debug("__________ 변경된 LAN OFFICE IP 정보 : %s" % lan_office)
                    if lan_server:
                        chg_port_info["lan_server"] = lan_server
                        log.debug("__________ 변경된 LAN SERVER IP 정보 : %s" % lan_server)

                publicip_update_dict = {}

                if (server_dict.get('publicip') is not None and old_info.get("public_ip") is not None) and (old_info.get("public_ip") != server_dict.get('publicip')):
                    publicip_update_dict['publicip'] = server_dict['publicip']
                    # publicip_update_dict['old_publicip'] = old_info.get("public_ip")
                    publicip_update_dict['publiccidr_cur'] = server_dict['publiccidr']

                    log.debug("One-Box Public IP Addresses are changed:\n  - One-Box ID: %s\n  - %s" %(server_dict['onebox_id'], str(publicip_update_dict)))

                if (server_dict.get('publicmac') is not None and old_info.get('public_mac') is not None) and (old_info.get('public_mac') != server_dict.get('publicmac')):
                    publicip_update_dict['publicmac'] = server_dict['publicmac']
                    publicip_update_dict['old_publicmac'] = old_info.get("public_mac")
                    log.debug("One-Box Public MAC Addresses are changed:\n  - One-Box ID: %s\n  - %s" %(server_dict['onebox_id'], str(publicip_update_dict)))

                if (server_dict.get('ipalloc_mode_public') is not None and old_info.get('ipalloc_mode_public') is not None) and (old_info.get('ipalloc_mode_public') != server_dict.get('ipalloc_mode_public')):
                    publicip_update_dict['ipalloc_mode_public'] = server_dict['ipalloc_mode_public']
                    publicip_update_dict['old_ipalloc_mode_public'] = old_info.get("ipalloc_mode_public")
                    log.debug("One-Box Public IP Allocation Mode is changed:\n  - One-Box ID: %s\n  - %s" %(server_dict['onebox_id'], str(publicip_update_dict)))

                if (server_dict.get('publicgwip') is not None and old_info.get('publicgwip') is not None) and (old_info.get('publicgwip') != server_dict.get('publicgwip')):
                    publicip_update_dict['publicgwip'] = server_dict['publicgwip']
                    publicip_update_dict['old_publicgwip'] = old_info.get("publicgwip")
                    log.debug("One-Box Public GW IP is changed:\n  - One-Box ID: %s\n  - %s" %(server_dict['onebox_id'], str(publicip_update_dict)))

                if (server_dict.get('publiccidr') is not None and old_info.get('publiccidr') is not None) and (old_info.get('publiccidr') != server_dict.get('publiccidr')):
                    publicip_update_dict['publiccidr'] = server_dict['publiccidr']
                    publicip_update_dict['old_publiccidr'] = old_info.get("publiccidr")
                    log.debug("One-Box Public IP CIDR is changed:\n  - One-Box ID: %s\n  - %s" %(server_dict['onebox_id'], str(publicip_update_dict)))

                # BEGIN : publicip 변경에 대한 예외사항 처리
                # 일부 프로세스(복구, 프로비젼 등) 진행중 public_ip가 변경되어 이벤트를 받은 경우,
                # tb_server만 변경되어 '뒷단의 일부 변경처리[wan_list변경 -> parameters/cp/web_url]' 작업이 빠질수 있다.
                # wan_list에서 public_ip에 해당하는 wan의 ip가 변경되었고 tb_server의 publicip는 이미 변경되어 변경사항을 모를 경우,
                # publicip_update_dict 의 publicip가 변경된 것으로 값을 전달해서 문제가 없도록 처리한다.
                if chg_wan_info and chg_wan_info.get("public_ip") and "publicip" not in publicip_update_dict:

                    public_wan = None
                    for wan in server_dict["wan_list"]:
                        if wan["status"] == "A":
                            public_wan = wan
                            break
                    # 변경된 public_ip가 있고 해당 wan이 public wan 인 경우
                    if public_wan and chg_wan_info["public_ip"].has_key(public_wan["name"]):
                        publicip_update_dict['publicip'] = public_wan['public_ip']
                        # publicip_update_dict['publiccidr_cur'] = public_wan['public_cidr_prefix']
                # END : publicip 변경에 대한 예외사항 처리

                update_info = {}
                if publicip_update_dict or chg_port_info:

                    if publicip_update_dict:
                        update_info["publicip_update_dict"] = publicip_update_dict
                    if chg_port_info:
                        update_info["chg_port_info"] = chg_port_info
                    if server_dict.get("wan_list", None):
                        update_info["is_wan_list"] = True

                    # 1. Update NSR Info with new Public IP
                    if server_info['nsseq'] is not None:
                        nsr_update_result, nsr_update_content = common_manager.update_nsr_by_obagent(mydb, server_info['nsseq'], update_info, use_thread=False)


                # BEGIN : 사용안함 # 일단 False처리한다.
                if False and "publicip_update_dict" in update_info:

                    # log.debug("__________ Backup Start : publicip_update_dict = %s " % publicip_update_dict)

                    # 2. Disable Backup Data with old settings
                    log.debug("[****HJC******] Out-Of-Date One-Box Backup Data")
                    need_nsbackup = False

                    bd_update_condition = {'serverseq': server_dict['serverseq']}

                    if 'publicip' in publicip_update_dict or 'publicgwip' in publicip_update_dict \
                        or 'ipalloc_mode_public' in publicip_update_dict or 'publiccidr' in publicip_update_dict:

                        if server_dict.get('ipalloc_mode_public') == "STATIC" or 'ipalloc_mode_public' in publicip_update_dict:
                            log.debug("Disable NSR Backup Data")
                            need_nsbackup = True
                    else:
                        bd_update_condition['category'] = 'onebox'

                    #bd_update_result, bd_update_content = orch_dbm.update_backup_history(mydb, {'ood_flag':True}, bd_update_condition)
                    #if bd_update_result < 0:
                    #    log.warning("failed to disable old backup data")

                    # 3. Make a new Backup Data with new settings
                    # log.debug("__________ %s _new_server_thread >> backup_onebox START" % server_dict['onebox_id'])
                    try:
                        bo_result, bo_content = backup_onebox(mydb, {}, server_dict['onebox_id'], tid = None, tpath = None, use_thread=False)
                        if bo_result < 0:
                            log.error("failed to backup One-Box: %d %s" %(bo_result, bo_content))

                        #if server_info.get('nsseq') is not None and need_nsbackup == True:
                        #    nsb_result, nsb_content = _backup_nsr_api(server_info['nsseq'])
                        #    if nsb_result < 0:
                        #        log.error("failed to backup NSR: %d %s" %(nsb_result, nsb_content))
                    except Exception, e:
                        log.exception("__________ Exception: %s" %str(e))
                    # log.debug("__________ %s _new_server_thread >> backup_onebox END" % server_dict['onebox_id'])
                    # 4. update NSR backup file
                    #global global_config
                # END : 사용안함

                if server_info.get('nsseq') is not None and update_info and not is_wad:
                    try:
                        flag_chg_mac = None
                        is_wan_list = update_info.get("is_wan_list", False)
                        if is_wan_list:
                            if "chg_port_info" in update_info\
                                and update_info["chg_port_info"].get("wan", None)\
                                and update_info["chg_port_info"]["wan"].get("mac", None):
                                flag_chg_mac = "MULTI"
                        else:
                            if 'publicmac' in publicip_update_dict:
                                flag_chg_mac = "ONE"

                        if flag_chg_mac:

                            log.debug("Update Mac Address of NS backup file %s %s" %(str(server_info['nsseq']), str(publicip_update_dict)))

                            target_condition = {"nsseq":server_info['nsseq'], "category": "vnf", "ood_flag":False}
                            nsb_result, nsb_content = orch_dbm.get_backup_history(mydb, target_condition)
                            if nsb_result < 0:
                                log.error("Failed to get Backup data for NSR: %s from DB" %str(server_info['nsseq']))
                            elif nsb_result == 0:
                                log.debug("Not found Backup data for NSR: %s" %str(server_info['nsseq']))
                            else:
                                for b_info in nsb_content:
                                    if b_info.get('backup_server') is None or b_info.get('backup_location') is None:
                                        log.debug("Invalid Backup Info: %s" %str(b_info))
                                        continue

                                    backup_filepath = b_info['backup_location']
                                    backup_server_ip = b_info['backup_server']

                                    if backup_filepath.find("KT-VNF") < 0:
                                        log.debug("Not Target Backup Data: %s" %str(b_info))
                                        continue

                                    log.debug("========================================")
                                    log.debug("Target Backup Data: %s" %str(b_info))
                                    log.debug("========================================")

                                    # get ha connection
                                    ssh_conn = ssh_connector(backup_server_ip, 9922)

                                    # make script
                                    command = {}
                                    command["name"]= "/var/onebox/script/update_KT-VNF_backup.sh"

                                    if flag_chg_mac == "ONE":
                                        command["params"] = [ backup_filepath, publicip_update_dict['old_publicmac'], publicip_update_dict['publicmac'] ]
                                    else:
                                        command["params"] = [ backup_filepath ]
                                        mac_dict = update_info["chg_port_info"]["wan"]["mac"]
                                        old_mac_dict = update_info["chg_port_info"]["wan"]["old_mac"]
                                        for r_name in mac_dict.keys():
                                            command["params"].extend([old_mac_dict[r_name], mac_dict[r_name]])

                                        log.debug("__________ ssh_command : %s" % command)

                                    # do script
                                    result, output = ssh_conn.run_ssh_command(command)

                                    log.debug("ssh_conn result = %s %s" %(str(result), str(output)))

                    except Exception, e:
                        log.exception("Exception: %s" %str(e))

        except Exception, e:
            log.exception("Exception: %s" %str(e))
            return -HTTP_Internal_Server_Error, "One-Box 서버정보 처리가 실패하였습니다. 원인: %s" %str(e)

    # first_notify = True 인 경우(agent가 재시동했을 경우), monitor쪽에 noti를 해줘야한다. (Plugin 재설치)
    if "first_notify" in server_info and server_info["first_notify"]:
        noti_result, noti_data = first_notify_monitor(mydb, server_info)
        if noti_result < 0:
            log.error("__________ Failed to notify monitor: %s" % noti_data)

    return 200, "OK"

def _new_server_update_vim(mydb, server_dict, use_thread=False):
    # Step 1. Get VIM Info
    if 'vimseq' in server_dict:
        vim_id = server_dict['vimseq']
    else:
        vim_result, vim_content = orch_dbm.get_vim_serverseq(mydb, server_dict['serverseq'])
        if vim_result < 0:
            log.error("Failed to get VIM Info from DB: %d %s" %(vim_result, vim_content))
            return -HTTP_Internal_Server_Error, "No VIM Associated"
        vim_id = vim_content[0]['vimseq']

    # Step 2. VIM Network, Image Update
    # 신버전인 경우 image-update를 생략한다.
    result, version = common_manager.get_vnfm_version(mydb, server_dict['serverseq'])
    if result < 0:
        log.error("Failed to get vnfm version : serverseq = %s" % server_dict['serverseq'])
        return -HTTP_Internal_Server_Error, "Failed to get vnfm version : serverseq = %s" % server_dict['serverseq']
    if version["kind"] == "OLD":
        vi_result, vi_content = vim_action(mydb, vim_id, {"image-update":""})
        if vi_result < 0:
            log.error("Failed to VIM Image Update %d %s" % (vi_result, vi_content))
    else:
        vi_result, vi_content = (200, "")

    vn_result, vn_content = vim_action(mydb, vim_id, {"net-update":""})
    if vn_result < 0:
        log.error("Failed to VIM Network Update %d %s" % (vn_result, vn_content))

    if vi_result < 0 or vn_result < 0:
        return -HTTP_Internal_Server_Error, "Image Update Result: %s, Network Update Result: %s" %(str(vi_content), str(vn_content))
    else:
        return 200, "Both Image and Network are updated successfully"

# event manager
def _new_server_update_vim_em(mydb, server_dict, myvnfm, use_thread=False):
    # Step 1. Get VIM Info
    if 'vimseq' in server_dict:
        vim_id = server_dict['vimseq']
    else:
        vim_result, vim_content = orch_dbm.get_vim_serverseq(mydb, server_dict['serverseq'])
        if vim_result < 0:
            log.error("Failed to get VIM Info from DB: %d %s" %(vim_result, vim_content))
            return -HTTP_Internal_Server_Error, "No VIM Associated"
        vim_id = vim_content[0]['vimseq']

    # Step 2. VIM Network, Image Update
    # 신버전인 경우 image-update를 생략한다.
    # result, version = common_manager.get_vnfm_version(mydb, server_dict['serverseq'])
    result, version = myvnfm.get_vnfm_version()

    if result < 0:
        log.error("Failed to get vnfm version : serverseq = %s" % server_dict['serverseq'])
        return -HTTP_Internal_Server_Error, "Failed to get vnfm version : serverseq = %s" % server_dict['serverseq']
    if version["kind"] == "OLD":
        vi_result, vi_content = vim_action(mydb, vim_id, {"image-update":""})
        if vi_result < 0:
            log.error("Failed to VIM Image Update %d %s" % (vi_result, vi_content))
    else:
        vi_result, vi_content = (200, "")

    vn_result, vn_content = vim_action(mydb, vim_id, {"net-update":""})
    if vn_result < 0:
        log.error("Failed to VIM Network Update %d %s" % (vn_result, vn_content))

    if vi_result < 0 or vn_result < 0:
        return -HTTP_Internal_Server_Error, "Image Update Result: %s, Network Update Result: %s" %(str(vi_content), str(vn_content))
    else:
        return 200, "Both Image and Network are updated successfully"

# def _new_server_do_monitor(mydb, serverseq, job = "START_M", use_thread=False, body_dict=None):
#     # s_result, s_content = orch_dbm.get_server_id(mydb, server_dict['serverseq'])
#     # if s_result < 0:
#     #     log.error("Failed to get Server Info from DB: %d %s" %(s_result, s_content))
#     #     return s_result, s_content
#
#     if job == "START_M":
#         log.debug("Do start_onebox_monitor()")
#         monitor_result, monitor_data = start_onebox_monitor(mydb, serverseq)
#         if monitor_result >= 0:
#             us_result, us_data = orch_dbm.update_server(mydb, {'serverseq':serverseq, 'state':"RUNNING"})
#     elif job == "UPDATE_M":
#         log.debug("DO update_onebox_monitor()")
#         monitor_result, monitor_data = update_onebox_monitor(mydb, serverseq, body_dict)
#     else:
#         log.warning("Monitor API is unknown: serverseq=%s" % serverseq)
#         monitor_result=-HTTP_Internal_Server_Error
#         monitor_data="Monitor API is unknown: serverseq=%s" % serverseq
#
#     if monitor_result < 0:
#         log.warning("Failed to call monitor api for One-Box: %d %s" %(monitor_result, str(monitor_data)))
#
#     return monitor_result, monitor_data

def get_server_with_filter(mydb, filter_data=None, onebox_type=None):
    filter_dict={}

    # if type(filter_data) is str:
    #     log.debug('get_server_with_filter : filter_data type check = %s' % type(filter_data))

    if filter_data == None:
        return -HTTP_Bad_Request, "Invalid Condition"
    elif type(filter_data) is int or type(filter_data) is long:
        filter_dict['serverseq'] = filter_data
    elif type(filter_data) is str and filter_data.isdigit():
        filter_dict['serverseq'] = filter_data
    elif unicode(filter_data).isnumeric():
        filter_dict['serverseq'] = filter_data
    elif af.is_ip_addr(filter_data):
        filter_dict['public_ip'] = filter_data
    else:
        filter_dict['onebox_id'] = filter_data

    # 초소형 이후 개발 관련
    if onebox_type is not None:
        filter_dict['onebox_type'] = onebox_type

    log.debug('get_server_with_filter : filter_dict = %s' %str(filter_dict))

    # result, data = orch_dbm.get_server_filters(mydb, filter_dict)
    result, data = orch_dbm.get_server_filters_wf(mydb, filter_dict)
    if result > 0:
        ret_data=[]

        for d in data:
            r = {"onebox_id":d['onebox_id'], "status":d['status'], "ob_service_number":d['ob_service_number'], "nfsubcategory":d['nfsubcategory'], "serverseq":d['serverseq'], "nsseq":d['nsseq']}
            ret_data.append(r)
        return result, ret_data

    elif result == 0:
        return -HTTP_Not_Found, "Cannot find the server(one-box) of %s" %str(filter_dict)
    return result, data


def delete_server(mydb, server):
    log.debug("IN: %s" %str(server))
    #delete customer server info
    result, server_dict = orch_dbm.get_server_id(mydb, server)
    if result < 0:
        log.error("failed to delete the server %s" %server)
        return result, server_dict

    #TODO: Stop monitor for the One-Box
    m_result, m_data = stop_onebox_monitor(mydb, server_dict)
    if m_result < 0:
        log.warning("failed to stop monitoring on the One-Box: %s" %str(server_dict))

    # Delete One-Box Info. from DB
    result, server_id = orch_dbm.delete_server(mydb, server_dict['serverseq'])
    if result < 0:
        log.error("failed to delete the DB record for %s" %server)
        return result, server_id

    data={"onebox_id":server_dict['onebox_id'], "status":SRVStatus.IDLE}
    return 200, data


def _check_server_validation(mydb, server_dict, hardware_dict=None, network_list=None, software_dict = None, mac_check = True):
    """
    서버의 유효성 체크, [new_server]
    :param mydb:
    :param server_dict:
    :param hardware_dict:
    :param network_list:
    :param software_dict:
    :param mac_check:
    :return:
    """

    ret_result = 200
    ret_msg = ""

    # Step 1. check One-Box general info, Skip

    # Step 2. Check mgmtip and public ip
    if server_dict.get('mgmtip') is None or af.check_valid_ipv4(server_dict['mgmtip']) == False:
        ret_result = -HTTP_Bad_Request
        ret_msg += "\n [MIP][%s] One-Box의 관리용 IP가 유효하지 않습니다. \n - 관리용 IP 주소: %s" %(str(datetime.datetime.now()), str(server_dict.get('mgmtip')))

    if mac_check:
        if server_dict.get('publicip') is None or af.check_valid_ipv4(server_dict.get('publicip')) == False:
           ret_result = -HTTP_Bad_Request
           ret_msg = "\n One-Box의 공인 IP가 유효하지 않습니다. %s" %str(server_dict.get('publicip'))

        if server_dict.get('publicgwip') is None or af.check_valid_ipv4(server_dict['publicgwip']) == False:
           ret_result = -HTTP_Bad_Request
           ret_msg += "\n [MIP][%s] One-Box의 공인 GW IP가 유효하지 않습니다. \n - GW IP 주소: %s" %(str(datetime.datetime.now()), str(server_dict.get('publicgwip')))

    # Step 3. check public MAC
    if server_dict.get('publicmac') is None or len(server_dict['publicmac']) < 3:
        ret_result = -HTTP_Bad_Request
        ret_msg += "\n [WMAC][%s] One-Box의 WAN NIC의 MAC 주소가 유효하지 않습니다. \n - MAC 주소: %s" %(str(datetime.datetime.now()), str(server_dict.get('publicmac')))
    else:
        # TODO: Check Duplication of MAC & Public IP
        pass

    # 회선이중화 : wan_list에서 public_gw_ip 값이 "" 이거나 잘못된 값이면 예외처리
    if server_dict.get("wan_list", None):
        for wan in server_dict["wan_list"]:
            if not wan["public_ip_dhcp"]: # STATIC인 경우
                if  wan.get("public_gw_ip", None) is None:
                    ret_result = -HTTP_Bad_Request
                    ret_msg += "\n [WGW][%s] One-Box의 WAN Public Gateway IP주소가 존재하지 않습니다." %(str(datetime.datetime.now()))
                    break
                elif wan["public_gw_ip"] == "" or af.check_valid_ipv4(wan["public_gw_ip"]) == False:
                    ret_result = -HTTP_Bad_Request
                    ret_msg += "\n [WGW][%s] One-Box의 WAN Public Gateway IP주소가 유효하지 않습니다. \n - Gateway IP 주소: %s" %(str(datetime.datetime.now()), str(wan["public_gw_ip"]))
                    break
    if server_dict.get("extra_wan_list", None):
        for wan in server_dict["extra_wan_list"]:
            if not wan["public_ip_dhcp"]: # STATIC인 경우
                if  wan.get("public_gw_ip", None) is None:
                    ret_result = -HTTP_Bad_Request
                    ret_msg += "\n [WGW][%s] One-Box의 Extra WAN Public Gateway IP주소가 존재하지 않습니다." %(str(datetime.datetime.now()))
                    break
                elif wan["public_gw_ip"] == "" or af.check_valid_ipv4(wan["public_gw_ip"]) == False:
                    ret_result = -HTTP_Bad_Request
                    ret_msg += "\n [WGW][%s] One-Box의 Extra WAN Public Gateway IP주소가 유효하지 않습니다. \n - Gateway IP 주소: %s" %(str(datetime.datetime.now()), str(wan["public_gw_ip"]))
                    break

    if ret_result < 0:
        return ret_result, ret_msg

    if mac_check:
        #public_ip = server_dict['publicip']
        public_mac = server_dict['publicmac']
        onebox_id = server_dict['onebox_id']

        # oob_result, oob_content = common_manager.get_server_all_with_filter(mydb, onebox_id)
        oob_result, oob_content = orch_dbm.get_server_id(mydb, onebox_id)
        if oob_result < 0:
            log.error("failed to get One-Box Info from DB: %d %s" %(oob_result, oob_content))
            ret_result = -HTTP_Internal_Server_Error
            ret_msg += "\n DB Error로 One-Box 정보 검증이 실패하였습니다."
        elif oob_result == 0:
            pass
        else:
            # for c in oob_content:
            if oob_content.get('publicmac') is not None:
                # log.debug("[HJC] public mac: %s" %str(c.get('publicmac')))
                if len(oob_content.get('publicmac')) < 3:
                    log.debug("[HJC] ignore invalid public mac: %s" % str(oob_content.get('publicmac')))
                elif oob_content.get('publicmac') != public_mac:
                    result_wan, wan_list = orch_dbm.get_server_wan_list(mydb, oob_content["serverseq"])
                    found_old_mac = False
                    if result_wan > 0:
                        for w in wan_list:
                            if w['mac'] == public_mac:
                                log.debug("Valid MAC Address because it mached with %s" % str(w))
                                found_old_mac = True
                                break
                    elif result_wan <= 0:
                        log.debug("Failed to get WAN List for the One-Box: %s due to %d %s" %(onebox_id, result_wan, str(wan_list)))

                    if found_old_mac is False:
                        log.debug("Invalid One-Box Info: an One-Box ID cannot have different public MAC Address")
                        ret_result = -HTTP_Conflict
                        ret_msg += "\n [DOB][%s] 다른 MAC 주소의 One-Box 정보가 수신되었습니다. \n - 확인 필요한 One-Box의 IP주소: %s \n - One-Box 서버 교체의 경우 좌측 초기화 버튼을 실행해주세요." %(str(datetime.datetime.now()), str(server_dict.get('mgmtip')))

                        # break

    if ret_result < 0:
        return ret_result, ret_msg

    # Step 4. check hardware type
    if hardware_dict is not None:
        order_ob_flavor = server_dict['onebox_flavor']
        ob_hw_result, ob_hw_data = orch_dbm.get_onebox_flavor_name(mydb, order_ob_flavor)
        if ob_hw_result <= 0:
            log.error("failed to get One-Box HW Model Info: %d %s" %(ob_hw_result, ob_hw_data))
        else:
            order_hw_model = ob_hw_data['hw_model']
            if order_hw_model != hardware_dict['model']:
                log.debug("One-Box HW Model is different from the Order: %s vs %s" %(hardware_dict['model'], order_hw_model))
                #ret_result = -HTTP_Bad_Request
                ret_msg += "\n [WHW][%s] One-Box H/W 모델이 오더 정보와 다릅니다. One-Box H/W 모델 확인 필요. \n - 오더 H/W 모델: %s \n   - One-Box H/W 모델: %s" %(str(datetime.datetime.now()), order_hw_model, hardware_dict['model'])

    if ret_result < 0:
        return ret_result, ret_msg

    # Step 5. check One-Box Agents Connectivity
    if software_dict is not None:
        #TODO
        pass

    return ret_result, ret_msg


def _parse_server_info(mydb, server_info):
    """
    서버정보를 객체에 담아서 리턴
    :param mydb:
    :param server_info:
    :return: server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict
    """
    vim_dict = None
    vim_tenant_dict = None
    hardware_dict = None
    software_dict = None
    vnet_dict = None

    #log.debug("[HJC] IN: Server_info = %s" %str(server_info))

    server_dict = {'customerseq':server_info['customerseq'], 'onebox_id':server_info['onebox_id']}
    server_dict['servername'] = server_info['onebox_id']
    server_dict['nfmaincategory'] = "Server"

    # server_dict['nfsubcategory'] = "One-Box"      # Arm-Box의 경우 이미 채워져 오기 때문에 값이 바뀌면 안된다
    server_dict['nfsubcategory'] = "One-Box"

    server_dict['orgnamescode'] = server_info.get("org_name", "목동")

    if 'serverseq' in server_info:
        server_dict['serverseq'] = server_info['serverseq']

    if 'public_ip' in server_info:
        server_dict['publicip'] = server_info['public_ip']
        server_dict['mgmtip'] = server_info.get("mgmt_ip", server_dict['publicip'])

    if 'public_ip_dhcp' in server_info:
        if server_info.get('public_ip_dhcp', True):
            server_dict['ipalloc_mode_public'] = "DHCP"
            # log.debug("One-Box Info: ipalloc_mode_public DHCP")
        else:
            server_dict['ipalloc_mode_public'] = "STATIC"
            # log.debug("One-Box Info: ipalloc_mode_public STATIC")

    if server_info.get('public_gw_ip') is not None:
        server_dict['publicgwip'] = server_info['public_gw_ip']

    if server_info.get('public_cidr_prefix') is not None:
        server_dict['publiccidr'] = server_info['public_cidr_prefix']

    if 'mgmt_ip' in server_info:
        server_dict['mgmtip'] = server_info['mgmt_ip']

    if 'onebox_flavor' in server_info:
        #TODO
        # 1. get flavor list from tb_onebox_flavor
        # 2. if exists, add value else add default
        server_dict['onebox_flavor']=server_info['onebox_flavor']

    # 5G router 사용 여부
    if 'router' in server_info:
        server_dict['router'] = server_info['router']

    if 'vim' in server_info:
        vim_dict = {'vimtypecode':server_info['vim']['vim_type'],'authurl':server_info['vim']['vim_authurl']}
        vim_dict['name']=server_dict['onebox_id']+"_"+"VIM-OS1"
        vim_dict['display_name']=server_info['vim']['vim_type'].split("-")[0]
        vim_dict['version']=server_info['vim'].get("vim_version","kilo")
        vim_tenant_dict = {'name':server_info['vim']['vim_tenant_name'], 'username':server_info['vim']['vim_tenant_username'], 'password':server_info['vim']['vim_tenant_passwd']}
        vim_tenant_dict['domain'] = "default"

    if 'hardware' in server_info:
        hardware_dict = {'model':server_info['hardware']['model']}
        hardware_dict['cpu'] = server_info['hardware'].get('cpu')
        hardware_dict['num_cpus'] = server_info['hardware'].get('num_cpus')
        hardware_dict['num_cores_per_cpu'] = server_info['hardware'].get('num_cores_per_cpu')
        hardware_dict['num_logical_cores'] = server_info['hardware'].get('num_logical_cores')
        hardware_dict['mem_size'] = server_info['hardware'].get('mem_size')

    if 'software' in server_info:
        software_dict = {'operating_system': server_info['software']['operating_system']}
        if 'vnfm' in server_info:
            software_dict['onebox_vnfm_base_url'] = server_info['vnfm']['base_url']
            software_dict['onebox_vnfm_version'] = server_info['vnfm'].get('version', "0.0")

            server_dict['vnfm_base_url'] = server_info['vnfm']['base_url']

            # Get vnfm version
            myvnfm = vnfmconnector.vnfmconnector(id=server_dict['servername'], name=server_dict['servername'], url=server_dict['vnfm_base_url'], mydb=mydb)
            result_ver, ver_dict = myvnfm.get_vnfm_version()
            if result_ver < 0:
                log.error("Failed to get vnfm version %s %s" % (result_ver, ver_dict))
            else:
                log.debug('result_ver : %d, ver_dict : %s' %(result_ver, str(ver_dict)))

                if ver_dict["version"] == "NOTSUPPORTED":
                    server_dict['vnfm_version'] = "0.0"
                else:
                    server_dict['vnfm_version'] = ver_dict["version"]
                    software_dict['onebox_vnfm_version'] = ver_dict["version"]
            # server_dict['vnfm_version'] = server_info['vnfm'].get('version', "0.0")

        if 'obagent' in server_info:
            software_dict['onebox_agent_base_url'] = server_info['obagent']['base_url']
            software_dict['onebox_agent_version'] = server_info['obagent'].get('version', "0.0")

            server_dict['obagent_base_url'] = server_info['obagent']['base_url']
            server_dict['obagent_version'] = server_info['obagent'].get('version', "0.0")

    if 'public_nic' in server_info:
        server_dict['public_nic'] = server_info['public_nic']
        server_dict['mgmt_nic'] = server_info.get("mgmt_nic", server_dict['public_nic'])

    network_list = []
    # 회선이중화 : wan_list 가 있는 경우 publicmac, net_mode, network_list 처리
    if 'wan_list' in server_info:

        # check validation of wan list
        for idx in range(len(server_info["wan_list"])-1, -1, -1):
            wan = server_info["wan_list"][idx]

            # public_ip, public_cidr_prefix 항목이 존재하지 않거나, 빈값이면 public_ip = NA, public_cidr_prefix = -1
            if wan.get("public_ip", None) is None:
                wan["public_ip"] = "NA"
            if wan.get("public_cidr_prefix", None) is None:
                wan["public_cidr_prefix"] = -1

            # DHCP인 경우에 public_gw_ip가 없을 수 있다. 없는 경우 "NA" 처리
            if wan["public_ip_dhcp"]:
                if "public_gw_ip" not in wan or wan["public_gw_ip"] is None or wan["public_gw_ip"] == "":
                    wan["public_gw_ip"] = "NA"
            else:
                if "public_gw_ip" not in wan or wan["public_gw_ip"] is None or wan["public_gw_ip"] == "":
                    log.error("Empty public_gw_ip! If 'STATIC', public_gw_ip must be.")
                    # TODO : 예외처리하는 것이 맞으나 일단 NA 주고 넘어감...
                    wan["public_gw_ip"] = "NA"

        server_dict["wan_list"] = server_info["wan_list"]
        public_nic = server_info["public_nic"]

        r_num = 0
        for wan in server_dict["wan_list"]:
            if wan["nic"] == public_nic:
                server_dict['publicmac'] = wan["mac"]
                server_dict['net_mode'] = wan["mode"]

                # wan_list값이 들어왔을때 기본 pulblic_nic을 Active로 세팅한다.
                wan["status"] = "A"
            else:
                wan["status"] = "S"

            # wan_list 순서대로 R0~N 주는 방식으로 변경처리.
            wan["name"] = "R"+ str(r_num)
            r_num += 1

            network_list.append({'name':wan['nic'], 'display_name':"wan"})

            # public_ip_dhcp 항목을 ipalloc_mode_public 형태로 변경처리
            if wan['public_ip_dhcp']:
                wan['ipalloc_mode_public'] = "DHCP"
            else:
                wan['ipalloc_mode_public'] = "STATIC"

    elif 'wan' in server_info: # 회선 이중화 호환성 유지부분
        server_dict['publicmac'] = server_info['wan']['mac']
        if 'mode' in server_info['wan'] and 'nic' in server_info['wan']:
            server_dict['net_mode'] = server_info['wan']['mode']
            network_list.append({'name':server_info['wan']['nic'], 'display_name':"wan"})

    if 'lan_office' in server_info:
        if server_info['lan_office']['nic'] is not None:
            # nic이 여러개인경우 처리
            nic = server_info['lan_office']['nic']
            if nic is not None and len(nic.strip(" ")) > 0:
                nics = nic.replace(" ","").split(",")
                for item in nics:
                    network_list.append({'name':item, 'display_name':"office"})

    if 'lan_server' in server_info:
        if server_info['lan_server']['nic'] is not None:
            # nic이 여러개인경우 처리
            nic = server_info['lan_server']['nic']
            if nic is not None and len(nic.strip(" ")) > 0:
                nics = nic.replace(" ","").split(",")
                for item in nics:
                    network_list.append({'name':item, 'display_name':"server"})

    # HA 구성일 경우 : 우선은 other zone 으로
    if 'lan_ha' in server_info:
        if server_info['lan_ha']['nic']:
            server_dict['ha'] = "HA"

            if server_info['lan_ha']['nic'] is not None:
                # nic이 여러개인경우 처리
                nic = server_info['lan_ha']['nic']
                if nic is not None and len(nic.strip(" ")) > 0:
                    nics = nic.replace(" ","").split(",")
                    for item in nics:
                        network_list.append({'name':item, 'display_name':"other"})

    # extra_wan_list 항목 처리
    if 'extra_wan_list' in server_info and len(server_info["extra_wan_list"]) > 0:
        # check validation of wan list
        for idx in range(len(server_info["extra_wan_list"])-1, -1, -1):
            wan = server_info["extra_wan_list"][idx]

            # public_ip, public_cidr_prefix 항목이 존재하지 않거나, 빈값이면 public_ip = NA, public_cidr_prefix = -1
            if wan.get("public_ip", None) is None:
                wan["public_ip"] = "NA"
            if wan.get("public_cidr_prefix", None) is None:
                wan["public_cidr_prefix"] = -1

            # DHCP인 경우에 public_gw_ip가 없을 수 있다. 없는 경우 "NA" 처리
            if wan["public_ip_dhcp"]:
                if "public_gw_ip" not in wan or wan["public_gw_ip"] is None or wan["public_gw_ip"] == "":
                    wan["public_gw_ip"] = "NA"
            else:
                if "public_gw_ip" not in wan or wan["public_gw_ip"] is None or wan["public_gw_ip"] == "":
                    log.error("Empty public_gw_ip! If 'STATIC', public_gw_ip must be.")
                    wan["public_gw_ip"] = "NA"

        server_dict["extra_wan_list"] = server_info["extra_wan_list"]

        e_num = 0
        for wan in server_dict["extra_wan_list"]:

            wan["status"] = "A"

            # extra_wan_list 순서대로 E0~N 주는 방식으로 변경처리.
            wan["name"] = "E"+ str(e_num)
            e_num += 1

            network_list.append({'name':wan['nic'], 'display_name':"extra_wan"})

            # public_ip_dhcp 항목을 ipalloc_mode_public 형태로 변경처리
            if wan['public_ip_dhcp']:
                wan['ipalloc_mode_public'] = "DHCP"
            else:
                wan['ipalloc_mode_public'] = "STATIC"

    try:
        if 'vnet' in server_info:

            vnet_dict={}

            for vnet in server_info['vnet']:

                if vnet.get('name', "") == "net_office":
                    if vnet.get('ip') is not None:
                        vnet_dict['vnet_office_ip'] = vnet['ip']
                    if vnet.get('cidr_prefix') is not None:
                        vnet_dict['vnet_office_cidr'] = vnet['cidr_prefix']
                    if vnet.get('subnet') is not None:
                        vnet_dict['vnet_office_subnets'] = vnet['subnet']

                elif vnet.get('name', "") == "net_server":
                    if vnet.get('ip') is not None:
                        vnet_dict['vnet_server_ip'] = vnet['ip']
                    if vnet.get('cidr_prefix') is not None:
                        vnet_dict['vnet_server_cidr'] = vnet['cidr_prefix']
                    if vnet.get('subnet') is not None:
                        vnet_dict['vnet_server_subnets'] = vnet['subnet']

                # HA 구성일 경우
                elif vnet.get('name', "") == "net_ha":
                    if vnet.get('ip') is not None:
                        vnet_dict['vnet_ha_ip'] = vnet['ip']
                    if vnet.get('cidr_prefix') is not None:
                        vnet_dict['vnet_ha_cidr'] = vnet['cidr_prefix']
                    if vnet.get('subnet') is not None:
                        vnet_dict['vnet_ha_subnets'] = vnet['subnet']

    except Exception, e:
        log.exception("Exception: %s" %str(e))
        vnet_dict = None

    server_dict['state'] = server_info.get('state', "NOTSTART")

    #if 'network' in server_info and server_info['network'] != None:
    #    if len(server_info['network']) == 0:
    #        network_list=[]
    #    else:
    #        network_list=[]
    #        for net in server_info['network']:
    #            net_dict = {'name': net['name'], 'display_name': net['display_name']}
    #            if 'metadata' in net:
    #                net_dict['metadata'] = net['metadata']
    #            network_list.append(net_dict)

    server_dict['status'] = server_info['status']

    if server_dict['status'] == SRVStatus.LWT:
        if 'publicip' in server_dict:
            server_dict['status']=SRVStatus.RIS
        if vim_dict and vim_tenant_dict:
            server_dict['status']=SRVStatus.RDS

    elif server_dict['status'] == SRVStatus.RIS:
        if vim_dict and vim_tenant_dict:
            server_dict['status']=SRVStatus.RDS

    elif server_dict['status'] == SRVStatus.DSC:
        if 'publicip' in server_dict:
            server_dict['status']=SRVStatus.RIS

        if vim_dict and vim_tenant_dict:
            server_dict['status']=SRVStatus.RDS

        if server_info.get('nsseq') is not None:
            nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, server_info.get('nsseq'))

            if nsr_result <= 0:
                log.warning("Failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
            else:
                if nsr_data.get('status', "UNDEFINED") == NSRStatus.RUN:
                    server_dict['status']=SRVStatus.INS
                elif nsr_data.get('status', "UNDEFINED") == NSRStatus.ERR:
                    server_dict['status']=SRVStatus.ERR
                else:
                    log.error("NSR Status is unexpected: %s" % str(nsr_data.get('status')))
                    server_dict['status']=SRVStatus.ERR

    elif server_dict['status'] == SRVStatus.ERR:
        if server_info.get('nsseq') is None:
            if 'publicip' in server_dict:
                server_dict['status']=SRVStatus.RIS
                log.debug("[HJC] Update Server Status to %s" %server_dict['status'])

            if vim_dict and vim_tenant_dict:
                server_dict['status']=SRVStatus.RDS
                log.debug("[HJC] Update Server Status to %s" %server_dict['status'])
            else:
                log.debug("[HJC] Do not update Server Status")
        else:
            nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, server_info.get('nsseq'))
            if nsr_result <= 0:
                log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
            else:
                if nsr_data.get('status', "UNDEFINED") == NSRStatus.RUN:
                    server_dict['status']=SRVStatus.INS
                else:
                    log.debug("[HJC] Do not update Server Status in ERROR because there is a NS that is not RUNNING")

    log.debug("The Server status is %s" % (str(server_info['status']) if str(server_info['status']) == str(server_dict['status'])
                                                                      else "changed : %s => %s" % (str(server_info['status']), str(server_dict['status']))))

    if server_dict['status'] == SRVStatus.RDS:
        if server_info.get('serveruuid'):
            server_dict['serveruuid'] = server_info['serveruuid']
        else:
            server_dict['serveruuid'] = af.create_uuid()

    # note 정보가 있을 경우 처리
    if 'note' in server_info:
        memo = ""
        for note in server_info["note"]:
            if "noteCode" in note: # 필수
                noteCode = note["noteCode"]
                noteText = ""
                if noteCode == "001_001":
                    noteText = "KT-VNF에 Route 설정 삭제 됨."
                elif noteCode == "001_002":
                    noteText = "KT-VNF에 Route 맵규칙 설정 삭제 됨."
                elif noteCode == "001_003":
                    noteText = "KT-VNF에 기존 WAN IP 설정 변경 됨."
                elif noteCode == "001_004":
                    noteText = "KT-VNF에 ARP 설정 삭제 됨."

                memo += "\n" + datetime.datetime.now().strftime("[%Y-%m-%d %H:%M] ") + noteText + "\n"
                memo += json.dumps(note, indent=4)
        if len(memo) > 0:
            server_dict["note"] = memo

    return server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict


def _check_existing_servers(mydb, server_dict, filter_data=None):
    """
    해당 조건에 맞는 server 정보가 있는지 체크 후, 조회
    :param server_dict: server_info
    :param filter_data: onebox_id or public_ip
    :return: 서버 정보
    """
    filter_dict={}
    if "customer_name" in server_dict:
        cust_result, cust_data = orch_dbm.get_customer_id(mydb, server_dict['customer_name'])
        if cust_result < 0:
            pass
        else:
            filter_dict['customerseq'] = cust_data['customerseq']

    if filter_data is None:
        pass
    elif af.is_ip_addr(filter_data):
        filter_dict['public_ip'] = filter_data
    else:
        filter_dict['onebox_id'] = filter_data

    if len(filter_dict) == 0:
        return -HTTP_Bad_Request, "Not Valid Request: Cannot find Customer"

    result, data = orch_dbm.get_server_filters_wf(mydb, filter_dict)
    if result <= 0:
        return result, data
    elif len(data) > 1:
        return len(data), "%d oneboxes are found" %(len(data))
    else: # 서버 정보가 정상적으로 1개만 조회되었을 경우
        # 회선이중화 : wan list 정보가 넘어온 경우 기존 wan list 정보 조회
        # 변경 되었을 경우 수정작업을 위해...
        if "wan_list" in server_dict:
            result_wan, wan_list = orch_dbm.get_server_wan_list(mydb, data[0]["serverseq"])
            if result_wan > 0:
                data[0]["wan_list"] = wan_list

        if "extra_wan_list" in server_dict:
            result_wan, extra_wan_list = orch_dbm.get_server_wan_list(mydb, data[0]["serverseq"], kind="E")
            if result_wan > 0:
                data[0]["extra_wan_list"] = extra_wan_list

        return result, data


def associate_server_with_customer(mydb, server_id, data):
    result, server_dict = orch_dbm.get_server_id(mydb, server_id)
    if result < 0:
        log.error("failed to get the server info from DB %d %s" %(result, server_dict))
        return result, server_dict
    if result == 0:
        log.error("No pOne-Box server found %d %s" %(result, server_dict))
        return -HTTP_Not_Found, server_dict

    r, customer_dict = orch_dbm.get_customer_id(mydb, data['customerseq'])
    if r <= 0:
        log.error("failed to get the Customer Info from DB %d %s" %(r, customer_dict))
        return result, customer_dict
    data['customerseq'] = customer_dict['customerseq']

    if server_dict['status'] != SRVStatus.IDLE and server_dict.get('customerseq',"none") != data['customerseq']:
        log.error("The pOne-Box server %s has been already allocated to the other customer %s" %(server_dict['customername'], server_dict['customerseq']))
        return -HTTP_Bad_Request, "The pOne-Box server already allocated, detach the pOneBox server before newly attaching"

    #TODO Check if the install_org exists
    #TODO Check if the IP address is accessible

    for key in server_dict:
        if key in data:
            log.debug("key: %s, old value = %s, new value = %s" %(key, server_dict[key], data.get(key,"None")))
            server_dict[key] = data[key]

    #server_dict['status'] = SRVStatus.RIS

    result, content = orch_dbm.update_server(mydb, server_dict)
    if result < 0:
        log.error("failed to update the server %d %s" %(result, content))
    return result, content


def deassociate_server_from_customer(mydb, server_id):
    result, server_dict = orch_dbm.get_server_id(mydb, server_id)
    if result < 0:
        log.error("failed to get pOne-Box server Info from DB %d %s" %(result, server_dict))
        return result, server_dict

    if result == 0:
        log.error("No pOne-Box server found")
        return -HTTP_Not_Found, "No pOne-Box found server %s" %server_id

    server_dict['customerseq'] = None
    server_dict['mgmtip'] = None
    server_dict['orgnamescode'] = None
    #server_dict['status'] = SRVStatus.RIS

    warning=''
    result, data = orch_dbm.update_server(mydb, server_dict)
    if result<0:
        log.error("failed to deassociate a customer form pOne-Box server %d %s" %(result, data))
        return result, data

    return 200, "server %s (%s) detached.%s" %(server_dict['serverseq'], server_dict['serveruuid'], warning)


def get_server_progress_with_filter(mydb, filter_data):
    result, ob_data = orch_dbm.get_server_id(mydb, filter_data)   #common_manager.get_server_all_with_filter(mydb, filter_data)

    if result <= 0:
        log.error("failed to get server info from DB: %d %s" %(result, ob_data))
        return result, ob_data

    action_type = ob_data.get('action')
    if action_type is None: action_type = "NONE"

    status = "DOING"

    #log.debug("[+++++HJC++++++] One-Box Info: %s" %str(content[0]))
    if ob_data['status'] != SRVStatus.OOS:
        if ob_data['status'] == SRVStatus.ERR:
            status = "ERROR"
        else:
            if action_type == "ME":
                status = "ERROR"
            else:
                status = "DONE"

    progress_data = {'action_type': action_type, 'status': status}

    return 200, progress_data


def get_server_backup_data(mydb, onebox_id):
    try:
        # Step.1 Get One-Box info
        ob_result, ob_data = orch_dbm.get_server_id(mydb, onebox_id)   #common_manager.get_server_all_with_filter(mydb, onebox_id)
        if ob_result <= 0:
            log.error("get_server_with_filter Error %d %s" %(ob_result, ob_data))
            return ob_result, ob_data

        # ob_data = ob_content[0]

        # Step.2 Get backup info
        target_dict = {'serverseq':ob_data['serverseq']}
        target_dict['category'] = 'onebox'

        backup_result, backup_data = orch_dbm.get_backup_history_lastone(mydb, target_dict)

        log.debug("[*******HJC**********] %d, %s" %(backup_result, str(backup_data)))

        if backup_result <= 0:
            log.warning("Failed to get backup history for %d %s" %(backup_result, str(backup_data)))
            return -HTTP_Bad_Request, "Cannot find a Backup File"

        ret_data_backup = json.loads(backup_data.get('backup_data'))

        # 임시코드
        try:
            if "mgmt" in ret_data_backup and "extra_mgmt" in ret_data_backup:
                mgmt = ret_data_backup["mgmt"]
                for extra_mgmt in ret_data_backup["extra_mgmt"]:
                    if mgmt["interface"] == extra_mgmt["interface"]:
                        mgmt["bridge"] = extra_mgmt["bridge"]
                        break
        except Exception, e:
            log.debug("Exception for setting bridge of mgmt : %s" % str(e))
        # 임시코드 END

        resp_dict = {"backup_data": ret_data_backup}
        if 'backup_location' in backup_data: resp_dict['remote_location'] = backup_data['backup_location']
        if 'backup_local_location' in backup_data: resp_dict['local_location'] = backup_data['backup_local_location']
        if backup_data.get('backup_server') is not None: resp_dict['backup_server_ip'] = backup_data['backup_server']
        if backup_data.get('backup_server_port') is not None:
            resp_dict['backup_server_port'] = backup_data['backup_server_port']
        else:
            resp_dict['backup_server_port'] = "9922"

        return 200, resp_dict
    except Exception, e:
        error_msg = "failed to get backup_data: %s" %str(e)
        log.exception(error_msg)
        return -HTTP_Internal_Server_Error, error_msg


def backup_onebox(mydb, backup_settings, onebox_id, tid = None, tpath = None, use_thread=True):
    global global_config

    try:
        # Step.1 Check arguments
        if onebox_id is None:
            log.error("One-Box ID is not given")
            return -HTTP_Bad_Request, "One-Box ID is required."

        if tid is not None:
            action_tid = tid
        else:
            action_tid = af.create_action_tid()

        if tpath is None:
            tpath = "/orch_onebox-backup"
        else:
            tpath += "/orch_onebox-backup"

        log.debug("Action TID : %s, TPATH : %s" % (action_tid, tpath))
        log.debug("onebox_id : %s" % str(onebox_id))

        # Step.2 Get One-Box info. and check status
        ob_result, ob_data = orch_dbm.get_server_id(mydb, onebox_id) #common_manager.get_server_all_with_filter(mydb, onebox_id)
        if ob_result <= 0:
            log.error("get_server_with_filter Error : server_id = %s, %d %s" %(onebox_id, ob_result, ob_data))
            return ob_result, ob_data

        # ob_data = ob_content[0]

        if ob_data['status'] == SRVStatus.LWT or ob_data['status'] == SRVStatus.PVS or ob_data['status'] == SRVStatus.OOS or ob_data['status'] == SRVStatus.ERR:
            return -HTTP_Bad_Request, "Cannot backup the One-Box in the status of %s" %(ob_data['status'])

        if ob_data['action'] is None or ob_data['action'].endswith("E"): # NGKIM: Use RE for backup
            pass
        else:
            return -HTTP_Bad_Request, "The One-Box is in Progress for another action: status= %s action= %s" %(ob_data['status'], ob_data['action'])

        ob_org_status = ob_data['status']

        # Step.3 Update One-Box status
        action_dict = {'tid':action_tid}
        action_dict['category'] = "OBBackup"
        action_dict['action'] = "BS"
        action_dict['status'] = "Start"
        action_dict['action_user'] = backup_settings.get("user", "admin")
        action_dict['server_name'] = ob_data['servername']
        action_dict['server_seq'] = ob_data['serverseq']

        try:
            e2e_log = e2elogger(tname='One-Box backup', tmodule='orch-f', tid=action_tid, tpath=tpath)
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

    except Exception, e:
        error_msg = "failed invoke a Thread for backup VNF %s" %str(e)
        log.exception(error_msg)
        return -HTTP_Internal_Server_Error, error_msg
    try:
        common_manager.update_onebox_status_internally(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.STRT, ob_data=ob_data, ob_status=SRVStatus.OOS)

        # Step 4. Start One-Box backup
        if use_thread:
            th = threading.Thread(target=_backup_onebox_thread, args=(mydb, onebox_id, ob_data, ob_org_status, action_dict, backup_settings, e2e_log, True))
            th.start()

            return_data = {"backup": "OK", "status": "DOING"}
        else:
            return _backup_onebox_thread(mydb, onebox_id, ob_data, ob_org_status, action_dict, backup_settings, e2e_log=e2e_log, use_thread=False)
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        common_manager.update_onebox_status_internally(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
        return -HTTP_Internal_Server_Error, "One-Box 백업이 실패하였습니다. 원인: %s" %str(e)

    return 200, return_data


def _backup_onebox_thread(mydb, onebox_id, ob_data, ob_org_status, action_dict, backup_settings={}, e2e_log=None, use_thread=True):

    if use_thread:
        log.debug("[THREAD STARTED] _backup_onebox_thread()")

    is_onebox_backup_successful = True

    try:
        # Step.1 initialize variables
        global global_config

        # Step.2 Get One-Box Agent connector
        result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)
        if result < 0:
            log.error("Error. One-Box Agent not found")
            is_onebox_backup_successful = False
        elif result > 1:
            is_onebox_backup_successful = False
            log.error("Error. Several One-Box Agents available, must be identify")

        log.debug("D__________0 %s _backup_onebox_thread >> get_onebox_agent" % ob_data['onebox_id'])
        if is_onebox_backup_successful is False:
            common_manager.update_onebox_status_internally(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
            if e2e_log:
                e2e_log.job('One-Box backup Fail', CONST_TRESULT_FAIL,
                            tmsg_body="serverseq: %s\nResult: One-Box backup이 실패하였습니다. 원인: %s" % (str(ob_data['serverseq']), "Cannot establish One-Box Agent Connector"))
                e2e_log.finish(CONST_TRESULT_FAIL)
            return -HTTP_Not_Found, "Cannot establish One-Box Agent Connector"

        ob_agent = ob_agents.values()[0]

        # Step.3 Update One-Box status
        common_manager.update_onebox_status_internally(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.INPG, ob_data=ob_data, ob_status=SRVStatus.OOS)
        log.debug("D__________1 %s _backup_onebox_thread >> update_onebox_status_internally : ACTStatus.INPG:%s" % (ob_data['onebox_id'], ACTStatus.INPG))
        # Step.4 Backup One-Box
        result = 200
        backup_content = None
        # 4-1. composing backup request info
        req_dict = {"onebox_id": ob_data['onebox_id']}
        req_dict['backup_server'] = backup_settings.get('backup_server', global_config['backup_server'])
        if af.check_valid_ipv4(req_dict['backup_server']) is False:
            req_dict['backup_server'] = global_config['backup_server']
        if 'backup_location' in backup_settings:
            req_dict['backup_location'] = backup_settings['backup_location']

        # log.debug("D__________2 %s _backup_onebox_thread >> ob_agent.backup_onebox BEFORE: req_dict = %s" % (ob_data['onebox_id'],req_dict))
        backup_result, backup_data = ob_agent.backup_onebox(req_dict)
        if backup_result < 0:
            # result = backup_result
            # log.error("Failed to backup One-Box %s: %d %s" %(ob_data['onebox_id'], backup_result, backup_data))
            # common_manager.update_onebox_status_internally(mydb, "B", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
            # return result, backup_data
            raise Exception("Failed to backup One-Box %s: %d %s" %(ob_data['onebox_id'], backup_result, backup_data))
        elif backup_data.get('backup_data') is None:
            # log.error("No Backup Data in the response from One-Box Agent")
            # return -HTTP_Internal_Server_Error, "No Backup Data in the response from One-Box Agent"
            raise Exception("No Backup Data in the response from One-Box Agent")
        else:
            log.debug("Completed to send backup command to the One-Box Agent for %s" % (ob_data['onebox_id']))
            # common_manager.update_onebox_status_internally(mydb, "B", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
            backup_content = json.dumps(backup_data['backup_data'], indent=4)
        # log.debug("D__________3 %s _backup_onebox_thread >> ob_agent.backup_onebox AFTER: result = %d %s" % (ob_data['onebox_id'], backup_result, backup_data))

        if e2e_log:
            e2e_log.job('Backup One-Box by Agent', CONST_TRESULT_SUCC,
                        tmsg_body="onebox_id: %s\nBackup Contents:%s" % (str(ob_data['onebox_id']), backup_content))

        # 4-2. DB insert: backup info
        backup_dict = {'serverseq':ob_data['serverseq'], 'nsseq':ob_data['nsseq'], 'category':"onebox"}
        backup_dict['server_name'] = ob_data['onebox_id']
        backup_dict['backup_server'] = req_dict['backup_server']
        backup_dict['backup_location'] = backup_data.get('remote_location')
        backup_dict['backup_local_location'] = backup_data.get('local_location')
        backup_dict['description'] = "One-Box backup file"
        backup_dict['creator'] = backup_settings.get('user', "admin")
        backup_dict['trigger_type'] = backup_settings.get('trigger_type', "manual")
        backup_dict['status'] = "Completed"
        backup_dict['backup_data'] = backup_content

        backup_dict['download_url'] = "http://"+backup_dict['backup_server']+backup_dict['backup_location'].replace("/var/onebox/backup", "/backup", 1)
        db_result, db_data = orch_dbm.insert_backup_history(mydb, backup_dict)
        if db_result < 0:
            raise Exception("Failed to insert backup history into DB : %d %s" % (db_result, db_data))

        # log.debug("D__________4 %s _backup_onebox_thread >> insert_backup_history END" % ob_data['onebox_id'])

        if e2e_log:
            e2e_log.job('Insert backup history to DB', CONST_TRESULT_SUCC,
                        tmsg_body="serverseq: %s\nInserted data:%s" % (str(ob_data['serverseq']), backup_dict))

        # 4-3. update One-Box status and record action history
        common_manager.update_onebox_status_internally(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.SUCC, ob_data=ob_data, ob_status=ob_org_status)
        log.debug("D__________SUCC %s _backup_onebox_thread >> END" % str(ob_data['onebox_id']))
        if e2e_log:
            e2e_log.job('One-Box Backup Finished', CONST_TRESULT_SUCC, tmsg_body="")
            e2e_log.finish(CONST_TRESULT_SUCC)

    except Exception, e:
        log.error("D__________E %s : %s" % (str(ob_data['onebox_id']), str(e)))
        # is_onebox_backup_successful = False
        common_manager.update_onebox_status_internally(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)

        if e2e_log:
            e2e_log.job('One-Box backup Fail', CONST_TRESULT_FAIL,
                        tmsg_body="serverseq: %s\nResult: One-Box backup이 실패하였습니다. 원인: %s" % (str(ob_data['serverseq']), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, str(e)

    if use_thread:
        log.debug("[THREAD FINISHED] _backup_onebox_thread()")
    return 200, "OK"


# def _check_nsr_exist(mydb, ob_data):
#     is_nsr_exist = True
#     nsr_id = -1
#     if ob_data.get('nsseq') is None:
#         is_nsr_exist = False
#         return 200, {"nsr_exist": is_nsr_exist, "nsseq": nsr_id}
#
#     nsr_id = ob_data['nsseq']
#     nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr_id)
#     if nsr_result <= 0:
#         log.debug("No NSR found")
#         is_nsr_exist = False
#         return 200, {"nsr_exist": is_nsr_exist, "nsseq": nsr_id}
#
#     #TODO: Check One-Box Inside
#
#     if nsr_id < 0:
#         is_nsr_exist = False
#
#     log.debug("NSR Info: %s, %d" %(str(is_nsr_exist), nsr_id))
#     return 200, {"nsr_exist": is_nsr_exist, "nsseq": nsr_id}


# def _delete_nsr(mydb, nsr_id, server_data, need_stop_monitor=True, use_thread=True, tid=None, tpath=""):
#     try:
#         try:
#             if not tid:
#                 e2e_log = e2elogger(tname='NS Deleting', tmodule='orch-f', tpath="orch_ns-del")
#             else:
#                 e2e_log = e2elogger(tname='NS Deleting', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_ns-del")
#         except Exception, e:
#             log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
#             e2e_log = None
#
#         if e2e_log:
#             e2e_log.job("NS 종료 API 수신 처리 시작", CONST_TRESULT_SUCC, tmsg_body="NS ID: %s" % (str(nsr_id)))
#
#         # Step 1. get scenario instance from DB
#         # log.debug ("Check that the nsr_id exists and getting the instance dictionary")
#         result, instanceDict = orch_dbm.get_nsr_id(mydb, nsr_id)
#         if result < 0:
#             log.error("delete_nsr error. Error getting info from database")
#             raise Exception("Failed to get NS Info. from DB: %d %s" % (result, instanceDict))
#         elif result == 0:
#             log.error("delete_nsr error. Instance not found")
#             raise Exception("NSR not found")
#
#         #if instanceDict['action'] is None or instanceDict['action'].endswith("E"):
#         #    pass
#         #else:
#         #    raise Exception("Orch is handling other requests for the instance %s. try later" % nsr_id)
#
#         if e2e_log:
#             e2e_log.job("Get scenario instance from DB", CONST_TRESULT_SUCC,
#                         tmsg_body="Scenario instance Info : %s" % (json.dumps(instanceDict, indent=4)))
#     except Exception, e:
#         log.exception("Exception: %s" % str(e))
#
#         if e2e_log:
#             e2e_log.job('NS 종료 API 수신 처리 실패', CONST_TRESULT_FAIL, tmsg_body="NS ID: %s" % (str(nsr_id)))
#             e2e_log.finish(CONST_TRESULT_FAIL)
#
#         return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)
#
#     try:
#         if use_thread:
#             try:
#                 th = threading.Thread(target=_delete_nsr_thread, args=(mydb, instanceDict, server_data, need_stop_monitor, use_thread, e2e_log))
#                 th.start()
#             except Exception, e:
#                 error_msg = "failed to start a thread for deleting the NS Instance %s" % str(nsr_id)
#                 log.exception(error_msg)
#
#                 if e2e_log:
#                     e2e_log.job('NS 종료 Background Thread 시작', CONST_TRESULT_FAIL, tmsg_body=error_msg)
#
#                 use_thread = False
#
#         if use_thread:
#             return result, 'OK'
#         else:
#             return _delete_nsr_thread(mydb, instanceDict, server_data, need_stop_monitor, False, e2e_log)
#     except Exception, e:
#         log.exception("Exception: %s" % str(e))
#
#         if e2e_log:
#             e2e_log.job('NS 종료', CONST_TRESULT_FAIL, tmsg_body="NS 삭제가 실패하였습니다. 원인: %s" % str(e))
#
#         return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)
#
# def _delete_nsr_thread(mydb, instanceDict, server_data, need_stop_monitor=True, use_thread=True, e2e_log=None):
#     try:
#         if use_thread:
#             log_info_message = "Deleting NS - Thread Started (%s)" % instanceDict['name']
#             log.info(log_info_message.center(80, '='))
#
#             if e2e_log:
#                 e2e_log.job('NS 종료 Background Thread 시작', CONST_TRESULT_SUCC, tmsg_body=log_info_message)
#
#         if need_stop_monitor:
#             if e2e_log:
#                 e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_NONE, tmsg_body="NS 모니터링 종료 요청")
#
#             monitor_result, monitor_response = stop_nsr_monitor(mydb, instanceDict['nsseq'], e2e_log)
#
#             if monitor_result < 0:
#                 log.error("failed to stop monitor for %d: %d %s" % (instanceDict['nsseq'], monitor_result, str(monitor_response)))
#                 if e2e_log:
#                     e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_FAIL,
#                                 tmsg_body="NS 모니터링 종료 요청 실패\n원인: %d %s" % (monitor_result, monitor_response))
#                     # return monitor_result, monitor_response
#             else:
#                 if e2e_log:
#                     e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_SUCC,
#                                 tmsg_body="NS 모니터링 종료 요청 완료")
#
#         result, vims = get_vim_connector(mydb, instanceDict['vimseq'])
#
#         if result < 0:
#             log.error("nfvo.delete_nsr_thread() error. vim not found")
#             raise Exception("Failed to establish VIM connection: %d %s" % (result, vims))
#
#         myvim = vims.values()[0]
#
#         # return back license and request to finish VNF
#         for vnf in instanceDict['vnfs']:
#             #result, data = return_license(mydb, vnf.get('license'))
#             #if result < 0:
#             #    log.warning("Failed to return license back for VNF %s and License %s" % (vnf['name'], vnf.get('license')))
#
#             result, data = _finish_vnf_using_ktvnfm(mydb, server_data['serverseq'], vnf['vdus'], e2e_log)
#
#             if result < 0:
#                 log.error("Failed to finish VNF %s: %d %s" % (vnf['name'], result, data))
#                 raise Exception("Failed to finish VNF %s: %d %s" % (vnf['name'], result, data))
#
#         result, stack_uuid = myvim.delete_heat_stack_v4(instanceDict['uuid'], instanceDict['name'])
#
#         if result == -HTTP_Not_Found:
#             log.error("Not exists. Just Delete DB Records")
#         elif result < 0:
#             log.error("failed to delete stack from Heat because of " + stack_uuid)
#
#             if result != -HTTP_Not_Found:
#                 raise Exception("failed to delete stack from Heat because of " + stack_uuid)
#
#         result, c = orch_dbm.delete_nsr(mydb, instanceDict['nsseq'], instanceDict['name'], instanceDict)
#
#         if result < 0:
#             log.error("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))
#             raise Exception("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))
#
#         if use_thread:
#             log_info_message = "Deleting NS - Thread Finished (%s)" % instanceDict['name']
#             log.info(log_info_message.center(80, '='))
#
#         if e2e_log:
#             e2e_log.job('NS 종료 처리 완료', CONST_TRESULT_SUCC, tmsg_body="NS 종료 처리 완료")
#
#         return 1, 'NSR ' + str(instanceDict['nsseq']) + ' deleted'
#
#     except Exception, e:
#         if use_thread:
#             log_info_message = "Deleting NS - Thread Finished with Error Exception: %s" % str(e)
#             log.exception(log_info_message.center(80, '='))
#         else:
#             log.exception("Exception: %s" % str(e))
#         if e2e_log:
#             e2e_log.job('NS 종료 처리 실패', CONST_TRESULT_FAIL, tmsg_body=str(e))
#
#         return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)
#
# # 사용하지 않음 : 일정기간 확인 후 삭제예정.
# def freset_onebox(mydb, request, onebox_id):
#     try:
#         # Step.1 Check arguments and initialize variables
#         if onebox_id == None:
#             log.error("One-Box ID is not given")
#             return -HTTP_Bad_Request, "One-Box ID is required."
#
#         action_tid = af.create_action_tid()
#
#         # Step.2 Get One-Box info
#         ob_result, ob_content = common_manager.get_server_all_with_filter(mydb, onebox_id)
#         if ob_result <= 0:
#             log.error("get_server_with_filter Error %d %s" %(ob_result, ob_content))
#             return ob_result, ob_content
#
#         ob_data = ob_content[0]
#
#         if ob_data['status'] == SRVStatus.LWT or ob_data['status'] == SRVStatus.PVS or ob_data['status'] == SRVStatus.OOS:
#             return -HTTP_Bad_Request, "Cannot factory reset the One-Box in the status of %s" %(ob_data['status'])
#
#         if ob_data['action'] == None or ob_data['action'].endswith("E"): # NGKIM: Use RE for backup
#             pass
#         else:
#             return -HTTP_Bad_Request, "The One-Box is in Progress for another action: status= %s action= %s" %(ob_data['status'], ob_data['action'])
#
#         ob_org_status = ob_data['status']
#
#         # Step.3 Update One-Box status
#         action_dict = {'tid':action_tid}
#         action_dict['category'] = "OBReset"
#         action_dict['action'] = "FS"
#         action_dict['status'] = "Start"
#         action_dict['action_user'] = request.get("user", "admin")
#         action_dict['server_name'] = ob_data['servername']
#         action_dict['server_seq'] = ob_data['serverseq']
#     except Exception, e:
#         log.exception("Exception: %s" %str(e))
#         return -HTTP_Internal_Server_Error, "One-Box 공장초기화가 실패하였습니다. 원인: %s" %str(e)
#
#     try:
#         common_manager.update_onebox_status_internally(mydb, "F", action_dict=action_dict, action_status=ACTStatus.STRT, ob_data=ob_data, ob_status=SRVStatus.OOS)
#
#         # Step.4 Restore One-Box
#         th = threading.Thread(target=_freset_onebox_thread, args=(mydb, onebox_id, ob_data, ob_org_status, action_dict, request))
#         th.start()
#     except Exception, e:
#         log.exception("Exception: %s" %str(e))
#         common_manager.update_onebox_status_internally(mydb, "F", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
#         return -HTTP_Internal_Server_Error, "One-Box 공장초기화가 실패하였습니다. 원인: %s" %str(e)
#
#     return 200, "OK"
#
# def _freset_onebox_thread(mydb, onebox_id, ob_data, ob_org_status, action_dict, request, use_thread=True):
#     try:
#         # Step.1 initialize variables
#         global global_config
#         result = 200
#         is_onebox_backup_successful = True
#
#         # Step.2 Get One-Box Agent Connector
#         result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)
#         if result < 0:
#             log.error("Error. One-Box Agent not found")
#             is_onebox_backup_successful = False
#         elif result > 1:
#             is_onebox_backup_successful = False
#             log.error("Error. Several One-Box Agents available, must be identify")
#
#         if is_onebox_backup_successful == False:
#             common_manager.update_onebox_status_internally(mydb, "F", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
#             return -HTTP_Not_Found, "Cannot establish One-Box Agent Connector"
#
#         ob_agent = ob_agents.values()[0]
#         # Step.3 Reset One-Box
#         common_manager.update_onebox_status_internally(mydb, "F", action_dict=action_dict, action_status=ACTStatus.INPG, ob_data=ob_data, ob_status=SRVStatus.OOS)
#
#         # 3-1. Delete NSR
#         if ob_data.get('nsseq') is not None:
#             dn_result, dn_data = _delete_nsr(mydb, ob_data.get('nsseq'), ob_data, need_stop_monitor=True, use_thread=False, tid=None, tpath="")
#             if dn_result < 0:
#                 common_manager.update_onebox_status_internally(mydb, "F", action_dict=None, action_status=None, ob_data=ob_data, ob_status=ob_org_status)
#                 return dn_result, dn_data
#             else:
#                 ob_data['nsseq']=None
#
#         # 3-2. Suspend Monitor for One-Box
#         common_manager.update_onebox_status_internally(mydb, "F", action_dict=None, action_status=None, ob_data=ob_data, ob_status=SRVStatus.OOS_suspendingmonitor)
#         monitor_result, monitor_data = suspend_onebox_monitor(mydb, ob_data)
#         if monitor_result < 0:
#             log.warning("Failed to suspend monitor for One-Box. False Alarms are expected")
#
#         # 3-3. Compose One-Box Agent request
#         req_dict = {"onebox_id": ob_data['onebox_id']}
#         req_dict['backup_server'] = global_config['backup_server']
#
#         # 3-4. Call API of One-Box Agent: Restore One-Box
#         freset_result, freset_data = ob_agent.freset_onebox(req_dict)
#         if freset_result < 0:
#             result = freset_result
#             log.error("Failed to factory reset One-Box %s: %d %s" %(ob_data['onebox_id'], freset_result, freset_data))
#
#             #TODO
#             common_manager.update_onebox_status_internally(mydb, "F", action_dict=None, action_status=None, ob_data=ob_data, ob_status=ob_org_status)
#             #update_onebox_status_internally(mydb, "F", action_dict=None, action_status=None, ob_data=ob_data, ob_status=SRVStatus.ERR)
#             return freset_result, freset_data
#
#         # 3-5. Wait for FReset One-Box
#         log.debug("Completed to send factory reset command to the One-Box Agent for %s: %s" %(ob_data['onebox_id'], str(freset_data)))
#         req_dict['tid'] = freset_data['transaction_id']
#         action = "freset"
#         trial_no = 1
#         pre_status = "UNKNOWN"
#
#         log.debug("Wait for freset One-Box by Agent: %s" %(ob_data['onebox_id']))
#         time.sleep(30)
#
#         while trial_no < 30:
#             log.debug("Checking the progress of freset (%d):" %trial_no)
#
#             result, check_data, check_status = _check_onebox_status(ob_agent, action, req_dict)
#
#             if pre_status != check_status:
#                     pre_status = check_status
#                     #TODO Update Status
#
#             if check_data == "DONE":
#                 log.debug("Completed to freset One-Box by Agent")
#                 break
#             else:
#                 log.debug("Factory Reset in Progress")
#
#             trial_no += 1
#             time.sleep(10)
#
#         # 3-6. Resume Monitor
#         common_manager.update_onebox_status_internally(mydb, "F", action_dict=None, action_status=None, ob_data=ob_data, ob_status=SRVStatus.OOS_resumingmonitor)
#         monitor_result, monitor_data = resume_onebox_monitor_old(mydb, ob_data)
#         if monitor_result < 0:
#             log.warning("Failed to resume monitor.")
#
#         # 3-7. Update One-Box status and record action history
#         if result < 0:
#             common_manager.update_onebox_status_internally(mydb, "F", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=SRVStatus.ERR)
#         else:
#             common_manager.update_onebox_status_internally(mydb, "F", action_dict=action_dict, action_status=ACTStatus.SUCC, ob_data=ob_data, ob_status=SRVStatus.RDS)
#
#         log.debug("End One-Box Factory Reset: %s" %ob_data['onebox_id'])
#     except Exception, e:
#         log.exception("Exception: %s" %str(e))
#         common_manager.update_onebox_status_internally(mydb, "F", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=SRVStatus.ERR)
#         return -HTTP_Internal_Server_Error, "공장초기화가 실패하였습니다. 원인: %s" %str(e)
#
#     log.debug("_freset_onebox_thread() OUT")
#
#     return 200, "OK"

def reset_mac(mydb, request_dict, onebox_id, force=True):
    log.debug("[HJC] IN with One-Box ID = %s" %onebox_id)
    # tb_server update
    log.debug("[HJC] 1. get One-Box info from DB")
    filter_dict = {'onebox_id': onebox_id}

    result, data = orch_dbm.get_server_filters(mydb, filter_dict)
    if result < 0:
        log.error("failed to get One-Box Info from DB: %d %s" %(result, str(data)))
        return -HTTP_Not_Found, str(data)
    elif result == 0:
        log.error("%s Not found: %d %s" %(onebox_id, result, str(data)))
        return -HTTP_Not_Found, "%s Not found" %(onebox_id)

    onebox_db = data[0]
    log.debug("[HJC] Succeed to get One-Box info from DB: %s" %str(onebox_db))

    #log.debug("[HJC] 2. reset mac addrss in DB")
    #server_dict = {'serverseq': onebox_db['serverseq'], 'publicmac': ""}
    #result, data = orch_dbm.update_server(mydb, server_dict)
    #if result < 0:
    #    log.error("failed to reset mac due to DB Error: %d %s" %(result, data))
    #    return result, data
    #log.debug("[HJC] Succeed to reset mac addrss in DB")

    # request to update OB Info to OBA
    try:
        log.debug("[HJC] 3. get one-box info from One-Box Agent")
        result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)
        if result < 0 or result > 1:
            log.error("Error. Invalid DB Records for the One-Box Agent: %s" %str(onebox_id))
            raise Exception("Error. Invalid DB Records for the One-Box Agent: %s" %str(onebox_id))

        ob_agent = ob_agents.values()[0]
        result, content = ob_agent.get_onebox_info(None)
        log.debug("The result of getting onebox info: %d %s" %(result, str(content)))
        if result < 0:
            log.error("Failed to get onebox info from One-Box Agent: %d %s" %(result, content))
            raise Exception("Failed to get onebox info from One-Box Agent: %d %s" %(result, content))

        server_info = content
        log.debug("[HJC] Succeed to get one-box info from One-Box Agent: %s" %str(server_info))
    except Exception, e:
        log.exception("Exception: %s" % str(e))

        log.debug("reset mac addrss in DB")
        server_dict = {'serverseq': onebox_db['serverseq'], 'publicmac': ""}
        result, data = orch_dbm.update_server(mydb, server_dict)
        if result < 0:
            log.error("failed to reset mac due to DB Error: %d %s" %(result, data))
            return result, data
        log.debug("Succeed to reset mac addrss in DB")
        rtn_msg = "MAC주소 초기화 동작 중 Agent에 접속이 안되고 있습니다.\n" \
                  "Agent에서 서버정보를 보내주면 MAC 주소가 자동으로 초기화 됩니다.(몇분 이상 걸릴 수 있습니다.)\n" \
                  "만약 해결되지 않으면 관리자에게 문의하세요."

        return -HTTP_Internal_Server_Error, rtn_msg

    # update server info
    try:
        log.debug("[HJC] 4. update one-box info into DB")
        result, data = new_server(mydb, server_info, filter_data=onebox_id, use_thread=True, forced=True)
        if result < 0:
            raise Exception("failed to update onebox-info to DB: %d %s" %(result, data))
        log.debug("[HJC] Succeed to update one-box info into DB")
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, str(e)

    log.debug("[HJC] OUT with One-Box ID = %s" %onebox_id)
    return 200, "OK"


def check_onebox_valid(mydb, check_settings, onebox_id, nfsubcategory="One-Box", force = True):
    global global_config

    try:
        # Step.1 Check arguments
        if onebox_id == None:
            log.error("One-Box ID is not given")
            return -HTTP_Bad_Request, "One-Box ID is required."

        action_tid = af.create_action_tid()
        log.debug("Action TID: %s" %action_tid)

        # Step.2 Get One-Box info. and Status
        if nfsubcategory == "One-Box":
            ob_result, ob_content = common_manager.get_server_all_with_filter(mydb, onebox_id)
        else:
            ob_result, ob_content = common_manager.get_server_all_with_filter_wf(mydb, onebox_id)

        if ob_result <= 0:
            log.error("get_server_with_filter Error %d %s" %(ob_result, ob_content))
            return ob_result, ob_content
        ob_data = ob_content[0]
        ob_org_status = ob_data['status']
        onebox_id = ob_data['onebox_id']    # onebox_id가 serverseq값으로 들어온 경우를 위해 실제 onebox_id로 교체처리.

        result_data = {"status": ob_data['status']}

        # Step.3 Check connections to One-Box Agents
        if ob_data['status'] != SRVStatus.ERR or force == True:
            result_data['status']="DONE"
            result_data['detail']=[]
            #3-1. One-Box Agent
            result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)
            # log.debug('event : check_onebox_vaild > result = %d, ob_agents = %s' %(result, str(ob_agents)))
            if result < 0 or result > 1:
                log.error("Error. Invalid DB Records for the One-Box Agent: %s" %str(onebox_id))
                result_data['status']="FAIL"
                result_data['detail'].append({'agent_connection':"NOK"})
            else:
                ob_agent = ob_agents.values()[0]

                result, check_content = ob_agent.check_connection()
                log.debug("The result of checking a connection to One-Box Agent: %d %s" %(result, str(check_content)))
                if result < 0:
                    result_data['status']="FAIL"
                    result_data['detail'].append({'agent_connection':"NOK"})
                else:
                    result_data['detail'].append({'agent_connection':"OK"})

            # kind : One-Box | KtPnf, PNF형은 vnf 체크 하지 않는다
            if ob_data.get('nfsubcategory') == 'One-Box':
                #3-2. VNFM Agent
                result, vnfms = common_manager.get_ktvnfm(mydb, ob_data['serverseq'])
                if result < 0 or result > 1:
                    log.error("Error. Invalid DB Records for the VNFM: %s" %str(ob_data['serverseq']))
                    result_data['status']="FAIL"
                    result_data['detail'].append({'vnfm_connection':"NOK"})
                else:
                    myvnfm = vnfms.values()[0]
                    result, check_content = myvnfm.check_connection()
                    log.debug("The result of checking a connection to VNFM: %d %s" %(result, str(check_content)))
                    if result < 0:
                        result_data['status']="FAIL"
                        result_data['detail'].append({'vnfm_connection':"NOK"})
                    else:
                        result_data['detail'].append({'vnfm_connection':"OK"})
                #3-3. VIM
                vims = ob_data.get("vims")
                if type(vims) == list and len(vims) > 0:
                    ob_data['vimseq'] = vims[0]['vimseq']
                    vim_result, vim_data = _new_server_update_vim(mydb, ob_data)
                    if vim_result < 0:
                        log.error("Failed to VIM Test: %d %s" %(vim_result, str(vim_data)))
                        result_data['status']="FAIL"
                        result_data['detail'].append({'vim_connection':"NOK"})
                    else:
                        result_data['detail'].append({'vim_connection':"OK"})
                else:
                    log.debug("No VIM Data found: %s" %str(ob_data))


        # Step.4 Resume WAN Monitoring of OBA
        #result, needwanswitch = need_wan_switch(mydb, {"onebox_id": onebox_id})
        #if result < 0:
        #    log.warning("failed to check the network mode of One-Box: %d %s" %(result, needwanswitch))
        #    needwanswitch = False

        #if needwanswitch:
        #    result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)
        #    if result < 0 or result > 1:
        #        log.warning("Error. Invalid DB Records for the One-Box Agent: %s" %str(onebox_id))
        #    else:
        #        ob_agent = ob_agents.values()[0]
        #        rm_result, rm_content = ob_agent.resume_monitor_wan()
        #        if rm_result < 0:
        #            log.warning("failed to resume WAN Monitoring of OBA: %d %s" %(rm_result, str(rm_content)))

        return 200, result_data
    except Exception, e:
        error_msg = "One-Box 연결 확인이 실패하였습니다. One-Box 연결상태를 확인하세요."
        log.exception(error_msg)
        return -515, error_msg

# event manager
def check_onebox_valid_em(mydb, check_settings, onebox_id, ob, force = True):
    global global_config

    try:
        # Step.1 Check arguments
        if onebox_id == None:
            log.error("One-Box ID is not given")
            return -HTTP_Bad_Request, "One-Box ID is required."

        action_tid = af.create_action_tid()
        log.debug("Action TID: %s" %action_tid)

        # Step.2 Get One-Box info. and Status
        # if ob.get('nfsubcategory') == "One-Box":
        #         #     ob_result, ob_content = common_manager.get_server_all_with_filter(mydb, onebox_id)
        #         # else:
        #         #     ob_result, ob_content = common_manager.get_server_all_with_filter_wf(mydb, onebox_id)
        content_list = [ob]
        ob_result, ob_content = common_manager.get_server_all_with_filter_em(mydb, content_list)

        if ob_result <= 0:
            log.error("get_server_with_filter Error %d %s" %(ob_result, ob_content))
            return ob_result, ob_content

        ob_data = ob_content[0]

        ob_org_status = ob_data['status']
        onebox_id = ob_data['onebox_id']    # onebox_id가 serverseq값으로 들어온 경우를 위해 실제 onebox_id로 교체처리.

        result_data = {"status": ob_data['status']}

        # Step.3 Check connections to One-Box Agents
        if ob_data['status'] != SRVStatus.ERR or force == True:
            result_data['status']="DONE"
            result_data['detail']=[]
            #3-1. One-Box Agent
            # result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)

            ob_dict = {}
            ob_dict[ob['serverseq']] = obconnector.obconnector(name=ob['servername'], url=ob['obagent_base_url'], mydb=mydb)

            result, ob_agents = len(ob_dict), ob_dict

            # log.debug('event : check_onebox_vaild > result = %d, ob_agents = %s' %(result, str(ob_agents)))
            if result < 0 or result > 1:
                log.error("Error. Invalid DB Records for the One-Box Agent: %s" %str(onebox_id))
                result_data['status']="FAIL"
                result_data['detail'].append({'agent_connection':"NOK"})
            else:
                ob_agent = ob_agents.values()[0]

                result, check_content = ob_agent.check_connection()
                log.debug("The result of checking a connection to One-Box Agent: %d %s" %(result, str(check_content)))
                if result < 0:
                    result_data['status']="FAIL"
                    result_data['detail'].append({'agent_connection':"NOK"})
                else:
                    result_data['detail'].append({'agent_connection':"OK"})

            # kind : One-Box | KtPnf, PNF형은 vnf 체크 하지 않는다
            if ob_data.get('nfsubcategory') == 'One-Box':
                #3-2. VNFM Agent
                # result, vnfms = common_manager.get_ktvnfm(mydb, ob_data['serverseq'])

                vnfm_dict = {}
                vnfm_dict[ob['serverseq']] = vnfmconnector.vnfmconnector(id=ob_data['serverseq'], name=ob['servername'], url=ob['vnfm_base_url'], mydb=mydb)

                result, vnfms = len(vnfm_dict), vnfm_dict

                if result < 0 or result > 1:
                    log.error("Error. Invalid DB Records for the VNFM: %s" %str(ob_data['serverseq']))
                    result_data['status']="FAIL"
                    result_data['detail'].append({'vnfm_connection':"NOK"})
                else:
                    myvnfm = vnfms.values()[0]
                    result, check_content = myvnfm.check_connection()
                    log.debug("The result of checking a connection to VNFM: %d %s" %(result, str(check_content)))
                    if result < 0:
                        result_data['status']="FAIL"
                        result_data['detail'].append({'vnfm_connection':"NOK"})
                    else:
                        result_data['detail'].append({'vnfm_connection':"OK"})

                #3-3. VIM
                vims = ob_data.get("vims")
                if type(vims) == list and len(vims) > 0:
                    ob_data['vimseq'] = vims[0]['vimseq']
                    # vim_result, vim_data = _new_server_update_vim(mydb, ob_data)
                    vim_result, vim_data = _new_server_update_vim_em(mydb, ob_data, myvnfm)
                    if vim_result < 0:
                        log.error("Failed to VIM Test: %d %s" %(vim_result, str(vim_data)))
                        result_data['status']="FAIL"
                        result_data['detail'].append({'vim_connection':"NOK"})
                    else:
                        result_data['detail'].append({'vim_connection':"OK"})
                else:
                    log.debug("No VIM Data found: %s" %str(ob_data))


        # Step.4 Resume WAN Monitoring of OBA
        #result, needwanswitch = need_wan_switch(mydb, {"onebox_id": onebox_id})
        #if result < 0:
        #    log.warning("failed to check the network mode of One-Box: %d %s" %(result, needwanswitch))
        #    needwanswitch = False

        #if needwanswitch:
        #    result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)
        #    if result < 0 or result > 1:
        #        log.warning("Error. Invalid DB Records for the One-Box Agent: %s" %str(onebox_id))
        #    else:
        #        ob_agent = ob_agents.values()[0]
        #        rm_result, rm_content = ob_agent.resume_monitor_wan()
        #        if rm_result < 0:
        #            log.warning("failed to resume WAN Monitoring of OBA: %d %s" %(rm_result, str(rm_content)))

        return 200, result_data
    except Exception, e:
        error_msg = "One-Box 연결 확인이 실패하였습니다. One-Box 연결상태를 확인하세요."
        log.exception(error_msg)
        return -515, error_msg

# def _check_onebox_status(ob_agent, action, req_dict):
#     result = 200
#     data = "DOING"
#     status = None
#
#     try:
#         check_result, check_data = ob_agent.check_onebox_status(req_dict)
#     except Exception, e:
#         log.exception("Exception: %s" %str(e))
#         check_result = -500
#         check_data = {'status':"UNKNOWN", 'error':str(e)}
#
#     if check_result < 0:
#         result = check_result
#         data = "DOING"
#         log.debug("Error %d, %s" %(check_result, str(check_data)))
#     else:
#         log.debug("Status form One-Box by Agent: %s" %(check_data['status']))
#         if check_data['status'] == "RUNNING":
#             result = 200
#             data = "DONE"
#         else:
#             try:
#                 action_result, action_data = ob_agent.check_onebox_action_status(action, req_dict)
#             except Exception, e:
#                 log.exception("Exception: %s" %str(e))
#                 action_result = -500
#                 action_data = {'status':"UNKNOWN", 'error':str(e)}
#
#             if action_result < 0 and action_data == None:
#                 log.debug("Error %d %s" %(action_result, str(action_data)))
#             else:
#                 status = "A__" + action_data['status'] + "__" + str(action_data['current_step']) + "__" + str(action_data['total_step'])
#
#     return result, data, status


def suspend_onebox_monitor(mydb, ob_data, e2e_log=None):
    monitor = common_manager.get_ktmonitor()
    if monitor == None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    target_dict = {}
    target_dict['server_id'] = ob_data['serverseq']
    target_dict['onebox_id'] = ob_data['onebox_id']
    target_dict['server_ip'] = ob_data['mgmtip']
    #target_dict['server_uuid'] = ob_data['serveruuid']
    #target_dict['vms'] = []

    result, data = monitor.suspend_monitor_onebox(target_dict, e2e_log)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

def stop_nsr_monitor(mydb, ob_data, e2e_log=None):
    monitor = common_manager.get_ktmonitor()
    if monitor == None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    target_dict = {}
    target_dict['server_id'] = ob_data['serverseq']
    target_dict['server_uuid'] = ob_data['serveruuid']
    target_dict['onebox_id'] = ob_data['onebox_id']
    target_dict['server_ip'] = ob_data['mgmtip']
    target_dict['vms'] = []

    nsr_result, nsr_content = orch_dbm.get_nsr_id(mydb, ob_data['nsseq'])
    if nsr_result < 0:
        log.warning("Error getting NSR info from database")
        return nsr_result, nsr_content
    elif nsr_result == 0:
        log.warning("NSR not found")
        return nsr_result, "NSR not found"

    np_result, np_content = orch_dbm.get_nsr_params(mydb, nsr_content['nsseq'])
    if np_result < 0:
        log.error("Failed to get NSR Parameter Info")
        return -HTTP_Internal_Server_Error, "Failed to get NSR Parameter Info for NSR = %s" %str(nsr_content['nsseq'])
    nsr_content['parameters'] = np_content

    target_dict['name'] = nsr_content['name']

    target_vms = []
    for vnf in nsr_content['vnfs']:
        vnf_app_id=None
        vnf_app_passwd=None
        for param in nsr_content['parameters']:
            if param['name'].find("appid_"+vnf['name']) >= 0:
                vnf_app_id = param['value']
            if param['name'].find("apppasswd_"+vnf['name']) >= 0:
                vnf_app_passwd = param['value']

        for vm in vnf['vdus']:
            target_vm = {'vm_name':vm['name'], 'vdud_id':vm['vdudseq'], 'vm_vim_name':vm['vim_name'], 'vm_vim_uuid':vm['uuid'], 'monitor_target_seq':vm['monitor_target_seq'],
                         'vm_id':vm['vm_access_id'], 'vm_passwd':vm['vm_access_passwd']}
            if vnf_app_id: target_vm['vm_app_id']=vnf_app_id
            if vnf_app_passwd: target_vm['vm_app_passwd']=vnf_app_passwd

            target_cps = []
            for cp in vm['cps']:
                target_cp = {'cp_name':cp['name'], 'cp_vim_name':cp['vim_name'], 'cp_vim_uuid':cp['uuid'], 'cp_ip':cp['ip']}
                target_cps.append(target_cp)
            target_vm['vm_cps']=target_cps

            target_vms.append(target_vm)
    target_dict['vms'] = target_vms

    result, data = monitor.stop_monitor_nsr(target_dict, e2e_log)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

def resume_onebox_monitor_old(mydb, ob_data):
    monitor = common_manager.get_ktmonitor()
    if monitor == None:
        log.error("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    nsr_result, nsr_content = orch_dbm.get_nsr_id(mydb, ob_data['nsseq'])
    if nsr_result < 0:
        log.debug("Error getting NSR info from database")
    elif nsr_result == 0:
        log.debug("NSR not found")

    target_dict = {}
    target_dict['server_id'] = ob_data['serverseq']
    target_dict['server_uuid'] = ob_data['serveruuid']
    target_dict['onebox_id'] = ob_data['onebox_id']
    target_dict['server_ip'] = ob_data['mgmtip']

    vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(mydb, vim_id=None, vim_name=None, server_id=ob_data['serverseq'])
    if vim_result <= 0:
        log.error("failed to get vim info of %s: %d %s" %(str(ob_data['serverseq']), vim_result, vim_content))
        return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
    target_dict['vim_auth_url'] = vim_content[0]['authurl']
    target_dict['vim_id'] = vim_content[0]['username']
    target_dict['vim_passwd'] = vim_content[0]['password']
    target_dict['vim_domain'] = vim_content[0]['domain']

    if nsr_result > 0:
        np_result, np_content = orch_dbm.get_nsr_params(mydb, nsr_content['nsseq'])
        if np_result < 0:
            log.error("Failed to get NSR Parameter Info")
            return -HTTP_Internal_Server_Error, "Failed to get NSR Parameter Info for NSR = %s" %str(nsr_content['nsseq'])
        nsr_content['parameters'] = np_content

        target_dict['name'] = nsr_content['name']

        target_vms = []
        for vnf in nsr_content['vnfs']:
            vnf_app_id=None
            vnf_app_passwd=None
            for param in nsr_content['parameters']:
                if param['name'].find("appid_"+vnf['name']) >= 0:
                    vnf_app_id = param['value']
                if param['name'].find("apppasswd_"+vnf['name']) >= 0:
                    vnf_app_passwd = param['value']

            for vm in vnf['vdus']:
                target_vm = {'vm_name':vm['name'], 'vdud_id':vm['vdudseq'], 'vm_vim_name':vm['vim_name'], 'vm_vim_uuid':vm['uuid'], 'monitor_target_seq':vm['monitor_target_seq'],
                             'vm_id':vm['vm_access_id'], 'vm_passwd':vm['vm_access_passwd']}
                if vnf_app_id: target_vm['vm_app_id']=vnf_app_id
                if vnf_app_passwd: target_vm['vm_app_passwd']=vnf_app_passwd

                target_cps = []
                for cp in vm['cps']:
                    target_cp = {'cp_name':cp['name'], 'cp_vim_name':cp['vim_name'], 'cp_vim_uuid':cp['uuid'], 'cp_ip':cp['ip']}
                    target_cps.append(target_cp)
                target_vm['vm_cps']=target_cps

                target_vm['nfsubcategory'] = vnf['nfsubcategory']

                target_vms.append(target_vm)
        target_dict['vms'] = target_vms
    else:
        target_dict['vms'] = []

    result, data = monitor.resume_monitor_onebox(target_dict, None, True)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

def resume_onebox_monitor(mydb, serverseq, e2e_log=None):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    ob_result, ob_data = orch_dbm.get_server_id(mydb, serverseq)
    if ob_result < 0:
        log.error("Failed to get Server Info from DB: %d %s" %(ob_result, ob_data))
        return ob_result, ob_data

    target_dict = {}
    target_dict['server_id'] = ob_data['serverseq']
    target_dict['server_uuid'] = ob_data['serveruuid']
    target_dict['onebox_id'] = ob_data['onebox_id']
    target_dict['server_name'] = ob_data['servername']
    target_dict['server_ip'] = ob_data['mgmtip']
    target_dict['ob_service_number'] = ob_data['ob_service_number']

    vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(mydb, vim_id=None, vim_name=None, server_id=ob_data['serverseq'])
    if vim_result <= 0:
        log.error("failed to get vim info of %s: %d %s" %(str(ob_data['serverseq']), vim_result, vim_content))
        return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
    target_dict['vim_auth_url'] = vim_content[0]['authurl']
    target_dict['vim_id'] = vim_content[0]['username']
    target_dict['vim_passwd'] = vim_content[0]['password']
    target_dict['vim_domain'] = vim_content[0]['domain']
    target_dict['vim_typecod'] = vim_content[0]['vimtypecode']
    target_dict['vim_version'] = vim_content[0]['version']

    target_dict['vim_net']=[]
    vn_result, vn_content = orch_dbm.get_vim_networks(mydb, vim_content[0]['vimseq'])
    if vn_result <= 0:
        log.warning("failed to get vim_net info: %d %s" %(vn_result, vn_content))
    else:
        for vn in vn_content:
            target_dict['vim_net'].append(vn['name'])

    hw_result, hw_content = orch_dbm.get_onebox_hw_serverseq(mydb, ob_data['serverseq'])
    if hw_result <= 0:
        log.warning("failed to get HW info: %d %s" %(hw_result, hw_content))
    else:
        target_dict['hw_model'] = hw_content[0]['model']

    os_result, os_content = orch_dbm.get_onebox_sw_serverseq(mydb, ob_data['serverseq'])
    if os_result <=0:
        log.warning("failed to get OS info: %d %s" %(os_result, os_content))
    else:
        target_dict['os_name'] = os_content[0]['operating_system']

    sn_result, sn_content = orch_dbm.get_onebox_nw_serverseq(mydb, ob_data['serverseq'])
    if sn_result <= 0:
        log.warning("failed to get Server Net info: %d %s" %(sn_result, sn_content))
    else:
        target_dict['svr_net'] = []
        for sn in sn_content:
            target_dict['svr_net'].append({'name':sn['name'], 'display_name':sn['display_name']})

    result, data = monitor.resume_monitor_onebox(target_dict, e2e_log)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

def start_onebox_monitor(mydb, serverseq):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    ob_result, ob_data = orch_dbm.get_server_id(mydb, serverseq)
    if ob_result < 0:
        log.error("Failed to get Server Info from DB: %d %s" %(ob_result, ob_data))
        return ob_result, ob_data

    target_dict = {}
    target_dict['server_id'] = ob_data['serverseq']
    target_dict['server_uuid'] = ob_data['serveruuid']
    target_dict['onebox_id'] = ob_data['onebox_id']
    target_dict['server_name'] = ob_data['servername']
    target_dict['server_ip'] = ob_data['mgmtip']
    target_dict['ob_service_number'] = ob_data['ob_service_number']

    vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(mydb, vim_id=None, vim_name=None, server_id=ob_data['serverseq'])
    if vim_result <= 0:
        log.error("failed to get vim info of %s: %d %s" %(str(ob_data['serverseq']), vim_result, vim_content))
        return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
    target_dict['vim_auth_url'] = vim_content[0]['authurl']
    target_dict['vim_id'] = vim_content[0]['username']
    target_dict['vim_passwd'] = vim_content[0]['password']
    target_dict['vim_domain'] = vim_content[0]['domain']
    target_dict['vim_typecod'] = vim_content[0]['vimtypecode']
    target_dict['vim_version'] = vim_content[0]['version']

    target_dict['vim_net']=[]
    vn_result, vn_content = orch_dbm.get_vim_networks(mydb, vim_content[0]['vimseq'])
    if vn_result <= 0:
        log.warning("failed to get vim_net info: %d %s" %(vn_result, vn_content))
    else:
        for vn in vn_content:
            target_dict['vim_net'].append(vn['name'])

    hw_result, hw_content = orch_dbm.get_onebox_hw_serverseq(mydb, ob_data['serverseq'])
    if hw_result <= 0:
        log.warning("failed to get HW info: %d %s" %(hw_result, hw_content))
    else:
        target_dict['hw_model'] = hw_content[0]['model']

    os_result, os_content = orch_dbm.get_onebox_sw_serverseq(mydb, ob_data['serverseq'])
    if os_result <=0:
        log.warning("failed to get OS info: %d %s" %(os_result, os_content))
    else:
        target_dict['os_name'] = os_content[0]['operating_system']

    sn_result, sn_content = orch_dbm.get_onebox_nw_serverseq(mydb, ob_data['serverseq'])
    if sn_result <= 0:
        log.warning("failed to get Server Net info: %d %s" %(sn_result, sn_content))
    else:
        target_dict['svr_net'] = []
        for sn in sn_content:
            target_dict['svr_net'].append({'name':sn['name'], 'display_name':sn['display_name']})

    result, data = monitor.start_monitor_onebox(target_dict)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

def update_onebox_monitor(mydb, body_dict):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    # ob_result, ob_data = orch_dbm.get_server_id(mydb, serverseq)
    # if ob_result < 0:
    #     log.error("Failed to get Server Info from DB: %d %s" %(ob_result, ob_data))
    #     return ob_result, ob_data
    #
    # target_dict = {}
    # target_dict['server_id'] = ob_data['serverseq']
    # #target_dict['server_uuid'] = ob_data['serveruuid']
    # #target_dict['onebox_id'] = ob_data['onebox_id']
    # #target_dict['server_name'] = ob_data['servername']
    # target_dict['server_ip'] = ob_data['mgmtip']

    #vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(mydb, vim_id=None, vim_name=None, server_id=ob_data['serverseq'])
    #if vim_result <= 0:
    #    log.error("failed to get vim info of %s: %d %s" %(str(ob_data['serverseq']), vim_result, vim_content))
    #    return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
    #target_dict['vim_auth_url'] = vim_content[0]['authurl']
    #target_dict['vim_id'] = vim_content[0]['username']
    #target_dict['vim_passwd'] = vim_content[0]['password']
    #target_dict['vim_domain'] = vim_content[0]['domain']

    result, data = monitor.update_monitor_onebox(body_dict)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

def stop_onebox_monitor(mydb, ob_data):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    target_dict = {}
    target_dict['server_id'] = ob_data['serverseq']
    target_dict['onebox_id'] = ob_data['onebox_id']
    target_dict['server_ip'] = ob_data['mgmtip']
    #target_dict['server_uuid'] = ob_data['serveruuid']
    #target_dict['server_name'] = ob_data['servername']

    result, data = monitor.stop_monitor_onebox(target_dict)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

def first_notify_monitor(mydb, ob_data):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    target_dict = {}
    target_dict['server_id'] = ob_data['serverseq']
    target_dict['onebox_id'] = ob_data['onebox_id']
    target_dict['server_ip'] = ob_data['mgmt_ip']

    result, data = monitor.first_notify_monitor(target_dict)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data

# def need_wan_switch(mydb, filter):
#     log.debug("[HJC] IN with filter: %s" % str(filter))
#     result, content = orch_dbm.get_server_filters(mydb, filter)
#     if result < 0:
#         log.error("Failed to get server Info: %d %s" % (result, content))
#         return result, content
#
#     server_data = content[0]
#     if server_data['net_mode'] is not None and server_data['net_mode'] == "separate":
#         log.debug("[HJC] Don't need to switch WAN for the One-Box of %s Since Mode is SEPARATE" % str(filter))
#         return 200, False
#
#     if server_data['publicip'] is None or server_data['publicip'] == server_data['mgmtip']:
#         log.debug("[HJC] Need to switch WAN for the One-Box of %s" % str(filter))
#         return 200, True
#     else:
#         log.debug("[HJC] Don't need to switch WAN for the One-Box of %s" % str(filter))
#         return 200, False


def new_onebox_account(mydb, account_info):

    if not account_info.get("force", False):

        # 1. DB에 이미 존재하는지 체크
        result, server_account_info = orch_dbm.get_server_account_by_id(mydb, account_info["account_id"])
        if result < 0:
            log.error("Failed to get account info : account_id = %s" % account_info["account_id"])
            return result, server_account_info
        elif result == 0:
            # 아직 등록되지 않은 ID
            pass
        else:
            # 이미 등록된 ID
            return 200, {"code":"DUP_ORCH", "errorMsg":""}

        acc_conn = accountconnector.accountconnector("xms")
        # XMS Server 중복체크
        result, resultCd = acc_conn.view_account(account_info["account_id"])
        log.debug("__________________ view_account %d %s" % (result, resultCd))
        if result < 0:
            log.error("Failed to get XMS Server Account")
            return result, resultCd

        if resultCd.get("ResultCd", "") == "000":
            # 이미 XMS 서버에 등록된 계정인 경우
            return 200, {"code":"DUP_XMS", "errorMsg":""}
        elif resultCd.get("ResultCd", "") == "111":
            # 존재하지 않는 사용자
            pass
        else:
            return -HTTP_Service_Unavailable, resultCd.get("ResultCd", "")

        # XMS 계정 유효성 체크
        result, resultCd = acc_conn.check_validate(account_info["account_id"], account_info["account_pw"])
        log.debug("__________________ check_validate %d %s" % (result, resultCd))
        if result < 0:
            if result == -HTTP_Service_Unavailable:
                log.warning("Warning : Failed to connect XMS Server %d %s" % (result, resultCd))
                description = "Failed to connect XMS Server %d %s" % (result, resultCd)
            else:
                log.warning("Warning : Failed to check valid of xms account - %d %s" % (result, resultCd))
                description = "Failed to check valid of xms account %d %s" % (result, resultCd)
            return result, description

        if resultCd.get("ResultCd", "") != "000":
            return 200, {"code":"INVALID", "errorMsg":resultCd.get("ResultCd", "")}
            # account_info["metadata"] = resultCd.get("ResultCd", "")

    # customerseq 조회
    result, server_data = orch_dbm.get_server_id(mydb, account_info["serverseq"])
    if "customerseq" in server_data:
        account_info["customerseq"] = server_data["customerseq"]

    result, account_seq = orch_dbm.insert_server_account(mydb, account_info)
    log.debug("__________________ insert_server_account %d %s" % (result, account_seq))
    if result < 0:
        log.error("failed to insert an One-Box Account: %d %s" %(result, account_seq))
        return result, account_seq

    return 200, {"code":"OK", "errorMsg":""}

def delete_onebox_account(mydb, onebox_id, is_auto=False):

    result, server = orch_dbm.get_server_id(mydb, onebox_id)
    if result < 0:
        log.error("Failed to get server %d %s" % (result, server))
        return result, server

    # 1.계정사용처 확인
    result, account = orch_dbm.get_server_account(mydb, server["serverseq"])
    if result < 0:
        log.error("Failed to get server account [onebox_id=%s] %d %s" % (server["serverseq"], result, account))

    result, account_use_list = orch_dbm.get_server_account_use(mydb, {"accountseq":account["accountseq"]})
    if result < 0:
        log.error("Failed to get server_account_use [accountseq=%s] %d %s" % (str(account["accountseq"]), result, account_use_list))

    if account_use_list is not None and len(account_use_list) > 0:

        if not is_auto: # 계정삭제 버튼을 클릭했을때는 사용중이 VNF가 있는지 확인해야 한다.

            # 2.XMS VNF 존재 확인
            result, nsr_data = orch_dbm.get_nsr_id(mydb, server["nsseq"])
            if result > 0:
                for vnf in nsr_data["vnfs"]:
                    for account_use in account_use_list:
                        if vnf["name"] == account_use["vnfd_name"] and vnf["version"] == account_use["vnfd_version"]:
                            # 같은 vnf가 존재하면 삭제할 수 없음.
                            log.error("Failed to delete server account")
                            return -HTTP_Internal_Server_Error, "XMS에서 고객 계정 정보를 사용중입니다. XMS VNF를 먼저 삭제하세요."
            else:
                log.debug("Cannot get NSR Info from DB: %d %s" %(result, nsr_data))

        # 3.고객 계정 삭제
        acc_conn = accountconnector.accountconnector("xms")
        for account_use in account_use_list:
            result, resultCd = acc_conn.delete_account(account_use["use_account_id"])
            log.debug("__________________ delete_account %d %s" % (result, resultCd))
            if result < 0:
                log.error("Error : Fail to delete xms account - %d %s" % (result, resultCd))

            if "ResultCd" in resultCd and (resultCd["ResultCd"] == "000" or resultCd["ResultCd"] == "111"): #성공
                pass
            else:
                log.debug("Failed to delete xms account %d %s" % (result, resultCd))
                if not is_auto:
                    return -HTTP_Internal_Server_Error, "[%s], 시스템 관리자 확인 필요" % resultCd["ResultCd"]

    # 4.계정정보 삭제
    result, data = orch_dbm.delete_server_account(mydb, account["accountseq"])
    log.debug("__________________ delete_server_account %d %s" % (result, data))
    if result < 0:
        log.error("Failed to delete tb_server_account %d %s" % (result, data))

    return 200, data


def check_server_account(mydb, account_id, account_pw):
    result, contents = orch_dbm.get_server_account_by_id(mydb, account_id)
    if result < 0:
        return result, contents
    elif result == 0:
        return 200, {"result":"NO_ID"}
    else:
        is_pw_match = False
        for c in contents:
            if account_pw == c.get("account_pw", ""):
                is_pw_match = True
                break

        if is_pw_match:
            rtn_data = {"result":"OK"}
        else:
            rtn_data = {"result":"NOT_PW"}

    return 200, rtn_data


# def _backup_nsr_api(nsr_id):
#     log.debug("[HJC] IN with %s"%(str(nsr_id)))
#
#     global global_config
#
#     headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
#     URLrequest = "https://localhost:9090/orch/nsr/"+str(nsr_id)+"/action"
#     log.debug("Backup request URL: %s" %URLrequest)
#
#     reqDict = {'backup':{'trigger_type':"manual",'nsrId':str(nsr_id),'user':"admin"}}
#
#     payload_req = json.dumps(reqDict)
#     log.debug("Backup request body = %s" %str(payload_req))
#
#     try:
#         ob_response = requests.post(URLrequest, headers = headers_req, data=payload_req, verify=False)
#     except Exception, e:
#         log.exception("failed to backup NSR due to HTTP Error %s" %str(e))
#         return -500, str(e)
#
#     try:
#         log.debug("Response from Orch = %s" %str(ob_response.text))
#         log.debug("Response HTTP Code from Orch = %s" %str(ob_response.status_code))
#         content = ob_response.json()
#     except Exception, e:
#         log.exception("Exception: %s" %str(e))
#         return -HTTP_Internal_Server_Error, 'Invalid Response Body'
#
#     if ob_response.status_code==200:
#         result = 200
#     else:
#         result = -ob_response.status_code, "NOK"
#
#     return result, "OK"


def update_vnf_image_id(mydb, onebox_id, http_content, tid=None, tpath=""):

    """
        vnf imageId가 변경(버젼)되었을 경우 수동으로 RLT의 Parameter값 변경 처리
    :param mydb:
    :param onebox_id:
    :param http_content:
    :param tid:
    :param tpath:
    :return:
    """

    try:
        vnfd_name = http_content.get("vnfd_name", None)
        image_id = http_content.get("image_id", None)
        if vnfd_name is None or image_id is None:
            return -HTTP_Bad_Request, "Parameter is wrong"

        result, onebox_db = orch_dbm.get_server_id(mydb, onebox_id)
        if result < 0:
            log.error("Failed to get server Info: %d %s" % (result, onebox_db))
            return result, onebox_db

        result, rlt_data = orch_dbm.get_rlt_data(mydb, onebox_db["nsseq"])
        if result < 0:
            log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

        rlt_dict = rlt_data["rlt"]

        for param in rlt_dict["parameters"]:

            if param["name"].find("RPARM_imageId_" + vnfd_name) >= 0:
                log.debug("__________ Old image ID : %s, New image ID : %s" % (param["value"], image_id))
                param["value"] = image_id
                break

        result, content = orch_dbm.update_rlt_data(mydb, json.dumps(rlt_dict), rlt_seq=rlt_data["rltseq"])
        if result < 0:
            raise Exception("failed to DB Update for RLT: %d %s" %(result, content))
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "VNF Image ID 변경이 실패하였습니다. 원인: %s" % str(e)
    return 200, "OK"

# def get_server_action_progress(mydb, filter_data):
#     pass


def vnf_image_sync(mydb, server_filter):
    log.debug('[ 버전 정보 동기화 시작 ]')

    select_dict = {}
    select_dict['serverseq'] = server_filter.get('serverseq')
    server_result, server_data = orch_dbm.get_table_data(mydb, select_dict, 'tb_server')
    if server_result < 0:
        log.error("Failed to get server Info: %d %s" % (server_result, server_data))
        return server_result, server_data

    select_dict = {}
    select_dict['nsseq'] = server_data.get('nsseq')
    nfr_result, nfr_data = orch_dbm.get_table_data(mydb, select_dict, 'tb_nfr')
    if nfr_result < 0:
        log.error("Failed to get nfr Info: %d %s" % (nfr_result, nfr_data))
        return nfr_result, nfr_data

    # log.debug('nfr_data = %s' %str(nfr_data))

    nfseq = nfr_data.get('nfseq')
    vdudimageseq = nfr_data.get('vdudimageseq')

    result, content = nfvo.get_vnf_image_version_by_vnfm(mydb, nfseq, server_filter.get('serverseq'))
    if result < 0:
        log.debug('vnf_image_sync : content = %s' %str(content))
        return result, content

    # log.debug('vnf_image_sync > content = %s' %str(content))

    if vdudimageseq == content.get('vdudimageseq'):
        log.debug('#######      버전 정보가 동일합니다.       ##############################')
    else:
        # update start
        # {"update":{"update_dt":"20191219","memo":"","mode":"M"}}
        update_dict = {}
        now = datetime.datetime.now()

        update = {}
        # update['update_dt'] = '20191219'
        update['update_dt'] = now.strftime('%Y%m%d')
        update['memo'] = ''
        update['mode'] = 'M'
        update_dict['update'] = update

        result, content = nfvo.upgrade_vnf_with_image(mydb, nfseq, update_dict['update'], tid=update_dict.get('tid'), tpath=update_dict.get('tpath', ""))
        if result < 0:
            return result, content
        else:
            log.debug('#######      VNF Upgrade Orch 제어 성공      ################################')
            return 200, content


    return 200, "OK"



def test_function(mydb, id):

    return 200, "OK"
    # ssh = None

    # try:
    #     result, server_info = orch_dbm.get_server_id(mydb, id)
    #     log.debug("%s Info : %s" % (id, server_info))
    #
    #     # result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=id)
    #     # if result < 0 or result > 1:
    #     #     log.error("Error. Invalid DB Records for the One-Box Agent: %s" %str(id))
    #     #     raise Exception("Error. Invalid DB Records for the One-Box Agent: %s" %str(id))
    #     #
    #     # ob_agent = ob_agents.values()[0]
    #     # result, content = ob_agent.get_onebox_info(None)
    #     #
    #     # log.debug("CONTENT : %s" % content)
    #     #
    #     #
    #     # if False:
    #     #
    #     #     ssh = paramiko.SSHClient()
    #     #     ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    #     #     ssh.load_system_host_keys()
    #     #     ssh.connect(server_info["publicip"], port=9922)
    #     #
    #     #     # ssh_cmd = "pwd"
    #     #     # stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=60)
    #     #     # output = stdout.readlines()
    #     #     # log.debug("run_ssh_command output= %s" % output)
    #     #
    #     #
    #     #     # ssh_cmd = "cd /home/onebox"
    #     #     # stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=60)
    #     #     # output = stdout.readlines()
    #     #     # log.debug("run_ssh_command output= %s" % output)
    #     #     #
    #     #     # ssh_cmd = "pwd"
    #     #     # stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=60)
    #     #     # output = stdout.readlines()
    #     #     # log.debug("run_ssh_command output= %s" % output)
    #     #
    #     #     ssh_cmd = "tar xvzf /home/onebox/1.2.0_upgrade_patch_test.tar.gz -C /home/onebox/"
    #     #     stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=60)
    #     #     output = stdout.readlines()
    #     #     log.debug("run_ssh_command output= %s" % output)
    #     #
    #     #     ssh_cmd = "python /home/onebox/1.2.0_upgrade_patch/OBP_script_main.py"
    #     #     stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=60)
    #     #     output = stdout.readlines()
    #     #     log.debug("run_ssh_command output= %s" % output)
    #     #
    #     # # 패치 스크립트 실행 결과:
    #     # # 성공 시: 화면 출력 로그 마지막에 '=====Finished Updating One-Box: SUCCESS=====' 표시 됨.
    #     # # 실패 시: 화면 출력 로그 마지막에 '=====Finished Updating One-Box: FAIL=====' 표시 됨.
    #     # # 패치 실행 불가한 경우: 화면 출력 로그에 '====Aborted Updating: ... =====' 표시 됨.
    #     #
    #     #
    #     #
    #     # result, rlt_data = orch_dbm.get_rlt_data(mydb, server_info["nsseq"])
    #     # if result < 0:
    #     #     log.error("Error, failed to get RLT data from DB %d %s" % (result, rlt_data))
    #     #     raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))
    #     #
    #     # rlt_dict = rlt_data["rlt"]
    #     #
    #     # result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
    #     # myvim = vims.values()[0]
    #     #
    #     # result, stack_info = myvim.get_heat_stack_id_v4(rlt_dict["uuid"])
    #     #
    #     # log.debug("@@@@@@@@@@ stack_info = %s" % stack_info)
    #     #
    #     # result, stack_template = myvim.get_heat_stack_template_v4(rlt_dict["uuid"])
    #     #
    #     # log.debug("@@@@@@@@@@ stack_template = %s" % stack_template)
    #
    # except Exception, e:
    #     log.error("##########__________ %s" % str(e))
    # finally:
    #     if ssh is not None:
    #         ssh.close()