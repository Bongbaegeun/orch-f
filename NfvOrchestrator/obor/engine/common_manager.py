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

"""
공통함수 모듈.
1. 공통적으로 사용되는 함수를 여기에 작성해서 코드중복을 없앤다.
2. 소스상의 순환 문제를 해결하는 역할.
    - orch_core 및 여러 manager끼리 함수 호출 과정에서 생기는 순환문제를 없애기 위해 이용한다.
    - !!! 이 모듈에서는 orch_db_manager를 제외한 다른 manager를 import하지 않는다 !!!
"""

__author__="Jechan Han"
__date__ ="$23-Mar-2017 10:05:01$"

import json
import sys
import threading

import netaddr
import yaml

import db.orch_db_manager as orch_dbm
import utils.log_manager as log_manager
from db.orch_db import HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found
from utils import auxiliary_functions as af

log = log_manager.LogManager.get_instance()

from connectors import odmconnector
from connectors import vnfmconnector
from connectors import obconnector
from connectors import monitorconnector

from engine.server_status import SRVStatus
from engine.action_status import ACTStatus
from image_status import ImageStatus
from engine.action_type import ActionType

global_config = None

def _find_r_kind(param_name):
    """
        내부함수.
        해당 Parameter가 회선이중화에서 사용하는 R0~R4 중 어떤 종류인지 확인해준다.

    :param param_name: param_name에 'R1' 문구가 있으면 R1으로 판단. R0는 R.문가가 없다.
    :return:
    """
    r_kind = "R0"
    if param_name.find("R1") >= 0:
        r_kind = "R1"
    elif param_name.find("R2") >= 0:
        r_kind = "R2"
    elif param_name.find("R3") >= 0:
        r_kind = "R3"
    return r_kind


def update_nsr_by_obagent(mydb, nsr_id, update_info, use_thread=True):
    """
        Onebox Agent가 Call하는 API에서 Onebox정보가 변경된 부분이 있을 경우 호출된다.

    :param mydb:
    :param nsr_id: nsseq of tb_nsr
    :param update_info:
    :param use_thread:
    :return:
    """
    # log.debug("________________ update_nsr_by_obagent START")
    nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, nsr_id)
    if nsr_result <= 0:
        log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
        return -HTTP_Internal_Server_Error, nsr_data

    if nsr_data['status'].find("N__") >= 0 or nsr_data['status'].find("E__") >= 0:
        pass
    else:
        log.warning("__________ Passed to invoke _update_nsr because the status of nsr %d is not normal : %s" % (nsr_id, nsr_data['status']))
        return 200, "PASS"

    try:
        if use_thread:
            try:
                th = threading.Thread(target=_update_nsr_by_obagent_thread, args=(mydb, nsr_data, update_info))
                th.start()
            except Exception, e:
                error_msg = "failed to start a thread for updating the NS Instance %s" % str(nsr_id)
                log.exception(error_msg)
        else:
            return _update_nsr_by_obagent_thread(mydb, nsr_data, update_info)
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -HTTP_Internal_Server_Error, "Failed to update NSR: %s" % str(e)

    return 200, "OK"


