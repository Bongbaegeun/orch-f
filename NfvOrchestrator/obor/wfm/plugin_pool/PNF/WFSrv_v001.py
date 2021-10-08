# coding=utf-8

import json
import time, datetime

from utils import auxiliary_functions as af
from wfm.plugin_spec.WFSvrSpec import WFSvrSpec

from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import db.dba_manager as orch_dbm
# import wfm.common_biz as orch_com     # common plugin 으로 대체

import threading
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from engine.server_status import SRVStatus
from engine.nsr_status import NSRStatus
# from engine.action_status import ACTStatus
# from engine.action_type import ActionType

# from engine.nsr_manager import handle_default_nsr


class WFSvr(WFSvrSpec):
    def get_version(self):
        return 2

    # rlt 조회용
    def rlt(self, req_info):
        log.debug("[BBG] GET RLT INFO() OK!")

        result, rlt_data = orch_dbm.get_rlt_data(req_info["nsseq"])
        if result < 0:
            log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

        log.debug("[BBG] RLT INFO = %s" % str(rlt_data))

        return 200, req_info.get("serverseq", "NONE")


    def new_server(self, server_info, plugins, use_thread=True, forced=False):
        # log.debug("IN new_server()")

        orch_comm = plugins.get('orch_comm')

        server_id = str(server_info['onebox_id'])
        check_result, check_data = self._check_existing_servers(server_info)

        if check_result < 0:
            log.error("new_server() failed to check the registered servers %d %s" % (check_result, check_data))
            return check_result, check_data
        elif check_result == 0:
            return -HTTP_Bad_Request, "No Server : %s" % str(server_id)
        elif check_result > 1:
            log.error("new_server() there are two or more servers.")
            return -HTTP_Bad_Request, "Cannot Identify Server : %s" % str(server_id)

        # redis 에 noti 데이터 저장
        if 'wf_redis' in plugins:
            redis_key = check_data['onebox_id']
            redis_data = server_info
            redis_msg = "Redis save server data"

            # log.debug('key = %s, data = %s, msg = %s' %(str(redis_key), str(redis_data), str(redis_msg)))

            wf_redis = plugins.get('wf_redis')
            res, cont = wf_redis.redis_set(redis_key, redis_data, redis_msg)

            # log.debug('res = %d, cont = %s' %(res, str(cont)))

        #################################   설치 중, 설정 변경 noti는 중지    S   ##########################################################
        # 이미 설치중, 백업 중일때 처리 중지 (설치 타이밍 이슈) - 설치 중에 설정 변경 할때마다 noti가 계속 들어와 중복으로 처리 되는 문제가 발생됨
        # 복구 시, 강제로 new_server() 를 날려주기 때문에 이 부분을 통과해야 한다
        # log.debug('[server status check] check_data = %s' %str(check_data))
        is_proc = False
        proc_status = ""

        if 'restore' not in server_info:
            if check_data['status'] == SRVStatus.LPV:
                is_proc = True
                proc_status = "설치"
            elif check_data['status'] == SRVStatus.OOS:
                is_proc = True

                if check_data['action'].find("TS") >= 0:
                    proc_status = "재시작"
                else:
                    proc_status = "백업"

            log.debug('[server status check] proc_status = %s' % str(proc_status))
            if is_proc:
                log.debug("##########   new_server() %s 중 이므로 처리 중지.....    #######################" % str(proc_status))
                return 200, "Stop installation because it is being processed Server : %s" % str(proc_status)
        #################################   설치 중, 설정 변경 noti는 중지    E   ##########################################################

        server_info['serverseq'] = check_data['serverseq']
        server_info['status'] = check_data['status']
        server_info['state'] = check_data['state']  # monitor state
        server_info['customerseq'] = check_data['customerseq']
        server_info['org_name'] = check_data['orgnamescode']
        server_info['onebox_id'] = check_data['onebox_id']
        server_info['serveruuid'] = check_data['serveruuid']
        server_info['action'] = check_data['action']
        server_info['nsseq'] = check_data['nsseq']
        server_info['onebox_flavor'] = check_data['onebox_flavor']

        old_info = {
            "mgmt_ip": check_data['mgmtip'],
            "public_ip": check_data['publicip'],
            "public_mac": check_data['publicmac'],
            "ipalloc_mode_public": check_data['ipalloc_mode_public']
        }

        if check_data.get('publicgwip') is not None:
            old_info['publicgwip'] = check_data.get('publicgwip')
        if check_data.get('publiccidr') is not None:
            old_info['publiccidr'] = check_data.get('publiccidr')

        # 회선이중화 : wan list 정보가 넘어온 경우 기존 wan list 정보 조회
        result_wan, wan_list = orch_dbm.get_server_wan_list(check_data['serverseq'])
        if result_wan > 0:
            old_info['wan_list'] = wan_list

        # log.debug("===== OBA Call ===== [%s] DB Info : %s" % (server_info['onebox_id'],str(old_info)))

        server_dict, hardware_dict, software_dict, network_list = self._parse_server_info(server_info, orch_comm)

        thread_dict = {}
        thread_dict['server_info'] = server_info
        thread_dict['server_dict'] = server_dict
        thread_dict['hardware_dict'] = hardware_dict
        thread_dict['software_dict'] = software_dict
        thread_dict['network_list'] = network_list

        log.debug("### [WF] server_dict = %s" % server_dict)
        log.debug("### [WF] hardware_dict = %s" % hardware_dict)
        log.debug("### [WF] software_dict = %s" % software_dict)
        log.debug("### [WF] network_list = %s" % network_list)


        # # 유선->무선 or 무선->유선 변경 시 agent에 리턴될 정보
        # is_ssh_use = False
        # ssh_status = None
        # ssh_port = None
        #
        # if check_data['router'] is None:
        #     # 유선 -> 무선으로 변경
        #     if 'router' in server_dict and server_dict.get('router') == 'W':
        #         log.debug('유선 -> 무선')
        #
        #         is_ssh_use = True
        #         ssh_status = 'add'
        #         ssh_port = 20001
        # else:
        #     # 무선 -> 유선으로 변경
        #     if server_dict.get('router') is None:
        #         log.debug('무선 -> 유선')
        #
        #         is_ssh_use = True
        #         ssh_status = 'del'

        try:
            if use_thread:
                th = threading.Thread(target=self._new_server_thread, args=(thread_dict, plugins, old_info, forced))
                th.start()
            else:
                return self._new_server_thread(thread_dict, plugins, old_info, forced)
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "One-Box 서버 등록이 실패하였습니다. 원인: %s" % str(e)

        # return 200, server_info.get("serverseq", "NONE")

        rt_dict = {'serverseq':  server_info.get("serverseq", "NONE")}

        # tunnel_dict = {}
        # if is_ssh_use:
        #     tunnel_dict['status'] = ssh_status
        #
        #     if ssh_port is not None:
        #         tunnel_dict['number'] = ssh_port
        #
        #     rt_dict['tunnel'] = tunnel_dict

        return 200, rt_dict


    def _new_server_thread(self, thread_dict, plugins, old_info, forced=False):
        orch_comm = plugins.get('orch_comm')

        # Step 1. Parsing Input Data
        # server_dict, hardware_dict, software_dict, network_list = self._parse_server_info(server_info, orch_comm)
        server_info = thread_dict.get('server_info')
        server_dict = thread_dict.get('server_dict')
        hardware_dict = thread_dict.get('hardware_dict')
        software_dict = thread_dict.get('software_dict')
        network_list = thread_dict.get('network_list')

        log.debug("[PNF : %s] Threading Start!" % str(server_info['onebox_id']))

        # Step 2. Check Valid of the input info.
        check_result, check_data = self._check_server_validation(server_dict, hardware_dict, network_list, software_dict, server_info, old_info, mac_check = not forced)

        if check_result < 0:
            log.warning("Invalid One-Box Info: %s" %str(check_data))
            ob_status = server_info['status']
            if server_info['status'].find("I__") >= 0 or server_info['status'].find("E__") >= 0:
                if not forced and server_info["action"] == "RS":
                    pass
                else:
                    ob_status = SRVStatus.ERR

            server_dict = {'serverseq': server_info['serverseq'], 'onebox_id': server_info['onebox_id'], 'status': ob_status, 'description': str(check_data)}

            result, data = orch_dbm.update_server(server_dict)
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
        is_first_noti = False

        # "I__LINE_WAIT" : 변경점 없고 모니터링은 수행
        if server_info["status"] == SRVStatus.LWT: # server_info["status"] 는 조정되지 않은 원래 상태값.
            is_monitor_process = True
            is_change_process = False
            is_first_noti = True
        elif server_dict['status'].find("N__") >= 0 or server_dict['status'].find("E__") >= 0:
            is_monitor_process = True
            is_change_process = True

        # 3.1. 서버정보 업데이트 : status 는 제외

        # update_server 전에 처리
        # update_server 에서 tb_onebox_nw 데이타 삭제하기 전에 기존 데이타 따로 담아놓는다. > port 변경사항 체크해서 모니터 업데이트 처리 필요
        result, nw_list_old = orch_dbm.get_onebox_nw_serverseq(server_dict["serverseq"])
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
            # log.debug("OLD nw_list = %s" % str(nw_list_old))
            # log.debug("NEW nw_list = %s" % str(network_list))
            chg_port_result, chg_port_dict = self._check_chg_port(server_dict["serverseq"], nw_list_old, network_list)

            # log.debug("chg_port_result = %d, chg_port_dict = %s" % (chg_port_result, str(chg_port_dict)))

            is_config_changed = False   # 설변에 관련된 사항이 있는지 체크하는 flag --> 설변이면 backup_history ood_flag를 True로 처리해야한다.
            # 설변체크 1. wan/office/server 변경체크
            if chg_port_result > 0:
                is_config_changed = True

            # 설변체크 3. wan이 STATIC인데 IP가 변경된 경우
            old_wan_list = old_info.get("wan_list", None)
            new_wan_list = server_dict.get("wan_list", None)
            if new_wan_list and old_wan_list and not is_config_changed:
                for new_wan in new_wan_list:
                    if new_wan["ipalloc_mode_public"] == "STATIC":
                        for old_wan in old_wan_list:
                            if old_wan["nic"] == new_wan["nic"]:
                                if old_wan["public_ip"] != new_wan["public_ip"]:
                                    is_config_changed = True
                                break

                # 설변체크 4. wan의 ipalloc_mode_public 가 변경된 경우
                for new_wan in new_wan_list:
                    for old_wan in old_wan_list:
                        if new_wan["nic"] == old_wan["nic"]:
                            if new_wan["ipalloc_mode_public"] != old_wan["ipalloc_mode_public"]:
                                is_config_changed = True
                            break

            if is_config_changed:
                # 기존 백업정보 OOD 변경
                log.debug('[WF] new_server : 기존 백업 정보 OOD FLAG 변경')
                result, content = orch_dbm.update_backup_history({"ood_flag":"TRUE"}, {"serverseq":server_info['serverseq']})

            # 설변체크 END ########################################

        # TODO : LINE_WAIT 에서 Noti가 처음 들어왔을때...초소형은 UTM이 기본 설치되어 있으니, NSR/NFR 데이타를 만들어준다.
        # if is_first_noti:
        #
        #     log.debug('[PNF] ### first_noti start')
        #
        #     # insert tb_nsr
        #     nsr_name = 'NS-%s.AXGATE-UTM-V.2' % str(server_info['onebox_id'])
        #     nsr_description=None
        #
        #     result, nsr_key = orch_dbm.insert_nsr_general_info(nsr_name, nsr_description, server_info, server_info['nsseq'])
        #
        #     log.debug('[PNF] ### nsr_seq = %s' %str(nsr_key))
        #
        #     # insert tb_nfr : nsr_key 넘겨준다.
        #     nfr_seq=None
        #     nfr_name = 'KtPnf-%s-UTM' % str(server_info['onebox_id'])
        #     result, nfr_key = orch_dbm.insert_nfr_general_info(nfr_name, server_info, nsr_key, nfr_seq)
        #
        #     log.debug('[PNF] ### nfr_seq = %d, %s' % (result, str(nfr_key)))
        #
        #     # nsr_key 를 server_info["nsseq"] 에, nfr_key 를 server_info["nfseq"] 에 넣어준다.
        #     server_info['nsseq'] = nsr_key
        #     server_info['nfseq'] = nfr_key
        #
        #     log.debug('[PNF] ### first_noti end')
        #
        #
        # if server_info["nsseq"] is not None:
        #     server_dict["nsseq"] = server_info["nsseq"]

        result, data = orch_dbm.update_server_oba(server_dict, hardware_dict, software_dict, network_list)
        if result < 0:
            log.error("new_server() failed to DB Update for Server")
            return result, data

        # 3.2. 서버 status 정리 및 update

        # server 또는 NSR 이 action 중 일때는 update_server_status 함수를 호출하지 않는다.
        is_update_server_status = False
        nsr_data = None

        # 1. check server action
        server_action = server_info.get("action", None)
        if server_action is None or len(server_action) == 0 or server_action.endswith("E"):
            if server_info['nsseq'] is not None:
                nsr_result, nsr_data = orch_dbm.get_nsr_general_info(server_info['nsseq'])
                if nsr_result < 0:
                    log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
                    return -HTTP_Internal_Server_Error, nsr_data

                nsr_action = nsr_data["action"]

                if nsr_action is None or len(nsr_action) == 0 or nsr_action.endswith("E"):
                    is_update_server_status = True
                else:
                    # NSR이 동작중
                    is_update_server_status = False
                    log.debug("__________ 1. DO NOT update server status. The action of NSR is %s" % nsr_action)
            else:
                is_update_server_status = True

        else:   # server가 동작중
            is_update_server_status = False
            log.debug("__________ 2. DO NOT update server status. The action of Server is %s " % server_action)

        is_handle_default_nsr = False

        if is_update_server_status:
            if server_info["status"] != server_dict["status"]:
                com_dict = {}
                com_dict['server_dict'] = server_dict
                com_dict['is_action'] = False
                com_dict['e2e_log'] = None
                com_dict['action_type'] = None
                com_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_server_status', com_dict)
                com_dict.clear()

                log.debug("__________ The actions of Server and NSR are NORMAL. Update server status : %s" % server_dict["status"])

            if server_dict["status"] == SRVStatus.RDS or server_dict["status"] == SRVStatus.LWT or server_dict["status"] == SRVStatus.LPV:
                if server_info.get('onebox_type'):
                    # PNF type 인 경우 update_server 후에 handle_default_nsr 처리하고 상태값을 최종 변경한다. 설치완료 전까지는 "N__LOCAL_PROVISIONING" 상태로 변경해놓는다.
                    server_dict["status"] = SRVStatus.LPV

                    com_dict = {}
                    com_dict['server_dict'] = server_dict
                    com_dict['is_action'] = False
                    com_dict['e2e_log'] = None
                    com_dict['action_type'] = None
                    com_dict['wf_Odm'] = plugins.get('wf_Odm')

                    orch_comm.getFunc('update_server_status', com_dict)
                    com_dict.clear()

                    is_handle_default_nsr = True
                else:
                    if "default_ns_id" in server_info and server_info["default_ns_id"] == "RESERVED":
                        server_dict["status"] = SRVStatus.LPV
                    elif "default_ns_id" in server_info and server_info["default_ns_id"] == "ERROR":
                        server_dict["status"] = SRVStatus.RDS
                    elif "default_ns_id" in server_info and af.check_valid_uuid(server_info["default_ns_id"]):
                        # update_server 후에 handle_default_nsr 처리하고 상태값을 최종 변경한다. 설치완료 전까지는 "N__LOCAL_PROVISIONING" 상태로 변경해놓는다.
                        log.debug("__________ default_ns_id : %s, status : %s --> %s" % (server_info["default_ns_id"], server_dict["status"], SRVStatus.LPV))
                        server_dict["status"] = SRVStatus.LPV
                        is_handle_default_nsr = True

        if is_monitor_process:
            try:
                # Step 4. 모니터링 처리 및 vim,image 현행화
                if server_dict.get('mgmtip') is not None:
                    update_body_dict = {}

                    if server_dict.get('state', "NOTSTART") == "NOTSTART":
                        log.debug("[WF] Starts monitor One-Box[%s]" % server_dict['onebox_id'])

                        # monitor_result, monitor_data = orch_com.start_onebox_monitor(server_dict['serverseq'])

                        comm_dict = {}
                        comm_dict['serverseq'] = server_dict['serverseq']
                        comm_dict['wf_monitorconnector'] = plugins.get('wf_monitorconnector')

                        monitor_result, monitor_data = orch_comm.getFunc('start_onebox_monitor', comm_dict)
                        comm_dict.clear()

                        if monitor_result >= 0:
                            # OS 모니터 성공 시, 'OSSTART' 로 상태값 변경
                            us_result, us_data = orch_dbm.update_server({'serverseq': server_dict['serverseq'], 'state': "RUNNING"})
                            # us_result, us_data = orch_dbm.update_server({'serverseq': server_dict['serverseq'], 'state': "OSSTART"})
                            # server_dict['chg_state'] = 'OSSTART'
                        else:
                            # error 시 tb_server status를 NOTSTART 상태 그대로 둔다
                            server_dict['status'] = SRVStatus.ERR

                            com_dict = {}
                            com_dict['server_dict'] = server_dict
                            com_dict['is_action'] = False
                            com_dict['e2e_log'] = None
                            com_dict['action_type'] = None
                            com_dict['wf_Odm'] = plugins.get('wf_Odm')

                            orch_comm.getFunc('update_server_status', com_dict)
                            com_dict.clear()

                            log.debug('[PNF] failed to start_onebox_monitor, result = %d, data = %s' %(monitor_result, str(monitor_data)))

                            return -HTTP_Internal_Server_Error, "One-Box 서버정보 처리가 실패하였습니다. 원인: start_onebox_monitor failed"

                            # [BBG] error 시 return 되므로 이부분은 생략
                            # # defalut_ns 설치케이스인 경우 One-Box 모니터링이 실패했으면 어차피 실패되므로 설치 생략.
                            # if is_handle_default_nsr:
                            #     is_handle_default_nsr = False
                            #     log.warning("__________ Skip install Default NS for the Failure of One-Box monitoring start.")
                    else:
                        if old_info.get("mgmt_ip") != server_dict.get('mgmtip'):
                            log.debug(
                                "[PNF] DO update_onebox_monitor() - One-Box MGMT IP Addresses are changed: \n  - One-Box ID: %s\n  - Old MGMT IP:%s\n  - New MGMT IP:%s"
                                % (server_dict['onebox_id'], str(old_info.get('mgmt_ip')), str(server_dict.get('mgmtip'))))

                            update_body_dict['server_id'] = server_dict['serverseq']
                            update_body_dict['server_ip'] = server_dict['mgmtip']

                        # 기존 데이타와 현재 데이타가 변경된 부분이 있는지 체크한다.
                        if chg_port_result > 0:
                            log.debug("[PNF] __________ 변경된 Port 정보 : %s" % chg_port_dict)
                            update_body_dict["change_info"] = chg_port_dict["change_info"]

                        # mgmt_ip가 변경되었거나, vPort 가 변경되었을때 One-Box monitoring을 update 해준다.
                        if update_body_dict:
                            log.debug("[PNF] __________ 모니터링 업데이트 처리 : update_body_dict = %s" % update_body_dict)
                            # monitor_result, monitor_data = orch_com.update_onebox_monitor(update_body_dict)

                            com_dict = {}
                            com_dict['update_body_dict'] = update_body_dict
                            com_dict['wf_monitorconnector'] = plugins.get('wf_monitorconnector')

                            monitor_result, monitor_data = orch_comm.getFunc('update_onebox_monitor', com_dict)
                            com_dict.clear()

                # default_ns 설치 처리.
                # TODO : nsr monitor 처리
                # 서버 상태값 변경 변수 (맨 마지막 상태값 변경 : 타이밍 이슈로 동시 처리 되지 않도록 - True : success, False : error)
                server_status_chg = True

                if is_handle_default_nsr:

                    if server_info['onebox_type'] == "KtPnf":
                        # OS 모니터만 성공 상태일 때, UTM 모니터를 실행해준다
                        # if server_dict['state'] == 'OSSTART':
                        #     nsr_dict = {}
                        #     nsr_dict['serverseq'] = server_dict['serverseq']
                        #     nsr_dict['onebox_type'] = server_info['onebox_type']
                        #     nsr_dict['e2e_log'] = None
                        #
                        #     nsm_result, nsm_data = orch_comm.getFunc('start_nsr_monitoring', nsr_dict)
                        #     nsr_dict.clear()
                        #
                        #     # nsr monitor failed
                        #     if nsm_result <= 0:
                        #         # 모니터링 실패 : server status change > error
                        #         server_status_chg = False

                        if server_info['action'] is not None and server_info['action'].endswith("E"):
                            # action 에 E로 끝났다는 것은 backup, restore, reboot 실행 에러인 경우
                            pass
                        else:
                            # UTM monitor start는 최초 noti 에서만 실행
                            nsr_dict = {}
                            nsr_dict['serverseq'] = server_dict['serverseq']
                            nsr_dict['onebox_type'] = server_info['onebox_type']
                            nsr_dict['e2e_log'] = None
                            nsr_dict['wf_monitorconnector'] = plugins.get('wf_monitorconnector')

                            nsm_result, nsm_data = orch_comm.getFunc('start_nsr_monitoring', nsr_dict)
                            nsr_dict.clear()

                            # nsr monitor failed
                            if nsm_result <= 0:
                                # 모니터링 실패 : server status change > error
                                server_status_chg = False
                    else:
                        # result, server_db = orch_dbm.get_server_id(server_dict['serverseq'])
                        # if server_db["status"] != server_dict["status"]:
                        #     # 이 경우 다른 프로세스(아마도 다른 타이밍의 new_server호출)에 의해서 서버의 상태값이 바뀐 경우이다. 다른 프로세스에 맡기고 모든 처리를 중단한다.
                        #     log.warning("DEFAULT NS 설치 생략 : Changed the server status : [%s] %s ==> %s" % (server_dict['serverseq'], server_dict["status"], server_db["status"]))
                        #     return 200, "OK"
                        #
                        # result, content = handle_default_nsr(customer_id=server_dict["customerseq"], onebox_id=server_dict['servername'], default_ns_id=server_info["default_ns_id"], server_dict=server_dict, tid=None, tpath="")
                        # if result < 0:
                        #     if result == -404:
                        #         # One-Box에 VM이 삭제되서 vnfm이 default NS 정보를 넘겨줄 수 없는 경우. --> 제어시스템에서 설치할 수 있도록 "N__READY_SERVICE" 상태로...
                        #         server_dict["status"] = SRVStatus.RDS
                        #     else:
                        #         # vnfm에서 default NS를 설치중이어서 정보를 줄수 없거나, 에러가 난 경우. --> 다시 시도할 수 있도록 "N__LOCAL_PROVISIONING" 상태로...
                        #         server_dict["status"] = SRVStatus.LPV
                        # else:
                        #     server_dict["status"] = SRVStatus.INS
                        #
                        # # default ns 작업 후 상태를 다시 업데이트한다.
                        # common_manager.update_server_status(mydb, server_dict, e2e_log=None)
                        pass
                # else:
                #     # false 일 경우 에러 처리 (실제 에러인데 설치중 상태로 놔둘수 없어서)
                #     # TODO : 다른 상황에서도 에러 처리 될수 있으므로 테스트 하면서 상태 체크해야 한다(경우의 수 확장 가능성 있음)
                #     server_dict['status'] = SRVStatus.ERR
                #
                #     com_dict = {}
                #     com_dict['server_dict'] = server_dict
                #     com_dict['is_action'] = False
                #     com_dict['e2e_log'] = None
                #     com_dict['action_type'] = None
                #
                #     orch_comm.getFunc('update_server_status', com_dict)
                #     com_dict.clear()

                # Step 5. 변경사항 처리
                if False and is_change_process:

                    # NSR이 없거나, NSR이 존재하고 NSR 상태가 정상일때 wan 변경사항 처리.
                    is_check = False

                    lan_office = None
                    lan_server = None
                    if server_info.get("nsseq", None):
                        nsr_result, nsr_data = orch_dbm.get_nsr_general_info(server_info['nsseq'])

                        if nsr_result < 0:
                            log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
                            return -HTTP_Internal_Server_Error, nsr_data
                        elif nsr_result > 0:
                            if nsr_data['status'].find("N__") >= 0 or nsr_data['status'].find("E__") >= 0:
                                is_check = True
                                # office IP 변경여부 체크
                                if "office_list" in server_dict or "server_list" in server_dict:
                                    lan_office, lan_server = self._check_chg_lan_info(server_info["nsseq"], server_dict)
                    else:
                        is_check = True

                    chg_port_info = {}
                    chg_wan_info = None
                    chg_extra_wan_info = None

                    # if is_check:
                    #     chg_wan_info = common_manager.check_chg_wan_info(mydb, server_dict['serverseq'], old_info.get("wan_list", None), server_dict.get("wan_list", None), is_wan_count_changed=server_dict.get("is_wan_count_changed"))
                    #
                    #     if chg_wan_info and chg_wan_info.get("parm_count", 0) > 0:
                    #         chg_port_info["wan"] = chg_wan_info
                    #     if chg_extra_wan_info and chg_extra_wan_info.get("parm_count", 0) > 0:
                    #         chg_port_info["extra_wan"] = chg_extra_wan_info
                    #
                    #     if lan_office:
                    #         chg_port_info["lan_office"] = lan_office
                    #         log.debug("__________ 변경된 LAN OFFICE IP 정보 : %s" % lan_office)
                    #     if lan_server:
                    #         chg_port_info["lan_server"] = lan_server
                    #         log.debug("__________ 변경된 LAN SERVER IP 정보 : %s" % lan_server)

                    publicip_update_dict = {}

                    if (server_dict.get('publicip') is not None and old_info.get("public_ip") is not None) and (old_info.get("public_ip") != server_dict.get('publicip')):
                        publicip_update_dict['publicip'] = server_dict['publicip']
                        # publicip_update_dict['old_publicip'] = old_info.get("public_ip")
                        publicip_update_dict['publiccidr_cur'] = server_dict['publiccidr']

                        log.debug("One-Box Public IP Addresses are changed:\n  - One-Box ID: %s\n  - %s" % (server_dict['onebox_id'], str(publicip_update_dict)))

                    if (server_dict.get('publicmac') is not None and old_info.get('public_mac') is not None) and (old_info.get('public_mac') != server_dict.get('publicmac')):
                        publicip_update_dict['publicmac'] = server_dict['publicmac']
                        publicip_update_dict['old_publicmac'] = old_info.get("public_mac")
                        log.debug("One-Box Public MAC Addresses are changed:\n  - One-Box ID: %s\n  - %s" % (
                        server_dict['onebox_id'], str(publicip_update_dict)))

                    if (server_dict.get('ipalloc_mode_public') is not None and old_info.get('ipalloc_mode_public') is not None) and (old_info.get('ipalloc_mode_public') != server_dict.get('ipalloc_mode_public')):
                        publicip_update_dict['ipalloc_mode_public'] = server_dict['ipalloc_mode_public']
                        publicip_update_dict['old_ipalloc_mode_public'] = old_info.get("ipalloc_mode_public")
                        log.debug("One-Box Public IP Allocation Mode is changed:\n  - One-Box ID: %s\n  - %s" % (server_dict['onebox_id'], str(publicip_update_dict)))

                    if (server_dict.get('publicgwip') is not None and old_info.get('publicgwip') is not None) and (old_info.get('publicgwip') != server_dict.get('publicgwip')):
                        publicip_update_dict['publicgwip'] = server_dict['publicgwip']
                        publicip_update_dict['old_publicgwip'] = old_info.get("publicgwip")
                        log.debug("One-Box Public GW IP is changed:\n  - One-Box ID: %s\n  - %s" % (server_dict['onebox_id'], str(publicip_update_dict)))

                    if (server_dict.get('publiccidr') is not None and old_info.get('publiccidr') is not None) and (old_info.get('publiccidr') != server_dict.get('publiccidr')):
                        publicip_update_dict['publiccidr'] = server_dict['publiccidr']
                        publicip_update_dict['old_publiccidr'] = old_info.get("publiccidr")
                        log.debug("One-Box Public IP CIDR is changed:\n  - One-Box ID: %s\n  - %s" % (server_dict['onebox_id'], str(publicip_update_dict)))

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
                        # if server_info['nsseq'] is not None:
                        #     nsr_update_result, nsr_update_content = common_manager.update_nsr_by_obagent(mydb,
                        #                                                                                  server_info['nsseq'],
                        #                                                                                  update_info,
                        #                                                                                  use_thread=False)

                    # if server_info.get('nsseq') is not None and update_info:
                    #     try:
                    #         flag_chg_mac = None
                    #         is_wan_list = update_info.get("is_wan_list", False)
                    #
                    #         if is_wan_list:
                    #             if "chg_port_info" in update_info \ and update_info["chg_port_info"].get("wan", None) \ and update_info["chg_port_info"]["wan"].get("mac", None):
                    #                 flag_chg_mac = "MULTI"
                    #         else:
                    #             if 'publicmac' in publicip_update_dict:
                    #                 flag_chg_mac = "ONE"
                    #
                    #         if flag_chg_mac:
                    #             log.debug("Update Mac Address of NS backup file %s %s" % (str(server_info['nsseq']), str(publicip_update_dict)))
                    #
                    #             target_condition = {"nsseq": server_info['nsseq'], "category": "vnf", "ood_flag": False}
                    #             nsb_result, nsb_content = orch_dbm.get_backup_history(mydb, target_condition)
                    #
                    #             if nsb_result < 0:
                    #                 log.error("Failed to get Backup data for NSR: %s from DB" % str(server_info['nsseq']))
                    #             elif nsb_result == 0:
                    #                 log.debug("Not found Backup data for NSR: %s" % str(server_info['nsseq']))
                    #             else:
                    #                 for b_info in nsb_content:
                    #                     if b_info.get('backup_server') is None or b_info.get('backup_location') is None:
                    #                         log.debug("Invalid Backup Info: %s" % str(b_info))
                    #                         continue
                    #
                    #                     backup_filepath = b_info['backup_location']
                    #                     backup_server_ip = b_info['backup_server']
                    #
                    #                     if backup_filepath.find("KT-VNF") < 0:
                    #                         log.debug("Not Target Backup Data: %s" % str(b_info))
                    #                         continue
                    #
                    #                     log.debug("========================================")
                    #                     log.debug("Target Backup Data: %s" % str(b_info))
                    #                     log.debug("========================================")
                    #
                    #                     # get ha connection
                    #                     ssh_conn = ssh_connector(backup_server_ip, 9922)
                    #
                    #                     # make script
                    #                     command = {}
                    #                     command["name"] = "/var/onebox/script/update_KT-VNF_backup.sh"
                    #
                    #                     if flag_chg_mac == "ONE":
                    #                         command["params"] = [backup_filepath, publicip_update_dict['old_publicmac'], publicip_update_dict['publicmac']]
                    #                     else:
                    #                         command["params"] = [backup_filepath]
                    #                         mac_dict = update_info["chg_port_info"]["wan"]["mac"]
                    #                         old_mac_dict = update_info["chg_port_info"]["wan"]["old_mac"]
                    #
                    #                         for r_name in mac_dict.keys():
                    #                             command["params"].extend([old_mac_dict[r_name], mac_dict[r_name]])
                    #
                    #                         log.debug("__________ ssh_command : %s" % command)
                    #
                    #                     # do script
                    #                     result, output = ssh_conn.run_ssh_command(command)
                    #
                    #                     log.debug("ssh_conn result = %s %s" % (str(result), str(output)))
                    #
                    #     except Exception, e:
                    #         log.exception("Exception: %s" % str(e))

                if server_status_chg is False:
                    # error 시 tb_server status를 error로 만든다
                    server_dict['status'] = SRVStatus.ERR

                    com_dict = {}
                    com_dict['server_dict'] = server_dict
                    com_dict['is_action'] = False
                    com_dict['e2e_log'] = None
                    com_dict['action_type'] = None
                    com_dict['wf_Odm'] = plugins.get('wf_Odm')

                    orch_comm.getFunc('update_server_status', com_dict)
                    com_dict.clear()

                    return -HTTP_Internal_Server_Error, "One-Box 서버정보 처리가 실패하였습니다. 원인: start_nsr_monitoring failed"
                else:
                    # nsr monitor success
                    # 서버 state 를 RUNNING 으로 같이 변경한다.
                    # server_dict['chg_state'] = 'RUNNING'
                    server_dict['status'] = SRVStatus.INS

                    com_dict = {}
                    com_dict['server_dict'] = server_dict
                    com_dict['is_action'] = False
                    com_dict['e2e_log'] = None
                    com_dict['action_type'] = None
                    com_dict['wf_Odm'] = plugins.get('wf_Odm')

                    orch_comm.getFunc('update_server_status', com_dict)
                    com_dict.clear()

            except Exception, e:
                log.exception("Exception: %s" % str(e))
                return -HTTP_Internal_Server_Error, "One-Box 서버정보 처리가 실패하였습니다. 원인: %s" % str(e)

        # first_notify = True 인 경우(agent가 재시동했을 경우), monitor쪽에 noti를 해줘야한다. (Plugin 재설치)
        if "first_notify" in server_info and server_info["first_notify"]:
            server_info['mgmt_ip'] = server_dict.get('mgmtip')
            server_info['wf_monitorconnector'] = plugins.get('wf_monitorconnector')
            noti_result, noti_data = orch_comm.getFunc("first_notify_monitor", server_info)
            if noti_result < 0:
                log.error("__________ Failed to notify monitor: %s" % noti_data)

        log.debug("[PNF : %s] Threading End!" % str(server_info['onebox_id']))

        # 변수 초기화
        server_info = None
        server_dict = None
        update_info = None
        hardware_dict = None
        software_dict = None
        network_list = None

        return 1, "[PNF] Threading End!"

    # OneBox 작업 상태 조회
    def get_server_progress_with_filter(self, server_id):
        result, ob_data = orch_dbm.get_server_id(server_id)

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

        progress_data = {'action_type': action_type, 'status': status, 'message':'Success'}

        return 200, progress_data


    # 백업 데이타 조회
    def get_server_backup_data(self, server_id):
        try:
            # Step.1 Get One-Box info
            ob_result, ob_data = orch_dbm.get_server_id(server_id)  # common_manager.get_server_all_with_filter(mydb, onebox_id)
            if ob_result <= 0:
                log.error("get_server_with_filter Error %d %s" % (ob_result, ob_data))
                return ob_result, ob_data

            # ob_data = ob_content[0]

            # Step.2 Get backup info
            target_dict = {'serverseq': ob_data['serverseq']}
            target_dict['category'] = 'onebox'

            backup_result, backup_data = orch_dbm.get_backup_history_lastone(target_dict)

            # log.debug("[*******HJC**********] %d, %s" % (backup_result, str(backup_data)))

            if backup_result <= 0:
                log.warning("Failed to get backup history for %d %s" % (backup_result, str(backup_data)))
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

            resp_dict = {"backup_data": ret_data_backup.get('backup_data')}

            if 'backup_location' in backup_data:
                resp_dict['remote_location'] = backup_data['backup_location']

            if 'backup_local_location' in backup_data:
                resp_dict['local_location'] = backup_data['backup_local_location']

            if backup_data.get('backup_server') is not None:
                resp_dict['backup_server_ip'] = backup_data['backup_server']

            if backup_data.get('backup_server_port') is not None:
                resp_dict['backup_server_port'] = backup_data['backup_server_port']
            else:
                resp_dict['backup_server_port'] = "9922"

            if 'download_url' in backup_data:
                resp_dict['download_url'] = backup_data['download_url']

            return 200, resp_dict
        except Exception, e:
            error_msg = "failed to get backup_data: %s" % str(e)
            log.exception(error_msg)
            return -HTTP_Internal_Server_Error, error_msg


    # Server Delete
    def delete_server(self, req_info, plugins):
        log.debug("delte_server() IN: %s" % str(req_info.get('serverseq')))

        # delete customer server info
        result, server_dict = orch_dbm.get_server_id(req_info.get('serverseq'))
        if result < 0:
            log.error("failed to delete the server %s" % req_info.get('serverseq'))
            return result, server_dict

        # TODO: Stop monitor for the One-Box
        # m_result, m_data = stop_onebox_monitor(server_dict)

        req_info = {'onebox_type': req_info['onebox_type']}
        # orch_comm = common_manager.common_manager(req_info)
        orch_comm = plugins.get('orch_comm')

        comm_dict = {}
        comm_dict['serverseq'] = server_dict['serverseq']
        comm_dict['onebox_type'] = req_info['onebox_type']
        comm_dict['onebox_id'] = server_dict['onebox_id']
        comm_dict['mgmtip'] = server_dict['mgmtip']
        comm_dict['e2e_log'] = None
        comm_dict['wf_monitorconnector'] = plugins.get('wf_monitorconnector')

        m_result, m_data = orch_comm.getFunc('stop_onebox_monitor', comm_dict)
        comm_dict.clear()

        if m_result < 0:
            log.warning("failed to stop monitoring on the One-Box: %s" % str(server_dict))

        # Delete One-Box Info. from DB
        result, server_id = orch_dbm.delete_server(server_dict['serverseq'])
        if result < 0:
            log.error("failed to delete the DB record for %s" % server_dict['serverseq'])
            return result, server_id

        data = {"onebox_id": server_dict['onebox_id'], "status": SRVStatus.IDLE}

        return 200, data


    # 내장함수 #########################################################################################################################

    def _check_existing_servers(self, req_info):
        """
        해당 조건에 맞는 server 정보가 있는지 체크 후, 조회
        :param req_info: http_content
        :return: 서버 정보
        """
        filter_dict = {}
        filter_dict['onebox_id'] = req_info['onebox_id']
        filter_dict['onebox_type'] = req_info['onebox_type']
        result, data = orch_dbm.get_server_filters(filter_dict)
        if result <= 0:
            return result, data
        elif len(data) > 1:
            return len(data), "%d oneboxes are found" % (len(data))
        else:  # 서버 정보가 정상적으로 1개만 조회되었을 경우
            return result, data[0]


    def _parse_server_info(self, server_info, orch_comm):
        """
        서버정보를 객체에 담아서 리턴
        :param server_info:
        :param orch_comm: common_manager
        :return: server_dict, hardware_dict, software_dict, network_list
        """

        # log.debug('_parse_server_info > server_info = %s' %str(server_info))

        hardware_dict = None
        software_dict = None
        network_list = []

        server_dict = {'customerseq': server_info['customerseq'], 'onebox_id': server_info['onebox_id']}
        server_dict['servername'] = server_info['onebox_id']
        server_dict['nfmaincategory'] = "Server"
        server_dict['nfsubcategory'] = server_info.get('nfsubcategory', "KtPnf")
        server_dict['orgnamescode'] = server_info.get("org_name", "목동")
        server_dict['onebox_flavor'] = server_info['onebox_flavor']
        server_dict['web_url'] = server_info['web_url']
        server_dict['obagent_version'] = server_info['oba_version']

        # 무선(router/lte) 사용 시 'W' 값 넣어줌
        server_dict['router'] = None

        if 'serverseq' in server_info:
            server_dict['serverseq'] = server_info['serverseq']

        # if 'public_ip' in server_info:
        #     server_dict['publicip'] = server_info['public_ip']
        #     server_dict['mgmtip'] = server_info.get("mgmt_ip", server_dict['publicip'])

        # 물리 nic 포트의 mgmt_boolean 이 모두 false 인 경우 에러를 막고, 변수로 사용하기 위해 초기값 설정한다.
        server_dict['mgmtip'] = None

        wan_list = []
        office_list = []
        server_list = []
        other_list = []

        if 'nic' in server_info:
            public_nic = None
            zone = None

            # for nic in server_info['nic']:
            #     # zone 값이 없으면 비활성 이므로 pass
            #     # if nic.get('zone') is None or len(nic.get('zone')) <= 0:
            #     #     continue
            #
            #     # zone 값으로 판단, bridge 정보는 pass
            #     # if 'bridge' in nic.get('iface_name'):
            #     #     continue
            #
            #     server_dict['ipalloc_mode_public'] = nic.get('ip_type')
            #     server_info_ip = nic['ip_addr'].split('/')        # xxx.xxx.xxx.xxx/24
            #
            #     if len(server_info_ip) < 2:
            #         p_ip = nic['ip_addr']
            #         p_cidr = None
            #     else:
            #         p_ip = server_info_ip[0]
            #         p_cidr = server_info_ip[1]
            #
            #     # public
            #     if nic['mgmt_boolean'] is True:
            #         server_dict['publicip'] = p_ip
            #
            #         if p_cidr:
            #             server_dict['publiccidr'] = p_cidr
            #
            #         server_dict['mgmtip'] = p_ip
            #         server_dict['publicgwip'] = nic['gw_ip_addr']
            #         server_dict['public_nic'] = nic['iface_name']
            #         server_dict['mgmt_nic'] = nic['iface_name']
            #         server_dict['publicmac'] = nic['mac_addr']
            #
            #         public_nic = nic['iface_name']
            #
            #     port = {"public_ip" : p_ip, "public_cidr_prefix" : p_cidr, "ipalloc_mode_public":nic.get('ip_type')}
            #     port["public_gw_ip"] = nic['gw_ip_addr']
            #     port["mac"] = nic['mac_addr']
            #     port["mode"] = nic['zone'] # ???
            #     port["nic"] = nic['iface_name']
            #     port["mgmt_boolean"] = nic['mgmt_boolean']
            #
            #     if nic["zone"] == "lan_office":
            #         office_list.append(port)
            #         zone = "office"
            #     elif nic["zone"] == "lan_server":
            #         server_list.append(port)
            #         zone = "server"
            #     elif nic['zone'] == "uplink_main":
            #         # if nic.get('gw_ip_addr') is None or len(nic.get('gw_ip_addr')) <= 0:
            #         #     continue
            #
            #         wan_list.append(port)
            #         zone = "wan"
            #     else:
            #         # etc
            #         other_list.append(port)
            #         zone = "other"
            #
            #     network_list.append({'name': nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(nic)})
            #
            # server_dict["wan_list"] = wan_list
            #
            # if office_list:
            #     server_dict["office_list"] = office_list
            # if server_list:
            #     server_dict["server_list"] = server_list
            # if other_list:
            #     server_dict["other_list"] = other_list
            #
            # r_num = 0
            # for wan in wan_list:
            #     if wan["nic"] == public_nic:
            #         wan["status"] = "A"
            #     else:
            #         wan["status"] = "S"
            #
            #     # wan_list 순서대로 R0~N 주는 방식으로 변경처리.
            #     wan["name"] = "R" + str(r_num)
            #     r_num += 1

            tmp_etc = {}
            tmp_bridge = []

            # 우선순위 결정을 위해 bridge 와 ethernet 을 분리한다
            # public 정보는 이 부분에서 처리
            for nic in server_info['nic']:
                if 'bridge' in nic.get('iface_name'):
                    tmp_bridge.append(nic)
                else:
                    # public 정보 처리
                    server_dict['ipalloc_mode_public'] = nic.get('ip_type')
                    server_info_ip = nic['ip_addr'].split('/')  # xxx.xxx.xxx.xxx/24

                    if len(server_info_ip) < 2:
                        p_ip = nic['ip_addr']
                        p_cidr = None
                    else:
                        p_ip = server_info_ip[0]
                        p_cidr = server_info_ip[1]

                    if nic.get('zone') == "uplink_main":
                        # public
                        if nic['mgmt_boolean'] is True:  # mgmt_boolean 이 True 가 아닌 경우가 있다.

                            comm_dict = {}
                            comm_dict['mgmtip'] = p_ip

                            # log.debug('comm_dict = %s' %str(comm_dict))

                            # 라우터를 통해 수신된 것인지 체크
                            m_result, m_data = orch_comm.getFunc('_private_ip_check', comm_dict)
                            comm_dict.clear()

                            # log.debug('m_result = %d, m_data = %s' %(m_result, str(m_data)))

                            if m_result < 0:
                                server_dict['router'] = 'W'
                                server_dict['web_url'] = server_dict['web_url'].replace(p_ip, server_info.get('remote_ip'))

                                # 아래에서 server_dict 에 다시 저장 하므로 여기에서는 server_info 값만 변경해준다
                                server_info['oba_baseurl'] = server_info['oba_baseurl'].replace(p_ip, server_info.get('remote_ip'))
                                p_ip = server_info.get('remote_ip')

                            server_dict['publicip'] = p_ip

                            if p_cidr:
                                server_dict['publiccidr'] = p_cidr

                            server_dict['mgmtip'] = p_ip
                            server_dict['publicgwip'] = nic['gw_ip_addr']
                            server_dict['public_nic'] = nic['iface_name']
                            server_dict['mgmt_nic'] = nic['iface_name']
                            server_dict['publicmac'] = nic['mac_addr']

                        public_nic = nic['iface_name']

                        zone = "wan"
                        wan_list.append(self._parseList(nic))
                        network_list.append({'name': nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(nic)})
                    else:
                        # etc 는 추가 검증을 위해 뽑아쓰기 편하도록 key-value 형태로 저장
                        tmp_etc[nic.get('iface_name')] = nic

            # log.debug('tmp_bridge = %s' % str(tmp_bridge))
            # log.debug('wan_list = %s' % str(wan_list))
            # log.debug('network_list = %s' % str(network_list))
            # log.debug('tmp_etc = %s' % str(tmp_etc))
            log.debug('1 ===========================================================================================================')

            # wan을 제외한 port들은 bridge sequrity zone 우선
            for bridge in tmp_bridge:
                # log.debug('tmp_bridge loop : bridge = %s' %str(bridge))

                if bridge.get('zone') == "uplink_main":
                    # 물리 nic 정보에 mgmt 가 없었으므로 bridge:uplink_main 에 있는 정보로 대체
                    if server_dict['mgmtip'] is None or len(server_dict['mgmtip']) <= 0:
                        # public 정보 처리
                        server_dict['ipalloc_mode_public'] = bridge.get('ip_type')
                        server_info_ip = bridge['ip_addr'].split('/')  # xxx.xxx.xxx.xxx/24

                        if len(server_info_ip) < 2:
                            p_ip = bridge['ip_addr']
                            p_cidr = None
                        else:
                            p_ip = server_info_ip[0]
                            p_cidr = server_info_ip[1]

                        server_dict['publicip'] = p_ip

                        if p_cidr:
                            server_dict['publiccidr'] = p_cidr

                        server_dict['mgmtip'] = p_ip
                        server_dict['publicgwip'] = bridge['gw_ip_addr']
                        # server_dict['publicmac'] = bridge['mac_addr']

                        # 아래 두 정보는 물리 nic 정보가 이미 들어있으므로 세팅하지 않는다
                        # server_dict['public_nic'] = bridge['iface_name']
                        # server_dict['mgmt_nic'] = bridge['iface_name']

                    # ethernet zone 설정은 없지만
                    # bridge : uplink_main 이 있는지 체크 -> 있으면 wan_list 에 포함
                    # mac addr 넣기 위한 처리 변수
                    is_mac_insert = False

                    for bridge_port in bridge.get('port'):
                        # log.debug('bridge : uplink_main : port = %s' %str(bridge_port))

                        # 이미 물리 nic 정보에서 빠진 port 이므로 pass
                        if bridge_port not in tmp_etc:
                            continue

                        # wan 중에서 하나만 public mac addr 로 설정
                        tmp_info = tmp_etc.get(bridge_port)
                        if tmp_info:
                            if is_mac_insert is False:
                                server_dict['publicmac'] = tmp_etc.get(bridge_port).get('mac_addr')
                                is_mac_insert = True

                        wan_list.append(self._parseList(tmp_etc.get(bridge_port)))
                        zone = "wan"

                        etc_nic = tmp_etc.get(bridge_port)
                        network_list.append({'name': etc_nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(etc_nic)})

                        # tmp_etc에 사용안한 nic 만 남긴다
                        tmp_etc.pop(bridge_port)

                    for tmp_wan in wan_list:
                        tmp_wan['public_ip'] = 'Bridge 사용 중'
                else:
                    for bridge_port in bridge.get('port'):
                        log.debug('bridge : %s : bridge_port = %s' % (str(bridge.get('zone')), str(bridge_port)))

                        # 이미 물리 nic 정보에서 빠진 port 이므로 pass
                        if bridge_port not in tmp_etc:
                            log.debug("does not find etc list : %s" % str(bridge_port))
                            continue

                        if bridge.get('zone') == "lan_office":
                            office_list.append(self._parseList(tmp_etc.get(bridge_port)))
                            zone = "office"
                        elif bridge.get('zone') == "lan_server":
                            server_list.append(self._parseList(tmp_etc.get(bridge_port)))
                            zone = "server"
                        else:
                            other_list.append(self._parseList(tmp_etc.get(bridge_port)))
                            zone = "other"

                        etc_nic = tmp_etc.get(bridge_port)
                        network_list.append({'name': etc_nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(etc_nic)})

                        # tmp_etc에 사용안한 nic 만 남긴다
                        tmp_etc.pop(bridge_port)

            # log.debug('wan_list = %s' % str(wan_list))
            # log.debug('network_list = %s' % str(network_list))
            # log.debug('tmp_etc = %s' % str(tmp_etc))
            log.debug('2 ===========================================================================================================')

            # 남은 tmp_etc list 를 각 zone 에 추가
            # ethernet zone은 설정되어 있지만, bridge에 포함되지 않았을 경우 -> ethernet zone 설정으로 각 zone에 포함시켜준다.
            for ek, ev in tmp_etc.items():
                ps_nic = self._parseList(ev)
                # log.debug('key = %s, value = %s' % (str(ek), str(ev)))

                if ev.get('zone') is None or len(ev.get('zone')) <= 0:
                    log.debug('%s, not found zone value....' % str(ek))
                    continue

                if ev.get('zone'):
                    if ev.get('zone') == "lan_office":
                        office_list.append(ps_nic)
                        etc_zone = "office"
                    elif ev.get('zone') == "lan_server":
                        server_list.append(ps_nic)
                        etc_zone = "server"
                    else:
                        other_list.append(ps_nic)
                        etc_zone = "other"

                    network_list.append({'name': ev['iface_name'], 'display_name': etc_zone, 'metadata': json.dumps(ps_nic)})

            server_dict["wan_list"] = wan_list

            if office_list:
                server_dict["office_list"] = office_list
            if server_list:
                server_dict["server_list"] = server_list
            if other_list:
                server_dict["other_list"] = other_list

            r_num = 0
            for wan in wan_list:
                if wan["nic"] == public_nic:
                    wan["status"] = "A"
                else:
                    wan["status"] = "S"

                # wan_list 순서대로 R0~N 주는 방식으로 변경처리.
                wan["name"] = "R" + str(r_num)
                r_num += 1

            log.debug('==================   Change  ============================================')
            log.debug('wan_list = %s' % str(wan_list))
            log.debug('office_list = %s' % str(office_list))
            log.debug('server_list = %s' % str(server_list))
            log.debug('other_list = %s' % str(other_list))
            log.debug('server_dict = %s' % str(server_dict))

        # 5G router 사용 여부
        if 'router' in server_info:
            server_dict['router'] = server_info['router']

        if 'hardware' in server_info:
            hardware_dict = {'model': server_info['hardware']['model']}
            hardware_dict['cpu'] = server_info['hardware'].get('cpu')
            hardware_dict['num_cpus'] = server_info['hardware'].get('num_cpus')
            hardware_dict['num_cores_per_cpu'] = server_info['hardware'].get('num_cores_per_cpu')
            hardware_dict['mem_size'] = server_info['hardware'].get('mem_size')
            #hardware_dict['num_logical_cores'] = server_info['hardware'].get('num_logical_cores')

        if 'operating_system' in server_info:
            software_dict = {'operating_system' : server_info['operating_system']}

        if 'oba_baseurl' in server_info:
            software_dict['onebox_agent_base_url'] = server_info['oba_baseurl']
            server_dict['obagent_base_url'] = server_info['oba_baseurl']

        if 'oba_version' in server_info:
            software_dict['onebox_agent_version'] = server_info.get('oba_version')

        server_dict['state'] = server_info.get('state', "NOTSTART")
        server_dict['status'] = server_info['status']

        if server_dict['status'] == SRVStatus.LWT:
            if 'publicip' in server_dict:
                server_dict['status'] = SRVStatus.RDS
        elif server_dict['status'] == SRVStatus.DSC:
            if 'publicip' in server_dict:
                server_dict['status'] = SRVStatus.RDS

            # PNF 의 경우 ns가 없고, 정상동작 여부를 server_info['state'] == 'RUNNING' 으로 판단한다
            if server_info.get('state') == 'RUNNING':
                server_dict['status'] = SRVStatus.INS

            # PNF 의 경우 ns가 없으므로 이부분은 그냥 pass 된다
            if server_info.get('nsseq') is not None:
                nsr_result, nsr_data = orch_dbm.get_nsr_id(server_info.get('nsseq'))

                if nsr_result <= 0:
                    log.warning("Failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
                else:
                    if nsr_data.get('status', "UNDEFINED") == NSRStatus.RUN:
                        server_dict['status'] = SRVStatus.INS
                    elif nsr_data.get('status', "UNDEFINED") == NSRStatus.ERR:
                        server_dict['status'] = SRVStatus.ERR
                    else:
                        log.error("NSR Status is unexpected: %s" % str(nsr_data.get('status')))
                        server_dict['status'] = SRVStatus.ERR

        elif server_dict['status'] == SRVStatus.ERR:    # 서버 상태가 error 일때
            # PNF 의 경우 ns가 없으므로 ready service 상태로 만들어준다
            if server_info.get('nsseq') is None:
                if 'publicip' in server_dict:
                    server_dict['status'] = SRVStatus.RDS
                    log.debug("[HJC] Update Server Status to %s" % server_dict['status'])
                else:
                    log.debug("[HJC] Do not update Server Status")
            else:
                nsr_result, nsr_data = orch_dbm.get_nsr_id(server_info.get('nsseq'))
                if nsr_result <= 0:
                    log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
                else:
                    if nsr_data.get('status', "UNDEFINED") == NSRStatus.RUN:
                        server_dict['status'] = SRVStatus.INS
                    else:
                        log.debug("[HJC] Do not update Server Status in ERROR because there is a NS that is not RUNNING")

        log.debug("The Server status is %s" % (
            str(server_info['status']) if str(server_info['status']) == str(server_dict['status'])
            else "changed : %s => %s" % (str(server_info['status']), str(server_dict['status'])))
        )

        if server_dict['status'] == SRVStatus.RDS:
            if server_info.get('serveruuid'):
                server_dict['serveruuid'] = server_info['serveruuid']
            else:
                server_dict['serveruuid'] = af.create_uuid()

        return server_dict, hardware_dict, software_dict, network_list


    # nic parsing
    def _parseList(self, nic):
        server_info_ip = nic['ip_addr'].split('/')  # xxx.xxx.xxx.xxx/24

        if len(server_info_ip) < 2:
            p_ip = nic['ip_addr']
            p_cidr = None
        else:
            p_ip = server_info_ip[0]
            p_cidr = server_info_ip[1]

        port = {"public_ip": p_ip, "public_cidr_prefix": p_cidr, "ipalloc_mode_public": nic.get('ip_type')}
        port["public_gw_ip"] = nic['gw_ip_addr']
        port["mac"] = nic['mac_addr']
        port["mode"] = nic['zone']  # ???
        port["nic"] = nic['iface_name']
        port["mgmt_boolean"] = nic['mgmt_boolean']

        return port

    def _check_server_validation(self, server_dict, hardware_dict=None, network_list=None, software_dict=None, server_info=None, old_info=None, mac_check=True):
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
            ret_msg += "\n [MIP][%s] One-Box의 관리용 IP가 유효하지 않습니다. \n - 관리용 IP 주소: %s" % (
            str(datetime.datetime.now()), str(server_dict.get('mgmtip')))

        if mac_check:
            if server_dict.get('publicip') is None or af.check_valid_ipv4(server_dict.get('publicip')) == False:
                ret_result = -HTTP_Bad_Request
                ret_msg = "\n One-Box의 공인 IP가 유효하지 않습니다. %s" % str(server_dict.get('publicip'))

            # PNF 타입에서 gateway ip 가 없는 경우가 있어, 체크하지 않도록 결정됨 (2019.03.19 회의)
            # if server_dict.get('publicgwip') is None or af.check_valid_ipv4(server_dict['publicgwip']) == False:
            #     ret_result = -HTTP_Bad_Request
            #     ret_msg += "\n [MIP][%s] One-Box의 공인 GW IP가 유효하지 않습니다. \n - GW IP 주소: %s" % (
            #     str(datetime.datetime.now()), str(server_dict.get('publicgwip')))

        # Step 3. check public MAC
        if server_dict.get('publicmac') is None or len(server_dict['publicmac']) < 3:
            ret_result = -HTTP_Bad_Request
            ret_msg += "\n [WMAC][%s] One-Box의 WAN NIC의 MAC 주소가 유효하지 않습니다. \n - MAC 주소: %s" % (
            str(datetime.datetime.now()), str(server_dict.get('publicmac')))
        else:
            # TODO: Check Duplication of MAC & Public IP
            pass

        # PNF 타입에서 gateway ip 가 없는 경우가 있어, 체크하지 않도록 결정됨 (2019.03.19 회의)
        # 회선이중화 : wan_list에서 public_gw_ip 값이 "" 이거나 잘못된 값이면 예외처리
        # if server_dict.get("wan_list", None):
        #     for wan in server_dict["wan_list"]:
        #         # log.debug('[WF] _check_server_validation : wan = %s' %str(wan))
        #
        #         if wan["ipalloc_mode_public"] == "STATIC":
        #             if wan.get("public_gw_ip", None) is None:
        #                 ret_result = -HTTP_Bad_Request
        #                 ret_msg += "\n [WGW][%s] One-Box의 WAN Public Gateway IP주소가 존재하지 않습니다." % (
        #                     str(datetime.datetime.now()))
        #                 break
        #             elif wan["public_gw_ip"] == "" or af.check_valid_ipv4(wan["public_gw_ip"]) == False:
        #                 ret_result = -HTTP_Bad_Request
        #                 ret_msg += "\n [WGW][%s] One-Box의 WAN Public Gateway IP주소가 유효하지 않습니다. \n - Gateway IP 주소: %s" % (
        #                 str(datetime.datetime.now()), str(wan["public_gw_ip"]))
        #                 break

        if ret_result < 0:
            return ret_result, ret_msg

        if mac_check:
            # 초소형 에서는 받은 wan list 의 물리 nic 정보의 모든 mac 을 체크한다
            # old_info(tb_server) 에 public_mac 이 없을경우는 초기 설치 되었을때만 이다
            if old_info.get('public_mac'):
                found_old_mac = False

                for nic in server_info.get('nic'):
                    if 'bridge' in nic.get('iface_name'):
                        continue

                    if nic.get('mac_addr') != old_info.get('public_mac'):
                        continue

                    found_old_mac = True
                    break

                if found_old_mac is False:
                    log.debug("Invalid One-Box Info: an One-Box ID cannot have different public MAC Address")
                    ret_result = -HTTP_Conflict
                    ret_msg += "\n [DOB][%s] 다른 MAC 주소의 One-Box 정보가 수신되었습니다. \n - 확인 필요한 One-Box의 IP주소: %s \n - One-Box 서버 교체의 경우 좌측 초기화 버튼을 실행해주세요." % (
                    str(datetime.datetime.now()), str(server_dict.get('mgmtip')))

            # # public_ip = server_dict['publicip']
            # public_mac = server_dict['publicmac']
            # onebox_id = server_dict['onebox_id']
            #
            # oob_result, oob_content = orch_dbm.get_server_id(onebox_id)
            # if oob_result < 0:
            #     log.error("failed to get One-Box Info from DB: %d %s" % (oob_result, oob_content))
            #     ret_result = -HTTP_Internal_Server_Error
            #     ret_msg += "\n DB Error로 One-Box 정보 검증이 실패하였습니다."
            # elif oob_result == 0:
            #     pass
            # else:
            #     # for c in oob_content:
            #     if oob_content.get('publicmac') is not None:
            #         # log.debug("[HJC] public mac: %s" %str(c.get('publicmac')))
            #         if len(oob_content.get('publicmac')) < 3:
            #             log.debug("[HJC] ignore invalid public mac: %s" % str(oob_content.get('publicmac')))
            #         elif oob_content.get('publicmac') != public_mac:
            #             result_wan, wan_list = orch_dbm.get_server_wan_list(oob_content["serverseq"])
            #             found_old_mac = False
            #             if result_wan > 0:
            #                 for w in wan_list:
            #                     if w['mac'] == public_mac:
            #                         log.debug("Valid MAC Address because it mached with %s" % str(w))
            #                         found_old_mac = True
            #                         break
            #             elif result_wan <= 0:
            #                 log.debug("Failed to get WAN List for the One-Box: %s due to %d %s" % (
            #                 onebox_id, result_wan, str(wan_list)))
            #
            #             if found_old_mac is False:
            #                 log.debug("Invalid One-Box Info: an One-Box ID cannot have different public MAC Address")
            #                 ret_result = -HTTP_Conflict
            #                 ret_msg += "\n [DOB][%s] 다른 MAC 주소의 One-Box 정보가 수신되었습니다. \n - 확인 필요한 One-Box의 IP주소: %s \n - One-Box 서버 교체의 경우 좌측 초기화 버튼을 실행해주세요." % (
            #                 str(datetime.datetime.now()), str(server_dict.get('mgmtip')))
            #
            #                 # break

        if ret_result < 0:
            return ret_result, ret_msg

        # Step 4. check hardware type
        if hardware_dict is not None:
            order_ob_flavor = server_dict['onebox_flavor']
            ob_hw_result, ob_hw_data = orch_dbm.get_onebox_flavor_name(order_ob_flavor)
            if ob_hw_result <= 0:
                log.error("failed to get One-Box HW Model Info: %d %s" % (ob_hw_result, ob_hw_data))
            else:
                order_hw_model = ob_hw_data['hw_model']
                if order_hw_model != hardware_dict['model']:
                    log.debug("One-Box HW Model is different from the Order: %s vs %s" % (
                    hardware_dict['model'], order_hw_model))
                    # ret_result = -HTTP_Bad_Request
                    ret_msg += "\n [WHW][%s] One-Box H/W 모델이 오더 정보와 다릅니다. One-Box H/W 모델 확인 필요. \n - 오더 H/W 모델: %s \n   - One-Box H/W 모델: %s" % (
                    str(datetime.datetime.now()), order_hw_model, hardware_dict['model'])

        if ret_result < 0:
            return ret_result, ret_msg

        # Step 5. check One-Box Agents Connectivity
        if software_dict is not None:
            # TODO
            pass

        return ret_result, ret_msg


    def _check_chg_port(self, serverseq, nw_list_old, nw_list_new=None):

        if nw_list_new is None:
            result, nw_list_new = orch_dbm.get_onebox_nw_serverseq(serverseq)
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


    def check_onebox_valid(self, req_info=None):
        global global_config

        check_settings = req_info.get('check_settings')
        onebox_id = req_info.get('onebox_id')
        force = True

        orch_comm = req_info.get('orch_comm')

        try:
            # Step.1 Check arguments
            if onebox_id == None:
                log.error("One-Box ID is not given")
                return -HTTP_Bad_Request, "One-Box ID is required."

            action_tid = af.create_action_tid()
            log.debug("Action TID: %s" %action_tid)

            # Step.2 Get One-Box info. and Status

            # common manager load
            # orch_comm = common_manager.common_manager(req_info)
            com_dict = {'onebox_id':req_info.get('onebox_id'), 'onebox_type':req_info.get('onebox_type')}

            ob_result, ob_content = orch_comm.getFunc('get_server_all_with_filter', com_dict)
            com_dict.clear()

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
                # result, ob_agents = common_manager.get_onebox_agent(onebox_id=onebox_id)

                # comm_dict = {'onebox_id': onebox_id, 'onebox_type': req_info['onebox_type']}
                # result, ob_agents = orch_comm.getFunc('get_onebox_agent', comm_dict)
                result, ob_agents = 1, req_info.get('wf_obconnector')

                if result < 0 or result > 1:
                    log.error("Error. Invalid DB Records for the One-Box Agent: %s" %str(onebox_id))
                    result_data['status']="FAIL"
                    result_data['detail'].append({'agent_connection':"NOK"})
                else:
                    # ob_agent = ob_agents.values()[0]

                    check_dict = {}
                    check_dict['onebox_id'] = ob_data.get('onebox_id')
                    check_dict['obagent_base_url'] = ob_data.get('obagent_base_url')
                    result, check_content = ob_agents.connection_check(check_dict)
                    log.debug("The result of checking a connection to One-Box Agent: %d %s" %(result, str(check_content)))
                    if result < 0:
                        result_data['status']="FAIL"
                        result_data['detail'].append({'agent_connection':"NOK"})
                    else:
                        result_data['detail'].append({'agent_connection':"OK"})

                if req_info.get('onebox_type') == "KtPnf":
                    # PNF type
                    pass
                else:
                    #3-2. VNFM Agent
                    # result, vnfms = common_manager.get_ktvnfm(ob_data['serverseq'])
                    # if result < 0 or result > 1:
                    #     log.error("Error. Invalid DB Records for the VNFM: %s" %str(ob_data['serverseq']))
                    #     result_data['status']="FAIL"
                    #     result_data['detail'].append({'vnfm_connection':"NOK"})
                    # else:
                    #     myvnfm = vnfms.values()[0]
                    #     result, check_content = myvnfm.check_connection()
                    #     log.debug("The result of checking a connection to VNFM: %d %s" %(result, str(check_content)))
                    #     if result < 0:
                    #         result_data['status']="FAIL"
                    #         result_data['detail'].append({'vnfm_connection':"NOK"})
                    #     else:
                    #         result_data['detail'].append({'vnfm_connection':"OK"})
                    # #3-3. VIM
                    # vims = ob_data.get("vims")
                    # if type(vims) == list and len(vims) > 0:
                    #     ob_data['vimseq'] = vims[0]['vimseq']
                    #     vim_result, vim_data = _new_server_update_vim(ob_data)
                    #     if vim_result < 0:
                    #         log.error("Failed to VIM Test: %d %s" %(vim_result, str(vim_data)))
                    #         result_data['status']="FAIL"
                    #         result_data['detail'].append({'vim_connection':"NOK"})
                    #     else:
                    #         result_data['detail'].append({'vim_connection':"OK"})
                    # else:
                    #     log.debug("No VIM Data found: %s" %str(ob_data))

                    pass

            return 200, result_data
        except Exception, e:
            error_msg = "One-Box 연결 확인이 실패하였습니다. One-Box 연결상태를 확인하세요."
            log.exception(error_msg)
            return -515, error_msg


    def _check_chg_lan_info(self, nsseq, server_dict):

        result, rlt_data = orch_dbm.get_rlt_data(nsseq)
        if result < 0:
            log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
            raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

        rlt_dict = rlt_data["rlt"]

        office = {}
        # for param in rlt_dict['parameters']:
        #     if param["name"].find("greenFixedIp") >= 0:
        #         if param["value"] != vnet_dict["vnet_office_ip"]:
        #             office["vnet_office_ip"] = vnet_dict["vnet_office_ip"]
        #             office["vnet_office_cidr"] = vnet_dict["vnet_office_cidr"]
        #             office["vnet_office_subnets"] = vnet_dict["vnet_office_subnets"]
        #         break
        server = {}
        # for param in rlt_dict['parameters']:
        #     if param["name"].find("orangeFixedIp") >= 0:
        #         if param["value"] != vnet_dict["vnet_server_ip"]:
        #             server["vnet_server_ip"] = vnet_dict["vnet_server_ip"]
        #             server["vnet_server_cidr"] = vnet_dict["vnet_server_cidr"]
        #             server["vnet_server_subnets"] = vnet_dict["vnet_server_subnets"]
        #         break

        return office, server

