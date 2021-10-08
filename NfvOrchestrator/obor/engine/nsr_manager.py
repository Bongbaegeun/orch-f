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
import sys
import copy
import time

import db.orch_db_manager as orch_dbm
import utils.log_manager as log_manager
from db.orch_db import HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found
from engine.action_status import ACTStatus
from engine.descriptor_manager import new_nsd_with_vnfs
from engine.license_manager import get_license_available, take_license, update_license
from engine.nfr_status import NFRStatus
from engine.nsr_status import NSRStatus
from engine.server_status import SRVStatus
from engine.action_type import ActionType
from engine.vim_manager import get_vim_connector
from utils.e2e_logger import CONST_TRESULT_SUCC, CONST_TRESULT_FAIL

log = log_manager.LogManager.get_instance()
import common_manager

global global_config

def _check_server_provavailable(server_dict):
    if server_dict['status'] != SRVStatus.RDS:
        log.error("_check_server_provavailable() The One-Box server is not ready yet: %s" % server_dict['status'])
        return -HTTP_Bad_Request, "The One-Box server is not ready"

    if server_dict['nsseq']:
        log.error("_check_server_provavailable() The customer already has a NS: %s" % str(server_dict['nsseq']))
        return -HTTP_Bad_Request, "The customer already has a NS: %s" % str(server_dict['nsseq'])

    return 200, "OK"

def new_nsr_check_customer(mydb, customer_id, onebox_id=None, check_server=True):
    result, customer_dict = orch_dbm.get_customer_id(mydb, customer_id)

    if result < 0:
        log.error("[Provisioning][NS]  : Error, failed to get customer info from DB %d %s" % (result, customer_dict))
        return -HTTP_Internal_Server_Error, "Failed to get Customer Info. from DB: %d %s" % (result, customer_dict)
    elif result == 0:
        log.error("[Provisioning][NS]  : Error, Customer Not Found")
        return -HTTP_Not_Found, "Failed to get Customer Info. from DB: Customer not found"

    result, customer_inventory = orch_dbm.get_customer_resources(mydb, customer_id, onebox_id)
    if result <= 0:
        log.error("[Provisioning][NS]  : Error, failed to get resource info of the customer %s" % (str(customer_id)))
        return -HTTP_Internal_Server_Error, "failed to get resource info of the customer %s" % (str(customer_id))

    for item in customer_inventory:
        if item['resource_type'] == 'vim':
            customer_dict['vim_id'] = item['vimseq']

        if item['resource_type'] == 'server':
            log.debug("[Provisioning][NS] server info = %s" % str(item))

            customer_dict['server_id'] = item['serverseq']
            customer_dict['server_org'] = item.get('orgnamescode')
            if check_server:
                server_check_result, server_check_msg = _check_server_provavailable(item)

                if server_check_result < 0:
                    return -HTTP_Bad_Request, "Cannot perform provisioning with the server: %d %s" % (server_check_result, server_check_msg)

    if customer_dict.get('vim_id') is None:
        log.error("[Provisioning][NS]  : Error, VIM Not Found for the Customer %s" % str(customer_id))
        return -HTTP_Internal_Server_Error, "Failed to get VIM Info."

    return 200, customer_dict

def new_nsr_check_license(mydb, vnf_list):
    global global_config
    if not global_config.get("license_mngt", False):
        return 200, "OK"

    for vnf in vnf_list:
        result, license_info = get_license_available(mydb, vnf.get('license_name'))
        if result <= 0:
            log.warning("Failed to get VNF License for %s %s" % (vnf['name'], vnf['license_name']))
            # TEMP
            # vnf['license'] = af.create_uuid()
            return -HTTP_Internal_Server_Error, "Failed to get VNF License for %s %s" % (vnf['name'], vnf['license_name'])
        else:
            vnf['license'] = license_info['value']
            result, data = take_license(mydb, license_info)
            log.debug("The Result of taking a license: %d %s" % (result, str(data)))

        log.debug("VNF %s uses the license %s" % (vnf['name'], vnf['license']))

    return 200, "OK"