def _update_nsr_by_obagent_thread(mydb, nsr_data, update_info):
    """
        update_nsr_by_obagent 에서 호출하는 Thread 함수.
    :param mydb:
    :param nsr_data:
    :param update_info:
    :return:
    """
    log.debug("__________ _update_nsr_by_obagent_thread START, update info : %s" % str(update_info))

    extra_wan_mapping = {}

    try:
        vnf_name_list = []

        for vnf in nsr_data['vnfs']:
            if vnf['name'].find("UTM") >= 0 or vnf['name'].find("KT-VNF") >= 0 or vnf['name'].find("ACROMATE-CALLBOX") >= 0:
                vnf_name_list.append(vnf['name'])

        if vnf_name_list:

            result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_data["nsseq"])
            if result < 0:
                log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
                raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

            rlt_dict = rlt_data["rlt"]

            if update_info.get("is_wan_list", False):

                rt_dict = None

                for vnf_name in vnf_name_list:

                    chg_wan_info = None
                    chg_dlm = "WAN"
                    physnet_name = None

                    if vnf_name.find("UTM") >= 0 or vnf_name.find("KT-VNF") >= 0:
                        if update_info.get("chg_port_info", None) and update_info["chg_port_info"].get("wan", None):
                            # 회선이중화 : 변경된 wan 정보가 있으면 rlt > parameters 에서 해당 값 수정처리.
                            chg_wan_info = update_info["chg_port_info"]["wan"]
                            log.debug("__________ 변경된 wan 정보가 있는 경우 chg_wan_info = %s" % chg_wan_info)
                    elif vnf_name.find("ACROMATE-CALLBOX") >= 0:
                        if update_info.get("chg_port_info", None) and update_info["chg_port_info"].get("extra_wan", None):
                            # 회선이중화 : 변경된 extra_wan 정보가 있으면 rlt > parameters 에서 해당 값 수정처리.
                            chg_wan_info = update_info["chg_port_info"]["extra_wan"]
                            chg_dlm = "XWAN"

                            # 해당 vnf 가 사용하는 physnet_name을 찾아야한다.
                            try:
                                if rt_dict is None: # yaml load를 한번만 하기 위해서...
                                    rt_dict = yaml.load(rlt_dict["resourcetemplate"])

                                serv_main_ports = rt_dict["resources"]["SERV_main_" + vnf_name]["properties"]["networks"]
                                for port in serv_main_ports:
                                    if port["port"]["get_resource"].find("PORT_red") >= 0:
                                        port_name = port["port"]["get_resource"]
                                        pnet_name = rt_dict["resources"][port_name]["properties"]["network_id"]["get_resource"]
                                        physnet_name = rt_dict["resources"][pnet_name]["properties"]["physical_network"]
                                        break
                            except Exception, e:
                                log.error("Failed to get physnet info of a vnf (%s) : %s" % (vnf_name, str(e)))
                                return -500, str(e)

                            if physnet_name is None:
                                log.warning("Failed to find physnet_name of vnf %s" % vnf_name)
                                continue
                            else:
                                # vnf_name : physnet_name mapping 정보...
                                extra_wan_mapping[vnf_name] = physnet_name

                            log.debug("__________ 변경된 extra_wan 정보가 있는 경우 chg_wan_info = %s" % chg_wan_info)
                    else:
                        continue

                    if chg_wan_info is None:
                        continue

                    for param in rlt_dict['parameters']:

                        if param["name"].find("redFixedIp") >= 0 and param["name"].find(vnf_name) >= 0:
                            if chg_wan_info["public_ip"]: # 변경된 public_ip 정보가 있으면.
                                if chg_dlm == "WAN":
                                    key = _find_r_kind(param["name"])
                                else:
                                    key = physnet_name

                                if key in chg_wan_info["public_ip"]: # 현재 param 관련 nic이 있는지 체크.

                                    if chg_wan_info["public_ip"][key] != "NA":
                                        param["value"] = chg_wan_info["public_ip"][key]
                                        log.debug("_____ Parameter name : %s, new value : %s" %(param["name"], param["value"]))

                        elif param["name"].find("redSubnet") >= 0 and param["name"].find(vnf_name) >= 0:
                            if chg_wan_info["public_ip"]:
                                if chg_dlm == "WAN":
                                    key = _find_r_kind(param["name"])
                                else:
                                    key = physnet_name
                                if key in chg_wan_info["public_ip"]:
                                    if chg_wan_info["public_ip"][key] != "NA" and chg_wan_info["public_cidr_prefix_new"][key] != -1:
                                        cidr_prefix = chg_wan_info["public_cidr_prefix_new"][key]
                                        temp_ip_info = netaddr.IPNetwork(chg_wan_info["public_ip"][key] + "/" + str(cidr_prefix))
                                        param['value'] = str(temp_ip_info.network) + "/" + str(cidr_prefix)
                                        log.debug("_____ Parameter name : %s, new value : %s" %(param["name"], param["value"]))

                        elif param["name"].find("redFixedMac") >= 0 and param["name"].find(vnf_name) >= 0:
                            if chg_wan_info["mac"]: # 변경된 mac 정보가 있으면.
                                if chg_dlm == "WAN":
                                    key = _find_r_kind(param["name"])
                                else:
                                    key = physnet_name
                                if key in chg_wan_info["mac"]:
                                    param["value"] = chg_wan_info["mac"][key]
                                    log.debug("_____ Parameter name : %s, new value : %s" %(param["name"], param["value"]))

                        elif param["name"].find("redType") >= 0 and param["name"].find(vnf_name) >= 0:
                            if chg_wan_info["ipalloc_mode_public"]: # 변경된 public_ip_dhcp 정보가 있으면.
                                if chg_dlm == "WAN":
                                    key = _find_r_kind(param["name"])
                                else:
                                    key = physnet_name
                                if key in chg_wan_info["ipalloc_mode_public"]:
                                    param["value"] = chg_wan_info["ipalloc_mode_public"][key]
                                    log.debug("_____ Parameter name : %s, new value : %s" %(param["name"], param["value"]))

                        elif param["name"].find("defaultGw") >= 0 and param["name"].find(vnf_name) >= 0:
                            if chg_wan_info["public_gw_ip"]: # 변경된 public_gw_ip 정보가 있으면.
                                if chg_dlm == "WAN":
                                    key = _find_r_kind(param["name"])
                                else:
                                    key = physnet_name
                                if key in chg_wan_info["public_gw_ip"]:
                                    if chg_wan_info["public_gw_ip"][key] != "NA":
                                        param["value"] = chg_wan_info["public_gw_ip"][key]
                                        log.debug("_____ Parameter name : %s, new value : %s" %(param["name"], param["value"]))

                        elif param["name"].find("redCIDR") >= 0 and param["name"].find(vnf_name) >= 0:
                            if chg_wan_info["public_cidr_prefix"]: # 변경된 public_cidr_prefix 정보가 있으면.
                                if chg_dlm == "WAN":
                                    key = _find_r_kind(param["name"])
                                else:
                                    key = physnet_name
                                if key in chg_wan_info["public_cidr_prefix"]:
                                    if chg_wan_info["public_cidr_prefix"][key] != -1:
                                        param["value"] = chg_wan_info["public_cidr_prefix"][key]
                                        log.debug("_____ Parameter name : %s, new value : %s" %(param["name"], param["value"]))

            elif update_info.get("publicip_update_dict", None): # 기존 로직...호환성 유지문제로 남겨놓음
                publicip_update_dict = update_info["publicip_update_dict"]
                for param in rlt_dict['parameters']:

                    if publicip_update_dict.get('publicip', None):
                        # log.debug("[HJC] 1. update_info - publicip: %s" %str(update_info['publicip']))

                        if param["name"].find("redFixedIp") >= 0:
                            param['value'] = publicip_update_dict['publicip']
                            log.debug("[HJC] Update %s = %s" % (str(param["name"]), str(param["value"])))

                        if param['name'].find("redSubnet") >= 0:
                            temp_ip_info = netaddr.IPNetwork(publicip_update_dict['publicip'] + "/" + str(publicip_update_dict['publiccidr_cur']))
                            param['value'] = str(temp_ip_info.network) + "/" + str(publicip_update_dict['publiccidr_cur'])
                            log.debug("[HJC] Update %s = %s" % (str(param["name"]), str(param["value"])))

                    if param['name'].lower().find("redfixedmac") >= 0:
                        if publicip_update_dict.get('publicmac', None):
                            param['value'] = publicip_update_dict['publicmac']
                            log.debug("[HJC] Update %s = %s" % (str(param["name"]), str(param["value"])))

                    if param['name'].lower().find("redtype") >= 0:
                        if publicip_update_dict.get('ipalloc_mode_public', None):
                            param['value'] = publicip_update_dict['ipalloc_mode_public']
                            log.debug("[HJC] Update %s = %s" % (str(param["name"]), str(param["value"])))

                    if param['name'].lower().find("defaultgw") >= 0:
                        if publicip_update_dict.get('publicgwip', None):
                            param['value'] = publicip_update_dict['publicgwip']
                            log.debug("[HJC] Update %s = %s" % (str(param["name"]), str(param["value"])))

                    if param['name'].lower().find("redcidr") >= 0:
                        if publicip_update_dict.get('publiccidr', None):
                            param['value'] = publicip_update_dict['publiccidr']
                            log.debug("[HJC] Update %s = %s" % (str(param["name"]), str(param["value"])))

            is_changed = False

            # 변경된 LAN IP => Parameters value
            if update_info.get("chg_port_info", None):
                chg_port_info = update_info.get("chg_port_info")
                if chg_port_info.get("lan_office", None):
                    lan_office = chg_port_info["lan_office"]
                    for param in rlt_dict['parameters']:
                        if param["name"].find("UTM") >= 0 or param["name"].find("KT-VNF") >= 0:
                            if param["name"].find("greenFixedIp") >= 0:
                                param["value"] = lan_office["vnet_office_ip"]
                                log.debug("_____ greenFixedIp name : %s, new value : %s" %(param["name"], param["value"]))
                            if param["name"].find("greenCIDR") >= 0:
                                param["value"] = lan_office["vnet_office_cidr"]
                                log.debug("_____ greenCIDR name : %s, new value : %s" %(param["name"], param["value"]))

                    for vnf in nsr_data['vnfs']:
                        if vnf["name"].find("UTM") >= 0 or vnf["name"].find("KT-VNF") >= 0:
                            for vm in vnf['vdus']:
                                for cp in vm['cps']:
                                    if cp["name"].find("green") >= 0 and cp["name"].find(vnf["name"]) >= 0:
                                        cp["ip"] = lan_office["vnet_office_ip"]
                                        is_changed = True
                                        log.debug("_____[GREEN CP 변경] %s - CP name : %s, new IP : %s" %(vnf["name"], cp["name"], cp["ip"]))
                                        break

                if chg_port_info.get("lan_server", None):
                    lan_server = chg_port_info["lan_server"]
                    for param in rlt_dict['parameters']:
                        if param["name"].find("UTM") >= 0 or param["name"].find("KT-VNF") >= 0:
                            if param["name"].find("orangeFixedIp") >= 0:
                                param["value"] = lan_server["vnet_server_ip"]
                                log.debug("_____ orangeFixedIp name : %s, new value : %s" %(param["name"], param["value"]))
                            if param["name"].find("orangeCIDR") >= 0:
                                param["value"] = lan_server["vnet_server_cidr"]
                                log.debug("_____ orangeCIDR name : %s, new value : %s" %(param["name"], param["value"]))

                    for vnf in nsr_data['vnfs']:
                        if vnf["name"].find("UTM") >= 0 or vnf["name"].find("KT-VNF") >= 0:
                            for vm in vnf['vdus']:
                                for cp in vm['cps']:
                                    if cp["name"].find("orange") >= 0 and cp["name"].find(vnf["name"]) >= 0:
                                        cp["ip"] = lan_server["vnet_server_ip"]
                                        is_changed = True
                                        log.debug("_____[ORANGE CP 변경] %s - CP name : %s, new IP : %s" %(vnf["name"], cp["name"], cp["ip"]))
                                        break

            iparm_result, iparm_content = compose_nsr_internal_params(vnf_name_list, rlt_dict['parameters'])

            if iparm_result < 0:
                raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))

            result, content = orch_dbm.delete_nsr_param(mydb, {"nsseq" : rlt_dict['nsseq']})
            if result < 0:
                raise Exception("failed to DB Delete of old NSR parameters: %d %s" %(result, content))

            result, content = orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])
            if result < 0:
                raise Exception("failed to DB Insert New NSR Params: %d %s" %(result, content))

            # rlt 업데이트
            result, content = orch_dbm.update_rlt_data(mydb, json.dumps(rlt_dict), rlt_seq=rlt_data["rltseq"])
            if result < 0:
                raise Exception("failed to DB Update for RLT: %d %s" %(result, content))

            # UTM의 public_ip가 변경되면 해당 UTM과 UTM의 public_ip를 사용하는 기타 VNF의 web_url을 변경한다.
            # 단, extra_wan을 사용하는 VNF는 자신의 IP Port를 따로 가지고 있으므로 별도로 처리해야한다.
            if update_info.get("publicip_update_dict", None) and update_info["publicip_update_dict"].get("publicip", None):
                is_changed = True

                publicip_update_dict = update_info["publicip_update_dict"]

                for vnf in nsr_data['vnfs']:

                    # UTM 만 처리 (extra_wan을 사용하는 VNF 제외)
                    if vnf["name"].find("ACROMATE-CALLBOX") >= 0:
                        continue

                    if vnf.get('web_url', None):

                        old_web_url = vnf['web_url']
                        new_web_url = publicip_update_dict['publicip']
                        if old_web_url.find("://") >= 0:
                            new_web_url = old_web_url[0:old_web_url.index("://")+3] + new_web_url

                        if old_web_url.find(":", 7) >= 0:
                            new_web_url += old_web_url[old_web_url.index(":", 7):]

                        vnf['web_url'] = new_web_url
                        log.debug("_____[WAN WEB_URL 변경] VNF : %s, old web_url : %s, new web_url : %s" % (vnf['name'], old_web_url, new_web_url))

                    for vm in vnf['vdus']:

                        if vm.get('web_url', None):

                            old_web_url = vm['web_url']
                            new_web_url = publicip_update_dict['publicip']
                            if old_web_url.find("://") >= 0:
                                new_web_url = old_web_url[0:old_web_url.index("://")+3] + new_web_url

                            if old_web_url.find(":", 7) >= 0:
                                new_web_url += old_web_url[old_web_url.index(":", 7):]

                            vm['web_url'] = new_web_url
                            log.debug("_____[WAN WEB_URL 변경] VM : %s, old web_url : %s, new web_url : %s" % (vm['name'], old_web_url, new_web_url))

                        # 기존 로직 호환성 유지. is_wan_list 없을 경우 - cp ip 변경.
                        if not update_info.get("is_wan_list", False):
                            if 'cps' in vm:
                                for cp in vm['cps']:
                                    if cp["name"].find("red") >= 0:
                                        if cp['ip'] != publicip_update_dict['publicip']:
                                            cp['ip'] = publicip_update_dict['publicip']
                                            log.debug("_____[기존 호환성 - CP 변경] CP : %s, new IP : %s" % (cp['name'], cp['ip']))

            # 회선이중화 : 변경된 wan 정보가 있으면 cp의 ip값 변경
            if update_info.get("is_wan_list", False) and update_info.get("chg_port_info", None) and update_info["chg_port_info"].get("wan", None):
                is_changed = True
                chg_wan_info = update_info["chg_port_info"]["wan"]
                if chg_wan_info["public_ip"]: # 변경된 public_ip 정보가 있으면.

                    for vnf in nsr_data['vnfs']:

                        if vnf["name"].find("KT-VNF") >= 0 or vnf["name"].find("UTM") >= 0:
                            pass
                        else:
                            continue

                        for vm in vnf['vdus']:
                            for cp in vm['cps']:
                                if cp["name"].find("red") >= 0 and cp["name"].find(vnf["name"]) >= 0:
                                    r_kind = _find_r_kind(cp['name'])
                                    if r_kind in chg_wan_info["public_ip"]: # 현재 param 관련 nic이 있는지 체크.
                                        cp["ip"] = chg_wan_info["public_ip"][r_kind]
                                        log.debug("_____[WAN CP 변경] %s - CP name : %s, new IP : %s" %(vnf["name"], cp["name"], cp["ip"]))

            # extra_wan : web_url, cp ip 변경처리.
            if update_info.get("is_wan_list", False) and update_info.get("chg_port_info", None) and update_info["chg_port_info"].get("extra_wan", None):
                is_changed = True
                chg_wan_info = update_info["chg_port_info"]["extra_wan"]
                if chg_wan_info["public_ip"]: # 변경된 public_ip 정보가 있으면.
                    for vnf in nsr_data['vnfs']:
                        # 변경된 extra_wan의 public_ip가 존재하는지 체크...
                        if extra_wan_mapping.has_key(vnf["name"]) and extra_wan_mapping[vnf["name"]] in chg_wan_info["public_ip"]:

                            if vnf.get('web_url', None):
                                old_web_url = vnf['web_url']
                                new_web_url = chg_wan_info["public_ip"][extra_wan_mapping[vnf["name"]]]
                                if old_web_url.find("://") >= 0:
                                    new_web_url = old_web_url[0:old_web_url.index("://")+3] + new_web_url
                                if old_web_url.find(":", 7) >= 0:
                                    new_web_url += old_web_url[old_web_url.index(":", 7):]
                                vnf['web_url'] = new_web_url
                                log.debug("_____ [EXTRA_WAN WEB_URL 변경] VNF : %s, old web_url : %s, new web_url : %s" % (vnf['name'], old_web_url, new_web_url))

                            for vm in vnf['vdus']:

                                if vm.get('web_url', None):
                                    old_web_url = vm['web_url']
                                    new_web_url = chg_wan_info["public_ip"][extra_wan_mapping[vnf["name"]]]
                                    if old_web_url.find("://") >= 0:
                                        new_web_url = old_web_url[0:old_web_url.index("://")+3] + new_web_url
                                    if old_web_url.find(":", 7) >= 0:
                                        new_web_url += old_web_url[old_web_url.index(":", 7):]
                                    vm['web_url'] = new_web_url
                                    log.debug("_____[EXTRA_WAN WEB_URL 변경] VM : %s, old web_url : %s, new web_url : %s" % (vm['name'], old_web_url, new_web_url))

                                for cp in vm['cps']:
                                    if cp["name"].find("red") >= 0 and cp["name"].find(vnf["name"]) >= 0:
                                        cp["ip"] = chg_wan_info["public_ip"][extra_wan_mapping[vnf["name"]]]
                                        log.debug("_____[EXTRA_WAN CP 변경] %s - CP name : %s, new IP : %s" %(vnf["name"], cp["name"], cp["ip"]))
                                        break   # red port가 하나뿐이므로 빠져나간다.

            if is_changed:
                result, data = orch_dbm.update_nsr_as_a_whole(mydb, nsr_data['name'], nsr_data['description'], nsr_data)
                if result < 0:
                    log.error("Failed to update NSR from DB: %d %s" % (result, data))
                    return result, data

            log.debug("__________[HJC] Completed to _update_nsr_by_obagent_thread with %s" % str(update_info))

    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return 200, "OK"


