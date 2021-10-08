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
__author__ = "Jechan Han"
__date__ = "$05-Nov-2015 22:05:01$"

import json
import yaml
import os
import sys
import time, datetime
import threading
import random
import netaddr
import copy
import requests

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Conflict
import db.orch_db_manager as orch_dbm
from engine.vim_manager import get_vim_connector
from engine.license_manager import update_license, return_license, check_license
from engine.server_manager import new_server, check_onebox_valid, suspend_onebox_monitor, resume_onebox_monitor
from engine.nsr_manager import update_nsr_status, new_nsr_check_customer, new_nsr_check_license, new_nsr_vnf_proc, new_nsr_db_proc, new_nsr_start_monitor
from connectors import goconnector
from connectors import accountconnector
from connectors.haconnector import ssh_connector

from engine.nsr_status import NSRStatus
from engine.action_status import ACTStatus
from engine.server_status import SRVStatus
from engine.nfr_status import NFRStatus
from engine.action_type import ActionType
from engine.image_status import ImageStatus

from utils.e2e_logger import e2elogger, CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
import utils.log_manager as log_manager

log = log_manager.LogManager.get_instance()

from engine.descriptor_manager import compose_nsd_hot, new_nsd_with_vnfs, deploy_vnf_image, get_vdud_image_list_by_vnfd_id
from engine import common_manager

from engine.authkey_manager import AuthKeyDeployManager
import paramiko
from scp import SCPClient

global_config = None

BASE_URL_GIGA_STORAGE = "https://222.106.202.138:8080/platform/1"
BASE_URL_SDN_SWITCH = "http://210.183.241.179:9000/kt/edge"
BASE_URL_GIGA_PC = "http://go.kt.com/v1"
BASE_URL_GIGA_SERVER = "http://go.kt.com/v1"

NWBW_UNIT = 1000  # Kbps


# def rollback(mydb, vims, rollback_list):
#     undeleted_items = []
#     # delete things by reverse order
#     for i in range(len(rollback_list) - 1, -1, -1):
#         item = rollback_list[i]
#         if item["where"] == "vim":
#             if item["vim_id"] not in vims:
#                 continue
#             vim = vims[item["vim_id"]]
#             if item["what"] == "image":
#                 result, message = vim.delete_tenant_image(item["uuid"])
#                 if result < 0:
#                     log.error("Error in rollback. Not possible to delete VIM image '%s'. Message: %s" % (item["uuid"], message))
#                     undeleted_items.append("image %s from VIM %s" % (item["uuid"], vim["name"]))
#                 else:
#                     result, message = mydb.delete_row_by_dict(FROM="datacenters_images",
#                                                               WHERE={"datacenter_id": vim["datacenter_id"], "vim_id": item["uuid"]})
#                     if result < 0:
#                         log.error(
#                             "Error in rollback. Not possible to delete image '%s' from DB.dacenters_images. Message: %s" % (item["uuid"], message))
#             elif item["what"] == "flavor":
#                 result, message = vim.delete_tenant_flavor(item["uuid"])
#                 if result < 0:
#                     log.error("Error in rollback. Not possible to delete VIM flavor '%s'. Message: %s" % (item["uuid"], message))
#                     undeleted_items.append("flavor %s from VIM %s" % (item["uuid"], vim["name"]))
#                 else:
#                     result, message = mydb.delete_row_by_dict(FROM="datacenters_flavos",
#                                                               WHERE={"datacenter_id": vim["datacenter_id"], "vim_id": item["uuid"]})
#                     if result < 0:
#                         log.error(
#                             "Error in rollback. Not possible to delete flavor '%s' from DB.dacenters_flavors. Message: %s" % (item["uuid"], message))
#             elif item["what"] == "network":
#                 result, message = vim.delete_tenant_network(item["uuid"])
#                 if result < 0:
#                     log.error("Error in rollback. Not possible to delete VIM network  '%s'. Message: %s" % (item["uuid"], message))
#                     undeleted_items.append("network %s from VIM %s" % (item["uuid"], vim["name"]))
#             elif item["what"] == "vm":
#                 result, message = vim.delete_tenant_vminstance(item["uuid"])
#                 if result < 0:
#                     log.error("Error in rollback. Not possible to delete VIM VM  '%s'. Message: %s" % (item["uuid"], message))
#                     undeleted_items.append("VM %s from VIM %s" % (item["uuid"], vim["name"]))
#         else:  # where==mano
#             if item["what"] == "image":
#                 result, message = mydb.delete_row_by_dict(FROM="images", WHERE={"uuid": item["uuid"]})
#                 if result < 0:
#                     log.error("Error in rollback. Not possible to delete image '%s' from DB.images. Message: %s" % (item["uuid"], message))
#                     undeleted_items.append("image %s" % (item["uuid"]))
#             elif item["what"] == "flavor":
#                 result, message = mydb.delete_row_by_dict(FROM="flavors", WHERE={"uuid": item["uuid"]})
#                 if result < 0:
#                     log.error("Error in rollback. Not possible to delete flavor '%s' from DB.flavors. Message: %s" % (item["uuid"], message))
#                     undeleted_items.append("flavor %s" % (item["uuid"]))
#     if len(undeleted_items) == 0:
#         return True, " Rollback successful."
#     else:
#         return False, " Rollback fails to delete: " + str(undeleted_items)

def generate_action_tid():
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + str(random.randint(1, 99)).zfill(2)

def _need_wan_switch(mydb, filter):
    #log.debug("[HJC] IN with filter: %s" % str(filter))
    result, content = orch_dbm.get_server_filters(mydb, filter)
    if result < 0:
        log.error("Failed to get server Info: %d %s" % (result, content))
        return result, content

    server_data = content[0]

    log.debug('_need_wan_switch : server_data = %s' %str(server_data))
    
    if server_data['net_mode'] is not None and server_data['net_mode'] == "separate":
        log.debug("[HJC] Don't need to switch WAN for the One-Box of %s Since Mode is SEPARATE" % str(filter))
        return 200, False

    if server_data['publicip'] is None or server_data['publicip'] == server_data['mgmtip']:
        log.debug("[HJC] Need to switch WAN for the One-Box of %s" % str(filter))
        return 200, True
    else:
        log.debug("[HJC] Don't need to switch WAN for the One-Box of %s" % str(filter))
        return 200, False

####################################################    for KT One-Box Service   #############################################    


def _check_server_restoreavailable(server_dict):
    log.debug("[HJC] server status = %s, server action = %s" % (server_dict['status'], server_dict['action']))
    if server_dict['action'] is None or server_dict['action'].endswith("E"):
        pass
    else:
        return -HTTP_Bad_Request, "The One-Box is in Progress for another action: status = %s, action = %s" % (server_dict['status'], server_dict['action'])

    return 200, "OK"


def new_nsr(mydb, nsd_id, instance_scenario_name, instance_scenario_description, customer_id=None, customer_name=None, vim=None, vim_tenant=None
            , startvms=True, params=None, use_thread=True, start_monitor=True, nsr_seq=None, onebox_id = None, vnf_list = [], tid=None, tpath="", bonding=None):

    e2e_log = None

    try:
        log_info_message = "Provisioning NS Started (Name: %s)" % instance_scenario_name
        log.info(log_info_message.center(80, '='))
        # Step 1. Check arguments and initialize variables

        try:
            if not tid:
                e2e_log = e2elogger(tname='NS Provisioning', tmodule='orch-f', tpath="orch_ns-prov")
            else:
                e2e_log = e2elogger(tname='NS Provisioning', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_ns-prov")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('Provisioning 생성 API Call 수신', CONST_TRESULT_SUCC,
                        tmsg_body="NS Name: %s\nParameters: %s" % (str(instance_scenario_name), params))

        # Step 2. Check Customer Info.
        log.debug("[Provisioning][NS] 2. Check Customer and Get VIM ID")
        result, customer_dict = new_nsr_check_customer(mydb, customer_id, onebox_id)
        if result < 0:
            raise Exception("Customer is not ready to provision: %d %s" % (result, customer_dict))

        log.debug("[Provisioning][NS] 2. Success")
        if e2e_log:
            e2e_log.job("Check Customer Info", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 3. Check NS and Params
        log.debug("[Provisioning][NS] 3. Get and Check Scenario (NS) Templates")
        result, scenarioDict = orch_dbm.get_nsd_id(mydb, nsd_id)

        if result < 0:
            log.error("[Provisioning][NS]  : Error, failed to get Scenario Info From DB %d %s" % (result, scenarioDict))
            raise Exception("Failed to get NSD from DB: %d %s" % (result, scenarioDict))
        elif result == 0:
            log.error("[Provisioning][NS]  : Error, No Scenario Found")
            raise Exception("Failed to get NSD from DB: NSD not found")

        # Step 3-1. save service number and service period from Order Manager in RLT
        if len(vnf_list) > 0:
            for vnf in scenarioDict['vnfs']:
                for req_vnf in vnf_list:
                    if req_vnf['vnfd_name'] == vnf['vnfd_name'] and req_vnf['vnfd_version'] == vnf['version'] and vnf.get('service_number') is None:
                        vnf['service_number'] = req_vnf.get('service_number')
                        vnf['service_period'] = req_vnf.get('service_period')
                        break

        log.debug("[Provisioning][NS] 3. Success")
        if e2e_log:
            e2e_log.job("Check NS and Params", CONST_TRESULT_SUCC, tmsg_body=None)

        # check if the requested nsr already exists
        if instance_scenario_name == 'NotGiven':
            if onebox_id is not None:
                instance_scenario_name = "NS-" + onebox_id + "." + scenarioDict['name']
            else:
                instance_scenario_name = "NS-" + customer_dict['customerename'] + "." + scenarioDict['name']

        server_result, server_data = orch_dbm.get_server_id(mydb, customer_dict["server_id"])
        if server_result <= 0:
            raise Exception("Cannot do provisioning : %s" % server_result)
        else:
            if "nsseq" in server_data and server_data["nsseq"] is not None:
                raise Exception("Cannot perform provisioning: NSR already exists : %d" % server_data["nsseq"])

        # check_result, check_data = orch_dbm.get_nsr_id(mydb, instance_scenario_name)
        # if check_result > 0:
        #     raise Exception("Cannot perform provisioning: NSR already exists")


        # 3-2. bonding 구석일 경우, wan list 체크 : 두개 이상일때만 설치 가능
        if bonding is True:
            wan_result, wan_data = orch_dbm.get_server_wan_list(mydb, server_data['serverseq'])

            if wan_result <= 0:
                raise Exception("Cannot do provisioning : %s" % wan_result)
            else:
                if len(wan_data) <= 1:
                    raise Exception("Cannot do provisioning : lack of wan list")


        # 회선 이중화 관련 Parameters 정리 및 resourcetemplate 정리
        if params is not None and params != "":
            wan_dels = _get_wan_dels(params)
            log.debug("_____ get_wan_dels : %s " % wan_dels)
            scenarioDict['parameters'] = common_manager.clean_parameters(scenarioDict['parameters'], wan_dels)
            log.debug("_____ clean_parameters END")
            if scenarioDict['resourcetemplatetype'] == "hot":
                rt_dict = _clean_wan_resourcetemplate(scenarioDict['resourcetemplate'], wan_dels)
                # 정리된 resourcetemplate dictionary 객체를 다시 yaml 포맷 문자열로 변경
                ns_hot_result, ns_hot_value = compose_nsd_hot(scenarioDict['name'], [rt_dict])
                if ns_hot_result < 0:
                    log.error("[Provisioning][NS] Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
                    raise Exception("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
                scenarioDict['resourcetemplate'] = ns_hot_value
                log.debug("_____ clean_resourcetemplate END")

        check_param_result, check_param_data = _new_nsr_check_param(mydb, customer_dict['vim_id'], scenarioDict['parameters'], params)

        if check_param_result < 0:
            raise Exception("Invalid Parameters: %d %s" % (check_param_result, check_param_data))

        # Step 4. Check and Get Available VNF License Key
        log.debug("[Provisioning][NS] 4. Check and Get Available VNF License Key")
        check_license_result, check_license_data = new_nsr_check_license(mydb, scenarioDict['vnfs'])

        if check_license_result < 0:
            raise Exception("Failed to allocate VNF license: %d %s" % (check_license_result, check_license_data))

        log.debug("[Provisioning][NS] 4. Success")
        if e2e_log:
            e2e_log.job("Check and Get Available VNF License Key", CONST_TRESULT_SUCC, tmsg_body="VNF license : %s" % check_license_data)

        # XMS 계정 확인 및 생성 처리
        result, msg = _create_account(mydb, customer_dict['server_id'], scenarioDict["parameters"], e2e_log)
        if result < 0:
            pass

    except Exception, e:
        log.exception("[Provisioning][NS] Exception: %s" % str(e))

        if e2e_log:
            e2e_log.job('API Call 수신 처리 실패', CONST_TRESULT_FAIL,
                        tmsg_body="NS Name: %s\nParameters: %s\nResult:Fail, Cause:%s" % (str(instance_scenario_name), params, str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Bad_Request, "Failed to start Provisioning. Cause: %s" % str(e)

    # Add Following Fields Before Creating RLT 1: customerseq, vimseq, vim_tenant_name
    scenarioDict['customerseq'] = customer_dict['customerseq']
    scenarioDict['vimseq'] = customer_dict['vim_id']
    scenarioDict['vim_tenant_name'] = customer_dict['tenantid']

    update_server_dict = {}
    update_server_dict['serverseq'] = customer_dict['server_id']

    try:
        rollback_list = []

        # Step 5. Review and fill missing fields for DB 'tb_nsr'
        log.debug("[Provisioning][NS] 5. DB Insert: General Info. of the requested NS")

        scenarioDict['status'] = NSRStatus.CRT

        if instance_scenario_description == 'none':
            instance_scenario_description = scenarioDict.get('description', "No Description")
        if 'server_org' in customer_dict:
            scenarioDict['orgnamescode'] = customer_dict['server_org']

        result, nsr_id = orch_dbm.insert_nsr_general_info(mydb, instance_scenario_name, instance_scenario_description, scenarioDict, nsr_seq)

        if result < 0:
            log.error("[Provisioning][NS]  : Error, failed to insert DB records %d %s" % (result, nsr_id))
            raise Exception("Failed to insert DB record for new NSR: %d %s" % (result, nsr_id))

        scenarioDict['nsseq'] = nsr_id
        scenarioDict['serverseq'] = customer_dict['server_id']

        # tb_server에 nsseq 저장.
        result, up_data = orch_dbm.update_server(mydb, {"serverseq":customer_dict['server_id'], "nsseq":nsr_id})
        if result < 0:
            log.error("Failed to update nsr_id of server : %d %s" % (result, up_data))
            raise Exception("Failed to update nsr_id of server")

        update_nsr_status(mydb, ActionType.PROVS, nsr_data=scenarioDict, nsr_status=NSRStatus.CRT_parsing, server_dict=update_server_dict, server_status=SRVStatus.PVS)

        log.debug("[Provisioning][NS] 5. success")

        if e2e_log:
            e2e_log.job("Review and fill missing fields for DB 'tb_nsr'", CONST_TRESULT_SUCC, tmsg_body=None)

        #TODO Replace VNFD Name to VNF Name
        rlt_dict = copy.deepcopy(scenarioDict)
        rlt_dict["name"] = instance_scenario_name

        if bonding is True:
            log.debug('##########   2. bonding 구성 처리   ################')

            # ha 저장
            result, up_data = orch_dbm.update_server(mydb, {"serverseq": customer_dict['server_id'], "ha": "bonding"})
            if result < 0:
                log.error("Failed to update nsr_id of server : %d %s" % (result, up_data))
                raise Exception("Failed to update nsr_id of server")

        if use_thread:
            th = threading.Thread(target=new_nsr_thread, args=(mydb, nsd_id, instance_scenario_name, instance_scenario_description
                                                               , rlt_dict, customer_dict['server_id'], vim_tenant
                                                               , startvms, params, rollback_list, use_thread, start_monitor, e2e_log, bonding))
            th.start()
            return orch_dbm.get_nsr_id(mydb, nsr_id)
        else:
            return new_nsr_thread(mydb, nsd_id, instance_scenario_name, instance_scenario_description
                                  , rlt_dict, customer_dict['server_id'], vim_tenant
                                  , startvms, params, rollback_list, False, start_monitor, e2e_log, bonding)
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=scenarioDict, nsr_status=NSRStatus.ERR, server_dict=update_server_dict, server_status=SRVStatus.ERR)

        if e2e_log:
            e2e_log.job('NS Prov - 전처리', CONST_TRESULT_FAIL,
                        tmsg_body="NS Name: %s\nParameters: %s\nResult:Fail, Cause:%s" % (str(instance_scenario_name), params, str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "NS 설치가 실패하였습니다. 원인: %s" % str(e)



def _update_rlt_data(mydb, rlt_dict, rlt_seq=None, nsseq=None):
    if rlt_seq is None and nsseq is None:
        return -HTTP_Internal_Server_Error, "No Search Key"

    rlt_data = json.dumps(rlt_dict)

    result, rltseq = orch_dbm.update_rlt_data(mydb, rlt_data, rlt_seq=rlt_seq, nsseq=nsseq)
    if result < 0:
        log.error("failed to DB Update RLT: %d %s" %(result, rltseq))

    return result, rltseq

def _update_vnf_status(mydb, action_type, action_dict=None, action_status=None, vnf_data=None, vnf_status=None, action_flag=None):
    try:
        if action_dict and action_status:
            action_dict['status'] = action_status

            if action_status == ACTStatus.FAIL or action_status == ACTStatus.SUCC:
                action_dict['action'] = action_type + "E"  # NGKIM: Use RE for restore
            else:
                action_dict['action'] = action_type + "S"  # NGKIM: Use RE for restore

            if action_flag:
                action_dict['action'] = action_flag

            orch_dbm.insert_action_history(mydb, action_dict)

        if vnf_data and vnf_status:
            vnf_data['status'] = vnf_status

            if vnf_status == NFRStatus.ERR or vnf_status == NFRStatus.RUN or vnf_status == NFRStatus.STOP or vnf_status == NFRStatus.UNKNOWN:
                vnf_data['action'] = action_type + "E"
            else:
                vnf_data['action'] = action_type + "S"

            vnf_data['status_description'] = "Action: %s, Result: %s" % (action_type, vnf_status)
            orch_dbm.update_nsr_vnf(mydb, vnf_data)
    except Exception, e:
        log.exception("Exception: %s" % str(e))

    return 200, "OK"




# def update_nsr(mydb, nsr_id, update_info, use_thread=True):
#     """
#     update_nsr_thread 에서 호출...현재 주석처리되어서 사용안함
#     :param mydb:
#     :param nsr_id:
#     :param update_info:
#     :param use_thread:
#     :return:
#     """
#     # TODO: update public ip
#     if 'publicip' in update_info:
#         #log.debug("[HJC] Update Public IP of NSR %s with %s" % (str(nsr_id), str(update_info['publicip'])))
#         pass
#     else:
#         return -HTTP_Bad_Request, "Not Supported"
#
#     nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr_id)
#     if nsr_result <= 0:
#         log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
#         return -HTTP_Internal_Server_Error, nsr_data
#
#     try:
#         if use_thread:
#             try:
#                 th = threading.Thread(target=_update_nsr_thread, args=(mydb, nsr_data, update_info))
#                 th.start()
#             except Exception, e:
#                 error_msg = "failed to start a thread for updating the NS Instance %s" % str(nsr_id)
#                 log.exception(error_msg)
#                 use_thread = False
#
#         else:
#             return _update_nsr_thread(mydb, nsr_data, update_info)
#     except Exception, e:
#         log.exception("Exception: %s" % str(e))
#         return -HTTP_Internal_Server_Error, "Failed to update NSR: %s" % str(e)
#
#     return 200, "OK"
#
# def _update_nsr_thread(mydb, nsr_data, update_info):
#     """
#     update_nsr 에서 호출...현재 사용안함
#     :param mydb:
#     :param nsr_data:
#     :param update_info:
#     :return:
#     """
#     #log.debug("[HJC] Update request for NSR with %s" % str(update_info))
#
#     if 'publicip' in update_info:
#
#         if update_info.get('old_publicip') is None:
#             log.debug("Old Public IP is Invalid: %s" % str(update_info.get('old_publicip')))
#             return -HTTP_Bad_Request, "Not Valid Old Public IP"
#
#         for vnf in nsr_data['vnfs']:
#             vnf_web_url = vnf.get('web_url')
#             if vnf_web_url:
#                 vnf['web_url'] = vnf['web_url'].replace(update_info['old_publicip'], update_info['publicip'])
#                 log.debug("[HJC] VNF:%s, old web_url: %s, new web_url: %s" % (vnf['name'], vnf_web_url, vnf['web_url']))
#
#             for vm in vnf['vdus']:
#                 vm_web_url = vm.get('web_url')
#                 if vm_web_url:
#                     vm['web_url'] = vm['web_url'].replace(update_info['old_publicip'], update_info['publicip'])
#                     log.debug("[HJC] VM:%s, old web_url: %s, new web_url: %s" % (vm['name'], vm_web_url, vm['web_url']))
#
#                 if 'cps' in vm:
#                     for cp in vm['cps']:
#                         if cp['ip'] == update_info['old_publicip']:
#                             cp['ip'] = update_info['publicip']
#                             #log.debug("[HJC] CP:%s, new IP: %s" % (cp['name'], cp['ip']))
#
#             # TODO: for UTM, update nsr_params and rlt_parameters
#             if vnf['name'].find("UTM") >= 0 or vnf['name'].find("KT-VNF") >= 0:
#                 try:
#                     result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_data["nsseq"])
#                     if result < 0:
#                         log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
#                         raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))
#
#                     rlt_dict = rlt_data["rlt"]
#
#                     for param in rlt_dict['parameters']:
#                         param['value'] = param['value'].replace(update_info['old_publicip'], update_info['publicip'])
#
#                         if param.find("redSubnet") >= 0:
#                             temp_ip_info = netaddr.IPNetwork(update_info['publicip'] + "/24")
#                             param['value'] = str(temp_ip_info.network) + "/24"
#
#                     vnf_list = [vnf['name']]
#
#                     iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_list, rlt_dict['parameters'])
#                     if iparm_result < 0:
#                         raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
#
#                     result, content = orch_dbm.delete_nsr_param(mydb, {"nsseq" : rlt_dict['nsseq']})
#                     if result < 0:
#                         raise Exception("failed to DB Delete of old NSR parameters: %d %s" %(result, content))
#
#                     result, content = orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])
#                     if result < 0:
#                         raise Exception("failed to DB Insert New NSR Params: %d %s" %(result, content))
#
#                     result, content = _update_rlt_data(mydb, rlt_dict, rlt_seq=rlt_data["rltseq"])
#                     if result < 0:
#                         raise Exception("failed to DB Update for RLT: %d %s" %(result, content))
#
#                 except Exception, e:
#                     log.error(str(e))
#
#     result, data = orch_dbm.update_nsr_as_a_whole(mydb, nsr_data['name'], nsr_data['description'], nsr_data)
#     if result < 0:
#         log.error("Failed to update NSR from DB: %d %s" % (result, data))
#         return result, data
#
#     #log.debug("[HJC] Completed to update NSR with %s" % str(update_info))
#     return 200, "OK"



def _new_nsr_check_param(mydb, vim_id, scenarioDict_parameters, params):
    """
    Provision시 필요한 Parameter 값의 유효성 체크
    매개변수 scenarioDict_parameters는 회선 이중화 관련 WAN 사용 정보가 정리된 것(WAN 4개 중 사용하지 않는 것은 제거처리)으로 전제한다.
    :param mydb:
    :param vim_id:
    :param scenarioDict_parameters:
    :param params:
    :return:
    """
    log.debug("[HJC] Params: %s" % str(params))

    if params is None:
        log.error("Failed to NS Provisioning: Parameters are not given")
        return -HTTP_Bad_Request, "Failed to NS Provisioning: Parameters are not given"

    if params == "":
        log.warning("No Parameter Value Given")
        return 200, "OK"

    arg_dict = {}
    arg_list = params.split(';')
    for arg in arg_list:
        arg_dict[arg.split('=')[0]] = arg.split('=')[1]

    for param in scenarioDict_parameters:

        param['value'] = arg_dict.get(param['name'], 'none')

        if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
            if param['value'] == 'none':
                param_desc_list = param['description'].split("__")
                log.debug("[*****HJC*******] Param Desc List: %s" %str(param_desc_list))
                if param_desc_list[0] != "NONE" and param_desc_list[1] != "NONE":
                    error_msg = "No argument for the param: %s %s" % (param['name'], param['category'])
                    log.error("[Provisioning][NS]  : Error, " + error_msg)
                    return -HTTP_Bad_Request, error_msg

            # check image value
            if param['name'].find("imageId") >= 0:
                check_result = False
                log.debug("check the param, %s = %s" % (str(param['name']), str(param['value'])))
                vi_result, vi_content = orch_dbm.get_vim_images(mydb, vim_id)

                if vi_result < 0:
                    error_msg = "Internal Error: Cannot get VIM Image Info %d %s" % (vi_result, str(vi_content))
                    log.error("[Provisioning][NS]  : Error, " + error_msg)
                    return -HTTP_Internal_Server_Error, error_msg

                if af.check_valid_uuid(param['value']):
                    # convert to name
                    for c in vi_content:
                        if c['uuid'] == param['value']:
                            param['value'] = c['vimimagename']
                            log.debug("the param, %s, value is changed to %s" % (str(param['name']), str(param['value'])))
                            check_result = True
                            break
                else:
                    # check if there is vim-image
                    for c in vi_content:
                        if c['vimimagename'] == param['value']:
                            log.debug("found the vim image of name = %s" % str(param['value']))
                            check_result = True
                            break

                if not check_result:
                    error_msg = "Invalid Value for %s: Need Image Name or UUID" % str(param['name'])
                    log.error("[Provisioning][NS]  : Error, " + error_msg)
                    return -HTTP_Bad_Request, error_msg

            if param['name'].find("FixedIp") >= 0:
                log.debug("check the param, %s = %s" % (str(param['name']), str(param['value'])))
                if not af.check_valid_ipv4(param['value']):
                    error_msg = "Invalid Value for %s: Need IPv4 Address" % str(param['name'])
                    log.error("[Provisioning][NS]  : Error, " + error_msg)
                    return -HTTP_Bad_Request, error_msg

        # Check GW IP Validation
        if param['name'].find('CPARM_defaultGw') >= 0 and (param['value'] == 'none' or param['value'] == 'NA'):
            wan_kind = ["R1", "R2", "R3"]
            r_kind = "_"
            for wk in wan_kind:
                if param['name'].find(wk) >= 0:
                    r_kind = wk
                    break

            for ag in arg_list:
                if ag.find("redType" + r_kind) >= 0 and ag.find("STATIC") >= 0:
                    error_msg = "Invalid GW IP Address for WAN: %s - %s" % (param['name'], param['value'])
                    log.error("[Provisioning][NS]  : Error, " + error_msg)
                    return -HTTP_Bad_Request, error_msg
                elif ag.find("redType" + r_kind) >= 0 and ag.find("DHCP") >= 0:
                    log.debug("[Provisioning][NS] Red IP Alloc Type is DHCP")
                    break

    return 200, "OK"



def new_nsr_thread(mydb, nsd_id, instance_scenario_name, instance_scenario_description, rlt_dict, server_id
                   , vim_tenant=None, startvms=True, params=None, rollback_list=[], use_thread=True, start_monitor=True, e2e_log=None, bonding=None):

    update_server_dict = {}
    update_server_dict['serverseq'] = server_id
    update_server_dict['nsseq'] = rlt_dict['nsseq']

    try:
        # Step 6. Get VIM Connector
        log.debug("[Provisioning][NS] 6. Get VIM Connector")
        if use_thread:
            log_info_message = "Provisioning NS - Thread Started (%s)" % instance_scenario_name
            log.info(log_info_message.center(80, '='))

        log.debug("[Provisioning][NS] : Connect to the Target VIM %s" % str(rlt_dict['vimseq']))

        result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
        if result < 0:
            # log.error("[Provisioning][NS]  : Error, failed to connect to VIM")
            raise Exception("Failed to establish a VIM connection: %d %s" % (result, vims))
        elif result > 1:
            # log.error("[Provisioning][NS]  : Error, Several VIMs available, must be identify the target VIM")
            raise Exception("Failed to establish a VIM connection:Several VIMs available, must be identify")

        myvim = vims.values()[0]
        rlt_dict['vim_tenant_name'] = myvim['tenant']
        rlt_dict['vimseq'] = myvim['id']

        log.debug("[Provisioning][NS] 6. Success")
        if e2e_log:
            e2e_log.job("Get VIM Connector", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 7. Compose Arguments for Parameters
        log.debug("[Provisioning][NS] 7. Compose Arguments for Parameters")
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_parsing, server_dict=update_server_dict,
                           server_status=SRVStatus.PVS)

        # cache_nsr_parameters(mydb, server_id, nsd_id, rlt_dict['parameters'])

        vnf_name_list = []
        for vnf in rlt_dict['vnfs']:
            vnf_name_list.append(vnf['name'])

        iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_name_list, rlt_dict['parameters'])
        if iparm_result < 0:
            # log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
            raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))

        template_param_list = []
        for param in rlt_dict['parameters']:
            if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
                template_param_list.append(param)

        log.debug("[Provisioning][NS] 7. Success")

        if e2e_log:
            e2e_log.job("Compose Arguments for Parameters", CONST_TRESULT_SUCC, tmsg_body="template_param_list = %s" % template_param_list)

        # Step 8. Create VMs Using Heat
        log.debug("[Provisioning][NS] 8. Create VMs Using the Heat")
        if e2e_log:
            e2e_log.job("Create VMs Using Heat", CONST_TRESULT_NONE, tmsg_body=None)

        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_creatingvr)

        stack_result, stack_data = _new_nsr_create_vm(myvim, rlt_dict, instance_scenario_name, rlt_dict['resourcetemplatetype'],
                                                      rlt_dict['resourcetemplate'], template_param_list)

        if stack_result < 0:
            if e2e_log:
                e2e_log.job("Create VMs Using Heat", CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to create VMs for VNFs: %d %s" % (stack_result, stack_data))
        else:
            rlt_dict['uuid'] = stack_data

        log.debug("[Provisioning][NS] 8. Success")
        if e2e_log:
            e2e_log.job("Create VMs Using Heat", CONST_TRESULT_SUCC, tmsg_body="Stack UUID : %s" % str(stack_data))

        # Step 9. compose web url for each VDUs and VNF info
        log.debug("[Provisioning][NS] 9. compose web url for each VDUs and VNF info")
        vnf_proc_result, vnf_proc_data = new_nsr_vnf_proc(rlt_dict)
        if vnf_proc_result < 0:
            log.warning("Failed to process vnf app information: %d %s" % (vnf_proc_result, vnf_proc_data))

        if e2e_log:
            e2e_log.job("Compose web url for each VDUs and VNF info", CONST_TRESULT_SUCC, tmsg_body=None)
        log.debug("[Provisioning][NS] 9. Success")

        # Step 10. DB Insert NS Instance
        log.debug("[Provisioning][NS] 10. Insert DB Records for NS Instance")
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_processingdb)

        nsr_db_result, instance_id = new_nsr_db_proc(mydb, rlt_dict, instance_scenario_name, instance_scenario_description)

        if nsr_db_result < 0:
            error_txt = "Failed to insert DB Records %d %s" % (nsr_db_result, str(instance_id))
            # log.error("[Provisioning][NS]  : Error, %s" % error_txt)
            raise Exception(error_txt)

        log.debug("[Provisioning][NS] 10. Success")
        if e2e_log:
            e2e_log.job("DB Insert NS Instance", CONST_TRESULT_SUCC, tmsg_body="NS Instance ID : %s" % instance_id)

        # Step 11. VNF Configuration
        log.debug("[Provisioning][NS] 11. VNF Configuration")
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_configvnf)

        if bonding is True:
            log.debug('##########   3. bonding 구성 처리   ################')

        vnf_confg_result, vnf_config_data = _new_nsr_vnf_conf(mydb, rlt_dict, server_id, e2e_log, bonding)
        if vnf_confg_result < 0:
            # log.error("[Provisioning][NS]   : Error, %d %s" % (vnf_confg_result, vnf_config_data))
            raise Exception("Failed to init-config VNFs: %d %s" % (vnf_confg_result, vnf_config_data))

        log.debug("[Provisioning][NS] 11. Success")
        if e2e_log:
            e2e_log.job("VNF Configuration", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 12. Verify NS Instance
        log.debug("[Provisioning][NS] 12. Test NS Instance")
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_testing)

        res, msg = _new_nsr_test(mydb, server_id, rlt_dict)

        log.debug("[Provisioning][NS]   : Test Result = %d, %s" % (res, msg))
        if res < 0:
            error_txt = "NSR Test Failed %d %s" % (res, str(msg))
            # log.error("[Provisioning][NS]  : Error, %s" % error_txt)
            raise Exception(error_txt)

        log.debug("[Provisioning][NS] 12. Success")
        if e2e_log:
            e2e_log.job("Verify NS Instance", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 13. Setup Monitor for the NS Instance
        log.debug("[Provisioning][NS] 13. Setup Monitor")
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_startingmonitor)

        if start_monitor:
            mon_result, mon_data = new_nsr_start_monitor(mydb, rlt_dict, server_id, e2e_log)
            if mon_result < 0:
                log.warning("[Provisioning][NS]   : Failed %d %s" % (mon_result, mon_data))
                # raise Exception("Failed to setup Monitor for the NS Instance %d %s" % (mon_result, mon_data))
                log.debug("[Provisioning][NS] 13. Failed")
                if e2e_log:
                    e2e_log.job("Setup Monitor for the NS Instance", CONST_TRESULT_FAIL, tmsg_body=None)
            else:
                log.debug("[Provisioning][NS] 13. Success")

                if e2e_log:
                    e2e_log.job("Setup Monitor for the NS Instance", CONST_TRESULT_SUCC, tmsg_body=None)
        # log.debug("[Provisioning][NS] 10. Skip")

        log.debug("[Provisioning][NS] 14. Insert RLT into DB")
        ur_result, ur_data = common_manager.store_rlt_data(mydb, rlt_dict)
        if ur_result < 0:
            # log.error("Failed to insert rlt data: %d %s" %(ur_result, ur_data))
            raise Exception("Failed to insert rlt data: %d %s" %(ur_result, ur_data))
        log.debug("[Provisioning][NS] 14. Success")
        if e2e_log:
            e2e_log.job("RLT - DB Insert", CONST_TRESULT_SUCC, tmsg_body="rlt_dict\n%s" % (json.dumps(rlt_dict, indent=4)))

        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.RUN, server_dict=update_server_dict, server_status=SRVStatus.INS)

        if use_thread:
            log_info_message = "Provisioning NS - Thread Finished (%s) Status = %s" % (str(instance_id), rlt_dict['status'])
        else:
            log_info_message = "Provisioning NS Completed (%s) Status = %s" % (str(instance_id), rlt_dict['status'])
        log.info(log_info_message.center(80, '='))

        if e2e_log:
            e2e_log.job("Provisioning 완료", CONST_TRESULT_SUCC, tmsg_body=None)
            e2e_log.finish(CONST_TRESULT_SUCC)

        return orch_dbm.get_nsr_id(mydb, instance_id)

    except Exception, e:
        if use_thread:
            log_info_message = "Provisioning NS - Thread Finished with Error: Exception [%s] %s" % (str(e), sys.exc_info())
        else:
            log_info_message = "Provisioning NS Failed: Exception [%s] %s" % (str(e), sys.exc_info())
        log.exception(log_info_message.center(80, '='))

        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR, server_dict=update_server_dict, server_status=SRVStatus.ERR,
                           nsr_status_description=str(e))

        if e2e_log:
            e2e_log.job('NS Provisioning 실패', CONST_TRESULT_FAIL,
                        tmsg_body="NS Name: %s\nParameters: %s\nResult:Fail, Cause:%s" % (str(instance_scenario_name), params, str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "NS 설치가 실패하였습니다. 원인: %s" % str(e)


def _new_nsr_create_vm(myvim, rlt_dict, instance_scenario_name, template_type, template, template_params):
    if template is None:
        log.warning("[Provisioning][NS] No Template. Skip Creating VMs")
        return 200, "NOSTACK"

    # extra_wan을 동적할당
    # 프로비져닝 또는 NS 복구시 해당 함수를 태우기때문에 이부분에서 로직을 추가한다.
    # extra_wan을 사용하는 VNF가 있는 경우, br_internet 동적할당을 위해 VNFD에 RPARM_extrawan_VNF parameter를 세팅했다.
    # 현재 라인시점에 값은 template_params 존재한다.
    rt_dict = None
    is_update = False
    for param in template_params:
        if param["name"].find("RPARM_extrawan") >= 0:
            try:
                vnf_name = param["name"].split("_")[2]
                if rt_dict is None:
                    rt_dict = yaml.load(template)
                physical_network = rt_dict["resources"]["PNET_extrawan_" + vnf_name]["properties"]["physical_network"]
                if physical_network != param["value"]:
                    rt_dict["resources"]["PNET_extrawan_" + vnf_name]["properties"]["physical_network"] = param["value"]
                    is_update = True
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
    if is_update:
        ns_hot_result, ns_hot_value = compose_nsd_hot(instance_scenario_name, [rt_dict])
        if ns_hot_result < 0:
            log.error("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
            raise Exception("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
        rlt_dict['resourcetemplate'] = ns_hot_value
        log.debug("_____ [_new_nsr_create_vm > resourcetemplate 재구성] : %s" % ns_hot_value)
        template = ns_hot_value

    # Create Stack using HEAT
    # log.debug('instance_scenario_name = %s' %str(instance_scenario_name))
    # log.debug('template_type = %s' %str(template_type))
    # log.debug('template = %s' %str(template))
    # log.debug('template_params = %s' %str(template_params))

    result, stack_uuid = myvim.new_heat_stack_v4(instance_scenario_name, template_type, template, template_params)

    if result < 0:
        error_txt = "Failed to deploy the NSD %s through Heat. Heat Status =  %s" % (instance_scenario_name, str(stack_uuid))

        heat_result, stack_info = myvim.get_heat_stack_id_v4(instance_scenario_name)
        if heat_result > 0:
            error_txt += " Casue: Failure from VIM"

        log.error("[Provisioning][NS]  : Error, " + error_txt)

        if result == -409:
            pass
        elif stack_uuid is not None and af.check_valid_uuid(stack_uuid):
            rlt_dict['uuid'] = stack_uuid
            log.debug("Heat Error: %s %s" % (rlt_dict['uuid'], stack_uuid))
        else:
            # TODO: rollback heat
            pass
        return result, error_txt

    rlt_dict['uuid'] = stack_uuid
    # Get Resource Info of the Stack
    log.debug("[Provisioning][NS] 6. Get Resource Info of the created Stack")
    # update_nsr_status(mydb, "P", nsr_data=scenarioDict, nsr_status=NSRStatus.CRT_checkingvr)

    result, stack_info = myvim.get_heat_stack_id_v4(stack_uuid)
    if result < 0:
        log.warning("[Provisioning][NS]  : Warning, failed to get Stack Info from the VIM %d %s" % (result, stack_info))
        result, stack_status = myvim.get_heat_stack_statu_v4(stack_uuid)
        if result < 0:
            log.error("[Provisioning][NS]  : Error, failed to check stack status %d %s" % (result, stack_status))
            error_txt = "Cannot get the information about virtual resources from VIM, " + str(stack_status)
            return -HTTP_Internal_Server_Error, error_txt
        elif stack_status == 'CREATE_FAILED':
            log.error("[Provisioning][NS]  : Error, failed to create Heat Stack")
            error_txt = "Failed to create virtual resources through VIM, " + str(stack_status)
            return -HTTP_Internal_Server_Error, error_txt

    result, stack_resources = myvim.get_heat_resource_list_v4(stack_uuid)
    if result < 0:
        log.error("[Provisioning][NS]  : Error, failed to get Resource Info from the VIM %d %s" % (result, stack_resources))
        if result != -HTTP_Not_Found:
            # update status
            error_txt = "Error", "Cannot get the information about virtual resources from VIM, " + str(stack_resources)
            return -HTTP_Internal_Server_Error, error_txt

    _set_stack_data(rlt_dict, stack_resources, stack_info, instance_scenario_name, template_params)

    return 200, stack_uuid


def _set_stack_data(rlt_dict, stack_resources, stack_info, instance_scenario_name, template_params):

    vm_resource_dict = {}
    for resource in stack_resources:
        resource_dict = resource.to_dict()
        if resource_dict['resource_type'] == 'OS::Nova::Server':
            vm_resource_dict[resource_dict['resource_name']] = resource_dict
        if resource_dict['resource_type'] == 'OS::Neutron::Port':
            vm_resource_dict[resource_dict['resource_name']] = resource_dict

    for vnf in rlt_dict['vnfs']:
        if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            log.debug("[HJC] Skip getting CP Info for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
            continue

        vnf['status'] = NFRStatus.CRT
        if 'orgnamescode' in rlt_dict:
            vnf['orgnamescode'] = rlt_dict['orgnamescode']
        for vm in vnf['vdus']:
            # vm['vdudseq'] = vm['vdudseq']
            vm['uuid'] = vm_resource_dict[vm['name']]['physical_resource_id']
            vm['vim_name'] = instance_scenario_name + "-" + vm['name']
            vm['status'] = 'Creating'
            if 'orgnamescode' in rlt_dict:
                vm['orgnamescode'] = rlt_dict['orgnamescode']

            mgmt_ipaddr_key = "ROUT_mgmtIp_" + vnf['name']

            # TODO:DHCP IP
            vm_public_ip = None
            # public_ipaddr_key = "ROUT_publicIp_" + vnf['name']

            for output in stack_info['outputs']:
                # log.debug("output_key = %s, %s: %s" % (output['output_key'], output['output_value'], str(output)))

                if output['output_key'] == mgmt_ipaddr_key:
                    vm['mgmtip'] = output['output_value']
                    break
                # TODO:DHCP IP
                # if output['output_key'] == public_ipaddr_key:
                #     vm_public_ip = output['output_value']
                #     log.debug("[HJC] VM public IP: %s" % vm_public_ip)

            # for param in rlt_dict['parameters']:
            #     if param['name'] == mgmt_ipaddr_key:
            #         param['value'] = vm['mgmtip']
            #     # TODO:DHCP IP
            #     if param['name'] == public_ipaddr_key:
            #         param['value'] = vm_public_ip

            if 'cps' in vm:
                log.debug("[HJC] CP - Update IP: %s" % str(vm['cps']))
                for idx in range(len(vm['cps'])-1, -1, -1):
                    cpd = vm['cps'][idx]
                    if vm_resource_dict.get(cpd['name']) is None:
                        log.debug("Not used CP: %s" %cpd['name'])
                        del vm['cps'][idx]
                        continue

                    cpd['uuid'] = vm_resource_dict[cpd['name']]['physical_resource_id']
                    cpd['vim_name'] = instance_scenario_name + "-" + cpd['name']
                    if cpd['name'].find('mgmt') > 0:
                        cpd['ip'] = vm.get('mgmtip', "None")
                    # TODO:DHCP IP
                    elif cpd['name'].find('red') > 0 and vm_public_ip is not None:
                        cpd['ip'] = vm_public_ip
                        log.debug("[HJC] CP public IP: %s = %s" % (cpd['name'], vm_public_ip))
                    else:
                        target_vdu_name = cpd['name'].split('_')[2]
                        target_vdu_param_name = cpd['name'].split('_')[1]

                        if target_vdu_param_name.find('redR') >= 0:
                            update_target_vdu_param_name = 'redFixedIp' + target_vdu_param_name.split('red')[1]
                            target_vdu_param_name = update_target_vdu_param_name
                        elif target_vdu_param_name.find('red') >= 0:
                            target_vdu_param_name = 'redFixedIp'
                        else:
                            update_target_vdu_param_name = target_vdu_param_name + 'FixedIp'
                            target_vdu_param_name = update_target_vdu_param_name

                        log.debug("[HJC] Target VDU Param Name: %s" %target_vdu_param_name)

                        for param in template_params:
                            if param['name'].split('_')[2] == target_vdu_name:
                                if param['name'].split('_')[1] == target_vdu_param_name:
                                    cpd['ip'] = param['value']
                                    break

# router 이용 OneBox 인 경우 사용되는 함수
def _set_stack_data_remote(rlt_dict, stack_resources, stack_info, instance_scenario_name, template_params, remote_dict):

    vm_resource_dict = {}
    for resource in stack_resources:
        resource_dict = resource.to_dict()
        if resource_dict['resource_type'] == 'OS::Nova::Server':
            vm_resource_dict[resource_dict['resource_name']] = resource_dict
        if resource_dict['resource_type'] == 'OS::Neutron::Port':
            vm_resource_dict[resource_dict['resource_name']] = resource_dict

    for vnf in rlt_dict['vnfs']:
        if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            log.debug("[HJC] Skip getting CP Info for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
            continue

        vnf['status'] = NFRStatus.CRT
        if 'orgnamescode' in rlt_dict:
            vnf['orgnamescode'] = rlt_dict['orgnamescode']
        for vm in vnf['vdus']:
            # vm['vdudseq'] = vm['vdudseq']
            vm['uuid'] = vm_resource_dict[vm['name']]['physical_resource_id']
            vm['vim_name'] = instance_scenario_name + "-" + vm['name']
            vm['status'] = 'Creating'
            if 'orgnamescode' in rlt_dict:
                vm['orgnamescode'] = rlt_dict['orgnamescode']

            mgmt_ipaddr_key = "ROUT_mgmtIp_" + vnf['name']

            # TODO:DHCP IP
            vm_public_ip = None
            # public_ipaddr_key = "ROUT_publicIp_" + vnf['name']

            # if remote_dict is not None:
            #     vm_public_ip = remote_dict.get('public_ip')

            for output in stack_info['outputs']:
                # log.debug("output_key = %s, %s: %s" % (output['output_key'], output['output_value'], str(output)))

                if output['output_key'] == mgmt_ipaddr_key:
                    vm['mgmtip'] = output['output_value']
                    break
                # TODO:DHCP IP
                # if output['output_key'] == public_ipaddr_key:
                #     vm_public_ip = output['output_value']
                #     log.debug("[HJC] VM public IP: %s" % vm_public_ip)

            # for param in rlt_dict['parameters']:
            #     if param['name'] == mgmt_ipaddr_key:
            #         param['value'] = vm['mgmtip']
            #     # TODO:DHCP IP
            #     if param['name'] == public_ipaddr_key:
            #         param['value'] = vm_public_ip

            if 'cps' in vm:
                log.debug("[HJC] CP - Update IP: %s" % str(vm['cps']))
                for idx in range(len(vm['cps'])-1, -1, -1):
                    cpd = vm['cps'][idx]
                    if vm_resource_dict.get(cpd['name']) is None:
                        log.debug("Not used CP: %s" %cpd['name'])
                        del vm['cps'][idx]
                        continue

                    cpd['uuid'] = vm_resource_dict[cpd['name']]['physical_resource_id']
                    cpd['vim_name'] = instance_scenario_name + "-" + cpd['name']
                    if cpd['name'].find('mgmt') > 0:
                        cpd['ip'] = vm.get('mgmtip', "None")
                    # TODO:DHCP IP
                    elif cpd['name'].find('red') > 0 and vm_public_ip is not None:
                        cpd['ip'] = vm_public_ip
                        log.debug("[HJC] CP public IP: %s = %s" % (cpd['name'], vm_public_ip))
                    else:
                        target_vdu_name = cpd['name'].split('_')[2]
                        target_vdu_param_name = cpd['name'].split('_')[1]

                        if target_vdu_param_name.find('redR') >= 0:
                            update_target_vdu_param_name = 'redFixedIp' + target_vdu_param_name.split('red')[1]
                            target_vdu_param_name = update_target_vdu_param_name
                        elif target_vdu_param_name.find('red') >= 0:
                            target_vdu_param_name = 'redFixedIp'
                        else:
                            update_target_vdu_param_name = target_vdu_param_name + 'FixedIp'
                            target_vdu_param_name = update_target_vdu_param_name

                        log.debug("[HJC] Target VDU Param Name: %s" %target_vdu_param_name)

                        for param in template_params:
                            if param['name'].split('_')[2] == target_vdu_name:
                                if param['name'].split('_')[1] == target_vdu_param_name:
                                    cpd['ip'] = param['value']
                                    break

                    # log.debug('[BBG] CP - Update IP: %s' % str(cpd))

                # log.debug('[BBG] remote_dict = %s' %str(remote_dict))
                # log.debug("[HJC] CP END - Update IP: %s" % str(vm['cps']))


def _new_nsr_vnf_prov_GigaOffice(mydb, vnf_dict, server_id, nsr_id, e2e_log=None):
    if vnf_dict is None:
        log.warning("No VNF Info Given")
        return -HTTP_Bad_Request, "No VNF Info"

    #log.debug("[HJC] IN with %s" % str(vnf_dict))
    try:
        if vnf_dict['name'].find("Storage"):
            log.debug("[HJC] GiGA Storage")
            # Get Quota ID
            quota_id = None
            storage_amount = 200 * 1024 * 1024
            p_result, p_content = orch_dbm.get_nsr_params(mydb, nsr_id)
            if p_result > 0:
                for param in p_content:
                    if param['name'].find("quotaid_GiGA-Storage") >= 0:
                        quota_id = param['value']

                    if param['name'].find("capacity_GiGA-Storage") >= 0:
                        storage_amount = param['value']

            # Get GiGA-Storage
            mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_STORAGE)

            if quota_id:
                result, content = mygo.start_storage(storage_amount, quota_id)
            else:
                result, content = mygo.start_storage(storage_amount)

            if result < 0:
                log.error("failed to start GiGA Storage: %d %s" % (result, content))
                return result, content
            '''
            log.debug("[HJC] SDN Switch")
            mygo = goconnector.goconnector("GOName", BASE_URL_SDN_SWITCH)
            result, content = mygo.start_sdnswitch()
            if result < 0:
                log.error("failed to start SDN Switch: %d %s" %(result, content))
                return result, content
            '''
        elif vnf_dict['name'].find("PC"):
            log.debug("[HJC] GiGA PC")
            mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_PC)
            result, content = mygo.start_pc()
            if result < 0:
                log.error("failed to start GiGA PC: %d %s" % (result, content))
                return result, content
        elif vnf_dict['name'].find("Server"):
            log.debug("[HJC] GiGA Server")
            mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_SERVER)
            result, content = mygo.start_server()
            if result < 0:
                log.error("failed to start GiGA Server: %d %s" % (result, content))
                return result, content
        else:
            log.warning("Not supported GiGA-Office Solution")

    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -500, "Exception: %s" % str(e)

    return 200, "OK"

def _new_nsr_vnf_conf(mydb, rlt_dict, server_id, e2e_log=None, bonding=None):

    try:
        rt_dict = load_yaml(rlt_dict["resourcetemplate"])
    except Exception, e:
        return -500, str(e)

    for vnf in rlt_dict['vnfs']:

        if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            log.debug("[HJC] Skip provisioning VNF for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
            try:
                go_result, go_content = _new_nsr_vnf_prov_GigaOffice(mydb, vnf, server_id, rlt_dict['nsseq'], e2e_log)
            except Exception, e:
                log.exception("Exception: %s" % str(e))
                go_result = -HTTP_Internal_Server_Error

            if go_result < 0:
                log.error("[_NEW_NSR_VNF_CONF]   : failed to provision the GiGA Office Solution %s" % (vnf['name']))
        else:
            log.debug("[_NEW_NSR_VNF_CONF]   : %s VNF Provisioning Start" % (vnf['name']))

            if 'vdus' in vnf:
                vdu_list = vnf['vdus']
            else:
                vdu_list = []

            # 2018-03-15 : VNF(UTM) 종류가 늘어남에 따라 vnf 정보(vnfd_version, VNF vendor, WAN구분정보)를 추가적으로 필요로 한다.
            vnf_add_info = {"version":vnf["version"], "vendor":vnf["vendorcode"]}
            wan_list = []

            try:
                serv_main_ports = rt_dict["resources"]["SERV_main_" + vnf["name"]]["properties"]["networks"]
                for port in serv_main_ports:
                    if port["port"]["get_resource"].find("PORT_red") >= 0:
                        port_name = port["port"]["get_resource"]
                        pnet_name = rt_dict["resources"][port_name]["properties"]["network_id"]["get_resource"]
                        physical_network = rt_dict["resources"][pnet_name]["properties"]["physical_network"]
                        if type(physical_network) == str:
                            wan_list.append(physical_network)
                        else:
                            param_name = physical_network["get_param"]
                            for param in rlt_dict['parameters']:
                                if param["name"] == param_name:
                                    log.debug("__________ physical_network >> %s : %s" % (param["name"], param["value"]))
                                    wan_list.append(param["value"])
                                    break
            except Exception, e:
                log.error("Failed to get physnet info of a vnf (%s) : %s" % (vnf["name"], str(e)))
                return -500, str(e)

            vnf_add_info["wan_list"] = wan_list

            if bonding is True:
                log.debug('##########   4. bonding 구성 처리   ################')

            res, content = _prov_vnf_as_a_whole_using_ktvnfm(mydb, server_id, vdu_list, rlt_dict['parameters'], vnf_add_info, e2e_log, bonding=bonding)
            log.debug("[_NEW_NSR_VNF_CONF]   : VNF Provisioning Result = %d, %s" % (res, content))
            if res < 0:
                log.error("[_NEW_NSR_VNF_CONF]   : Error, %d %s" % (res, content))
                _update_vnf_status(mydb, ActionType.PROVS, action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.ERR)

                for vm in vdu_list:
                    vm['status'] = 'Error'
                    orch_dbm.update_nsr_vnfvm(mydb, vm)

                return res, content
            else:
                # TODO: update nsr with VNF IP addresses
                pass
                # if vnf['name'].find("UTM") >= 0 or vnf['name'].find("KT-VNF") >= 0:
                #     old_public_ip = None
                #     new_public_ip = None
                #
                #     for vm in vdu_list:
                #         if 'cps' in vm:
                #             cp_list = vm['cps']
                #         else:
                #             continue
                #
                #         for cpd in cp_list:
                #             if cpd['name'].find('red') > 0:
                #                 old_public_ip = cpd['ip']
                #                 break
                #         if old_public_ip: break
                #
                #     for citem in content:
                #         #log.debug("[HJC] citems = %s" % str(citem))
                #         for c in citem['content']:
                #             #log.debug("[HJC] c = %s" % str(c))
                #             cr_list = c.get('req_result', [])
                #             for cr in cr_list:
                #                 #log.debug("[HJC] cr = %s" % str(cr))
                #                 if cr['name'].find('ROUT_publicIp') >= 0 and (cr['name'].find('UTM') >= 0 or cr['name'].find('KT-VNF') >= 0):
                #                     new_public_ip = cr['value']
                #                     break
                #         if new_public_ip: break
                #
                #     log.debug("[HJC] old_public_ip = %s, new public IP = %s" % (str(old_public_ip), str(new_public_ip)))
                #
                #     if new_public_ip and old_public_ip != new_public_ip:
                #         nsr_update_dict = {'publicip': new_public_ip, 'old_publicip': old_public_ip}
                #         un_result, un_content = update_nsr(mydb, rlt_dict['nsseq'], nsr_update_dict, use_thread=False)
                #         if un_result < 0:
                #             log.warning("Failed to update NSR with %s: %d %s" % (str(nsr_update_dict), un_result, un_content))

    for vnf in rlt_dict['vnfs']:

        _update_vnf_status(mydb, ActionType.PROVS, action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.RUN)
        if 'vdus' in vnf:
            vdu_list = vnf['vdus']
        else:
            continue

        for vm in vdu_list:
            vm['status'] = 'Active'
            try:
                orch_dbm.update_nsr_vnfvm(mydb, vm)
            except Exception, e:
                log.exception("Failed to update VNF VM: %s" %str(e))

    return 200, "OK"


def _update_nsr_vnf_config(mydb, rlt_dict, server_id, add_vnf_names, e2e_log=None):

    try:
        rt_dict = load_yaml(rlt_dict["resourcetemplate"])
    except Exception, e:
        return -500, str(e)

    for vnf in rlt_dict['vnfs']:

        # if UTM, do, else: continue
        if vnf['name'].find("UTM") < 0 and vnf['name'].find("KT-VNF") < 0:
            continue

        # 2018-03-15 : VNF(UTM) 종류가 늘어남에 따라 vnf 정보(vnfd_version, VNF vendor, WAN구분정보)를 추가적으로 필요로 한다.
        vnf_add_info = {"version":vnf["version"], "vendor":vnf["vendorcode"]}
        wan_list = []

        try:
            serv_main_ports = rt_dict["resources"]["SERV_main_" + vnf["name"]]["properties"]["networks"]
            for port in serv_main_ports:
                if port["port"]["get_resource"].find("PORT_red") >= 0:
                    port_name = port["port"]["get_resource"]
                    pnet_name = rt_dict["resources"][port_name]["properties"]["network_id"]["get_resource"]
                    physical_network = rt_dict["resources"][pnet_name]["properties"]["physical_network"]
                    if type(physical_network) == str:
                        wan_list.append(physical_network)
                    else:
                        param_name = physical_network["get_param"]
                        for param in rlt_dict['parameters']:
                            if param["name"] == param_name:
                                log.debug("__________ physical_network >> %s : %s" % (param["name"], param["value"]))
                                wan_list.append(param["value"])
                                break
        except Exception, e:
            log.error("Failed to get physnet info of a vnf (%s) : %s" % (vnf["name"], str(e)))
            return -500, str(e)

        vnf_add_info["wan_list"] = wan_list

        res, content = _update_vnf_as_a_whole_using_ktvnfm(mydb, server_id, vnf['vdus'], rlt_dict['parameters'], vnf_add_info, add_vnf_names, e2e_log)
        log.debug("[NS Update]   : VNF Update Result = %d, %s" % (res, content))

        if res < 0:
            log.error("[NS Update]   : Error, %d %s" % (res, content))
            _update_vnf_status(mydb, ActionType.PROVS, action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.ERR)

            for vm in vnf['vdus']:
                vm['status'] = 'Error'
                try:
                    orch_dbm.update_nsr_vnfvm(mydb, vm)
                except Exception, e:
                    log.exception("Failed to update VNF VM: %s" %str(e))

            return res, content

    return 200, "OK"

# 포트 추가/삭제(nic_modify) 에서 사용했는데, 해당 로직을 Agent에서 처리하기로 함. 삭제대삭
# def _new_wan_vnf_conf(mydb, rlt_dict, serverseq, new_wan_list, e2e_log=None):
#
#     for vnf in rlt_dict['vnfs']:
#         if 'vdus' in vnf:
#             vdu_list = vnf['vdus']
#         else:
#             vdu_list = []
#
#         new_wan_parameters = []
#
#         PARAM_TEMPLATE = ["RPARM_redFixedIp", "RPARM_redFixedMac", "RPARM_redSubnet"
#                     , "CPARM_redCIDR", "CPARM_redType", "CPARM_defaultGw"
#                     , "IPARM_redNetmask", "IPARM_redBroadcast"]
#
#         size = len(rlt_dict['parameters'])
#         for idx in range(size-1, -1, -1):
#             param_name = rlt_dict['parameters'][idx]["name"]
#             is_append = False
#             for new_wan in new_wan_list:
#                 str_R = new_wan["name"]
#                 if str_R == "R0":
#                     str_R = "_"
#                 for tmp in PARAM_TEMPLATE:
#                     if param_name.find(tmp + str_R) >= 0:
#                         new_wan_parameters.append(rlt_dict['parameters'][idx].copy())
#                         is_append = True
#                         break
#                 if is_append:
#                     break
#
#         res, content = _prov_vnf_as_a_whole_using_ktvnfm(mydb, serverseq, vdu_list, new_wan_parameters, e2e_log, mode="ADD")
#         if res < 0:
#             log.error("_prov_vnf_as_a_whole_using_ktvnfm Error, %d %s" % (res, content))
#             _update_vnf_status(mydb, "P", action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.ERR)
#
#             for vm in vdu_list:
#                 vm['status'] = 'Error'
#                 orch_dbm.update_nsr_vnfvm(mydb, vm)
#
#             return res, content
#         else:
#             pass
#
#     for vnf in rlt_dict['vnfs']:
#
#         _update_vnf_status(mydb, "P", action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.RUN)
#         if 'vdus' in vnf:
#             vdu_list = vnf['vdus']
#         else:
#             continue
#
#         for vm in vdu_list:
#             vm['status'] = 'Active'
#             try:
#                 orch_dbm.update_nsr_vnfvm(mydb, vm)
#             except Exception, e:
#                 log.exception("Failed to update VNF VM: %s" %str(e))
#
#     return 200, "OK"

def _new_nsr_test(mydb, server_id, nsr_data):
    entire_result  = 200
    entire_msg = "OK"

    return entire_result, entire_msg
    # TODO: 1. check virtual resources' status

    # TODO: 2. check VNF's internal status
    vnfVmList = []
    for vnf in nsr_data['vnfs']:
        if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            log.debug("[HJC] Skip composing web URL for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
            continue

        if vnf['name'].find("UTM") >= 0 or vnf['name'].find("KT-VNF") >= 0:
            public_ip = None

            # Ping Test
            for vm in vnf['vdus']:
                if 'cps' in vm:
                    cp_list = vm['cps']
                else:
                    continue

                for cpd in cp_list:
                    if cpd['name'].find('red') > 0 > cpd['name'].find('redR'):
                        public_ip = cpd['ip']
                        break

            if public_ip is not None:
                #TODO: ping to UTM WAN
                log.debug("[HJC] Skip PING Test: IP Address = %s" %str(public_ip))
                entire_msg += "\nVNF %s PING Test: SKIP" %vnf['name']
                pass

            # Web Server Test
            if vnf.get('weburl') is not None:
                #TODO: http request to UTM Web
                log.debug("[HJC] WEB Test: URL = %s" %str(vnf.get('weburl')))

                try:
                    weburl_response = requests.get(vnf.get('weburl'), verify=False)

                    if weburl_response.status_code == 401:
                        entire_msg += "\nVNF %s WEB Access: Need Auth Verify" %vnf['name']
                    elif weburl_response.status_code >= 300:
                        entire_result = -HTTP_Internal_Server_Error
                        entire_msg += "\nVNF %s WEB Access: FAILED" %vnf['name']
                    else:
                        entire_msg += "\nVNF %s WEB Access: SUCCEED" %vnf['name']

                except Exception, e:
                    log.exception("failed to access WEB of VNF: %s due to HTTP Error %s" %(vnf['name'], str(e)))
                    entire_result = -HTTP_Internal_Server_Error
                    entire_msg += "\nVNF %s WEB Access: FAILED" %vnf['name']

        for vm in vnf['vdus']:
            # TODO: check and update VM Status
            vnfVmList.append(vm)

    # TODO: 3. check VNFs through VNFM
    vnfVmList = []
    res, msg = _test_vnfs_using_ktvnfm(mydb, server_id, vnfVmList, nsr_data['parameters'])
    log.debug("VNF Test Result = %d, %s" % (res, msg))
    if res < 0:
        log.error("VNF Test Error, %d %s" % (res, msg))
        entire_result = res
        entire_msg += "\n" + msg

    return entire_result, entire_msg


# def cache_nsr_parameters(mydb, server_id, nsd_id, params):
#     try:
#         orch_dbm.delete_nsr_params_cache(mydb, server_id, nsd_id)
#         orch_dbm.insert_nsr_params_cache(mydb, server_id, nsd_id, params)
#
#         return 200, "OK"
#     except Exception, e:
#         log.exception("Exception: %s" % str(e))
#         return -HTTP_Internal_Server_Error, "NS 패러미터 값 저장에 실패하였습니다. 원인: %s" % str(e)


def get_prev_arguments_for_ns(mydb, nsd_id, customer_id):
    try:
        result, customer_dict = orch_dbm.get_customer_id(mydb, customer_id)

        if result < 0:
            log.error("get_prev_arguments_for_ns() Error, failed to get customer info from DB %d %s" % (result, customer_dict))
            return result, customer_dict
        elif result == 0:
            log.error("get_prev_arguments_for_ns() Error, Customer Not Found")
            return -HTTP_Not_Found, customer_dict

        result, customer_inventory = orch_dbm.get_customer_resources(mydb, customer_id)
        # vim_id = None
        server_id = None
        for item in customer_inventory:
            if item['resource_type'] == 'server':
                server_id = item['serverseq']
                # server_orgnamescode = item.get('orgnamescode')
                break

        if server_id:
            param_result, param_content = orch_dbm.get_nsr_params_cache(mydb, server_id, nsd_id)
            if param_result < 0:
                log.error("get_prev_arguments_for_ns() Error, failed to get Param Info from DB")
                return param_result, param_content
            elif param_result == 0:
                log.error("get_prev_arguments_for_ns() No Parameters Found")
                return -HTTP_Not_Found, "No Parameters Found"

            return 200, {"parameters": param_content}
        else:
            return -HTTP_Not_Found, "Server Not found"
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -HTTP_Internal_Server_Error, "NS 패러미터 값 조회에 실패하였습니다. 원인: %s" % str(e)

# def setup_monitor_for_vnfd(mydb, vnfd_dict):
#     monitor = get_ktmonitor()
#     if monitor is None:
#         log.warning("failed to setup montior")
#         return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"
#     target_dict = {}
#     target_dict['name'] = vnfd_dict.get('vnfd_name', vnfd_dict['name'])
#     target_dict['type'] = vnfd_dict['nfsubcategory']
#     target_dict['vendor'] = vnfd_dict['vendorcode']
#     target_dict['version'] = str(vnfd_dict['version'])
#     target_dict['vdus'] = vnfd_dict['vdus']
#
#     result, data = monitor.get_monitor_vnf_target_seq(target_dict)
#
#     if result < 0:
#         log.error("setup_monitor_for_vnfd(): error %d %s" % (result, data))
#
#     return result, data


def stop_nsr_monitor(mydb, nsr_id, e2e_log=None, del_vnfs=None):

    result, nsr_content = orch_dbm.get_nsr_id(mydb, nsr_id)

    if result <= 0:
        return result, nsr_content

    result, customer_resources = orch_dbm.get_customer_resources(mydb, nsr_content['customerseq'])
    if result <= 0:
        return result, customer_resources

    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup montior")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

    server_id = None
    server_uuid = None
    server_ip = None
    server_onebox_id = None
    for resource in customer_resources:
        if resource['resource_type'] == 'server' and str(resource['nsseq']) == str(nsr_id):
            server_id = resource['serverseq']
            server_uuid = resource['serveruuid']
            server_onebox_id = resource['onebox_id']
            server_ip = resource['mgmtip']
            # log.debug("stop_nsr_monitor() serverseq: %d" %server_id)
            break

    if server_id is None:
        return -HTTP_Not_Found, "Cannot find Server Info"

    target_dict = {}
    target_dict['name'] = nsr_content['name']
    target_dict['server_id'] = server_id
    target_dict['server_uuid'] = server_uuid
    target_dict['onebox_id'] = server_onebox_id
    target_dict['server_ip'] = server_ip

    target_vm_list = []
    for vnf in nsr_content['vnfs']:

        # Update NS 에서 del_vnfs 가 있는 경우 처리...
        if del_vnfs is not None and len(del_vnfs) > 0:
            is_pass = False
            for del_vnf in del_vnfs:
                if vnf["vnfd_name"] == del_vnf["vnfd_name"] and vnf["version"] == del_vnf["vnfd_version"]:
                    is_pass = True
                    log.debug("[NS Update] Append VNF[%s %s] to target_vm_list for stopping monitor" % (del_vnf["vnfd_name"], del_vnf["vnfd_version"]))
                    break
            if is_pass:
                pass
            else:
                continue

        for vm in vnf['vdus']:
            target_vm = {'vm_name': vm['name'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid'],
                         'monitor_target_seq': vm['monitor_target_seq']}
            target_vm_list.append(target_vm)

    target_dict['vms'] = target_vm_list

    result, data = monitor.stop_monitor_nsr(target_dict, e2e_log)

    if result < 0:
        log.error("stop_nsr_monitor(): error %d %s" % (result, data))

    return result, data

def resume_nsr_monitor(mydb, server_id, nsr_dict, e2e_log=None):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup montior")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

    target_dict = {}
    target_dict['nsr_name'] = nsr_dict['name']

    server_result, server_data = orch_dbm.get_server_id(mydb, server_id)
    if server_result <= 0:
        log.warning("failed to get server info of %d: %d %s" % (server_id, server_result, server_data))
        return -HTTP_Internal_Server_Error, "Cannot get Server Info from DB"
    target_dict['server_id'] = server_data['serverseq']
    target_dict['server_uuid'] = server_data['serveruuid']
    target_dict['onebox_id'] = server_data['onebox_id']
    target_dict['server_ip'] = server_data['mgmtip']

    vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(mydb, vim_id=None, vim_name=None, server_id=server_data['serverseq'])
    if vim_result <= 0:
        log.error("failed to get vim info of %d: %d %s" % (server_data['serverseq'], vim_result, vim_content))
        return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
    target_dict['vim_auth_url'] = vim_content[0]['authurl']
    target_dict['vim_id'] = vim_content[0]['username']
    target_dict['vim_passwd'] = vim_content[0]['password']
    target_dict['vim_domain'] = vim_content[0]['domain']

    target_vms = []
    for vnf in nsr_dict['vnfs']:
        vnf_app_id = None
        vnf_app_passwd = None
        for param in nsr_dict['parameters']:
            if param['name'].find("appid_" + vnf['name']) >= 0:
                vnf_app_id = param['value']
            if param['name'].find("apppasswd_" + vnf['name']) >= 0:
                vnf_app_passwd = param['value']

        for vm in vnf['vdus']:
            target_vm = {'vm_name': vm['name'], 'vdud_id': vm['vdudseq'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid'],
                         'monitor_target_seq': vm['monitor_target_seq'],
                         'vm_id': vm['vm_access_id'], 'vm_passwd': vm['vm_access_passwd']}
            if vnf_app_id: target_vm['vm_app_id'] = vnf_app_id
            if vnf_app_passwd: target_vm['vm_app_passwd'] = vnf_app_passwd

            target_cps = []
            if 'cps' in vm:
                for cp in vm['cps']:
                    target_cp = {'cp_name': cp['name'], 'cp_vim_name': cp['vim_name'], 'cp_vim_uuid': cp['uuid'], 'cp_ip': cp['ip']}
                    target_cps.append(target_cp)
            target_vm['vm_cps'] = target_cps

            target_vm['nfsubcategory'] = vnf['nfsubcategory']

            target_vms.append(target_vm)
    target_dict['vms'] = target_vms

    result, data = monitor.resume_monitor_nsr(target_dict, e2e_log)

    if result < 0:
        log.error("resume_nsr_monitor(): error %d %s" % (result, data))

    return result, data

def suspend_nsr_monitor(mydb, nsr_content, customer_data, e2e_log=None):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup montior")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

    if customer_data.get('server_id') is None:
        return -HTTP_Not_Found, "Cannot find Server Info"

    target_dict = {}
    target_dict['name'] = nsr_content['name']
    target_dict['server_id'] = customer_data.get('server_id')
    target_dict['server_uuid'] = customer_data.get('server_uuid')
    target_dict['onebox_id'] = customer_data.get('server_onebox_id')
    target_dict['server_ip'] = customer_data.get('server_mgmt_ip')

    target_vm_list = []
    for vnf in nsr_content['vnfs']:
        for vm in vnf['vdus']:
            target_vm = {'vm_name': vm['name'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid'],
                         'monitor_target_seq': vm['monitor_target_seq']}
            target_vm_list.append(target_vm)
    target_dict['vms'] = target_vm_list

    result, data = monitor.suspend_monitor_nsr(target_dict, e2e_log)

    if result < 0:
        log.error("suspend_monitor_nsr(): error %d %s" % (result, data))

    return result, data

def retry_init_config_vnfs(mydb, nsr_id):
    result, data = orch_dbm.get_nsr_id(mydb, nsr_id)

    if result < 0:
        log.error("retry_init_config_vnfs() error failed to get db records for instance %s %s" % (str(nsr_id), data))
        return result, data

    result, customer_inventory = orch_dbm.get_customer_resources(mydb, data['customerseq'])
    server_id = None
    for item in customer_inventory:
        if item['resource_type'] == 'server' and str(item['nsseq']) == str(nsr_id):
            server_id = item['serverseq']
            break

    result, vnf_config_params = orch_dbm.get_nsr_params(mydb, nsr_id)
    if result < 0:
        log.error("failed to get NSR params %d %s" % (result, vnf_config_params))
        return result, vnf_config_params

    data['parameters'] = vnf_config_params

    # res, msg = init_config_vnfs_using_ktvnfm(mydb, server_id, vnfVmList, vnf_config_params)
    res, msg = _new_nsr_vnf_conf(mydb, data, server_id)
    if res < 0:
        log.warning("retry_init_config_vnfs error. %s" % msg)

    return res, msg

# def _compose_nsr_internal_params(vnf_name_list, params):
#     if vnf_name_list is None or params is None:
#         return -HTTP_Internal_Server_Error, "Invaild Parameter List"
#     if len(params) == 0:
#         return 200, "No Params"
#
#     CONST_FIXED_IP = "FixedIp"
#     CONST_CIDR = "CIDR"
#     CONST_NETWORK_ADDR = "NetAddr"
#     CONST_NETMASK = "Netmask"
#     CONST_BROADCAST = "Broadcast"
#     CONST_SUBNET = "Subnet"
#
#     for vnf_name in vnf_name_list:
#
#         for param in params:
#
#             dict_cidr = None
#             dict_netaddr = None
#             dict_netmask = None
#             dict_broadcast = None
#             dict_subnet = None
#
#             if param['name'].find(vnf_name) >= 0 and param['name'].find(CONST_FIXED_IP) >= 0:
#
#                 id_ip = param['name'].split("_")[1].split(CONST_FIXED_IP)[0]
#                 dict_fixedip = param
#
#                 log.debug("[****** HJC *****] Target Param: %s (%s)" %(param['name'], id_ip))
#
#                 wan_kind = "_"+param['name'].split("_")[2]
#                 if id_ip == "red":
#                     if param['name'].find("R1") >= 0:
#                         wan_kind = "R1"
#                     elif param['name'].find("R2") >= 0:
#                         wan_kind = "R2"
#                     elif param['name'].find("R3") >= 0:
#                         wan_kind = "R3"
#
#                 log.debug("[****** HJC *****] Target Param - wan kind: %s (%s)" %(param['name'], wan_kind))
#
#                 for p in params:
#
#                     if p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_CIDR + wan_kind) >= 0:
#                         dict_cidr = p
#                     elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_NETWORK_ADDR + wan_kind) >= 0:
#                         dict_netaddr = p
#                     elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_NETMASK + wan_kind) >= 0:
#                         dict_netmask = p
#                     elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_BROADCAST + wan_kind) >= 0:
#                         dict_broadcast = p
#                     elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_SUBNET + wan_kind) >= 0:
#                         dict_subnet = p
#
#                 try:
#                     if dict_subnet and dict_subnet.get('value', "none").lower() != "none":
#                         log.debug("[****** HJC *****] Subnet Given: %s" %str(dict_subnet))
#                         ip_cal_result = netaddr.IPNetwork(dict_subnet['value'])
#                     elif dict_netmask and dict_netmask.get('value', "none").lower() != "none" :
#                         log.debug("[****** HJC *****] Netmask Given: %s" %str(dict_netmask))
#                         ip_cal_result = netaddr.IPNetwork(dict_fixedip['value']+"/"+dict_netmask['value'])
#                     elif dict_cidr and dict_cidr.get('value', "none").lower() != "none":
#                         log.debug("[****** HJC *****] CIDR Given: %s" %str(dict_cidr))
#                         ip_cal_result = netaddr.IPNetwork(dict_fixedip['value'] + "/" + dict_cidr['value'])
#                     else:
#                         log.debug("No CIDR. Use 24 as a prefix len")
#                         ip_cal_result = netaddr.IPNetwork(dict_fixedip['value'] + "/24")
#
#                     if netaddr.IPAddress(dict_fixedip['value']) in ip_cal_result:
#                         log.debug("Valid IP Address and Network Address: %s for %s" %(str(dict_fixedip['value']), dict_fixedip['name']))
#                     else:
#                         log.debug("InValid IP Address and Network Address: %s for %s" %(str(dict_fixedip['value']), dict_fixedip['name']))
#                         ip_cal_result = netaddr.IPNetwork(dict_fixedip['value'] + "/24")
#
#                     if ip_cal_result:
#                         if dict_cidr:
#                             dict_cidr['value'] = str(ip_cal_result.prefixlen)
#                             log.debug("[****** HJC *****] cidr updated: %s" %str(dict_cidr))
#
#                         if dict_netaddr:
#                             dict_netaddr['value'] = str(ip_cal_result.network)
#                             log.debug("[****** HJC *****] netaddr updated: %s" %str(dict_netaddr))
#
#                         if dict_netmask:
#                             dict_netmask['value'] = str(ip_cal_result.netmask)
#                             log.debug("[****** HJC *****] netmask updated: %s" %str(dict_netmask))
#
#                         if dict_broadcast:
#                             dict_broadcast['value'] = str(ip_cal_result.broadcast)
#                             log.debug("[****** HJC *****] broadcast updated: %s" %str(dict_broadcast))
#
#                         if dict_subnet:
#                             dict_subnet['value'] = str(ip_cal_result.network) + "/" + str(ip_cal_result.prefixlen)
#                             log.debug("[****** HJC *****] subnet updated: %s" %str(dict_subnet))
#
#                 except Exception, e:
#                     log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
#                     return -HTTP_Internal_Server_Error, str(e)
#     return 200, "OK"


def _parse_vnf_vnfm_scritps(vm_dict, config, vnf_config_params=[], mode=None):
    """
    vm 구동을 위해 vnfm에 전달할 스크립트 처리
    :param vm_dict:
    :param config:
    :param vnf_config_params:
    :param mode: One-Box에 새로운 WAN Port가 추가되었을경우 사용하는 옵션. Default : None, 새로 추가된 WAN 해당 스크립트만 처리할 경우 : ADD
    :return:
    """
    req_dict = {}
    config_items = []

    req_dict['type'] = config['type']
    for script in config['scripts']:
        if script['type'] == 'ssh':
            log.debug("[*********HJC*********] script: %s" %str(script))
            valid_script = True
            if 'condition' in script and script['condition'] is not None:
                try:
                    cond_list = script['condition'].split(";")
                    cond_param_name = cond_list[0]
                    cond_condition = cond_list[1]
                    cond_value = cond_list[2]

                    for param in vnf_config_params:
                        if param['name'] == cond_param_name:
                            cond_param_value = param['value']

                            if cond_condition == "eq":
                                if cond_param_value == cond_value:
                                    valid_script = True
                                else:
                                    valid_script = False
                            elif cond_condition == "neq":
                                if cond_param_value != cond_value:
                                    valid_script = True
                                else:
                                    valid_script = False
                            break
                    else:
                        valid_script = False

                except Exception, e:
                        error_msg = "failed to parse condition of the script %s" % str(e)
                        log.exception(error_msg)

            if script['builtinyn'] is False:
                # TODO: transmit Script files to the target onebox VNFM
                script_builtin = False
                script_command = script['name'] + '.sh'
            else:
                script_builtin = True
                script_command = script['body']

            script_args = []
            if script['paramorder'] is not None and len(script['paramorder']) > 0:
                params = script['paramorder'].split(";")
                for param in params:
                    found_argument = False
                    if param.find("PARM_") < 0 and param.find("OUT_") < 0:
                        log.debug("[HJC] Pre-defined Parameter Value: %s" %str(param))
                        script_args.append(param)
                        continue

                    for arg in vnf_config_params:
                        if arg['name'].find(param) >= 0:
                            if arg['value'] is None or arg['value'].lower() == "none":
                                break

                            script_args.append(arg['value'])
                            found_argument = True
                            break

                    if found_argument is False:
                        valid_script = False
                        break
            if script['output'] is not None:
                script_output = script['output'].split(";")
                #log.debug("[HJC] output list = %s" % str(script['output']))

            if valid_script:
                log.debug("[*********HJC*********] add script: %s" %script_command)
                config_items.append({'name': script_command, 'params': script_args, 'builtin': script_builtin, 'output': script_output})
            else:
                log.debug("[*********HJC*********] skip script: %s" %script_command)

        elif script['type'] == 'rest_api':
            try:
                valid_script = True

                # 2018-03-20 : 시용안함. 삭제예정.
                # WAN 이 추가된 경우 get_session, get_auth 는 기본으로 추가되고,
                # 나머지 스크립트 중 새로 추가된 WAN 관련 스크립트만 추가될 수 있도록 처리해야한다.
                # if mode is not None and mode == "ADD":
                #     if script["name"] == "get_session" or script["name"] == "get_auth":
                #         pass
                #     else:
                #         valid_script = False

                if 'condition' in script and script['condition'] is not None:
                    try:
                        cond_list = script['condition'].split(";")
                        cond_param_name = cond_list[0]
                        cond_condition = cond_list[1]
                        cond_value = cond_list[2]

                        for param in vnf_config_params:
                            if param['name'] == cond_param_name:
                                cond_param_value = param['value']

                                if cond_condition == "eq":
                                    if cond_param_value == cond_value:
                                        valid_script = True
                                    else:
                                        valid_script = False
                                elif cond_condition == "neq":
                                    if cond_param_value != cond_value:
                                        valid_script = True
                                    else:
                                        valid_script = False
                                break
                        else:
                            valid_script = False

                    except Exception, e:
                        error_msg = "failed to parse condition of the script %s" % str(e)
                        log.exception(error_msg)

                if valid_script:
                    log.debug("[************HJC*************] [%s] paramorder type = %s, value = %s" %(script['name'], str(type(script['paramorder'])), str(script['paramorder'])))
                    arg_result, arg_list = _compose_arg_list(script['paramorder'], vnf_config_params, vm_dict, config['scripts'])
                    if arg_result < 0:
                        raise Exception(arg_list)
                    script['params'] = arg_list

                    log.debug("[************HJC*************] [%s] requestheaders_args type = %s, value = %s" %(script['name'], str(type(script['requestheaders_args'])), str(script['requestheaders_args'])))
                    arg_result, arg_list = _compose_arg_list(script['requestheaders_args'], vnf_config_params, vm_dict, config['scripts'])
                    if arg_result < 0:
                        raise Exception(arg_list)
                    script['requestheaders_args'] = arg_list

                    log.debug("[************HJC*************] [%s] body_args type = %s, value = %s" %(script['name'], str(type(script['body_args'])), str(script['body_args'])))
                    arg_result, arg_list = _compose_arg_list(script['body_args'], vnf_config_params, vm_dict, config['scripts'])
                    if arg_result < 0:
                        raise Exception(arg_list)
                    script['body_args'] = arg_list

                    arg_result, arg_list = _compose_arg_list(script['cookiedata'], vnf_config_params, vm_dict, config['scripts'])
                    if arg_result < 0:
                        raise Exception(arg_list)
                    script['cookiedata'] = arg_list

                    if script['output'] is not None and len(script['output']) > 0:
                        script['output'] = script['output'].split(";")
                    else:
                        script['output'] = []

                    config_items.append(script)
            except Exception, e:
                error_msg = "failed to compose a script %s" %str(e)
                log.exception(error_msg)

        else:
            error_msg = "Unknown Script Type %s" % script['type']
            log.error(error_msg)
            return -HTTP_Internal_Server_Error, error_msg

    req_dict['scripts'] = config_items
    req_dict['name'] = vm_dict['name'].split("_")[2]
    req_dict['uuid'] = vm_dict['uuid']
    req_dict['mgmtip'] = vm_dict['mgmtip']
    try:
        cp_list = []
        if 'cps' in vm_dict:
            #log.debug("[HJC] check CPs to get local IP of %s" % str(vm_dict['name']))
            cp_list = vm_dict['cps']
        else:
            log.error("error failed to get local IP of %s" % str(vm_dict['name']))

        for cp in cp_list:
            #log.debug("[HJC] check CP: %s" % str(cp))
            if cp['name'].find("blue") >= 0 or cp['name'].find("local") >= 0:
                #log.debug("[HJC] Found the Local IP: %s" % str(cp['ip']))
                req_dict['local_ip'] = cp['ip']

    except Exception, e:
        error_msg = "failed to get local IP of %s " % str(vm_dict['name'])
        log.exception(error_msg)

    req_dict['user'] = vm_dict.get('vm_access_id')
    req_dict['password'] = vm_dict.get('vm_access_passwd')

    return 200, req_dict


def _compose_arg_list(param_string, all_arg_list, vm_dict, all_script_list=None):
    script_args = []

    if param_string and type(param_string) is str and len(param_string) > 0:
        param_list = param_string.split(";")
    elif param_string and type(param_string) is unicode:
        param_value = param_string.encode('ascii','ignore')
        param_list = param_value.split(";")
    elif param_string and type(param_string) is list:
        param_list = param_string
    elif param_string and type(param_string) is not str:
        return -HTTP_Internal_Server_Error, "param_string is not string"
    else:
        #log.debug("No Parameters Given")
        return 200, script_args

    if all_arg_list is None or len(all_arg_list) == 0:
        log.debug("No Arguments Given")
        return 200, script_args

    try:
        for param in param_list:
            if param == "vm_id":
                script_args.append(vm_dict.get('vm_access_id', ""))
                continue
            elif param == "vm_passwd":
                script_args.append(vm_dict.get('vm_access_passwd', ""))
                continue

            arg_found = False

            script_args.append(param)

            for arg in all_arg_list:
                if arg['name'] == param:
                    if arg['value'] is None or arg['value'].lower() == "none":
                        log.debug("Skip Script because Param Name: %s, Value: %s" %(arg['name'], str(arg['value'])))
                    else:
                        script_args.pop()
                        script_args.append(arg['value'])
                        arg_found = True
                    break

            log.debug("*******HJC******* Start Checking output of scripts")
            if all_script_list is not None and len(all_script_list) > 0:
                log.debug("*******HJC******* Loop in")
                for script in all_script_list:
                    log.debug("*******HJC******* Script: %s, %s" %(str(script.get('name')), str(script.get('output'))))
                    if script.get('output'):
                        for output in script['output']:
                            if output == param:
                                log.debug("Found param value at output of the script: %s, %s" %(str(script.get('name')), script['output']))
                                arg_found = True
                                break
                    if arg_found:
                        break

            if arg_found == False:
                return -HTTP_Internal_Server_Error, "failed to find parameter value for %s" %param

    except Exception, e:
        error_msg = "failed to compose args due to exception: %s" % str(e)
        log.exception(error_msg)
        return -HTTP_Internal_Server_Error, error_msg

    return 200, script_args


def _prov_vnf_as_a_whole_using_ktvnfm(mydb, server_id, vnf_vm_list, vnf_config_params=[], vnf_add_info=None, e2e_log=None, mode=None, bonding=None):
    """

    :param mydb:
    :param server_id:
    :param vnf_vm_list: vnf['vdus']
    :param vnf_config_params: rlt_dict['parameters']
    :param vnf_add_info: {"version":vnf["version"], "vendor":vnf["vendorcode"], "wan_list":[]}
    :param e2e_log:
    :param mode: 사용안함.
    :param bonding: bonding 구성 사용여부 1:사용, 0:기본
    :return:
    """

    if vnf_vm_list is None:
        return -1, "No vnf info"

    result, needWanSwitch = _need_wan_switch(mydb, {"serverseq": server_id})

    result, vnfms = common_manager.get_ktvnfm(mydb, server_id)
    if result < 0:
        log.error("Failed to establish a vnfm connection")
        return -HTTP_Not_Found, "No KT VNFM Found"
    elif result > 1:
        log.error("Error, Several vnfms available, must be identify")
        return -HTTP_Bad_Request, "Several vnfms available, must be identify"
    myvnfm = vnfms.values()[0]

    # check if VM is accessible
    # TODO: General Checker
    result, content = myvnfm.check_connection()
    if result < 0:
        log.error(" error in VNFM or cannot connect to VNFM %d %s" % (result, content))
        return result, content
    result_content = []
    for vm in vnf_vm_list:
        vm_content = {'name': vm['name']}  # , 'vduseq': vm['vduseq']}
        vm_content['content'] = []

        init_config_req_dict = None
        get_setting_req_dict = None
        # 1. Parsing VNFM Scripts

        backup_configs = copy.deepcopy(vm['configs'])

        for config in vm['configs']:
            #log.debug("[HJC] VNFD configs = %s" % str(config))
            if config['name'].find("init-config") >= 0:
                parse_result, init_config_req_dict = _parse_vnf_vnfm_scritps(vm, config, vnf_config_params)
                if parse_result < 0:
                    return -HTTP_Internal_Server_Error, "Failed to parse vnf config scripts"
                if vm['name'].find("UTM") >= 0 or vm['name'].find("KT-VNF") >= 0:
                    init_config_req_dict['needWanSwitch'] = needWanSwitch
            elif config['name'].find("get-settings") >= 0:
                parse_result, get_setting_req_dict = _parse_vnf_vnfm_scritps(vm, config, vnf_config_params)
                if parse_result < 0:
                    log.warning("Failed to parse vnf get_setting scripts")
            else:
                log.warning("Not Supported Scripts of %s" % str(config['name']))
        # 2. Init Config
        if init_config_req_dict:
            #log.debug("[Provisioning][NS]     Request: %s" % str(init_config_req_dict))
            req_content = {'req_name': "init-config", 'req_result': []}

            # init_config_req_dict['async_progress']=True
            init_config_req_dict.update(vnf_add_info)
            # if mode is None:

            if bonding is True:
                log.debug('##########   5. bonding 구성 처리   ################')

            res_code, res_msg = myvnfm.init_config_vnf(init_config_req_dict, e2e_log, bonding)
            # else:
            #     res_code, res_msg = myvnfm.update_config_vnf(init_config_req_dict, e2e_log)

            log.debug("[Provisioning][NS]     Request Result: %d, %s" % (res_code, res_msg))
            if res_code < 0:
                log.error("[Provisioning][NS]    failed to configure VNF through VNFM: %s, %s" % (str(res_code), str(res_msg)))
                return res_code, res_msg
            else:
                log.debug("[Provisioning][NS]     Result: OK")
                result = res_code
                req_content['req_result'] = res_msg
                vm_content['content'].append(req_content)

        # 3. Get Settings
        if get_setting_req_dict:
            log.debug("[Provisioning][NS]     Request: %s" % str(get_setting_req_dict))
            req_content = {'req_name': "get-settings", 'req_result': []}

            res_code, res_msg = myvnfm.get_vnf_settings(get_setting_req_dict, e2e_log)
            log.debug("[Provisioning][NS]     Request Result: %d, %s" % (res_code, str(res_msg)))
            if res_code < 0:
                log.warning("[Provisioning][NS]    failed to get VNF Settings from VNFM: %s, %s" % (str(res_code), str(res_msg)))
                # return res_code, res_msg
            else:
                log.debug("[Provisioning][NS]     Result: OK")
                req_content['req_result'] = res_msg
                vm_content['content'].append(req_content)

        result_content.append(vm_content)

        vm['configs'] = backup_configs

    #log.debug("[HJC] OUT: %s" % str(result_content))
    return result, result_content


def _finish_vnf_using_ktvnfm(mydb, server_id, vnf_vm_list, e2e_log=None):
    # log.debug('[BONG] _finish_vnf_using_ktvnfm > vnf_vm_list = %s' %str(vnf_vm_list))

    if vnf_vm_list is None:
        return -1, "No vnf info"

    result, needWanSwitch = _need_wan_switch(mydb, {"serverseq": server_id})

    result, vnfms = common_manager.get_ktvnfm(mydb, server_id)
    if result < 0:
        log.error("Failed to establish a vnfm connection")
        return -HTTP_Not_Found, "No KT VNFM Found"
    elif result > 1:
        log.error("Error, Several vnfms available, must be identify")
        return -HTTP_Bad_Request, "Several vnfms available, must be identify"
    myvnfm = vnfms.values()[0]

    # check if VM is accessible
    # TODO: General Checker
    result, content = myvnfm.check_connection()
    if result < 0:
        log.error(" error in VNFM or cannot connect to VNFM %d %s" % (result, content))
        #TODO: check the status of OB again

        return -HTTP_Not_Found, content

    result_content = []
    for vm in vnf_vm_list:
        # check vm
        if vm.get('uuid') is None or vm.get('mgmtip') is None: #or (vm['name'].find("UTM") < 0 and vm['name'].find("KT-VNF") < 0):
            log.debug("Skip the VMs without a Public IP: %s" % str(vm))
            continue

        vm_content = {'name': vm['name'], 'vduseq': vm['vduseq']}
        vm_content['content'] = []

        req_dict = {}
        req_dict['name'] = vm['name'].split("_")[2]
        req_dict['uuid'] = vm['uuid']
        req_dict['mgmtip'] = vm['mgmtip']
        req_dict['user'] = vm.get('vm_access_id')
        req_dict['password'] = vm.get('vm_access_passwd')
        req_dict['needWanSwitch'] = needWanSwitch

        cp_list = vm.get('cps')
        if cp_list and len(cp_list) > 0:
            for cp in cp_list:
                if cp['name'].find("blue") >= 0 or cp['name'].find("local") >= 0:
                    req_dict['local_ip'] = cp['ip']
        res_code, res_msg = myvnfm.finish_vnf(req_dict, e2e_log)

        if res_code < 0:
            log.error("[Deleting][NS]    failed to finish VNF %s through VNFM: %s, %s" % (vm['name'], str(res_code), str(res_msg)))
            return res_code, res_msg
        else:
            log.debug("[Deleting][NS]    VNF %s Result: OK" % (vm['name']))
            result = res_code

        result_content.append(vm_content)
    #log.debug("[HJC] OUT: %s" % str(result_content))

    return result, result_content


def _update_vnf_as_a_whole_using_ktvnfm(mydb, server_id, vnf_vm_list, vnf_config_params=[], vnf_add_info=None, add_vnf_names=[], e2e_log=None):

    if vnf_vm_list is None:
        return -1, "No vnf info"

    result, needWanSwitch = _need_wan_switch(mydb, {"serverseq": server_id})

    result, vnfms = common_manager.get_ktvnfm(mydb, server_id)
    if result < 0:
        log.error("Failed to establish a vnfm connection")
        return -HTTP_Not_Found, "No KT VNFM Found"
    elif result > 1:
        log.error("Error, Several vnfms available, must be identify")
        return -HTTP_Bad_Request, "Several vnfms available, must be identify"
    myvnfm = vnfms.values()[0]

    # check if VM is accessible
    # TODO: General Checker
    result, content = myvnfm.check_connection()
    if result < 0:
        log.error(" error in VNFM or cannot connect to VNFM %d %s" % (result, content))
        return result, content

    result_content = []
    for vm in vnf_vm_list:

        vm_content = {'name': vm['name']}  # , 'vduseq': vm['vduseq']}
        vm_content['content'] = []

        # 1. Parsing VNFM Scripts
        backup_configs = copy.deepcopy(vm['configs'])
        for config in vm['configs']:
            #log.debug("[HJC] VNFD configs = %s" % str(config))
            update_config_req_dict = None

            for add_vnf_name in add_vnf_names:
                if config['name'].find("update-" + add_vnf_name) >= 0:
                    parse_result, update_config_req_dict = _parse_vnf_vnfm_scritps(vm, config, vnf_config_params)
                    if parse_result < 0:
                        return -HTTP_Internal_Server_Error, "Failed to parse vnf config scripts"
                    if vm['name'].find("UTM") >= 0 or vm['name'].find("KT-VNF") >= 0:
                        update_config_req_dict['needWanSwitch'] = needWanSwitch
                    break

            # 2. Init Config
            if update_config_req_dict:
                if vnf_add_info:
                    update_config_req_dict.update(vnf_add_info)

                res_code, res_msg = myvnfm.update_config_vnf(update_config_req_dict, e2e_log)

                log.debug("[NS Update] Request Result: %d, %s" % (res_code, res_msg))
                if res_code < 0:
                    log.error("[NS Update] failed to configure VNF through VNFM: %s, %s" % (str(res_code), str(res_msg)))
                    return res_code, res_msg
                else:
                    log.debug("[NS Update] Result: OK")
                    result = res_code
                    vm_content['content'].append({'req_name':config['name']})

        result_content.append(vm_content)
        vm['configs'] = backup_configs

    return result, result_content


def _test_vnfs_using_ktvnfm(mydb, server_id, vnfVmList=[], vnf_config_params=[]):
    if vnfVmList is None or len(vnfVmList) == 0:
        return 200, "No vnf info"

    result, vnfms = common_manager.get_ktvnfm(mydb, server_id)
    if result < 0:
        log.error("_test_vnfs_using_ktvnfm() error. vnfm not found")
        return -HTTP_Not_Found, "No KT VNFM Found"
    elif result > 1:
        log.error("_test_vnfs_using_ktvnfm() Several vnfms available, must be identify")
        return -HTTP_Bad_Request, "Several vnfms available, must be identify"
    myvnfm = vnfms.values()[0]

    # check if VM is accessible
    # TODO: General Checker
    result, content = myvnfm.check_connection()

    if result < 0:
        log.error(" error in VNFM or cannot connect to VNFM %d %s" % (result, content))
        return result, content

    for vm in vnfVmList:
        req_dict = {}
        config_items = []

        for config in vm['configs']:
            if config['name'].find("test-script") < 0:
                continue

            req_dict['type'] = config['type']
            for script in config['scripts']:
                if script['type'] == 'ssh':
                    valid_script = True

                    if script['builtinyn'] == False:
                        # TODO: transmit Script files to the target onebox VNFM
                        script_builtin = False
                        script_command = script['name'] + '.sh'
                    else:
                        script_builtin = True
                        script_command = script['body']

                    script_args = []
                    if script['paramorder'] is not None and len(script['paramorder']) > 0:
                        params = script['paramorder'].split(";")
                        for param in params:
                            found_argument = False
                            for arg in vnf_config_params:
                                if arg['name'] == param:
                                    script_args.append(arg['value'])
                                    found_argument = True
                                    break
                            if found_argument == False:
                                valid_script = False
                                break

                    if valid_script: config_items.append({'name': script_command, 'params': script_args, 'builtin': script_builtin})

                elif script['type'] == 'rest_api':
                    script_args = []
                    if script['paramorder'] is not None and len(script['paramorder']) > 0:
                        script['paramorder'] = script['paramorder'].split(";")
                        for param in script['paramorder']:
                            script_args.append(param)
                            for arg in vnf_config_params:
                                if arg['name'] == param:
                                    script_args.pop()
                                    script_args.append(arg['value'])
                                    break
                    script['params'] = script_args
                    if script['cookiedata'] is not None and len(script['cookiedata']) > 0:
                        script['cookiedata'] = script['cookiedata'].split(";")
                    if script['output'] is not None and len(script['output']) > 0:
                        script['output'] = script['output'].split(";")

                    config_items.append(script)

                else:
                    error_msg = "Unknown Script Type %s" % script['type']
                    log.error(error_msg)
                    return -HTTP_Internal_Server_Error, error_msg

            req_dict['scripts'] = config_items
            req_dict['name'] = vm['name'].split("_")[2]
            req_dict['uuid'] = vm['uuid']
            req_dict['mgmtip'] = vm['mgmtip']
            req_dict['user'] = vm.get('vm_access_id')
            req_dict['password'] = vm.get('vm_access_passwd')

            log.debug("[Provisioning][NS]     Request: %s" % str(req_dict))
            res_code, res_msg = myvnfm.test_vnf(req_dict)
            log.debug("[Provisioning][NS]     Request Result: %d, %s" % (res_code, res_msg))
            if res_code < 0:
                log.error("[Provisioning][NS]    failed to test VNF VM: %s, %s" % (str(res_code), str(res_msg)))
                return res_code, res_msg
            else:
                log.debug("[Provisioning][NS]     Result: OK")

    return result, content


def delete_nsr(mydb, nsr_id, need_stop_monitor=True, only_orch=False, use_thread=True, tid=None, tpath="", force_flag = False):

    e2e_log = None
    try:
        try:
            if not tid:
                e2e_log = e2elogger(tname='NS Deleting', tmodule='orch-f', tpath="orch_ns-del")
            else:
                e2e_log = e2elogger(tname='NS Deleting', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_ns-del")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job("NS 종료 API 수신 처리 시작", CONST_TRESULT_SUCC, tmsg_body="NS ID: %s" % (str(nsr_id)))

        # Step 1. get scenario instance from DB
        # log.debug ("Check that the nsr_id exists and getting the instance dictionary")
        result, instanceDict = orch_dbm.get_nsr_id(mydb, nsr_id)
        if result < 0:
            log.error("delete_nsr error. Error getting info from database")
            raise Exception("Failed to get NS Info. from DB: %d %s" % (result, instanceDict))
        elif result == 0:
            log.error("delete_nsr error. Instance not found")
            raise Exception("NSR not found")

        if instanceDict['action'] is None or instanceDict['action'].endswith("E"):
            pass
        else:
            raise Exception("Orch is handling other requests for the instance %s. try later" % nsr_id)

        rollback_list = []  # TODO

        if e2e_log:
            e2e_log.job("Get scenario instance from DB", CONST_TRESULT_SUCC,
                        tmsg_body="Scenario instance Info : %s" % (json.dumps(instanceDict, indent=4)))

        # Step 2. update the status of the scenario instance to 'DELETING'
        server_result, server_content = orch_dbm.get_server_filters(mydb, {"nsseq": instanceDict['nsseq']})
        if server_result <= 0:
            log.warning("failed to get server info %d %s" % (server_result, server_content))
            server_content = None
            raise Exception("Failed to get server info.: %d %s" % (server_result, server_content))
        else:
            server_data = server_content[0]

        if use_thread:
            update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL, server_dict=server_data, server_status=SRVStatus.OOS)

        if e2e_log:
            e2e_log.job("Update the status of the scenario instance to 'DELETING'", CONST_TRESULT_SUCC, tmsg_body=None)

    except Exception, e:
        log.warning("Exception: %s" % str(e))

        if e2e_log:
            e2e_log.job('NS 종료 API 수신 처리 실패', CONST_TRESULT_FAIL, tmsg_body="NS ID: %s" % (str(nsr_id)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)

    try:
        if use_thread:
            try:
                th = threading.Thread(target=_delete_nsr_thread, args=(mydb, instanceDict, server_data, need_stop_monitor, use_thread, force_flag, e2e_log, only_orch))
                th.start()
            except Exception, e:
                error_msg = "failed to start a thread for deleting the NS Instance %s" % str(nsr_id)
                log.exception(error_msg)

                if e2e_log:
                    e2e_log.job('NS 종료 Background Thread 시작', CONST_TRESULT_FAIL, tmsg_body=error_msg)

                use_thread = False

        if use_thread:
            return result, 'OK'
        else:
            return _delete_nsr_thread(mydb, instanceDict, server_data, need_stop_monitor=need_stop_monitor, use_thread=False, force_flag=force_flag, e2e_log=e2e_log, only_orch=only_orch)
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR,
                           nsr_status_description=str(e))

        if e2e_log:
            e2e_log.job('NS 종료', CONST_TRESULT_FAIL, tmsg_body="NS 삭제가 실패하였습니다. 원인: %s" % str(e))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)


def _delete_nsr_thread(mydb, instanceDict, server_data, need_stop_monitor=True, use_thread=True, force_flag=False, e2e_log=None, only_orch=False):
    # Check One-Box connectivity
    onebox_chk_status = server_data['status']
    try:
        ob_chk_result, ob_chk_data = check_onebox_valid(mydb, None, server_data['onebox_id'], True)
        if ob_chk_result < 0:
            log.error("failed to check One-Box Status for %s" % server_data['onebox_id'])
            raise Exception("Failed to check a connection to One-Box")
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        onebox_chk_status = SRVStatus.DSC
        if force_flag is False:
            update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.DSC)
            return -HTTP_Internal_Server_Error, "Failed to check a connection to One-Box"
        #update_nsr_status(mydb, "D", nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR)

    try:
        if use_thread:
            log_info_message = "Deleting NS - Thread Started (%s)" % instanceDict['name']
            log.info(log_info_message.center(80, '='))

            if e2e_log:
                e2e_log.job('NS 종료 Background Thread 시작', CONST_TRESULT_SUCC, tmsg_body=log_info_message)

        if need_stop_monitor:
            if use_thread:
                update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL_stoppingmonitor)

            if e2e_log:
                e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_NONE, tmsg_body="NS 모니터링 종료 요청")

            monitor_result, monitor_response = stop_nsr_monitor(mydb, instanceDict['nsseq'], e2e_log)

            if monitor_result < 0:
                log.error("failed to stop monitor for %d: %d %s" % (instanceDict['nsseq'], monitor_result, str(monitor_response)))
                if e2e_log:
                    e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_FAIL,
                                tmsg_body="NS 모니터링 종료 요청 실패\n원인: %d %s" % (monitor_result, monitor_response))
                    # return monitor_result, monitor_response
            else:
                if e2e_log:
                    e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_SUCC,
                                tmsg_body="NS 모니터링 종료 요청 완료")

        if use_thread:
            update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL_deletingvr)

        # return back license and request to finish VNF
        if not only_orch: # TODO : 제어시스템에서만 삭제하는 조건 추가...
            if onebox_chk_status != SRVStatus.DSC:
                for vnf in instanceDict['vnfs']:
                    if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
                        log.debug("[HJC] Deleting GiGA Office Solution for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
                        try:
                            go_result, go_content = _delete_nsr_GigaOffice(mydb, vnf, server_data['serverseq'], instanceDict['nsseq'], e2e_log)
                        except Exception, e:
                            log.exception("Exception: %s" % str(e))
                            go_result = -HTTP_Internal_Server_Error
                            go_content = None

                        if go_result < 0:
                            log.warning("failed to finish GiGA Office Solution %s: %d %s" % (vnf['name'], go_result, go_content))

                    result, data = return_license(mydb, vnf.get('license'))
                    if result < 0:
                        log.warning("Failed to return license back for VNF %s and License %s" % (vnf['name'], vnf.get('license')))

                    result, data = _finish_vnf_using_ktvnfm(mydb, server_data['serverseq'], vnf['vdus'], e2e_log)

                    if result < 0:
                        log.error("Failed to finish VNF %s: %d %s" % (vnf['name'], result, data))
                        if result == -HTTP_Not_Found:
                            log.debug("One-Box is out of control. Skip finishing VNFs")
                        else:
                            raise Exception("Failed to finish VNF %s: %d %s" % (vnf['name'], result, data))

            # delete heat stack
            if onebox_chk_status != SRVStatus.DSC:
                time.sleep(10)

                result, vims = get_vim_connector(mydb, instanceDict['vimseq'])

                if result < 0:
                    log.error("nfvo.delete_nsr_thread() error. vim not found")
                    log.debug("One-Box is out of control. Skip deleting Heat Stack")
                    #raise Exception("Failed to establish VIM connection: %d %s" % (result, vims))
                else:
                    myvim = vims.values()[0]

                    cc_result, cc_content = myvim.check_connection()
                    if cc_result < 0:
                        log.debug("One-Box is out of control. Skip deleting Heat Stack")
                    else:
                        result, stack_uuid = myvim.delete_heat_stack_v4(instanceDict['uuid'], instanceDict['name'])

                        if result == -HTTP_Not_Found:
                            log.error("Not exists. Just Delete DB Records")
                        elif result < 0:
                            log.error("failed to delete stack from Heat because of " + stack_uuid)

                            if result != -HTTP_Not_Found:
                                raise Exception("failed to delete stack from Heat because of " + stack_uuid)

        result, c = orch_dbm.delete_nsr(mydb, instanceDict['nsseq'])

        if result < 0:
            log.error("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))
            raise Exception("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))

        # backup scheduler 삭제 : backup category = NS
        delete_result, delete_data = common_manager._delete_backup_scheduler(mydb, 'NS', instanceDict['nsseq'])

        server_data.pop('nsseq')
        if use_thread:
            if onebox_chk_status == SRVStatus.DSC:
                update_nsr_status(mydb, ActionType.DELNS, nsr_data=None, nsr_status=None, server_dict=server_data, server_status=SRVStatus.DSC)
            else:
                update_nsr_status(mydb, ActionType.DELNS, nsr_data=None, nsr_status=None, server_dict=server_data, server_status=SRVStatus.RDS)

        if not only_orch:
            # resume_monitor_wan 처리를 명시적으로 해준다.
            result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=server_data['onebox_id'])
            if result < 0:
                log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
                return result, str(ob_agents)

            myoba = ob_agents.values()[0]
            rs_result, rs_content = myoba.resume_monitor_wan()
            if rs_result < 0:
                log.error("Failed to resume monitoring WAN of the One-Box: %d %s" %(rs_result, rs_content))

        if use_thread:
            log_info_message = "Deleting NS - Thread Finished (%s)" % instanceDict['name']
            log.info(log_info_message.center(80, '='))

        if e2e_log:
            e2e_log.job('NS 종료 처리 완료', CONST_TRESULT_SUCC, tmsg_body="NS 종료 처리 완료")
            e2e_log.finish(CONST_TRESULT_SUCC)

        return 1, 'NSR ' + str(instanceDict['nsseq']) + ' deleted'

    except Exception, e:
        if use_thread:
            log_info_message = "Deleting NS - Thread Finished with Error Exception: %s" % str(e)
            log.exception(log_info_message.center(80, '='))
        else:
            log.exception("Exception: %s" % str(e))

        if onebox_chk_status == SRVStatus.DSC:
            update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.DSC)
        else:
            update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR)

        if e2e_log:
            e2e_log.job('NS 종료 처리 실패', CONST_TRESULT_FAIL, tmsg_body=str(e))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)


# def get_nsr_resources(mydb, nsr_id):
#     result, instanceDict = orch_dbm.get_nsr_id(mydb, nsr_id)
#     if result < 0:
#         log.error("nfvo.get_nsr_resources() error. Error getting info from database")
#         return result, instanceDict
#     elif result == 0:
#         log.error("get_nsr_resources() error. Instance not found")
#         return result, instanceDict
#     # log.debug("NSR info: %s" %str(instanceDict))
#
#     result, vims = get_vim_connector(mydb, instanceDict['vimseq'])
#     if result < 0:
#         log.error("nfvo.get_nsr_resources() error. vim not found")
#         return result, vims
#     myvim = vims.values()[0]
#
#     result, res_list = myvim.get_heat_resource_list_v4(instanceDict['uuid'])
#     if result < 0:
#         log.error("failed to get stack resource list from Heat because of " + str(res_list))
#         if result != -HTTP_Not_Found:
#             return result, res_list
#     return result, res_list


def get_nsr_parameters(mydb, nsr_id):
    try:
        result, nsr_param_list = orch_dbm.get_nsr_params(mydb, nsr_id)
        if result < 0:
            log.error("nfvo.get_nsr_parameters() error. Error getting info from database")
            return result, nsr_param_list
        elif result == 0:
            log.error("get_nsr_parameters() error. Instance not found")
            return result, nsr_param_list

        # get vnfd version
        result, ver_list = orch_dbm.get_vnfd_version_list(mydb, nsr_id)

        nsr_params = []
        for param in nsr_param_list:
            if param['name'].find("IPARM_") >= 0 or param['name'].find("ROUT_") >= 0:
                continue

            for ver in ver_list:
                if ver["name"] == param["ownername"]:
                    param["ownerversion"] = ver["version"]
                    break

            nsr_params.append(param)
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "NSR Parameter 조회에 실패하였습니다. 원인: %s" %str(e)

    return 200, nsr_params


def get_vdu_vnc_console_url(mydb, vdu_id):
    try:
        # Step 1. get VDU Info
        vdu_result, vdu_content = orch_dbm.get_vdu_id(mydb, vdu_id)
        if vdu_result < 0:
            log.error("get_vdu_vnc_console_url() error, failed to get the VDU Info %d %s" % (vdu_result, vdu_content))
            return vdu_result, vdu_content

        vdu_vim_uuid = vdu_content['uuid']
        nfr_id = vdu_content['nfseq']

        # Step 2. get VIM Seq.
        nsr_result, nsr_content = orch_dbm.get_nsr_general_info_with_nfr_id(mydb, nfr_id)
        if nsr_result < 0:
            log.error("get_vdu_vnc_console_url() error, failed to get the NSR, VIM info for the VDU")
            return nsr_result, nsr_content

        # Step 3. get VIM Connection
        result, vims = get_vim_connector(mydb, nsr_content['vimseq'])
        if result < 0:
            log.error("get_vdu_vnc_console_url() error, failed to get a VIM connection for the VDU")
            return result, vims
        myvim = vims.values()[0]

        # Step 4. get VNC URL
        result, vnc_url = myvim.get_server_vnc_url_v4(vdu_vim_uuid)
        if result < 0:
            log.error("get_vdu_vnc_console_url() error, get VNC URL from VIM")
            return result, vnc_url
        else:
            data = {}
            data["vdu_seq"] = vdu_content['vduseq']
            data["vdu_name"] = vdu_content["name"]
            data["vdu_uuid"] = vdu_vim_uuid

            # data["nf_seq"] = vdu_content["nfseq"]
            # data["nf_name"] = nsr_content["nf_name"]

            # data["ns_seq"] = nsr_content["nsseq"]
            # data["ns_name"] = nsr_content["ns_name"]

            # {'console': {'url': u'https://127.0.0.1:6080/vnc_auto.html?token=41cba95f-91eb-4999-977e-94f66ec03a99', 'type': 'novnc'}}
            result, servers = orch_dbm.get_server_filters(mydb, {"nsseq":nsr_content["nsseq"]})
            if result > 0:
                mgmt_ip = servers[0]["mgmtip"]
                old_url = vnc_url['console']['url']
                new_url = mgmt_ip
                if old_url.find("://") >= 0:
                    new_url = old_url[0:old_url.index("://")+3] + new_url

                if old_url.find(":", 7) >= 0:
                    new_url += old_url[old_url.index(":", 7):]
            else:
                new_url = vnc_url['console']['url']

            data["vdu_vnc_url"] = new_url
            data["vdu_vnc_type"] = vnc_url['console']['type']
            log.debug("GET_VDU_VNC_CONSOLE_URL : %s" % data)
            return 200, data
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -HTTP_Internal_Server_Error, "VNF VNC 접속 URL 획득에 실패하였습니다. 원인: %s" % str(e)


def get_vnf_vnc_console_url(mydb, vnf_id):
    try:
        # Step 1. get VNF Info
        vnf_result, vnf_content = orch_dbm.get_vnf_id(mydb, vnf_id)
        if vnf_result < 0:
            log.error("get_vnf_vnc_console_url() error, failed to get the VNF Info %d %s" % (vnf_result, vnf_content))
            return vnf_result, vnf_content

        # Step 2. get VIM Seq.
        nsr_result, nsr_content = orch_dbm.get_nsr_general_info_with_nfr_id(mydb, vnf_id)
        if nsr_result < 0:
            log.error("get_vnf_vnc_console_url() error, failed to get the NSR, VIM info for the VDU")
            return nsr_result, nsr_content

        # Step 3. get VIM Connection
        result, vims = get_vim_connector(mydb, nsr_content['vimseq'])
        if result < 0:
            log.error("get_vnf_vnc_console_url() error, failed to get a VIM connection for the VDU")
            return result, vims
        myvim = vims.values()[0]

        # Step 4. get VNC URL
        data = []
        result = 200
        for vdu in vnf_content['vdus']:
            vnc_result, vnc_url = myvim.get_server_vnc_url_v4(vdu['uuid'])
            if vnc_result < 0:
                log.warning("get_vnf_vnc_console_url() error, failed to get VNC URL from VIM")
                data.append({vdu['name']: "error, failed to get VNC URL"})
                result = vnc_result
            else:
                vnc_data = {}
                vnc_data["vdu_seq"] = vdu['vduseq']
                vnc_data["vdu_name"] = vdu["name"]
                vnc_data["vdu_uuid"] = vdu['uuid']

                vnc_data["vdu_vnc_url"] = vnc_url['console']['url']
                vnc_data["vdu_vnc_type"] = vnc_url['console']['type']
                data.append(vnc_data)

        return result, data
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -HTTP_Internal_Server_Error, "VNF VNC 접속 URL 획득에 실패하였습니다. 원인: %s" % str(e)


def get_nsr_vnc_console_url(mydb, nsr):
    return -HTTP_Internal_Server_Error, "Not Supported Yet"


def action_vnf(mydb, vnf_id, type, meta_data='NotGiven', tid=None, tpath=""):

    e2e_log = None
    try:
        try:
            if not tid:
                e2e_log = e2elogger(tname='VNF Action', tmodule='orch-f', tpath="orch_vnf-action")
            else:
                e2e_log = e2elogger(tname='VNF Action', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_vnf-action")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        # Step 1. check request and get VNF Info.
        if type == 'stop' or type == 'start' or type == 'reboot':
            log.debug("Requested Action for the VNF %d: %s" % (vnf_id, type))
            if e2e_log:
                e2e_log.job('VNF Action API Call : Type = %s' % type, CONST_TRESULT_SUCC, tmsg_body="VNF ID: %s" % str(vnf_id))
        else:
            raise Exception("Invalid Action: %d %s" % (-HTTP_Bad_Request, "Invalid Action : %s" % str(type)))
            # return -HTTP_Bad_Request, "Invalid Action: %s" %str(type)

        vnf_result, vnf_content = orch_dbm.get_vnf_id(mydb, vnf_id)
        if vnf_result < 0:
            log.error("action_vnf() error, failed to get the VNF Instance Info from DB")
            raise Exception("Failed to get the VNF Instance Info from DB : %d %s" % (vnf_result, vnf_content))
            # return vnf_result, vnf_content

        # vnf 상태체크
        if (type == 'stop' and vnf_content['status'] != NFRStatus.RUN) \
                or (type == 'start' and vnf_content['status'] != NFRStatus.STOP) \
                or (type == 'reboot' and vnf_content['status'] != NFRStatus.RUN):
            raise Exception("Cannot %s VNF in the status of %s" % (type, vnf_content['status']))
        elif vnf_content['action'] is None or vnf_content['action'].endswith("E"):
            pass
        else:
            raise Exception("The VNF is in Progress for another action: status= %s action= %s" % (vnf_content['status'], vnf_content['action']))

        vdu_list = vnf_content['vdus']

        if e2e_log:
            e2e_log.job("Check request and get VNF Info", CONST_TRESULT_SUCC, tmsg_body="VNF Info: %s" % (json.dumps(vnf_content, indent=4)))

        # Step 2. get VIM Seq.
        nsr_result, nsr_content = orch_dbm.get_nsr_general_info_with_nfr_id(mydb, vnf_id)
        if nsr_result < 0:
            log.error("action_vnf() error, failed to get the NSR, VIM info for the VDU")
            raise Exception("Failed to get the NSR, VIM info for the VDU : %d %s" % (nsr_result, nsr_content))
            # return nsr_result, nsr_content

        if e2e_log:
            e2e_log.job("Get VIM Seq", CONST_TRESULT_SUCC, tmsg_body="VIM Seq : %s" % nsr_content['vimseq'])

        # Step 3. get VIM Connection
        result, vims = get_vim_connector(mydb, nsr_content['vimseq'])
        if result < 0:
            log.error("action_vnf() error, failed to get a VIM connection for the VDU")
            raise Exception("Failed to get a VIM connection for the VDU : %d %s" % (result, vims))
            # return result, vims
        myvim = vims.values()[0]

        if e2e_log:
            e2e_log.job("Get VIM Connection", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 4. get Server Info
        result, needWanSwitch = _need_wan_switch(mydb, {"nsseq": nsr_content["nsseq"]})

        if e2e_log:
            e2e_log.job("Get Server Info", CONST_TRESULT_SUCC, tmsg_body=None)

        # if needWanSwitch and vnf_content['name'].find("UTM") >= 0:
        #    log.error("Not supported for the One-Box with only one Public IP yet")
        #    return -HTTP_Not_Found, "Not supported for the One-Box with only one Public IP yet"

        # Step 5. Stop Monitoring
        # TODO

        # Step 6. do action with VIM
        try:
            th = threading.Thread(target=_action_vdu_thread,
                                  args=(mydb, nsr_content['nsseq'], vdu_list, myvim, type, needWanSwitch, meta_data, nsr_content['vimseq'], e2e_log))
            th.start()
        except Exception, e:
            error_msg = "failed invoke a Thread for doing Action, %s, to VDUs %s: %s" % (type, str(vdu_list), str(e))
            log.exception(error_msg)
            if e2e_log:
                e2e_log.job("VNF Action Thread 시작 실패", CONST_TRESULT_FAIL, tmsg_body=error_msg)
                e2e_log.finish(CONST_TRESULT_FAIL)
            return -HTTP_Internal_Server_Error, error_msg
        return 200, "In the progress"

    except Exception, e:
        log.exception("Exception: %s" % str(e))
        if e2e_log:
            e2e_log.job('VNF Action 종료', CONST_TRESULT_FAIL, tmsg_body="VNF Action[%s]가 실패하였습니다. 원인: %s" % (type, str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, "VNF Action(%s) 실행에 실패하였습니다. 원인: %s" % (str(type), str(e))


def action_vnf_check_license(mydb, vnf_id, license_info):
    try:
        result = check_license(mydb, license_info['license_value'])
        if result:
            return 200, "OK"
        else:
            return 200, "NOK"
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -HTTP_Internal_Server_Error, "VNF Action(%s) 실행에 실패하였습니다. 원인: %s" % (str(type), str(e))


def action_vdu(mydb, vdu_id, type, meta_data='NotGiven', tid=None, tpath=""):

    e2e_log = None
    try:
        try:
            if not tid:
                e2e_log = e2elogger(tname='VNF Action', tmodule='orch-f', tpath="orch_vdu-action")
            else:
                e2e_log = e2elogger(tname='VNF Action', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_vdu-action")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        # Step 1. check Action and get VDU Info.
        if type == 'stop' or type == 'start' or type == 'reboot':
            log.debug("Requested Action for the VNF %s: %s" % (str(vdu_id), type))
        else:
            raise Exception("Invalid Action: %s" % str(type))
            # return -HTTP_Bad_Request, "Invalid Action: %s" % str(type)

        vdu_result, vdu_content = orch_dbm.get_vdu_id(mydb, vdu_id)
        if vdu_result < 0:
            log.error("action_vdu() error, failed to get the VDU Info from DB")
            raise Exception("Failed to get the VDU Info from DB : %s" % vdu_content)
            # return vdu_result, vdu_content

        if e2e_log:
            e2e_log.job('Get the VDU Info from DB', CONST_TRESULT_SUCC, tmsg_body="vdu_content: %s" % vdu_content)

        vdu_list = [vdu_content]
        # vdu_seq = vdu_content['vduseq']
        # vdu_vim_uuid = vdu_content['uuid']
        # vdu_name = vdu_content['name']
        nfr_id = vdu_content['nfseq']

        # vnf 상태체크
        vnf_result, vnf_content = orch_dbm.get_vnf_id(mydb, nfr_id)
        if vnf_result < 0:
            log.error("action_vnf() error, failed to get the VNF Instance Info from DB")
            raise Exception("Failed to get the VNF Instance Info from DB : %d %s" % (vnf_result, vnf_content))

        if (type == 'stop' and (vnf_content['status'] != NFRStatus.RUN and vnf_content['status'] != NFRStatus.UNKNOWN)) \
                or (type == 'start' and (vnf_content['status'] != NFRStatus.STOP and vnf_content['status'] != NFRStatus.UNKNOWN)) \
                or (type == 'reboot' and vnf_content['status'] != NFRStatus.RUN):
            raise Exception("Cannot %s VNF in the status of %s" % (type, vnf_content['status']))
        elif vnf_content['action'] is None or vnf_content['action'].endswith("E"):
            pass
        else:
            raise Exception("The VNF is in Progress for another action: status= %s action= %s" % (vnf_content['status'], vnf_content['action']))

        # Step 2. get VIM Seq.
        nsr_result, nsr_content = orch_dbm.get_nsr_general_info_with_nfr_id(mydb, nfr_id)
        if nsr_result < 0:
            log.error("action_vdu() error, failed to get the NSR, VIM info for the VDU")
            raise Exception("Failed to get the NSR, VIM info for the VDU : %s" % nsr_content)
            # return nsr_result, nsr_content

        if e2e_log:
            e2e_log.job('Get the NSR, VIM info for the VDU', CONST_TRESULT_SUCC, tmsg_body="nsr_content: %s" % nsr_content)

        # Step 3. get VIM Connection
        # Check Server Status
        svr_result, svr_data = orch_dbm.get_server_filters(mydb, {'nsseq': nsr_content['nsseq']})
        if svr_result <= 0:
            log.error("failed to get server info for NSR: %s" %str(nsr_content['nsseq']))
            raise Exception("action_vdu() error, failed to get One-Box Info. from DB")
        else:
            if svr_data[0].get('status') == SRVStatus.DSC:
                raise Exception("Cannot %s VNF since One-Box is not connected." % (type))

        result, vims = get_vim_connector(mydb, nsr_content['vimseq'])
        if result < 0:
            log.error("action_vdu() error, failed to get a VIM connection for the VDU")
            raise Exception("Failed to get a VIM connection for the VDU : %s" % vims)
            # return result, vims
        myvim = vims.values()[0]

        # result_data = {"vdu_id": vdu_seq, "vdu_name": vdu_name, "vdu_uuid": vdu_vim_uuid, "action": type}

        if e2e_log:
            e2e_log.job('Get VIM Connection', CONST_TRESULT_SUCC, tmsg_body="")

        # Step 4. get Server Info
        result, needWanSwitch = _need_wan_switch(mydb, {"nsseq": nsr_content["nsseq"]})

        if e2e_log:
            e2e_log.job('Get Server Info', CONST_TRESULT_SUCC, tmsg_body="needWanSwitch : %s" % needWanSwitch)

        # if needWanSwitch and vdu_name.find("UTM") >= 0:
        #    log.error("Not supported for the One-Box with only one Public IP yet")
        #    return -HTTP_Not_Found, "Not supported for the One-Box with only one Public IP yet"

        # Step 5. Stop Monitoring
        # TODO

        # Step 6. do action with VIM
        try:
            th = threading.Thread(target=_action_vdu_thread, args=(mydb, nsr_content['nsseq'], vdu_list, myvim, type, needWanSwitch, meta_data, nfr_id, nsr_content['vimseq'], e2e_log))
            th.start()
        except Exception, e:
            error_msg = "failed invoke a Thread for doing Action, %s, to VDUs %s: %s" % (type, str(vdu_list), str(e))
            log.exception(error_msg)
            if e2e_log:
                e2e_log.job('Thread for doing Action 실패', CONST_TRESULT_FAIL, tmsg_body=error_msg)
                e2e_log.finish(CONST_TRESULT_FAIL)
            return -HTTP_Internal_Server_Error, error_msg

        return 200, "In the progress"

    except Exception, e:
        log.exception("Exception: %s" % str(e))
        if e2e_log:
            e2e_log.job('VNF Action 실패', CONST_TRESULT_FAIL, tmsg_body="VNF Action Failed. Cause: %s" % str(e))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, "VDU Action(%s) 실행에 실패하였습니다. 원인: %s" % (str(type), str(e))

def _action_vdu_thread(mydb, nsr_id, vdu_list, myvim, type, needWanSwitch, meta_data, nfr_id, vimseq, e2e_log=None):

    vnf_dict = {"nfseq":nfr_id}
    is_succ = True
    result = 200
    try:
        if e2e_log:
            e2e_log.job('VNF Action Thread 시작 [%s]' % type, CONST_TRESULT_SUCC, tmsg_body=None)

        if type == 'stop':
            _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=NFRStatus.STOP_ing)
            for vdu in vdu_list:
                result, content = _action_vdu_stop(mydb, nsr_id, vdu, myvim, needWanSwitch, meta_data, vimseq, e2e_log)
                if result < 0:
                    log.error("Failed to stop VDU: %d %s" % (result, content))
                    if e2e_log:
                        e2e_log.job('Failed to stop VDU', CONST_TRESULT_FAIL, tmsg_body="Failed to stop VDU: %d %s" % (result, content))
                else:
                    _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=NFRStatus.STOP)
        elif type == 'start':
            _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=NFRStatus.START_ing)
            for vdu in vdu_list:
                result, content = _action_vdu_start(mydb, nsr_id, vdu, myvim, needWanSwitch, meta_data, vimseq, e2e_log)
                if result < 0:
                    log.error("Failed to start VDU: %d %s" % (result, content))
                    if e2e_log:
                        e2e_log.job('Failed to start VDU', CONST_TRESULT_FAIL, tmsg_body="Failed to start VDU: %d %s" % (result, content))
                else:
                    _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=NFRStatus.RUN)
        elif type == 'reboot':
            _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=NFRStatus.REBOOT)
            for vdu in vdu_list:
                result, content = _action_vdu_reboot(mydb, nsr_id, vdu, myvim, needWanSwitch, meta_data, vimseq, e2e_log, remote_dict=None)
                if result < 0:
                    log.error("Failed to reboot VDU: %d %s" % (result, content))
                    if e2e_log:
                        e2e_log.job('Failed to reboot VDU', CONST_TRESULT_FAIL, tmsg_body="Failed to reboot VDU: %d %s" % (result, content))
                else:
                    _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=NFRStatus.RUN)
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        if e2e_log:
            e2e_log.job('VNF Action Thread 실패', CONST_TRESULT_FAIL, tmsg_body="VNF Action Failed. Cause: %s" % str(e))
            e2e_log.finish(CONST_TRESULT_FAIL)
            is_succ = False
            result = -500
        # return -HTTP_Internal_Server_Error, "VNF Action(%s)이 실패하였습니다. 원인: %s" % (str(type), str(e))

    if e2e_log and is_succ:
        e2e_log.job('VNF Action Thread 완료 [%s]' % type, CONST_TRESULT_SUCC, tmsg_body=None)
        e2e_log.finish(CONST_TRESULT_SUCC)

    # VNF 최종 상태 업데이트 - tb_nfr
    if result < 0:
        log.debug("[********HJC**********] Update VUD Status for %s" %str(vdu_list))
        for vdu in vdu_list:
            try:
                log.debug("[********HJC**********] action vdu 1")
                time.sleep(5)
                result, vims = get_vim_connector(mydb, vimseq)
                log.debug("[********HJC**********] action vdu 2")
                if result < 0:
                    log.error("action_vnf() error, failed to get a VIM connection for the VDU")
                    raise Exception("Failed to get a VIM connection for the VDU : %d %s" % (result, vims))
                    # return result, vims
                myvim = vims.values()[0]

                log.debug("[********HJC**********] action vdu 3")
                status_result, status_content = myvim.get_server_id(vdu['uuid'])
                log.debug("[********HJC**********] action vdu 4")
            except Exception, e:
                log.exception("Exception: %s" %str(e))
                status_result = -HTTP_Internal_Server_Error
                status_content = str(e)

            log.debug("[********HJC**********] action vdu 5")
            if status_result < 0:
                try:
                    log.debug("2nd Try to get vdu status from VIM after 10 sec")
                    time.sleep(10)
                    result, vims = get_vim_connector(mydb, vimseq)
                    if result < 0:
                        log.error("action_vnf() error, failed to get a VIM connection for the VDU")
                        raise Exception("Failed to get a VIM connection for the VDU : %d %s" % (result, vims))
                        # return result, vims
                    myvim = vims.values()[0]

                    status_result, status_content = myvim.get_server_id(vdu['uuid'])
                except Exception, e:
                    log.exception("Exception: %s" %str(e))
                    status_result = -HTTP_Internal_Server_Error
                    status_content = str(e)

            log.debug("[********HJC**********] action vdu 6")
            if status_result < 0:
                log.debug("[**********HJC***********] fail result: %s" %str(status_result))
                _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=NFRStatus.UNKNOWN)
            else:
                if status_content.get("status") == "SHUTOFF":
                    vnf_status = NFRStatus.STOP
                elif status_content.get("status") == "ACTIVE":
                    vnf_status = NFRStatus.RUN
                else: # 이런경우는 없어야...디버깅용
                    vnf_status = status_content.get("status")
                log.debug("[**********HJC***********] result: %s" %str(status_result))
                _update_vnf_status(mydb, ActionType.VDUAC, action_dict=None, action_status=None, vnf_data=vnf_dict, vnf_status=vnf_status)

    log.debug("Completed the VNF Action")


def _check_vdu_status(mydb, vimseq, vdu_uuid, vdu_dict, max_check_num=10, target_status='ACTIVE', OBAction="NONE"):
    vdu_status = 'WAITING'
    check_count = 1
    while vdu_status != target_status:
        if check_count > max_check_num:
            log.warning("Check No: %d, stop checking the VDU Status. The Last Status = %s" % (check_count, vdu_status))
            break
        time.sleep(20)

        try:
            result, vims = get_vim_connector(mydb, vimseq)
            if result < 0:
                log.error("action_vnf() error, failed to get a VIM connection for the VDU")
                status_result = result
                status_content = vims
            else:
                vim = vims.values()[0]
                status_result, status_content = vim.get_server_id(vdu_uuid)
        except Exception, e:
            log.error("Exception: %s" %str(e))
            status_result = -HTTP_Internal_Server_Error
            status_content = str(e)

        if status_result < 0:
            log.error("Check No: %d, failed to check the VDU Status : %s" % (check_count, status_content))
        else:
            vdu_status = status_content.get("status")
            log.debug("Check No: %d, the VDU Status = %s" % (check_count, vdu_status))

        check_count += 1

    if vdu_status == 'ACTIVE':
        vdu_status = 'Active'
        pass

    # Update Status
    vdu_dict["status"] = vdu_status
    orch_dbm.update_nsr_vdu_status(mydb, vdu_dict)

    return 200, vdu_status

def _action_vdu_stop(mydb, nsr_id, vdu, myvim, needWanSwitch, meta_data, vimseq, e2e_log=None):
    result = 200
    content = {"name": vdu['name'], "message": "OK"}
    vm_local_ip = None
    myoba = None

    # if (vdu['name'].find("UTM") >= 0 or vdu['name'].find("KT-VNF") >= 0) and needWanSwitch:
    #     cp_result, cp_list = orch_dbm.get_vnf_cp_only(mydb, vdu['vduseq'])
    #     if cp_result < 0:
    #         log.warning("Failed to get CP List of the VDU: %s" % (vdu['name']))
    #     else:
    #         for cp in cp_list:
    #             if cp['name'].find("local") >= 0 or cp['name'].find("blue") >= 0:
    #                 vm_local_ip = cp['ip']
    #                 #log.debug("[HJC] found local IP: %s, %s" % (cp['name'], cp['ip']))
    #                 break
    #
    #     if vm_local_ip is None:
    #         log.error("Failed to get Local IP address of the VM: %s" % vdu['name'])
    #         return -HTTP_Internal_Server_Error, "Cannot find the loca ip address of the VM"
    #
    #     result, ob_agents = get_onebox_agent(mydb, nsr_id=nsr_id)
    #     if result < 0:
    #         log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
    #         return result, str(ob_agents)
    #
    #     myoba = ob_agents.values()[0]
    #
    #     result, ob_content = myoba.suspend_monitor_wan(vdu['name'], vm_local_ip)
    #     if result < 0:
    #         log.error("Failed to suspend monitoring WAN of the One-Box: %d %s" %(result, ob_content))
    #         #return -HTTP_Internal_Server_Error, "Failed to suspend monitoring WAN of the One-Box"
    #
    #     result, ob_content = myoba.do_switch_wan("vm2host", vdu['name'], vm_local_ip, time_interval = 1, e2e_log=None)
    #     if result < 0:
    #         log.error("Failed to switch WAN of the One-Box: %d %s" % (result, ob_content))
    #         return -HTTP_Internal_Server_Error, "Failed to switch WAN of the One-Box: %d %s" % (result, ob_content)

    if e2e_log:
        e2e_log.job('VDU Stop', CONST_TRESULT_NONE,
                    tmsg_body="Heat API: VDU Stop [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    result, vims = get_vim_connector(mydb, vimseq)
    if result < 0:
        log.error("action_vnf() error, failed to get a VIM connection for the VDU")
    else:
        myvim = vims.values()[0]

    stop_result, stop_content = myvim.action_server_stop(vdu['uuid'])

    if stop_result < 0:
        log.error("STOP VDU %s Error, VIM stop %d %s" % (vdu['name'], stop_result, stop_content))
        result = stop_result
        content['message'] = 'Error, ' + str(stop_content)
        if e2e_log:
            e2e_log.job('VDU Stop', CONST_TRESULT_FAIL,
                        tmsg_body="Heat API: VDU Stop [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    else:
        log.debug("STOP VDU %s OK" % (vdu['name']))

        # Update Status
        vdu["status"] = "STOP-ING"
        orch_dbm.update_nsr_vdu_status(mydb, vdu)

        check_result, check_content = _check_vdu_status(mydb, vimseq, vdu['uuid'], vdu, 10, 'SHUTOFF')

        if e2e_log:
            e2e_log.job('VDU Stop', CONST_TRESULT_SUCC,
                        tmsg_body="Heat API: VDU Stop [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    # if vm_local_ip is not None and myoba is not None:
    #     result, ob_content = myoba.resume_monitor_wan(vdu['name'], vm_local_ip)
    #     if result < 0:
    #         log.error("Failed to suspend monitoring WAN of the One-Box: %d %s" %(result, ob_content))

    return result, str(content)

def _action_vdu_start(mydb, nsr_id, vdu, myvim, needWanSwitch, meta_data, vimseq, e2e_log=None):
    result = 200
    content = {"name": vdu['name'], "message": "OK"}

    if e2e_log:
        e2e_log.job('VDU Start', CONST_TRESULT_NONE,
                    tmsg_body="Heat API: VDU Start [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    result, vims = get_vim_connector(mydb, vimseq)
    if result < 0:
        log.error("action_vnf() error, failed to get a VIM connection for the VDU")
    else:
        myvim = vims.values()[0]
    start_result, start_content = myvim.action_server_start(vdu['uuid'])

    if start_result < 0:
        log.error("START VDU %s Error, VIM start %d %s" % (vdu['name'], start_result, start_content))
        result = start_result
        content['message'] = 'Error, ' + str(start_content)
        if e2e_log:
            e2e_log.job('VDU Start', CONST_TRESULT_FAIL,
                        tmsg_body="Heat API: VDU Start [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    else:
        log.debug("START VDU %s OK" % (vdu['name']))

        # Update Status
        vdu["status"] = "START-ING"
        orch_dbm.update_nsr_vdu_status(mydb, vdu)

        check_result, check_content = _check_vdu_status(mydb, vimseq, vdu['uuid'], vdu, 20, 'ACTIVE')
        if e2e_log:
            e2e_log.job('VDU Start', CONST_TRESULT_SUCC,
                        tmsg_body="Heat API: VDU Start [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    # if (vdu['name'].find("UTM") >= 0 or vdu['name'].find("KT-VNF") >= 0) and needWanSwitch:
    #     vm_local_ip = None
    #     cp_result, cp_list = orch_dbm.get_vnf_cp_only(mydb, vdu['vduseq'])
    #     if cp_result < 0:
    #         log.warning("Failed to get CP List of the VDU: %s" % (vdu['name']))
    #     else:
    #         for cp in cp_list:
    #             if cp['name'].find("local") >= 0 or cp['name'].find("blue") >= 0:
    #                 vm_local_ip = cp['ip']
    #                 #log.debug("[HJC] found local IP: %s, %s" % (cp['name'], cp['ip']))
    #                 break
    #
    #     if vm_local_ip is None:
    #         log.error("Failed to get Local IP address of the VM: %s" % vdu['name'])
    #         return -HTTP_Internal_Server_Error, "Cannot find the loca ip address of the VM"
    #
    #     result, ob_agents = get_onebox_agent(mydb, nsr_id=nsr_id)
    #     if result < 0:
    #         log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
    #         return result, str(ob_agents)
    #
    #     myoba = ob_agents.values()[0]
    #
    #     result, ob_content = myoba.suspend_monitor_wan(vdu['name'], vm_local_ip)
    #     if result < 0:
    #         log.error("Failed to suspend monitoring WAN of the One-Box: %d %s" %(result, ob_content))
    #
    #     try:
    #         log.debug("Try 1st WAN Switch: time interval = 30 sec")
    #         result, ob_content = myoba.do_switch_wan("host2vm", vdu['name'], vm_local_ip, time_interval = 30, e2e_log=None)
    #     except Exception, e:
    #         result = -HTTP_Internal_Server_Error
    #         content = str(e)
    #
    #     if result < 0:
    #         log.error("Failed to switch WAN of the One-Box: %d %s" % (result, ob_content))
    #
    #         try:
    #             log.debug("Try 2nd WAN Switch: time interval = 30 sec")
    #             result, ob_content = myoba.do_switch_wan("host2vm", vdu['name'], vm_local_ip, time_interval = 30, e2e_log=None)
    #         except Exception, e:
    #             log.exception("2nd WAN Switch Failed: %s" %str(e))
    #             result = -HTTP_Internal_Server_Error
    #             content = str(e)
    #     else:
    #         log.debug("Succeed to switch WAN")
    #
    #
    #     rs_result, rs_content = myoba.resume_monitor_wan(vdu['name'], vm_local_ip)
    #     if rs_result < 0:
    #         log.error("Failed to suspend monitoring WAN of the One-Box: %d %s" %(rs_result, rs_content))

    return result, str(content)


def _action_vdu_reboot(mydb, nsr_id, vdu, myvim, needWanSwitch, meta_data, vimseq, e2e_log=None, type="SOFT", remote_dict=None):
    result = 200
    content = {"name": vdu['name'], "message": "OK"}
    vm_local_ip = None

    if (vdu['name'].find("UTM") >= 0 or vdu['name'].find("KT-VNF") >= 0) and needWanSwitch:
        cp_result, cp_list = orch_dbm.get_vnf_cp_only(mydb, vdu['vduseq'])
        if cp_result < 0:
            log.warning("Failed to get CP List of the VDU: %s" % (vdu['name']))
        else:
            for cp in cp_list:
                if cp['name'].find("local") >= 0 or cp['name'].find("blue") >= 0:
                    vm_local_ip = cp['ip']
                    #log.debug("[HJC] found local IP: %s, %s" % (cp['name'], cp['ip']))
                    break

        if vm_local_ip is None:
            log.error("Failed to get Local IP address of the VM: %s" % vdu['name'])
            return -HTTP_Internal_Server_Error, "Cannot find the loca ip address of the VM"

        # result, ob_agents = get_onebox_agent(mydb, nsr_id=nsr_id)
        # if result < 0:
        #     log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
        # else:
        #     myoba = ob_agents.values()[0]
        #
        #     result, ob_content = myoba.suspend_monitor_wan(vdu['name'], vm_local_ip)
        #     if result < 0:
        #         log.error("Failed to suspend monitoring WAN of the One-Box: %d %s" %(result, ob_content))
        #     result, ob_content = myoba.do_switch_wan("vm2host", vdu['name'], vm_local_ip, time_interval = 10, e2e_log=None)
        #     if result < 0:
        #         log.error("Failed to wan switching VM2HOST WAN of the One-Box: %d %s" %(result, ob_content))

    if e2e_log:
        e2e_log.job('VDU Reboot', CONST_TRESULT_NONE,
                    tmsg_body="Heat API: VDU Reboot [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    # router 사용 시 : nova endpoint url 변경해주기 위해
    if 'public_ip' in remote_dict:
        try:
            log.debug('[5G Router] remote_dict = %s' %str(remote_dict))

            key_manager = AuthKeyDeployManager(mydb)
            key_manager.nova_endpoint_update(remote_dict.get('origin_ip'), remote_dict.get('public_ip'))
        except Exception, e:
            log.error(str(e))
            return -HTTP_Internal_Server_Error, str(e)


    time.sleep(5)
    result, vims = get_vim_connector(mydb, vimseq)
    if result < 0:
        log.error("action_vnf() error, failed to get a VIM connection for the VDU")
    else:
        myvim = vims.values()[0]

    reboot_result, reboot_content = myvim.action_server_reboot(vdu['uuid'], type)
    if reboot_result < 0:
        log.error("action_vnf() REBOOT VDU %s Error, VIM reboot %d %s" % (vdu['name'], reboot_result, reboot_content))
        result = reboot_result
        content['message'] = 'Error to reboot VM: %s' %str(reboot_content)
        if e2e_log:
            e2e_log.job('VDU Reboot', CONST_TRESULT_FAIL,
                        tmsg_body="Heat API: VDU Reboot [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))
        return result, str(content)
    else:
        log.debug("action_vnf() REBOOT VDU %s OK" % (vdu['name']))

        # Update Status
        vdu["status"] = "REBOOT-ING"
        orch_dbm.update_nsr_vdu_status(mydb, vdu)

        check_result, check_content = _check_vdu_status(mydb, vimseq, vdu['uuid'], vdu, 30, 'ACTIVE')
        if e2e_log:
            e2e_log.job('VDU Reboot', CONST_TRESULT_SUCC,
                        tmsg_body="Heat API: VDU Reboot [VDU ID = %s, VDU Name = %s]" % (str(vdu['uuid']), str(vdu['name'])))

    # if (vdu['name'].find("UTM") >= 0 or vdu['name'].find("KT-VNF") >= 0) and needWanSwitch:
    #     result, ob_agents = get_onebox_agent(mydb, nsr_id=nsr_id)
    #     if result < 0:
    #         log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
    #
    #     myoba = ob_agents.values()[0]
    #
    #     #trial_no = 0
    #     #while trial_no < 3:
    #     #    try:
    #     #        result, content = myoba.resume_monitor_wan(vdu['name'], vm_local_ip)
    #     #    except Exception, e:
    #     #        result = -HTTP_Internal_Server_Error
    #     #        content = str(e)
    #
    #     #    if result < 0:
    #     #        log.error("Failed to resume monitoring WAN of the One-Box: %d %s" %(result, content))
    #     #    else:
    #     #        log.debug("Succeed to resume monitoring WAN")
    #     #        break
    #
    #     #    trial_no += 1
    #
    #     try:
    #         log.debug("Try 1st WAN Switch: time_interval = 30 sec")
    #         time.sleep(60)
    #         result, ob_content = myoba.do_switch_wan("host2vm", vdu['name'], vm_local_ip, time_interval = 30, e2e_log=None)
    #     except Exception, e:
    #         result = -HTTP_Internal_Server_Error
    #         content = str(e)
    #
    #     if result < 0:
    #         log.error("Failed to switch WAN of the One-Box: %d %s" % (result, content))
    #     else:
    #         log.debug("Succeed to switch WAN")
    #
    #     rs_result, rs_content = myoba.resume_monitor_wan(vdu['name'], vm_local_ip)
    #     if rs_result < 0:
    #         log.error("Failed to suspend monitoring WAN of the One-Box: %d %s" %(rs_result, rs_content))

    return result, str(content)

def backup_nsr_vnf(mydb, backup_settings, vnf, tid=None, tpath=""):
    try:
        #log.debug("[HJC] tid = %s, tpath = %s" % (str(tid), str(tpath)))
        try:
            if not tid:
                e2e_log = e2elogger(tname='VNF Backup', tmodule='orch-F', tpath="orch_vnf-backup")
            else:
                e2e_log = e2elogger(tname='VNF Backup', tmodule='orch-F', tid=tid, tpath=tpath + "/orch_vnf-backup")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('API Call 수신 처리', CONST_TRESULT_SUCC,
                        tmsg_body="VNF ID: %s\nVNF Backup Request Body:%s" % (str(vnf), json.dumps(backup_settings, indent=4)))
            action_tid = e2e_log['tid']
        else:
            action_tid = generate_action_tid()

        log.debug("Action TID: %s" % action_tid)

        # Step.1 Check arguments
        if vnf is None:
            log.error("backup_nsr_vnf() Error. vnf id is not given")
            raise Exception("VNF id is not given")

        # Step.2 Get VNF info.
        # 2-1 Get VNF record
        vnf_result, vnf_data = orch_dbm.get_vnf_id(mydb, vnf)
        if vnf_result <= 0:
            log.error("backup_nsr_vnf() failed to get NSR-VNF info. from DB")
            raise Exception("Failed to get NSR-VNF Info. from DB: %d %s" % (vnf_result, vnf_data))

        if vnf_data['status'] != NFRStatus.RUN:
            raise Exception("Cannot backup VNF in the status of %s" % vnf_data['status'])
        elif vnf_data['action'] is None or vnf_data['action'].endswith("E"):  # NGKIM: Use RE for backup
            pass
        else:
            raise Exception("The VNF is in Progress for another action: status= %s action= %s" % (vnf_data['status'], vnf_data['action']))

        if e2e_log:
            e2e_log.job("Get VNF record 성공", CONST_TRESULT_SUCC, tmsg_body="NSR-VNF Info : %s" % vnf_data)

        nsr = vnf_data['nsseq']
        vnf = vnf_data['nfseq']

        # 2-2 Get NS record
        nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr)
        if nsr_result <= 0:
            log.error("backup_nsr_vnf() failed to get NSR info. from DB")
            raise Exception("Failed to get NSR Info. from DB: %d %s" % (nsr_result, nsr_data))

        log.debug("backup_nsr_vnf() NSR seq: %s, VNF seq: %s" % (str(nsr), str(vnf)))

        if e2e_log:
            e2e_log.job("Get NS record 성공", CONST_TRESULT_SUCC, tmsg_body="NSR Info : %s" % nsr_data)

        # 2-3. Get customer info and server info
        customer_result, customer_data = orch_dbm.get_customer_resources(mydb, nsr_data['customerseq'])
        if customer_result <= 0:
            log.error("backup_nsr_vnf() failed to get Customer info. from DB")
            raise Exception("Failed to get Customer Info. from DB: %d %s" % (customer_result, customer_data))

        server_id = None
        server_action = None
        server_status = None
        for resource in customer_data:
            if resource['resource_type'] == 'server' and str(resource['nsseq']) == str(nsr):
                server_id = resource['serverseq']
                server_name = resource['servername']
                server_status = resource['status']
                server_action = resource['action']
                break

        if e2e_log:
            e2e_log.job("Get Customer Info 성공", CONST_TRESULT_SUCC, tmsg_body="Customer Info : %s" % customer_data)

        # 2-3 Check Server Status
        log.debug("[HJC] server status = %s, server action = %s" % (server_status, server_action))
        if server_action is None or server_action.endswith("E"):
            pass
        else:
            raise Exception("The One-Box is in Progress for another action: status = %s, action = %s" % (server_status, server_action))

        if server_id is None:
            log.error("backup_nsr_vnf() failed to get Server info. from DB")
            raise Exception("Failed to get Server Info. From DB")

        if e2e_log:
            e2e_log.job("Check Server Status 성공", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.3 Update VNF status
        action_dict = {'tid': action_tid}
        action_dict['category'] = "NFBackup"
        action_dict['action'] = "BS"
        action_dict['status'] = "Start"
        action_dict['action_user'] = backup_settings.get("user", "admin")
        action_dict['server_name'] = server_name
        action_dict['server_seq'] = server_id
        action_dict['nsr_name'] = nsr_data['name']
        action_dict['nsr_seq'] = nsr_data['nsseq']

        vnf_exist = False
        for vnf_data in nsr_data['vnfs']:
            if vnf_data is not None and vnf_data['nfseq'] != vnf:
                continue

            vnf_exist = True

            action_dict['nfr_name'] = vnf_data['name']
            action_dict['nfr_seq'] = vnf_data['nfseq']
            _update_vnf_status(mydb, ActionType.BACUP, action_dict=None, action_status=None, vnf_data=vnf_data, vnf_status=NFRStatus.BAC_waiting)

        if not vnf_exist:
            log.error("backup_nsr_vnf() Cannot find VNF")

            # Record action history
            action_dict['nfr_name'] = "Not Found"
            _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL)
            raise Exception("VNF %s Not found" % (str(vnf)))

        if e2e_log:
            e2e_log.job("Update VNF status 성공", CONST_TRESULT_SUCC, tmsg_body="Status : %s" % NFRStatus.BAC_waiting)

        # Step 4. Start VNF backup
        try:
            th = threading.Thread(target=_backup_vnf_thread, args=(mydb, server_id, nsr_data, action_dict, backup_settings, vnf, e2e_log))
            th.start()
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
            error_msg = "failed invoke a Thread for backup VNF %s" % str(nsr)
            _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL)
            raise Exception(error_msg)
    except Exception, e:
        log.warning("Exception: [%s] " % (str(e)))
        error_msg = "VNF 백업이 실패하였습니다. 원인: %s" % str(e)

        if e2e_log:
            e2e_log.job('Ready for VNF Backup', CONST_TRESULT_FAIL, error_msg)
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, error_msg

    if e2e_log:
        e2e_log.job("API Call 수신 처리 완료", CONST_TRESULT_SUCC, tmsg_body="VNF ID: %s\nVNF Backup Completed" % str(vnf))
    # e2e_log.job('API Call 수신 처리', CONST_TRESULT_SUCC,
    #         tmsg_body="VNF ID: %s\nVNF Backup Request Body:%s\n처리 결과: 성공" %(str(vnf), json.dumps(backup_settings, indent=4)))

    return 200, "OK"

def _backup_vnf_thread(mydb, server_id, nsr_dict, action_dict, backup_settings={}, vnf_id=None, e2e_log=None, use_thread=True):
    if use_thread:
        log.debug("[THREAD STARTED] _backup_vnf_thread()")

    is_vnf_backup_successful = True

    if e2e_log:
        e2e_log.job("VNF Backup Thread Start", CONST_TRESULT_SUCC, tmsg_body=None)

    err_str = ""
    action_category = action_dict['category']
    action_nfr_name = ""
    try:
        # Step.1 initialize variables
        global global_config

        # 1-1. cache action info for NSR
        action_dict['category'] = 'NFBackup'

        if action_category != 'NFBackup':
            action_nfr_name = action_dict['nfr_name']

        # Step.2 Update VNF status
        # for vnf in nsr_dict['vnfs']:
        #     if vnf_id is not None and vnf['nfseq'] != vnf_id:
        #         continue

            #_update_vnf_status(mydb, "B", action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.BAC_waiting)

        # Step.3 Get VNFM connector
        result, vnfms = common_manager.get_ktvnfm(mydb, server_id)
        if result < 0:
            log.error("_backup_vnf_thread() error. vnfm not found")
            is_vnf_backup_successful = False
        elif result > 1:
            is_vnf_backup_successful = False
            log.error("_backup_vnf_thread() Several vnfms available, must be identify")

        if not is_vnf_backup_successful:
            action_dict['category'] = action_category
            action_dict['nfr_name'] = action_nfr_name
            # action_dict.pop('nfr_seq')
            update_nsr_status(mydb, ActionType.BACUP, action_dict, ACTStatus.FAIL, nsr_dict, NSRStatus.RUN)
            raise Exception("Cannot establish VNFM Connector")

        myvnfm = vnfms.values()[0]

        if e2e_log:
            e2e_log.job('Get VNFM connector 성공', CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.4 Backup VNF
        for vnf in nsr_dict['vnfs']:
            if vnf_id is not None and vnf['nfseq'] != vnf_id:
                continue

            # 4-1. update VNF status and record action history
            action_dict['nfr_name'] = vnf['name']
            action_dict['nfr_seq'] = vnf['nfseq']

            try:
                org_vnf_status = vnf['status']
                _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.STRT, vnf_data=vnf, vnf_status=NFRStatus.BAC_composingvnfm)

                result = 200

                # 4-3. Start to backup VNF
                for vdu in vnf['vdus']:
                    access_ip = None

                    # 4-3-1. call VNFM API: backup VNF
                    for cp in vdu['cps']:
                        if cp['name'].find('blue') >= 0 or cp['name'].find('local') >= 0:
                            log.debug("_backup_vnf_thread(): the VNF access IP address found %s" % cp['ip'])
                            access_ip = cp['ip']
                            break

                    req_dict = {"name": vdu['name'], "ip": access_ip, "vnf_name": vnf['name'], "vnfd_name": vnf['vnfd_name'], "vnfd_version": vnf['version']}
                    log.debug("[======= HJC =======] backup req_dict = %s" %str(req_dict))
                    # if 'backup_server' in backup_settings: req_dict['backup_server'] = backup_settings['backup_server']
                    req_dict['backup_server'] = backup_settings.get('backup_server', global_config['backup_server'])

                    if 'backup_location' in backup_settings:
                        req_dict['backup_location'] = backup_settings['backup_location']

                    _update_vnf_status(mydb, ActionType.BACUP, action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.BAC_requestingvnfm)

                    tmsg_body = "VNFM API: Request Body\n %s" % str(req_dict['backup_server'])

                    if e2e_log:
                        e2e_log.job('Call VNFM API: VNF Backup', CONST_TRESULT_NONE, tmsg_body)

                    backup_result, backup_data = myvnfm.backup_vdu(req_dict, e2e_log)

                    if backup_result < 0:
                        result = backup_result
                        is_vnf_backup_successful = False
                        err_str = "_backup_vnf_thread() failed to backup VNF %s: %d %s" % (vdu['name'], backup_result, backup_data)
                        log.error(err_str)

                        # log.debug('_update_vnf_status : action_category = %s' %str(action_category))
                        # log.debug('_update_vnf_status : action_dict = %s' %str(action_dict))

                        # insert action history
                        if action_category == "NFBackup":
                            _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.RUN)
                        # else:
                        #     _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.RUN,
                        #                        action_flag="BS")

                        tmsg_body = "VNFM API: Request Body\n%s\n\nVNFM API: Response: %d %s" \
                                    % (str(req_dict['backup_server']), backup_result, str(backup_data))
                        if e2e_log:
                            e2e_log.job('Call VNFM API: VNF Backup', CONST_TRESULT_FAIL, tmsg_body)

                        raise Exception(tmsg_body)
                        # break

                    tmsg_body = "VNFM API: Request Body\n%s\n\nVNFM API: Response: %d %s" \
                                % (str(req_dict['backup_server']), backup_result, str(backup_data['remote_location']))
                    if e2e_log:
                        e2e_log.job('Call VNFM API: VNF Backup', CONST_TRESULT_SUCC, tmsg_body)

                    # 4-3-2. DB insert: backup info
                    _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.INPG, vnf_data=vnf,
                                       vnf_status=NFRStatus.BAC_processingdb)
                    backup_dict = {'serverseq': server_id, 'nsr_name': nsr_dict['name'], 'vnf_name': vnf['name'], 'vdu_name': vdu['name'],
                                   'nsseq': nsr_dict['nsseq'], 'nfseq': vnf['nfseq'], 'vduseq': vdu['vduseq'], 'category': "vnf"}
                    backup_dict['backup_server'] = req_dict['backup_server']
                    backup_dict['backup_location'] = backup_data['remote_location']
                    backup_dict['backup_local_location'] = backup_data['local_location']
                    backup_dict['description'] = "vdu config backup file"
                    backup_dict['creator'] = backup_settings.get('user', "admin")
                    backup_dict['trigger_type'] = backup_settings.get('trigger_type', "manual")
                    backup_dict['status'] = "Completed"
                    if 'parentseq' in backup_settings:
                        backup_dict['parentseq'] = backup_settings['parentseq']

                    backup_dict['download_url'] = "http://" + backup_dict['backup_server'] + backup_dict['backup_location'].replace("/var/onebox/backup",
                                                                                                                                    "/backup", 1)
                    db_result, db_data = orch_dbm.insert_backup_history(mydb, backup_dict)

                    tmsg_body = "DB Record: \n%s" % (str(backup_dict['download_url']))
                    if e2e_log:
                        e2e_log.job('DB Record: VNF Backup History', CONST_TRESULT_SUCC, tmsg_body)

                # 4-4. update VNF status and record action history
                if action_category == "NFBackup":
                    _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.SUCC, vnf_data=vnf, vnf_status=NFRStatus.RUN)
                else:
                    _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.SUCC, vnf_data=vnf, vnf_status=NFRStatus.RUN, action_flag="BS")
            except Exception, e:
                # log.debug('Exception : action_dict = %s' %str(action_dict))
                _update_vnf_status(mydb, ActionType.BACUP, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.RUN)
                raise Exception(str(e))

        # tb_backup_history 'ns' status => 'Completed' update
        if "parentseq" in backup_settings:
            bd_update_result, bd_update_content = orch_dbm.update_backup_history(mydb, {'backupseq':backup_settings['parentseq'], "status":"Completed"})
            if bd_update_result < 0:
                log.warning("failed to set status of backup data")

    except Exception, e:
        log.exception("Exception: %s" % str(e))
        is_vnf_backup_successful = False
        err_str = str(e)

    # Step.5 update NSR if necessary
    if action_category == 'NFBackup':
        if is_vnf_backup_successful:
            # _update_vnf_status(mydb, "B", action_dict=action_dict, action_status=ACTStatus.SUCC, vnf_data=vnf, vnf_status=NFRStatus.RUN)
            if e2e_log:
                e2e_log.job('Completed: VNF Backup', CONST_TRESULT_SUCC, tmsg_body=None)
                e2e_log.finish(CONST_TRESULT_SUCC)
        else:
            # _update_vnf_status(mydb, "B", action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.RUN)
            if e2e_log:
                e2e_log.job('Failed: VNF Backup', CONST_TRESULT_FAIL, tmsg_body=err_str)
                e2e_log.finish(CONST_TRESULT_FAIL)
    else:
        action_dict['category'] = action_category
        action_dict['nfr_name'] = action_nfr_name
        if "nfr_seq" in action_dict:
            action_dict.pop('nfr_seq')

        if is_vnf_backup_successful:
            update_nsr_status(mydb, ActionType.BACUP, action_dict, ACTStatus.SUCC, nsr_dict, NSRStatus.RUN)

            if e2e_log:
                e2e_log.job('Completed: VNF Backup', CONST_TRESULT_SUCC, tmsg_body=None)
                e2e_log.finish(CONST_TRESULT_SUCC)
        else:
            update_nsr_status(mydb, ActionType.BACUP, action_dict, ACTStatus.FAIL, nsr_dict, NSRStatus.RUN)

            if "parentseq" in backup_settings:
                bd_update_result, bd_update_content = orch_dbm.update_backup_history(mydb, {'backupseq':backup_settings['parentseq'], "status":"Completed", "ood_flag": "TRUE"})
                if bd_update_result < 0:
                    log.warning("failed to set status of backup data")

            if e2e_log:
                e2e_log.job('Failed: VNF Backup', CONST_TRESULT_FAIL, tmsg_body=err_str)
                e2e_log.finish(CONST_TRESULT_FAIL)

    if use_thread:
        log.debug("[THREAD FINISHED] _backup_vnf_thread()")

    return 200, "OK"


def restore_nsr_vnf(mydb, request, vnf, tid=None, tpath=""):

    e2e_log = None

    try:
        #log.debug("[HJC] tid = %s, tpath = %s" % (str(tid), str(tpath)))
        try:
            if not tid:
                e2e_log = e2elogger(tname='VNF Restore', tmodule='orch-f', tpath="orch_vnf-restore")
            else:
                e2e_log = e2elogger(tname='VNF Restore', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_vnf-restore")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('API Call 수신 처리', CONST_TRESULT_SUCC,
                        tmsg_body="VNF ID: %s\nVNF Restore Request Body:%s" % (str(vnf), json.dumps(request, indent=4)))

        # Step.1 Check arguments and initialize variables
        action_tid = generate_action_tid()

        # Step.2 Get VNF info
        # 2-1. Get VNF record
        vnf_result, vnf_data = orch_dbm.get_vnf_id(mydb, vnf)
        if vnf_result <= 0:
            log.error("restore_nsr_vnf() failed to get NSR-VNF info. from DB")
            raise Exception("Failed to get NSR-VNF Info. from DB: %d %s" % (vnf_result, vnf_data))

        if vnf_data['status'] == NFRStatus.STOP:
            raise Exception("Cannot restore VNF in the status of %s" % vnf_data['status'])

        if vnf_data['action'] is None or vnf_data['action'].endswith("E"):  # NGKIM: Use RE for backup
            pass
        else:
            raise Exception("The VNF is in Progress for another action: status= %s action= %s" % (vnf_data['status'], vnf_data['action']))

        nsr = vnf_data['nsseq']
        vnf = vnf_data['nfseq']

        if e2e_log:
            e2e_log.job("Get VNF record", CONST_TRESULT_SUCC, tmsg_body=None)

        # 2-2. Get NS record
        nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr)
        if nsr_result <= 0:
            log.error("restore_nsr_vnf() failed to get NSR info. from DB")
            raise Exception("Failed to get NSR Info. From DB: %d %s" % (nsr_result, nsr_data))

        if e2e_log:
            e2e_log.job("Get NS record", CONST_TRESULT_SUCC, tmsg_body=None)

        # 2-3. Get customer info and server info
        customer_result, customer_data = orch_dbm.get_customer_resources(mydb, nsr_data['customerseq'])
        if customer_result <= 0:
            log.error("restore_nsr_vnf() failed to get Customer info. from DB")
            raise Exception("Failed to get Customer Info. From DB: %d %s" % (customer_result, customer_data))

        server_id = None
        server_name = None
        server_action = None
        server_status = None
        server_public_ip = None
        server_mgmt_ip = None
        for resource in customer_data:
            if resource['resource_type'] == 'server' and resource['nsseq'] == nsr:
                server_id = resource['serverseq']
                server_name = resource['servername']
                server_status = resource['status']
                server_action = resource['action']
                server_public_ip = resource['publicip']
                server_mgmt_ip = resource['mgmtip']
                break

        if e2e_log:
            e2e_log.job("Get customer info and server info", CONST_TRESULT_SUCC, tmsg_body=None)

        # 2-4 Check Server Status
        log.debug("[HJC] server status = %s, server action = %s" % (server_status, server_action))
        if server_status == SRVStatus.DSC:
            raise Exception("The One-Box is not connected. Check One-Box: status = %s, action = %s" % (server_status, server_action))

        if server_action is None or server_action.endswith("E"):
            pass
        else:
            raise Exception("The One-Box is in Progress for another action: status = %s, action = %s" % (server_status, server_action))

        if server_id is None:
            log.error("restore_nsr_vnf() failed to get Server info. from DB")
            raise Exception("Failed to get Server Info. from DB")

        result, request['needWanSwitch'] = _need_wan_switch(mydb, {"serverseq": server_id})

        if e2e_log:
            e2e_log.job("Check Server Status", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.3 Compose action history and Update VNF status
        action_dict = {'tid': action_tid}
        action_dict['category'] = "NFRestore"
        action_dict['action'] = "RS"
        action_dict['status'] = "Start"
        action_dict['action_user'] = request.get("user", "admin")
        if 'backup_id' in request:
            action_dict['nfr_backup_seq'] = request['backup_id']
        action_dict['server_name'] = server_name
        action_dict['server_seq'] = server_id
        action_dict['nsr_name'] = nsr_data['name']
        action_dict['nsr_seq'] = nsr_data['nsseq']

        vnf_exist = False
        for vnf_data in nsr_data['vnfs']:
            if vnf_data is not None and vnf_data['nfseq'] != vnf:
                continue

            vnf_exist = True
            action_dict['nfr_name'] = vnf_data['name']
            action_dict['nfr_seq'] = vnf_data['nfseq']
            _update_vnf_status(mydb, ActionType.RESTO, action_dict=None, action_status=None, vnf_data=vnf_data, vnf_status=NFRStatus.RST_waiting)

        if not vnf_exist:
            log.error("restore_nsr_vnf() Cannot find VNF")

            action_dict['nfr_name'] = "Not Found"
            _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=None, vnf_status=None)

            raise Exception("VNF %s Not found" % (str(vnf)))

        if e2e_log:
            e2e_log.job("Compose action history and Update VNF status", CONST_TRESULT_SUCC,
                        tmsg_body="action_dict : %s" % json.dumps(action_dict, indent=4))
            e2e_log.job('API Call 수신 처리', CONST_TRESULT_SUCC,
                        tmsg_body="VNF ID: %s\nVNF Restore Request Body:%s" % (str(vnf), json.dumps(request, indent=4)))

        # Step.5 Restore VNF
        try:
            th = threading.Thread(target=_restore_nsr_vnf_thread, args=(mydb, server_id, nsr_data, action_dict, request, vnf, e2e_log))
            th.start()
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
            raise Exception("failed invoke a Thread for restore NSR-VNF %s" % str(vnf))
    except Exception, e:
        log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
        if e2e_log:
            e2e_log.job('API Call 수신 처리 실패', CONST_TRESULT_FAIL,
                        tmsg_body="VNF ID: %s\nVNF Restore Request Body:%s\nResult: VNF 복구가 실패하였습니다. 원인: %s" % (
                        str(vnf), json.dumps(request, indent=4), str(e)))

        return -HTTP_Internal_Server_Error, "VNF 복구가 실패하였습니다. 원인: %s" % str(e)

    return 200, "OK"


def _restore_nsr_vnf_thread(mydb, server_id, nsr_dict, action_dict, request, vnf_id=None, e2e_log=None):

    # Step.1 initialize variables
    action_category = action_dict['category']
    action_dict['category'] = "NFRestore"
    action_nfr_name = None

    try:
        if action_category != 'NFRestore':
            action_nfr_name = action_dict['nfr_name']

        entire_result = 200

        # Step.2 Get VNFM Connector
        result, vnfms = common_manager.get_ktvnfm(mydb, server_id)
        if result < 0 or result > 1:
            log.error("_restore_nsr_vnf_thread() error. cannot find vnfm connector")
            raise Exception("No KT VNFM Found: %d %s" % (result, vnfms))

        myvnfm = vnfms.values()[0]

        if e2e_log:
            e2e_log.job('VNF 연결 준비', CONST_TRESULT_SUCC, tmsg_body="VNF 연결 준비 완료\nVNF Connection: %s" % (myvnfm['url']))

        # Step.3 Restore VNF
        for vnf in nsr_dict['vnfs']:
            if vnf_id is not None and vnf['nfseq'] != vnf_id:
                continue

            if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
                log.debug("VNF, %s, belongs to GiGA Office. Skip Restoring" % vnf['name'])
                continue

            log.debug("_restore_nsr_vnf_thread() Start VNF Restore: %s" % vnf['name'])

            # 3-1. update VNF status and record action history
            action_dict['nfr_name'] = vnf['name']
            action_dict['nfr_seq'] = vnf['nfseq']
            action_dict['status'] = "Start"
            if 'nfr_backup_seq' in action_dict:
                action_dict.pop('nfr_backup_seq')

            _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.STRT, vnf_data=vnf, vnf_status=NFRStatus.RST_parsing)

            # 3-3. Restore VNF
            for vdu in vnf['vdus']:
                # 3-3-1. Compose VNFM API request
                access_ip = None
                for cp in vdu['cps']:
                    # if "restore_ip" in request and request["restore_ip"] == "mgmt":
                    #     if cp["name"].find("mgmt") >= 0:
                    #         log.debug("_restore_nsr_vnf_thread(): the VNF access IP address found %s" % cp['ip'])
                    #         access_ip = cp['ip']
                    #         break
                    # else:
                    if cp['name'].find('blue') >= 0 or cp['name'].find('local') >= 0:
                        log.debug("_restore_nsr_vnf_thread(): the VNF access IP address found %s" % cp['ip'])
                        access_ip = cp['ip']
                        break

                req_dict = {"name": vdu['name'], "ip": access_ip, "vnf_name": vnf['name'], "vnfd_name": vnf['vnfd_name'], "vnfd_version": vnf['version']}
                if "vm_access_id" in vdu:
                    req_dict["user"] = vdu["vm_access_id"]
                if "vm_access_passwd" in vdu:
                    req_dict["password"] = vdu["vm_access_passwd"]

                if req_dict['name'].find("UTM") >= 0 or req_dict['name'].find("KT-VNF") >= 0:
                    req_dict['needWanSwitch'] = request['needWanSwitch']
                if request.get('type') is not None:
                    req_dict['type'] = request['type']

                # 3-3-1-1. Get backup info
                target_dict = {'serverseq': server_id, 'nsr_name': nsr_dict['name'], 'vnf_name': vnf['name'], 'vdu_name': vdu['name']}
                # if 'parentseq' in request:
                #    target_dict['parentseq']=request['parentseq']

                if 'parentseq' in request:
                    target_dict['parentseq'] = request['parentseq']

                    # onebox restore할때 vnf의 ood_flag = True 이면, type을 'orch_wonet'로 변경
                    if "process_name" in request and request["process_name"] == "onebox_restore":
                        target_dict['ood_all'] = True

                    backup_result, backup_data = orch_dbm.get_backup_history_id(mydb, target_dict)
                    if backup_result > 0 and backup_data["ood_flag"]:
                        req_dict['type'] = "orch_wonet"

                elif 'backup_id' in request:
                    target_dict['backupseq'] = request['backup_id']
                    backup_result, backup_data = orch_dbm.get_backup_history_id(mydb, target_dict)
                else:
                    target_dict = {'serverseq': server_id, 'nsr_name': nsr_dict['name'], 'vnf_name': vnf['name'], 'vdu_name': vdu['name']}
                    backup_result, backup_data = orch_dbm.get_backup_history_lastone(mydb, target_dict)

                if backup_result <= 0:
                    log.warning("_restore_nsr_vnf_thread(): failed to get backup history for %s" % str(target_dict))
                    continue
                else:
                    action_dict['nfr_backup_seq'] = backup_data['backupseq']
                    req_dict['backup_server'] = backup_data["backup_server"]
                    if 'backup_location' in backup_data: req_dict['backup_location'] = backup_data["backup_location"]
                    if 'backup_local_location' in backup_data: req_dict['backup_local_location'] = backup_data["backup_local_location"]

                    # 3-3-2. Call API of VNFM: Restore VNF
                _update_vnf_status(mydb, ActionType.RESTO, action_dict=None, action_status=None, vnf_data=vnf, vnf_status=NFRStatus.RST_requestingvnfm)

                if e2e_log:
                    e2e_log.job("VNF Restore Request API 호출 %s" % req_dict['vnf_name'], CONST_TRESULT_NONE,
                                tmsg_body="VNF Restore Request Body: %s" % (json.dumps(req_dict, indent=4)),
                                tjobinfo="API_URL:%s/vnfs/%s/restore" % (myvnfm['url'], req_dict['vnf_name']))

                restore_result, restore_data = myvnfm.restore_vdu(req_dict, e2e_log)

                if restore_result > 0 or restore_result == -505:
                    # Step 3-4. Wait for rebooting VNF VDU
                    log.debug("_restore_nsr_vnf_thread() completed to send restore command to the VNFM for VNF VDU %s: %s" % (
                    vnf['name'], str(restore_data)))
                    result = -514
                    trial_no = 1
                    log.debug("_restore_nsr_vnf_thread() Wait for rebooting the VNF VDU %s" % (vnf['name']))
                    time.sleep(20)
                    _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.INPG, vnf_data=vnf,
                                       vnf_status=NFRStatus.RST_waitingvnfm)
                    while trial_no < 30:
                        log.debug("_restore_nsr_vnf_thread() Checking progress of restoring (%d):" % trial_no)

                        check_result, check_data = myvnfm.check_vdu_status(req_dict, e2e_log)

                        if check_result < 0:
                            result = check_result
                            log.debug("_restore_nsr_vnf_thread() Error %d, %s" % (check_result, str(check_data)))

                            if e2e_log:
                                e2e_log.job("VNF Restore Request API 호출 %s" % req_dict['vnf_name'],
                                            CONST_TRESULT_FAIL,
                                            tmsg_body="VNF Restore Failed. Cause: %s" % (str(check_data)),
                                            tjobinfo="API_URL:%s/vnfs/%s/restore" % (myvnfm['url'], req_dict['vnf_name']))
                                # break
                        else:
                            if check_data['status'] == "RUNNING":
                                result = 200
                                log.debug("_restore_nsr_vnf_thread() Completed to restore VNF VDU")
                                if e2e_log:
                                    e2e_log.job("VNF Restore Request API 호출 %s" % req_dict['vnf_name'],
                                                CONST_TRESULT_SUCC,
                                                tmsg_body="VNF Restore Succeed.",
                                                tjobinfo="API_URL:%s/vnfs/%s/restore" % (myvnfm['url'], req_dict['vnf_name']))
                                break
                            elif check_data['status'] == "UNDEFINED":
                                result = -500
                                log.debug("_restore_nsr_vnf_thread() Error to restore VNF VDU")
                                if e2e_log:
                                    e2e_log.job("VNF Restore Request API 호출 %s" % req_dict['vnf_name'],
                                                CONST_TRESULT_FAIL,
                                                tmsg_body="VNF Restore Failed.",
                                                tjobinfo="API_URL:%s/vnfs/%s/restore" % (myvnfm['url'], req_dict['vnf_name']))
                                break
                            else:
                                log.debug("_restore_nsr_vnf_thread() Restoring in Progress")
                        trial_no += 1
                        time.sleep(20)

                    if trial_no == 20 and result < 0:
                        log.error("Restore is under Progress")

                else:
                    result = restore_result
                    log.error("_restore_nsr_vnf_thread() failed to restore VNF %s: %d %s" % (vdu['name'], restore_result, restore_data))

            # 3-4. Update VNF status and record action history
            if action_category == 'NFRestore':
                if result < 0:
                    entire_result = -HTTP_Internal_Server_Error
                    _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.ERR)
                else:
                    _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.SUCC, vnf_data=vnf, vnf_status=NFRStatus.RUN)
            else:
                if result < 0:
                    entire_result = -HTTP_Internal_Server_Error
                    _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.ERR,
                                   action_flag="RS")
                else:
                    _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.SUCC, vnf_data=vnf, vnf_status=NFRStatus.RUN,
                                   action_flag="RS")

        # Step.4 restore action history info. if necessary
        if e2e_log:
            if entire_result < 0:
                e2e_log.job('VNF Restore 완료', CONST_TRESULT_FAIL, tmsg_body="VNF Restore Failed.")
            else:
                e2e_log.job('VNF Restore 완료', CONST_TRESULT_SUCC, tmsg_body="VNF Restore Succeed.")

        if action_category != 'NFRestore':
            action_dict['category'] = action_category
            action_dict['nfr_name'] = action_nfr_name
            action_dict.pop('nfr_seq')
            if 'nfr_backup_seq' in action_dict:
                action_dict.pop('nfr_backup_seq')
        else:
            if e2e_log:
                if entire_result < 0:
                    e2e_log.finish(CONST_TRESULT_FAIL)
                else:
                    e2e_log.finish(CONST_TRESULT_SUCC)

        log.debug("_restore_nsr_vnf_thread() End VNF Restore")

    except Exception, e:
        log.exception("Exception: %s" % str(e))

        for vnf in nsr_dict['vnfs']:
            if vnf_id is not None and vnf['nfseq'] != vnf_id:
                continue

            action_dict['nfr_name'] = vnf['name']
            action_dict['nfr_seq'] = vnf['nfseq']
            if action_category == "NFRestore":
                _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.ERR)
            else:
                _update_vnf_status(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, vnf_data=vnf, vnf_status=NFRStatus.ERR,
                                   action_flag="RS")

        if e2e_log:
            e2e_log.job('VNF Restore 실패', CONST_TRESULT_FAIL, tmsg_body="VNF Restore Failed. Cause: %s" % str(e))

        if action_category != 'NFRestore':
            action_dict['category'] = action_category
            action_dict['nfr_name'] = action_nfr_name
            action_dict.pop('nfr_seq')
        else:
            if e2e_log:
                e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "복구가 실패하였습니다. 원인: %s" % str(e)

    log.debug("_restore_nsr_vnf_thread() OUT")

    if entire_result < 0:
        entire_msg = "VNF 복구가 실패하였습니다."
    else:
        entire_msg = "OK"

    return entire_result, entire_msg


def backup_nsr(mydb, backup_settings, nsr, tid=None, tpath="", use_thread=True):

    nsr_data = None
    db_data = None
    e2e_log = None
    action_dict = None

    try:
        # Step.1 Check arguments, initialize variables
        if nsr is None:
            log.error("backup_nsr() Error. Both nsr id is not given")
            return -HTTP_Bad_Request, "NSR ID is required."

        try:
            if not tid:
                e2e_log = e2elogger(tname='NS Backup', tmodule='orch-F', tpath="orch_ns-backup")
            else:
                e2e_log = e2elogger(tname='NS Backup', tmodule='orch-F', tid=tid, tpath=tpath + "/orch_ns-backup")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('NSR Backup API Call 수신 처리', CONST_TRESULT_SUCC,
                        tmsg_body="NSR ID: %s\nNSR Backup Request Body:%s" % (str(nsr), json.dumps(backup_settings, indent=4)))
            action_tid = e2e_log['tid']
        else:
            action_tid = generate_action_tid()

        # Step.2 Get NSR info
        # 2-1. Get NS record
        nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr)
        if nsr_result <= 0:
            log.error("backup_nsr() failed to get NSR info. from DB : %d %s" % (nsr_result, nsr_data))
            nsr_data = None
            raise Exception("Failed to get NSR Info from DB : nsr : %s" % nsr)

        log.debug("backup_nsr() NSR seq: %s" % (str(nsr)))

        if nsr_data['status'] != NSRStatus.RUN:
            raise Exception("Cannot backup NSR in the status of %s" % nsr_data['status'])
        elif nsr_data['action'] is None or nsr_data['action'].endswith("E"):  # NGKIM: Use RE for backkup
            pass
        else:
            raise Exception("The NSR is in Progress for another action: status= %s, action= %s" % (nsr_data['status'], nsr_data['action']))

        # check VNF Status
        for vnf in nsr_data['vnfs']:
            if vnf['status'] != NFRStatus.RUN:
                log.warning("The status of VNF is %s. Passed backup-nsr!!!" % vnf['status'])
                raise Exception("RUNNING 상태가 아닌 VNF가 존재합니다.")

        if e2e_log:
            e2e_log.job("Get VNF record 성공", CONST_TRESULT_SUCC, tmsg_body="NSR-VNF Info : %s" % (json.dumps(nsr_data, indent=4)))

        # 2-2 Get customer info and server info
        customer_result, customer_data = orch_dbm.get_customer_resources(mydb, nsr_data['customerseq'])
        if customer_result <= 0:
            log.error("backup_nsr() failed to get Customer info. from DB")
            raise Exception("Failed to get Customer Info. from DB: %d %s" % (customer_result, customer_data))
            # return customer_result, customer_data

        server_id = None
        server_name = None
        server_action = None
        server_status = None

        for resource in customer_data:
            if resource['resource_type'] == 'server' and str(resource['nsseq']) == str(nsr):
                server_id = resource['serverseq']
                server_name = resource['servername']
                server_status = resource['status']
                server_action = resource['action']
                break

        if e2e_log:
            e2e_log.job("Get customer info and server info", CONST_TRESULT_SUCC, tmsg_body="Customer Info : %s" % (customer_data))

        # 2-3 Check Server Status
        log.debug("[HJC] server status = %s, server action = %s" % (server_status, server_action))
        if server_action is None or server_action.endswith("E"):
            pass
        elif server_action == "BS":
            pass
        else:
            raise Exception("The One-Box is in Progress for another action: status = %s, action = %s" % (server_status, server_action))

        # Step.3 record action history and update NSR
        vnf_name = ""
        for vnf_data in nsr_data['vnfs']:
            vnf_name = vnf_name + " " + vnf_data['name']

        action_dict = {'tid': action_tid}
        action_dict['category'] = "NSBackup"
        action_dict['action'] = "BS"
        action_dict['status'] = "Start"
        action_dict['action_user'] = backup_settings.get("user", "admin")
        action_dict['server_name'] = server_name
        action_dict['server_seq'] = server_id
        action_dict['nsr_name'] = nsr_data['name']
        action_dict['nsr_seq'] = nsr_data['nsseq']
        action_dict['nfr_name'] = vnf_name

        update_nsr_status(mydb, ActionType.BACUP, action_dict, ACTStatus.STRT, nsr_data, NSRStatus.BAC_backupnsr)

        if e2e_log:
            e2e_log.job("Record action history and update NSR", CONST_TRESULT_SUCC, tmsg_body="action_dict : %s" % (action_dict))

        # 백업을 RLT버젼으로 변경하기 위해 RLT 조회
        result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_data["nsseq"])
        if result <= 0:
            log.error("[Backup NSR][NS] : Error, failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("Failed to get RLT data from DB %d %s" % (result, rlt_data))

        rlt_dict = rlt_data["rlt"]

        # Step.5 Backup NSR
        # 5-1. backup NSR parameter values
        # np_result, np_data = _backup_nsr_param(mydb, nsr_data['nsseq'])
        # if np_result < 0:
        #     log.error("backup_nsr() error. Error getting NS Param from database")
        #     update_nsr_status(mydb, "B", action_dict, ACTStatus.FAIL, nsr_data, NSRStatus.RUN)
        #     raise Exception("Error getting NS Param from database %d %s" % (np_result, np_data))
        #     # return np_result, np_data
        #
        # # nsr_data['backup_params'] = np_data
        # rlt_dict['backup_params'] = np_data
        #
        # if e2e_log:
        #     e2e_log.job("Backup NSR parameter values", CONST_TRESULT_SUCC, tmsg_body="Parameters Data : %s" % (np_data))

        # 5-2. Make NSR backup file
        # req_dict = {"nsr_name": nsr_data['name'], "data": rlt_dict}
        # if 'backup_server' in backup_settings: req_dict['backup_server'] = backup_settings['backup_server']
        # req_dict['backup_server'] = backup_settings.get('backup_server', global_config['backup_server'])
        # if 'backup_location' in backup_settings:
        #     req_dict['backup_location'] = backup_settings['backup_location']

        backup_result, backup_data = _make_nsr_backup_file({"nsr_name": nsr_data['name'], "data": rlt_dict}, server_name)
        if backup_result < 0:
            update_nsr_status(mydb, ActionType.BACUP, action_dict, ACTStatus.FAIL, nsr_data, NSRStatus.RUN)
            raise Exception("Error makeing NSR backup file %d %s" % (backup_result, backup_data))

        if e2e_log:
            e2e_log.job("Make NSR backup file", CONST_TRESULT_SUCC, tmsg_body="NSR backup file Data : %s" % (backup_data))

        # 5-3. DB insert: NSR backup file
        backup_dict = {'serverseq': server_id, 'nsr_name': nsr_data['name'], 'nsseq': nsr_data['nsseq'], 'category': "ns"}
        backup_dict['backup_server'] = backup_settings.get('backup_server', global_config['backup_server'])
        backup_dict['backup_location'] = backup_data['backup_location']  # "/var/onebox/backup/test/nsr_name.yaml"
        backup_dict['backup_local_location'] = backup_data['backup_local_location']
        backup_dict['description'] = "nsr backup file"
        backup_dict['creator'] = backup_settings.get('user', "admin")
        backup_dict['trigger_type'] = backup_settings.get('trigger_type', "manual")
        backup_dict['status'] = "Backup"

        backup_dict['download_url'] = "http://" + backup_dict['backup_server'] + backup_dict['backup_location'].replace("/var/onebox/backup",
                                                                                                                        "/backup", 1)
        db_result, db_data = orch_dbm.insert_backup_history(mydb, backup_dict)

        if db_result < 0:
            log.warning("backup_nsr() failed to DB insert backup history: %d %s" % (db_result, db_data))
            raise Exception("Failed to insert backup history into DB %d %s" %(db_result, db_data))
        else:
            # backup_settings['backup_id'] = db_data
            log.debug("backup_nsr() created backup history record: %s" % (str(db_data)))
            backup_settings['parentseq'] = db_data

        if e2e_log:
            e2e_log.job("DB insert: NSR backup file", CONST_TRESULT_SUCC, tmsg_body="backup_dict : %s" % (json.dumps(backup_dict, indent=4)))

        # Step.6 Backup VNFs composing NSR
        update_nsr_status(mydb, ActionType.BACUP, action_dict, ACTStatus.INPG, nsr_data, NSRStatus.BAC_backupvnf)
        try:

            if use_thread:
                th = threading.Thread(target=_backup_vnf_thread, args=(mydb, server_id, rlt_dict, action_dict, backup_settings, None, e2e_log, use_thread))
                th.start()

            else:
                return _backup_vnf_thread(mydb, server_id, rlt_dict, action_dict, backup_settings=backup_settings, vnf_id=None, e2e_log=e2e_log, use_thread=False)
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
            error_msg = "failed invoke a Thread for backup NSR %s" % str(nsr)
            # update_nsr_status(mydb, "B", action_dict, ACTStatus.FAIL, nsr_data, NSRStatus.RUN)
            raise Exception("%d %s" % (HTTP_Internal_Server_Error, error_msg))

    except Exception, e:
        log.error("Exception: [%s]" % (str(e)))
        error_msg = "NS 백업이 실패하였습니다. 원인: %s" % str(e)
        update_nsr_status(mydb, ActionType.BACUP, action_dict, ACTStatus.FAIL, nsr_data, NSRStatus.RUN)

        # 백업실패니까, backup_history에 저장한 데이타가 존재할 경우 out of data 처리.
        if db_data is not None:
            bd_update_result, bd_update_content = orch_dbm.update_backup_history(mydb, {'backupseq':db_data, "status":"Completed", "ood_flag": "TRUE"})
            if bd_update_result < 0:
                log.warning("Failed to set ood flag as True of backup data")

        if e2e_log:
            e2e_log.job('Ready for NS Backup', CONST_TRESULT_FAIL, error_msg)
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, error_msg

    return 200, "OK"

def _make_nsr_backup_file(req_dict, onebox_id = "NONE"):
    global global_config

    base_directory = global_config['backup_repository']

    if not os.path.exists(base_directory):
        os.makedirs(base_directory)

    if not os.path.exists(os.path.join(base_directory, "nsr")):
        os.makedirs(os.path.join(base_directory, "nsr"))

    backup_datetime = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    backup_file = "backup-nsr_" + req_dict['nsr_name'] + "_" + backup_datetime + ".json"
    nsr_backup_filename = base_directory + "/nsr/" + backup_file

    log.debug("Local NSR Backup File: %s" %nsr_backup_filename)

    if not os.path.exists(nsr_backup_filename):
        f = file(nsr_backup_filename, "w")
        f.write(json.dumps(req_dict['data'], indent=4) + os.linesep)
        f.close()

    data = {'backup_local_location': nsr_backup_filename}

    try:
        #FilePath: base_directory/<onebox_id>/nsr/<date-time>/<nsr_name>_<datetime>.json
        remote_directory = base_directory + "/" + str(onebox_id) + "/nsr/" + backup_datetime
        remote_bakcup_filename = base_directory + "/" + str(onebox_id) + "/nsr/" + backup_datetime + "/" + backup_file

        log.debug("Remote NSR Backup File: %s" %remote_bakcup_filename)

        # get ha connection
        backup_server_ip = global_config['backup_server_local']
        ssh_conn = ssh_connector(backup_server_ip, 9922)

        # make direcotry
        command = {}
        command["name"]= "mkdir"
        command["params"] = [ "-p", remote_directory ]

        result, output = ssh_conn.run_ssh_command(command)

        # do scp
        result, output = ssh_conn.run_scp_command(nsr_backup_filename, remote_bakcup_filename)
        if result < 0:
            log.error("failed to remote-copy NSR backup file: %s %s" %(str(result), str(output)))

        data['backup_location'] = remote_bakcup_filename

    except Exception, e:
        log.exception("Exception: %s" %str(e))
        data['backup_location'] = ""

    return 200, data

# def _backup_nsr_param(mydb, nsr_id):
#     nsr_param_result, nsr_param_data = orch_dbm.get_nsr_params(mydb, nsr_id)
#     if nsr_param_result < 0:
#         log.error("_backup_nsr_param() error. Error getting NSR info (Param) from database")
#         return nsr_param_result, nsr_param_data
#
#     backup_params = None
#     backup_param_list = []
#     for param in nsr_param_data:
#         if param['name'].find("ROUT") >= 0:
#             log.debug("_backup_nsr_param() nsr_param type is ROUT. Skip")
#             continue
#
#         already_exist = False
#
#         for bparam in backup_param_list:
#             if bparam.find(param['name']) >= 0:
#                 already_exist = True
#                 break
#
#         if not already_exist:
#             backup_param_list.append("%s=%s" % (param['name'], param['value']))
#
#     if len(backup_param_list) > 0:
#         backup_params = ";".join(backup_param_list)
#         #log.debug("_backup_nsr_param() NSR Params = %s" % backup_params)
#
#         return 200, backup_params
#     else:
#         return -HTTP_Not_Found, "No NS Parameters found"

def _get_nsr_backup_data(backup_dict):
    nsr_backup_filename = backup_dict['backup_local_location']

    if os.path.exists(nsr_backup_filename):
        log.debug("_get_nsr_backup_data() backup file %s exists" % nsr_backup_filename)
        f = file(nsr_backup_filename, "r")
        raw_data = f.read()
        # log.debug("_get_nsr_backup_data() succeed to read backup file: %s" %str(raw_data))
        f.close()
    else:
        dir_nsr = os.path.dirname(nsr_backup_filename)
        if not os.path.exists(dir_nsr):
            os.mkdir(dir_nsr, mode=0755)

        # 서버이중화 등의 문제로 로컬에 백업파일이 없을경우 백업서버에서 파일을 가져온다.
        global global_config
        backup_server_ip = global_config['backup_server_local']
        ssh_conn = ssh_connector(backup_server_ip, 9922)
        result, output = ssh_conn.run_scp_command(backup_dict['backup_location'], nsr_backup_filename, mode="GET")
        if result < 0:
            log.error("failed to get NSR backup file from remote server: %s %s" %(str(result), str(output)))
        else:
            return _get_nsr_backup_data(backup_dict)

        log.error("_get_nsr_backup_data() Error. Cannot find the backup file %s" % nsr_backup_filename)
        return -HTTP_Internal_Server_Error, "Backup file not found"

    data = json.loads(raw_data)
    # log.debug("_get_nsr_backup_data() succeed to get NSR backup data: %s" %str(data))

    return 200, data

def restore_onebox_nsr(mydb, request, onebox_id):
    # Step.1 Check One-Box with One-Box ID

    # Step.2 Check NSR
    # 2-1. if NSR exists, call restore_nsr()
    # 2-2. if NSR does not exist, go to Step.3

    # Step.3 try to get NSR Backup Data with serverseq
    # 3-1. if NSR Backup Data exists, call restore_nsr() with NSR Backup Data
    # 3-2. if NSR Backup Data does not exist, return failure

    return 200, "OK"


def restore_nsr(mydb, nsr_id, request, use_thread=True, tid=None, tpath=""):

    e2e_log = None

    try:
        # Step.1 Check arguments and initialize variables
        log.debug("[Restore][NS][1] Initialize Local Variables: tid = %s, tpath = %s" % (str(tid), str(tpath)))

        try:
            if not tid:
                e2e_log = e2elogger(tname='NS Restore', tmodule='orch-f', tpath="orch_ns-restore")
            else:
                e2e_log = e2elogger(tname='NS Restore', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_ns-restore")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('NS 복구 API Call 수신 처리 시작', CONST_TRESULT_SUCC,
                        tmsg_body="NS ID: %s\nNS Restore Request Body:%s" % (str(nsr_id), json.dumps(request, indent=4)))
            action_tid = e2e_log['tid']
        else:
            action_tid = generate_action_tid()

        # Step.2 Get and check NS record
        log.debug("[Restore][NS][2] Get and Check NS Record of %s" % (str(nsr_id)))
        result, nsr_db_data = orch_dbm.get_nsr_id(mydb, nsr_id)
        if result < 0:
            log.error("restore_nsr() error. Error getting NSR info from database")
            raise Exception("Failed to get NSR Info. from DB: %d %s" % (result, nsr_db_data))
        elif result == 0:
            log.error("restore_nsr() error. Instance not found")
            raise Exception("Failed to get NSR Info. from DB: No NSR found")
        if nsr_db_data['action'].endswith("E"):  # NGKIM: Use RE for restore
            pass
        else:
            raise Exception("The NSR is in Progress for another action: status= %s, action= %s" % (nsr_db_data['status'], nsr_db_data['action']))

        # check VNF Status
        #for vnf in nsr_db_data['vnfs']:
        #    if vnf['status'] != NFRStatus.RUN:
        #        raise Exception("Cannot backup NSR since VNF is not normal")

        if e2e_log:
            e2e_log.job('Get and check NS record', CONST_TRESULT_SUCC,
                        tmsg_body="NS ID: %s\nNSR DB DATA:%s" % (str(nsr_id), json.dumps(nsr_db_data, indent=4)))

        # Step.3 Get customer info and server info
        log.debug("[Restore][NS][3] Get Customer Info and Server Info of Customer ID: %d" % (nsr_db_data['customerseq']))

        customer_result, customer_data = _restore_nsr_check_customer(mydb, nsr_db_data['customerseq'], nsr_id)

        if customer_result <= 0:
            log.error("restore_nsr() failed to get Customer info. from DB")
            raise Exception("Failed to get Customer Info. from DB: %d %s" % (customer_result, customer_data))

        if customer_data['server_status'] == SRVStatus.DSC:
            raise Exception("The One-Box is not connected. Check One-Box: status = %s" % (customer_data['server_status']))

        if e2e_log:
            e2e_log.job("Get customer info and server info", CONST_TRESULT_SUCC, tmsg_body="Customer ID: %s" % (nsr_db_data['customerseq']))

        # Step.4 Get backup info
        log.debug("[Restore][NS][4] Get backup info")

        nsr_result, rlt_backup = _restore_nsr_get_backup_data(mydb, nsr_id, request)

        if nsr_result < 0:
            raise Exception("Failed to get Backup Data and NSR data")

        # 임시코드 - 기존에 프로비져닝된 rlt의 값을 보정하기 위해 사용. 새로 프로비져닝 된 rlt는 문제 없도록 수정되었음.
        # 기존 rlt 의 nsr name이 잘못들어간 부분 수정처리
        if rlt_backup["name"] != nsr_db_data["name"]:
            rlt_backup["name"] = nsr_db_data["name"]
        # 임시코드 END - 해당 로직 이전에 프로비져닝 된 항목이 없을 경우 제거가능

        vnf_name = ""
        for vnf_data in rlt_backup['vnfs']:
            vnf_name = vnf_name + " " + vnf_data['name']

        if e2e_log:
            e2e_log.job("Get backup info", CONST_TRESULT_SUCC, tmsg_body="NS ID: %s" % (str(nsr_id)))

    except Exception, e:
        log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
        if e2e_log:
            e2e_log.job('NS 복구 API Call 수신 처리 실패', CONST_TRESULT_FAIL,
                        tmsg_body="NS ID: %s\nNS Restore Request Body:%s\nCause: %s" % (str(nsr_id), json.dumps(request, indent=4), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, "NS 복구가 실패하였습니다. 원인: %s" % str(e)

    if e2e_log:
        e2e_log.job("NS 복구 API Call 수신 처리 완료", CONST_TRESULT_SUCC,
                    tmsg_body="NS ID: %s\nNS Restore Request Body:%s\nNSR:%s" % (
                        str(nsr_id), json.dumps(request, indent=4), json.dumps(rlt_backup, indent=4)))

    action_dict = {'tid': action_tid}
    action_dict['category'] = "NSRestore"
    action_dict['action'] = "RS"
    action_dict['status'] = "Start"
    action_dict['action_user'] = request.get("user", "admin")
    action_dict['nsr_backup_seq'] = rlt_backup.get('backupseq')
    action_dict['server_name'] = customer_data['server_name']
    action_dict['server_seq'] = customer_data['server_id']
    action_dict['nsr_name'] = rlt_backup['name']
    action_dict['nsr_seq'] = rlt_backup['nsseq']
    action_dict['nfr_name'] = vnf_name

    try:
        update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.STRT, rlt_backup, NSRStatus.RST)

        # Step.5 start a thread for restoring NSR
        log.debug("[Restore][NS][5] start a thread to restore NSR")
        th = threading.Thread(target=_restore_nsr_thread,
                              args=(mydb, rlt_backup, action_dict, request, customer_data, e2e_log, use_thread))
        th.start()

        return 200, "OK"
    except Exception, e:
        log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
        update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.FAIL, rlt_backup, NSRStatus.RUN)

        if e2e_log:
            e2e_log.job('NS 복구 - Background 동작 시작', CONST_TRESULT_FAIL, tmsg_body="NS ID: %s\nCause: %s" % (str(nsr_id), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "NS 복구가 실패하였습니다. 원인: %s" % str(e)


def _restore_nsr_thread(mydb, rlt_backup, action_dict, request, customer_data, e2e_log=None, use_thread=True):
    if use_thread:
        log_info_message = "[THREAD STARTED] _restore_nsr_thread()"
        log.info(log_info_message.center(80, '='))

    # initialize variables
    if e2e_log:
        e2e_log.job('NS 복구 - Background 동작 시작', CONST_TRESULT_SUCC, tmsg_body="NS Info: %s" % (json.dumps(rlt_backup, indent=4)))

    server_dict = {}

    try:
        # Step.6 Stop monitoring
        log.debug("[Restore][NS][6] Suspending Monitoring of NS")

        server_dict['serverseq'] = customer_data['server_id']
        server_dict['nsseq'] = rlt_backup['nsseq']
        update_nsr_status(mydb, ActionType.RESTO, None, None, rlt_backup, NSRStatus.RST_suspendingmonitor, server_dict, SRVStatus.OOS)

        monitor_result, monitor_data = suspend_nsr_monitor(mydb, rlt_backup, customer_data, e2e_log)

        if monitor_result < 0:
            log.warning("_restore_nsr_thread() failed to stop monitor. False Alarms are expected")
            if e2e_log:
                e2e_log.job("Suspend monitoring", CONST_TRESULT_FAIL, tmsg_body=None)
        else:
            if e2e_log:
                e2e_log.job("Suspend monitoring", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.7 delete nsr
        log.debug("[Restore][NS][7] Deleting NSR")
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_backup, nsr_status=NSRStatus.RST_deletingvr)

        delete_result, delete_data = _restore_nsr_delete(mydb, rlt_backup, customer_data['server_id'], False, e2e_log)

        if delete_result < 0:
            log.warning("_restore_nsr_thread() failed to delete NSR %d %s" % (delete_result, delete_data))
            raise Exception("_restore_nsr_thread() failed to delete NSR %d %s" % (delete_result, delete_data))

        if e2e_log:
            e2e_log.job("Deleted NSR", CONST_TRESULT_SUCC, tmsg_body=None)

        time.sleep(10)
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.FAIL, rlt_backup, NSRStatus.ERR, server_dict, SRVStatus.ERR)
        if e2e_log:
            e2e_log.job('NS Virtual Resource 제거', CONST_TRESULT_FAIL, tmsg_body="Result: Fail\nCause: %s" % (str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "복구가 실패하였습니다. 원인: %s" % str(e)

    new_nsr_data = None
    try:

        # Step.8 reprovisioning NSR
        log.debug("[Restore][NS][8] Reprovisioning NSR")
        new_nsr_result, new_nsr_data = _restore_nsr_reprov(mydb, rlt_backup, rlt_backup['name'], rlt_backup['description'], customer_data, e2e_log)

        if new_nsr_result < 0:
            log.error("_restore_nsr_thread() failed to re-create NSR %d %s" % (new_nsr_result, new_nsr_data))
            err_cause = new_nsr_data
            new_nsr_data = rlt_backup
            raise Exception("_restore_nsr_thread() failed to re-create NSR %d %s" % (new_nsr_result, err_cause))

        if e2e_log:
            e2e_log.job("Reprovisioning NSR", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.9 Restore VNFs
        log.debug("[Restore][NS][8] Restore VNFs")
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_backup, nsr_status=NSRStatus.RST_restoringvnf)
        request['parentseq'] = rlt_backup['backupseq']

        result, request['needWanSwitch'] = _need_wan_switch(mydb, {"serverseq": customer_data["server_id"]})

        restore_result, restore_data = _restore_nsr_vnf_thread(mydb, customer_data['server_id'], new_nsr_data, action_dict, request, None, e2e_log)

        if restore_result < 0:
            log.warning("_restore_nsr_thread() error. failed to restore VNFs: %d %s" % (restore_result, restore_data))
            raise Exception("_restore_nsr_thread() error. failed to restore VNFs: %d %s" %(restore_result, restore_data))
            # if e2e_log:
            #     e2e_log.job("Restore VNFs", CONST_TRESULT_FAIL, tmsg_body=None)
        else:
            if e2e_log:
                e2e_log.job("Restore VNFs", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.10 Resume monitoring
        log.debug("[Restore][NS][10] Resuming NSR")
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_backup, nsr_status=NSRStatus.RST_resumingmonitor)
        result, data = resume_nsr_monitor(mydb, customer_data['server_id'], new_nsr_data, e2e_log)
        if result < 0:
            log.debug("_restore_nsr_thread()   : Failed %d %s" % (result, data))

        log.debug("_restore_nsr_thread() restoring VNF Configs Succeed")

        # Step.11 update NSR status
        log.debug("[Restore][NS][11] Updating NSR status")
        if restore_result < 0:
            update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.FAIL, new_nsr_data, NSRStatus.ERR, server_dict, SRVStatus.ERR)
        else:
            update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.RUN, server_dict, SRVStatus.INS)

            # 복구중 변경된 정보가 있을 수 있으므로, 최종적으로 new_server를 한번 호출해준다.
            result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=customer_data['server_id'])
            if result == 1:
                ob_agent = ob_agents.values()[0]
                result, server_info = ob_agent.get_onebox_info(None)
                if result < 0:
                    log.warning("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))
                else:
                    new_server(mydb, server_info, filter_data=customer_data["server_name"])

    except Exception, e:
        log.exception("Exception: %s" % str(e))
        if new_nsr_data:
            update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.FAIL, new_nsr_data, NSRStatus.ERR, server_dict, SRVStatus.ERR)
        else:
            update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.FAIL, rlt_backup, NSRStatus.ERR, server_dict, SRVStatus.ERR)

        if e2e_log:
            e2e_log.job('NS 복구 - 후처리', CONST_TRESULT_FAIL, tmsg_body="Result: Fail\nCause: %s" % (str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "복구가 실패하였습니다. 원인: %s" % str(e)

    if e2e_log:
        e2e_log.job('NS 복구 - 후처리', CONST_TRESULT_SUCC, tmsg_body="Result: Success")
        e2e_log.finish(CONST_TRESULT_SUCC)

    return 200, "OK"

def _restore_nsr_delete(mydb, nsr_data, server_id, need_stop_monitor=False, e2e_log=None):
    try:
        if e2e_log:
            e2e_log.job('Virtual Resource 삭제', CONST_TRESULT_NONE,
                        tmsg_body="Heat API: Delete Stack %s %s" % (str(nsr_data.get('uuid')), nsr_data.get('name')))

        # stop monitoring NSR
        if need_stop_monitor is True:
            monitor_result, monitor_response = stop_nsr_monitor(mydb, nsr_data['nsseq'], e2e_log)

            if monitor_result < 0:
                log.error("failed to stop monitor for %d: %d %s" % (nsr_data['nsseq'], monitor_result, str(monitor_response)))
                if e2e_log:
                    e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_FAIL,
                                tmsg_body="NS 모니터링 종료 요청 실패\n원인: %d %s" % (monitor_result, monitor_response))
                # return monitor_result, monitor_response

        # request to finish VNFs
        for vnf in nsr_data['vnfs']:
            result, data = _finish_vnf_using_ktvnfm(mydb, server_id, vnf['vdus'], e2e_log)
            if result < 0:
                log.error("failed to finsih VNF %s: %d %s" % (vnf['name'], result, data))
                raise Exception("failed to finsih VNF %s: %d %s" % (vnf['name'], result, data))

        # Delete VIM resources
        time.sleep(10)
        result, vims = get_vim_connector(mydb, nsr_data['vimseq'])
        if result < 0:
            log.error("nfvo.delete_nsr_thread() error. vim not found")
            raise Exception("Failed to establish a connection to VIM: %d %s" % (result, vims))
        myvim = vims.values()[0]

        result, stack_uuid = myvim.delete_heat_stack_v4(nsr_data['uuid'], nsr_data['name'])
        if result == -HTTP_Not_Found:
            log.error("Not exists. Just Delete DB Records")
        elif result < 0:
            log.error("failed to delete stack from Heat because of " + stack_uuid)
            if result != -HTTP_Not_Found:
                raise Exception("Failed to delete NS virtual resource (Heat stack): %d %s" % (result, stack_uuid))

    except Exception, e:
        log.exception("Exception: %s" % str(e))
        if e2e_log:
            e2e_log.job('Virtual Resource 삭제', CONST_TRESULT_FAIL,
                        tmsg_body="Heat API: Delete Stack %s %s\nCause:%s" % (str(nsr_data.get('uuid')), nsr_data.get('name'), str(e)))

        return -HTTP_Internal_Server_Error, "Exception: %s" % str(e)

    if e2e_log:
        e2e_log.job('Virtual Resource 삭제', CONST_TRESULT_SUCC,
                    tmsg_body="Heat API: Delete Stack %s %s" % (str(nsr_data.get('uuid')), nsr_data.get('name')))

    return 200, 'Resources for NSR Deleted'


def _restore_nsr_reprov(mydb, rlt_dict, instance_scenario_name, instance_scenario_description, customer_dict, e2e_log=None):
    log_info_message = "[Reprovisioning][NS] Started (Name: %s)" % instance_scenario_name
    log.info(log_info_message.center(80, '='))

    try:
        # update status
        rlt_dict['status'] = 'Parsing'
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.RST_parsing)

        result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=customer_dict['server_id'])
        if result < 0:
            raise Exception("Cannot establish One-Box Agent Connector")
        elif result > 1:
            raise Exception("Several One-Box Agents available, must be identify")

        ob_agent = ob_agents.values()[0]
        try_cnt = 0

        while try_cnt < 3:
            result, server_info = ob_agent.get_onebox_info(None)
            if result < 0:
                raise Exception("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))

            if server_info.get("public_ip", None):
                break
            else:
                try_cnt += 1
                time.sleep(10)
        else:
            raise Exception("Failed to get One-Box Info from OBA")

        log.debug("_____ [[Reprovisioning][NS]] Get One-Box Info = %s" % server_info)

        vnf_name_list_utm = []
        for vnf in rlt_dict["vnfs"]:
            if vnf["nfsubcategory"] == "UTM":
                vnf_name_list_utm.append(vnf["name"])

        # server_info의 WAN 과 rlt_backup 의 WAN 갯수가 같은지 확인....다르면 안되는데....rlt_backup 재구성해서 허용해주기로...
        if "wan_list" in server_info:
            wan_count = len(server_info["wan_list"])

            rlt_wan_count = 0
            for param in rlt_dict["parameters"]:
                if param["name"].find("RPARM_redFixedIp") >= 0:
                    rlt_wan_count += 1
            log.debug("_____####_____ server_info WAN 갯수 : %d, rlt_backup WAN 갯수 : %d" % (wan_count, rlt_wan_count))

            # BEGIN : 갯수가 다른경우 rlt_backup >> template, parameter 재구성 ######################################################################
            if rlt_wan_count != wan_count:
                log.debug("_____ [rlt_backup 재구성 BEGIN] 0. server_info WAN 갯수 : %d, rlt_backup WAN 갯수 : %d" % (wan_count, rlt_wan_count))
                log.debug("_____ [rlt_backup 재구성] 1. wan_list 데이타 보정작업")
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
                            wan["public_gw_ip"] = "NA"

                # Active/Standby 를 정하기 위해 기존 데이타에서 Active인 WAN을 찾는다.
                public_nic = server_info.get("public_nic", "eth0")

                r_num = 0
                for wan in server_info["wan_list"]:
                    if wan["nic"] == public_nic:
                        wan["status"] = "A"
                    else:
                        wan["status"] = "S"

                    # wan_list 순서대로 R0~N 주는 방식으로 변경처리.
                    wan["name"] = "R"+ str(r_num)
                    r_num += 1

                    # public_ip_dhcp 항목을 ipalloc_mode_public 형태로 변경처리
                    if wan['public_ip_dhcp']:
                        wan['ipalloc_mode_public'] = "DHCP"
                    else:
                        wan['ipalloc_mode_public'] = "STATIC"

                result, nsd_data = orch_dbm.get_nsd_id(mydb, rlt_dict["nscatseq"])

                wan_dels = _get_wan_dels_by_list(server_info["wan_list"])
                log.debug("_____ [rlt_backup 재구성] 2. clean_parameters > get_wan_dels = %s " % wan_dels)
                nsd_data['parameters'] = common_manager.clean_parameters(nsd_data['parameters'], wan_dels)

                # 기존 RLT의 Parameters의 value를 새로 만드는 Parameters에 부어 넣는다.
                # WAN (red) 을 제외한 다른 Parameter의 값을 채우기위한 작업 > 변경된 WAN 포트 정보 아래 로직에서 모든 WAN 포트 정보를 업데이트 처리한다.
                for param1 in nsd_data['parameters']:
                    for param2 in rlt_dict['parameters']:
                        if param1["name"] == param2["name"]:
                            param1["value"] = param2["value"]
                            break
                # RLT Parameters를 새로 만든 것으로 교체한다.
                rlt_dict['parameters'] = nsd_data['parameters']

                # WAN Port 관련 rlt paramters value 작업
                # 변경된 WAN 관련 Parameter의 value를 새로 채운다.
                common_manager.set_paramters_of_wan(vnf_name_list_utm, rlt_dict["parameters"], server_info["wan_list"])

                log.debug("_____ [rlt_backup 재구성] 3. 보정된 RLT의 Parameters : %s" % rlt_dict['parameters'])

                # cps 재구성
                for vnf in rlt_dict["vnfs"]:
                    for vnfd in nsd_data["vnfs"]:
                        if vnf["name"] == vnfd["name"]:
                            for vdu in vnf["vdus"]:
                                for vdud in vnfd["vdus"]:
                                    if vdu["name"] == vdud["name"]:
                                        # 추가/삭제 항목이 있으면 적용
                                        # 삭제
                                        length = len(vdu["cps"])
                                        for idx in range(length-1, -1, -1):
                                            cp = vdu["cps"][idx]
                                            for cpd in vdud["cps"]:
                                                if cpd["name"] == cp["name"]:
                                                    break
                                            else:
                                                vdu["cps"].remove(cp)
                                        # 추가
                                        length = len(vdu["cps"])
                                        for cpd in vdud["cps"]:
                                            for idx in range(length-1, -1, -1):
                                                cp = vdu["cps"][idx]
                                                if cpd["name"] == cp["name"]:
                                                    break
                                            else:
                                                vdu["cps"].append(cpd)
                                        break
                            break

                rt_dict = _clean_wan_resourcetemplate(nsd_data['resourcetemplate'], wan_dels)
                # 정리된 resourcetemplate dictionary 객체를 다시 yaml 포맷 문자열로 변경
                ns_hot_result, ns_hot_value = compose_nsd_hot(nsd_data['name'], [rt_dict])
                if ns_hot_result < 0:
                    log.error("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
                    raise Exception("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
                rlt_dict['resourcetemplate'] = ns_hot_value
                log.debug("_____ [rlt_backup 재구성] 4. resourcetemplate : %s" % ns_hot_value)

                # 기존 wan 데이타 삭제 후 다시 저장
                wan_result, wan_content = orch_dbm.delete_server_wan(mydb, {"serverseq":customer_dict['server_id']}, kind="R")
                if wan_result < 0:
                    return wan_result, wan_content

                # 변경된 wan 데이타 저장처리
                for wan in server_info["wan_list"]:
                    wan["serverseq"] = customer_dict['server_id']
                    wan["onebox_id"] = customer_dict['server_name']

                    # mode가 대문자로 오는경우 처리 --> 소문자로 변경
                    wan["mode"] = str(wan["mode"]).lower()

                    wan_result, wan_content = orch_dbm.insert_server_wan(mydb, wan)
                    if wan_result < 0:
                        return wan_result, wan_content
                log.debug("_____ [rlt_backup 재구성 END] 5. 기존 wan 데이타 삭제 후 다시 저장 완료")
            # END : 갯수가 다른경우 rlt_backup >> template, parameter 재구성 ######################################################################

        vnf_name_list = []
        for vnf in rlt_dict['vnfs']:
            vnf_name_list.append(vnf['name'])

        # backup rlt의 wan 정보 변경
        log.debug("[_RESTORE_NSR_REPROV - %s] _____ 백업 RLT Parameters(WAN) 현행화 _____ " % customer_dict['server_name'])
        _set_wan_parameter_of_backup(vnf_name_list, rlt_dict["parameters"], server_info)

        log.debug("[_RESTORE_NSR_REPROV - %s] _____ SYNC_VNF_IMAGE_VERSION _____ " % customer_dict['server_name'])
        sync_vnf_image_version(mydb, rlt_dict, e2e_log)

        iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_name_list, rlt_dict['parameters'])

        if iparm_result < 0:
            log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
            raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))

        # Step.1 Create VMs Using Heat
        log.debug("[Reprovisioning][NS] 1. Create VMs Using the Heat")
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.RST_creatingvr)

        # Get VIM Connector
        result, vims = get_vim_connector(mydb, customer_dict['vim_id'])
        if result < 0:
            log.error("[Reprovisioning][NS]  : Error, failed to connect to VIM")
            update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR)
            raise Exception("Failed to establish a connection to VIM: %d %s" % (result, vims))
        elif result > 1:
            log.error("[Reprovisioning][NS]  : Error, Several VIMs available, must be identify the target VIM")
            update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR)
            raise Exception("Failed to establish a connection to VIM: Several VIMs available, must be identify")

        myvim = vims.values()[0]
        rlt_dict['vimseq'] = myvim['id']
        rlt_dict['vim_tenant_name'] = myvim['tenant']

        # Compose Heat Parameters
        template_param_list = []
        for param in rlt_dict['parameters']:
            if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
                template_param_list.append(param)

        # Create VMs using the Heat
        if e2e_log:
            e2e_log.job('NS Virtual Resource 생성', CONST_TRESULT_NONE,
                        tmsg_body="HEAT_API: Create Heat Stack, Stack Name: %s, HOT: %s" % (
                        instance_scenario_name, json.dumps(rlt_dict['resourcetemplate'], indent=4)))

        time.sleep(10)
        stack_result, stack_data = _new_nsr_create_vm(myvim, rlt_dict, instance_scenario_name, rlt_dict['resourcetemplatetype'],
                                                      rlt_dict['resourcetemplate'], template_param_list)
        if stack_result < 0:
            update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR)
            if e2e_log:
                e2e_log.job('NS Virtual Resource 생성', CONST_TRESULT_FAIL,
                            tmsg_body="HEAT_API: Create Heat Stack, Stack Name: %s\nResult: Fail\nHOT: %s" % (
                            instance_scenario_name, json.dumps(rlt_dict['resourcetemplate'], indent=4)))

            raise Exception("Failed to create VMs for VNFs: %d %s" % (stack_result, stack_data))

        if e2e_log:
            e2e_log.job('NS Virtual Resource 생성', CONST_TRESULT_SUCC,
                        tmsg_body="HEAT_API: Create Heat Stack, Stack Name: %s\nResult: Success\nHOT: %s" % (
                        instance_scenario_name, json.dumps(rlt_dict['resourcetemplate'], indent=4)))
        log.debug("[Reprovisioning][NS] 1. Success")
        # Step.2 DB Insert: NSR
        log.debug("[Reprovisioning][NS] 2. Update DB Records for NS Instance")
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.RST_processingdb)

        if e2e_log:
            e2e_log.job('NS 복구 - DB Update', CONST_TRESULT_NONE, tmsg_body="Update NSR Data: %s" % (json.dumps(rlt_dict, indent=4)))

        # compose web url for each VDUs
        log.debug("[Reprovisioning][NS] 2.1 compose web url for each VDUs and VNF info")
        vnf_proc_result, vnf_proc_data = new_nsr_vnf_proc(rlt_dict)
        if vnf_proc_result < 0:
            log.warning("Failed to process vnf app information: %d %s" % (vnf_proc_result, vnf_proc_data))

        result, instance_id = orch_dbm.update_nsr_as_a_whole(mydb, instance_scenario_name, instance_scenario_description, rlt_dict)

        if result < 0:
            log.error("[Reprovisioning][NS]  : Error, failed to insert DB records %d %s" % (result, instance_id))
            update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR)

            if e2e_log:
                e2e_log.job('NS 복구 - DB Update', CONST_TRESULT_FAIL,
                            tmsg_body="Result:Fail, Cause: %s\nUpdate NSR Data: %s" % (instance_id, json.dumps(rlt_dict, indent=4)))

            return result, instance_id

        # 복구시 제거되어야 할 vnf[nfr 데이타]가 남아있는지 확인하고, 있으면 삭제처리.
        result, nsr_db_data = orch_dbm.get_nsr_id(mydb, rlt_dict["nsseq"])
        if result < 0:
            log.error("Failed to get nsr data %d %s" % (result, nsr_db_data))
            raise Exception("Failed to get nsr data %d %s" % (result, nsr_db_data))

        for vnf in nsr_db_data['vnfs']:
            vnf["del_flag"] = True
            for s_vnf in rlt_dict['vnfs']:
                if s_vnf['name'] == vnf['name']:
                    vnf["del_flag"] = False
                    break
        for vnf in nsr_db_data['vnfs']:
            if vnf["del_flag"]:
                result, data = orch_dbm.delete_nfr(mydb, {"nfseq": vnf["nfseq"]})
                if result < 0:
                    log.error("Failed to deleted vnf data %d %s" % (result, data))
                    raise Exception("Failed to deleted vnf data %d %s" % (result, data))
                log.debug("_____________deleted vnf : %s" % vnf["nfseq"])

        result, content = orch_dbm.delete_nsr_param(mydb, {"nsseq" : rlt_dict['nsseq']})
        if result < 0:
            raise Exception("failed to DB Delete of old NSR parameters: %d %s" %(result, content))

        result, content = orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])
        if result < 0:
            raise Exception("failed to DB Insert New NSR Params: %d %s" %(result, content))

        ur_result, ur_data = _update_rlt_data(mydb, rlt_dict, nsseq=rlt_dict['nsseq'])
        if ur_result < 0:
            log.error("Failed to update rlt data %d %s" % (ur_result, ur_data))
            raise Exception("Failed to update rlt data %d %s" % (ur_result, ur_data))

        if e2e_log:
            e2e_log.job('NS 복구 - DB Update', CONST_TRESULT_SUCC, tmsg_body="Result:Success\nUpdate NSR Data: %s" % (json.dumps(rlt_dict, indent=4)))

        log.debug("[Reprovisioning][NS] 2. Success")

        # Step.5 VNF Configuration
        log.debug("[Reprovisioning][NS] 3. VNF Configuration")
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.RST_configvnf)

        if e2e_log:
            e2e_log.job('VNF Configuration', CONST_TRESULT_NONE,
                        tmsg_body="Configuration Parameters:%s" % (json.dumps(rlt_dict['parameters'], indent=4)))

        vnf_confg_result, vnf_config_data = _new_nsr_vnf_conf(mydb, rlt_dict, customer_dict['server_id'], e2e_log)
        if vnf_confg_result < 0:
            log.error("[Reprovisioning][NS]   : Error, %d %s" % (vnf_confg_result, vnf_config_data))

            if e2e_log:
                e2e_log.job('VNF Configuration', CONST_TRESULT_FAIL,
                            tmsg_body="Result:Fail\nConfiguration Parameters:%s" % (json.dumps(rlt_dict['parameters'], indent=4)))

            raise Exception("Failed to init-config VNFs: %d %s" % (vnf_confg_result, vnf_config_data))

        if e2e_log:
            e2e_log.job('VNF Configuration', CONST_TRESULT_SUCC,
                        tmsg_body="Result:Success\nConfiguration Parameters:%s" % (json.dumps(rlt_dict['parameters'], indent=4)))

        log.debug("[Reprovisioning][NS] 3. Success")

        # Step.6 Verify NSR
        log.debug("[Reprovisioning][NS] 4. Test NS Instance")
        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.RST_testing)
        res, msg = _new_nsr_test(mydb, customer_dict['server_id'], rlt_dict)
        log.debug("[Reprovisioning][NS]   : Test Result = %d, %s" % (res, msg))
        if res < 0:
            error_txt = "NSR Test Failed %d %s" % (res, str(msg))
            log.error("[Reprovisioning][NS]  : Error, %s" % error_txt)
            raise Exception(error_txt)

        log.debug("[Reprovisioning][NS] 4. Success")

        # Step.7 Compose return data: NSR info
        #update_nsr_status(mydb, "R", nsr_data=nsr_data, nsr_status=NSRStatus.RUN)
        result, new_nsr_data = orch_dbm.get_nsr_id(mydb, instance_id)
        if result < 0:
            raise Exception("Failed to get updated NSR Info. from DB: %d %s" % (result, new_nsr_data))
        else:
            new_nsr_data['parameters'] = rlt_dict['parameters']

    except Exception, e:
        log.exception("Exception: %s" % str(e))

        update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR)

        if e2e_log:
            e2e_log.job('NS 복구 - 재프로비저닝', CONST_TRESULT_FAIL, tmsg_body="Result:Fail, Cause:%s" % (str(e)))

        return -HTTP_Internal_Server_Error, "Exception: %s" % str(e)

    log_info_message = "Reprovisioning NS Completed (%s) Status = %s" % (str(instance_id), rlt_dict['status'])
    log.info(log_info_message.center(80, '='))

    if e2e_log:
        e2e_log.job('NS 복구 - 재프로비저닝', CONST_TRESULT_SUCC, tmsg_body="Result:Success, NSR:%s" % (json.dumps(new_nsr_data, indent=4)))

    return result, new_nsr_data

def _restore_nsr_check_customer(mydb, customer_id, nsr_id):
    result, customer_dict = orch_dbm.get_customer_id(mydb, customer_id)

    if result < 0:
        log.error("[Restore][NS]  : Error, failed to get customer info from DB %d %s" % (result, customer_dict))
        return -HTTP_Internal_Server_Error, "Failed to get Customer Info. from DB: %d %s" % (result, customer_dict)
    elif result == 0:
        log.error("[Restore][NS]  : Error, Customer Not Found")
        return -HTTP_Not_Found, "Failed to get Customer Info. from DB: Customer not found"

    result, customer_inventory = orch_dbm.get_customer_resources(mydb, customer_id)
    if result <= 0:
        log.error("[Restore][NS]  : Error, failed to get resource info of the customer %s" % (str(customer_id)))
        return -HTTP_Internal_Server_Error, "failed to get resource info of the customer %s" % (str(customer_id))

    for item in customer_inventory:
        if item['resource_type'] == 'server' and str(item['nsseq']) == str(nsr_id):
            log.debug("[Provisioning][NS] server info = %s" % str(item))

            customer_dict['server_name'] = item['servername']
            customer_dict['server_id'] = item['serverseq']
            customer_dict['server_org'] = item.get('orgnamescode')
            customer_dict['server_action'] = item['action']
            customer_dict['server_status'] = item['status']
            customer_dict['server_uuid'] = item['serveruuid']
            customer_dict['server_mgmt_ip'] = item['mgmtip']
            customer_dict['server_public_ip'] = item['publicip']
            customer_dict['server_onebox_id'] = item['onebox_id']

            server_check_result, server_check_msg = _check_server_restoreavailable(item)
            if server_check_result < 0:
                return -HTTP_Bad_Request, "Cannot perform provisioning with the server: %d %s" % (server_check_result, server_check_msg)
            break

    for item in customer_inventory:
        if item['resource_type'] == 'vim' and item['serverseq'] == customer_dict['server_id']:
            customer_dict['vim_id'] = item['vimseq']
            break

    if customer_dict.get('vim_id') is None:
        log.error("[Provisioning][NS]  : Error, VIM Not Found for the Customer %s" % str(customer_id))
        return -HTTP_Internal_Server_Error, "Failed to get VIM Info."

    return 200, customer_dict

def _restore_nsr_get_backup_data(mydb, nsr_id, request):
    nsr_data = None
    target_dict = {'nsseq': nsr_id, 'category': "ns"}
    if 'backup_id' in request:
        target_dict['backupseq'] = request['backup_id']
        bn_result, bn_data = orch_dbm.get_backup_history_id(mydb, target_dict)
    else:
        bn_result, bn_data = orch_dbm.get_backup_history_lastone(mydb, target_dict)

    if bn_result <= 0:
        log.warning("_restore_nsr_get_backup_data(): failed to get backup history for %s" % str(target_dict))
    else:
        n_result, n_data = _get_nsr_backup_data(bn_data)
        if n_result <= 0:
            log.warning("_restore_nsr_get_backup_data(): failed to get backup data for nsr %s" % str(nsr_id))
        else:
            nsr_data = n_data
            nsr_data['backupseq'] = bn_data['backupseq']
            #log.debug("[HJC] backupseq %s" % (str(nsr_data['backupseq'])))

    # 3-2. if no backup file, use NS record
    if nsr_data is None:
        log.warning("_restore_nsr_get_backup_data() error. No backup file found. Just recreating NSR")
        log.debug("_restore_nsr_get_backup_data() request: %s" % str(request))

        if not request.get('force_restore', False):
            return -HTTP_Internal_Server_Error, "No Backup File found"

        # 백업데이타가 없고, 강제로 복구진행할때 rlt로 진행하도록 수정처리
        result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_id)
        if result < 0:
            log.error("_restore_nsr_get_backup_data() error. Error getting NSR info from database")
            return result, rlt_data
        elif result == 0:
            log.error("_restore_nsr_get_backup_data() error. Instance not found")
            return -HTTP_Not_Found, rlt_data

        nsr_data = rlt_data["rlt"]

    return 200, nsr_data

def start_sdn_switch(mydb, sdn_switch_bw, customer_id=None):
    customer_ename = None
    if customer_id:
        result, content = orch_dbm.get_customer_id(mydb, customer_id)
        if result < 0:
            log.error("failed to get Customer Info with id: %s" % str(customer_id))
        else:
            customer_ename = content['customerename']

    mygo = goconnector.goconnector("SDN", BASE_URL_SDN_SWITCH)
    result, content = mygo.start_sdnswitch(customer_ename, sdn_switch_bw)
    if result < 0:
        log.error("Failed to set SDN Switch: %s(%d): %d %s" % (str(customer_ename), sdn_switch_bw, result, content))

    return result, content

def end_sdn_switch(mydb, nsr_id):
    customer_ename = None

    nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr_id)
    if nsr_result < 0:
        log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
        return nsr_result, nsr_data

    if nsr_data.get('customerseq'):
        result, content = orch_dbm.get_customer_id(mydb, nsr_data.get('customerseq'))
        if result < 0:
            log.error("failed to get Customer Info with id: %s" % str(nsr_data.get('customerseq')))
        else:
            customer_ename = content['customerename']

    mygo = goconnector.goconnector("SDN", BASE_URL_SDN_SWITCH)
    result, content = mygo.finish_sdnswitch()
    if result < 0:
        log.error("Failed to set SDN Switch: %s: %d %s" % (str(customer_ename), result, content))

    return result, content

def update_nsr_for_go(mydb, nsr_id, storage_amount=-1, sdn_switch_bw=-1):
    #log.debug("[HJC] IN: storage= %d, sdn_bw=%d" % (storage_amount, sdn_switch_bw))
    customer_ename = None

    nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr_id)
    if nsr_result < 0:
        log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
        return nsr_result, nsr_data

    if nsr_data.get('customerseq'):
        result, content = orch_dbm.get_customer_id(mydb, nsr_data.get('customerseq'))
        if result < 0:
            log.error("failed to get Customer Info with id: %s" % str(nsr_data.get('customerseq')))
        else:
            customer_ename = content['customerename']

    # Update GiGA Storage
    if storage_amount > 0:
        mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_STORAGE)
        result, content = mygo.update_storage(storage_amount)
        if result <= 0:
            log.warning("failed to update GiGA Storage: %d %s" % (result, content))
        else:
            log.debug("succeed to udpate GiGA Storage: %d %s" % (result, content))
            # TODO Update DB Values for record
            for vnf in nsr_data['vnfs']:
                if vnf['name'] == "GiGA-Storage":
                    pre_report = vnf.get('report')
                    if pre_report is not None and len(pre_report) > 0:
                        for r in pre_report:
                            if r['name'] == 'storage_capacity': r['value'] = storage_amount
                            if r['name'] == 'traffic_limit': r['value'] = sdn_switch_bw
                    orch_dbm.update_nsr_vnf_report(mydb, pre_report)
                    break

                    # Update SDN Switch
    if sdn_switch_bw > 0:
        mygo = goconnector.goconnector("SDN", BASE_URL_SDN_SWITCH)
        result, content = mygo.update_sdnswitch(sdn_switch_bw)
        if result < 0:
            log.warning("failed to update SDN Switch: %d %s" % (result, content))
        else:
            log.debug("succeed to update SDN Switch: %d %s" % (result, content))

    return 200, {'nsseq': nsr_id}

def get_nsr_monitor(mydb, nsr_id):
    #log.debug("[HJC] IN")
    result, instanceDict = orch_dbm.get_nsr_id(mydb, nsr_id)
    if result <= 0:
        log.error("failed to get NSR Info. from DB: %d %s" % (result, instanceDict))
        return result, instanceDict

    # log.debug("[HJC] NSR Info: %s" %str(instanceDict))

    result, serverDict = orch_dbm.get_server_filters(mydb, {'nsseq': nsr_id})
    if result < 0:
        log.error("failed to get Server Info.: %d %s" % (result, serverDict))
        return result, serverDict

    # log.debug("[HJC] Server Info: %s" %str(serverDict))

    customer_id = instanceDict['customerseq']
    onebox_id = serverDict[0]['onebox_id']

    mon_data = {}

    # get NSR NFV Monitor Info
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.eror("failed to get a connection to Montior")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

    log.debug("[HJC] Succeed to get a connection to Monitor")

    nm_data = {}
    nm_result, nm_content = monitor.get_nsr_simple_data(onebox_id)
    if nm_result < 0:
        log.error("failed to get monitoring data from NFV Monitoring System: %d %s" % (nm_result, nm_content))
    else:
        #log.debug("[HJC] NSR Monitor Data: %s" % str(nm_content))
        nm_data = nm_content['onebox']
        vm_data = nm_content['vnf']

    if 'lan' in nm_data:
        nm_data['lan']['tx'] = nm_data['lan'].get('tx', 0) / NWBW_UNIT
        nm_data['lan']['rx'] = nm_data['lan'].get('rx', 0) / NWBW_UNIT
    if 'wan' in nm_data:
        nm_data['wan']['tx'] = nm_data['wan'].get('tx', 0) / NWBW_UNIT
        nm_data['wan']['rx'] = nm_data['wan'].get('rx', 0) / NWBW_UNIT

    mon_data['onebox'] = nm_data
    vnf_data = []
    # get NSR GiGA Office Monitor Info
    for vnf_dict in instanceDict['vnfs']:
        #log.debug("[HJC] NSR VNF Info: %s" % str(vnf_dict))
        if vnf_dict['name'].find("Storage") >= 0:
            log.debug("[HJC] GiGA Storage")
            storage_info = {'name': vnf_dict['name'], 'display_name': vnf_dict.get('display_name'), 'status': "OK"}

            # Get Quota ID
            quota_id = None
            p_result, p_content = orch_dbm.get_nsr_params(mydb, nsr_id)
            if p_result > 0:
                for param in p_content:
                    if param['name'].find("quotaid_GiGA-Storage") >= 0:
                        quota_id = param['value']
                        break

            # Get GiGA-Storage
            '''
            mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_STORAGE)

            if quota_id:
                result, content = mygo.get_storage(quota_id)
            else:
                result, content = mygo.get_storage()

            if result <= 0:
                log.error("failed to get GiGA Storage: %d %s" %(result, content))
                storage_info['status'] = "NOK"
            else:
                storage_info['status'] = content.get('status', "OK")

                if 'capacity' in content:
                    storage_info['capacity'] = content['capacity']
                    if 'usage' in content: storage_info['usage'] = content['usage']*100/content['capacity']
                    if storage_info['capacity'] <= 1000:
                        storage_info['status'] = 'OVER'
                        storage_info['usage'] = 80
                        log.debug("[HJC] OFF: Storage M Info: %s" %str(storage_info))
                    else:
                        storage_info['status'] = 'OK'
                        log.debug("[HJC] OK: Storage M Info: %s" %str(storage_info))
            '''
            storage_info['stauts'] = "OK"
            storage_info['capacity'] = 1000
            storage_info['usage'] = 5

            vnf_data.append(storage_info)
        elif (vnf_dict['name'].find('UTM') >= 0 or vnf_dict['name'].find('KT-VNF') >= 0):
            utm_info = {'name': vnf_dict['name'], 'display_name': vnf_dict.get('display_name'), 'status': "OK"}
            for vm in vm_data:
                if (vm['name'].find('UTM') >= 0 or vm['name'].find('KT-VNF') >= 0):
                    utm_info['status'] = vm.get('status', "UNKNOWN")
                    if 'lan' in vm:
                        vm['lan']['tx'] = vm['lan'].get('tx', 0) / NWBW_UNIT
                        vm['lan']['rx'] = vm['lan'].get('rx', 0) / NWBW_UNIT
                        utm_info['lan'] = vm['lan']
                    if 'wan' in vm:
                        vm['wan']['tx'] = vm['wan'].get('tx', 0) / NWBW_UNIT
                        vm['wan']['rx'] = vm['wan'].get('rx', 0) / NWBW_UNIT
                        utm_info['wan'] = vm['wan']
                    if 'cpu_load' in vm: utm_info['cpu_load'] = vm['cpu_load']
                    if 'usage' in vm: utm_info['usage'] = vm['usage']
                    break
            vnf_data.append(utm_info)
        elif vnf_dict['name'].find('XMS') >= 0:
            xms_info = {'name': vnf_dict['name'], 'display_name': vnf_dict.get('display_name'), 'status': "OK"}
            for vm in vm_data:
                if vm['name'].find('XMS') >= 0:
                    xms_info['status'] = vm.get('status', "UNKNOWN")
                    if 'lan' in vm:
                        vm['lan']['tx'] = vm['lan'].get('tx', 0) / NWBW_UNIT
                        vm['lan']['rx'] = vm['lan'].get('rx', 0) / NWBW_UNIT
                        xms_info['lan'] = vm['lan']
                    if 'wan' in vm:
                        vm['wan']['tx'] = vm['wan'].get('tx', 0) / NWBW_UNIT
                        vm['wan']['rx'] = vm['wan'].get('rx', 0) / NWBW_UNIT
                        xms_info['wan'] = vm['wan']
                    if 'cpu_load' in vm: xms_info['cpu_load'] = vm['cpu_load']
                    if 'usage' in vm: xms_info['usage'] = vm['usage']
                    break
            vnf_data.append(xms_info)
        elif vnf_dict['name'].find('WIMS') >= 0:
            wims_info = {'name': vnf_dict['name'], 'display_name': vnf_dict.get('display_name'), 'status': "OK"}
            for vm in vm_data:
                if vm['name'].find('WIMS') >= 0:
                    wims_info['status'] = vm.get('status', "UNKNOWN")
                    if 'lan' in vm:
                        vm['lan']['tx'] = vm['lan'].get('tx', 0) / NWBW_UNIT
                        vm['lan']['rx'] = vm['lan'].get('rx', 0) / NWBW_UNIT
                        wims_info['lan'] = vm['lan']
                    if 'wan' in vm:
                        vm['wan']['tx'] = vm['wan'].get('tx', 0) / NWBW_UNIT
                        vm['wan']['rx'] = vm['wan'].get('rx', 0) / NWBW_UNIT
                        wims_info['wan'] = vm['wan']
                    if 'cpu_load' in vm: wims_info['cpu_load'] = vm['cpu_load']
                    if 'usage' in vm: wims_info['usage'] = vm['usage']
                    break
            vnf_data.append(wims_info)
        elif vnf_dict['name'].find('PBX') >= 0:
            pbx_info = {'name': vnf_dict['name'], 'display_name': vnf_dict.get('display_name'), 'status': "OK"}
            for vm in vm_data:
                if vm['name'].find('PBX') >= 0:
                    pbx_info['status'] = vm.get('status', "UNKNOWN")
                    if 'lan' in vm:
                        vm['lan']['tx'] = vm['lan'].get('tx', 0) / NWBW_UNIT
                        vm['lan']['rx'] = vm['lan'].get('rx', 0) / NWBW_UNIT
                        pbx_info['lan'] = vm['lan']
                    if 'wan' in vm:
                        vm['wan']['tx'] = vm['wan'].get('tx', 0) / NWBW_UNIT
                        vm['wan']['rx'] = vm['wan'].get('rx', 0) / NWBW_UNIT
                        pbx_info['wan'] = vm['wan']
                    if 'cpu_load' in vm: pbx_info['cpu_load'] = vm['cpu_load']
                    if 'usage' in vm: pbx_info['usage'] = vm['usage']
                    break
            vnf_data.append(pbx_info)
        elif vnf_dict['name'].find('GiGA-PC') >= 0:
            gpc_info = {'name': vnf_dict['name'], 'display_name': vnf_dict.get('display_name'), 'status': "OK"}
            for vm in vm_data:
                if vm['name'].find('GiGA-PC') >= 0:
                    gpc_info['status'] = vm.get('status', "UNKNOWN")
                    if 'lan' in vm:
                        vm['lan']['tx'] = vm['lan'].get('tx', 0) / NWBW_UNIT
                        vm['lan']['rx'] = vm['lan'].get('rx', 0) / NWBW_UNIT
                        gpc_info['lan'] = vm['lan']
                    if 'wan' in vm:
                        vm['wan']['tx'] = vm['wan'].get('tx', 0) / NWBW_UNIT
                        vm['wan']['rx'] = vm['wan'].get('rx', 0) / NWBW_UNIT
                        gpc_info['wan'] = vm['wan']
                    if 'cpu_load' in vm: gpc_info['cpu_load'] = vm['cpu_load']
                    if 'usage' in vm: gpc_info['usage'] = vm['usage']
                    break
            vnf_data.append(gpc_info)
        elif vnf_dict['name'].find('GiGA-Server') >= 0:
            gserver_info = {'name': vnf_dict['name'], 'display_name': vnf_dict.get('display_name'), 'status': "OK"}
            for vm in vm_data:
                if vm['name'].find('GiGA-Server') >= 0:
                    gserver_info['status'] = vm.get('status', "UNKNOWN")
                    if 'lan' in vm:
                        vm['lan']['tx'] = vm['lan'].get('tx', 0) / NWBW_UNIT
                        vm['lan']['rx'] = vm['lan'].get('rx', 0) / NWBW_UNIT
                        gserver_info['lan'] = vm['lan']
                    if 'wan' in vm:
                        vm['wan']['tx'] = vm['wan'].get('tx', 0) / NWBW_UNIT
                        vm['wan']['rx'] = vm['wan'].get('rx', 0) / NWBW_UNIT
                        gserver_info['wan'] = vm['wan']
                    if 'cpu_load' in vm: gserver_info['cpu_load'] = vm['cpu_load']
                    if 'usage' in vm: gserver_info['usage'] = vm['usage']
                    break
            vnf_data.append(gserver_info)
        else:
            log.warning("Unknown Solution: %s" % vnf_dict.get('name', "NONE"))

    log.debug("[HJC] SDN Switch")
    customer_ename = None

    if customer_id:
        result, content = orch_dbm.get_customer_id(mydb, customer_id)
        if result < 0:
            log.error("failed to get Customer Info with id: %s" % str(customer_id))
        else:
            customer_ename = content['customerename']
            mon_data['customer'] = {'customername': content['customername'], 'detailaddr': content.get('detailaddr'), 'hp_num': content.get('hp_num')}

    sdn_info = {'name': 'SDN Switch', 'display_name': 'SDN Switch', 'status': "OK"}
    #mygo = goconnector.goconnector("SDN", BASE_URL_SDN_SWITCH)
    log.debug("[HJC] Customer E-Name: %s" % customer_ename)
    #result, content = mygo.get_sdnswitch()
    result = 200
    content = {'usage': "30", 'bandwidth': "100"}
    if result < 0:
        log.error("failed to get SDN Switch: %d %s" % (result, content))
        sdn_info['status'] = "NOK"
    else:
        if 'usage' in content: sdn_info['usage'] = content['usage']
        if 'bandwidth' in content:
            sdn_info['bandwidth'] = content['bandwidth']

        if 'usage' in content and 'bandwidth' in content:
            sdn_info['lan'] = {'tx': int(content['bandwidth']) * int(content['usage']) / 100}

        if 'usage' in sdn_info:
            if int(sdn_info['usage']) > 80:
                sdn_info['status'] = content.get('status', "OVER")
            else:
                sdn_info['status'] = content.get('status', "OK")
        else:
            sdn_info['status'] = content.get('status', "UNKNOWN")

    vnf_data.append(sdn_info)

    mon_data['vnf'] = vnf_data

    #log.debug("[HJC] OUT: %s" % str(mon_data))
    return 200, mon_data

def get_sdn_report_info():
    mygo = goconnector.goconnector("SDN", BASE_URL_SDN_SWITCH)
    result, content = mygo.get_sdnswitch()
    if result < 0:
        log.error("failed to get SDN Switch: %d %s" % (result, content))
        result = 200
        content = {'usage': "30", 'bandwidth':"100"}
        return result, content
    else:
        sdn_info = {}
        sdn_info['usage'] = content.get('usage', "N/A")
        sdn_info['bandwidth'] = content.get('bandwidth', "N/A")

        return 200, sdn_info

def _delete_nsr_GigaOffice(mydb, vnf_dict, server_id, nsr_id, e2e_log=None):
    if vnf_dict is None:
        log.warning("No VNF Info Given")
        return -HTTP_Bad_Request, "No VNF Info"

    #log.debug("[HJC] IN with %s" % str(vnf_dict))
    try:
        if vnf_dict['name'].find("Storage"):
            log.debug("[HJC] GiGA Storage")
            # Get Quota ID
            quota_id = None
            p_result, p_content = orch_dbm.get_nsr_params(mydb, nsr_id)
            if p_result > 0:
                for param in p_content:
                    if param['name'].find("quotaid_GiGA-Storage") >= 0:
                        quota_id = param['value']
                        break

            # Get GiGA-Storage
            mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_STORAGE)

            if quota_id:
                result, content = mygo.finish_storage(quota_id)
            else:
                result, content = mygo.finish_storage()

            if result < 0:
                log.error("failed to finish GiGA Storage: %d %s" % (result, content))
                return result, content
            log.debug("[HJC] SDN Switch")
            mygo = goconnector.goconnector("GOName", BASE_URL_SDN_SWITCH)
            result, content = mygo.finish_sdnswitch()
            if result < 0:
                log.error("failed to finish SDN Switch: %d %s" % (result, content))
                return result, content
        elif vnf_dict['name'].find("PC"):
            log.debug("[HJC] GiGA PC")
            mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_PC)
            result, content = mygo.finish_pc()
            if result < 0:
                log.error("failed to finish GiGA PC: %d %s" % (result, content))
                return result, content
        elif vnf_dict['name'].find("Server"):
            log.debug("[HJC] GiGA Server")
            mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_SERVER)
            result, content = mygo.finish_server()
            if result < 0:
                log.error("failed to finish GiGA Server: %d %s" % (result, content))
                return result, content
        else:
            log.warning("Not supported GiGA-Office Solution")

    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -500, "Exception: %s" % str(e)

    return 200, "OK"

def test_set_go_sdn(mydb, storage_amount=-1, sdn_switch_bw=-1):
    #log.debug("[HJC] IN")

    # Set GiGA Storage
    if storage_amount > 0:
        mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_STORAGE)
        result, content = mygo.update_storage(storage_amount)
        if result <= 0:
            log.warning("failed to update GiGA Storage: %d %s" % (result, content))
        else:
            log.debug("succeed to udpate GiGA Storage: %d %s" % (result, content))

    # Update SDN Switch
    if sdn_switch_bw > 0:
        mygo = goconnector.goconnector("SDN", BASE_URL_SDN_SWITCH)
        result, content = mygo.update_sdnswitch(sdn_switch_bw)
        if result < 0:
            log.warning("failed to update SDN Switch: %d %s" % (result, content))
        else:
            log.debug("succeed to update SDN Switch: %d %s" % (result, content))

    return 200, {'result': str(result), 'message': str(content)}

def test_get_go(mydb, quota_id=None):
    #log.debug("[HJC] IN")

    storage_info = {'name': 'GiGA Storage', 'display_name': 'GiGA Storage'}
    mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_STORAGE)
    if quota_id is None or len(quota_id) < 1:
        result, content = mygo.get_storage()
    else:
        result, content = mygo.get_storage(quota_id)

    if result <= 0:
        log.error("failed to get GiGA Storage: %d %s" % (result, content))
        return result, content
    else:
        storage_info['status'] = content.get('status', "UNKNOWN")
        if 'usage' in content: storage_info['usage'] = content['usage']
        if 'capacity' in content: storage_info['capacity'] = content['capacity']

    return 200, storage_info

def test_get_sdn(mydb, sdn_id=None):
    #log.debug("[HJC] IN")

    sdn_info = {'name': 'SDN Switch', 'display_name': 'SDN Switch'}
    mygo = goconnector.goconnector("SDN", BASE_URL_SDN_SWITCH)
    if sdn_id is None or len(sdn_id) < 1:
        result, content = mygo.get_sdnswitch()
    else:
        result, content = mygo.get_sdnswitch(sdn_id)

    if result < 0:
        log.error("failed to get SDN Switch: %d %s" % (result, content))
        sdn_info['status'] = content.get('status', "UNKNOWN")
    else:
        log.debug("response from SDN: %s" % str(content))
        sdn_info['status'] = content.get('status', "OK")
        if 'usage' in content: sdn_info['usage'] = content['usage']
        if 'bandwidth' in content: sdn_info['bandwidth'] = content['bandwidth']

    return 200, sdn_info


def update_nsr_for_vnfs(mydb, nsr_id, http_content, tid=None, tpath="", use_thread=True):
    """
    이미 Provisioning된 NSR 에서 VNF를 추가 및 삭제해서 다시 Provisioning 하기 위해 사용.
    :param mydb:
    :param nsr_id:
    :param http_content:
    :param tid:
    :param tpath:
    :param use_thread:
    :return:
    """

    e2e_log = None
    try:
        try:
            if not tid:
                e2e_log = e2elogger(tname='NS Update', tmodule='orch-f', tpath="orch_ns-update")
            else:
                e2e_log = e2elogger(tname='NS Update', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_ns-update")
        except Exception, e:
            log.error("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('NS Update API 수신 처리 시작', CONST_TRESULT_SUCC, tmsg_body="NSR ID: %s\n Request Body: %s" % (str(nsr_id), http_content))

        # 1. Get RLT Data
        log.debug("[NS Update] _____1. Get RLT Data_____")
        result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_id)
        if result < 0:
            log.error("[Updating NSR][NS] : Error, failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

        if e2e_log:
            e2e_log.job('Get RLT Data', CONST_TRESULT_SUCC,
                        tmsg_body="RLT Data: rltseq: %d\n RLT: %s" % (rlt_data["rltseq"], json.dumps(rlt_data['rlt'], indent=4)))

        rlt_dict = rlt_data["rlt"]

        add_vnfs_param = None
        del_vnfs_param = None
        is_add_vnfs = False
        is_del_vnfs = False

        # 2. Delete del_vnf in RLT
        log.debug("[NS Update] _____2. Delete del_vnf in RLT_____")
        if "del_vnf" in http_content['update'] and http_content['update']['del_vnf'] is not None and len(http_content['update']['del_vnf']) > 0:
            is_del_vnfs = True
            del_vnfs_param = http_content['update']["del_vnf"]

            for del_vnf in del_vnfs_param:
                log.debug("vnf info to delete : vnfd_name = %s, vnfd_version = %s" % (del_vnf["vnfd_name"], del_vnf["vnfd_version"]))

                is_exist_del = False    # 실제로 삭제되는 vnf가 있는지 체크
                for idx in range(len(rlt_dict["vnfs"])-1, -1, -1):
                    vnf_rlt = rlt_dict["vnfs"][idx]

                    if vnf_rlt["vnfd_name"] == del_vnf["vnfd_name"] and vnf_rlt["version"] == del_vnf["vnfd_version"]:

                        # 2.1 Parameters 삭제
                        # RLT에서 vnf 삭제 전에 먼저 삭제할 vnf에 대한 parameters 정보 삭제부터...
                        for idx_param in range(len(rlt_dict["parameters"])-1, -1 ,-1):
                            parameter_rlt = rlt_dict["parameters"][idx_param]
                            if vnf_rlt["nscatseq"] == parameter_rlt["nscatseq"] and vnf_rlt["nfcatseq"] == parameter_rlt["ownerseq"]:
                                del rlt_dict["parameters"][idx_param]
                                # break

                        # 2.2 RLT에서 vnf 삭제
                        del rlt_dict["vnfs"][idx]
                        is_exist_del = True
                        break
                if not is_exist_del:
                    log.debug("[NS Update] # Warning # vnfd_name[%s], version[%s] doesn't exist in RLT" % (del_vnf["vnfd_name"], del_vnf["vnfd_version"]))

        # 3. Add vnf info to RLT
        log.debug("[NS Update] _____3. Add vnf info to RLT_____")
        if "add_vnf" in http_content['update'] and http_content['update']['add_vnf'] is not None and len(http_content['update']['add_vnf']) > 0:
            is_add_vnfs = True
            add_vnfs_param = http_content['update']["add_vnf"]

            add_vnfs = []
            param_list = []
            parameters = ""

            for add_vnf in add_vnfs_param:

                # vnf 기본정보
                result, vnf_info = orch_dbm.get_vnfd_general_info_with_name(mydb, add_vnf)
                # vnf에 딸린 상세 정보
                result, vnf_dtl = orch_dbm.get_vnfs_detail_info(mydb, vnf_info)
                vnf_dtl["nscatseq"] = rlt_dict["nscatseq"]
                # 추가된 vnf 표시...config 작업후 삭제하고 RLT 테이블에 저장
                vnf_dtl["isAdded"] = True
                vnf_dtl["service_number"] = add_vnf["service_number"]
                if "service_period" in add_vnf:
                    vnf_dtl["service_period"] = add_vnf["service_period"]

                # parameters
                vnf_info["vnfd_name"] = add_vnf["vnfd_name"]
                vnf_params = vnf_info["parameters"]
                # result, vnf_params = orch_dbm.get_vnfd_parmeters(mydb, vnf_info)

                # TODO: 회선이중화 : 사용하지 않는 WAN 관련 Parameter 정리
                # vnf가 KT_VNF(UTM)이 아닌 경우에도 WAN 정보 골라내야하는지 확인 필요
                is_R_for_del = False
                for param in vnf_params:
                    if param["name"].find("redFixedIpR") >= 0:
                        is_R_for_del = True
                        break
                if is_R_for_del:
                    wan_dels = _get_wan_dels(add_vnf["parameters"])
                    vnf_params = common_manager.clean_parameters(vnf_params, wan_dels)
                    vnf_dtl["wan_dels"] = wan_dels  # 개발용 추가정보 삽입...resourcetemplate 정리할때 사용...사용 후 삭제 처리함.

                # rlt_dict["vnfs"] 에 추가하기 위해 배열 작성.
                add_vnfs.append(vnf_dtl)

                for vnf_param in vnf_params:
                    vnf_param["nscatseq"] = rlt_dict["nscatseq"]

                # rlt_dict["parameters"] 에 추가하기 위해 배열 작성.
                param_list.extend(vnf_params)

                # _new_nsr_check_param을 위한 준비...
                if parameters:
                    parameters += ";"
                parameters += add_vnf["parameters"]

            # 라이센스
            check_license_result, check_license_data = new_nsr_check_license(mydb, add_vnfs)

            if check_license_result < 0:
                raise Exception("Failed to allocate VNF license: %d %s" % (check_license_result, check_license_data))

            check_param_result, check_param_data = _new_nsr_check_param(mydb, rlt_dict['vimseq'], param_list, parameters)
            if check_param_result < 0:
                raise Exception("Invalid Parameters: %d %s" % (check_param_result, check_param_data))

            # 추가된 vnf 및 parameter에 대한 RLT 구성
            rlt_dict["vnfs"].extend(add_vnfs)
            rlt_dict["parameters_add"] = param_list

            # 추가된 vnf중에 XMS가 있을 경우 XMS 계정 확인 및 생성 처리
            result, msg = _create_account(mydb, rlt_dict['serverseq'], param_list, e2e_log)
            if result < 0:
                # raise Exception(msg)
                pass

        if e2e_log:
            e2e_log.job('Composed RLT Data with deleting and adding vnfs, parameters, license', CONST_TRESULT_SUCC,
                        tmsg_body="RLT Data: %s" % (json.dumps(rlt_dict, indent=4)))

        if use_thread:
            th = threading.Thread(target=update_nsr_for_vnfs_thread,
                                  args=(mydb, http_content, rlt_dict, is_add_vnfs, is_del_vnfs, del_vnfs_param, True, e2e_log))
            th.start()
            return 200, "OK"
        else:
            return update_nsr_for_vnfs_thread(mydb, http_content, rlt_dict, is_add_vnfs, is_del_vnfs, del_vnfs_param, start_monitor=True, e2e_log=e2e_log)

    except Exception, e:
        log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
        if e2e_log:
            e2e_log.job('NS Update API Call 수신 처리 실패', CONST_TRESULT_FAIL,
                        tmsg_body="NS ID: %s\nNS Restore Request Body:%s\nCause: %s" % (str(nsr_id), json.dumps(http_content, indent=4), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, "NS Update가 실패하였습니다. 원인: %s" % str(e)

def update_nsr_for_vnfs_thread(mydb, http_content, rlt_dict, is_add_vnfs, is_del_vnfs, del_vnfs_param, start_monitor=True, e2e_log=None):

    rlt_dict['status'] = NSRStatus.UDT
    update_server_dict = {}
    update_server_dict['serverseq'] = rlt_dict['serverseq']
    update_server_dict['nsseq'] = rlt_dict['nsseq']

    try:
        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_parsing, server_dict=update_server_dict, server_status=SRVStatus.PVS)

        # 4. Recomposing HOT resourcetemplate
        log.debug("[NS Update] _____4. Recomposing HOT resourcetemplate_____")

        # 4.1 HOT resourcetemplate 세팅
        # 삭제된 vnf가 있으면, rlt의 기존 resourcetemplate 에서 해당 vnf정보 삭제처리
        del_rt_dict = _clean_vnf_resourcetemplate(rlt_dict["resourcetemplate"], del_vnfs_param)
        vnf_hot_list = [del_rt_dict]

        # ns_hot_result, ns_hot_value = compose_nsd_hot(rlt_dict["name"], vnf_hot_list)
        # if ns_hot_result < 0:
        #     log.error("[NS Update] Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
        #     raise Exception("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
        #
        # # log.debug("before rlt_dict['resourcetemplate'] = %s" % rlt_dict['resourcetemplate'])
        # rlt_dict['resourcetemplate'] = ns_hot_value
        # # log.debug("\n\nafter rlt_dict['resourcetemplate'] = %s" % rlt_dict['resourcetemplate'])

        # 5. VMs Update
        # 5.1 stack 정보 DB에서 가져오기
        # log.debug("[NS Update] _____5. VMs Update_____")
        # result, nsr_info = orch_dbm.get_nsr_general_info(mydb, rlt_dict['nsseq'])
        # if result < 0:
        #     log.error("[NS Update] Failed to get NSR Info[%s] : %d %s" % (rlt_dict['nsseq'], result, nsr_info))
        #     raise Exception("Failed to get NSR Info[%s] : %d %s" % (rlt_dict['nsseq'], result, nsr_info))

        # 5.2 Vim connector 가져오기
        result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
        myvim = vims.values()[0]

        stack_uuid = rlt_dict["uuid"]
        nsr_name = rlt_dict["name"]
        template_param_list = None

        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_updatingvr)

        if is_del_vnfs:

            if e2e_log:
                e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_NONE, tmsg_body="NS 모니터링 종료 요청")

            log.debug("[NS Update] _____5.a Stop Monitor_____")
            monitor_result, monitor_response = stop_nsr_monitor(mydb, rlt_dict['nsseq'], e2e_log, del_vnfs_param)
            if monitor_result < 0:
                log.error("[NS Update] Failed to stop monitor for %d: %d %s" % (rlt_dict['nsseq'], monitor_result, str(monitor_response)))
                if e2e_log:
                    e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_FAIL, tmsg_body="NS 모니터링 종료 요청 실패\n원인: %d %s" % (monitor_result, monitor_response))
                # raise Exception("Failed to stop monitor for %d: %d %s" % (rlt_dict['nsseq'], monitor_result, str(monitor_response)))
            else:
                if e2e_log:
                    e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_SUCC, tmsg_body="NS 모니터링 종료 요청 완료")

            if del_vnfs_param is not None and len(del_vnfs_param) > 0:
                log.debug("[HJC] Start finishing VNFs for %s" %str(del_vnfs_param))
                fn_result, fn_data = orch_dbm.get_nsr_id(mydb, rlt_dict['nsseq'])
                if fn_result <= 0:
                    log.error("failed to get NSR Info from DB: %d %s" %(fn_result, fn_data))
                    raise Exception("failed to get NSR Info from DB: %d %s" %(fn_result, fn_data))

                for vnf in fn_data['vnfs']:
                    # Update NS 에서 del_vnfs 가 있는 경우 처리...
                    for del_vnf in del_vnfs_param:
                        if vnf["vnfd_name"] == del_vnf["vnfd_name"] and vnf["version"] == del_vnf["vnfd_version"]:
                            fv_result, fv_data = _finish_vnf_using_ktvnfm(mydb, rlt_dict['serverseq'], vnf['vdus'], e2e_log)
                            if fv_result < 0:
                                log.error("Failed to finish VNF %s: %d %s" % (vnf['name'], fv_result, fv_data))
                                if result == -HTTP_Not_Found:
                                    log.debug("One-Box is out of control. Skip finishing VNFs")
                                else:
                                    raise Exception("Failed to finish VNF %s: %d %s" % (vnf['name'], fv_result, fv_data))

                            log.debug("[HJC] Succeed to finish VNF for %s" %vnf['name'])
                            break

            time.sleep(10)

            log.debug("[NS Update] _____5.1.1 Update Heat Stack for DEL_____")
            if e2e_log:
                e2e_log.job('Update Heat Stack for DEL', CONST_TRESULT_NONE, tmsg_body=None)
            result, msg, template_param_list = _update_heat_stack(myvim, nsr_name, stack_uuid, rlt_dict, vnf_hot_list, mydb)
            if result < 0:
                log.error("[NS Update] Failed to update Heat Stack for DEL[%s] : %d %s" % (nsr_name, result, msg))
                if e2e_log:
                    e2e_log.job('Update Heat Stack for DEL', CONST_TRESULT_FAIL, tmsg_body="Failed to update Heat Stack for DEL[%s] : %d %s" % (nsr_name, result, msg))
                raise Exception("Failed to update Heat Stack for DEL[%s] : %d %s" % (nsr_name, result, msg))
            if e2e_log:
                e2e_log.job('Update Heat Stack for DEL', CONST_TRESULT_SUCC, tmsg_body="RLT Data: %s" % (json.dumps(rlt_dict, indent=4)))

        deploy_order = 1
        for vnf in rlt_dict["vnfs"]:

            # deployorder 다시 세팅
            vnf["deployorder"] = deploy_order
            deploy_order += 1

            if not vnf.get("isAdded", False):
                continue

            # 새로 추가된 vnf들만 처리.
            vnf_dict = {"vnfd_name" : vnf["vnfd_name"], "vnfd_version" : vnf["version"]}
            result, nfcatalog_info = orch_dbm.get_vnfd_general_info_with_name(mydb, vnf_dict)

            if nfcatalog_info['resourcetemplatetype'] != "hot":
                log.debug("[HJC] skip getting resource template because it belongs to Other Service System")
                continue

            # 추가된 vnf들이 있으면 vnfd resourcetemplate 정리 후 배열에 추가
            rt_dict = load_yaml(nfcatalog_info['resourcetemplate'])
            if "wan_dels" in vnf:
                rt_dict = _clean_wan_resourcetemplate(rt_dict, vnf["wan_dels"])

            vnf_hot_list.append(rt_dict)

        if is_add_vnfs:
            log.debug("[NS Update] _____5.1.2 Update Heat Stack for ADD_____")
            if is_del_vnfs:
                time.sleep(20)

            rlt_dict["parameters"].extend(rlt_dict["parameters_add"])
            del rlt_dict["parameters_add"]

            if e2e_log:
                e2e_log.job('Update Heat Stack for ADD', CONST_TRESULT_NONE, tmsg_body=None)
            result, msg, template_param_list = _update_heat_stack(myvim, nsr_name, stack_uuid, rlt_dict, vnf_hot_list, mydb)
            if result < 0:
                log.error("[NS Update] Failed to update Heat Stack for ADD[%s] : %d %s" % (nsr_name, result, msg))
                if e2e_log:
                    e2e_log.job('Update Heat Stack for ADD', CONST_TRESULT_FAIL, tmsg_body="Failed to update Heat Stack for ADD[%s] : %d %s" % (nsr_name, result, msg))
                raise Exception("Failed to update Heat Stack for ADD[%s] : %d %s" % (nsr_name, result, msg))
            if e2e_log:
                e2e_log.job('Update Heat Stack for ADD', CONST_TRESULT_SUCC, tmsg_body="RLT Data: %s" % (json.dumps(rlt_dict, indent=4)))

        if e2e_log:
            e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_NONE, tmsg_body=None)

        log.debug("[NS Update] _____5.2 Get the Heat Stack Info for updated one_____")
        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_checkingvr)

        result, stack_info = myvim.get_heat_stack_id_v4(stack_uuid)
        if result < 0:
            log.error("[NS Update] Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))
            if e2e_log:
                e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))

        log.debug("[NS Update] _____5.3 Get the resource list of updated Heat Stack_____")
        result, stack_resources = myvim.get_heat_resource_list_v4(stack_uuid)
        if result < 0:
            log.error("[NS Update] Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))
            if e2e_log:
                e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))

        if e2e_log:
            e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_SUCC, tmsg_body=None)

        # cp 처리
        _set_stack_data(rlt_dict, stack_resources, stack_info, rlt_dict["name"], template_param_list)

        # web_url 처리
        vnf_proc_result, vnf_proc_data = new_nsr_vnf_proc(rlt_dict)
        if vnf_proc_result < 0:
            log.debug("[NS Update] Failed to get vnf data by new_nsr_vnf_proc %d %s" % (vnf_proc_result, vnf_proc_data))

        # Step 6. Update NSR,VDU,CP, Web URL
        log.debug("[NS Update] _____6. Update NSR,VDU,CP,Web URL_____")
        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_processingdb)
        # delete 작업 : tb_nfr 에서 삭제될 vnf 제거
        if is_del_vnfs:
            log.debug("[NS Update] _____6.a Delete VNFs_____")
            for del_vnf in del_vnfs_param:
                condition = {"name" : del_vnf["vnfd_name"], "nsseq" : rlt_dict["nsseq"]}

                global global_config
                if global_config.get("license_mngt", False):
                    result, nfr_data = orch_dbm.get_vnf_only(mydb, condition)
                    if result < 0:
                        log.debug("[NS Update] Error : Failed to get nfr %d %s" % (result, nfr_data))
                        raise Exception("Failed to get nfr %d %s" % (result, nfr_data))
                    # 삭제된 nfr 관련 license_pool update 처리
                    result, data = return_license(mydb, nfr_data["license"])
                    if result < 0:
                        log.warning("Failed to return license back for VNF %s and License %s" % (vnf['name'], vnf.get('license')))

                result, content = orch_dbm.delete_nfr(mydb, condition)
                if result < 0:
                    log.debug("[NS Update] Error : Failed to delete nfr %d %s" % (result, content))
                    raise Exception("Failed to delete nfr %d %s" % (result, content))

        # insert 작업
        rlt_dict_add = None
        if is_add_vnfs:
            # 추가된 VNF 가 있는 경우, 추가된 VNF만 갖는 rlt_dict 복사본을 만든다.
            # insert_nsr_for_vnfs, _new_nsr_vnf_conf, start_monitor 에서 사용
            rlt_dict_add = copy.deepcopy(rlt_dict)
            for idx in range(len(rlt_dict_add['vnfs'])-1, -1, -1):
                vnf = rlt_dict_add['vnfs'][idx]
                if not vnf.get("isAdded", False):
                    del rlt_dict_add['vnfs'][idx]

            log.debug("[NS Update] _____6.b Insert VNFs_____")
            result, content = orch_dbm.insert_nsr_for_vnfs(mydb, rlt_dict_add, update_mode=True)
            if result < 0:
                log.debug("[NS Update] Error : Failed to insert vnfs %d %s" % (result, content))
                raise Exception("Failed to insert vnfs %d %s" % (result, content))
            # rlt_dict_add의 정보를 rlt_dict에 추가
            for new_vnf in rlt_dict_add["vnfs"]:
                for vnf in rlt_dict["vnfs"]:
                    if new_vnf["vnfd_name"] == vnf["vnfd_name"] and new_vnf["version"] == vnf["version"]:
                        vnf["nfseq"] = new_vnf["nfseq"]
                        vnf["vdus"] = new_vnf["vdus"]

                        # 추가된 nfr 관련 license_pool update 처리
                        global global_config
                        if global_config.get("license_mngt", False):
                            license_update_info = {'nfseq': vnf['nfseq']}
                            update_license(mydb, vnf.get('license'), license_update_info)
                        break

        # parameter 정보 업데이트
        log.debug("[NS Update] _____6.c Delete NSR Params_____")
        orch_dbm.delete_nsr_param(mydb, {"nsseq" : rlt_dict['nsseq']})
        # calculate internal parameter values
        log.debug("[NS Update] _____6.d Insert NSR Params_____")
        vnf_name_list = []
        for vnf in rlt_dict['vnfs']:
            vnf_name_list.append(vnf['name'])
        iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_name_list, rlt_dict['parameters'])
        if iparm_result < 0:
            log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
            # raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
        orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])

        if e2e_log:
            e2e_log.job('Updated DB for NSR, VDU, CP, Web URL', CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 7. Init config for added vnfs
        log.debug("[NS Update] _____7. Init config_____")
        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_configvnf)
        if rlt_dict_add:
            log.debug("[NS Update] _____7.1 Init config for added vnfs_____")
            result, msg = _new_nsr_vnf_conf(mydb, rlt_dict_add, rlt_dict_add["serverseq"], e2e_log=e2e_log)
            if result < 0:
                log.debug("[NS Update] Failed to init config %d %s" % (result, msg))
                raise Exception("Failed to init config %d %s" % (result, msg))

            # update config for pre-existing VNF related to the added VNFs for XMS, conduct update config of UTM
            add_vnf_names = []
            for vnf in rlt_dict_add["vnfs"]:
                add_vnf_names.append(vnf["vnfd_name"])

            result, msg = _update_nsr_vnf_config(mydb, rlt_dict, rlt_dict["serverseq"], add_vnf_names, e2e_log=e2e_log)
            if result < 0:
                log.debug("[NS Update] Failed to init config for UTM %d %s" % (result, msg))
                raise Exception("Failed to init config for UTM %d %s" % (result, msg))

        if e2e_log:
            e2e_log.job('Init config for added vnfs', CONST_TRESULT_SUCC, tmsg_body=None)

        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_testing)
        # if rlt_dict_add:
        #     res, msg = _new_nsr_test(mydb, rlt_dict_add["serverseq"], rlt_dict_add)

        # Step 8. Start Monitor for new VNFs Instance
        log.debug("[NS Update] _____8. Start Monitor_____")
        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_resumingmonitor)

        if start_monitor and rlt_dict_add:
            log.debug("[NS Update] _____8.1. Start Monitor for new VNFs Instance_____")
            if e2e_log:
                e2e_log.job('Start Monitor for new VNFs Instance', CONST_TRESULT_NONE, tmsg_body="Start Monitor for new VNFs Instance")
            # 추가된 VNF가 있는 경우에만 Monitor를 Start시킨다.
            # Parameter로 넘기는 rlt_dict는 추가된 VNF만 남긴다.
            mon_result, mon_data = new_nsr_start_monitor(mydb, rlt_dict_add, rlt_dict_add["serverseq"], e2e_log)
            if mon_result < 0:
                log.warning("[NS Update] : Failed to start monitor for new VNFs %d %s" % (mon_result, mon_data))
                if e2e_log:
                    e2e_log.job("Start Monitor for new VNFs Instance", CONST_TRESULT_FAIL, tmsg_body=None)
                # raise Exception("Failed to start monitor for new VNFs %d %s" % (mon_result, mon_data))
            else:
                if e2e_log:
                    e2e_log.job("Start Monitor for new VNFs Instance", CONST_TRESULT_SUCC, tmsg_body=None)

        # nscatlog 가 새로 구성된 경우 nsd를 등록하고, rlt의 nscatseq를 변경처리 해준다.
        vnf_list = []
        for vnf in rlt_dict['vnfs']:
            vnf_list.append({"vnfd_name": vnf['name'], "vnfd_version": str(vnf['version'])})
        result, nsd_id = new_nsd_with_vnfs(mydb, vnf_list)
        if result < 0:
            log.error("failed to get NSD: %d %s" %(result, nsd_id))
            raise Exception("failed to get NSD: %d %s" %(result, nsd_id))
        if nsd_id != rlt_dict["nscatseq"]:
            log.debug("_____ [NS Update] nsd 새로 등록 : %s, 기존 nsd : %s" % (nsd_id, rlt_dict["nscatseq"]))
            rlt_dict["nscatseq"] = nsd_id
            for vnf in rlt_dict['vnfs']:
                vnf["nscatseq"] = nsd_id
            for param in rlt_dict['parameters']:
                param["nscatseq"] = nsd_id

        # Step 9. Update RLT Data
        log.debug("[NS Update] _____9. Update RLT Data_____")
        # 개발용 데이타 삭제처리...
        for vnf in rlt_dict['vnfs']:
            if vnf.get("isAdded", False):
                del vnf["isAdded"]
                if vnf.get("wan_dels", False):
                    del vnf["wan_dels"]

        result, content = _update_rlt_data(mydb, rlt_dict, nsseq=rlt_dict['nsseq'])
        if result < 0:
            log.debug('[NS Update] Failed to update RLT %d %s' % (result, content))
            raise Exception("Failed to update RLT %d %s" % (result, content))
        if e2e_log:
            e2e_log.job("Updated RLT Data", CONST_TRESULT_SUCC, tmsg_body="Updated RLT Data : %s" % (json.dumps(rlt_dict, indent=4)))

        # Update OOD Flag to True of NS Backup Data
        orch_dbm.update_ood_flag(mydb, rlt_dict['nsseq'])

        log.debug("[NS Update] _____10. Update NS End_____")
        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.RUN, server_dict=update_server_dict, server_status=SRVStatus.INS)

        if e2e_log:
            e2e_log.job("Update NS 완료", CONST_TRESULT_SUCC, tmsg_body=None)

        return 200, "OK"

    except Exception, e:
        log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
        update_nsr_status(mydb, ActionType.NSRUP, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR, server_dict=update_server_dict, server_status=SRVStatus.ERR,
                           nsr_status_description=str(e))
        if e2e_log:
            e2e_log.job('NS Update for vnfs Thread 작업 실패', CONST_TRESULT_FAIL,
                        tmsg_body="NS ID: %s\nNS Update Request Body:%s\nCause: %s" % (str(rlt_dict['nsseq']), json.dumps(http_content, indent=4), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, "NS Update가 실패하였습니다. 원인: %s" % str(e)


def _update_heat_stack(myvim, nsr_name, stack_uuid, rlt_dict, vnf_hot_list, mydb):

    vnf_name_list = []
    for vnf in rlt_dict['vnfs']:
        vnf_name_list.append(vnf['name'])
    # for update stack
    iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_name_list, rlt_dict['parameters'])
    if iparm_result < 0:
        log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
        #return iparm_result, "Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content)

    # 5.3 Compose Heat Parameters
    template_param_list = []
    for param in rlt_dict['parameters']:
        if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
            template_param_list.append(param)

    # extrawan을 사용하는 VNF에서 선택한 Port값을 resourcetemplate에 적용시켜줘야한다.
    for param in template_param_list:
        if param["name"].find("RPARM_extrawan") >= 0:
            try:
                vnf_name = param["name"].split("_")[2]
                for rt_dict in vnf_hot_list:
                    if "PNET_extrawan_" + vnf_name in rt_dict["resources"]:
                        physical_network = rt_dict["resources"]["PNET_extrawan_" + vnf_name]["properties"]["physical_network"]
                        if physical_network != param["value"]:
                            rt_dict["resources"]["PNET_extrawan_" + vnf_name]["properties"]["physical_network"] = param["value"]
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)

    ns_hot_result, ns_hot_value = compose_nsd_hot(rlt_dict["name"], vnf_hot_list)
    if ns_hot_result < 0:
        log.error("[NS Update] Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
        raise Exception("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))

    log.debug("rlt_dict['resourcetemplate'] = %s" % ns_hot_value)
    rlt_dict['resourcetemplate'] = ns_hot_value

    template_param_list_for_heat = copy.deepcopy(template_param_list)

    # timing issue 가 있을 수 있다...IP 변경이 반영되지 않는 문제. 여러번 TRY 하도록.
    try_cnt = 0
    stack_info = None
    while True:
        result, stack_info = myvim.get_heat_stack_id_v4(stack_uuid)
        if result < 0:
            try_cnt += 1
            if try_cnt < 3:
                log.warning("Retry get heat stack info : %d" % try_cnt)
                time.sleep(10)
                result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
                myvim = vims.values()[0]
                continue
            else:
                raise Exception("Failed to get heat stack info")
        else:
            break

    for param_key, param_value in stack_info["parameters"].items():
        if param_key.find("RPARM_imageId") >= 0:
            continue

        for template_param in template_param_list_for_heat:
            if param_key == template_param["name"]:
                template_param["value"] = param_value
                break

    result, msg = myvim.update_heat_stack_v4(nsr_name, stack_uuid, rlt_dict['resourcetemplatetype'], rlt_dict['resourcetemplate'], template_param_list_for_heat)

    return result, msg, template_param_list


def _check_nsr_exist(mydb, ob_data):
    is_nsr_exist = True
    if ob_data.get('nsseq') is None:
        is_nsr_exist = False
        return 200, {"nsr_exist": is_nsr_exist, "nsseq": -1}

    nsr_id = ob_data['nsseq']
    nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr_id)
    if nsr_result <= 0:
        log.debug("No NSR found")
        is_nsr_exist = False
        return 200, {"nsr_exist": is_nsr_exist, "nsseq": nsr_id}

    #TODO: Check One-Box Inside
    # if nsr_id < 0:
    #     is_nsr_exist = False

    log.debug("NSR Info: %s, %d" %(str(is_nsr_exist), nsr_id))
    return 200, {"nsr_exist": is_nsr_exist, "nsseq": nsr_id, "nsr_data":nsr_data}


def restore_onebox(mydb, request, server_id, tid=None, tpath=""):
    """
        One-Box 복구
    :param mydb:
    :param request:
    :param server_id: tb_server > serverseq
    :param tid:
    :param tpath:
    :return:
    """

    e2e_log = None
    onebox_id = None

    try:
        # Step.1 Check arguments and initialize variables
        if server_id is None:
            log.error("One-Box ID is not given")
            raise Exception(-HTTP_Bad_Request, "One-Box ID is required.")

        try:
            if not tid:
                e2e_log = e2elogger(tname='One-Box Restore', tmodule='orch-f', tpath="orch_onebox-restore")
            else:
                e2e_log = e2elogger(tname='One-Box Restore', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_onebox-restore")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('One-Box 복구 API Call 수신 처리 시작', CONST_TRESULT_SUCC,
                        tmsg_body="Server ID: %s\nOne-Box Restore Request Body:%s" % (str(server_id), json.dumps(request, indent=4)))
            action_tid = e2e_log['tid']
        else:
            action_tid = generate_action_tid()

        # Step.2 Get One-Box info and Check Status
        ob_result, ob_content = common_manager.get_server_all_with_filter(mydb, server_id)
        if ob_result <= 0:
            log.error("get_server_all_with_filter Error %d %s" %(ob_result, ob_content))
            raise Exception(ob_result, ob_content)

        ob_data = ob_content[0]
        onebox_id = ob_data["onebox_id"]

        #if ob_data['status'] == SRVStatus.LWT or ob_data['status'] == SRVStatus.PVS or ob_data['status'] == SRVStatus.OOS or ob_data['status'] == SRVStatus.DSC:
        if ob_data['status'] == SRVStatus.LWT or ob_data['status'] == SRVStatus.PVS:
            raise Exception(-HTTP_Bad_Request, "Cannot restore the One-Box in the status of %s" %(ob_data['status']))

        if ob_data['action'] is None or ob_data['action'].endswith("E"): # NGKIM: Use RE for backup
            pass
        else:
            raise Exception(-HTTP_Bad_Request, "The One-Box is in Progress for another action: status= %s action= %s" %(ob_data['status'], ob_data['action']))

        if e2e_log:
            e2e_log.job('Get One-Box info and Check Status', CONST_TRESULT_SUCC,
                        tmsg_body="One-Box ID: %s\nOne-Box DB DATA:%s" % (str(onebox_id), ob_data))

        # Step.3 Get backup info
        target_dict = {'serverseq':ob_data['serverseq']}

        if 'backup_id' in request and len(request['backup_id']) > 0:
            target_dict['backupseq'] = request['backup_id']
            backup_result, backup_data = orch_dbm.get_backup_history_id(mydb, target_dict)
        else:
            target_dict['category'] = 'onebox'
            backup_result, backup_data = orch_dbm.get_backup_history_lastone(mydb, target_dict)

        if backup_result < 0:
            log.warning("Failed to get backup history for %d %s" %(backup_result, backup_data))
            raise Exception(-HTTP_Bad_Request, "Cannot find a Backup File")
        elif backup_result == 0:
            log.debug("No One-Box Backup Data found: %d %s" %(backup_result, str(backup_data)))
            backup_data = None

        if e2e_log:
            e2e_log.job('Get backup info', CONST_TRESULT_SUCC, tmsg_body="backup data:%s" % backup_data)

    except Exception, e:
        error_code = -HTTP_Internal_Server_Error
        if len(e.args) == 2:
            error_code, error_msg = e
        else:
            error_msg = str(e)

        log.warning("Exception: %s" % error_msg)
        if e2e_log:
            e2e_log.job('One-Box 복구 API Call 수신 처리 실패', CONST_TRESULT_FAIL,
                        tmsg_body="One-Box ID: %s\nOne-Box Restore Request Body:%s\nCause: %s" % (str(onebox_id), json.dumps(request, indent=4), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return error_code, "One-Box 복구가 실패하였습니다. 원인: %s" % error_msg

    try:
        request_data = {"user":request.get("user", "admin"), "mgmt_ip":request.get('mgmt_ip'), "tid":action_tid}

        if request.get("wan_mac", None):
            request_data["wan_mac"] = request.get("wan_mac", None)

        # Step.4 Start restoring One-Box Thread
        th = threading.Thread(target=_restore_onebox_thread, args=(mydb, onebox_id, ob_data, request_data, backup_data, True, e2e_log))
        th.start()

        return_data = {"restore":"OK", "status": "DOING"}
    except Exception, e:
        log.warning("Exception: %s" %str(e))
        if e2e_log:
            e2e_log.job('One-Box 복구 Thread 시작 실패', CONST_TRESULT_FAIL, tmsg_body=None)
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "One-Box 복구가 실패하였습니다. 원인: %s" % str(e)

    return 200, return_data

def _restore_onebox_thread(mydb, onebox_id, ob_data, request_data, backup_data=None, use_thread=True, e2e_log=None):

    log.debug("[_RESTORE_ONEBOX_THREAD - %s] BEGIN" % onebox_id)

    # log.debug('[   BONG   ] ob_data = %s' %str(ob_data))

    public_ip_dcp = str(copy.deepcopy(ob_data.get('publicip')))
    # log.debug('[   BONG   ] public_ip_dcp = %s' %str(public_ip_dcp))

    action_dict = {'tid':request_data["tid"]}
    action_dict['category'] = "OBRestore"
    action_dict['action_user'] = request_data["user"]
    action_dict['server_name'] = ob_data['servername']
    action_dict['server_seq'] = ob_data['serverseq']
    try:
        ob_org_status = ob_data["status"]

        common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.STRT, ob_data=ob_data, ob_status=SRVStatus.OOS)

        # Step.1 initialize variables
        is_agent_successful = True

        # Step.2 Get One-Box Agent Connector
        # ob_conn_dict = {"serverseq":ob_data["serverseq"], "servername":ob_data["servername"], "obagent_base_url":ob_data["obagent_base_url"]}
        result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=onebox_id)
        if result < 0:
            log.error("Error. One-Box Agent not found")
            is_agent_successful = False
        elif result > 1:
            log.error("Error. Several One-Box Agents available, must be identify")
            is_agent_successful = False

        if is_agent_successful is False:
            ob_data_temp = {"serverseq":action_dict["server_seq"]}
            common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data_temp, ob_status=ob_org_status)
            raise Exception("Cannot establish One-Box Agent Connector")

        ob_agent = ob_agents.values()[0]

        if e2e_log:
            e2e_log.job('Get One-Box Agent Connector', CONST_TRESULT_SUCC, tmsg_body="onebox_id: %s\nob_agents:%s" % (onebox_id, ob_agents))

        if request_data.get('mgmt_ip') is not None:
            is_change_server_info = False
            server_dict = {"serverseq":ob_data["serverseq"]}

            # tb_server mgmt_ip 와 다르면 agent 접속을 위해 obagent_base_url 만 변경처리, mgmt_ip는 new_server에서 처리하도록 한다(모니터링 업데이트)
            if request_data['mgmt_ip'] != ob_data["mgmtip"]:
                is_change_server_info = True

                old_obagent_base_url = ob_data["obagent_base_url"]
                new_obagent_base_url = request_data['mgmt_ip']
                if old_obagent_base_url.find("://") >= 0:
                    new_obagent_base_url = old_obagent_base_url[0:old_obagent_base_url.index("://")+3] + new_obagent_base_url

                if old_obagent_base_url.find(":", 7) >= 0:
                    new_obagent_base_url += old_obagent_base_url[old_obagent_base_url.index(":", 7):]

                server_dict["obagent_base_url"] = new_obagent_base_url
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Update obagent_base_url:%s" % (onebox_id, new_obagent_base_url))

            if request_data.get("wan_mac", None) and request_data['wan_mac'] != ob_data["publicmac"]:
                is_change_server_info = True
                server_dict["publicmac"] = request_data['wan_mac']
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Update publicmac:%s" % (onebox_id, request_data['wan_mac']))

            if is_change_server_info:
                result, content = orch_dbm.update_server(mydb, server_dict)
                if result < 0:
                    log.error("failed to update the server %d %s" %(result, content))

                #############################################################################################################################
                # one-box 정보를 직접 얻어와서 new_server 호출
                # - server, vim, monitor update 필요
                # - 뒷단에서 _restore_nsr_reprov 하면서 NS는 새로 구성하므로 변경 프로세스는 수행하지 않아도 된다.
                #
                time.sleep(5)   # agent가 아직 부팅되지 않았거나, 정보를 제대로
                result, server_info = ob_agent.get_onebox_info(None)
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] The result of getting onebox info: %d %s" % (onebox_id, result, str(server_info)))
                if result < 0:
                    # log.error("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))
                    raise Exception("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))

                # public_ip, mgmt_ip 정보 valication check
                if server_info.get("public_ip") is None or server_info.get("mgmt_ip") is None:
                    time.sleep(10)
                    log.debug("_____ Try getting onebox info again")
                    result, server_info = ob_agent.get_onebox_info(None)
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] The result of getting onebox info: %d %s" % (onebox_id, result, str(server_info)))
                    if result < 0:
                        raise Exception("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))

                    if server_info.get("public_ip") is None or server_info.get("mgmt_ip") is None:
                        raise Exception("IP data from agent is wrong!!!")

                log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ First NEW_SERVER _____ BEGIN" % onebox_id)
                su_result, su_data = new_server(mydb, server_info, filter_data=onebox_id, use_thread=False, forced=True)
                if su_result < 0:
                    log.error("Failed to update One-Box Info: %d %s" %(su_result, su_data))
                    raise Exception("Failed to update One-Box Info: %d %s" %(su_result, su_data))
                else:
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ First NEW_SERVER _____ END" % onebox_id)
                #############################################################################################################################

        # DB server 정보 조회 : 변경된 정보가 있을 수 있어서 다시 조회한다.
        ob_result, ob_content = common_manager.get_server_all_with_filter(mydb, onebox_id)  # 뒷단에 vims 정보를 활용하므로 이 함수로 호출
        if ob_result <= 0:
            log.error("get_server_all_with_filter Error %d %s" %(ob_result, ob_content))
            raise Exception("get_server_all_with_filter Error %d %s" %(ob_result, ob_content))

        ob_data = ob_content[0]

        # Step.3 Stop One-Box Monitoring >>>>> Change to call Suspend One-Box Monitoring
        #som_result, som_data = stop_onebox_monitor(mydb, ob_data)
        som_result, som_data = suspend_onebox_monitor(mydb, ob_data, e2e_log)
        if som_result < 0:
            log.warning("Failed to stop One-Box monitor. False Alarms are expected")

        if e2e_log:
            e2e_log.job('Suspend One-Box Monitoring', CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.4 Remove NSR
        common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.INPG, ob_data=ob_data, ob_status=SRVStatus.OOS)

        is_nsr_exist = True
        nsr_check_result, nsr_check_data = _check_nsr_exist(mydb, ob_data)
        if nsr_check_result < 0:
            log.warning("failed to check NSR in the One-Box: %d %s" %(nsr_check_result, nsr_check_data))
        else:
            is_nsr_exist = nsr_check_data.get("nsr_exist", True)

        nsr_name = None

        if is_nsr_exist:
            nsr_data = nsr_check_data["nsr_data"]
            nsr_name = nsr_data["name"]

            update_nsr_status(mydb, ActionType.RESTO, nsr_data=nsr_data, nsr_status=NSRStatus.RST)

            log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_DELETE _____ BEGIN" % onebox_id)
            dnsr_result, dnsr_data = _restore_nsr_delete(mydb, nsr_data, ob_data['serverseq'], False, e2e_log=e2e_log)
            if dnsr_result < 0:
                log.error("failed to delete NSR: %d %s" %(dnsr_result, dnsr_data))
                update_nsr_status(mydb, ActionType.RESTO, nsr_data=nsr_data, nsr_status=NSRStatus.ERR)
                raise Exception("failed to delete NSR: %d %s" %(dnsr_result, dnsr_data))
            log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_DELETE _____ END" % onebox_id)
            if e2e_log:
                e2e_log.job('Remove NSR', CONST_TRESULT_SUCC, tmsg_body=None)

        if backup_data is not None:
            # Step.5 Request Restoring One-Box to the One-Box Agent
            # 5-1 Compose Request Message
            req_dict = {"onebox_id": ob_data['onebox_id']}

            action_dict['server_backup_seq'] = backup_data['backupseq']
            req_dict['backup_server'] = backup_data["backup_server"]
            if 'backup_location' in backup_data: req_dict['backup_location'] = backup_data["backup_location"]
            if 'backup_local_location' in backup_data: req_dict['backup_local_location'] = backup_data["backup_local_location"]
            if 'backup_data' in backup_data: req_dict['backup_data'] = backup_data['backup_data']

            # 5-2. Call API of One-Box Agent: Restore One-Box
            #update_onebox_status_internally(mydb, "R", action_dict=None, action_status=None, ob_data=ob_data, ob_status=SRVStatus.OOS)

            restore_result, restore_data = ob_agent.restore_onebox(req_dict)
            if restore_result < 0:
                result = restore_result
                log.error("Failed to restore One-Box %s: %d %s" %(ob_data['onebox_id'], restore_result, restore_data))
                common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=SRVStatus.ERR)
                raise Exception(restore_data)
            else:
                req_dict['request_type'] = "restore"
                req_dict['transaction_id'] = restore_data.get('transaction_id')

            if e2e_log:
                e2e_log.job('Call API of One-Box Agent: Restore One-Box', CONST_TRESULT_SUCC, tmsg_body=None)

            # 5-3 Wait for Restoring One-Box
            log.debug("[_RESTORE_ONEBOX_THREAD - %s] Completed to send restore command to the One-Box Agent : %s" %(ob_data['onebox_id'], str(restore_data)))
            if restore_data['status'] == "DOING":
                action = "restore"
                trial_no = 1
                pre_status = "UNKNOWN"

                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Wait for restore One-Box by Agent" %(ob_data['onebox_id']))
                time.sleep(10)

                while trial_no < 30:
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] Checking the progress of restore (%d):" % (onebox_id, trial_no))

                    result, check_status = _check_onebox_agent_progress(ob_agent, action, req_dict)
                    if check_status != "DOING":
                        log.debug("Completed to restore One-Box by Agent")
                        break
                    else:
                        log.debug("Restore in Progress")

                    trial_no += 1
                    time.sleep(10)

        # Step.6 Resume Monitor One-Box >> API Call Changed
        log.debug("[_RESTORE_ONEBOX_THREAD - %s] RESUME_ONEBOX_MONITOR BEGIN" % onebox_id)

        monitor_result, monitor_data = resume_onebox_monitor(mydb, ob_data['serverseq'], e2e_log)
        if monitor_result < 0:
            log.warning("Failed to start monitor: %d %s" %(monitor_result, monitor_data))

            ###################################################################################################################################################
            ### Wan 이중화에서 Wan1 이 절체된 상황에서,
            ### OneBox 복구 후 agent 재시작으로 인하여 noti가 두번 들어오는데 첫번째 noti에 잘못된 정보로 설변되어 resume_onebox_monitor 실패

            ### START : resume_onebox_monitor 실패 시, OneBox 정보 받아와서 설변 처리 후 다시 resume_onebox_monitor

            result, server_info = ob_agent.get_onebox_info(None)
            log.debug("[_RESTORE_ONEBOX_THREAD - %s] RESUME_ONEBOX_MONITOR FAILED and The result of getting onebox info: %d %s" % (onebox_id, result, str(server_info)))
            if result < 0:
                # log.error("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))
                raise Exception("Failed to get onebox info from One-Box Agent: %d %s" % (result, server_info))

            # 라우터 통해서 들어온 경우 통신 가능 하도록 public ip 를 remote_ip 로 대체
            if server_info.get('public_ip') != public_ip_dcp:
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ RESUME_ONEBOX_MONITOR _____ RETRY BEGIN" % onebox_id)
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ RESUME_ONEBOX_MONITOR > NEW_SERVER _____ BEGIN" % onebox_id)

                router_chk_result, router_chk_data = common_manager.router_check(server_info, public_ip_dcp)

                su_result, su_data = new_server(mydb, router_chk_data, filter_data=onebox_id, use_thread=False, forced=True)

                if su_result < 0:
                    log.error("Failed to update One-Box Info: %d %s" % (su_result, su_data))
                    raise Exception("Failed to update One-Box Info: %d %s" % (su_result, su_data))
                else:
                    # noti 처리 성공 후, resume_onebox_monitor 재요청
                    monitor_result, monitor_data = resume_onebox_monitor(mydb, ob_data['serverseq'], e2e_log)
                    if monitor_result < 0:
                        log.warning("Failed to start monitor: %d %s" % (monitor_result, monitor_data))

                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ RESUME_ONEBOX_MONITOR > NEW_SERVER _____ END" % onebox_id)
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ RESUME_ONEBOX_MONITOR _____ RETRY END" % onebox_id)

            ### END : resume_onebox_monitor 실패 시, OneBox 정보 받아와서 설변 처리 후 다시 resume_onebox_monitor
            ###################################################################################################################################################

        log.debug("[_RESTORE_ONEBOX_THREAD - %s] RESUME_ONEBOX_MONITOR END" % onebox_id)

        if e2e_log:
            e2e_log.job('Resume Monitor One-Box', CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.7 Restore NSR
        if is_nsr_exist:
            more_progress = True
            # 7-1 Get backup info
            log.debug("[_RESTORE_ONEBOX_THREAD - %s] Get NSR backup info" % onebox_id)
            result_backup, rlt_backup = _restore_nsr_get_backup_data(mydb, nsr_check_data['nsseq'], {"force_restore": True})
            if result_backup == HTTP_Not_Found:
                log.debug("No NSR found. Skip restoring NSR")
                more_progress = False
            if result_backup < 0:
                raise Exception("Failed to get Backup Data and NSR data")

            if e2e_log:
                e2e_log.job('Get NSR backup info', CONST_TRESULT_SUCC, tmsg_body="rlt_backup : %s" % rlt_backup)

            if more_progress:
                # 7-2. Reprovisioning NS
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Reprovisioning NSR" % onebox_id)

                # 임시코드 - 기존에 프로비져닝된 rlt의 값을 보정하기 위해 사용. 새로 프로비져닝 된 rlt는 문제 없도록 수정되었음.
                # 기존 rlt 의 nsr name이 잘못들어간 부분 수정처리
                if rlt_backup["name"] != nsr_name:
                    rlt_backup["name"] = nsr_name
                # 임시코드 END - 해당 로직 이전에 프로비져닝 된 항목이 없을 경우 제거가능

                log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_REPROV _____ BEGIN" % onebox_id)

                new_nsr_result, new_nsr_data = _restore_nsr_reprov(mydb, rlt_backup, rlt_backup['name'], rlt_backup['description']
                                                                   , {"vim_id": ob_data['vims'][0]['vimseq'], "server_id": ob_data['serverseq'], "server_name":ob_data["servername"]}
                                                                   , e2e_log)
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_REPROV _____ END" % onebox_id)
                if new_nsr_result < 0:
                    log.error("_restore_nsr_thread() failed to re-create NSR %d %s" % (new_nsr_result, new_nsr_data))
                    raise Exception("_restore_nsr_thread() failed to re-create NSR %d %s" % (new_nsr_result, new_nsr_data))

                if e2e_log:
                    e2e_log.job("Reprovisioning NSR", CONST_TRESULT_SUCC, tmsg_body=None)

                # 7-3 Restore VNFs
                if 'backupseq' in rlt_backup:
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] Restore VNFs" % onebox_id)

                    # TODO: nfr_name
                    vnf_name = ""
                    for vnf_data in rlt_backup['vnfs']:
                        vnf_name = vnf_name + " " + vnf_data['name']
                    action_dict['nfr_name'] = vnf_name

                    update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_backup, nsr_status=NSRStatus.RST_restoringvnf)
                    request = {'parentseq': rlt_backup['backupseq'], "process_name":"onebox_restore"}

                    result, request['needWanSwitch'] = _need_wan_switch(mydb, {"serverseq": ob_data['serverseq']})

                    restore_result, restore_data = _restore_nsr_vnf_thread(mydb, ob_data['serverseq'], new_nsr_data, action_dict, request, None, e2e_log)

                    if restore_result < 0:
                        log.warning("_restore_nsr_thread() error. failed to restore VNFs: %d %s" % (restore_result, restore_data))
                        if e2e_log:
                            e2e_log.job("Restore VNFs", CONST_TRESULT_FAIL, tmsg_body=None)
                            #update_nsr_status(mydb, "R", action_dict, ACTStatus.FAIL, new_nsr_data, NSRStatus.RUN)
                    else:
                        if e2e_log:
                            e2e_log.job("Restore VNFs", CONST_TRESULT_SUCC, tmsg_body=None)
                            #update_nsr_status(mydb, "R", action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.RUN)
                else:
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] No Backup Data. Skip restoring VNFs" % onebox_id)
                    #update_nsr_status(mydb, "R", action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.RUN)

                # 7-4 Resume monitoring >> Change API Call
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Resume NSR Monitoring" % onebox_id)
                update_nsr_status(mydb, ActionType.RESTO, nsr_data=new_nsr_data, nsr_status=NSRStatus.RST_resumingmonitor)

                #nm_result, nm_data = start_nsr_monitoring(mydb, ob_data['serverseq'], new_nsr_data, e2e_log=None)
                nm_result, nm_data = resume_nsr_monitor(mydb, ob_data['serverseq'], new_nsr_data, e2e_log)
                if nm_result < 0:
                    log.debug("Failed %d %s" % (nm_result, nm_data))
                    update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.ERR)
                else:
                    update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.RUN)

                    if e2e_log:
                        e2e_log.job("Resume NSR Monitoring", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.8 Update VNF status and record action history
        if ob_data['nsseq'] is None:
            common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.SUCC, ob_data=ob_data, ob_status=SRVStatus.RDS)
        else:
            common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.SUCC, ob_data=ob_data, ob_status=SRVStatus.INS)

        # 복구중 변경된 정보가 있을 수 있으므로, 최종적으로 new_server를 한번 호출해준다.
        result, server_info = ob_agent.get_onebox_info(None)

        if server_info.get('public_ip') != public_ip_dcp:
            result, server_info = common_manager.router_check(server_info, public_ip_dcp)

        log.debug('[   BONG   ] get_onebox_info = %s' %str(server_info))
        if result < 0:
            log.warning("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))
        else:
            su_result, su_data = new_server(mydb, server_info, filter_data=onebox_id)

    except Exception, e:
        error_code = -HTTP_Internal_Server_Error
        error_msg = str(e)

        log.exception("Exception: %s" % error_msg)
        ob_data_temp = {"serverseq":action_dict["server_seq"]}
        common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data_temp, ob_status=SRVStatus.ERR)

        if e2e_log:
            e2e_log.job('One-Box 복구 Thread 처리 실패', CONST_TRESULT_FAIL, tmsg_body="Cause: %s" % (str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return error_code, "One-Box 복구가 실패하였습니다. 원인: %s" % error_msg

    if e2e_log:
        e2e_log.job('One-Box 복구 Thread 완료', CONST_TRESULT_SUCC, tmsg_body="Result: Success")
        e2e_log.finish(CONST_TRESULT_SUCC)

    log.debug("[_RESTORE_ONEBOX_THREAD END - %s]" % onebox_id)

    return 200, "OK"


def _check_onebox_agent_progress(ob_agent, action, req_dict):
    result = 200
    data = "DOING"

    try:
        req_type = req_dict.get('request_type') # "restore"
        trans_id = req_dict.get('transaction_id')
        check_result, check_data = ob_agent.check_onebox_agent_progress(request_type = req_type, transaction_id=trans_id)
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        check_result = -500
        check_data = {'status':"UNKNOWN", 'error':str(e)}

    if check_result < 0:
        result = check_result
        data = "DOING"
        log.debug("Error %d, %s" %(check_result, str(check_data)))
    else:
        log.debug("Progress form One-Box by Agent: %s" %(check_data['status']))
        if check_data['status'] == "DONE":
            data = "DONE"
        elif check_data['status'] == "ERROR":
            data = "ERROR"

    return result, data


# provisioning, NS Update 시 사용
def _create_account(mydb, serverseq, parameters, e2e_log):
    # XMS 계정 확인 및 생성 처리
    # 1. parameters 중 APARM_appid_XMS, APARM_apppasswd_XMS 있는지 확인
    appid = None
    nfcatseq_xms = None

    for param in parameters:
        if param["name"] == "APARM_appid_XMS":
            appid = param["value"]
            nfcatseq_xms = param["ownerseq"]

    if appid is not None:
        # 2. 계정생성 요청 API 호출
        # 서버 계정 정보 조회...서버계정이 없으면 에러처리.
        result, server_account = orch_dbm.get_server_account(mydb, serverseq)
        if result <= 0 or server_account is None:
            log.error("Failed to get Server Account %d %s" % (result, server_account))
            return -HTTP_Internal_Server_Error, "Failed to get Server Account %d %s" % (result, server_account)

        apppasswd = server_account['account_pw']

        acc_conn = accountconnector.accountconnector("xms")
        result, resultCd = acc_conn.create_account(appid, apppasswd)
        if result < 0:
            log.warning("Warning : Error while creating of xms account - %d %s" % (result, resultCd))
            return -HTTP_Internal_Server_Error, "Error while creating of xms account %d %s" % (result, resultCd)

        if resultCd["ResultCd"] == "000" or resultCd["ResultCd"] == "221":

            # 3. API 호출 결과 성공이면, tb_server_account_use 에 저장하고 계속 진행 (저장할때 중복체크), 실패면 Exception 처리

            account_info = {"use_type":"vnf"}
            account_info["accountseq"] = server_account["accountseq"]

            result, vnfd_data = orch_dbm.get_vnfd_general_info(mydb, nfcatseq_xms)
            account_info["vnfd_name"] = vnfd_data["name"]
            account_info["vnfd_version"] = vnfd_data["version"]

            # 중복체크
            result, account_use_list = orch_dbm.get_server_account_use(mydb, account_info)
            if result < 0:
                log.error("Error while getting server account use data %d %s" % (result, account_use_list))
            elif result > 0:
                # 삭제처리
                for account_use in account_use_list:
                    result, data = orch_dbm.delete_server_account_use(mydb, account_use["accountuseseq"])
                    log.debug("Deleted server account use[dup data] %s" % account_use)
                    if result < 0:
                        log.error("Error while deleting server account use data %d %s" % (result, data))

            account_info["nfcatseq"] = nfcatseq_xms
            account_info["use_account_id"] = appid
            account_info["use_account_pw"] = apppasswd

            result, data = orch_dbm.insert_server_account_use(mydb, account_info)
            if result < 0:
                log.error("Failed to insert an One-Box Account: %d %s" %(result, data))
                return -HTTP_Internal_Server_Error, "Failed to insert an One-Box Account: %d %s" % (result, resultCd)
                # raise Exception("Failed to insert an One-Box Account: %d %s" % (result, resultCd))
        else:
            log.error("Error: Failed to create the account of XMS %d %s" % (result, resultCd))
            if resultCd["ResultCd"] == "222" or resultCd["ResultCd"] == "232" or resultCd["ResultCd"] == "233":
                return -HTTP_Internal_Server_Error, "[%s], 계정 정보 변경 필요" % resultCd["ResultCd"]
            elif resultCd["ResultCd"] == "999":
                return -HTTP_Internal_Server_Error, "XMS 계정 생성에 실패했습니다."
            else:
                return -HTTP_Internal_Server_Error, "[%s], 시스템 관리자 확인 필요" % resultCd["ResultCd"]
        if e2e_log:
            e2e_log.job("Created XMS Account", CONST_TRESULT_SUCC, tmsg_body="create result code = %s" % (resultCd["ResultCd"]))

    return 200, "OK"


def _get_wan_dels(req_params):
    """
    회선이중화 관련 작업. UI에서 받은 Parameters를 확인해서 사용하지 않는 WAN 리스트 작성
    :param req_params: UI에서 받은 Parameters
    :return: 사용하지 않는 WAN 리스트
    """

    wan_dels = ["R1", "R2", "R3"]
    param_list = req_params.split(';')
    for str_param in param_list:
        kv = str_param.split('=')
        # 전제조건 : RPARM_redFixedMac 값이 필수
        if kv[0].find("RPARM_redFixedMacR") >= 0:
            for num in range(1,4,1): # R1 ~ R3
                if kv[0].find("R" + str(num)) >= 0:
                    if kv[1] != "" and kv[1].lower() != "none":
                        # wan_opts.append("R" + str(num))
                        wan_dels.remove("R" + str(num))
                        break
    return wan_dels


# 공통 모듈로 이전 필요
def load_yaml(yaml_text):

    try:
        yaml_dict = yaml.load(yaml_text)
        return yaml_dict
    except yaml.YAMLError as exc:
        if hasattr(exc, 'problem_mark'):
            mark = exc.problem_mark
            error_text = "[Onboarding][NS]  : error, Yaml Data at line %s, column %s." %(mark.line, mark.column+1)
            log.error(error_text)
        else:
            error_text = "[Onboarding][NS]  : Unknown Error with Yaml Data."
            log.error(error_text)
        raise Exception(error_text)

def _clean_vnf_resourcetemplate(resourcetemplate, vnf_dels):
    """
    update_nsr_for_vnfs 에서 삭제되는 vnf 관련 내용 제거
    :param resourcetemplate:
    :param vnf_dels: 삭제된 vnf 리스트
    :return: dictionary 객체를 리턴한다.
    """

    rt_dict = load_yaml(resourcetemplate)

    if vnf_dels:
        # 제거 작업
        for key, value in rt_dict.items():
            if type(value) is dict:     # parameters / resources / outputs
                for p_key, p_value in value.items():
                    param = p_key.split("_")
                    if len(param) == 3:
                        for vnf_del in vnf_dels:
                            if vnf_del["vnfd_name"] == param[2]:
                                del rt_dict[key][p_key]
                                break
    return rt_dict

def _clean_wan_resourcetemplate(resourcetemplate, wan_dels):
    """
    resourcetemplate 에서 사용하지 않는 WAN 관련 정보 삭제처리
    :param resourcetemplate: str 또는 dict type으로 넘어오는 resourcetemplate 데이타
    :param wan_dels: 사용하지 않는 WAN 리스트
    :return:
    """

    if type(resourcetemplate) is dict:
        rt_dict = resourcetemplate
    else:
        rt_dict = load_yaml(resourcetemplate)

    # RPARM_redFixedIpR1_KT-VNF
    # RPARM_redFixedMacR1_KT-VNF
    # RPARM_redSubnetR1_KT-VNF
    # PNET_internetR1_KT-VNF
    # SUBN_internetR1_KT-VNF
    # -   port: { get_resource: PORT_redR1_KT-VNF }

    # parameters 항목 정리
    PARAM_TEMPLATE = ["RPARM_redFixedIp", "RPARM_redFixedMac", "RPARM_redSubnet"]

    param_names = rt_dict["parameters"].keys()
    length = len(param_names)
    for idx in range(length-1, -1, -1):
        param_name = param_names[idx]
        is_deleted = False
        for wr in wan_dels:
            for tmp in PARAM_TEMPLATE:
                if param_name.find(tmp + wr) >= 0:
                    log.debug("_____ Clean resourcetemplate : %s, %s" % (param_name, rt_dict["parameters"][param_name]))
                    del rt_dict["parameters"][param_name]
                    is_deleted = True
                    break
            if is_deleted:
                break

    # resources 항목 정리
    RESOURCE_TEMPLATE = ["PNET_internet", "SUBN_internet"]

    rsc_names = rt_dict["resources"].keys()
    length = len(rsc_names)

    port_dels = []
    for idx in range(length-1, -1, -1):
        rsc_name = rsc_names[idx]
        is_deleted = False

        if rsc_name.find("SERV_main") >= 0:
            ports = rt_dict["resources"][rsc_name]["properties"]["networks"]

            for k in range(len(ports)-1, -1, -1):
                for wr in wan_dels:
                    if ports[k]["port"]["get_resource"].find("red" + wr) >= 0:
                        port_dels.append(ports[k]["port"]["get_resource"])
                        log.debug("_____ Clean SERV_main port get_resource : %s, %s" % (ports[k]["port"]["get_resource"], ports[k]))
                        del ports[k]
                        break
        else:
            for wr in wan_dels:
                for tmp in RESOURCE_TEMPLATE:
                    if rsc_name.find(tmp + wr) >= 0:
                        log.debug("_____ Clean resources : %s, %s" % (rsc_name, rt_dict["resources"][rsc_name]))
                        del rt_dict["resources"][rsc_name]
                        is_deleted = True
                        break
                if is_deleted:
                    break

    for port_del in port_dels:
        log.debug("_____ Clean ports : %s, %s" % (port_del, rt_dict["resources"][port_del]))
        del rt_dict["resources"][port_del]

    return rt_dict


def _empty_wan_resourcetemplate(resourcetemplate, wan_dels):
    """
    resourcetemplate 에서 resource 항목 정리
    :param resourcetemplate: str 또는 dict type으로 넘어오는 resourcetemplate 데이타
    :return:
    """

    if type(resourcetemplate) is dict:
        rt_dict = resourcetemplate
    else:
        rt_dict = load_yaml(resourcetemplate)

    # parameters 항목 정리
    if wan_dels:
        PARAM_TEMPLATE = ["RPARM_redFixedIp", "RPARM_redFixedMac", "RPARM_redSubnet"]

        param_names = rt_dict["parameters"].keys()
        length = len(param_names)
        for idx in range(length-1, -1, -1):
            param_name = param_names[idx]
            is_deleted = False
            for wr in wan_dels:
                for tmp in PARAM_TEMPLATE:
                    if param_name.find(tmp + wr) >= 0:
                        log.debug("_____ Clean resourcetemplate : %s, %s" % (param_name, rt_dict["parameters"][param_name]))
                        del rt_dict["parameters"][param_name]
                        is_deleted = True
                        break
                if is_deleted:
                    break

    # resources 항목 정리
    RESOURCE_TEMPLATE = ["PNET_internet", "SUBN_internet"]

    rsc_names = rt_dict["resources"].keys()
    length = len(rsc_names)

    port_dels = []
    for idx in range(length-1, -1, -1):
        rsc_name = rsc_names[idx]

        if rsc_name.find("SERV_main") >= 0:
            ports = rt_dict["resources"][rsc_name]["properties"]["networks"]

            for k in range(len(ports)-1, -1, -1):
                if ports[k]["port"]["get_resource"].find("PORT_mgmt") >= 0:
                    continue

                port_dels.append(ports[k]["port"]["get_resource"])
                log.debug("_____ Delete port (SERV_main, Empty) : %s" % (ports[k]["port"]["get_resource"]))
                del ports[k]
        else:
            for tmp in RESOURCE_TEMPLATE:
                if rsc_name.find(tmp) >= 0:
                    log.debug("_____ Delete resource (Empty): %s, %s" % (rsc_name, rt_dict["resources"][rsc_name]))
                    del rt_dict["resources"][rsc_name]
                    break

    for port_del in port_dels:
        log.debug("_____ Delete resource > Port (Empty) : %s" % port_del)
        del rt_dict["resources"][port_del]

    return rt_dict


def switch_wan(mydb, onebox_id, tid=None, tpath=None):

    try:
        # server 상태체크
        server_result, server_data = orch_dbm.get_server_id(mydb, onebox_id)
        if server_result < 0:
            raise Exception("Failed to get server info from DB : onebox_id = %s" % onebox_id)

        if server_data['status'].find("N__") >= 0 or server_data['status'].find("E__") >= 0:
            if server_data['action'] is None or server_data['action'].endswith("E"):
                if server_data["nsseq"] is not None:
                    pass
                else:
                    raise Exception("서버에 NS정보가 존재하지 않습니다.")
            else:
                raise Exception("서버가 다른 작업을 진행중입니다.")
        else:
            raise Exception("서버가 다른 작업을 진행중입니다.")

        # nsr 상태체크크
        nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, server_data["nsseq"])
        if nsr_result < 0:
            raise Exception("Failed to get NSR Info for the VDU : nsseq=%s" % server_data["nsseq"])

        if nsr_data['status'].find("N__") >= 0 or nsr_data['status'].find("E__") >= 0:
            if nsr_data['action'] is None or nsr_data['action'].endswith("E"):
                pass
            else:
                raise Exception("NS가 다른 작업을 진행중입니다.")
        else:
            raise Exception("NS가 다른 작업을 진행중입니다.")

        # vnf 상태체크
        vnf_utm = None
        for vnf in nsr_data["vnfs"]:
            if vnf["name"] == "UTM" or vnf["name"] == "KT-VNF" or vnf["name"] == "AXGATE-UTM":
                vnf_utm = vnf
                break

        if vnf_utm is None:
            raise Exception("UTM이 존재하지 않습니다.")

        if vnf_utm["status"].find("N__") >= 0 or vnf_utm["status"].find("E__") >= 0:
            if vnf_utm['action'] is None or vnf_utm['action'].endswith("E"):
                pass
            else:
                raise Exception("NS가 다른 작업을 진행중입니다.")
        else:
            raise Exception("VNF가 다른 작업을 진행중입니다.")

        vdu_utm = None

        for vdu in vnf_utm["vdus"]:
            if vdu['name'].find("UTM") >= 0 or vdu['name'].find("KT-VNF") >= 0:
                vdu_utm = vdu
                break

        if vdu_utm is None:
            raise Exception("UTM VDU가 존재하지 않습니다.")

        vm_local_ip = None
        for cp in vdu_utm["cps"]:
            if cp['name'].find("local") >= 0 or cp['name'].find("blue") >= 0:
                vm_local_ip = cp['ip']
                break

        if vm_local_ip is None:
            log.error("Failed to get Local IP address of the VM: %s" % vdu_utm['name'])
            raise Exception("Cannot find the loca ip address of the VM")

        try:
            th = threading.Thread(target=_switch_wan_thread, args=(mydb, server_data["nsseq"], vdu_utm["name"], vm_local_ip, server_data["serverseq"]))
            th.start()
        except Exception, e:
            error_msg = "failed invoke a Thread for doing switch WAN: %s" % (str(e))
            log.exception(error_msg)
            raise Exception(error_msg)

        return 200, "OK"
    except Exception, e:
        log.exception("switch_wan() Error : %s" % str(e))
        return -HTTP_Internal_Server_Error, str(e)


def _switch_wan_thread(mydb, nsr_id, vdu_name, vm_local_ip, serverseq):

    server_dict = {"serverseq" : serverseq}
    # action : WS
    server_dict["action"] = "WS"
    orch_dbm.update_server_action(mydb, server_dict)
    # common_manager.update_server_status(mydb, server_dict)

    result, ob_agents = common_manager.get_onebox_agent(mydb, nsr_id=nsr_id)
    if result < 0:
        log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
        return result, str(ob_agents)

    myoba = ob_agents.values()[0]

    try:
        log.debug("Try 1st WAN Switch: time interval = 30 sec")
        result, ob_content = myoba.do_switch_wan("host2vm", vdu_name, vm_local_ip, time_interval = 30, e2e_log=None)
        if result < 0:
            log.debug("Failed to switch wan : %d %s" % (result, ob_content))
    except Exception, e:
        result = -HTTP_Internal_Server_Error
        content = str(e)
        log.exception(content)

    # action : WE
    server_dict["action"] = "WE"
    orch_dbm.update_server_action(mydb, server_dict)
    log.debug("__________ THREAD END _switch_wan_thread!")


def modify_nic(mydb, request, onebox_id, tid=None, tpath=None, use_thread=True, remote=False):
    """
        WAN Port 추가/삭제 처리 - 설변
    :param mydb:
    :param request:
    :param onebox_id:
    :param tid:
    :param tpath:
    :param use_thread:
    :param remote: router 사용 시 True
    :return:
    """
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
        log.debug("Action TID: %s" %action_tid)

        # Step.2 Get One-Box info. and check status
        ob_result, ob_data = orch_dbm.get_server_id(mydb, onebox_id) #common_manager.get_server_all_with_filter(mydb, onebox_id)
        if ob_result <= 0:
            log.error("get_server_with_filter Error %d %s" %(ob_result, ob_data))
            return ob_result, ob_data

        # ob_data = ob_content[0]

        if ob_data['status'] == SRVStatus.LWT or ob_data['status'] == SRVStatus.PVS or ob_data['status'] == SRVStatus.OOS or ob_data['status'] == SRVStatus.ERR:
            return -HTTP_Bad_Request, "Cannot modify NIC of the One-Box in the status of %s" %(ob_data['status'])

        if ob_data['action'] is None or ob_data['action'].endswith("E"): # NGKIM: Use RE for backup
            pass
        else:
            return -HTTP_Bad_Request, "The One-Box is in Progress for another action: status= %s action= %s" %(ob_data['status'], ob_data['action'])

        ob_org_status = ob_data['status']

        # Step.3 Update One-Box status
        action_dict = {'tid':action_tid}
        action_dict['category'] = "NICModify"
        action_dict['action'] = "NS"
        action_dict['action_user'] = "admin"
        action_dict['server_name'] = ob_data['servername']
        action_dict['server_seq'] = ob_data['serverseq']

        try:
            e2e_log = e2elogger(tname='One-Box NIC modify', tmodule='orch-f', tid=action_tid, tpath="/orch_onebox-nic_modify")
        except Exception, e:
            log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

    except Exception, e:
        error_msg = "failed invoke a Thread for modifying NIC %s" %str(e)
        log.exception(error_msg)
        return -HTTP_Internal_Server_Error, error_msg
    try:

        # 1. One-Box WAN 정보 Update : 기존 데이타 삭제 후, 새로 받은 정보 저장
        result_wan, db_wan_list = orch_dbm.get_server_wan_list(mydb, ob_data['serverseq'])
        if result_wan < 0:
            raise Exception("Failed to get wan list from DB %d %s" % (result_wan, db_wan_list))

        # 추가/삭제된 WAN이 있는지 체크...
        if len(request["wan_list"]) == result_wan:
            log.debug("__________ 추가되거나 삭제된 WAN Port가 없다. : %s" % request["wan_list"])
            raise Exception("No change wan count")

        common_manager.update_onebox_status_internally(mydb, ActionType.NICMD, action_dict=action_dict, action_status=ACTStatus.STRT, ob_data=ob_data, ob_status=SRVStatus.OOS)

        # # One-Box 정보가 넘어올때, WAN Port 추가/삭제 내용외에 public IP 변경이나 다른 설변 내용이 함께 넘어올 수 있다.
        # # new_server에서 이 부분을 처리해야 한다. 단, WAN Port 관련 부분은 nic_modify 프로세스에서 처리해야하니 new_server에서 건들지 않도록 조치가 필요하다.
        # # if ob_data["publicip"] != request["public_ip"]:
        # new_server(mydb, request, filter_data=onebox_id, use_thread=False, is_wad=True)

        # Step 4. Start One-Box backup
        if use_thread:
            th = threading.Thread(target=_modify_nic_thread, args=(mydb, ob_data, db_wan_list, ob_org_status, action_dict, request, e2e_log, True, remote))
            th.start()

            return_data = {"action_type": "NS", "action_id": action_tid,"status": "DOING"}
        else:
            return _modify_nic_thread(mydb, ob_data, db_wan_list, ob_org_status, action_dict, request, e2e_log=e2e_log, use_thread=False, remote=remote)
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        common_manager.update_onebox_status_internally(mydb, ActionType.NICMD, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
        return -HTTP_Internal_Server_Error, "NIC modify가 실패하였습니다. 원인: %s" %str(e)

    return 200, return_data


def _modify_nic_thread(mydb, ob_data, db_wan_list, ob_org_status, action_dict, request={}, e2e_log=None, use_thread=True, remote=False):

    if use_thread:
        log.debug("[THREAD STARTED] _modify_nic_thread()")

    rlt_dict = None
    # rollback 용
    rlt_dict_ori = None

    # empty resourcetemplate
    resourcetemplate_empty = None

    # remote_dict = None

    try:
        # new_server로 기존 네트워크 목록이 변경되기 전에 값을 가지고 있는다.
        # 변경된 항목에 대해 모니터링 업데이트 용도.
        result, nw_list = orch_dbm.get_onebox_nw_serverseq(mydb, ob_data["serverseq"])
        if result < 0:
            raise Exception("Failed to get onebox network info.")

        # One-Box 정보가 넘어올때, WAN Port 추가/삭제 내용외에 public IP 변경이나 다른 설변 내용이 함께 넘어올 수 있다.
        # new_server에서 이 부분을 처리해야 한다. 단, WAN Port 관련 부분은 nic_modify 프로세스에서 처리해야하니 new_server에서 건들지 않도록 조치가 필요하다.
        # if ob_data["publicip"] != request["public_ip"]:

        new_server(mydb, request, filter_data=ob_data["onebox_id"], use_thread=False, is_wad=True)

        # public_ip > remote_ip : router 이용 시 사용됨. dhcp public_ip 설정하기 위함
        remote_dict = {}

        if 'router' in remote:
            if remote.get('router'):
                remote_dict['origin_ip'] = remote.get('origin_ip')
                remote_dict['public_ip'] = remote.get('public_ip')
                remote_dict['router'] = True

        common_manager.update_onebox_status_internally(mydb, ActionType.NICMD, action_dict=action_dict, action_status=ACTStatus.INPG, ob_data=ob_data, ob_status=SRVStatus.OOS)

        # 1.1. 변경된 wan_list 데이타 보정작업
        # 삭제시는 config작업은 필요없다. heat update 후 재부팅만 해주면 된다.
        # 추가시 R0~N의 name을 정해야한다. 순서대로 0,1,2,3

        log.debug("__________ 1 변경된 wan_list 데이타 보정작업")
        for idx in range(len(request["wan_list"])-1, -1, -1):
            wan = request["wan_list"][idx]

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

        # Active/Standby 를 정하기 위해 기존 데이타에서 Active인 WAN을 찾는다.
        public_nic = "eth0"
        for db_wan in db_wan_list:
            if db_wan["status"] == "A":
                public_nic = db_wan["nic"]
                break

        r_num = 0
        for wan in request["wan_list"]:
            if wan["nic"] == public_nic:
                wan["status"] = "A"
            else:
                wan["status"] = "S"

            # wan_list 순서대로 R0~N 주는 방식으로 변경처리.
            wan["name"] = "R"+ str(r_num)
            r_num += 1

            # public_ip_dhcp 항목을 ipalloc_mode_public 형태로 변경처리
            if wan['public_ip_dhcp']:
                wan['ipalloc_mode_public'] = "DHCP"
            else:
                wan['ipalloc_mode_public'] = "STATIC"

        log.debug("__________ 1.2. 보정된 wan_list : %s" % request["wan_list"])

        # 2. RLT 변경 : Parameters, HOT
        result, rlt_data = orch_dbm.get_rlt_data(mydb, ob_data["nsseq"])
        if result < 0:
            log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

        rlt_dict = rlt_data["rlt"]
        rlt_dict_ori = copy.deepcopy(rlt_dict) # rollback 용

        update_nsr_status(mydb, ActionType.NICMD, nsr_data=rlt_dict, nsr_status=NSRStatus.NIC_updatingrlt)

        result, nsd_data = orch_dbm.get_nsd_id(mydb, rlt_dict["nscatseq"])

        wan_dels = _get_wan_dels_by_list(request["wan_list"])
        log.debug("_____ get_wan_dels : %s " % wan_dels)
        nsd_data['parameters'] = common_manager.clean_parameters(nsd_data['parameters'], wan_dels)

        # 기존 RLT의 Parameters의 value를 새로 만드는 Parameters에 부어 넣는다.
        # WAN (red) 을 제외한 다른 Parameter의 값을 채우기위한 작업 > 변경된 WAN 포트 정보 아래 로직에서 모든 WAN 포트 정보를 업데이트 처리한다.
        for param1 in nsd_data['parameters']:
            for param2 in rlt_dict['parameters']:
                if param1["name"] == param2["name"]:
                    param1["value"] = param2["value"]
                    break
        # RLT Parameters를 새로 만든 것으로 교체한다.
        rlt_dict['parameters'] = nsd_data['parameters']

        # UTM WAN Port 관련 rlt paramters value 작업
        # 변경된 WAN 관련 Parameter의 value를 새로 채운다.
        vnf_name_list_utm = []
        for vnf in rlt_dict["vnfs"]:
            if vnf["nfsubcategory"] == "UTM":
                vnf_name_list_utm.append(vnf["name"])

        # log.debug('request > wan_list = %s' %str(request["wan_list"]))
        ####################    router      ######################################################
        # for w in request['wan_list']:
        #     if common_manager._private_ip_check(w.get('public_ip')) == -1:
        #         if remote_dict is not None:
        #             w['public_ip'] = remote_dict.get('public_ip')
        #             break
        ####################    router      ######################################################

        common_manager.set_paramters_of_wan(vnf_name_list_utm, rlt_dict["parameters"], request["wan_list"])

        log.debug("__________ 2. 보정된 기존 RLT의 Parameters : %s" % rlt_dict['parameters'])

        # cps 재구성
        for vnf in rlt_dict["vnfs"]:
            for vnfd in nsd_data["vnfs"]:
                if vnf["name"] == vnfd["name"]:
                    for vdu in vnf["vdus"]:
                        for vdud in vnfd["vdus"]:
                            if vdu["name"] == vdud["name"]:
                                vdu["cps"] = vdud["cps"]
                                break
                    break

        # 3. Heat Stack Update : VNF vPort 구성 변경
        update_nsr_status(mydb, ActionType.NICMD, nsr_data=rlt_dict, nsr_status=NSRStatus.NIC_updatingvr)

        add_wan_list = []
        del_wan_list = copy.deepcopy(db_wan_list)
        for wan1 in request["wan_list"]:
            for wan2 in del_wan_list:
                if wan1["nic"] == wan2["nic"]:
                    del_wan_list.remove(wan2)
                    break
            else:
                add_wan_list.append(wan1)

        # resourcetemplate 재구성
        if nsd_data['resourcetemplatetype'] == "hot":
            rt_dict = _clean_wan_resourcetemplate(nsd_data['resourcetemplate'], wan_dels)
            # 정리된 resourcetemplate dictionary 객체를 다시 yaml 포맷 문자열로 변경
            ns_hot_result, ns_hot_value = compose_nsd_hot(nsd_data['name'], [rt_dict])
            if ns_hot_result < 0:
                log.error("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
                raise Exception("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
            rlt_dict['resourcetemplate'] = ns_hot_value
            log.debug("_____ 2.1. 재구성한 resourcetemplate : %s" % ns_hot_value)

            # 포트 삭제시 WAN이 빈 resourcetemplate 만들기
            if del_wan_list:
                rt_empty = _empty_wan_resourcetemplate(nsd_data['resourcetemplate'], wan_dels)
                empty_hot_result, empty_hot_value = compose_nsd_hot(nsd_data['name'], [rt_empty])
                if empty_hot_result < 0:
                    log.error("Failed to compose nsd hot %d %s" % (empty_hot_result, empty_hot_value))
                    raise Exception("Failed to compose nsd hot %d %s" % (empty_hot_result, empty_hot_value))
                resourcetemplate_empty = empty_hot_value
                log.debug("_____ 2.2. Empty resourcetemplate : %s" % resourcetemplate_empty)

        # log.debug('#########################    rlt_dict = %s' %str(rlt_dict))
        # log.debug('#########################    resourcetemplate_empty = %s' %str(resourcetemplate_empty))

        return_code, return_data = _heat_update_for_nic(mydb, rlt_dict, resourcetemplate_empty, e2e_log, is_wan_switch=False, remote_dict=remote_dict)
        if return_code < 0:
            raise Exception("RB_HEAT", return_data)

        log.debug("_____ 3.Update Heat Stack & 4.VNF VM 재부팅 Finished ")

        # 5. 추가된 VNF vPort 초기 설정
        # get_session, get_auth는 필수 포함...추가된 R1...등의 스크립트만 전달.

        # 추가된 WAN 이 있을경우에만 config 작업처리.
        # # TODO: _new_wan_vnf_conf 는 Agent에서 처리하기로 함...아래로직 삭제 예정
        # if add_wan_list:
        #     result, content = _new_wan_vnf_conf(mydb, rlt_dict, ob_data["serverseq"], add_wan_list, e2e_log)
        #     if result < 0:
        #         raise Exception("RB_HEAT_CONF", "Failed to set init-config by vnfm")
        #     log.debug("_____ 5.3. 추가된 VNF vPort 초기 설정")
        # log.debug("_____ 5. VNF vPort 초기 설정 END ")

        # 6. DB Processing
        update_nsr_status(mydb, ActionType.NICMD, nsr_data=rlt_dict, nsr_status=NSRStatus.NIC_processingdb)

        # 기존 wan 데이타 삭제처리
        wan_result, wan_content = orch_dbm.delete_server_wan(mydb, {"serverseq":ob_data["serverseq"]}, kind="R")
        if wan_result < 0:
            return wan_result, wan_content

        # 변경된 wan 데이타 저장처리
        for wan in request["wan_list"]:
            wan["serverseq"] = ob_data["serverseq"]
            wan["onebox_id"] = ob_data.get("onebox_id")

            # mode가 대문자로 오는경우 처리 --> 소문자로 변경
            wan["mode"] = str(wan["mode"]).lower()

            wan_result, wan_content = orch_dbm.insert_server_wan(mydb, wan)
            if wan_result < 0:
                return wan_result, wan_content

        result, content = orch_dbm.delete_nsr_param(mydb, {"nsseq" : rlt_dict['nsseq']})
        if result < 0:
            raise Exception("failed to DB Delete of old NSR parameters: %d %s" %(result, content))

        result, content = orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])
        if result < 0:
            raise Exception("failed to DB Insert New NSR Params: %d %s" %(result, content))

        # cp 삭제 후 새로 저장
        for vnf in rlt_dict['vnfs']:
            for vm in vnf['vdus']:

                result, content = mydb.delete_row_seq("tb_cp", "vduseq", vm['vduseq'], None)
                if result < 0:
                    log.error("delete cp error %d %s" % (result, content))
                    raise Exception("failed to delete CP info.: %d %s" %(result, content))

                if 'cps' in vm:
                    for cp in vm['cps']:
                        INSERT_={'name':cp['name'], 'uuid':cp['uuid'], 'vim_name':cp['vim_name'], 'vduseq': vm['vduseq'], 'cpdseq': cp['cpdseq'], 'ip':cp.get('ip')}
                        INSERT_['modify_dttm'] = datetime.datetime.now()
                        r, instance_cp_id = mydb.new_row('tb_cp', INSERT_, None, False)
                        if r < 0:
                            raise Exception("failed to DB Insert CP info.: %d %s" %(r, instance_cp_id))
                        cp['cpseq']=instance_cp_id

        # 기존 백업정보 OOD 변경 : "category":"onebox"
        result, content = orch_dbm.update_backup_history(mydb, {"ood_flag":"TRUE"}, {"serverseq":ob_data["serverseq"]})

        # rlt 업데이트
        result, content = orch_dbm.update_rlt_data(mydb, json.dumps(rlt_dict), rlt_seq=rlt_data["rltseq"])
        if result < 0:
            raise Exception("failed to DB Update for RLT: %d %s" %(result, content))

        if e2e_log:
            e2e_log.job('Process DB data', CONST_TRESULT_SUCC, tmsg_body=None)

        log.debug("_____ 6. DB 처리 Finished ")

        # 7. 모니터링 Update
        update_nsr_status(mydb, ActionType.NICMD, nsr_data=rlt_dict, nsr_status=NSRStatus.NIC_resumingmonitor)
        monitor = common_manager.get_ktmonitor()
        if monitor is None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        target_dict = {}
        # target_dict['tmode'] = "1"
        target_dict['change_info'] = []

        for add_wan in add_wan_list:

            chg_wan = {"svrseq":ob_data["serverseq"], "after_lan":"wan"}
            chg_wan["after_eth"] = add_wan["nic"]

            for nw in nw_list:
                # 기존에 다른 용도로 사용하는 경우
                if add_wan["nic"] == nw["name"] and nw["display_name"] != "wan":
                    chg_wan["before_lan"] = nw["display_name"]
                    chg_wan["before_eth"] = nw["name"]
                    break
            else:
                # 기존에 없고 새로 추가된 경우
                chg_wan["before_lan"] = ""
                chg_wan["before_eth"] = ""

            target_dict['change_info'].append(chg_wan)

        for del_wan in del_wan_list:
            for nw in nw_list:
                if del_wan["nic"] == nw["name"]:
                    chg_wan = {"svrseq":ob_data["serverseq"], "after_lan":"", "after_eth":""}
                    chg_wan["before_lan"] = "wan"
                    chg_wan["before_eth"] = del_wan["nic"]
                    target_dict['change_info'].append(chg_wan)
                    break

        result, data = monitor.update_monitor_onebox(target_dict, e2e_log)
        if result < 0:
            log.error("Error %d %s" %(result, data))

        if e2e_log:
            e2e_log.job('Update Monitor for One-Box', CONST_TRESULT_SUCC, tmsg_body=None)
        log.debug("_____ 7. 모니터링 업데이트 : target_dict = %s" % target_dict)

        update_nsr_status(mydb, ActionType.NICMD, nsr_data=rlt_dict, nsr_status=NSRStatus.RUN)

        # common_manager.update_nsr_for_latest(mydb, ob_data, rlt_dict['nsseq'])

        # Update One-Box status
        common_manager.update_onebox_status_internally(mydb, ActionType.NICMD, action_dict=action_dict, action_status=ACTStatus.SUCC, ob_data=ob_data, ob_status=SRVStatus.INS)

    except Exception, e:
        log.exception("__________ _MODIFY_NIC_THREAD : Exception: %s" %str(e))

        action_type = ActionType.NICMD
        nsr_status_val = NSRStatus.ERR
        ob_status_val = SRVStatus.ERR

        if len(e.args) == 2:
            error_code, error_msg = e
        else:
            error_code = "NONE"
            error_msg = str(e)

        if error_code.find("RB_HEAT") >= 0:
            # rollback :heat update
            log.debug("___________ _MODIFY_NIC_THREAD > Rollback 시도 [%s, %s]" % (error_code, error_msg))
            return_code, return_data = _heat_update_for_nic(mydb, rlt_dict_ori, resourcetemplate_empty, e2e_log, is_wan_switch=False)
            if return_code < 0:
                log.debug("___________ _MODIFY_NIC_THREAD > Rollback 실패 [%s, %s]" % (return_code, return_data))
                pass
            else:
                # rollback 성공
                log.debug("___________ _MODIFY_NIC_THREAD > Rollback 성공 [%s, %s]" % (return_code, return_data))
                # rollback 성공인 경우, action_type을 "M" 로 변경해서 VNF vPort구성 변경완료체크 API에서 "ERROR" 를 리턴할 수 있도록 (One-Box쪽도 록백할 수 있게...)
                action_type = ActionType.NICER
                nsr_status_val = NSRStatus.RUN
                ob_status_val = SRVStatus.INS

        if rlt_dict:
            update_nsr_status(mydb, ActionType.NICMD, nsr_data=rlt_dict, nsr_status=nsr_status_val)
        common_manager.update_onebox_status_internally(mydb, action_type, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_status_val)

        if e2e_log:
            e2e_log.job('NIC Modify Fail', CONST_TRESULT_FAIL,
                        tmsg_body="serverseq: %s\nResult: NIC modify가 실패하였습니다. 원인: %s" % (str(ob_data['serverseq']), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, str(e)

    if e2e_log:
        e2e_log.job('NIC modify Finished', CONST_TRESULT_SUCC, tmsg_body="")
        e2e_log.finish(CONST_TRESULT_SUCC)

    if use_thread:
        log.debug("[THREAD FINISHED] _modify_nic_thread()")
    return 200, "OK"


def _heat_update_for_nic(mydb, rlt_dict, resourcetemplate_empty, e2e_log=None, is_vm_boot=True, is_wan_switch=True, remote_dict=None):
    try:
        log.debug("__________ 3.1. _HEAT_UPDATE_FOR_NIC > START")
        # Vim connector 가져오기
        result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
        myvim = vims.values()[0]

        # Compose Heat Parameters
        template_param_list = []
        for param in rlt_dict['parameters']:
            if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
                template_param_list.append(param)

        stack_uuid = rlt_dict["uuid"]
        nsr_name = rlt_dict["name"]
        if e2e_log:
            e2e_log.job('Update Heat Stack', CONST_TRESULT_NONE, tmsg_body=None)

        log.debug("_____ Update Heat Stack : uuid = %s" % stack_uuid)

        # WAN 관련 항목을 다 지워서 빈 값으로 만든후
        if resourcetemplate_empty:

            log.debug("__________ 3.1.1. _HEAT_UPDATE_FOR_NIC > HEAT UPDATE with empty resourcetmeplate")

            result, msg = myvim.update_heat_stack_v4(nsr_name, stack_uuid, rlt_dict['resourcetemplatetype'], resourcetemplate_empty, template_param_list)
            if result < 0:
                log.error("Failed to update Heat Stack[%s] : %d %s" % (nsr_name, result, msg))
                if e2e_log:
                    e2e_log.job('Update Heat Stack with empty WAN', CONST_TRESULT_FAIL, tmsg_body="Failed to update Heat Stack with empty WAN[%s] : %d %s" % (nsr_name, result, msg))
                raise Exception("Failed to update Heat Stack with empty WAN[%s] : %d %s" % (nsr_name, result, msg))
            if e2e_log:
                e2e_log.job('Update Heat Stack with empty WAN', CONST_TRESULT_SUCC, tmsg_body=None)

            time.sleep(20)

        log.debug("__________ 3.2. _HEAT_UPDATE_FOR_NIC > HEAT UPDATE START")

        result, msg = myvim.update_heat_stack_v4(nsr_name, stack_uuid, rlt_dict['resourcetemplatetype'], rlt_dict['resourcetemplate'], template_param_list)
        if result < 0:
            log.error("Failed to update Heat Stack[%s] : %d %s" % (nsr_name, result, msg))
            if e2e_log:
                e2e_log.job('Update Heat Stack', CONST_TRESULT_FAIL, tmsg_body="Failed to update Heat Stack[%s] : %d %s" % (nsr_name, result, msg))
            raise Exception("Failed to update Heat Stack[%s] : %d %s" % (nsr_name, result, msg))
        if e2e_log:
            e2e_log.job('Update Heat Stack', CONST_TRESULT_SUCC, tmsg_body=None)
        log.debug("__________ 3.3. _HEAT_UPDATE_FOR_NIC > HEAT UPDATE END")

        time.sleep(20)

        retry_cnt = 0
        RETRY_MAX = 1

        while True:
            rt_step2, content = _heat_update_for_nic_step2(mydb, rlt_dict, myvim, stack_uuid, nsr_name, template_param_list, e2e_log, is_vm_boot, is_wan_switch, remote_dict)
            if rt_step2 < 0:
                log.warning("__________ Failed to invoke _heat_update_for_nic_step2 : %d %s " % (rt_step2, content))
                retry_cnt += 1
                if retry_cnt <= RETRY_MAX:
                    time.sleep(10)
                    log.debug("__________ RETRY _heat_update_for_nic_step2 : %d" % retry_cnt)
                else:
                    raise Exception(content)
            else:
                break

        # if e2e_log:
        #     e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_NONE, tmsg_body=None)
        #
        # result, stack_info = myvim.get_heat_stack_id_v4(stack_uuid)
        # if result < 0:
        #     log.error("Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))
        #     if e2e_log:
        #         e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
        #     raise Exception("Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))
        #
        # result, stack_resources = myvim.get_heat_resource_list_v4(stack_uuid)
        # if result < 0:
        #     log.error("Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))
        #     if e2e_log:
        #         e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
        #     raise Exception("Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))
        #
        # if e2e_log:
        #     e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_SUCC, tmsg_body=None)
        #
        # _set_stack_data(rlt_dict, stack_resources, stack_info, rlt_dict["name"], template_param_list)
        #
        # if is_vm_boot:
        #
        #     needWanSwitch = False
        #     if is_wan_switch:
        #         result, needWanSwitch = _need_wan_switch(mydb, {"nsseq": rlt_dict["nsseq"]})
        #
        #     for vnf in rlt_dict['vnfs']:
        #         for vm in vnf['vdus']:
        #             result, content = _action_vdu_reboot(mydb, rlt_dict["nsseq"], vm, myvim, needWanSwitch, None, rlt_dict["vimseq"], e2e_log, 'HARD')
        #             if result < 0:
        #                 log.error("Failed to reboot VDU: %d %s" % (result, content))
        #                 if e2e_log:
        #                     e2e_log.job('Failed to reboot VDU', CONST_TRESULT_FAIL, tmsg_body="Failed to reboot VDU: %d %s" % (result, content))
        #     time.sleep(90)
    except Exception, e:
        return -500, str(e)
    return 200, "OK"

def _heat_update_for_nic_step2(mydb, rlt_dict, myvim, stack_uuid, nsr_name, template_param_list, e2e_log=None, is_vm_boot=True, is_wan_switch=True, remote_dict=None):

    try:
        if e2e_log:
            e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_NONE, tmsg_body=None)

        result, stack_info = myvim.get_heat_stack_id_v4(stack_uuid)
        if result < 0:
            log.error("Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))
            if e2e_log:
                e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))

        # log.debug('                 [BBG] stack_info = %s' %str(stack_info))

        result, stack_resources = myvim.get_heat_resource_list_v4(stack_uuid)
        if result < 0:
            log.error("Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))
            if e2e_log:
                e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))

        if e2e_log:
            e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_SUCC, tmsg_body=None)

        # log.debug('[BBG] get_heat_resource_list_v4 = %s' %str(stack_resources))

        # router 사용시
        # log.debug('[_heat_update_for_nic_step2] remote_dict = %s' %str(remote_dict))

        _set_stack_data(rlt_dict, stack_resources, stack_info, rlt_dict["name"], template_param_list)

        if is_vm_boot:

            needWanSwitch = False
            if is_wan_switch:
                result, needWanSwitch = _need_wan_switch(mydb, {"nsseq": rlt_dict["nsseq"]})

            for vnf in rlt_dict['vnfs']:
                for vm in vnf['vdus']:
                    log.debug("__________ 3.4. _HEAT_UPDATE_FOR_NIC > REBOOT START")
                    # log.debug('__________ vm = %s' %str(vm))
                    result, content = _action_vdu_reboot(mydb, rlt_dict["nsseq"], vm, myvim, needWanSwitch, None, rlt_dict["vimseq"], e2e_log, 'HARD', remote_dict=remote_dict)
                    if result < 0:
                        log.error("Failed to reboot VDU: %d %s" % (result, content))
                        if e2e_log:
                            e2e_log.job('Failed to reboot VDU', CONST_TRESULT_FAIL, tmsg_body="Failed to reboot VDU: %d %s" % (result, content))
                        raise Exception(content)
                    log.debug("__________ 3.5. _HEAT_UPDATE_FOR_NIC > REBOOT END")
            time.sleep(90)
    except Exception, e:
        log.error("__________ Fail _heat_update_for_nic_step2() : %s" % str(e))
        return -500, str(e)
    return 200, "OK"


def _get_wan_dels_by_list(wan_list):
    """
    회선이중화 관련 작업. Agent에서 받은 wan_list를 확인해서 사용하지 않는 WAN 리스트 작성
    :param wan_list: Agent에서 받은 wan_list
    :return: 사용하지 않는 WAN 리스트
    """
    wan_dels = ["R1", "R2", "R3"]
    for wan in wan_list:
        if wan["name"] == "R0":
            continue
        wan_dels.remove(wan["name"])

    return wan_dels


def upgrade_vnf_with_image(mydb, vnf_id, req_dict, tid=None, tpath="", use_thread=True):
    """
        VNF image version Update 처리.
    :param mydb:
    :param vnf_id: nfseq
    :param req_dict: {'image_id':<string> [vdudimageseq], 'update_dt':<string>, 'memo':<string>, 'mode':<string> [M or A]}
    :param tid:
    :param tpath:
    :param use_thread:
    :return:
    """
    e2e_log = None
    try:

        mode = req_dict["mode"]
        if mode == "A":
            if req_dict.get("image_id", None) is None:
                raise Exception("Need image_id parameter!")

        try:
            if not tid:
                e2e_log = e2elogger(tname='VNF Upgrade', tmodule='orch-f', tpath="orch_vnf-upgrade")
            else:
                e2e_log = e2elogger(tname='VNF Upgrade', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_vnf-upgrade")
        except Exception, e:
            log.error("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
            e2e_log = None

        if e2e_log:
            e2e_log.job('VNF Upgrade Orch 제어 시작', CONST_TRESULT_SUCC, tmsg_body="VNF ID: %s\n Request Body: %s" % (str(vnf_id), str(req_dict)))

        # 1. Get vnfr, nsr, onebox, customer info
        # 1-1. Get VNF record
        vnf_result, vnf_data = orch_dbm.get_vnf_id(mydb, vnf_id)
        if vnf_result <= 0:
            log.error("failed to get VNF Info from DB : %d %s" % (vnf_result, vnf_data))
            raise Exception("Failed to get VNF Info from DB")

        if vnf_data['action'] is None or vnf_data['action'].endswith("E"):  # NGKIM: Use RE for backup
            pass
        else:
            log.error("The VNF is in Progress for another action: status= %s action= %s" % (vnf_data['status'], vnf_data['action']))
            raise Exception("다른 Action이 진행 중입니다. VNF 상태를 확인하세요.")

        nsr_id = vnf_data['nsseq']

        if e2e_log:
            e2e_log.job("Get VNF record", CONST_TRESULT_SUCC, tmsg_body=None)

        # 1-2. Get NS record
        nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr_id)
        if nsr_result <= 0:
            log.error("failed to get NSR Info from DB : %d %s" % (nsr_result, nsr_data))
            raise Exception("Failed to get NSR Info From DB")

        if e2e_log:
            e2e_log.job("Get NS record", CONST_TRESULT_SUCC, tmsg_body=None)

        if nsr_data['action'] is None or nsr_data['action'].endswith("E"):  # NGKIM: Use RE for backup
            pass
        else:
            log.error("The NS is in Progress for another action: status= %s action= %s" % (nsr_data['status'], nsr_data['action']))
            raise Exception("다른 Action이 진행 중입니다. NSR 상태를 확인하세요.")

        # 1-3. Get customer info and server info
        customer_result, customer_data = orch_dbm.get_customer_resources(mydb, nsr_data['customerseq'])
        if customer_result <= 0:
            log.error("Failed to get Customer Info From DB: %d %s" % (customer_result, customer_data))
            raise Exception("Failed to get Customer Info From DB")

        server_dict = None
        for resource in customer_data:
            if resource['resource_type'] == 'server' and resource['nsseq'] == nsr_id:
                server_dict = {'serverseq': resource['serverseq'], 'name': resource['servername'], 'status': resource['status']
                                , 'action': resource['action'], 'publicip': resource['publicip'], 'mgmtip': resource['mgmtip']}
                server_dict['onebox_id'] = resource['onebox_id']

                server_dict["server_id"] = resource["serverseq"]
                server_dict["server_uuid"] = resource["serveruuid"]
                server_dict["server_onebox_id"] = resource["onebox_id"]
                server_dict["server_mgmt_ip"] = resource["mgmtip"]
                break

        if server_dict is None:
            log.error("failed to get Server info from DB")
            raise Exception("Failed to get Server Info from DB")

        if e2e_log:
            e2e_log.job("Get customer info and server info", CONST_TRESULT_SUCC, tmsg_body=None)

        # 1-4 Check Server Status
        log.debug("server status = %s, server action = %s" % (server_dict['status'], server_dict['action']))
        if server_dict['status'] == SRVStatus.DSC:
            log.error("The One-Box is not connected. Check One-Box: status = %s, action = %s" % (server_dict['status'], server_dict['action']))
            raise Exception("One-Box가 Disconnected 되어 있습니다. One-Box 상태를 확인하세요.")

        if server_dict['action'] is None or server_dict['action'].endswith("E") or len(server_dict['action']) == 0:
            pass
        else:
            log.error("The One-Box is in Progress for another action: status = %s, action = %s" % (server_dict['status'], server_dict['action']))
            raise Exception("다른 Action이 진행 중입니다. One-Box 상태를 확인하세요.")

        if e2e_log:
            e2e_log.job("Check Server Status", CONST_TRESULT_SUCC, tmsg_body=None)

        # 3. Get RLT Data
        log.debug("[VNF Upgrade] _____1. Get RLT Data_____")
        result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_id)
        if result < 0:
            log.error("[VNF Upgrad][NS] : Error, failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("Failed to get RLT data from DB")

        if e2e_log:
            e2e_log.job('Get RLT Data', CONST_TRESULT_SUCC,
                        tmsg_body="RLT Data: rltseq: %d\n RLT: %s" % (rlt_data["rltseq"], json.dumps(rlt_data['rlt'], indent=4)))

        rlt_dict = rlt_data["rlt"]

        mode = req_dict["mode"]
        if mode == "A":
            if use_thread:
                th = threading.Thread(target=upgrade_vnf_with_image_thread,
                                      args=(mydb, req_dict, vnf_data, rlt_dict, server_dict, e2e_log))
                th.start()
                return 200, "VNF Update를 시작합니다."
            else:
                return upgrade_vnf_with_image_thread(mydb, req_dict, vnf_data, rlt_dict, server_dict, e2e_log)
        else:
            return upgrade_vnf_with_image_menual(mydb, req_dict, vnf_data, rlt_dict, server_dict, e2e_log)

    except Exception, e:
        log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
        if e2e_log:
            e2e_log.job('VNF Upgrade Orch 제어 시작 실패', CONST_TRESULT_FAIL,
                        tmsg_body="VNF ID: %s\n Request Body: %s\nCause: %s" % (str(vnf_id), json.dumps(req_dict, indent=4), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, str(e)

def upgrade_vnf_with_image_thread(mydb, req_dict, vnf_data, rlt_dict, server_dict, e2e_log):

    action_dict={'category':"NFRestore"}
    try:
        log.debug("[VNF Upgrade] _____2. VNF Image Check and Deploy Check_____")

        img_result, img_data_r = orch_dbm.get_vnfd_vdu_image(mydb, {"vdudimageseq":req_dict["image_id"]})
        if img_result < 0:
            raise Exception("Failed to get vdu_image : vdudimageseq = %s" % req_dict["image_id"])
        img_data = img_data_r[0]

        server_dict['nsseq'] = rlt_dict['nsseq']
        update_nsr_status(mydb, ActionType.IMGUP, action_dict=None, action_status=None, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU, server_dict=server_dict, server_status=SRVStatus.OOS)

        # 4. image release to One-Box if necessary
        # 배포되었는지 체크
        result, vnfimage_r = orch_dbm.get_server_vnfimage(mydb, {"serverseq":server_dict["serverseq"], "location":img_data["location"]})
        if result < 0:
            raise Exception("Failed to get tb_server_vnfimage record : %d, %s" % (result, vnfimage_r))
        elif result > 0 and vnfimage_r[0]["status"] == ImageStatus.COMPLETE:
            pass
        else:
            # 배포처리
            update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU_deploy)
            req_data = {"release":{"target_onebox":[server_dict["serverseq"]]}}
            result, data = deploy_vnf_image(mydb, vnf_data["nfcatseq"], req_dict["image_id"], req_data, use_thread=False, e2e_log=e2e_log)
            if result < 0:
                # TODO: SERVER/NSR을 에러처리할 필요는 없다???
                raise Exception("Failed to deploy vnf image : Error %d %s" %(result, data))

        # 5. suspend NS Monitoring
        log.debug("[VNF Upgrade] _____3. Suspend NS Monitoring_____")
        update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU_suspendingmonitor)

        monitor_result, monitor_data = suspend_nsr_monitor(mydb, rlt_dict, server_dict, e2e_log)

        if monitor_result < 0:
            log.warning("_restore_nsr_thread() failed to stop monitor. False Alarms are expected")
            if e2e_log:
                e2e_log.job("Suspend monitoring", CONST_TRESULT_FAIL, tmsg_body=None)
        else:
            if e2e_log:
                    e2e_log.job("Suspend monitoring", CONST_TRESULT_SUCC, tmsg_body=None)

        log.debug("[VNF Upgrade] _____4. Composed RLT Parameter for VNF Image ID_____")
        for param in rlt_dict["parameters"]:
            if param['name'] == "RPARM_imageId_" + vnf_data['name']:
                param['value'] = img_data["name"]
                log.debug("[VNF Upgrade] Image Param Info is changed to %s" %str(param))
                break

        if e2e_log:
            e2e_log.job('Composed RLT Data with new vnf image id', CONST_TRESULT_SUCC,
                        tmsg_body="RLT Data: %s" % (json.dumps(rlt_dict, indent=4)))

        # finish VNF
        result, data = _finish_vnf_using_ktvnfm(mydb, rlt_dict['serverseq'], vnf_data['vdus'], e2e_log)
        if result < 0:
            log.error("Failed to finish VNF %s: %d %s" % (vnf_data['name'], result, data))
            if result == -HTTP_Not_Found:
                log.debug("One-Box is out of control. Skip finishing VNFs")
            else:
                raise Exception("Failed to finish VNF %s: %d %s" % (vnf_data['name'], result, data))

        # 6. Heat Update
        # result, need_wan_switch = _need_wan_switch(mydb, {"serverseq": server_dict['serverseq']})
        template_param_list = []
        for param in rlt_dict['parameters']:
            if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
                template_param_list.append(param)

        template_param_list_for_heat = copy.deepcopy(template_param_list)

        stack_uuid = rlt_dict["uuid"]   # need to check nsr uuid in rlt
        nsr_name = rlt_dict["name"] # need to check nsr name in rlt

        log.debug("[VNF Upgrade] _____5.1 Update Heat Stack_____")
        update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU_creatingvr)
        if e2e_log:
            e2e_log.job('Update Heat Stack', CONST_TRESULT_NONE, tmsg_body=None)

        result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
        if result < 0:
            log.error("[VNF Upgrade] Error, failed to connect to VIM")
            raise Exception("Failed to establish a VIM connection: %d %s" % (result, vims))
        elif result > 1:
            log.error("[VNF Upgrade] Error, Several VIMs available, must be identify the target VIM")
            raise Exception("Failed to establish a VIM connection:Several VIMs available, must be identify")

        myvim = vims.values()[0]

        # open stack의 parameter를 그대로 반영한다. 이미지 정보만 변경되도록...
        result, stack_info = myvim.get_heat_stack_id_v4(stack_uuid)
        if result < 0:
            raise Exception("Failed to get heat stack info")

        for param_key, param_value in stack_info["parameters"].items():
            if param_key.find("RPARM_imageId") >= 0:
                continue

            for template_param in template_param_list_for_heat:
                if param_key == template_param["name"]:
                    template_param["value"] = param_value
                    break

        log.debug("_____##_____ template_param_list_for_heat : %s" % template_param_list_for_heat)

        result, msg = myvim.update_heat_stack_v4(nsr_name, stack_uuid, rlt_dict['resourcetemplatetype'], rlt_dict['resourcetemplate'], template_param_list_for_heat)
        if result < 0:
            log.error("[VNF Upgrade] Failed to update Heat Stack[%s] : %d %s" % (nsr_name, result, msg))
            if e2e_log:
                e2e_log.job('Update Heat Stack', CONST_TRESULT_FAIL, tmsg_body="Failed to update Heat Stack[%s] : %d %s" % (nsr_name, result, msg))
            raise Exception("Failed to update Heat Stack[%s] : %d %s" % (nsr_name, result, msg))
        if e2e_log:
            e2e_log.job('Update Heat Stack', CONST_TRESULT_SUCC, tmsg_body=None)

        if e2e_log:
            e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_NONE, tmsg_body=None)

        log.debug("[VNF Upgrade] _____5.2 Get the Heat Stack Info for updated one_____")
        update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.UDT_checkingvr)

        result, stack_info = myvim.get_heat_stack_id_v4(stack_uuid)
        if result < 0:
            log.error("[VNF Upgrade] Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))
            if e2e_log:
                e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to get Heat Stack Info[%s] : %d %s" % (nsr_name, result, stack_info))

        log.debug("[VNF Upgrade] _____5.3 Get the resource list of updated Heat Stack_____")
        result, stack_resources = myvim.get_heat_resource_list_v4(stack_uuid)
        if result < 0:
            log.error("[VNF Upgrade] Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))
            if e2e_log:
                e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to get Heat Stack Resource List[%s] : %d %s" % (nsr_name, result, stack_resources))

        if e2e_log:
            e2e_log.job('Get Heat Stack and Resource Info', CONST_TRESULT_SUCC, tmsg_body=None)

        _set_stack_data(rlt_dict, stack_resources, stack_info, nsr_name, template_param_list)

        # 6. VNF init-config
        log.debug("[VNF Upgrade] _____6. VNF init-config_____")
        update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU_configvnf)

        # vnfm 버젼 check
        # get vnfm connector
        # result, vnfms = common_manager.get_ktvnfm(mydb, server_dict['serverseq'])
        # if result < 0:
        #     raise Exception("No KT VNFM Found")
        # elif result > 1:
        #     raise Exception("Several vnfms available, must be identify")
        # myvnfm = vnfms.values()[0]

        # 2. VNFM 버전 조회 > 지원 가능 버전일 경우만 배포 프로세스 실행 : 버전의 최상위 값이 1 이상인 경우 지원 가능
        # result, version_res = myvnfm.get_vnfm_version()
        # if version_res["version"] < "1.1.0":

        # vnf init-config
        if e2e_log:
            e2e_log.job('VNF Configuration', CONST_TRESULT_NONE,
                        tmsg_body="Configuration Parameters:%s" % (json.dumps(rlt_dict['parameters'], indent=4)))

        # Update된 VNF만 init-conf 처리해야한다.
        rlt_dict_temp = copy.deepcopy(rlt_dict)
        for idx in range(len(rlt_dict_temp['vnfs'])-1, -1, -1):
            vnf = rlt_dict_temp['vnfs'][idx]
            if vnf["name"] != vnf_data["name"]:
                del rlt_dict_temp['vnfs'][idx]

        vnf_confg_result, vnf_config_data = _new_nsr_vnf_conf(mydb, rlt_dict_temp, server_dict["serverseq"], e2e_log)
        if vnf_confg_result < 0:
            log.error("[VNF Upgrade]   : Error, %d %s" % (vnf_confg_result, vnf_config_data))
            if e2e_log:
                e2e_log.job('VNF Configuration', CONST_TRESULT_FAIL,
                            tmsg_body="Result:Fail\nConfiguration Parameters:%s" % (json.dumps(rlt_dict['parameters'], indent=4)))
            raise Exception("Failed to init-config VNFs: %d %s" % (vnf_confg_result, vnf_config_data))

        if e2e_log:
            e2e_log.job('VNF Configuration', CONST_TRESULT_SUCC,
                        tmsg_body="Result:Success\nConfiguration Parameters:%s" % (json.dumps(rlt_dict['parameters'], indent=4)))

        # 8. DB Update
        update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU_processingdb)

        log.debug("[VNF Upgrade] _____7.1 Delete NSR Params_____")
        orch_dbm.delete_nsr_param(mydb, {"nsseq" : rlt_dict['nsseq']})
        # calculate internal parameter values
        log.debug("[VNF Upgrade] _____7.2 Insert NSR Params_____")

        vnf_name_list = []
        for vnf in rlt_dict['vnfs']:
            vnf_name_list.append(vnf['name'])

        iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_name_list, rlt_dict['parameters'])
        if iparm_result < 0:
            log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
            raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))

        orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])

        log.debug("[VNF Upgrade] _____7.3 Update RLT_____")
        ur_result, ur_data = _update_rlt_data(mydb, rlt_dict, nsseq=rlt_dict['nsseq'])
        if ur_result < 0:
            log.error("Failed to update rlt data %d %s" % (ur_result, ur_data))
            raise Exception("Failed to update rlt data %d %s" % (ur_result, ur_data))

        if e2e_log:
            e2e_log.job('Updated DB for NSR, VDU, CP, Web URL & RLT', CONST_TRESULT_SUCC, tmsg_body=None)

        # 8. VNF Restore
        log.debug("[VNF Upgrade] _____8. Restore VNFs_____")
        update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU_restoringvnf)

        #TODO: compose action_dict, request
        request = {'type': "orch_all"}
        result, request['needWanSwitch'] = _need_wan_switch(mydb, {"serverseq": server_dict["serverseq"]})

        restore_result, restore_data = _restore_nsr_vnf_thread(mydb, server_dict["serverseq"], rlt_dict, action_dict, request, None, e2e_log)

        if restore_result < 0:
            raise Exception("_restore_nsr_thread() error. failed to restore VNFs: %d %s" %(restore_result, restore_data))
        else:
            UPDATE_ = {'nfseq':vnf_data['nfseq']}
            UPDATE_["vnf_image_version"] = img_data["vnf_image_version"]
            UPDATE_["vnf_sw_version"] = img_data["vnf_sw_version"]
            UPDATE_["vdudimageseq"] = img_data["vdudimageseq"]

            r, instance_vnf_id = orch_dbm.update_nsr_vnf(mydb, UPDATE_)
            if r < 0:
                raise Exception("Failed to update vnf: %d %s" %(r, instance_vnf_id))

            if e2e_log:
                e2e_log.job("Restore VNFs", CONST_TRESULT_SUCC, tmsg_body=None)

        # 9 Resume monitoring
        log.debug("[VNF Upgrade] _____9. Resuming NSR monitor_____")
        update_nsr_status(mydb, ActionType.IMGUP, nsr_data=rlt_dict, nsr_status=NSRStatus.VIU_resumingmonitor)
        result, data = resume_nsr_monitor(mydb, server_dict['serverseq'], rlt_dict, e2e_log)
        if result < 0:
            log.error("Failed to resume NSR monitoring: %d %s" % (result, data))

        log.debug("[VNF Upgrade] _____10. Record History_____")
        # 이력저장
        history_dict = {"serverseq":server_dict["serverseq"], "server_name":server_dict["name"]}
        history_dict["nsseq"] = rlt_dict["nsseq"]
        history_dict["nsr_name"] = rlt_dict["name"]
        history_dict["nfseq"] = vnf_data["nfseq"]
        history_dict["nfr_name"] = vnf_data["name"]
        history_dict["vdudimageseq_old"] = vnf_data["vdudimageseq"]
        history_dict["vnf_image_version_old"] = vnf_data["vnf_image_version"]
        history_dict["vnf_sw_version_old"] = vnf_data["vnf_sw_version"]
        history_dict["vdudimageseq_new"] = img_data["vdudimageseq"]
        history_dict["vnf_image_version_new"] = img_data["vnf_image_version"]
        history_dict["vnf_sw_version_new"] = img_data["vnf_sw_version"]
        history_dict["memo"] = req_dict["memo"]
        history_dict["update_dt"] = datetime.datetime.now().strftime("%Y%m%d")

        result_his, content_his = orch_dbm.insert_vnf_image_history(mydb, history_dict)
        if result_his < 0:
            log.error("Failed to insert history of updating vnf image version")
        else:
            if e2e_log:
                e2e_log.job('Saved history of updating vnf image version', CONST_TRESULT_SUCC, tmsg_body=None)

        # Step.11 update NSR status
        log.debug("[VNF Upgrade] _____11. Updating NSR status_____")
        update_nsr_status(mydb, ActionType.IMGUP, action_dict=action_dict, action_status=ACTStatus.SUCC, nsr_data=rlt_dict, nsr_status=NSRStatus.RUN, server_dict=server_dict, server_status=SRVStatus.INS)

    except Exception, e:
        log.exception("upgrade_vnf_with_image_thread >> Exception: [%s] %s" % (str(e), sys.exc_info()))
        update_nsr_status(mydb, ActionType.IMGUP, action_dict=action_dict, action_status=ACTStatus.FAIL, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR, server_dict=server_dict, server_status=SRVStatus.ERR)
        if e2e_log:
            e2e_log.job('VNF Upgrade Orch 제어 Thread 실패', CONST_TRESULT_FAIL,
                        tmsg_body="VNF Upgrade Orch 제어 Thread 실패\nCause: %s" % str(e))
            e2e_log.finish(CONST_TRESULT_FAIL)
        return -HTTP_Internal_Server_Error, "VNF Upgrade가 실패하였습니다. 원인: %s" % str(e)

    log.debug("[VNF Upgrade] VNF Upgrade Orch 제어 Thread 성공")
    if e2e_log:
        e2e_log.job('VNF Upgrade Orch 제어 Thread 성공', CONST_TRESULT_SUCC, tmsg_body="VNF Upgrade Orch 제어 Thread 성공")
        e2e_log.finish(CONST_TRESULT_SUCC)

    return 200, "OK"


def upgrade_vnf_with_image_menual(mydb, req_dict, vnf_data, rlt_dict, server_dict, e2e_log):
    """
        해당 VNF의 버젼이 변경되었는지 체크하고, 변경되었으면 데이타 현행화
    :param mydb:
    :param req_dict:
    :param vnf_data:
    :param rlt_dict:
    :param server_dict:
    :param e2e_log:
    :return:
    """
    try:
        result, img_data = _find_vnf_image_by_vnfm(mydb, rlt_dict["serverseq"], vnf_data, e2e_log=e2e_log)
        if result < 0:
            log.error("Failed to find vnf image by vnfm : %s" % img_data)
            raise Exception("VNF Image의 Version정보를 얻는데 실패했습니다.")

        for param in rlt_dict["parameters"]:
            if param['name'] == "RPARM_imageId_" + vnf_data['name']:
                param['value'] = img_data["name"]
                log.debug("[VNF Upgrade] Image Param Info is changed to %s" %str(param))
                break

        if e2e_log:
            e2e_log.job('Composed RLT Data with new vnf image id', CONST_TRESULT_SUCC,
                        tmsg_body="RLT Data: %s" % (json.dumps(rlt_dict, indent=4)))

        # DB Update
        orch_dbm.delete_nsr_param(mydb, {"nsseq" : rlt_dict['nsseq']})
        # calculate internal parameter values
        vnf_list = []
        for vnf in rlt_dict['vnfs']:
            vnf_list.append(vnf['name'])

        iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_list, rlt_dict['parameters'])
        if iparm_result < 0:
            log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
            raise Exception("Failed to compose internal parameter values")

        orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])

        UPDATE_ = {'nfseq':vnf_data['nfseq']}
        UPDATE_["vnf_image_version"] = img_data["vnf_image_version"]
        UPDATE_["vnf_sw_version"] = img_data["vnf_sw_version"]
        UPDATE_["vdudimageseq"] = img_data["vdudimageseq"]

        if 'nfcatseq' in img_data:
            UPDATE_["nfcatseq"] = img_data.get("nfcatseq")

        r, instance_vnf_id = orch_dbm.update_nsr_vnf(mydb, UPDATE_, chg_nfcatseq=True)
        if r < 0:
            log.error("failed to update vnf: %d %s" %(r, instance_vnf_id))
            raise Exception("DB에 VNF Image정보를 업데이트 중 에러가 발생했습니다.")

        if e2e_log:
            e2e_log.job('Updated DB for NFR, NSR_PARAM', CONST_TRESULT_SUCC, tmsg_body=None)

        # 이력저장
        history_dict = {"serverseq":server_dict["serverseq"], "server_name":server_dict["name"]}
        history_dict["nsseq"] = rlt_dict["nsseq"]
        history_dict["nsr_name"] = rlt_dict["name"]
        history_dict["nfseq"] = vnf_data["nfseq"]
        history_dict["nfr_name"] = vnf_data["name"]
        history_dict["vdudimageseq_old"] = vnf_data["vdudimageseq"]
        history_dict["vnf_image_version_old"] = vnf_data["vnf_image_version"]
        history_dict["vnf_sw_version_old"] = vnf_data["vnf_sw_version"]
        history_dict["vdudimageseq_new"] = img_data["vdudimageseq"]
        history_dict["vnf_image_version_new"] = img_data["vnf_image_version"]
        history_dict["vnf_sw_version_new"] = img_data["vnf_sw_version"]
        history_dict["memo"] = req_dict["memo"]
        history_dict["update_dt"] = req_dict["update_dt"]

        result_his, content_his = orch_dbm.insert_vnf_image_history(mydb, history_dict)

        if result_his < 0:
            log.error("Failed to insert history of updating vnf image version")
        else:
            if e2e_log:
                e2e_log.job('Saved history of updating vnf image version', CONST_TRESULT_SUCC, tmsg_body=None)

    except Exception, e:
        log.exception("upgrade_vnf_with_image_menual >> Exception: [%s] %s" % (str(e), sys.exc_info()))
        if e2e_log:
            e2e_log.job('VNF Upgrade Orch 제어 실패', CONST_TRESULT_FAIL,
                        tmsg_body="VNF Upgrade Orch 제어 실패\nCause: %s" % str(e))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, str(e)

    log.debug("[VNF Upgrade] VNF Upgrade Orch 제어 성공")
    if e2e_log:
        e2e_log.job('VNF Upgrade Orch 제어 성공', CONST_TRESULT_SUCC, tmsg_body="VNF Upgrade Orch 제어 성공")
        e2e_log.finish(CONST_TRESULT_SUCC)

    return 200, "VNF Update가 성공했습니다."


def get_vnf_image_version_by_vnfm(mydb, vnf_id, serverseq):
    """
        "VNF 정보갱신" 요청시 실제 One-Box의 VNF 버전 정보를 조회한다.
    :param mydb:
    :param vnf_id:
    :param serverseq:
    :return:
    """

    try:
        # 현재 VNF 이미지 버젼 조회
        result, vnfms = common_manager.get_ktvnfm(mydb, serverseq)
        if result < 0:
            log.error("Failed to establish a vnfm connection")
            raise Exception("No KT VNFM Found")
        elif result > 1:
            log.error("Error, Several vnfms available, must be identify")
            raise Exception("Several vnfms available, must be identify")

        myvnfm = vnfms.values()[0]

        local_ip = None

        vnf_result, vnf_data = orch_dbm.get_vnf_id(mydb, vnf_id)
        if vnf_result < 0:
            raise Exception(vnf_data)

        for vdu in vnf_data["vdus"]:
            vduseq = vdu["vduseq"]
            break
        else:
            raise Exception("Failed to get vdu_id value.")

        cp_result, cp_list = orch_dbm.get_vnf_cp_only(mydb, vduseq)
        if cp_result < 0:
            raise Exception(cp_list)
        else:
            for cp in cp_list:
                if cp['name'].find("local") >= 0 or cp['name'].find("blue") >= 0:
                    local_ip = cp['ip']
                    log.debug("_____ Found local IP: %s, %s" % (cp['name'], cp['ip']))
                    break

        vnfd_result, vnfd_content = orch_dbm.get_vnfd_general_info(mydb, vnf_data["nfcatseq"])
        if vnfd_result < 0:
            raise Exception(vnfd_content)

        vnfd_name, vnfd_version = vnfd_content["name"], vnfd_content["version"]

        ver_req_dict = {"name":vnfd_name, "version":vnfd_version, "local_ip": local_ip}

        result_ver, data_ver = myvnfm.get_vnf_version(ver_req_dict)
        log.debug('result_ver : %d, data_ver : %s' %(result_ver, str(data_ver)))

        if result_ver < 0:
            raise Exception(data_ver)
        else:
            # data_ver을 가지고 등록된 vnf 이미지를 찾는다.
            result, vdud_images = get_vdud_image_list_by_vnfd_id(mydb, vnf_data["nfcatseq"])
            if result < 0:
                raise Exception("Failed to get registed image-list : vnfd_id = %s" % vnf_data["nfcatseq"])

            for vdud_img in vdud_images:
                if vdud_img["location"].find(data_ver["vnf_image_version"]) >= 0:
                    img_data = vdud_img
                    log.debug("__________ get_vnf_image_version_by_vnfm > img_data = %s" % img_data)

                    # 찾은 이미지의 vnf_sw_version과 tb_vdud_image 의 값이 다를 경우 현행화 -> 업데이트
                    if img_data["vnf_sw_version"] != data_ver["vnf_sw_version"]:
                        img_data["vnf_sw_version"] = data_ver["vnf_sw_version"]
                        orch_dbm.update_vdud_image(mydb, img_data)
                        # 해당 이미지를 사용하는 vnf의 정보 업데이트
                        orch_dbm.update_vnf_sw_version(mydb, {"vdudimageseq":img_data["vdudimageseq"], "vnf_sw_version":img_data["vnf_sw_version"]})

                    elif vnf_data["vnf_sw_version"] != data_ver["vnf_sw_version"]:  # 기존에 빠진 부분처리를 위해...새로 들어온 데이타는 필요없는 로직.
                        # 해당 이미지를 사용하는 vnf의 정보 업데이트
                        orch_dbm.update_vnf_sw_version(mydb, {"vdudimageseq":img_data["vdudimageseq"], "vnf_sw_version":img_data["vnf_sw_version"]})

                    data_ver["vdudimageseq"] = img_data["vdudimageseq"]
                    if img_data.get("vnf_image_version", None) and img_data["vnf_image_version"].find(data_ver["vnf_image_version"]) >= 0:
                        data_ver["vnf_image_version"] = img_data["vnf_image_version"]
                    break
            # else:
            #     raise Exception("Failed to get find target image from registed image table")

    except Exception, e:
        return -500, str(e)
    return 200, data_ver


def _find_vnf_image_by_vnfm(mydb, serverseq, vnf_data, myvnfm=None, e2e_log=None):
    """
        upgrade_vnf_with_image_menual / sync_vnf_image_version 에서
    :param mydb:
    :param serverseq:
    :param vnf_data:
    :param myvnfm:
    :param e2e_log:
    :return:
    """

    try:

        # log.debug('[%s] _find_vnf_image_by_vnfm :: vnf_data = %s' %(str(serverseq), str(vnf_data)))

        # 현재 VNF 이미지 버젼 조회
        if myvnfm is None:
            result, vnfms = common_manager.get_ktvnfm(mydb, serverseq)
            if result < 0:
                log.error("Failed to establish a vnfm connection")
                raise Exception("No KT VNFM Found")
            elif result > 1:
                log.error("Error, Several vnfms available, must be identify")
                raise Exception("Several vnfms available, must be identify")

            myvnfm = vnfms.values()[0]

        find_result, find_data = _find_images(mydb, vnf_data, myvnfm, e2e_log)
        if find_result < 0:
            raise Exception(find_data)

        vdud_images = find_data.get('vdud_images')
        data_ver = find_data.get('data_ver')

        img_data = None
        for vdud_img in vdud_images:
            if vdud_img["location"].find(data_ver["vnf_image_version"]) >= 0:
                img_data = vdud_img
                img_data['nfcatseq'] = vnf_data['nfcatseq']
                log.debug("__________ _find_vnf_image_by_vnfm > img_data = %s" % img_data)

                # 찾은 이미지의 vnf_sw_version과 tb_vdud_image의 vnf_sw_version 값이 다를 경우 현행화 -> 업데이트
                if img_data["vnf_sw_version"] != data_ver["vnf_sw_version"]:
                    img_data["vnf_sw_version"] = data_ver["vnf_sw_version"]
                    orch_dbm.update_vdud_image(mydb, img_data)
                    # 해당 이미지를 사용하는 vnf의 정보 업데이트
                    orch_dbm.update_vnf_sw_version(mydb, {"vdudimageseq":img_data["vdudimageseq"], "vnf_sw_version":img_data["vnf_sw_version"]})
                break
        else:
            # 실제 원박스가 가지고 있는 버전으로 다시 조회
            get_result, get_data = orch_dbm.get_vdud_image_to_nfcatseq(mydb, data_ver.get('vnf_image_version'))
            if get_result < 0:
                raise Exception("Failed to get Onebox real version")

            vnf_data['nfcatseq'] = get_data.get('nfcatseq')

            find_result, find_data = _find_images(mydb, vnf_data, myvnfm, e2e_log)
            if find_result < 0:
                raise Exception(find_data)

            vdud_images = find_data.get('vdud_images')
            data_ver = find_data.get('data_ver')

            img_data = None
            for vdud_img in vdud_images:
                if vdud_img["location"].find(data_ver["vnf_image_version"]) >= 0:
                    img_data = vdud_img
                    img_data['nfcatseq'] = vnf_data['nfcatseq']
                    log.debug("__________ _find_vnf_image_by_vnfm > img_data = %s" % img_data)

                    # 찾은 이미지의 vnf_sw_version과 tb_vdud_image의 vnf_sw_version 값이 다를 경우 현행화 -> 업데이트
                    if img_data["vnf_sw_version"] != data_ver["vnf_sw_version"]:
                        img_data["vnf_sw_version"] = data_ver["vnf_sw_version"]

                        log.debug('update_vdud_image...........')
                        orch_dbm.update_vdud_image(mydb, img_data)

                        # 해당 이미지를 사용하는 vnf의 정보 업데이트
                        log.debug('update_vnf_sw_version...........')
                        orch_dbm.update_vnf_sw_version(mydb, {"vdudimageseq": img_data["vdudimageseq"],
                                                              "vnf_sw_version": img_data["vnf_sw_version"]})
                    break
            else:
                raise Exception("Failed to get find target image from registed image table")
    except Exception, e:
        log.error("Failed to get vnf image : %s" % str(e))
        return -500, str(e)

    return 200, img_data


def _find_images(mydb, vnf_data, myvnfm, e2e_log):
    local_ip = None

    vduseq = None
    for vdu in vnf_data["vdus"]:
        vduseq = vdu["vduseq"]
        break
    else:
        return -500, "NOK"

    cp_result, cp_list = orch_dbm.get_vnf_cp_only(mydb, vduseq)
    if cp_result < 0:
        return -500, "NOK"
    else:
        for cp in cp_list:
            if cp['name'].find("local") >= 0 or cp['name'].find("blue") >= 0:
                local_ip = cp['ip']
                log.debug("_____ Found local IP: %s, %s" % (cp['name'], cp['ip']))
                break

    vnfd_result, vnfd_content = orch_dbm.get_vnfd_general_info(mydb, vnf_data["nfcatseq"])
    if vnfd_result < 0:
        return -500, vnfd_content

    vnfd_name, vnfd_version = vnfd_content["name"], vnfd_content["version"]

    ver_req_dict = {"name": vnfd_name, "version": vnfd_version, "local_ip": local_ip}

    result_ver, data_ver = myvnfm.get_vnf_version(ver_req_dict)
    log.debug("__________ VNF Image version : %s" % data_ver)
    if result_ver < 0:
        raise Exception("Failed to get vnf image version from vnfm %s %s" % (result_ver, data_ver))
    elif data_ver["status"] == "NOTSUPPORTED_VNFM":
        if e2e_log:
            e2e_log.job("VNFM이 VNF image version 조회기능을 지원하지 않는 버젼", CONST_TRESULT_FAIL, tmsg_body="")
        return -500, "NOTSUPPORTED_VNFM"
    elif data_ver["status"] == "NOTSUPPORTED_VNF":
        if e2e_log:
            e2e_log.job("VNF가 VNF image version 조회기능을 지원하지 않는 버젼", CONST_TRESULT_FAIL, tmsg_body="")
        return -500, "NOTSUPPORTED_VNF"

    # 예외처리...이런 경우는 없어야...
    if data_ver.get("vnf_image_version") is None:
        return -500, "Not found vnf_image_version for API"

    # data_ver을 가지고 등록된 vnf 이미지를 찾는다.
    result, vdud_images = get_vdud_image_list_by_vnfd_id(mydb, vnf_data["nfcatseq"])
    if result < 0:
        # raise Exception("Failed to get registed image-list : vnfd_id = %s" % vnf_data["nfcatseq"])
        return -500, "Failed to get registed image-list : vnfd_id = %s" % vnf_data["nfcatseq"]

    return_data = {}
    return_data['vdud_images'] = vdud_images
    return_data['data_ver'] = data_ver

    return 200, return_data


def sync_vnf_image_version(mydb, rlt_dict, e2e_log=None):
    """
        One-Box Restore / NS Restore 할때 백업파일의 VNF Image 정보가 변경되었을 경우 현행화 처리.
    :param mydb:
    :param rlt_dict:
    :param e2e_log:
    :return:
    """

    try:
        log.debug("__________ SYNC_VNF_IMAGE_VERSION BEGIN")
        # vnf image version 변경 체크 : vnfm에서 버젼 조회 및 변경 체크 => rlt > parameters > RPARM_imageId 변경
        result, vnfms = common_manager.get_ktvnfm(mydb, rlt_dict["serverseq"])
        if result < 0:
            raise Exception("No KT VNFM Found")
        elif result > 1:
            raise Exception("Several vnfms available, must be identify")

        myvnfm = vnfms.values()[0]

        for vnf in rlt_dict["vnfs"]:

            vnf_result, vnf_data = orch_dbm.get_vnf_id(mydb, vnf["nfseq"])

            result, img_data = _find_vnf_image_by_vnfm(mydb, rlt_dict["serverseq"], vnf, myvnfm=myvnfm, e2e_log=e2e_log)
            log.debug("__________ SYNC_VNF_IMAGE_VERSION > _find_vnf_image_by_vnfm > img_data : %s" % img_data)
            if result < 0:
                if img_data == "NOTSUPPORTED_VNFM" or img_data == "NOTSUPPORTED_VNF":
                    # if need to check somethings, coding it here.
                    pass
                img_data = None
                # vnfm 에서 vnf 버젼 정보를 가져오지 못하는 경우에는 tb_nfr 에서 vdudimageseq를 이용한다.
                if vnf_result > 0 and vnf_data.get("vdudimageseq", None):
                    result, img_data_r = orch_dbm.get_vnfd_vdu_image(mydb, {"vdudimageseq": vnf_data["vdudimageseq"]})
                    if result < 0:
                        img_data = None
                    else:
                        img_data = img_data_r[0]
                        log.debug("__________ SYNC_VNF_IMAGE_VERSION > tb_nfr 기준 > img_data : %s" % img_data)
            else:
                # 변경된 경우 tb_nfr 변경처리
                if img_data["vdudimageseq"] != vnf_data["vdudimageseq"]:
                    UPDATE_ = {"nfseq":vnf["nfseq"]}
                    UPDATE_["vnf_image_version"] = img_data["vnf_image_version"]
                    UPDATE_["vnf_sw_version"] = img_data["vnf_sw_version"]
                    UPDATE_["vdudimageseq"] = img_data["vdudimageseq"]

                    if 'nfcatseq' in img_data:
                        UPDATE_["nfcatseq"] = img_data["nfcatseq"]

                    r, instance_vnf_id = orch_dbm.update_nsr_vnf(mydb, UPDATE_, chg_nfcatseq=True)
                    if r < 0:
                        log.error("failed to update vnf: %d %s" %(r, instance_vnf_id))
                        return r, instance_vnf_id

            if img_data:
                for param in rlt_dict["parameters"]:
                    if param['name'] == "RPARM_imageId_" + vnf['name']:
                        param['value'] = img_data["name"]
                        log.debug("__________ SYNC_VNF_IMAGE_VERSION > %s = %s" % (param['name'], img_data["name"]))
                        break

                # 배포체크 전에 배포테이블 현행화
                common_manager.sync_image_for_server(mydb, rlt_dict["serverseq"])
                # vnf image가 배포되었는지 체크
                result, vnfimage_r = orch_dbm.get_server_vnfimage(mydb, {"serverseq":rlt_dict["serverseq"], "location":img_data["location"]})
                if result < 0:
                    raise Exception("Failed to get tb_server_vnfimage record : %d, %s" % (result, vnfimage_r))
                elif result > 0:
                    log.debug("__________ SYNC_VNF_IMAGE_VERSION > 배포된 이미지 : %s" % img_data["location"])
                    pass
                else:
                    # 배포처리
                    log.debug("__________ SYNC_VNF_IMAGE_VERSION > 배포되지 않은 이미지 : %s ==> 배포시작" % img_data["location"])
                    req_data = {"release":{"target_onebox":[rlt_dict["serverseq"]]}}
                    result, data = deploy_vnf_image(mydb, vnf["nfcatseq"], img_data["vdudimageseq"], req_data, use_thread=False, e2e_log=e2e_log)
                    if result < 0:
                        raise Exception("Failed to deploy vnf image : Error %d %s" %(result, data))
                    log.debug("__________ SYNC_VNF_IMAGE_VERSION > 배포완료 : %s" % img_data["location"])
    except Exception, e:
        return -500, str(e)

    return 200, "OK"


def _set_wan_parameter_of_backup(vnf_name_list, parameters, server_info):
    """
        NS백업파일의 내용(rlt_backup) 중 WAN 관련 항목이 변경되었을 수 있어서 현행화 시켜준다.
    :param vnf_name_list: VNF의 name list
    :param parameters: rlt_dict["parameters"]
    :param server_info:
    :return:
    """

    if "wan_list" in server_info:
        wan_list = server_info["wan_list"]
        idx = 0
        for wan in wan_list:

            if idx == 0:
                r_kind = "_"
            else:
                r_kind = "R" + str(idx)

            for vnf_name in vnf_name_list:
                if vnf_name.find("UTM") < 0 and vnf_name.find("KT-VNF") < 0:
                    continue

                for param in parameters:

                    if param["name"].find("redFixedIp" + r_kind) >= 0 and param["name"].find(vnf_name) >= 0:
                        if "public_ip" in wan and wan.get("public_ip") is not None:
                            param["value"] = wan["public_ip"]

                    elif param["name"].find("redSubnet" + r_kind) >= 0 and param["name"].find(vnf_name) >= 0:
                        if "public_ip" in wan and wan.get("public_ip") is not None:
                            cidr_prefix = wan["public_cidr_prefix"]
                            temp_ip_info = netaddr.IPNetwork(wan["public_ip"] + "/" + str(cidr_prefix))
                            param['value'] = str(temp_ip_info.network) + "/" + str(cidr_prefix)

                    elif param["name"].find("redFixedMac" + r_kind) >= 0 and param["name"].find(vnf_name) >= 0:
                        param["value"] = wan["mac"]

                    elif param["name"].find("redType" + r_kind) >= 0 and param["name"].find(vnf_name) >= 0:
                        if wan['public_ip_dhcp']:
                            param["value"] = "DHCP"
                        else:
                            param["value"] = "STATIC"

                    elif param["name"].find("defaultGw" + r_kind) >= 0 and param["name"].find(vnf_name) >= 0:
                        if "public_gw_ip" in wan and wan.get("public_gw_ip") is not None:
                            param["value"] = wan["public_gw_ip"]

                    elif param["name"].find("redCIDR" + r_kind) >= 0 and param["name"].find(vnf_name) >= 0:
                        param["value"] = wan["public_cidr_prefix"]
            idx += 1

    elif "wan" in server_info:
        wan = server_info["wan"]
        for param in parameters:
            if param["name"].find("redFixedMac_") >= 0:
                param["value"] = wan["mac"]
                break

    if "extra_wan_list" in server_info:
        wan_list = server_info["extra_wan_list"]
        for wan in wan_list:
            for vnf_name in vnf_name_list:
                if vnf_name.find("ACROMATE-CALLBOX") < 0:
                    continue

                for param in parameters:
                    if param["name"].find("redFixedIp") >= 0 and param["name"].find(vnf_name) >= 0:
                        if "public_ip" in wan and wan.get("public_ip") is not None:
                            param["value"] = wan["public_ip"]

                    elif param["name"].find("redSubnet") >= 0 and param["name"].find(vnf_name) >= 0:
                        if "public_ip" in wan and wan.get("public_ip") is not None:
                            cidr_prefix = wan["public_cidr_prefix"]
                            temp_ip_info = netaddr.IPNetwork(wan["public_ip"] + "/" + str(cidr_prefix))
                            param['value'] = str(temp_ip_info.network) + "/" + str(cidr_prefix)

                    elif param["name"].find("redFixedMac") >= 0 and param["name"].find(vnf_name) >= 0:
                        param["value"] = wan["mac"]

                    elif param["name"].find("redType") >= 0 and param["name"].find(vnf_name) >= 0:
                        if wan['public_ip_dhcp']:
                            param["value"] = "DHCP"
                        else:
                            param["value"] = "STATIC"

                    elif param["name"].find("defaultGw") >= 0 and param["name"].find(vnf_name) >= 0:
                        if "public_gw_ip" in wan and wan.get("public_gw_ip") is not None:
                            param["value"] = wan["public_gw_ip"]

                    elif param["name"].find("redCIDR") >= 0 and param["name"].find(vnf_name) >= 0:
                        param["value"] = wan["public_cidr_prefix"]

    return 200, "OK"

