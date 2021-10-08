# coding=utf-8

import json
import time, datetime

from utils import auxiliary_functions as af
from wfm.plugin_spec.WFSvrArmSpec import WFSvrArmSpec

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


class WFSvrArm(WFSvrArmSpec):

    def _new_server_thread(self, server_info, plugins, old_info, forced=False, is_wad=False):
        log.debug("[ARM : %s] Threading Start!" % str(server_info['onebox_id']))

        orch_comm = plugins.get('orch_comm')

        if 'serverseq' in server_info:

            # Step 1. Parsing Input Data
            # server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict
            server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict = self._parse_server_info(server_info, orch_comm)

            # log.debug("### [WF] server_dict = %s" % server_dict)
            # log.debug("### [WF]  hardware_dict = %s" % hardware_dict)
            # log.debug("### [WF]  software_dict = %s" % software_dict)
            # log.debug("### [WF]  network_list = %s" % network_list)
            # log.debug("### [WF]  vnet_dict = %s" % vnet_dict)

            # Step 2. Check Valid of the input info.
            # check_result, check_data = self._check_server_validation(server_dict, hardware_dict, network_list, software_dict, mac_check=not forced)
            check_result, check_data = self._check_server_validation(server_dict, hardware_dict, network_list, software_dict, mac_check=forced)

            # log.debug('### [WF]  check_data = %s' %str(check_data))

            if check_result < 0:
                log.warning("Invalid One-Box Info: %s" % str(check_data))
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
            # "I__LINE_WAIT" : 변경점 없고 모니터링은 수행
            if server_info["status"] == SRVStatus.LWT:  # server_info["status"] 는 조정되지 않은 원래 상태값.
                is_monitor_process = True
                is_change_process = False
            elif server_dict['status'].find("N__") >= 0 or server_dict['status'].find("E__") >= 0:
                is_monitor_process = True
                is_change_process = True
            elif is_wad:  # WAN 추가/삭제 프로세스.
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

                chg_port_result, chg_port_dict = self._check_chg_port(server_dict["serverseq"], nw_list_old, network_list)

                is_config_changed = False  # 설변에 관련된 사항이 있는지 체크하는 flag --> 설변이면 backup_history ood_flag를 True로 처리해야한다.
                # 설변체크 1. wan/office/server 변경체크
                if chg_port_result > 0:
                    is_config_changed = True

                # 설변체크 2. vnet ip 변경 체크
                if vnet_dict and not is_config_changed:
                    result, vnet_old = orch_dbm.get_server_vnet(server_dict["serverseq"])
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
                    result, content = orch_dbm.update_backup_history({"ood_flag": "TRUE"}, {"serverseq": server_info['serverseq']})

                # 설변체크 END ########################################

            # server의 status 가 변경되지 않도록 status 항목을 제거한다.
            status_bak = server_dict['status']
            del server_dict['status']

            log.debug('[KtArm] server_info = %s' %str(server_info))

            ############ WAN Update시 처리 관련 항목 정리 [update_server] ###################
            # NS 설치여부 필요 (nsseq 있으면 설치된 것으로 함.)
            if server_info.get("nsseq") is not None:
                server_dict["nsseq"] = server_info.get("nsseq")
            # WAN 추가/삭제 동작중에는 wan_list 저장 안함.
            server_dict["is_wad"] = is_wad
            ############ WAN Update시 처리 관련 항목 정리 END ###################

            # log.debug('[KtArm] server_dict = %s' %str(server_dict))
            # log.debug('[KtArm] hardware_dict = %s' %str(hardware_dict))
            # log.debug('[KtArm] software_dict = %s' %str(software_dict))
            # log.debug('[KtArm] network_list = %s' %str(network_list))
            # log.debug('[KtArm] vnet_dict = %s' %str(vnet_dict))
            # log.debug('[KtArm] vim_dict = %s' %str(vim_dict))
            # log.debug('[KtArm] vim_tenant_dict = %s' %str(vim_tenant_dict))

            result, data = orch_dbm.update_server_oba_arm(server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict)
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

                if server_info.get('nsseq') is not None:
                    nsr_result, nsr_data = orch_dbm.get_nsr_general_info(server_info.get('nsseq'))
                    if nsr_result < 0:
                        log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
                        return -HTTP_Internal_Server_Error, nsr_data

                    nsr_action = nsr_data.get("action")
                    if nsr_action is None or len(nsr_action) == 0 or nsr_action.endswith("E"):
                        is_update_server_status = True
                    else:  # NSR이 동작중
                        is_update_server_status = False
                        log.debug("__________ DO NOT update server status. The action of NSR is %s" % nsr_action)
                else:
                    is_update_server_status = True

                is_update_server_status = True

            else:  # server가 동작중
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
                        if nsr_data is not None:  # 이런 경우는 사실 없어야 한다. --> NSR이 존재한다면 서버 status가 INS/ERR 중 하나가 되어서 이부분 로직을 타지 않아야한다.
                            is_handle_default_nsr = False
                            log.warning("__________ 서버 상태가 정상적인지 확인 필요... server_info:%s, server_dict:%s, nsr:%s " % (
                            server_info["status"], server_dict["status"], nsr_data["status"]))

                # log.debug('server_info = %s' %str(server_info))
                # log.debug('server_dict = %s' %str(server_dict))

                if server_info["status"] != server_dict["status"]:
                    # common_manager.update_server_status(mydb, server_dict, e2e_log=None)
                    com_dict = {}
                    com_dict['server_dict'] = server_dict
                    com_dict['is_action'] = False
                    com_dict['e2e_log'] = None
                    com_dict['action_type'] = None
                    com_dict['wf_Odm'] = plugins.get('wf_Odm')

                    orch_comm.getFunc('update_server_status', com_dict)
                    com_dict.clear()

                    log.debug("__________ The actions of Server and NSR are NORMAL. Update server status : %s" % server_dict["status"])

            # note 처리
            try:
                if "note" in server_dict:
                    log.debug("********* HJC: start pasring note")
                    result, memo_r = orch_dbm.get_memo_info({'serverseq': server_dict['serverseq']})
                    if result < 0:
                        log.error("Failed to get memo : serverseq = %s" % server_dict['serverseq'])
                        return result, memo_r
                    elif result == 0:
                        memo_dict = {"serverseq": server_dict['serverseq']}
                        memo_dict["contents"] = server_dict["note"]
                        result, memoseq = orch_dbm.insert_memo(memo_dict)
                        if result < 0:
                            log.error("Failed to insert memo : serverseq = %s" % server_dict['serverseq'])
                            return result, memoseq
                    else:
                        contents = memo_r[0]["contents"]
                        contents += server_dict["note"]
                        memo_r[0]["contents"] = contents
                        result, update_msg = orch_dbm.update_memo(memo_r[0])
                        if result < 0:
                            log.error("Failed to update memo : memoseq = %s" % memo_r[0]['memoseq'])
                            return result, update_msg
                    log.debug("********* HJC: end pasring note")
            except Exception, e:
                log.exception("for Note, Exception: %s" % str(e))

        else:
            # Create Case: Not supported for One-Box Service
            log.error("Not found One-Box Info registered to Orchestrator")
            return -HTTP_Bad_Request, "Not found One-Box Info registered to Orchestrator"


        if is_monitor_process:
            try:
                # 서버 상태값 변경 변수 (맨 마지막 상태값 변경 : 타이밍 이슈로 동시 처리 되지 않도록 - True : success, False : error)
                server_status_chg = True

                # Step 4. 모니터링 처리 및 vim,image 현행화
                if server_dict.get('mgmtip') is not None:

                    update_body_dict = {}

                    if server_dict.get('state', "NOTSTART") == "NOTSTART":
                        log.debug("Starts monitor One-Box[%s]" % server_dict['onebox_id'])

                        # monitor_result, monitor_data = start_onebox_monitor(server_dict['serverseq'])

                        comm_dict = {}
                        comm_dict['serverseq'] = server_dict['serverseq']
                        comm_dict['wf_monitorconnector'] = plugins.get('wf_monitorconnector')

                        monitor_result, monitor_data = orch_comm.getFunc('start_onebox_monitor', comm_dict)
                        comm_dict.clear()

                        if monitor_result >= 0:
                            us_result, us_data = orch_dbm.update_server({'serverseq': server_dict['serverseq'], 'state': "RUNNING"})
                        else:
                            server_status_chg = False

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
                            # monitor_result, monitor_data = update_onebox_monitor(mydb, update_body_dict)

                            com_dict = {}
                            com_dict['update_body_dict'] = update_body_dict
                            com_dict['wf_monitorconnector'] = plugins.get('wf_monitorconnector')

                            monitor_result, monitor_data = orch_comm.getFunc('update_onebox_monitor', com_dict)
                            com_dict.clear()

                    # if old_info.get("mgmt_ip") != server_dict.get('mgmtip'):
                    #     _new_server_update_vim(mydb, server_dict)
                    #     common_manager.sync_image_for_server(mydb, server_dict['serverseq'])

                # default_ns 설치 처리.
                # TODO : nsr monitor 처리

                if is_handle_default_nsr:

                    if server_info['onebox_type'] == "KtArm":
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

                # Step 5. 변경사항 처리
                if is_change_process:

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
                                if vnet_dict:
                                    lan_office, lan_server = self._check_chg_lan_info(server_info["nsseq"], vnet_dict)
                    else:
                        is_check = True

                    chg_port_info = {}
                    chg_wan_info = None
                    chg_extra_wan_info = None

                    if is_check:

                        if not is_wad:  # wan add/delete 작업 중이면 wan 변경사항 체크 생략
                            chg_wan_info = self._check_chg_wan_info(server_dict['serverseq']
                                                                             , old_info.get("wan_list", None), server_dict.get("wan_list", None)
                                                                             , is_wan_count_changed=server_dict.get("is_wan_count_changed"))
                        # extra_wan_list 의 변경체크
                        if server_dict.get("extra_wan_list", None):
                            chg_extra_wan_info = self._check_chg_extra_wan_info(server_dict['serverseq']
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

                        log.debug("One-Box Public IP Addresses are changed:\n  - One-Box ID: %s\n  - %s" % (server_dict['onebox_id'], str(publicip_update_dict)))

                    if (server_dict.get('publicmac') is not None and old_info.get('public_mac') is not None) and (old_info.get('public_mac') != server_dict.get('publicmac')):
                        publicip_update_dict['publicmac'] = server_dict['publicmac']
                        publicip_update_dict['old_publicmac'] = old_info.get("public_mac")
                        log.debug("One-Box Public MAC Addresses are changed:\n  - One-Box ID: %s\n  - %s" % (server_dict['onebox_id'], str(publicip_update_dict)))

                    if (server_dict.get('ipalloc_mode_public') is not None and old_info.get('ipalloc_mode_public') is not None) and (
                            old_info.get('ipalloc_mode_public') != server_dict.get('ipalloc_mode_public')):
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
                        #     nsr_update_result, nsr_update_content = common_manager.update_nsr_by_obagent(mydb, server_info['nsseq'], update_info, use_thread=False)

                    # BEGIN : 사용안함 # 일단 False처리한다.
                    # if False and "publicip_update_dict" in update_info:
                    #
                    #     # log.debug("__________ Backup Start : publicip_update_dict = %s " % publicip_update_dict)
                    #
                    #     # 2. Disable Backup Data with old settings
                    #     log.debug("[****HJC******] Out-Of-Date One-Box Backup Data")
                    #     need_nsbackup = False
                    #
                    #     bd_update_condition = {'serverseq': server_dict['serverseq']}
                    #
                    #     if 'publicip' in publicip_update_dict or 'publicgwip' in publicip_update_dict \
                    #             or 'ipalloc_mode_public' in publicip_update_dict or 'publiccidr' in publicip_update_dict:
                    #
                    #         if server_dict.get('ipalloc_mode_public') == "STATIC" or 'ipalloc_mode_public' in publicip_update_dict:
                    #             log.debug("Disable NSR Backup Data")
                    #             need_nsbackup = True
                    #     else:
                    #         bd_update_condition['category'] = 'onebox'
                    #
                    #     # bd_update_result, bd_update_content = orch_dbm.update_backup_history(mydb, {'ood_flag':True}, bd_update_condition)
                    #     # if bd_update_result < 0:
                    #     #    log.warning("failed to disable old backup data")
                    #
                    #     # 3. Make a new Backup Data with new settings
                    #     # log.debug("__________ %s _new_server_thread >> backup_onebox START" % server_dict['onebox_id'])
                    #     try:
                    #         bo_result, bo_content = backup_onebox(mydb, {}, server_dict['onebox_id'], tid=None, tpath=None, use_thread=False)
                    #         if bo_result < 0:
                    #             log.error("failed to backup One-Box: %d %s" % (bo_result, bo_content))
                    #
                    #         # if server_info.get('nsseq') is not None and need_nsbackup == True:
                    #         #    nsb_result, nsb_content = _backup_nsr_api(server_info['nsseq'])
                    #         #    if nsb_result < 0:
                    #         #        log.error("failed to backup NSR: %d %s" %(nsb_result, nsb_content))
                    #     except Exception, e:
                    #         log.exception("__________ Exception: %s" % str(e))
                    #     # log.debug("__________ %s _new_server_thread >> backup_onebox END" % server_dict['onebox_id'])
                    #     # 4. update NSR backup file
                    #     # global global_config
                    # # END : 사용안함

                    # if server_info.get('nsseq') is not None and update_info and not is_wad:
                    #     try:
                    #         flag_chg_mac = None
                    #         is_wan_list = update_info.get("is_wan_list", False)
                    #         if is_wan_list:
                    #             if "chg_port_info" in update_info \
                    #                     and update_info["chg_port_info"].get("wan", None) \
                    #                     and update_info["chg_port_info"]["wan"].get("mac", None):
                    #                 flag_chg_mac = "MULTI"
                    #         else:
                    #             if 'publicmac' in publicip_update_dict:
                    #                 flag_chg_mac = "ONE"
                    #
                    #         if flag_chg_mac:
                    #
                    #             log.debug("Update Mac Address of NS backup file %s %s" % (str(server_info['nsseq']), str(publicip_update_dict)))
                    #
                    #             target_condition = {"nsseq": server_info['nsseq'], "category": "vnf", "ood_flag": False}
                    #             nsb_result, nsb_content = orch_dbm.get_backup_history(mydb, target_condition)
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
                    # error 시 tb_server status를 LINE_WAIT 로 만든다
                    server_dict['status'] = SRVStatus.LWT

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

                    # log.debug('server_dict = %s' %str(server_dict))

                    # server_dict['status'] = SRVStatus.RDS

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
            # noti_result, noti_data = first_notify_monitor(mydb, server_info)
            server_info['mgmt_ip'] = server_dict.get('mgmtip')
            server_info['wf_monitorconnector'] = plugins.get('wf_monitorconnector')
            noti_result, noti_data = orch_comm.getFunc("first_notify_monitor", server_info)
            if noti_result < 0:
                log.error("__________ Failed to notify monitor: %s" % noti_data)

        log.debug("[ARM : %s] Threading End!" % str(server_info['onebox_id']))

        return 200, "OK"


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


    def new_server_arm(self, server_info, plugins, use_thread=True, forced=False):
        """
        OneBox Agent / Onebox 복구 / reset_mac - 서버정보 업데이트 처리.
        :param server_info: request body정보
        :param plugins:
        :param use_thread: restore_onebox처리시 False
        :param forced: restore_onebox처리시 True
        :return:
        """

        old_info = {}
        # log.debug("[TEMP-HJC **********] server_info = %s" %str(server_info))
        # check if already reqistered server or not
        check_result, check_data = self._check_existing_servers(server_info)

        if check_result < 0:
            log.error("new_server() failed to check the registered servers %d %s" % (check_result, check_data))
            return check_result, check_data
        elif check_result == 0:
            return -HTTP_Bad_Request, "No Server : %s" % str(server_info)
        elif check_result > 1:
            log.error("new_server() there are two or more servers.")
            return -HTTP_Bad_Request, "Cannot Identify Server : %s" % str(server_info)
        elif check_result == 1:

            #################################   설치 중, 설정 변경 noti는 중지    S   ##########################################################
            # 이미 설치중, 백업 중일때 처리 중지 (설치 타이밍 이슈) - 설치 중에 설정 변경 할때마다 noti가 계속 들어와 중복으로 처리 되는 문제가 발생됨
            # 복구 시, 강제로 new_server() 를 날려주기 때문에 이 부분을 통과해야 한다
            # log.debug('[server status check] check_data = %s' %str(check_data))
            is_proc = False
            proc_status = ""

            if 'restore' not in server_info:
                if check_data['status'] == SRVStatus.LPV or check_data['status'] == SRVStatus.PVS:
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
                    log.debug("##########   new_server_arm() %s 중 이므로 처리 중지.....    #######################" % str(proc_status))
                    return 200, "Stop installation because it is being processed Server : %s" % str(proc_status)
            #################################   설치 중, 설정 변경 noti는 중지    E   ##########################################################

            log.debug('[KtArm] check_data = %s' %str(check_data))

            server_info['serverseq'] = check_data['serverseq']
            server_info['status'] = check_data['status']
            server_info['state'] = check_data['state']  # monitor state
            server_info['customerseq'] = check_data['customerseq']
            server_info['org_name'] = check_data['orgnamescode']
            server_info['onebox_id'] = check_data['onebox_id']
            server_info['serveruuid'] = check_data['serveruuid']
            server_info['action'] = check_data['action']

            # # Arm-Box 구분하기 위해 추가 : ex) nfsubcategory = OneBox or KtPnf or KtArm
            # server_info['nfsubcategory']=check_data[0]['nfsubcategory']

            # 복구중일때 agent call은 생략한다. (action = RS & forced = False)
            # action = RS & forced = True 인 경우는 복구 프로세스에서 강제 호출한 경우 : 생락안함.
            # if server_info['action'] == "RS" and forced is False:
            #     log.info("Pass processes by this API this time because The One-Box is restoring.")
            #     return 200, server_info['serverseq']

            if 'mgmt_ip' not in server_info and check_data.get('mgmtip') is not None:
                server_info['mgmt_ip'] = check_data['mgmtip']

            # server_info['nsseq'] = check_data[0]['nsseq']
            server_info['onebox_flavor'] = check_data['onebox_flavor']

            old_info = {"mgmt_ip": check_data['mgmtip'], "public_ip": check_data['publicip']
                , "public_mac": check_data['publicmac'], "ipalloc_mode_public": check_data['ipalloc_mode_public']}

            if check_data.get('publicgwip') is not None:
                old_info['publicgwip'] = check_data.get('publicgwip')
            if check_data.get('publiccidr') is not None:
                old_info['publiccidr'] = check_data.get('publiccidr')

            # 회선이중화 : 기존 wan list가 존재하는 경우
            if check_data.get('wan_list') is not None:
                old_info['wan_list'] = check_data.get('wan_list')
            if check_data.get('extra_wan_list') is not None:
                old_info['extra_wan_list'] = check_data.get('extra_wan_list')

            log.debug("===== OBA Call ===== [%s] DB Info : %s" % (server_info['onebox_id'], str(old_info)))

        try:
            if use_thread:
                th = threading.Thread(target=self._new_server_thread, args=(server_info, plugins, old_info, forced))
                th.start()
            else:
                return self._new_server_thread(server_info, plugins, old_info, forced)
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "One-Box 서버 등록이 실패하였습니다. 원인: %s" % str(e)

        return 200, server_info.get("serverseq", "NONE")



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
        result, data = orch_dbm.get_server_filters_wf(filter_dict)
        if result <= 0:
            return result, data
        elif len(data) > 1:
            return len(data), "%d oneboxes are found" % (len(data))
        else:  # 서버 정보가 정상적으로 1개만 조회되었을 경우
            return result, data[0]


    def _parse_server_info(self, server_info, orch_comm=None):
        """
        서버정보를 객체에 담아서 리턴
        :param server_info:
        :param orch_comm:
        :return: server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict
        """
        vim_dict = None
        vim_tenant_dict = None
        hardware_dict = None
        software_dict = None
        vnet_dict = None

        # log.debug("[HJC] IN: Server_info = %s" %str(server_info))

        server_dict = {'customerseq': server_info['customerseq'], 'onebox_id': server_info['onebox_id']}
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
            # TODO
            # 1. get flavor list from tb_onebox_flavor
            # 2. if exists, add value else add default
            server_dict['onebox_flavor'] = server_info['onebox_flavor']

        # # 5G router 사용 여부
        # if 'router' in server_info:
        #     server_dict['router'] = server_info['router']

        # if 'vim' in server_info:
        #     vim_dict = {'vimtypecode': server_info['vim']['vim_type'], 'authurl': server_info['vim']['vim_authurl']}
        #     vim_dict['name'] = server_dict['onebox_id'] + "_" + "VIM-OS1"
        #     vim_dict['display_name'] = server_info['vim']['vim_type'].split("-")[0]
        #     vim_dict['version'] = server_info['vim'].get("vim_version", "kilo")
        #     vim_tenant_dict = {'name': server_info['vim']['vim_tenant_name'], 'username': server_info['vim']['vim_tenant_username'], 'password': server_info['vim']['vim_tenant_passwd']}
        #     vim_tenant_dict['domain'] = "default"

        # vim 정보는 임시로 채워준다
        vim_dict = {'vimtypecode': 'OpenStack-ANode', 'authurl': None}
        vim_dict['name'] = server_dict['onebox_id'] + "_" + "VIM-OS1"
        vim_dict['display_name'] = 'OpenStack'
        vim_dict['version'] = None
        vim_tenant_dict = {'name': 'admin', 'username': 'admin', 'password': 'kt@ne130X', 'domain': 'default'}

        if 'hardware' in server_info:
            hardware_dict = {'model': server_info['hardware']['model']}
            hardware_dict['cpu'] = server_info['hardware'].get('cpu')
            hardware_dict['num_cpus'] = server_info['hardware'].get('num_cpus')
            hardware_dict['num_cores_per_cpu'] = server_info['hardware'].get('num_cores_per_cpu')
            hardware_dict['num_logical_cores'] = server_info['hardware'].get('num_logical_cores')
            hardware_dict['mem_size'] = server_info['hardware'].get('mem_size')

        if 'software' in server_info:
            software_dict = {'operating_system': server_info['software']['operating_system']}
            # if 'vnfm' in server_info:
            #     software_dict['onebox_vnfm_base_url'] = server_info['vnfm']['base_url']
            #     software_dict['onebox_vnfm_version'] = server_info['vnfm'].get('version', "0.0")
            #
            #     server_dict['vnfm_base_url'] = server_info['vnfm']['base_url']
            #
            #     # Get vnfm version
            #     server_dict['vnfm_version'] = "NOTSUPPORTED"
            #
            #     myvnfm = vnfmconnector.vnfmconnector(id=server_dict['servername'], name=server_dict['servername'], url=server_dict['vnfm_base_url'], mydb=mydb)
            #     result_ver, ver_dict = myvnfm.get_vnfm_version()
            #     if result_ver < 0:
            #         log.error("Failed to get vnfm version %s %s" % (result_ver, ver_dict))
            #     else:
            #         if ver_dict["version"] == "NOTSUPPORTED":
            #             server_dict['vnfm_version'] = "0.0"
            #         else:
            #             server_dict['vnfm_version'] = ver_dict["version"]
            #             software_dict['onebox_vnfm_version'] = ver_dict["version"]
            #     # server_dict['vnfm_version'] = server_info['vnfm'].get('version', "0.0")

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
            for idx in range(len(server_info["wan_list"]) - 1, -1, -1):
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
                wan["name"] = "R" + str(r_num)
                r_num += 1

                network_list.append({'name': wan['nic'], 'display_name': "wan"})

                # public_ip_dhcp 항목을 ipalloc_mode_public 형태로 변경처리
                if wan['public_ip_dhcp']:
                    wan['ipalloc_mode_public'] = "DHCP"
                else:
                    wan['ipalloc_mode_public'] = "STATIC"

        elif 'wan' in server_info:  # 회선 이중화 호환성 유지부분
            server_dict['publicmac'] = server_info['wan']['mac']
            if 'mode' in server_info['wan'] and 'nic' in server_info['wan']:
                server_dict['net_mode'] = server_info['wan']['mode']
                network_list.append({'name': server_info['wan']['nic'], 'display_name': "wan"})

        if 'lan_office' in server_info:
            if server_info['lan_office']['nic'] is not None:
                # nic이 여러개인경우 처리
                nic = server_info['lan_office']['nic']
                if nic is not None and len(nic.strip(" ")) > 0:
                    nics = nic.replace(" ", "").split(",")
                    for item in nics:
                        network_list.append({'name': item, 'display_name': "office"})

        if 'lan_server' in server_info:
            if server_info['lan_server']['nic'] is not None:
                # nic이 여러개인경우 처리
                nic = server_info['lan_server']['nic']
                if nic is not None and len(nic.strip(" ")) > 0:
                    nics = nic.replace(" ", "").split(",")
                    for item in nics:
                        network_list.append({'name': item, 'display_name': "server"})

        # # extra_wan_list 항목 처리
        # if 'extra_wan_list' in server_info and len(server_info["extra_wan_list"]) > 0:
        #     # check validation of wan list
        #     for idx in range(len(server_info["extra_wan_list"]) - 1, -1, -1):
        #         wan = server_info["extra_wan_list"][idx]
        #
        #         # public_ip, public_cidr_prefix 항목이 존재하지 않거나, 빈값이면 public_ip = NA, public_cidr_prefix = -1
        #         if wan.get("public_ip", None) is None:
        #             wan["public_ip"] = "NA"
        #         if wan.get("public_cidr_prefix", None) is None:
        #             wan["public_cidr_prefix"] = -1
        #
        #         # DHCP인 경우에 public_gw_ip가 없을 수 있다. 없는 경우 "NA" 처리
        #         if wan["public_ip_dhcp"]:
        #             if "public_gw_ip" not in wan or wan["public_gw_ip"] is None or wan["public_gw_ip"] == "":
        #                 wan["public_gw_ip"] = "NA"
        #         else:
        #             if "public_gw_ip" not in wan or wan["public_gw_ip"] is None or wan["public_gw_ip"] == "":
        #                 log.error("Empty public_gw_ip! If 'STATIC', public_gw_ip must be.")
        #                 wan["public_gw_ip"] = "NA"
        #
        #     server_dict["extra_wan_list"] = server_info["extra_wan_list"]
        #
        #     e_num = 0
        #     for wan in server_dict["extra_wan_list"]:
        #
        #         wan["status"] = "A"
        #
        #         # extra_wan_list 순서대로 E0~N 주는 방식으로 변경처리.
        #         wan["name"] = "E" + str(e_num)
        #         e_num += 1
        #
        #         network_list.append({'name': wan.get('nic'), 'display_name': "extra_wan"})
        #
        #         # public_ip_dhcp 항목을 ipalloc_mode_public 형태로 변경처리
        #         if wan.get('public_ip_dhcp'):
        #             wan['ipalloc_mode_public'] = "DHCP"
        #         else:
        #             wan['ipalloc_mode_public'] = "STATIC"

        try:
            if 'vnet' in server_info:

                vnet_dict = {}

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


        except Exception, e:
            log.exception("Exception: %s" % str(e))
            vnet_dict = None

        server_dict['state'] = server_info.get('state', "NOTSTART")

        # if 'network' in server_info and server_info['network'] != None:
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
                server_dict['status'] = SRVStatus.RIS
            # if vim_dict and vim_tenant_dict:
            #     server_dict['status'] = SRVStatus.RDS
            server_dict['status'] = SRVStatus.RDS

        elif server_dict['status'] == SRVStatus.RIS:
            # if vim_dict and vim_tenant_dict:
            #     server_dict['status'] = SRVStatus.RDS
            server_dict['status'] = SRVStatus.RDS

        elif server_dict['status'] == SRVStatus.DSC:
            if 'publicip' in server_dict:
                server_dict['status'] = SRVStatus.RIS

            # if vim_dict and vim_tenant_dict:
            #     server_dict['status'] = SRVStatus.RDS
            server_dict['status'] = SRVStatus.RDS

            # if server_info.get('nsseq') is not None:
            #     nsr_result, nsr_data = orch_dbm.get_nsr_id(server_info.get('nsseq'))
            #
            #     if nsr_result <= 0:
            #         log.warning("Failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
            #     else:
            #         if nsr_data.get('status', "UNDEFINED") == NSRStatus.RUN:
            #             server_dict['status'] = SRVStatus.INS
            #         elif nsr_data.get('status', "UNDEFINED") == NSRStatus.ERR:
            #             server_dict['status'] = SRVStatus.ERR
            #         else:
            #             log.error("NSR Status is unexpected: %s" % str(nsr_data.get('status')))
            #             server_dict['status'] = SRVStatus.ERR

        elif server_dict['status'] == SRVStatus.ERR:
            if server_info.get('nsseq') is None:
                if 'publicip' in server_dict:
                    server_dict['status'] = SRVStatus.RIS
                    log.debug("[HJC] Update Server Status to %s" % server_dict['status'])

                # if vim_dict and vim_tenant_dict:
                #     server_dict['status'] = SRVStatus.RDS
                #     log.debug("[HJC] Update Server Status to %s" % server_dict['status'])
                # else:
                #     log.debug("[HJC] Do not update Server Status")
                server_dict['status'] = SRVStatus.RDS
                log.debug("[HJC] Update Server Status to %s" % server_dict['status'])
            # else:
            #     nsr_result, nsr_data = orch_dbm.get_nsr_id(server_info.get('nsseq'))
            #     if nsr_result <= 0:
            #         log.error("failed to get NSR Info from DB: %d %s" % (nsr_result, nsr_data))
            #     else:
            #         if nsr_data.get('status', "UNDEFINED") == NSRStatus.RUN:
            #             server_dict['status'] = SRVStatus.INS
            #         else:
            #             log.debug("[HJC] Do not update Server Status in ERROR because there is a NS that is not RUNNING")

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
                if "noteCode" in note:  # 필수
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

        # return server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict
        return server_dict, vim_dict, vim_tenant_dict, hardware_dict, software_dict, network_list, vnet_dict


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

    def _check_server_validation(self, server_dict, hardware_dict=None, network_list=None, software_dict=None, mac_check=True):
        """
        서버의 유효성 체크, [new_server]
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
            ret_msg += "\n [MIP][%s] One-Box의 관리용 IP가 유효하지 않습니다. \n - 관리용 IP 주소: %s" % (str(datetime.datetime.now()), str(server_dict.get('mgmtip')))

        if mac_check:
            if server_dict.get('publicip') is None or af.check_valid_ipv4(server_dict.get('publicip')) == False:
                ret_result = -HTTP_Bad_Request
                ret_msg = "\n One-Box의 공인 IP가 유효하지 않습니다. %s" % str(server_dict.get('publicip'))

            if server_dict.get('publicgwip') is None or af.check_valid_ipv4(server_dict['publicgwip']) == False:
                ret_result = -HTTP_Bad_Request
                ret_msg += "\n [MIP][%s] One-Box의 공인 GW IP가 유효하지 않습니다. \n - GW IP 주소: %s" % (str(datetime.datetime.now()), str(server_dict.get('publicgwip')))

        # # Step 3. check public MAC
        # if server_dict.get('publicmac') is None or len(server_dict['publicmac']) < 3:
        #     ret_result = -HTTP_Bad_Request
        #     ret_msg += "\n [WMAC][%s] One-Box의 WAN NIC의 MAC 주소가 유효하지 않습니다. \n - MAC 주소: %s" % (str(datetime.datetime.now()), str(server_dict.get('publicmac')))
        # else:
        #     # TODO: Check Duplication of MAC & Public IP
        #     pass

        # 회선이중화 : wan_list에서 public_gw_ip 값이 "" 이거나 잘못된 값이면 예외처리
        if server_dict.get("wan_list", None):
            for wan in server_dict["wan_list"]:
                if not wan["public_ip_dhcp"]:  # STATIC인 경우
                    if wan.get("public_gw_ip", None) is None:
                        ret_result = -HTTP_Bad_Request
                        ret_msg += "\n [WGW][%s] One-Box의 WAN Public Gateway IP주소가 존재하지 않습니다." % (str(datetime.datetime.now()))
                        break
                    elif wan["public_gw_ip"] == "" or af.check_valid_ipv4(wan["public_gw_ip"]) == False:
                        ret_result = -HTTP_Bad_Request
                        ret_msg += "\n [WGW][%s] One-Box의 WAN Public Gateway IP주소가 유효하지 않습니다. \n - Gateway IP 주소: %s" % (
                        str(datetime.datetime.now()), str(wan["public_gw_ip"]))
                        break
        # if server_dict.get("extra_wan_list", None):
        #     for wan in server_dict["extra_wan_list"]:
        #         if not wan["public_ip_dhcp"]:  # STATIC인 경우
        #             if wan.get("public_gw_ip", None) is None:
        #                 ret_result = -HTTP_Bad_Request
        #                 ret_msg += "\n [WGW][%s] One-Box의 Extra WAN Public Gateway IP주소가 존재하지 않습니다." % (str(datetime.datetime.now()))
        #                 break
        #             elif wan["public_gw_ip"] == "" or af.check_valid_ipv4(wan["public_gw_ip"]) == False:
        #                 ret_result = -HTTP_Bad_Request
        #                 ret_msg += "\n [WGW][%s] One-Box의 Extra WAN Public Gateway IP주소가 유효하지 않습니다. \n - Gateway IP 주소: %s" % (
        #                 str(datetime.datetime.now()), str(wan["public_gw_ip"]))
        #                 break

        if ret_result < 0:
            return ret_result, ret_msg

        if mac_check:
            # public_ip = server_dict['publicip']
            public_mac = server_dict['publicmac']
            onebox_id = server_dict['onebox_id']

            # oob_result, oob_content = common_manager.get_server_all_with_filter(mydb, onebox_id)
            oob_result, oob_content = orch_dbm.get_server_id(onebox_id)
            if oob_result < 0:
                log.error("failed to get One-Box Info from DB: %d %s" % (oob_result, oob_content))
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
                        result_wan, wan_list = orch_dbm.get_server_wan_list(oob_content["serverseq"])
                        found_old_mac = False
                        if result_wan > 0:
                            for w in wan_list:
                                if w['mac'] == public_mac:
                                    log.debug("Valid MAC Address because it mached with %s" % str(w))
                                    found_old_mac = True
                                    break
                        elif result_wan <= 0:
                            log.debug("Failed to get WAN List for the One-Box: %s due to %d %s" % (onebox_id, result_wan, str(wan_list)))

                        if found_old_mac is False:
                            log.debug("Invalid One-Box Info: an One-Box ID cannot have different public MAC Address")
                            ret_result = -HTTP_Conflict
                            ret_msg += "\n [DOB][%s] 다른 MAC 주소의 One-Box 정보가 수신되었습니다. \n - 확인 필요한 One-Box의 IP주소: %s \n - One-Box 서버 교체의 경우 좌측 초기화 버튼을 실행해주세요." % (
                            str(datetime.datetime.now()), str(server_dict.get('mgmtip')))

                            # break

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
                    log.debug("One-Box HW Model is different from the Order: %s vs %s" % (hardware_dict['model'], order_hw_model))
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


    def _check_chg_wan_info(self, serverseq, old_wan_list, new_wan_list, is_wan_count_changed=False):
        """
        회선이중화 : wan_list 가 변경되었는지 체크, 변경정보를 찾고, 변경된 정보가 있으면, tb_server_wan에 update 후 chg_wan_info 리턴
        :param serverseq:
        :param old_wan_list:
        :param new_wan_list:
        :return: chg_wan_info
        """

        # chg_wan_info : 변경된 항목을 담아두는 객체. 변경 체크 항목과 변경된 항목 갯수 저장
        chg_wan_info = {"public_ip": {}, "public_cidr_prefix": {}, "public_gw_ip": {}, "ipalloc_mode_public": {}, "mac": {}, "nic": {}
            , "physnet_name": {}, "mode": {}, "status": {}, "parm_count": 0, "etc_count": 0, "old_mac": {}, "public_cidr_prefix_new": {}}

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
                    if old_wan["public_gw_ip"] != new_wan.get("public_gw_ip", None):  # STATIC인 경우 public_gw_ip가 없을수 있음.
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
        if not is_wan_count_changed:  # wan 갯수가 변경된 경우에는 update_server에서 이미 DB저장처리했으니까 업데이트 생략.
            if chg_wan_info["parm_count"] > 0 or chg_wan_info["etc_count"] > 0:
                for key1 in chg_wan_info.keys():
                    # tb_server_wan 업데이트할 column만 필터링(로직용 객체들은 제외시킨다.)
                    if key1 == "parm_count" or key1 == "etc_count" or key1 == "old_mac" or key1 == "public_cidr_prefix_new":
                        continue
                    for key2 in chg_wan_info[key1].keys():
                        log.debug("_##_ serverseq = %s, name = %s ==> %s = %s" % (serverseq, key2, key1, chg_wan_info[key1][key2]))
                        orch_dbm.update_server_wan({"serverseq": serverseq, "name": key2}, {key1: chg_wan_info[key1][key2]})

        return chg_wan_info


    def _check_chg_extra_wan_info(self, serverseq, old_wan_list, new_wan_list, is_wan_count_changed=False):
        """
        physnet_name 기준으로 변경체크
        :param serverseq:
        :param old_wan_list:
        :param new_wan_list:
        :param is_wan_count_changed:
        :return:
        """

        chg_wan_info = {"public_ip": {}, "public_cidr_prefix": {}, "public_gw_ip": {}, "ipalloc_mode_public": {}, "mac": {}, "nic": {}
            , "name": {}, "mode": {}, "status": {}, "parm_count": 0, "etc_count": 0, "old_mac": {}, "public_cidr_prefix_new": {}}

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
                    if old_wan["public_gw_ip"] != new_wan.get("public_gw_ip", None):  # STATIC인 경우 public_gw_ip가 없을수 있음.
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
        if not is_wan_count_changed:  # wan 갯수가 변경된 경우에는 update_server에서 이미 DB저장처리했으니까 업데이트 생략.
            if chg_wan_info["parm_count"] > 0 or chg_wan_info["etc_count"] > 0:
                for key1 in chg_wan_info.keys():
                    # tb_server_wan 업데이트할 column만 필터링(로직용 객체들은 제외시킨다.)
                    if key1 == "parm_count" or key1 == "etc_count" or key1 == "old_mac" or key1 == "public_cidr_prefix_new":
                        continue
                    for key2 in chg_wan_info[key1].keys():
                        log.debug("_##_ serverseq = %s, physnet_name = %s ==> %s = %s" % (serverseq, key2, key1, chg_wan_info[key1][key2]))
                        orch_dbm.update_server_wan({"serverseq": serverseq, "physnet_name": key2}, {key1: chg_wan_info[key1][key2]})

        return chg_wan_info