def compose_nsr_internal_params(vnf_name_list, params):
    """
        parameter list 에서 FixedIp 값에 따른 내부 Parameter의 value 세팅

    :param vnf_name_list:
    :param params:
    :return:
    """
    if vnf_name_list is None or params is None:
        return -HTTP_Internal_Server_Error, "Invaild Parameter List"
    if len(params) == 0:
        return 200, "No Params"

    CONST_FIXED_IP = "FixedIp"
    CONST_CIDR = "CIDR"
    CONST_NETWORK_ADDR = "NetAddr"
    CONST_NETMASK = "Netmask"
    CONST_BROADCAST = "Broadcast"
    CONST_SUBNET = "Subnet"

    for vnf_name in vnf_name_list:

        for param in params:

            dict_cidr = None
            dict_netaddr = None
            dict_netmask = None
            dict_broadcast = None
            dict_subnet = None

            if param['name'].find(vnf_name) >= 0 and param['name'].find(CONST_FIXED_IP) >= 0:

                id_ip = param['name'].split("_")[1].split(CONST_FIXED_IP)[0]
                dict_fixedip = param

                if dict_fixedip['value'] is None or dict_fixedip['value'] == 'NA':
                    continue

                wan_kind = ""
                if id_ip == "red":
                    if param['name'].find("R1") >= 0:
                        wan_kind = "R1"
                    elif param['name'].find("R2") >= 0:
                        wan_kind = "R2"
                    elif param['name'].find("R3") >= 0:
                        wan_kind = "R3"
                    else:
                        wan_kind = "_"

                for p in params:

                    if p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_CIDR + wan_kind) >= 0:
                        dict_cidr = p
                    elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_NETWORK_ADDR + wan_kind) >= 0:
                        dict_netaddr = p
                    elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_NETMASK + wan_kind) >= 0:
                        dict_netmask = p
                    elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_BROADCAST + wan_kind) >= 0:
                        dict_broadcast = p
                    elif p['name'].find(vnf_name) >= 0 and p['name'].find(id_ip + CONST_SUBNET + wan_kind) >= 0:
                        dict_subnet = p

                try:
                    if dict_subnet and dict_subnet.get('value', "none").lower() != "none":
                        log.debug("[****** HJC *****] Subnet Given: %s" %str(dict_subnet))
                        ip_cal_result = netaddr.IPNetwork(dict_subnet['value'])
                    elif dict_netmask and dict_netmask.get('value', "none").lower() != "none" :
                        log.debug("[****** HJC *****] Netmask Given: %s" %str(dict_netmask))
                        ip_cal_result = netaddr.IPNetwork(dict_fixedip['value']+"/"+dict_netmask['value'])
                    elif dict_cidr and dict_cidr.get('value', "none").lower() != "none":
                        log.debug("[****** HJC *****] CIDR Given: %s" %str(dict_cidr))
                        ip_cal_result = netaddr.IPNetwork(dict_fixedip['value'] + "/" + dict_cidr['value'])
                    else:
                        log.debug("No CIDR. Use 24 as a prefix len")
                        ip_cal_result = netaddr.IPNetwork(dict_fixedip['value'] + "/24")

                    if netaddr.IPAddress(dict_fixedip['value']) in ip_cal_result:
                        log.debug("Valid IP Address and Network Address: %s for %s" %(str(dict_fixedip['value']), dict_fixedip['name']))
                    else:
                        log.debug("InValid IP Address and Network Address: %s for %s" %(str(dict_fixedip['value']), dict_fixedip['name']))
                        ip_cal_result = netaddr.IPNetwork(dict_fixedip['value'] + "/24")

                    if ip_cal_result:
                        if dict_cidr:
                            dict_cidr['value'] = str(ip_cal_result.prefixlen)

                        if dict_netaddr:
                            dict_netaddr['value'] = str(ip_cal_result.network)

                        if dict_netmask:
                            dict_netmask['value'] = str(ip_cal_result.netmask)

                        if dict_broadcast:
                            dict_broadcast['value'] = str(ip_cal_result.broadcast)

                        if dict_subnet:
                            dict_subnet['value'] = str(ip_cal_result.network) + "/" + str(ip_cal_result.prefixlen)

                except Exception, e:
                    log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
                    return -HTTP_Internal_Server_Error, str(e)
    return 200, "OK"


