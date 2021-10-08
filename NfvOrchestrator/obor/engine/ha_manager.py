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

import threading

from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Conflict
import db.orch_db_manager as orch_dbm
import utils.log_manager as log_manager

log = log_manager.LogManager.get_instance()

from engine import common_manager

global_config = None


# HA 구성
def set_ha(mydb, http_content, use_thread=False):
    # e2e_log = None

    try:
        log_info_message = "Setting HA Started"
        log.info(log_info_message.center(80, '='))

        if use_thread:
            th = threading.Thread(target=set_ha_thread, args=(mydb, http_content))
            th.start()
            return 200, "OK"
        else:
            return set_ha_thread(mydb, http_content)
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -HTTP_Internal_Server_Error, "HA 구성이 실패하였습니다. 원인: %s" % str(e)


# HA 구성 해제
def clear_ha(mydb, http_content, use_thread=False):
    # e2e_log = None

    try:
        log_info_message = "Clear HA Started"
        log.info(log_info_message.center(80, '='))

        if use_thread:
            th = threading.Thread(target=clear_ha_thread, args=(mydb, http_content))
            th.start()
            return 200, "OK"
        else:
            return clear_ha_thread(mydb, http_content)
    except Exception, e:
        log.exception("Exception: %s" % str(e))
        return -HTTP_Internal_Server_Error, "HA 구성이 실패하였습니다. 원인: %s" % str(e)


# HA Setting Thread
def set_ha_thread(mydb, http_content):
    # Step 1. Set VIP dict
    log.debug("[Setting][HA] 1. Set VIP dict")

    vip_dict = {}
    vip_dict['vip_w'] = http_content['vip_w']
    vip_dict['vip_o'] = http_content['vip_o']
    vip_dict['vip_s'] = http_content['vip_s']

    # Step 2. Set HA information
    log.debug("[Setting][HA] 2. Compose HA information")

    # scripts 구성하기 위해 미리 사용할 변수를 만들어 둔다
    cmd={}
    profile={}
    master_seq = None

    for cl in http_content.get('cluster_list'):
        if cl.get('mode') == "master":
            master_seq = cl.get('serverseq')

        cmd[cl.get('mode')] = _ha_compose_command(cl, vip_dict, mode=cl.get('mode'))

        profile[cl.get('mode')] = "\\nha profile\\nha-cluster %s\\nmode router active-standby %s\\nhealth-check 1000 threshold 3" \
                                  "\\ncircuit-failover eth1\\nenable\\nend" % (str(cl.get('cluster_id')), str(cl.get('mode')))

    # log.debug('cmd = %s' %str(cmd))
    # log.debug('profile = %s' %str(profile))

    init_config_dict = _default_config(http_content)

    for cl in http_content.get('cluster_list'):
        # Step 3. Setting HA scripts
        log.debug("[Setting][HA] 3. Setting HA scripts")

        result, rlt_data = orch_dbm.get_rlt_data(mydb, cl.get('nsseq'))
        if result < 0:
            log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

        # log.debug('rlt_data = %s' %str(rlt_data))

        configs = rlt_data['rlt']['vnfs'][0]['vdus'][0]['configs']

        init_config_dict['uuid'] = cl.get('uuid')
        init_config_dict['mgmtip'] = rlt_data['rlt']['vnfs'][0]['vdus'][0]['mgmtip']
        init_config_dict['scripts'] = []

        for cf in configs[0]['scripts']:
            # scripts : login
            if cf.get('name') == 'get_session':
                init_config_dict['scripts'].append(_reset_scripts(cf, init_config_dict['user'], init_config_dict['password']))

            # scripts : write
            if cf.get('name') == 'write_config':
                init_config_dict['scripts'].append(_reset_scripts(cf))

            # scripts : config sync
            if cf.get('name') == 'set_nic_eth3':
                body = "cmd=configure terminal\\nconfig sync 1 224.0.0.2 source eth5\\nconfig sync auto\\nconfig sync profile ips application qos snat dnat ipsec nat64" \
                       "\\nconfig sync dhcp\\nend"
                cf['body'] = body

                init_config_dict['scripts'].append(_reset_scripts(cf))

            # scripts : HA Cluster config
            elif cf.get('name') == 'set_nic_eth4':
                body = cmd['master'] + cmd['slave'] + profile[cl.get('mode')]
                cf['body'] = body

                init_config_dict['scripts'].append(_reset_scripts(cf))
            else:
                continue


        # Step 4. Check Vnfm Connection
        log.debug("[Setting][HA] 4. Check Vnfm Connection : OneBox = %s" % str(cl.get('onebox_id')))

        # vnfm connection & status check
        result, vnfms = common_manager.get_ktvnfm(mydb, cl.get('serverseq'))
        if result < 0:
            log.error("Failed to establish a vnfm connnection")
            return -HTTP_Not_Found, "Failed to establish a vnfm connection: %d %s" % (result, vnfms)
        elif result > 1:
            log.error("Error, Several vnfms available, must be identify")
            return -HTTP_Bad_Request, "Several vnfms available, must be identify"

        myvnfm = vnfms.values()[0]

        result, content = myvnfm.check_connection()
        if result < 0:
            log.error(" error in VNFM or cannot connect to VNFM %d %s" % (result, content))
            return result, content


        # Step 5. Vnfm request init config
        log.debug("[Setting][HA] 5. Vnfm request init config : OneBox = %s" % str(cl.get('onebox_id')))

        res_code, res_msg = myvnfm.init_config_vnf_intval(init_config_dict, intval=10)
        log.debug("[Setting][HA] 5. Request Result: %d, %s" % (res_code, res_msg))

        if res_code < 0:
            log.error("[Setting][HA] 5. failed to configure VNF through VNFM: %s, %s" % (str(res_code), str(res_msg)))
            return res_code, res_msg
        else:
            log.debug("[Setting][HA] 5. Result: OK")

            # Step 6. DB 처리
            log.debug("[Setting][HA] 6. DB : OneBox = %s" % str(cl.get('onebox_id')))

            hanet_dict = {}
            hanet_dict['serverseq'] = cl.get('serverseq')
            hanet_dict['onebox_id'] = cl.get('onebox_id')
            hanet_dict['cluster_id'] = cl.get('cluster_id')
            hanet_dict['master_seq'] = master_seq
            hanet_dict['vip_w'] = http_content.get('vip_w')
            hanet_dict['vip_o'] = http_content.get('vip_o')
            hanet_dict['vip_s'] = http_content.get('vip_s')

            # 이미 등록되어 있다면 한번이라도 HA 구성이 되어진 OneBox
            ha_result, ha_content = orch_dbm.get_server_hanet(mydb, cl.get('serverseq'))
            if ha_result < 0:
                log.debug("Failed to DB get : server hanet")
                return ha_result, ha_content
            elif ha_result == 0:
                # 기 등록된 데이터가 없을 때 insert
                result, data = orch_dbm.insert_server_hanet(mydb, hanet_dict)
                if result < 0:
                    log.debug("Failed to DB insert : server hanet")
                    return result, data

            server_dict = {}
            server_dict['serverseq'] = cl.get('serverseq')
            server_dict['master_seq'] = master_seq

            # master OneBox는 master_seq 를 업데이트 하지 않는다. master 가 아닌 OneBox만 Update
            if cl.get('mode') != 'master':
                result, up_data = orch_dbm.update_server(mydb, server_dict)
                if result < 0:
                    log.error("Failed to update nsr_id of server : %d %s" % (result, up_data))
                    return result, up_data
                    # raise Exception("Failed to update nsr_id of server")

    log.debug('[Setting][HA] Finished Thread')
    return 200, "OK"


