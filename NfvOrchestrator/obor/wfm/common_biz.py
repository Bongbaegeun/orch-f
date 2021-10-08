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
공통 BIZ 함수
공통적으로 사용되는 함수를 여기에 작성해서 코드중복을 없앤다.
"""
from engine.action_type import ActionType
import db.dba_manager as orch_dbm
from utils.config_manager import ConfigManager

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from db.orch_db import HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found
from sbpm.sbpm_connectors import odmconnector
from sbpm.sbpm_connectors import monitorconnector

def update_server_status(server_dict, is_action=False, e2e_log = None, action_type=None):
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
        os_result, os_data = orch_dbm.get_server_id(server_dict['serverseq'])
        if os_result < 0:
            log.error("failed to get Server Info from DB: %d %s" %(os_result, os_data))
            raise Exception("failed to get Server Info from DB: %d %s" %(os_result, os_data))

        # Step 2. Update Server Data in DB
        if os_data.get('status') == server_dict.get('status', None):
            # log.debug("Don't need to update Server Status: %s" %os_data.get('status'))
            return 200, os_data.get('status')

        if server_dict.get('onebox_id') is None or server_dict['onebox_id'] != os_data.get('onebox_id'):
            server_dict['onebox_id'] = os_data.get('onebox_id')

        us_result, us_data = orch_dbm.update_server_status(server_dict, is_action=is_action)
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
            myOdm = odmconnector.odmconnector({"onebox_type":"General"})
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


def get_ktmonitor():
    cfgManager = ConfigManager.get_instance()
    config = cfgManager.get_config()
    host_ip = config["monitor_ip"]
    host_port = config["monitor_port"]

    log.debug("get_ktmonitor(): Monitor IP: %s, Monitor Port: %s" % (host_ip, host_port))
    # return monitorconnector.monitorconnector(name='ktmonitor', host=host_ip, port=host_port, uuid=None, user=None, passwd=None)
    return monitorconnector.monitorconnector({"onebox_type":"General", "host":host_ip, "port":host_port})


def start_onebox_monitor(serverseq):
    monitor = get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    ob_result, ob_data = orch_dbm.get_server_id(serverseq)
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

    # vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(vim_id=None, vim_name=None, server_id=ob_data['serverseq'])
    # if vim_result <= 0:
    #     log.error("failed to get vim info of %s: %d %s" %(str(ob_data['serverseq']), vim_result, vim_content))
    #     return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
    # target_dict['vim_auth_url'] = vim_content[0]['authurl']
    # target_dict['vim_id'] = vim_content[0]['username']
    # target_dict['vim_passwd'] = vim_content[0]['password']
    # target_dict['vim_domain'] = vim_content[0]['domain']
    # target_dict['vim_typecod'] = vim_content[0]['vimtypecode']
    # target_dict['vim_version'] = vim_content[0]['version']

    # target_dict['vim_net']=[]
    # vn_result, vn_content = orch_dbm.get_vim_networks(vim_content[0]['vimseq'])
    # if vn_result <= 0:
    #     log.warning("failed to get vim_net info: %d %s" %(vn_result, vn_content))
    # else:
    #     for vn in vn_content:
    #         target_dict['vim_net'].append(vn['name'])

    hw_result, hw_content = orch_dbm.get_onebox_hw_serverseq(ob_data['serverseq'])
    if hw_result <= 0:
        log.warning("failed to get HW info: %d %s" %(hw_result, hw_content))
    else:
        target_dict['hw_model'] = hw_content[0]['model']

    os_result, os_content = orch_dbm.get_onebox_sw_serverseq(ob_data['serverseq'])
    if os_result <=0:
        log.warning("failed to get OS info: %d %s" %(os_result, os_content))
    else:
        target_dict['os_name'] = os_content[0]['operating_system']

    sn_result, sn_content = orch_dbm.get_onebox_nw_serverseq(ob_data['serverseq'])
    if sn_result <= 0:
        log.warning("failed to get Server Net info: %d %s" %(sn_result, sn_content))
    else:
        target_dict['svr_net'] = []
        for sn in sn_content:
            target_dict['svr_net'].append({'name':sn['name'], 'display_name':sn['display_name']})

    log.debug('[PNF] Start_monitor_onebox : target_dict = %s' %str(target_dict))

    result, data = monitor.start_monitor_onebox(target_dict)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data


def update_onebox_monitor(body_dict):
    monitor = get_ktmonitor()
    if monitor is None:
        log.warning("failed to setup monitor")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

    result, data = monitor.update_monitor_onebox(body_dict)

    if result < 0:
        log.error("Error %d %s" %(result, data))

    return result, data


def start_nsr_monitoring(server_id, nsr_dict):
    monitor = get_ktmonitor()

    if monitor is None:
        log.warning("failed to setup montior")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

    target_dict = {}
    target_dict['nsr_name'] = nsr_dict['name']

    server_result, server_data = orch_dbm.get_server_id(server_id)

    if server_result <= 0:
        log.warning("failed to get server info of %d: %d %s" % (server_id, server_result, server_data))
        return -HTTP_Internal_Server_Error, "Cannot get Server Info from DB"

    target_dict['server_id'] = server_data['serverseq']
    target_dict['server_uuid'] = server_data['serveruuid']
    target_dict['onebox_id'] = server_data['onebox_id']
    target_dict['server_ip'] = server_data['mgmtip']

    # vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(vim_id=None, vim_name=None, server_id=server_data['serverseq'])
    #
    # if vim_result <= 0:
    #     log.error("failed to get vim info of %d: %d %s" % (server_data['serverseq'], vim_result, vim_content))
    #     return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
    #
    # target_dict['vim_auth_url'] = vim_content[0]['authurl']
    # target_dict['vim_id'] = vim_content[0]['username']
    # target_dict['vim_passwd'] = vim_content[0]['password']
    # target_dict['vim_domain'] = vim_content[0]['domain']
    #
    # target_vms = []
    # for vnf in nsr_dict['vnfs']:
    #     if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
    #         log.debug("[HJC] Skip starting monitoring for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
    #         continue
    #
    #     vnf_app_id = None
    #     vnf_app_passwd = None
    #
    #     for param in nsr_dict['parameters']:
    #
    #         if param['name'].find("appid_" + vnf['name']) >= 0:
    #             log.debug("start_nsr_monitoring() appid param = %s %s" % (param['name'], param['value']))
    #             vnf_app_id = param['value']
    #
    #         if param['name'].find("apppasswd_" + vnf['name']) >= 0:
    #             log.debug("start_nsr_monitoring() apppasswd param = %s %s" % (param['name'], param['value']))
    #             vnf_app_passwd = param['value']
    #
    #     for vm in vnf['vdus']:
    #
    #         target_vm = {'vm_name': vm['name'], 'vdud_id': vm['vdudseq'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid']
    #             , 'monitor_target_seq': vm['monitor_target_seq'], 'vm_id': vm['vm_access_id'], 'vm_passwd': vm['vm_access_passwd']}
    #
    #         target_vm['service_number'] = vnf.get('service_number')
    #
    #         if vnf_app_id:
    #             target_vm['vm_app_id'] = vnf_app_id
    #         if vnf_app_passwd:
    #             target_vm['vm_app_passwd'] = vnf_app_passwd
    #
    #         target_cps = []
    #         if 'cps' in vm:
    #             for cp in vm['cps']:
    #                 target_cp = {'cp_name': cp['name'], 'cp_vim_name': cp['vim_name'], 'cp_vim_uuid': cp['uuid'], 'cp_ip': cp['ip']}
    #                 target_cps.append(target_cp)
    #
    #         target_vm['vm_cps'] = target_cps
    #
    #         target_vm['nfsubcategory'] = vnf['nfsubcategory']
    #
    #         target_vms.append(target_vm)
    #
    # target_dict['vms'] = target_vms

    result, data = monitor.start_monitor_nsr(target_dict)

    if result < 0:
        log.error("start_nsr_monitoring(): error %d %s" % (result, data))

    return result, data