def check_chg_wan_info(mydb, serverseq, old_wan_list, new_wan_list, is_wan_count_changed=False):
    """
        회선이중화 : wan_list 가 변경되었는지 체크
        변경정보를 찾고, 변경된 정보가 있으면, tb_server_wan에 update 후 chg_wan_info 리턴

    :param mydb:
    :param serverseq:
    :param old_wan_list:
    :param new_wan_list:
    :return: chg_wan_info
    """

    # chg_wan_info : 변경된 항목을 담아두는 객체. 변경 체크 항목과 변경된 항목 갯수 저장
    chg_wan_info = {"public_ip":{}, "public_cidr_prefix":{}, "public_gw_ip":{}, "ipalloc_mode_public":{}, "mac":{}, "nic":{}
                , "physnet_name":{}, "mode":{}, "status":{}, "parm_count":0, "etc_count":0, "old_mac":{}, "public_cidr_prefix_new":{}}

    if old_wan_list is None or new_wan_list is None:
        return chg_wan_info

    for old_wan in old_wan_list:
        for new_wan in new_wan_list:
            if old_wan["name"] == new_wan["name"]:
                # _update_nsr 관련 정보 변경사항 체크
                if old_wan["public_ip"] != new_wan["public_ip"]:
                    chg_wan_info["public_ip"][new_wan["name"]] = new_wan["public_ip"]
                    # public_ip 변경시 redSubnet Parameter 도 변경. 이때 현재 public_cidr_prefix 가 필요하다.
                    chg_wan_info["public_cidr_prefix_new"][new_wan["name"]] = new_wan["public_cidr_prefix"]
                    chg_wan_info["parm_count"] += 1
                if old_wan["public_cidr_prefix"] != new_wan["public_cidr_prefix"]:
                    chg_wan_info["public_cidr_prefix"][new_wan["name"]] = new_wan["public_cidr_prefix"]
                    chg_wan_info["parm_count"] += 1
                if old_wan["public_gw_ip"] != new_wan.get("public_gw_ip", None): # STATIC인 경우 public_gw_ip가 없을수 있음.
                    chg_wan_info["public_gw_ip"][new_wan["name"]] = new_wan.get("public_gw_ip", None)
                    chg_wan_info["parm_count"] += 1
                if old_wan["ipalloc_mode_public"] != new_wan["ipalloc_mode_public"]:
                    chg_wan_info["ipalloc_mode_public"][new_wan["name"]] = new_wan["ipalloc_mode_public"]
                    chg_wan_info["parm_count"] += 1
                if old_wan["mac"] != new_wan["mac"]:
                    chg_wan_info["mac"][new_wan["name"]] = new_wan["mac"]
                    chg_wan_info["old_mac"][new_wan["name"]] = old_wan["mac"]
                    chg_wan_info["parm_count"] += 1

                # 추가적인 tb_server_wan 변경정보 체크
                if old_wan["nic"] != new_wan["nic"]:
                    chg_wan_info["nic"][new_wan["name"]] = new_wan["nic"]
                    chg_wan_info["etc_count"] += 1
                if old_wan["status"] != new_wan["status"]:
                    chg_wan_info["status"][new_wan["name"]] = new_wan["status"]
                    chg_wan_info["etc_count"] += 1
                if old_wan["mode"] != new_wan["mode"]:
                    chg_wan_info["mode"][new_wan["name"]] = new_wan["mode"]
                    chg_wan_info["etc_count"] += 1
                if new_wan.get("physnet_name"):
                    if old_wan.get("physnet_name") != new_wan["physnet_name"]:
                        chg_wan_info["physnet_name"][new_wan["name"]] = new_wan["physnet_name"]
                        chg_wan_info["etc_count"] += 1

                break

    # tb_server_wan 업데이트 처리.
    # chg_wan_info 변경사항
    if not is_wan_count_changed:    # wan 갯수가 변경된 경우에는 update_server에서 이미 DB저장처리했으니까 업데이트 생략.
        if chg_wan_info["parm_count"] > 0 or chg_wan_info["etc_count"] > 0:
            for key1 in chg_wan_info.keys():
                # tb_server_wan 업데이트할 column만 필터링(로직용 객체들은 제외시킨다.)
                if key1 == "parm_count" or key1 == "etc_count" or key1 == "old_mac" or key1 == "public_cidr_prefix_new":
                    continue
                for key2 in chg_wan_info[key1].keys():
                    log.debug("_##_ serverseq = %s, name = %s ==> %s = %s" %(serverseq, key2, key1, chg_wan_info[key1][key2]))
                    orch_dbm.update_server_wan(mydb, {"serverseq":serverseq, "name": key2}, {key1: chg_wan_info[key1][key2]})

    return chg_wan_info

def check_chg_extra_wan_info(mydb, serverseq, old_wan_list, new_wan_list, is_wan_count_changed=False):
    """
         physnet_name 기준으로 변경체크
    :param mydb:
    :param serverseq:
    :param old_wan_list:
    :param new_wan_list:
    :param is_wan_count_changed:
    :return:
    """

    chg_wan_info = {"public_ip":{}, "public_cidr_prefix":{}, "public_gw_ip":{}, "ipalloc_mode_public":{}, "mac":{}, "nic":{}
                , "name":{}, "mode":{}, "status":{}, "parm_count":0, "etc_count":0, "old_mac":{}, "public_cidr_prefix_new":{}}

    if old_wan_list is None or new_wan_list is None:
        return chg_wan_info

    for old_wan in old_wan_list:
        for new_wan in new_wan_list:
            if old_wan["physnet_name"] == new_wan["physnet_name"]:
                # _update_nsr 관련 정보 변경사항 체크
                if old_wan["public_ip"] != new_wan["public_ip"]:
                    chg_wan_info["public_ip"][new_wan["physnet_name"]] = new_wan["public_ip"]
                    # public_ip 변경시 redSubnet Parameter 도 변경. 이때 현재 public_cidr_prefix 가 필요하다.
                    chg_wan_info["public_cidr_prefix_new"][new_wan["physnet_name"]] = new_wan["public_cidr_prefix"]
                    chg_wan_info["parm_count"] += 1
                if old_wan["public_cidr_prefix"] != new_wan["public_cidr_prefix"]:
                    chg_wan_info["public_cidr_prefix"][new_wan["physnet_name"]] = new_wan["public_cidr_prefix"]
                    chg_wan_info["parm_count"] += 1
                if old_wan["public_gw_ip"] != new_wan.get("public_gw_ip", None): # STATIC인 경우 public_gw_ip가 없을수 있음.
                    chg_wan_info["public_gw_ip"][new_wan["physnet_name"]] = new_wan.get("public_gw_ip", None)
                    chg_wan_info["parm_count"] += 1
                if old_wan["ipalloc_mode_public"] != new_wan["ipalloc_mode_public"]:
                    chg_wan_info["ipalloc_mode_public"][new_wan["physnet_name"]] = new_wan["ipalloc_mode_public"]
                    chg_wan_info["parm_count"] += 1
                if old_wan["mac"] != new_wan["mac"]:
                    chg_wan_info["mac"][new_wan["physnet_name"]] = new_wan["mac"]
                    chg_wan_info["old_mac"][new_wan["physnet_name"]] = old_wan["mac"]
                    chg_wan_info["parm_count"] += 1

                # 추가적인 tb_server_wan 변경정보 체크
                if old_wan["nic"] != new_wan["nic"]:
                    chg_wan_info["nic"][new_wan["physnet_name"]] = new_wan["nic"]
                    chg_wan_info["etc_count"] += 1
                if old_wan["status"] != new_wan["status"]:
                    chg_wan_info["status"][new_wan["physnet_name"]] = new_wan["status"]
                    chg_wan_info["etc_count"] += 1
                if old_wan["mode"] != new_wan["mode"]:
                    chg_wan_info["mode"][new_wan["physnet_name"]] = new_wan["mode"]
                    chg_wan_info["etc_count"] += 1
                if old_wan["name"] != new_wan["name"]:
                    chg_wan_info["name"][new_wan["physnet_name"]] = new_wan["name"]
                    chg_wan_info["etc_count"] += 1

                break

    # tb_server_wan 업데이트 처리.
    # chg_wan_info 변경사항
    if not is_wan_count_changed:    # wan 갯수가 변경된 경우에는 update_server에서 이미 DB저장처리했으니까 업데이트 생략.
        if chg_wan_info["parm_count"] > 0 or chg_wan_info["etc_count"] > 0:
            for key1 in chg_wan_info.keys():
                # tb_server_wan 업데이트할 column만 필터링(로직용 객체들은 제외시킨다.)
                if key1 == "parm_count" or key1 == "etc_count" or key1 == "old_mac" or key1 == "public_cidr_prefix_new":
                    continue
                for key2 in chg_wan_info[key1].keys():
                    log.debug("_##_ serverseq = %s, physnet_name = %s ==> %s = %s" %(serverseq, key2, key1, chg_wan_info[key1][key2]))
                    orch_dbm.update_server_wan(mydb, {"serverseq":serverseq, "physnet_name": key2}, {key1: chg_wan_info[key1][key2]})

    return chg_wan_info