# HA Clear Thread
def clear_ha_thread(mydb, http_content):
    init_config_dict = _default_config(http_content)

    for cl in http_content.get('cluster_list'):
        # Step 1. Clear HA scripts
        log.debug("[Clear][HA] 1. Clear HA scripts")

        result, rlt_data = orch_dbm.get_rlt_data(mydb, cl.get('nsseq'))
        if result < 0:
            log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

        configs = rlt_data['rlt']['vnfs'][0]['vdus'][0]['configs']

        init_config_dict['uuid'] = cl.get('uuid')
        init_config_dict['mgmtip'] = rlt_data['rlt']['vnfs'][0]['vdus'][0]['mgmtip']
        init_config_dict['scripts'] = []

        for cf in configs[0]['scripts']:
            # scripts : login
            if cf.get('name') == 'get_session':
                init_config_dict['scripts'].append(_reset_scripts(cf, init_config_dict['user'], init_config_dict['password']))

            # scripts : write
            if cf.get('name') == 'write_config':
                init_config_dict['scripts'].append(_reset_scripts(cf))

            # scripts : config sync clear
            if cf.get('name') == 'set_nic_eth3':
                body = "cmd=configure terminal\\nno config sync 1\\nno config sync auto\\nno config sync profile ips application qos snat dnat ipsec nat64" \
                       "\\nno config sync dhcp\\nend"
                cf['body'] = body

                init_config_dict['scripts'].append(_reset_scripts(cf))

            # scripts : HA Cluster config clear
            elif cf.get('name') == 'set_nic_eth4':
                body = "cmd=configure terminal\\nno ha profile\\nno ha cluster all\\nend"
                cf['body'] = body

                init_config_dict['scripts'].append(_reset_scripts(cf))
            else:
                continue

        # Step 2. Check Vnfm Connection
        log.debug("[Clear][HA] 2. Check Vnfm Connection : OneBox = %s" % str(cl.get('onebox_id')))

        # vnfm connection & status check
        result, vnfms = common_manager.get_ktvnfm(mydb, cl.get('serverseq'))
        if result < 0:
            log.error("Failed to establish a vnfm connnection")
            return -HTTP_Not_Found, "Failed to establish a vnfm connection: %d %s" % (result, vnfms)
        elif result > 1:
            log.error("Error, Several vnfms available, must be identify")
            return -HTTP_Bad_Request, "Several vnfms available, must be identify"

        myvnfm = vnfms.values()[0]

        result, content = myvnfm.check_connection()
        if result < 0:
            log.error(" error in VNFM or cannot connect to VNFM %d %s" % (result, content))
            return result, content

        # Step 3. Vnfm request init config
        log.debug("[Clear][HA] 3. Vnfm request init config : OneBox = %s" % str(cl.get('onebox_id')))

        res_code, res_msg = myvnfm.init_config_vnf_intval(init_config_dict, intval=20)
        log.debug("[Clear][HA] 3. Request Result: %d, %s" % (res_code, res_msg))

        if res_code < 0:
            log.error("[Clear][HA] 3. failed to configure VNF through VNFM: %s, %s" % (str(res_code), str(res_msg)))
            return res_code, res_msg
        else:
            log.debug("[Clear][HA] 3. Result: OK")

            # Step 4. DB Clear
            log.debug("[Clear][HA] 4. DB Clear : OneBox = %s" % str(cl.get('onebox_id')))

            # 이미 등록되어 있다면 한번이라도 HA 구성이 되어진 OneBox
            ha_result, ha_content = orch_dbm.delete_server_hanet(mydb, cl.get('serverseq'))
            if ha_result < 0:
                log.debug("Failed to DB delete : server hanet")
                return ha_result, ha_content

            server_dict = {}
            server_dict['serverseq'] = cl.get('serverseq')
            server_dict['master_seq'] = None

            # master OneBox는 master_seq 를 업데이트 하지 않는다. master 가 아닌 OneBox만 Update
            if cl.get('mode') != 'master':
                result, up_data = orch_dbm.update_server(mydb, server_dict)
                if result < 0:
                    log.error("Failed to update master_seq of server : %d %s" % (result, up_data))
                    return result, up_data
                    # raise Exception("Failed to update nsr_id of server")

    log.debug('[Clear][HA] Finished Thread')
    return 200, "OK"