def new_nsr_vnf_proc(rlt_dict):

    CONST_APP_ACCID = "APARM_appid"
    CONST_APP_ACCID_NONE = "-"

    for vnf in rlt_dict['vnfs']:
        if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            log.debug("[HJC] Skip composing web URL for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))

            vnf['deploy_info'] = "GiGA Office"

            for vm in vnf['vdus']:
                web_url_fullpath = None
                web_url_type = None
                web_url_config = vm.get('web_url')
                log.debug("Web URL Config: %s" % str(web_url_config))

                if web_url_config:
                    try:
                        web_url_ip = web_url_config.get('ip_addr', "NotGiven")
                        log.debug("[HJC] Web URL IP Addr = %s" % str(web_url_ip))

                        # TODO: check web_url_ip is valid IP address (ver 4)
                        if web_url_ip == 'NotGiven':
                            log.debug("Web URL: Cannot compose URL Full Path because get a valid IP Address")
                            continue

                        web_url_fullpath = web_url_config['protocol'] + "://" + web_url_ip
                        if web_url_config.get('port') is not None and web_url_config['port'] > 0:
                            web_url_fullpath += ":" + str(web_url_config['port'])
                        if web_url_config.get('resource', "NotGiven") != "NotGiven":
                            web_url_fullpath += web_url_config['resource']

                        web_url_type = web_url_config.get('type', "main")
                    except KeyError as e:
                        log.exception("Error while composing VDU Web URL. KeyError: " + str(e))
                        web_url_fullpath = None
                if web_url_fullpath:
                    log.debug("Web URL Full Path: %s" % web_url_fullpath)
                    vm['weburl'] = web_url_fullpath
                    if web_url_type == 'main':
                        vnf['weburl'] = web_url_fullpath
        else:
            vnf['deploy_info'] = "GiGA One-Box"
            # web account id from parameter value
            vnf['webaccount'] = vnf.get('app_id', CONST_APP_ACCID_NONE)
            #log.debug("[HJC] Web Account ID: %s" % str(vnf['webaccount']))

            if vnf['webaccount'] == CONST_APP_ACCID_NONE:
                #log.debug("[HJC] get Web Account ID from parameter value")
                for param in rlt_dict['parameters']:
                    target_param_name = CONST_APP_ACCID + "_" + vnf['name']
                    if param['name'] == target_param_name:
                        vnf['webaccount'] = param.get('value', CONST_APP_ACCID_NONE)
                        #log.debug("[HJC] Web Account ID from parameter value %s" % vnf['webaccount'])
                        break

            for vm in vnf['vdus']:
                web_url_fullpath = None
                web_url_type = None
                web_url_config = vm.get('web_url')
                log.debug("Web URL Config: %s" % str(web_url_config))

                if web_url_config:
                    try:
                        web_url_ip = web_url_config.get('ip_addr', "NotGiven")
                        if web_url_ip == 'NotGiven':
                            log.debug("Web URL: Cannot compose URL Full Path because IP Address is NotGiven")
                            continue
                        elif web_url_ip.find("PARM_") >= 0 or web_url_ip.find("ROUT_") >= 0:
                            for param in rlt_dict['parameters']:
                                if param['name'].find(web_url_ip) >= 0:
                                    web_url_ip = param['value']
                                    break
                        elif web_url_ip.find("PORT_") >= 0:
                            #log.debug("[HJC] get web url ip from CP of %s" % str(web_url_ip))
                            if 'cps' in vm:
                                for cp in vm['cps']:
                                    if cp['name'] == web_url_ip:
                                        web_url_ip = cp['ip']
                                        log.debug("[HJC] web_url_ip = %s" % str(web_url_ip))
                                        break
                        else:
                            log.debug("Web URL IP Addr = %s" % str(web_url_ip))

                        # TODO: check web_url_ip is valid IP address (ver 4)
                        if web_url_ip == 'NotGiven':
                            log.debug("Web URL: Cannot compose URL Full Path because get a valid IP Address")
                            continue

                        web_url_fullpath = web_url_config['protocol'] + "://" + web_url_ip + ":" + str(web_url_config['port'])
                        if web_url_config.get('resource', "NotGiven") != "NotGiven":
                            web_url_fullpath += web_url_config['resource']

                        web_url_type = web_url_config.get('type', "main")
                    except KeyError as e:
                        log.exception("Error while composing VDU Web URL. KeyError: " + str(e))
                        web_url_fullpath = None
                if web_url_fullpath:
                    log.debug("Web URL Full Path: %s" % web_url_fullpath)
                    vm['weburl'] = web_url_fullpath
                    if web_url_type == 'main':
                        vnf['weburl'] = web_url_fullpath

        if 'report' in vnf:
            for report in vnf['report']:
                log.debug("[HJC] VNF Name: %s, Report: %s" % (vnf['name'], str(report)))
                report['value'] = report['data_provider']
                if report['data_provider'].find("PARM_") >= 0:
                    for param in rlt_dict['parameters']:
                        if param['name'] == report['data_provider']:
                            log.debug("[HJC] %s'value found: %s" % (report['data_provider'], param['value']))
                            report['value'] = param['value']
                            break

        if 'ui_action' in vnf:
            for action in vnf['ui_action']:
                log.debug("[HJC] VNF Name: %s, UI_Action: %s" % (vnf['name'], str(action)))

    return 200, "OK"


def new_nsr_db_proc(mydb, rlt_dict, instance_scenario_name, instance_scenario_description):

    result, instance_id = orch_dbm.insert_nsr_as_a_whole(mydb, instance_scenario_name, instance_scenario_description, rlt_dict)

    if result < 0:
        log.error("[Provisioning][NS]  : Error, failed to insert DB records %d %s" % (result, instance_id))
        # error_txt = "recordingDB", "Failed to insert DB Records %d %s" %(result, str(instance_id))

        return result, instance_id

    # update license info
    global global_config
    if global_config.get("license_mngt", False):
        for vnf in rlt_dict['vnfs']:
            if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
                log.debug("[HJC] Skip composing web URL for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
                continue

            license_update_info = {'nfseq': vnf['nfseq']}
            log.debug("[HJC] update license %s with nfseq %s" % (vnf.get('license'), str(license_update_info)))
            update_license(mydb, vnf.get('license'), license_update_info)

    # calculate internal parameter values
    #vnf_list = []
    #for vnf in rlt_dict['vnfs']:
    #    vnf_list.append(vnf['name'])

    #iparm_result, iparm_content = _compose_nsr_internal_params(vnf_list, rlt_dict['parameters'])
    #if iparm_result < 0:
    #    log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
    #    return iparm_result, "Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content)

    rlt_dict['nsseq'] = instance_id
    orch_dbm.insert_nsr_params(mydb, rlt_dict['nsseq'], rlt_dict['parameters'])

    return 200, instance_id


def update_nsr_status(mydb, action_type, action_dict=None, action_status=None, nsr_data=None, nsr_status=None, server_dict=None, server_status=None,
                       nsr_status_description=None):
    try:
        if action_dict and action_status:
            action_dict['status'] = action_status
            if action_status == ACTStatus.FAIL or action_status == ACTStatus.SUCC:
                action_dict['action'] = action_type + "E"
            else:
                action_dict['action'] = action_type + "S"

            orch_dbm.insert_action_history(mydb, action_dict)

        if nsr_data and nsr_status:
            nsr_data['status'] = nsr_status
            if nsr_status == NSRStatus.ERR or nsr_status == NSRStatus.RUN:
                nsr_data['action'] = action_type + "E"
            else:
                nsr_data['action'] = action_type + "S"

            nsr_data['status_description'] = "Action: %s, Result: %s" % (action_type, nsr_status)
            if nsr_status_description:
                nsr_data['status_description'] += ", Cause: " + nsr_status_description

            orch_dbm.update_nsr(mydb, nsr_data)
            try:
                if action_type == "R":
                    if nsr_status == NSRStatus.ERR or nsr_status == NSRStatus.RUN or nsr_status == NSRStatus.RST or nsr_status == NSRStatus.BAC:
                        if nsr_status == NSRStatus.RST:
                            nsr_status = NFRStatus.RST_waiting
                        elif nsr_status == NSRStatus.BAC:
                            nsr_status = NFRStatus.BAC_waiting

                        for vnf_data in nsr_data['vnfs']:
                            vnf_data['status'] = nsr_status
                            if nsr_status == NSRStatus.ERR or nsr_status == NSRStatus.RUN:
                                vnf_data['action'] = action_type + "E"
                            else:
                                vnf_data['action'] = action_type + "S"

                            vnf_data['status_description'] = "Action: %s, Result: %s" % (action_type, nsr_status)
                            orch_dbm.update_nsr_vnf(mydb, vnf_data)
            except Exception, e:
                log.exception("Exception: %s" % str(e))

        if server_dict and server_status:
            server_dict['status'] = server_status
            common_manager.update_server_status(mydb, server_dict)

    except Exception, e:
        log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))

    return 200, "OK"