def check_chg_lan_info(mydb, nsseq, vnet_dict):

    if vnet_dict is None:
        return None, None

    result, rlt_data = orch_dbm.get_rlt_data(mydb, nsseq)
    if result < 0:
        log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
        raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

    rlt_dict = rlt_data["rlt"]

    office = {}
    for param in rlt_dict['parameters']:
        if param["name"].find("UTM") >= 0 or param["name"].find("KT-VNF") >= 0:
            if param["name"].find("greenFixedIp") >= 0:
                if param["value"] != vnet_dict["vnet_office_ip"]:
                    office["vnet_office_ip"] = vnet_dict["vnet_office_ip"]
                    office["vnet_office_cidr"] = vnet_dict["vnet_office_cidr"]
                    office["vnet_office_subnets"] = vnet_dict["vnet_office_subnets"]
                break
    server = {}
    for param in rlt_dict['parameters']:
        if param["name"].find("UTM") >= 0 or param["name"].find("KT-VNF") >= 0:
            if param["name"].find("orangeFixedIp") >= 0:
                if param["value"] != vnet_dict["vnet_server_ip"]:
                    server["vnet_server_ip"] = vnet_dict["vnet_server_ip"]
                    server["vnet_server_cidr"] = vnet_dict["vnet_server_cidr"]
                    server["vnet_server_subnets"] = vnet_dict["vnet_server_subnets"]
                break
    # other = {}
    # for param in rlt_dict['parameters']:
    #     if param["name"].find("UTM") >= 0 or param["name"].find("KT-VNF") >= 0:
    #         if param["name"].find("orangeFixedIp") >= 0:
    #             if param["value"] != vnet_dict["vnet_ha_ip"]:
    #                 other["vnet_ha_ip"] = vnet_dict["vnet_ha_ip"]
    #                 other["vnet_ha_cidr"] = vnet_dict["vnet_ha_cidr"]
    #                 other["vnet_ha_subnets"] = vnet_dict["vnet_ha_subnets"]
    #             break

    return office, server

# 2018-03-15 : 더이상 사용하지 않는 함수... 삭제처리.
# def update_nsr_for_latest(mydb, server_data_before, nsr_id):
#     """
#         Provisioning 등 내부적인 제어동작이 수행되는 도중에는 obagent가 변경되는 정보(public_ip 등)를 가지고 Call 해도 Skip된다.
#         그럴경우 해당 제어동작 마지막 부분에서 update_nsr_for_latest 함수를 Call해서 최신 정보를 맞춰준다.
#
#     :param mydb:
#     :param server_data_before:
#     :param nsr_id:
#     :return:
#     """
#
#     log.debug("__________ WAN IP 변경사항 최신 반영처리 update_nsr_for_latest\nBEFORE SERVER : %s" % server_data_before)
#
#     result, server_data_after = orch_dbm.get_server_id(mydb, server_data_before['serverseq'])
#     if result < 0:
#         raise Exception("Failed to get server data : serverseq = %s" % str(server_data_before['serverseq']))
#
#     log.debug("__________ WAN IP 변경사항 최신 반영처리 update_nsr_for_latest\nAFTER SERVER%s" % server_data_after)
#
#     update_info = {}
#     publicip_update_dict = {}
#     if server_data_before["publicip"] !=  server_data_after["publicip"]:
#         publicip_update_dict['publicip'] = server_data_after['publicip']
#         publicip_update_dict['publiccidr_cur'] = server_data_after['publiccidr']
#     if server_data_before["publicmac"] !=  server_data_after["publicmac"]:
#         publicip_update_dict['publicmac'] = server_data_after['publicmac']
#     if server_data_before["ipalloc_mode_public"] !=  server_data_after["ipalloc_mode_public"]:
#         publicip_update_dict['ipalloc_mode_public'] = server_data_after['ipalloc_mode_public']
#     if server_data_before["publicgwip"] !=  server_data_after["publicgwip"]:
#         publicip_update_dict['publicgwip'] = server_data_after['publicgwip']
#     if server_data_before["publiccidr"] !=  server_data_after["publiccidr"]:
#         publicip_update_dict['publiccidr'] = server_data_after['publiccidr']
#
#     log.debug("__________ 변경사항 publicip_update_dict = %s" % publicip_update_dict)
#
#     # tb_server의 public 관련 값이 하나라도 변경된 사항이 있으면 계속 진행하고, 없으면 종료...
#     if publicip_update_dict:
#         update_info["publicip_update_dict"] = publicip_update_dict
#     else:
#         return
#
#     chg_wan_info = None
#     parm_count = 0
#     result_wan, old_wan_list = orch_dbm.get_server_wan_list(mydb, server_data_before['serverseq'])
#     if result_wan > 0:
#
#         update_info["is_wan_list"] = True
#         r_name = ""
#         for wan in old_wan_list:
#             if wan["nic"].strip() == server_data_after["public_nic"].strip():
#                 r_name =  wan["name"]
#                 break
#
#         if r_name == "":
#             log.error("__________ Not found wan name !!!")
#             pass
#         else:
#             new_wan_list = [{"public_ip":server_data_after["publicip"], "public_cidr_prefix":server_data_after["publiccidr"]
#                             , "public_gw_ip":server_data_after["publicgwip"], "ipalloc_mode_public":server_data_after["ipalloc_mode_public"]
#                             , "mac":server_data_after["publicmac"], "nic":server_data_after["public_nic"]
#                             , "mode":server_data_after["net_mode"], "name":r_name, "status":"A" }]
#
#             log.debug("__________ new_wan_list = %s" % new_wan_list)
#
#             chg_wan_info = check_chg_wan_info(mydb, server_data_before['serverseq'], old_wan_list, new_wan_list)
#             parm_count = chg_wan_info["parm_count"]
#
#             log.debug("__________ chg_wan_info = %s" % chg_wan_info)
#
#     if parm_count > 0:
#         chg_port_info = {"wan":chg_wan_info}
#         update_info["chg_port_info"] = chg_port_info
#
#     update_nsr_by_obagent(mydb, nsr_id, update_info, use_thread=False)


def update_server_status(mydb, server_dict, is_action=False, e2e_log = None, action_type=None):
    """
        서버의 상태값 업데이트 및 오더매니져에 Inform

    :param mydb:
    :param server_dict:
    :param e2e_log:
    :return:
    """
    try:
        # Step 0. Check server_dict
        if server_dict.get('serverseq') is None:
            log.error("Cannot update server status due to no serverseq: %s" %str(server_dict))
            raise Exception("Cannot update server status due to no serverseq: %s" %str(server_dict))

        # Step 1. Get Server Data from DB
        os_result, os_data = orch_dbm.get_server_id(mydb, server_dict['serverseq'])
        if os_result < 0:
            log.error("failed to get Server Info from DB: %d %s" %(os_result, os_data))
            raise Exception("failed to get Server Info from DB: %d %s" %(os_result, os_data))

        # Step 2. Update Server Data in DB
        if os_data.get('status') == server_dict.get('status', None):
            # log.debug("Don't need to update Server Status: %s" %os_data.get('status'))
            return 200, os_data.get('status')

        if server_dict.get('onebox_id') is None or server_dict['onebox_id'] != os_data.get('onebox_id'):
            server_dict['onebox_id'] = os_data.get('onebox_id')

        us_result, us_data = orch_dbm.update_server_status(mydb, server_dict, is_action=is_action)
        if us_result < 0:
            log.error("failed to update Server Info from DB: %d %s" %(us_result, us_data))
            raise Exception("failed to update Server Info from DB: %d %s" %(us_result, us_data))
        else:
            log.debug("Succeed to update server status: %s" % server_dict.get('status'))

        # Step 3. Notify to Order Manager
        if "order_type" in server_dict and server_dict["order_type"] == "ORDER_OB_NEW":
            pass
        elif server_dict.get("status", None) and action_type != ActionType.BACUP:   # PROVS/DELNS/NSRUP
            # if action_type == ActionType.PROVS or action_type == ActionType.DELNS or action_type == ActionType.NSRUP:
            #     pass
            myOdm = odmconnector.odmconnector("OrderManager")
            noti_result, noti_data = myOdm.inform_onebox_status(server_dict['onebox_id'], server_dict['status'])
            if noti_result < 0:
                log.error("Failed to inform One-Box's Status to the Order Manager: %d %s" %(noti_result, noti_data))
                raise Exception("Failed to inform One-Box's Status to the Order Manager: %d %s" %(noti_result, noti_data))
            else:
                log.debug("Succeed to inform new server status to the Order Manager : %s" %server_dict['status'])
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"