# Default config set
def _default_config(http_content):
    init_config_dict = {}
    init_config_dict['vendor'] = "axgate"
    init_config_dict['tid'] = http_content['tid']
    init_config_dict['tpath'] = http_content['tpath']
    init_config_dict['uuid'] = None
    init_config_dict['mgmtip'] = None
    init_config_dict['local_ip'] = "192.168.254.1"
    init_config_dict['wan_list'] = ['physnet_wan']
    init_config_dict['needWanSwitch'] = True
    init_config_dict['user'] = "axroot"
    init_config_dict['version'] = "4"
    init_config_dict['action'] = ""
    init_config_dict['password'] = "smflaqhNo1@"
    init_config_dict['type'] = "rest_api"
    init_config_dict['name'] = "AXGATE-UTM"

    return init_config_dict


# HA command compose
def _ha_compose_command(cl, vip_dict=None, mode='master'):
    if mode == 'master':
        cmd = "cmd=configure terminal" \
              "\\nno ha profile\\nno ha cluster all" \
              "\\n!" \
              "\\nha cluster %s" \
              "\\nlabel ONEBOX %s" \
              "\\nip %s port 7800 eth5 direct" \
              "\\nrouter virtual-ip 1 %s eth1" \
              "\\nrouter virtual-ip 2 %s eth2" \
              "\\nrouter virtual-ip 3 %s eth3" \
              "\\npreempt-mode true" \
              "\\npriority 1" \
              "\\n!" \
              % (str(cl.get('cluster_id')),
                 str(cl.get('cluster_id')),
                 str(cl.get('vnet_ha_ip')),
                 str(vip_dict['vip_w']),
                 str(vip_dict['vip_o']),
                 str(vip_dict['vip_s']))
    else:
        w_cidr = vip_dict['vip_w'].split('/')
        o_cidr = vip_dict['vip_o'].split('/')
        s_cidr = vip_dict['vip_s'].split('/')

        cmd = "\\nha cluster %s" \
              "\\nlabel ONEBOX %s" \
              "\\nip %s port 7800 eth5 direct" \
              "\\nrouter virtual-ip 1 2.2.2.2/%s eth1" \
              "\\nrouter virtual-ip 2 3.3.3.3/%s eth2" \
              "\\nrouter virtual-ip 3 4.4.4.4/%s eth3" \
              "\\npreempt-mode true" \
              "\\npriority 10" \
              "\\n!" \
              % (str(cl.get('cluster_id')),
                 str(cl.get('cluster_id')),
                 str(cl.get('vnet_ha_ip')),
                 str(w_cidr[1]),
                 str(o_cidr[1]),
                 str(s_cidr[1])
                 )

    return cmd

def _reset_scripts(config, id=None, passwd=None):
    if id is not None and passwd is not None:
        config['body_args'] = []
        config['cookiedata'] = []
        config['requestheaders_args'] = []
        config['output'] = [config['output']]
        config['params'] = [id, passwd]
    else:
        config['body_args'] = []
        config['cookiedata'] = [config['cookiedata']]
        config['requestheaders_args'] = []
        config['output'] = []
        config['params'] = []

    return config
