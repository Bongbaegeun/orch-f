# coding=utf-8
# jshwang, 2019.01.11.Fri.

import json
from utils import auxiliary_functions as af
from connectors import vnfmconnector
from engine.server_status import SRVStatus
from engine.nsr_status import NSRStatus
import datetime
import db.orch_db_manager as orch_dbm
from engine import common_manager
from engine import server_manager
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

def new_pnf_server(mydb, server_info, filter_data=None):
    '''
    :param filter_data: "ORCHTEST.OB1" is expected.
    '''

    log.debug("[JS] isinstance(server_info, dict) = %s" % str(isinstance(server_info, dict)))
    # log.debug("[JS] server_info == None: %s" % str(server_info == None))
    # log.debug("[JS] filter_data == None: %s" % str(filter_data == None))
    log.debug("[JS] filter_data: %s" % str(filter_data))
    log.debug("[JS] before #0. Parsing Input Data")
    #0. Parsing Input Data
    # temporary setting
    server_dict = server_info
    vim_dict = None
    vim_tenant_dict = None
    hardware_dict = None
    software_dict = None
    network_list = []
    vnet_dict = None

    log.debug("[JS] isinstance(server_dict, dict) = %s" % str(isinstance(server_dict, dict)))
    log.debug("[JS] server_dict == None: %s" % str(server_dict == None))

    # [return value]
    all_results = 0
    all_contents = ""    

    log.debug("[JS] before #1. SELECT serverseq FROM tb_server")
    #1. SELECT serverseq FROM tb_server
    SELECT_ = ("serverseq",)
    FROM_ = "tb_server"
    WHERE_ = {}
    WHERE_["onebox_id"] = filter_data

    result, content = mydb.get_table(SELECT=SELECT_, FROM=FROM_, WHERE=WHERE_)
    log.debug("[JS] SELECT result: %d" % result)
    assert (result > 0)
    serverseq = content[0]['serverseq']
    log.debug("[JS] serverseq: %d" % serverseq)

    log.debug("[JS] before #2. UPDATE tb_server by basic information")
    #2. tb_server 기본정보 UPDATE
    UPDATE_ = {}
    WHERE_ = {}

    #UPDATE_["servername"]
    #UPDATE_["description"]
    #UPDATE_["orgnamescode"]
    #UPDATE_["nfmaincategory"]
    #UPDATE_["nfsubcategory"]
    UPDATE_["mgmtip"] = server_dict.get("mgmt_ip", "")
    #UPDATE_["serveruuid"]
    #UPDATE_["nsseq"]
    #UPDATE_["state"]
    #UPDATE_["action"]
    UPDATE_["publicip"] = server_dict.get("public_ip", "")
    #UPDATE_["serial_no"]
    #UPDATE_["vnfm_base_url"]
    #UPDATE_["obagent_base_url"]
    #UPDATE_["status"]
    #UPDATE_["onebox_flavor"]
    #UPDATE_["vnfm_version"]
    #UPDATE_["obagent_version"]
    #UPDATE_["publicmac"]
    #UPDATE_["net_mode"]
    #UPDATE_["orgcustmcode"]
    #UPDATE_["ob_service_number"]
    #UPDATE_["ipalloc_mode_public"]
    UPDATE_["publicgwip"] = server_dict.get("public_gw_ip", "")
    #UPDATE_["publiccidr"]
    UPDATE_["mgmt_nic"] = server_dict.get("mgmt_nic", "")
    UPDATE_["public_nic"] = server_dict.get("public_nic", "")
    UPDATE_["modify_dttm"] = datetime.datetime.now()
    WHERE_["onebox_id"] = filter_data

    log.debug("[JS] UPDATE_['mgmtip']: %s" % UPDATE_.get('mgmtip'))
    log.debug("[JS] UPDATE_['publicip']: %s" % UPDATE_['publicip'])
    log.debug("[JS] UPDATE_['publicgwip']: %s" % UPDATE_['publicgwip'])
    log.debug("[JS] UPDATE_['mgmt_nic']: %s" % UPDATE_['mgmt_nic'])
    log.debug("[JS] UPDATE_['public_nic']: %s" % UPDATE_['public_nic'])
    log.debug("[JS] UPDATE_['modify_dttm']: %s" % UPDATE_['modify_dttm'])

    result, content = mydb.update_rows("tb_server", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)

    all_results += result
    all_contents += content

    log.debug("[JS] before #3. UPDATE tb_onebox_hw by hardware information")
    #3. hw 정보 업데이트 : tb_onebox_hw
    UPDATE_ = {}
    WHERE_ = {}

    UPDATE_["model"] = server_dict.get("hardware", {}).get("model", "")
    UPDATE_["cpu"] = server_dict.get("hardware", {}).get("cpu", "")
    UPDATE_["num_cpus"] = server_dict.get("hardware", {}).get("num_cpus", 0)
    UPDATE_["num_cores_per_cpu"] = server_dict.get("hardware", {}).get("num_cores_per_cpu", 0)
    UPDATE_["num_logical_cores"] = server_dict.get("hardware", {}).get("num_logical_cores", 0)
    UPDATE_["mem_size"] = server_dict.get("hardware", {}).get("mem_size", 0)
    UPDATE_["modify_dttm"] = datetime.datetime.now()
    WHERE_["serverseq"] = serverseq

    log.debug("[JS] UPDATE_['model']: %s" % UPDATE_['model'])
    log.debug("[JS] UPDATE_['cpu']: %s" % UPDATE_['cpu'])
    log.debug("[JS] UPDATE_['num_cpus']: %d" % UPDATE_['num_cpus'])
    log.debug("[JS] UPDATE_['num_cores_per_cpu']: %d" % UPDATE_['num_cores_per_cpu'])
    log.debug("[JS] UPDATE_['num_logical_cores']: %d" % UPDATE_['num_logical_cores'])
    log.debug("[JS] UPDATE_['mem_size']: %d" % UPDATE_['mem_size'])
    log.debug("[JS] UPDATE_['modify_dttm']: %s" % UPDATE_['modify_dttm'])

    result, content = mydb.update_rows("tb_onebox_hw", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)
    all_results += result
    all_contents += content

    log.debug("[JS] before #4. UPDATE tb_onebox_sw by software information")
    #4. sw 정보 업데이트 : tb_onebox_sw
    UPDATE_ = {}
    WHERE_ = {}

    UPDATE_["operating_system"] = server_dict.get("software", {}).get("operating_system", "")
    #UPDATE_["onebox_vnfm_base_url"]
    #UPDATE_["onebox_vnfm_version"]
    #UPDATE_["onebox_agent_base_url"]
    #UPDATE_["onebox_agent_version"]
    UPDATE_["modify_dttm"] = datetime.datetime.now()
    WHERE_["serverseq"] = serverseq

    result, content = mydb.update_rows("tb_onebox_sw", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)
    all_results += result
    all_contents += content

    log.debug("[JS] #5. before UPDATE tb_onebox_nw by network information")
    #5. network 정보 업데이트 : tb_onebox_nw
    UPDATE_ = {}
    WHERE_ = {}

    UPDATE_["name"] = server_dict.get("wan", {}).get("nic", "")     #ex. eth0, ech2, eth3, eth7
    #UPDATE_["display_name"]
    #UPDATE_["metadata"]
    UPDATE_["modify_dttm"] = datetime.datetime.now()
    WHERE_["serverseq"] = serverseq

    result, content = mydb.update_rows("tb_onebox_nw", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)
    all_results += result
    all_contents += content

    log.debug("[JS] before #6. UPDATE tb_server_vnet by lan_office/lan_server information")
    #6. lan_office/lan_server 정보 업데이트 : tb_server_vnet
    UPDATE_ = {}
    WHERE_ = {}

    if isinstance(server_dict.get("vnet", [])[0:1], dict) and isinstance(server_dict.get("vnet", [])[1:2], dict):
        UPDATE_["vnet_office_ip"] = server_dict.get("vnet", [])[0:1].get("ip", "")
        #UPDATE_["vnet_office_cidr"]
        UPDATE_["vnet_office_subnets"] = server_dict.get("vnet", [])[0:1].get("subnet", "")
        UPDATE_["vnet_server_ip"] = server_dict.get("vnet", [])[1:2].get("ip", "")
        #UPDATE_["vnet_server_cidr"]
        UPDATE_["vnet_server_subnets"] = server_dict.get("vnet", [])[1:2].get("subnet", "")
    else:
        UPDATE_["vnet_office_ip"] = ""
        #UPDATE_["vnet_office_cidr"]
        UPDATE_["vnet_office_subnets"] = ""
        UPDATE_["vnet_server_ip"] = ""
        #UPDATE_["vnet_server_cidr"]
        UPDATE_["vnet_server_subnets"] = ""

    WHERE_["serverseq"] = serverseq

    result, content = mydb.update_rows("tb_server_vnet", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)
    all_results += result
    all_contents += content

    log.debug("[JS] before #7-1. UPDATE tb_vim by vim information")
    #7-1. vim 정보 업데이트: tb_vim
    UPDATE_ = {}
    WHERE_ = {}

    #UPDATE_["name"]
    #UPDATE_["description"]
    UPDATE_["vimtypecode"] = server_dict.get("vim", {}).get("vim_type", "")
    #UPDATE_["mgmtip"]
    #UPDATE_["pvimseq"]
    UPDATE_["authurl"] = server_dict.get("vim", {}).get("vim_authurl", "")
    #UPDATE_["authurladmin"]
    #UPDATE_["display_name"]
    UPDATE_["version"] = server_dict.get("vim", {}).get("vim_version", "")
    UPDATE_["modify_dttm"] = datetime.datetime.now()
    WHERE_["serverseq"] = serverseq

    result, content = mydb.update_rows("tb_vim", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)
    all_results += result
    all_contents += content

    log.debug("[JS] before #7-2. SELECT vimseq FROM tb_vim")
    #7-2. tb_vim 에서 vimseq SELECT
    SELECT_ = ("vimseq", )
    FROM_ = "tb_vim"
    WHERE_ = {}
    WHERE_["serverseq"] = serverseq

    result, content = mydb.get_table(SELECT=SELECT_, FROM=FROM_, WHERE=WHERE_)
    log.debug("[JS] SELECT result: %d" % result)
    assert (result > 0)
    vimseq = content[0]['vimseq']
    log.debug("[JS] vimseq: %d" % vimseq)

    log.debug("[JS] before #7-3. UPDATE tb_vim_tenant by vim information")
    #7-3. vim 정보 업데이트: tb_vim_tenant
    UPDATE_ = {}
    WHERE_ = {}

    UPDATE_["name"] = server_dict.get("vim", {}).get("vim_tenant_name", "")
    #UPDATE_["description"]
    #UPDATE_["createdyn"]
    #UPDATE_["uuid"]
    UPDATE_["username"] = server_dict.get("vim", {}).get("vim_tenant_username", "")
    UPDATE_["password"] = server_dict.get("vim", {}).get("vim_tenant_passwd", "")
    #UPDATE_["domain"]
    UPDATE_["modify_dttm"] = datetime.datetime.now()
    WHERE_["vimseq"] = vimseq

    result, content = mydb.update_rows("tb_vim_tenant", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)
    all_results += result
    all_contents += content

    log.debug("[JS] before #8. UPDATE tb_server_wan by wan information")
    #8. wan 정보 업데이트 : tb_server_wan
    #    8.1. wan 갯수가 다를때 처리
    #    - NS가 설치된 경우 : 기존에 있는 항목만 체크한다.
    #    - NS가 설치되지 않은 경우 : 새로 들어온 정보에 맞춘다.

    SELECT_ = ("count(*) as cnt", )
    FROM_ = "tb_server_wan"
    WHERE_ = {}
    WHERE_["serverseq"] = serverseq

    result, content = mydb.get_table(SELECT=SELECT_, FROM=FROM_, WHERE=WHERE_)
    log.debug("[JS] SELECT result: %d" % result)
    assert (result > 0)
    db_wan_len = content[0]['cnt']
    log.debug("[JS] db_wan_len: %d" % db_wan_len)

    req_wan_len = len(server_dict.get("wan_list", []))
    if db_wan_len != req_wan_len:
        SELECT_ = ("count(nsseq) as cnt_nsseq", )
        FROM_ = "tb_server"
        WHERE_= {}
        result, content = mydb.get_table(SELECT=SELECT_, FROM=FROM_, WHERE=WHERE_)
        log.debug("[JS] SELECT result: %d" % result)
        assert(result > 0)
        is_ns_installed = True if (content[0]['cnt_nsseq'] > 0) else False

        log.debug("[JS] content[0]['cnt_nsseq']: %d" % content[0]['cnt_nsseq'])
        log.debug("[JS] is_ns_installed: %s" % str(is_ns_installed))

        if is_ns_installed:
            pass
        else:
            if server_dict.get("nsseq"):
                UPDATE_ = {}
                WHERE_ = {}

                UPDATE_["nsseq"] = server_dict["nsseq"]
                WHERE_["serverseq"] = serverseq

                result, content = mydb.update_rows("tb_server", UPDATE_, WHERE_)
                log.debug("[JS] UPDATE result: %d" % result)
                assert (result >= 0)
                all_results += result
                all_contents += content

    log.debug("[JS] before #9. UPDATE tb_server_wan by extra_wan information")
    #9. extra_wan 정보 업데이트 : tb_server_wan
    UPDATE_ = {}
    WHERE_ = {}

    if isinstance(server_dict.get("wan_list", [])[0:1], dict):
        #UPDATE_["onebox_id"]
        UPDATE_["public_ip"] = server_dict.get("wan_list", {})[0:1].get("public_ip", "")
        UPDATE_["public_cidr_prefix"] = server_dict.get("wan_list", {})[0:1].get("public_cidr_prefix", 0)
        UPDATE_["public_gw_ip"] = server_dict.get("wan_list", {})[0:1].get("public_gw_ip", "")
        #UPDATE_["ipalloc_mode_public"]
        UPDATE_["mac"] = server_dict.get("wan_list", {})[0:1].get("mac", "")
        UPDATE_["mode"] = server_dict.get("wan_list", {})[0:1].get("mode", "")
        UPDATE_["nic"] = server_dict.get("wan_list", {})[0:1].get("nic", "")
        #UPDATE_["name"]
        #UPDATE_["status"]
        #UPDATE_["physnet_name"]
    else:
        # UPDATE_["onebox_id"]
        UPDATE_["public_ip"] =""
        UPDATE_["public_cidr_prefix"] = 0
        UPDATE_["public_gw_ip"] = ""
        # UPDATE_["ipalloc_mode_public"]
        UPDATE_["mac"] = ""
        UPDATE_["mode"] = ""
        UPDATE_["nic"] = ""
        # UPDATE_["name"]
        # UPDATE_["status"]
        # UPDATE_["physnet_name"]
    WHERE_["serverseq"] = serverseq

    result, content = mydb.update_rows("tb_server_wan", UPDATE_, WHERE_)
    log.debug("[JS] UPDATE result: %d" % result)
    assert (result >= 0)
    all_results += result
    all_contents += content

    log.debug("[JS] before #10. processing monitoring")
    #10. 모니터링 처리
    #    10.1. server state 가 'NOTSTART' 인 경우
    #    10.1.1. One-Box 모니터링을 시작한다. : start_onebox_monitor
    #    10.1.2. 모니터링이 정상적으로 시작되면 server state를 'RUNNING'으로 변경
    #
    #    10.2. One-Box 모니터링을 업데이트 해야하는 경우 : update_onebox_monitor  (server state 가 'NOTSTART'가 아닐때)
    #    10.2.1. mgmt ip 가 변경된 경우
    #    10.2.2. port 정보가 변경된 경우 (wan, office, server) : tb_onebox_nw 에서 비교
    #            예> eth1 : wan 이 었는데 eth1 : office 로 바뀐 경우

    SELECT_ = ("state", )
    FROM_ = "tb_server"
    WHERE_ = {}
    WHERE_["serverseq"] = serverseq

    result, content = mydb.get_table(SELECT=SELECT_, FROM=FROM_, WHERE=WHERE_)
    log.debug("[JS] SELECT result: %d" % result)
    assert (result > 0)
    db_server_state = content[0]['state']
    log.debug("[JS] db_server_state: %s" % db_server_state)

    if db_server_state == 'NOTSTART':
        monitor_result, monitor_data = server_manager.start_onebox_monitor(mydb, serverseq)

        if monitor_result >= 0:
            us_result, us_data = orch_dbm.update_server(mydb, {'serverseq': serverseq, 'state': "RUNNING"})
    else:
        SELECT_ = ("mgmtip", )
        FROM_ = "tb_server"
        WHERE_ = {}
        WHERE_["serverseq"] = serverseq

        result, content = mydb.get_table(SELECT=SELECT_, FROM=FROM_, WHERE=WHERE_)
        log.debug("[JS] SELECT result: %d" % result)
        assert (result > 0)
        db_mgmtip = content[0]['mgmtip']
        log.debug("[JS] db_mgmtip: %s" % db_mgmtip)

        if db_mgmtip != server_dict.get("mgmtip", ""):
            log.debug("[JS] db_mgmtip != server_dict.get('mgmtip', '')")
            update_body_dict = {}
            update_body_dict['server_id'] = serverseq
            update_body_dict['mgmp_ip'] = server_dict.get("mgmtip", "")
            monitor_result, monitor_data = server_manager.update_onebox_monitor(mydb, update_body_dict)
            log.debug("[JS] update_onebox_monitor() result: %d" % monitor_result)
            assert (monitor_result > 0)

            if monitor_result > 0:
                result, nw_list_old = orch_dbm.get_onebox_nw_serverseq(mydb, serverseq)
                if result > 0:
                    #log.debug("[JS] nw_list_old: %s" % str(nw_list_old))
                    #log.debug("[JS] network_list: %s" % str(network_list))
                    chg_port_result, chg_port_dict = common_manager.check_chg_port(mydb, serverseq, nw_list_old, network_list)

                    if chg_port_result > 0:
                        log.debug("[JS] chg_port_result > 0")
                        log.debug("[JS] update_body_dict: %s" % str(update_body_dict))

                        monitor_result, monitor_data = server_manager.update_onebox_monitor(mydb, update_body_dict)
                        log.debug("[JS] update_onebox_monitor() result: %d" % monitor_result)

                        if monitor_result > 0:
                            log.debug("[JS] monitor_data: %s" % str(monitor_data))
                            log.debug("[JS] update_onebox_monitor() result: %d" % result)

                        assert (monitor_result > 0)

    log.debug("[JS_HOT] return temporarily before #11")
    log.debug("[JS] all_results: %d" % all_results)
    log.debug("[JS] all_contentss: %s" % all_contents)
    return all_results, all_contents

    log.debug("[JS] before #11. UPDATE control system by changed port ip information")
    #11. Port IP 변경 사항 처리 : 변경된 것이 있으면 제어시스템에 업데이트
    #    11.1. wan_list
    #    11.1.1. 업데이트 대상 : DB, RLT
    #    11.1.2. 업데이트 항목 : parameters 내용, web_url, cp ip
    #
    #    11.2. lan_office/lan_server IP
    #    11.2.1. 업데이트 대상 : DB, RLT
    #    11.2.2. 업데이트 항목 : parameters 내용, cp ip

    #TODO: wan_list(red)
    if "wan_list" in server_dict:
        result_wan, wan_list = orch_dbm.get_server_wan_list(mydb, serverseq)
        #assert (result_wan >= 0)

        log.debug("[JS] TODO: update parameters, web_url, cp ip")
        log.debug("[JS] TO REFER common_manager.py:111~476, _update_nsr_by_obagent_thread()")
        log.debug("[JS] TODO: result, rlt_data = orch_dbm.get_rlt_data(mydb, nsseq)")
        log.debug("[JS] TODO: esult, content = orch_dbm.update_rlt_data(mydb, json.dumps(rlt_dict), rlt_seq=rlt_data['rltseq'])")

    #TODO: lan_office(green)/lan_server(orange)
    log.debug("[JS] TODO: for param in rlt_dict['parameters']:if param['name'].find('greenFixedIp') >= 0:")
    log.debug("[JS] TODO: for param in rlt_dict['parameters']:if param['name'].find('orangeFixedIp') >= 0:")

    log.debug("[JS] returning new_pnf_server()")

    return all_results, all_contents