def update_onebox_status_internally(mydb, action_type, action_dict=None, action_status=None, ob_data=None, ob_status=None):
    """

    :param mydb:
    :param action_type:
    :param action_dict:
    :param action_status:
    :param ob_data:
    :param ob_status:
    :return:
    """
    try:
        if action_dict and action_status:
            action_dict['status'] = action_status
            if action_status == ACTStatus.FAIL or action_status == ACTStatus.SUCC:
                action_dict['action'] = action_type + "E" # NGKIM: Use RE for restore
            else:
                action_dict['action'] = action_type + "S" # NGKIM: Use RE for restore

            orch_dbm.insert_action_history(mydb, action_dict)

        if ob_data and ob_status:
            ob_data['status'] = ob_status
            if ob_status == SRVStatus.ERR or ob_status == SRVStatus.INS or ob_status == SRVStatus.RDS or ob_status == SRVStatus.RIS or ob_status == SRVStatus.DSC:
                ob_data['action']= action_type + "E"
            else:
                ob_data['action']= action_type + "S"

            update_server_status(mydb, ob_data, is_action=True, action_type=action_type)

    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return 200, "OK"

def get_ktvnfm(mydb, server_id):
    """
        Get VNFM Connector

    :param mydb:
    :param server_id:
    :return:
    """
    result, content = orch_dbm.get_server_id(mydb, server_id)
    if result < 0:
        log.error("_get_ktvnfm error %d %s" % (result, content))
        return result, content
    elif result == 0:
        log.error("_get_ktvnfm not found a valid VNFM with the input params " + str(server_id))
        return -HTTP_Not_Found, "VNFM not found for " + str(server_id)

    vnfm_dict = {}
    # vnfm_dict[content['serverseq']] = vnfmconnector.vnfmconnector(
    #                name=content['servername'], host=content['mgmtip'], port='9014', uuid=content['serverseq'],
    #                user='root', passwd='ohhberry3333' # TOOD
    #                )
    vnfm_dict[content['serverseq']] = vnfmconnector.vnfmconnector(id=server_id, name=content['servername'], url=content['vnfm_base_url'], mydb=mydb)

    return len(vnfm_dict), vnfm_dict


def get_onebox_agent(mydb, onebox_id=None, nsr_id=None):
    """
        Onebox Agent Connector 객체를 얻는다.
    :param mydb:
    :param onebox_id:
    :param nsr_id:
    :return:
    """

    filter_dict={}
    if onebox_id:
        if type(onebox_id) is int or type(onebox_id) is long or (type(onebox_id) is unicode and onebox_id.isnumeric()):
            filter_dict['serverseq'] = onebox_id
        elif type(onebox_id) is str and onebox_id.isdigit():
            filter_dict['serverseq'] = onebox_id
        else:
            filter_dict['onebox_id'] = onebox_id
    elif nsr_id:
        filter_dict['nsseq'] = nsr_id
    else:
        return -HTTP_Bad_Request, "Invalid Condition"

    # result, content = orch_dbm.get_server_filters(mydb, filter_dict)
    result, content = orch_dbm.get_server_filters_wf(mydb, filter_dict)     # PNF 타입의 원박스도 조회 가능하도록 변경

    if result < 0:
        log.error("get_onebox_agent error %d %s" % (result, content))
        return result, content
    elif result==0:
        log.error("get_onebox_agent not found a valid One-Box Agent with the input params " + str(onebox_id))
        return -HTTP_Not_Found, "One-Box Agent not found for " +  str(onebox_id)

    if content[0]['obagent_base_url'] is None:
        log.error("No Access URL. Cannot connect to the OB Agent of the One-Box %s" %str(onebox_id))
        return -HTTP_Not_Found, "No Access URL. Cannot connect to the OB Agent of the One-Box %s" %str(onebox_id)

    ob_dict={}
    ob_dict[content[0]['serverseq']] = obconnector.obconnector(name=content[0]['servername'], url=content[0]['obagent_base_url'], mydb=mydb)

    return len(ob_dict), ob_dict


def get_server_all_with_filter(mydb, filter_data=None):
    """
        서버정보와 해당 서버의 vim정보를 조회
    :param mydb:
    :param filter_data:
    :return:
    """
    filter_dict={}
    if filter_data is None:
        return -HTTP_Bad_Request, "Invalid Condition"
    elif type(filter_data) is int or type(filter_data) is long or (type(filter_data) is unicode and filter_data.isnumeric()):
        filter_dict['serverseq'] = filter_data
    elif type(filter_data) is str and filter_data.isdigit():
        filter_dict['serverseq'] = filter_data
    elif af.is_ip_addr(filter_data):
        filter_dict['public_ip'] = filter_data
    else:
        filter_dict['onebox_id'] = filter_data
    result, content = orch_dbm.get_server_filters(mydb, filter_dict)

    if result <= 0:
        return result, content

    for c in content:
        if c.get('nfsubcategory') == "KtPnf":
            log.debug("PNF type > No VIM info found for the Server: %s" % str(c['serverseq']))
            c['vims'] = None
        else:
            vim_result, vim_content = orch_dbm.get_vim_serverseq(mydb, c['serverseq'])
            if vim_result <= 0:
                log.debug("No VIM info found for the Server: %s" %str(c['serverseq']))
            else:
                c['vims']=vim_content

    return 200, content

# PNF type
def get_server_all_with_filter_wf(mydb, filter_data=None):
    """
        서버정보와 해당 서버의 vim정보를 조회
    :param mydb:
    :param filter_data:
    :return:
    """
    filter_dict={}
    if filter_data is None:
        return -HTTP_Bad_Request, "Invalid Condition"
    elif type(filter_data) is int or type(filter_data) is long or (type(filter_data) is unicode and filter_data.isnumeric()):
        filter_dict['serverseq'] = filter_data
    elif type(filter_data) is str and filter_data.isdigit():
        filter_dict['serverseq'] = filter_data
    elif af.is_ip_addr(filter_data):
        filter_dict['public_ip'] = filter_data
    else:
        filter_dict['onebox_id'] = filter_data
    result, content = orch_dbm.get_server_filters_wf(mydb, filter_dict)

    if result <= 0:
        return result, content

    for c in content:
        if c.get('nfsubcategory') == "KtPnf":
            log.debug("PNF type > No VIM info found for the Server: %s" % str(c['serverseq']))
            c['vims'] = None
        else:
            vim_result, vim_content = orch_dbm.get_vim_serverseq(mydb, c['serverseq'])
            if vim_result <= 0:
                log.debug("No VIM info found for the Server: %s" %str(c['serverseq']))
            else:
                c['vims']=vim_content

    return 200, content

# event manager
def get_server_all_with_filter_em(mydb, content=None):
    """
    서버정보와 해당 서버의 vim정보를 조회
    :param mydb:
    :param content:
    :return:
    """
    # filter_dict={}
    # if filter_data is None:
    #     return -HTTP_Bad_Request, "Invalid Condition"
    # elif type(filter_data) is int or type(filter_data) is long or (type(filter_data) is unicode and filter_data.isnumeric()):
    #     filter_dict['serverseq'] = filter_data
    # elif type(filter_data) is str and filter_data.isdigit():
    #     filter_dict['serverseq'] = filter_data
    # elif af.is_ip_addr(filter_data):
    #     filter_dict['public_ip'] = filter_data
    # else:
    #     filter_dict['onebox_id'] = filter_data
    # result, content = orch_dbm.get_server_filters(mydb, filter_dict)
    #
    # if result <= 0:
    #     return result, content

    for c in content:
        if c.get('nfsubcategory') == "KtPnf":
            log.debug("PNF type > No VIM info found for the Server: %s" % str(c['serverseq']))
            c['vims'] = None
        else:
            vim_result, vim_content = orch_dbm.get_vim_serverseq(mydb, c['serverseq'])
            if vim_result <= 0:
                log.debug("No VIM info found for the Server: %s" %str(c['serverseq']))
            else:
                c['vims']=vim_content

    return 200, content


def get_ktmonitor():
    global global_config

    host_ip = global_config["monitor_ip"]
    host_port = global_config["monitor_port"]
    log.debug("get_ktmonitor(): Monitor IP: %s, Monitor Port: %s" % (host_ip, host_port))
    return monitorconnector.monitorconnector(name='ktmonitor', host=host_ip, port=host_port, uuid=None, user=None, passwd=None)