def start_nsr_monitoring(mydb, server_id, nsr_dict, e2e_log=None):
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
        if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            log.debug("[HJC] Skip starting monitoring for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
            continue

        vnf_app_id = None
        vnf_app_passwd = None

        for param in nsr_dict['parameters']:

            if param['name'].find("appid_" + vnf['name']) >= 0:
                log.debug("start_nsr_monitoring() appid param = %s %s" % (param['name'], param['value']))
                vnf_app_id = param['value']

            if param['name'].find("apppasswd_" + vnf['name']) >= 0:
                log.debug("start_nsr_monitoring() apppasswd param = %s %s" % (param['name'], param['value']))
                vnf_app_passwd = param['value']

        for vm in vnf['vdus']:

            target_vm = {'vm_name': vm['name'], 'vdud_id': vm['vdudseq'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid']
                , 'monitor_target_seq': vm['monitor_target_seq'], 'vm_id': vm['vm_access_id'], 'vm_passwd': vm['vm_access_passwd']}

            target_vm['service_number'] = vnf.get('service_number')

            if vnf_app_id:
                target_vm['vm_app_id'] = vnf_app_id
            if vnf_app_passwd:
                target_vm['vm_app_passwd'] = vnf_app_passwd

            target_cps = []
            if 'cps' in vm:
                for cp in vm['cps']:
                    target_cp = {'cp_name': cp['name'], 'cp_vim_name': cp['vim_name'], 'cp_vim_uuid': cp['uuid'], 'cp_ip': cp['ip']}
                    target_cps.append(target_cp)

            target_vm['vm_cps'] = target_cps

            target_vm['nfsubcategory'] = vnf['nfsubcategory']

            target_vms.append(target_vm)

    target_dict['vms'] = target_vms

    result, data = monitor.start_monitor_nsr(target_dict, e2e_log)

    if result < 0:
        log.error("start_nsr_monitoring(): error %d %s" % (result, data))

    return result, data


def new_nsr_start_monitor(mydb, rlt_dict, server_id, e2e_log):
    for vnf in rlt_dict['vnfs']:
        if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            log.debug("[HJC] Skip starting monitoring for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
            continue

    return start_nsr_monitoring(mydb, server_id, rlt_dict, e2e_log)


def handle_default_nsr(mydb, customer_id, onebox_id, default_ns_id, server_dict=None, tid=None, tpath=""):
    e2e_log = None

    try:
        log_info_message = "Handling Default NS for %s in %s)" % (default_ns_id, onebox_id)
        log.info(log_info_message.center(80, '='))
        #try:
        #    if not tid:
        #        e2e_log = e2elogger(tname='Handling Default NS', tmodule='orch-f', tpath="orch_ns-prov")
        #    else:
        #        e2e_log = e2elogger(tname='Handling Default NS', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_ns-prov")
        #except Exception, e:
        #    log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
        #    e2e_log = None

        if e2e_log:
            e2e_log.job('Handling Default NS Started', CONST_TRESULT_SUCC,
                        tmsg_body="One-Box ID: %s\nDefault NS ID: %s" % (str(onebox_id), default_ns_id))

        # Step 1. Check Customer Info.
        log.debug("[Default NS] 1. Check Customer and Get VIM ID")
        result, customer_dict = new_nsr_check_customer(mydb, customer_id, onebox_id, check_server=False)
        if result < 0:
            raise Exception("Customer is not ready to provision: %d %s" % (result, customer_dict))

        log.debug("[Default NS] 1. Check Customer and Get VIM ID ------> OK\n _______customer_dict=%s" %str(customer_dict))
        if e2e_log:
            e2e_log.job("Check Customer Info", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 2. Get Default NS Info from One-Box VNFM with default_ns_id
        log.debug("[Default NS] 2. Get Default NS Info. from One-Box VNFM")
        defaul_nsr_dict = {}

        result, vnfms = common_manager.get_ktvnfm(mydb, customer_dict['server_id'])
        if result < 0:
            log.error("Failed to establish a vnfm connection")
            return -HTTP_Not_Found, "No KT VNFM Found"
        elif result > 1:
            log.error("Error, Several vnfms available, must be identify")
            return -HTTP_Bad_Request, "Several vnfms available, must be identify"
        myvnfm = vnfms.values()[0]

        result, content = myvnfm.get_default_ns_info(default_ns_id)
        if result < 0:
            log.error("Failed to get Default NS Info from One-Box VNFM: %d, %s" %(result, str(content)))
            return result, content
            # raise Exception("Failed to get Default NS Info from One-Box VNFM: %d, %s" %(result, str(content)))
        else:
            #defaul_nsr_dict = yaml.safe_load(content['default_nsr'])
            defaul_nsr_dict = content['default_nsr']
        log.debug("[Default NS] 2. Get Default NS Info. from One-Box VNFM -------> OK")
        log.debug("[Default NS] 2. Get Default NS Info = %s" %str(defaul_nsr_dict))

        # publicip, mgmtip 가 변경되었을 경우 현행화처리한다.
        if server_dict is not None:
            publicip = server_dict.get("publicip", None)
            mgmtip = server_dict.get("mgmtip", None)
            wan_list = server_dict.get("wan_list", None)

            for d_vm in defaul_nsr_dict['vnf']['vdus']:

                # mgmtip
                if mgmtip is not None:
                    if mgmtip != d_vm["mgmtip"]:
                        log.debug("__________ [Default NS] mgmtip 변경처리 old : %s, new : %s " % (d_vm["mgmtip"], mgmtip))
                        d_vm["mgmtip"] = mgmtip

                    # for d_cp in d_vm["cps"]:
                    #     if d_cp["name"].find("PORT_mgmt") >= 0:
                    #         if d_cp["ip"] != mgmtip:
                    #             log.debug("__________ [Default NS] %s ip 변경처리 old : %s, new : %s " % (d_cp["name"], d_cp["ip"], mgmtip))
                    #             d_cp["ip"] = mgmtip
                    #             break

                # publicip
                if wan_list:
                    for wan in wan_list:
                        r_gubun = wan["name"]
                        if r_gubun == "R0":
                            r_gubun = "_"
                        # cps 에서 처리
                        for d_cp in d_vm["cps"]:
                            if d_cp["name"].find("PORT_red" + r_gubun) >= 0:
                                if d_cp["ip"] != wan["public_ip"]:
                                    log.debug("__________ [Default NS] %s ip 변경처리 old : %s, new : %s " % (d_cp["name"], d_cp["ip"], wan["public_ip"]))
                                    d_cp["ip"] = wan["public_ip"]
                                    break

                        # parameters 에서 처리
                        for d_param in defaul_nsr_dict["parameters"]:
                            if d_param["name"].find("RPARM_redFixedIp" + r_gubun) >= 0:
                                if d_param["value"] != wan["public_ip"]:
                                    log.debug("__________ [Default NS] %s value 변경처리 old : %s, new : %s " % (d_param["name"], d_param["value"], wan["public_ip"]))
                                    d_param["value"] = wan["public_ip"]
                                    break
                elif publicip is not None:
                    log.debug("__________ [Default NS] public ip 변경로직 : wan_list 정보 없는경우 ")
                    for d_cp in d_vm["cps"]:
                        if d_cp["name"].find("PORT_red_") >= 0:
                            if d_cp["ip"] != publicip:
                                log.debug("__________ [Default NS] %s ip 변경처리 old : %s, new : %s " % (d_cp["name"], d_cp["ip"], publicip))
                                d_cp["ip"] = publicip
                                break

                    for d_param in defaul_nsr_dict["parameters"]:
                        if d_param["name"].find("RPARM_redFixedIp_") >= 0:
                            if d_param["value"] != publicip:
                                log.debug("__________ [Default NS] %s value 변경처리 old : %s, new : %s " % (d_param["name"], d_param["value"], publicip))
                                d_param["value"] = publicip
                                break


        # Step 2. Check NS and Params
        log.debug("[Default NS] 3. Check Scenario (NS) Templates")

        log.debug("vnf-name: %s, type = %s" % (defaul_nsr_dict['vnf']['name'], str(type(defaul_nsr_dict['vnf']['name']))))
        result, content = orch_dbm.get_vnfd_general_info_with_name(mydb, {"vnfd_name": defaul_nsr_dict['vnf']['name'], "vnfd_version": defaul_nsr_dict['vnf']['version']})

        if result < 0:
            log.error("failed to get VNFD:  %d %s" %(result, content))
            raise Exception("failed to get VNFD: %d %s" %(result, content))

        vnf_list=[{"vnfd_name": defaul_nsr_dict['vnf']['name'], "vnfd_version": str(defaul_nsr_dict['vnf']['version'])}]
        result, nsd_id = new_nsd_with_vnfs(mydb, vnf_list, customer_eng_name = "DefaultNSD")
        if result < 0:
            log.error("failed to get NSD: %d %s" %(result, nsd_id))
            raise Exception("failed to get NSD: %d %s" %(result, nsd_id))

        result, scenarioDict = orch_dbm.get_nsd_id(mydb, nsd_id)
        if result < 0:
            log.error("[Default NS]  : Error, failed to get Scenario Info From DB %d %s" % (result, scenarioDict))
            raise Exception("Failed to get NSD from DB: %d %s" % (result, scenarioDict))
        elif result == 0:
            log.error("[Default NS]  : Error, No Scenario Found")
            raise Exception("Failed to get NSD from DB: NSD not found")

        log.debug("[Default NS] 3. Check Scenario (NS) Templates -------> OK")

        result, content = register_default_nsr(mydb, customer_dict, onebox_id, scenarioDict, defaul_nsr_dict, server_dict, e2e_log)

        if result < 0:
            log.error ("failed to register Default NSR Info: %d %s" %(result, content))
            raise Exception, "failed to register Default NSR Info: %d %s" %(result, content)
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -500, str(e)

    return 200, "OK"

def register_default_nsr(mydb, customer_dict, onebox_id, scenarioDict, defaul_nsr_dict, server_dict=None, e2e_log=None):

    update_server_dict = {}

    try:
        if e2e_log:
            e2e_log.job('Registering Default NS Info', CONST_TRESULT_SUCC,
                        tmsg_body="One-Box ID: %s\nDefault NS Info: %s" % (onebox_id, str(defaul_nsr_dict)))

        # check if the requested nsr already exists
        instance_scenario_name = defaul_nsr_dict.get("instance_name", "NotGiven")

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
        #     log.debug("NSR already exists")
        #     return check_result, check_data

        # 회선 이중화 관련 Parameters 정리 및 resourcetemplate 정리:
        log.debug("[Default NS] 4. Check and Clean Parameters and HOT")
        if 'parameters' in scenarioDict and (scenarioDict['parameters']) > 0:
            for param in scenarioDict['parameters']:
                for d_param in defaul_nsr_dict['parameters']:
                    if param['name'] == d_param['name']:
                        param['value'] = d_param.get('value', "none")
                        break

            wan_dels = ["R1", "R2", "R3"]
            for p in scenarioDict['parameters']:
                if p['name'].find("RPARM_redFixedMacR") >= 0:
                    for num in range(1,4,1):
                        if p['name'].find("R"+str(num)) >= 0 and p.get("value", "none").lower() != "none":
                            wan_dels.remove("R"+str(num))
                            break
            log.debug("_____ get_wan_dels : %s " % wan_dels)

            scenarioDict['parameters'] = common_manager.clean_parameters(scenarioDict['parameters'], wan_dels)
            log.debug("_____ clean_parameters END")

            if scenarioDict['resourcetemplatetype'] == "hot":
                scenarioDict['resourcetemplate'] = defaul_nsr_dict['vnf']['resourcetemplate']
                log.debug("_____ resourcetemplate after wan cleaning : %s" % scenarioDict['resourcetemplate'])
        # [skip] check_param_result, check_param_data = _new_nsr_check_param(mydb, customer_dict['vim_id'], scenarioDict['parameters'], params)
        #if check_param_result < 0:
        #    raise Exception("Invalid Parameters: %d %s" % (check_param_result, check_param_data))
        log.debug("[Default NS] 4. Check and Clean Parameters and HOT -------> OK")


        # Step 4. Check and Get Available VNF License Key
        log.debug("[Default NS] 5. Check and Get Available VNF License Key")
        check_license_result, check_license_data = new_nsr_check_license(mydb, scenarioDict['vnfs'])

        if check_license_result < 0:
            raise Exception("Failed to allocate VNF license: %d %s" % (check_license_result, check_license_data))

        log.debug("[Default NS] 5. Check and Get Available VNF License Key ------> OK")
        if e2e_log:
            e2e_log.job("Check and Get Available VNF License Key", CONST_TRESULT_SUCC, tmsg_body="VNF license : %s" % check_license_data)

        # Step 6. Review and fill missing fields for DB 'tb_nsr'
        log.debug("[Default NS] 6. DB Insert: General Info. of the requested NS")
        # Add Following Fields Before Creating RLT 1: customerseq, vimseq, vim_tenant_name
        scenarioDict['customerseq'] = customer_dict['customerseq']
        scenarioDict['vimseq'] = customer_dict['vim_id']
        scenarioDict['vim_tenant_name'] = customer_dict['tenantid']
        scenarioDict['status'] = NSRStatus.CRT

        if defaul_nsr_dict.get('description') is None:
            instance_scenario_description = scenarioDict.get('description', "No Description")
        else:
            instance_scenario_description = defaul_nsr_dict['description']

        if 'server_org' in customer_dict:
            scenarioDict['orgnamescode'] = customer_dict['server_org']


        result, nsr_id = orch_dbm.insert_nsr_general_info(mydb, instance_scenario_name, instance_scenario_description, scenarioDict)

        if result < 0:
            log.error("[Default NS]  : Error, failed to insert DB records %d %s" % (result, nsr_id))
            raise Exception("Failed to insert DB record for new NSR: %d %s" % (result, nsr_id))

        scenarioDict['nsseq'] = nsr_id
        scenarioDict['serverseq'] = customer_dict['server_id']

        update_server_dict['serverseq'] = customer_dict['server_id']
        update_server_dict['nsseq'] = nsr_id

        update_nsr_status(mydb, ActionType.PROVS, nsr_data=scenarioDict, nsr_status=NSRStatus.CRT_parsing, server_dict=update_server_dict,
                          server_status=SRVStatus.LPV)

        # RLT Composing
        log.debug("RLT Composing")
        #TODO Replace VNFD Name to VNF Name
        rlt_dict = copy.deepcopy(scenarioDict)
        rlt_dict["name"] = instance_scenario_name

        log.debug("[Default NS] 6. DB Insert: General Info. of the requested NS -------> OK")

        if e2e_log:
            e2e_log.job("Review and fill missing fields for DB 'tb_nsr'", CONST_TRESULT_SUCC, tmsg_body=None)

        # Step 7. Handle VIM Instance Info
        log.debug("[Default NS] 7. Handle VIM Instance Info")
        result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
        if result < 0:
            log.error("[Default NS] Error, failed to connect to VIM")
            raise Exception("Failed to establish a VIM connection: %d %s" % (result, vims))
        elif result > 1:
            log.error("[Default NS] Error, Several VIMs available, must be identify the target VIM")
            raise Exception("Failed to establish a VIM connection:Several VIMs available, must be identify")

        myvim = vims.values()[0]
        rlt_dict['vim_tenant_name'] = myvim['tenant']
        rlt_dict['vimseq'] = myvim['id']
        rlt_dict['uuid'] = defaul_nsr_dict['uuid']

        for vnf in rlt_dict['vnfs']:
            if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
                log.debug("[HJC] Skip getting CP Info for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
                continue

            vnf['status'] = NFRStatus.RUN
            if 'orgnamescode' in rlt_dict:
                vnf['orgnamescode'] = rlt_dict['orgnamescode']

            for vm in vnf['vdus']:
                for d_vm in defaul_nsr_dict['vnf']['vdus']:
                    if vm['name'] == d_vm['name']:
                        vm['uuid'] = d_vm['uuid']
                        vm['vim_name'] = d_vm['vim_name']
                        vm['status'] = "Active"
                        if 'orgnamescode' in rlt_dict:
                            vm['orgnamescode'] = rlt_dict['orgnamescode']
                        vm['mgmtip'] = d_vm['mgmtip']

                        if 'cps' in vm:
                            for cp in d_vm['cps']:
                                for cpd in vm['cps']:
                                    if cp['name'] == cpd['name']:
                                        cp['cpdseq'] = cpd['cpdseq']
                                        break

                            vm['cps']= d_vm['cps']
                        break
        log.debug("[Default NS] 7. Handle VIM Instance Info -------> OK")
        if e2e_log:
            e2e_log.job("Handle VIM Instance Info", CONST_TRESULT_SUCC, tmsg_body=None)
    # except Exception, e:
    #     log.exception("Exception: %s" % str(e))
    #
    #     if e2e_log:
    #         e2e_log.job('Failed to register Default NS', CONST_TRESULT_FAIL,
    #                     tmsg_body="Default NS Info: %s\nResult:Fail, Cause:%s" % (str(defaul_nsr_dict), str(e)))
    #         e2e_log.finish(CONST_TRESULT_FAIL)
    #
    #     return -HTTP_Bad_Request, "Failed to register Default NS. Cause: %s" % str(e)
    #
    # try:
        # Step 8. compose web url for each VDUs and VNF info
        log.debug("[Default NS] 8. compose web url for each VDUs and VNF info")
        vnf_proc_result, vnf_proc_data = new_nsr_vnf_proc(rlt_dict)
        if vnf_proc_result < 0:
            log.warning("Failed to process vnf app information: %d %s" % (vnf_proc_result, vnf_proc_data))

        if e2e_log:
            e2e_log.job("Compose web url for each VDUs and VNF info", CONST_TRESULT_SUCC, tmsg_body=None)
        log.debug("[Default NS] 8. compose web url for each VDUs and VNF info -------> OK")

        # Step 9. DB Insert NS Instance
        log.debug("[Default NS] 9. Insert DB Records for NS Instance")
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_processingdb)

        nsr_db_result, instance_id = new_nsr_db_proc(mydb, rlt_dict, instance_scenario_name, instance_scenario_description)

        if nsr_db_result < 0:
            error_txt = "Failed to insert DB Records %d %s" % (nsr_db_result, str(instance_id))
            log.error("[Default NS] 9. Insert DB Records for NS Instance -----> Error, %s" % error_txt)
            raise Exception(error_txt)

        log.debug("[Default NS] 9. Insert DB Records for NS Instance ------> OK")
        if e2e_log:
            e2e_log.job("DB Insert NS Instance", CONST_TRESULT_SUCC, tmsg_body="NS Instance ID : %s" % instance_id)


         # Step 10. VNF Configuration: skip
        log.debug("[Default NS] 10. VNF Configuration --------> Skip")
        #_update_nsr_status(mydb, "P", nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_configvnf)

        # Step 11. Verify NS Instance: skip
        log.debug("[Default NS] 11. Test NS Instance ---------> Skip")
        #_update_nsr_status(mydb, "P", nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_testing)

        # Step 12. Setup Monitor for the NS Instance
        log.debug("[Default NS] 12. Setup Monitor")
        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_startingmonitor)

        time.sleep(10)
        mon_result, mon_data = new_nsr_start_monitor(mydb, rlt_dict, customer_dict['server_id'], e2e_log)
        if mon_result < 0:
            log.warning("[Default NS] 12. Setup Monitor ------> Failed %d %s" % (mon_result, mon_data))
            if e2e_log:
                e2e_log.job("Setup Monitor for the NS Instance", CONST_TRESULT_FAIL, tmsg_body=None)
            raise Exception("Failed to setup Monitor for the NS Instance %d %s" % (mon_result, mon_data))
        else:
            log.debug("[Default NS] 12. Setup Monitor ------> OK")

            if e2e_log:
                e2e_log.job("Setup Monitor for the NS Instance", CONST_TRESULT_SUCC, tmsg_body=None)

        log.debug("[Default NS] 13. Insert RLT into DB")
        ur_result, ur_data = common_manager.store_rlt_data(mydb, rlt_dict)
        if ur_result < 0:
            log.error("Failed to insert rlt data: %d %s" %(ur_result, ur_data))
            raise Exception("Failed to insert rlt data: %d %s" %(ur_result, ur_data))
        log.debug("[Default NS] 13. Insert RLT into DB --------> OK")
        if e2e_log:
            e2e_log.job("RLT - DB Insert", CONST_TRESULT_SUCC, tmsg_body="rlt_dict\n%s" % (json.dumps(rlt_dict, indent=4)))

        update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.RUN, server_dict=update_server_dict, server_status=SRVStatus.INS)

        # 명시적으로 nsseq 업데이트
        server_dict_temp = {"serverseq":rlt_dict["serverseq"], "nsseq":rlt_dict["nsseq"]}
        us_result, us_data = orch_dbm.update_server(mydb, server_dict_temp)
        if us_result < 0:
            log.error("failed to update Server Info from DB: %d %s" %(us_result, us_data))
            raise Exception("failed to update Server Info from DB: %d %s" %(us_result, us_data))

        if e2e_log:
            e2e_log.job("Registering Default NS 완료", CONST_TRESULT_SUCC, tmsg_body=None)
            e2e_log.finish(CONST_TRESULT_SUCC)

        return orch_dbm.get_nsr_id(mydb, instance_id)

    except Exception, e:
        log.exception("Exception: %s" % str(e))

        # 설치 실패시 롤백처리
        if "nsseq" in scenarioDict and scenarioDict['nsseq'] is not None:
            # NS 삭제
            del_result, del_data = orch_dbm.delete_nsr(mydb, scenarioDict['nsseq'])

        if e2e_log:
            e2e_log.job('Failed to register Default NS', CONST_TRESULT_FAIL,
                        tmsg_body="Default NS Info: %s\nResult:Fail, Cause:%s" % (str(defaul_nsr_dict), str(e)))
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -HTTP_Internal_Server_Error, "Default NS 등록이 실패하였습니다. 원인: %s" % str(e)