def get_vnfm_version(mydb, server_id):

    result, vnfms = get_ktvnfm(mydb, server_id)
    if result < 0:
        log.error("Failed to establish a vnfm connection")
        return -HTTP_Not_Found, "No KT VNFM Found"
    elif result > 1:
        log.error("Error, Several vnfms available, must be identify")
        return -HTTP_Bad_Request, "Several vnfms available, must be identify"
    myvnfm = vnfms.values()[0]

    result, version_res = myvnfm.get_vnfm_version()
    if result < 0:
        log.error("Failed to get vnfm version %s %s" % (result, version_res))
    return result, version_res


def sync_image_for_server(mydb, serverseq):

    sync_count = 0

    # get vnfm connector
    result, vnfms = get_ktvnfm(mydb, serverseq)
    if result < 0:
        log.error("Failed to establish a vnfm connection")
        return result, vnfms
    elif result > 1:
        log.error("Error, Several vnfms available, must be identify")
        return -500, "Error, Several vnfms available, must be identify"

    myvnfm = vnfms.values()[0]

    # 버전 체크로 지원가능하지 확인
    result, version_res = myvnfm.get_vnfm_version()
    if result < 0:
        log.error("Failed to get vnfm version %s %s" % (result, version_res))
        return result, version_res
    else:
        if version_res["kind"] == "NEW":
            pass
        else:
            return 200, -1

    # 1. 배포된 이미지 정보 요청 : VNFM-IMG-1
    result, deploy_img_data = myvnfm.get_deployed_images()
    if result < 0:
        log.error("Failed to get deployed images %s %s" % (result, deploy_img_data))
        return result, deploy_img_data
    # log.debug("__________ 배포된 이미지 정보 요청 : VNFM-IMG-1 : %s %s" % (result, deploy_img_data))

    # 2. 배포테이블 조회
    result, vnfimage_r = orch_dbm.get_server_vnfimage(mydb, {"serverseq":serverseq})
    # log.debug("__________ get_server_vnfimage : %s %s" % (result, vnfimage_r))
    if result < 0:
        log.error("Failed to get tb_server_vnfimage record")
        return result, vnfimage_r


    # 2. 서버에는 존재하지만, 배포테이블에는 없는 항목을 찾는다.
    if deploy_img_data is not None and "images" in deploy_img_data:

        # 배포테이블에 있는데 서버에 없는 항목은 삭제한다.
        is_del = False
        for vnfimage in vnfimage_r:
            for img_dict in deploy_img_data["images"]:
                if "location" in img_dict and img_dict["location"] == vnfimage["location"]:
                    break
            else:
                # 배포테이블에서 제거한다.
                result, delete_data = orch_dbm.delete_server_vnfimage(mydb, {"vnfimageseq":vnfimage["vnfimageseq"]})
                log.debug("__________ delete_server_vnfimage : %s" % vnfimage)

                result, delete_data = orch_dbm.delete_vim_image_filters(mydb, {"imageseq":vnfimage["vnfimageseq"]})
                log.debug("__________ delete_vim_image_filters : deleted count = %s" % result)

                sync_count += 1
                is_del = True

        if is_del:
            # 삭제된 항목이 있어서 다시 조회
            result, vnfimage_r = orch_dbm.get_server_vnfimage(mydb, {"serverseq":serverseq})
            log.debug("__________ SEARCH AGAIN : get_server_vnfimage : %s %s" % (result, vnfimage_r))
            if result < 0:
                log.error("Failed to get tb_server_vnfimage record")
                return result, vnfimage_r

        for img_dict in deploy_img_data["images"]:
            if "location" in img_dict:
                for vnfimage in vnfimage_r:
                    if img_dict["location"] == vnfimage["location"]:

                        # 양쪽에 모두 존재하는 이미지...
                        # 배포테이블의 상태값과 배포정보의 status가 일치하는지 확인
                        status_tmp = img_dict["status"]
                        dp_status = vnfimage["status"]

                        # true__true 이면 N__COMPLETE
                        # true__false 이면 E__ERROR-VIM
                        if status_tmp == "true__true":
                            if dp_status != ImageStatus.COMPLETE:
                                result, reg_data = _regist_vim_image(mydb, img_dict, serverseq, vnfimage["vnfimageseq"], vnfimage["name"])
                                if result < 0:
                                    return result, reg_data

                                vnfimage["status"] = ImageStatus.COMPLETE
                                result_u, data_u = orch_dbm.update_server_vnfimage(mydb, vnfimage)
                                if result_u < 0:
                                    log.error("Failed to update server_vnfimage : %s %s" % (result_u, data_u))

                                sync_count += 1

                        elif status_tmp == "true__false":
                            if dp_status != ImageStatus.ERROR_VIM:

                                vnfimage["status"] = ImageStatus.ERROR_VIM
                                result_u, data_u = orch_dbm.update_server_vnfimage(mydb, vnfimage)
                                if result_u < 0:
                                    log.error("Failed to update server_vnfimage : %s %s" % (result_u, data_u))

                                result, delete_data = orch_dbm.delete_vim_image_filters(mydb, {"imageseq":vnfimage["vnfimageseq"]})
                                log.debug("__________ delete_vim_image_filters : deleted count = %s" % result)

                                sync_count += 1
                        break
                else:
                    # tb_server_vnfimage에 존재하지 않는 배포이미지
                    # 해당 이미지가 등록테이블(tb_vdud_image)에 존재한다면 현행화 대상이다.
                    # vnfd image 정보 조회
                    result, img_r = orch_dbm.get_vnfd_vdu_image(mydb, {"location" : img_dict["location"]})
                    if result < 0:
                        log.error("Failed to get tb_vdud_image record : location = %s" % img_dict["location"])
                        return result, img_r
                    elif result == 0:
                        # 등록테이블에 존재하지 않는 이미지가 One-Box 에 배포된 경우
                        log.debug("__________SKIP:  No data in deploy/regist table : location = %s" % img_dict["location"])
                    else:
                        # 현행화 대상
                        reg_img = img_r[0]

                        # 3. 배포테이블에 저장 : 상태는 완료로...
                        # serverseq, status,
                        reg_img["status"] = ImageStatus.COMPLETE
                        reg_img["serverseq"] = serverseq
                        result, vnfimageseq = orch_dbm.insert_server_vnfimage(mydb, reg_img)
                        if result < 0:
                            log.error("Failed to insert server_vnfimage : %s %s" % (result, vnfimageseq))
                            return result, vnfimageseq
                        log.debug("__________ 현행화 - tb_server_vnfimage 에 배포정보 저장 : %s %s" % (result, vnfimageseq))

                        # 4. vim 등록 처리
                        status_val = img_dict.get("status")
                        log.debug("__________ status_val = %s" % status_val)
                        if status_val == "true__true":
                            result, reg_data = _regist_vim_image(mydb, img_dict, serverseq, vnfimageseq, reg_img["name"])
                            if result < 0:
                                return result, reg_data
                        else:
                            # status_val 이 true_false 인 경우는 상태값이 ERROR_VIM 가 되어야 한다.
                            reg_img["status"] = ImageStatus.ERROR_VIM
                            result_u, data_u = orch_dbm.update_server_vnfimage(mydb, reg_img)
                            if result_u < 0:
                                log.error("Failed to update server_vnfimage : %s %s" % (result_u, data_u))

                        sync_count += 1
    log.debug("__________ VNF Images SYNC FINISHED : %d" % sync_count)
    return 200, sync_count


def _regist_vim_image(mydb, img_dict, serverseq, vnfimageseq, vimimagename):
    # tb_vim 조회 : vimseq
    result, vim_r = orch_dbm.get_vim_serverseq(mydb, serverseq)
    if result <= 0:
        log.error("Failed to get vim record , serverseq = %s : %s" % (serverseq, vim_r))
        return -500, "Failed to get vim record , serverseq = %s : %s" % (serverseq, vim_r)

    # tb_vim_image 에 이미 등록되있는지 중복체크
    result, vim_image_r = orch_dbm.get_vim_images(mydb, vim_r[0]["vimseq"])
    if result < 0:
        log.error("Failed to get vim_image record, %s %s" % (result, vim_image_r))
        return result, vim_image_r

    for vim_image in vim_image_r:
        if vim_image["uuid"] == img_dict["vim_image"]["uuid"]:
            # 이미 존재
            log.debug("__________ tb_vim_image 에 이미 데이타 존재 : %s, %s" % (vim_r[0]["vimseq"], img_dict["vim_image"]["uuid"]))
            break
    else:
        # tb_vim_image에 vim정보 저장
        vim_image_data = {"vimseq":vim_r[0]["vimseq"], "vimimagename":vimimagename}
        vim_image_data["uuid"] = img_dict["vim_image"]["uuid"]
        vim_image_data["imageseq"] = vnfimageseq
        vim_image_data["createdyn"] = False

        result, vimimageseq = orch_dbm.insert_vim_image(mydb, vim_image_data)
        if result < 0:
            log.error("Failed to insert vim_image record : %s %s" % (result, vimimageseq))
            return result, vimimageseq
        log.debug("__________ tb_vim_image에 vim정보 저장 : %s %s" % (result, vimimageseq))

    return 200, "OK"


def set_paramters_of_wan(vnf_name_list_utm, parameters, wan_list):

    for vnf_name in vnf_name_list_utm:

        for param in parameters:
            if param["name"].find("redFixedIp") >= 0 and param["name"].find(vnf_name) >= 0:
                r_kind = _find_r_kind(param["name"])
                for wan in wan_list:
                    if r_kind == wan["name"]:
                        if wan["public_ip"] != "NA":
                            param["value"] = wan["public_ip"]
                            break

            elif param["name"].find("redSubnet") >= 0 and param["name"].find(vnf_name) >= 0:
                r_kind = _find_r_kind(param["name"])
                for wan in wan_list:
                    if r_kind == wan["name"]:
                        if wan["public_ip"] != "NA" and wan["public_cidr_prefix"] != -1:
                            cidr_prefix = wan["public_cidr_prefix"]
                            temp_ip_info = netaddr.IPNetwork(wan["public_ip"] + "/" + str(cidr_prefix))
                            param['value'] = str(temp_ip_info.network) + "/" + str(cidr_prefix)
                            break

            elif param["name"].find("redFixedMac") >= 0 and param["name"].find(vnf_name) >= 0:
                r_kind = _find_r_kind(param["name"])
                for wan in wan_list:
                    if r_kind == wan["name"]:
                        param["value"] = wan["mac"]
                        break

            elif param["name"].find("redType") >= 0 and param["name"].find(vnf_name) >= 0:
                r_kind = _find_r_kind(param["name"])
                for wan in wan_list:
                    if r_kind == wan["name"]:
                        param["value"] = wan["ipalloc_mode_public"]
                        break

            elif param["name"].find("defaultGw") >= 0 and param["name"].find(vnf_name) >= 0:
                r_kind = _find_r_kind(param["name"])
                for wan in wan_list:
                    if r_kind == wan["name"]:
                        if wan["public_gw_ip"] != "NA":
                            param["value"] = wan["public_gw_ip"]
                            break

            elif param["name"].find("redCIDR") >= 0 and param["name"].find(vnf_name) >= 0:
                r_kind = _find_r_kind(param["name"])
                for wan in wan_list:
                    if r_kind == wan["name"]:
                        if wan["public_cidr_prefix"] != -1:
                            param["value"] = wan["public_cidr_prefix"]
                            break

    iparm_result, iparm_content = compose_nsr_internal_params(vnf_name_list_utm, parameters)
    if iparm_result < 0:
        log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
        raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))


def check_chg_port(mydb, serverseq, nw_list_old, nw_list_new=None):

    if nw_list_new is None:
        result, nw_list_new = orch_dbm.get_onebox_nw_serverseq(mydb, serverseq)
        if result < 0:
            log.error("Failed to get onebox network info.")
            return result, nw_list_new

    chg_port_dict = {}
    chg_port_dict['change_info'] = []

    for nw_new in nw_list_new:
        for idx in range(len(nw_list_old)-1, -1, -1):
        # for nw_old in nw_list_old:
            nw_old = nw_list_old[idx]
            if nw_new["name"] == nw_old["name"]:
                if nw_new["display_name"] != nw_old["display_name"]:
                    chg_port = {"svrseq":serverseq}
                    chg_port["before_lan"] = nw_old["display_name"]
                    chg_port["before_eth"] = nw_old["name"]
                    chg_port["after_lan"] = nw_new["display_name"]
                    chg_port["after_eth"] = nw_new["name"]
                    chg_port_dict["change_info"].append(chg_port)
                    del nw_list_old[idx]
                    break
                else:
                    del nw_list_old[idx]
                    break
        else:
            chg_port = {"svrseq":serverseq}
            chg_port["before_lan"] = ""
            chg_port["before_eth"] = ""
            chg_port["after_lan"] = nw_new["display_name"]
            chg_port["after_eth"] = nw_new["name"]
            chg_port_dict["change_info"].append(chg_port)

    # log.debug("_____ 1. chg_port_dict['change_info'] : %s" % chg_port_dict["change_info"])
    # nw_list_old 에서 제거되고 남은 데이타는 삭제된 포트.
    for nw_old in nw_list_old:
        chg_port = {"svrseq":serverseq}
        chg_port["before_lan"] = nw_old["display_name"]
        chg_port["before_eth"] = nw_old["name"]
        chg_port["after_lan"] = ""
        chg_port["after_eth"] = ""
        chg_port_dict["change_info"].append(chg_port)
    # log.debug("_____ 2. chg_port_dict['change_info'] : %s" % chg_port_dict["change_info"])

    return len(chg_port_dict['change_info']), chg_port_dict


def clean_parameters(parameters, wan_dels):
    """
    tb_nscatalog_param에서 조회한 Parameter정보 중 사용하지 않는 WAN의 Param 제거
    :param parameters: tb_nscatalog_param에서 조회한 Parameter 목록
    :param wan_dels: 사용하지 않는 WAN 리스트
    :return: 정리된 Parameter 목록
    """
    # RPARM_redFixedIpR1_KT-VNF
    # RPARM_redFixedMacR1_KT-VNF
    # RPARM_redSubnetR1_KT-VNF
    # CPARM_redCIDRR1_KT-VNF
    # CPARM_redTypeR1_KT-VNF
    # CPARM_defaultGwR1_KT-VNF
    # IPARM_redNetmaskR1_KT-VNF
    # IPARM_redBroadcastR1_KT-VNF

    PARAM_TEMPLATE = ["RPARM_redFixedIp", "RPARM_redFixedMac", "RPARM_redSubnet"
                    , "CPARM_redCIDR", "CPARM_redType", "CPARM_defaultGw"
                    , "IPARM_redNetmask", "IPARM_redBroadcast"]

    size = len(parameters)
    for idx in range(size-1, -1, -1):
        param_name = parameters[idx]["name"]
        is_deleted = False
        for wr in wan_dels:
            for tmp in PARAM_TEMPLATE:
                if param_name.find(tmp + wr) >= 0:
                    log.debug("_____ Clean Parameter : %s" % param_name)
                    del parameters[idx]
                    is_deleted = True
                    break
            if is_deleted:
                break

    return parameters

def store_rlt_data(mydb, rlt_dict):

    result, rltseq = orch_dbm.insert_rlt_data(mydb, rlt_dict)
    if result < 0:
        log.error("failed to DB Insert RLT: %d %s" %(result, rltseq))
    else:
        rlt_dict['rltseq'] = rltseq

    return result, rltseq


def router_check(server_info, public_ip_dcp):
    if _private_ip_check(server_info.get('public_ip')) == -1:
        old_public_ip = server_info.get('public_ip')

        # log.debug('origin data = %s' % str(http_content['obagent']['base_url']))

        server_info['public_ip'] = public_ip_dcp
        server_info['mgmt_ip'] = public_ip_dcp

        obagent_base_url = server_info['obagent']['base_url']
        server_info['obagent']['base_url'] = obagent_base_url.replace(old_public_ip, public_ip_dcp)

        # log.debug('replace origin data = %s' %str(http_content['obagent']['base_url']))

        vnfm_base_url = server_info['vnfm']['base_url']
        server_info['vnfm']['base_url'] = vnfm_base_url.replace(old_public_ip, public_ip_dcp)

        vim_auth_url = server_info['vim']['vim_authurl']
        server_info['vim']['vim_authurl'] = vim_auth_url.replace(old_public_ip, public_ip_dcp)

    return 200, server_info


def _private_ip_check(public_ip):
    check_public_ip = public_ip.split('.')
    check_ip = str(check_public_ip[0])

    # log.debug('public_ip = %s, check_ip = %s' %(str(public_ip), str(check_ip)))
    # log.debug(type(check_ip))

    ip_arr = ['192', '172', '10']

    for ipa in ip_arr:
        if check_ip != ipa:
            continue

        log.debug('check_ip : %s' %str(ipa))
        return -1

    return 200

# backup scheduler 자동 삭제 : code = 'NS' or 'ONEBOX', seq = nsseq or serverseq
def _delete_backup_scheduler(mydb, code='NS', seq=None):
    # 호출 : ns삭제 실행 or OneBox 삭제 준공 시

    del_dict = {}
    del_dict['category'] = code
    del_dict['categoryseq'] = seq

    result, data = orch_dbm.delete_backup_scheduler(mydb, del_dict)
    if result < 0:
        log.debug('backup scheduler 삭제 실패 : %s' %str(code))
    else:
        log.debug('backup scheduler 삭제 성공 : %s' %str(code))

    return result, data


