# -*- coding: utf-8 -*-

from wfm.plugin_spec.WFNsrSpec import WFNsrSpec

import requests
import json
import sys
import time
import threading
import uuid as myUuid
from httplib import HTTPException
from requests.exceptions import ConnectionError

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

import db.dba_manager as orch_dbm
from utils.config_manager import ConfigManager

from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

from engine.server_status import SRVStatus
from engine.action_status import ACTStatus
# from image_status import ImageStatus
from engine.action_type import ActionType
from engine.nfr_status import NFRStatus
from engine.nsr_status import NSRStatus

from utils.e2e_logger import e2elogger, CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL

class WFNsr(WFNsrSpec):

    # order 등록
    def delete_nsr(self, req_info, plugins, need_stop_monitor=True, only_orch=False, use_thread=True, tid=None, tpath="", force_flag=False):
        log.debug('[WFNsr] delete_nsr Start............')
        log.debug('[WFNsr] req_info : %s' %str(req_info))

        # common plugin 사용
        # orch_comm = common_manager.common_manager(req_info)
        orch_comm = plugins.get('orch_comm')

        nsr_id = req_info.get('nsseq')

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

            # 기존 소스에서는 nsr_id 로 정보 조회하지만, PNF 의 경우 nsr 이 없으므로 onebox_id 로 정보 조회한다
            if req_info.get('onebox_type') == "KtPnf":
                # PNF type
                instanceDict = {}
                result = 200

                server_result, server_content = orch_dbm.get_server_filters(req_info)
            else:
                # Other type

                # Step 1. get scenario instance from DB
                log.debug("Check that the nsr_id exists and getting the instance dictionary")
                result, instanceDict = orch_dbm.get_nsr_id(nsr_id)
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

                # if e2e_log:
                #     e2e_log.job("Get scenario instance from DB", CONST_TRESULT_SUCC,
                #                 tmsg_body="Scenario instance Info : %s" % (json.dumps(instanceDict, indent=4)))

                # Step 2. update the status of the scenario instance to 'DELETING'

                server_result, server_content = orch_dbm.get_server_filters({"nsseq": nsr_id})

            if server_result <= 0:
                log.warning("failed to get server info %d %s" % (server_result, server_content))
                server_content = None
                raise Exception("Failed to get server info.: %d %s" % (server_result, server_content))
            else:
                server_data = server_content[0]

            if use_thread:
                # update_nsr_status(ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL, server_dict=server_data, server_status=SRVStatus.OOS)

                # PNF 의 경우 nsr 이 없으므로 분기 처리 하기 위해서 onebox_type을 변수에 추가 (PNF type은 nsr 관련 동작 안함)
                instanceDict['onebox_type'] = req_info.get('onebox_type')

                com_dict = {}
                com_dict['onebox_type'] = req_info.get('onebox_type')
                com_dict['action_type'] = ActionType.DELNS
                com_dict['nsr_data'] = instanceDict
                com_dict['action_status'] = NSRStatus.DEL
                com_dict['server_dict'] = server_data
                com_dict['server_status'] = SRVStatus.OOS
                com_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_nsr_status', com_dict)
                com_dict.clear()

            # thread 에 넘겨줄 기본 변수
            # instanceDict['onebox_id'] = req_info.get('onebox_id')     # TODO : 값 확인 후 넣어줄 방법 고민

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
                    th = threading.Thread(target=self._delete_nsr_thread,
                                          args=(instanceDict, server_data, plugins, need_stop_monitor, use_thread, force_flag, e2e_log, only_orch))
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
                return self._delete_nsr_thread(instanceDict, server_data, plugins, need_stop_monitor=need_stop_monitor, use_thread=False, force_flag=force_flag, e2e_log=e2e_log,
                                          only_orch=only_orch)
        except Exception, e:
            log.exception("Exception: %s" % str(e))

            # update_nsr_status(ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR,
            #                   nsr_status_description=str(e))

            com_dict = {}
            com_dict['action_type'] = ActionType.DELNS
            com_dict['action_dict'] = instanceDict
            com_dict['action_status'] = NSRStatus.ERR
            com_dict['server_dict'] = server_data
            com_dict['server_status'] = SRVStatus.ERR
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            if e2e_log:
                e2e_log.job('NS 종료', CONST_TRESULT_FAIL, tmsg_body="NS 삭제가 실패하였습니다. 원인: %s" % str(e))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)


    def _delete_nsr_thread(self, instanceDict, server_data, plugins, need_stop_monitor=True, use_thread=True, force_flag=False, e2e_log=None, only_orch=False):
        # Check One-Box connectivity
        onebox_chk_status = server_data['status']

        # common plugin 사용
        req_info = {'onebox_type' : server_data.get('nfsubcategory')}
        # orch_comm = common_manager.common_manager(req_info)
        orch_comm = plugins.get('orch_comm')

        try:
            wf_svr_dict = {'check_settings': None, 'onebox_id': server_data['onebox_id'], 'onebox_type': server_data.get('nfsubcategory'), 'force': True}
            wf_svr_dict['orch_comm'] = plugins.get('orch_comm')
            wf_svr_dict['wf_obconnector'] = plugins.get('wf_obconnector')

            # wf_server_manager = wfm_server_manager.server_manager(req_info)
            wf_server_manager = plugins.get('wf_server_manager')
            ob_chk_result, ob_chk_data = wf_server_manager.check_onebox_valid(wf_svr_dict)
            wf_svr_dict.clear()

            if ob_chk_result < 0:
                log.error("failed to check One-Box Status for %s" % server_data['onebox_id'])
                raise Exception("Failed to check a connection to One-Box")
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            onebox_chk_status = SRVStatus.DSC
            if force_flag is False:
                # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.DSC)

                com_dict = {}
                com_dict['onebox_type'] = req_info.get('onebox_type')
                com_dict['action_type'] = ActionType.DELNS
                com_dict['nsr_data'] = instanceDict
                com_dict['action_status'] = NSRStatus.ERR
                com_dict['server_dict'] = server_data
                com_dict['server_status'] = SRVStatus.DSC
                com_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_nsr_status', com_dict)
                com_dict.clear()

                return -HTTP_Internal_Server_Error, "Failed to check a connection to One-Box"

        try:
            if use_thread:
                if instanceDict.get('onebox_id') == "KtPnf":
                    log_info_message_name = server_data.get('onebox_id')
                else:
                    log_info_message_name = instanceDict.get('name')

                log_info_message = "Deleting NS - Thread Started (%s)" % log_info_message_name

                log.info(log_info_message.center(80, '='))

                if e2e_log:
                    e2e_log.job('NS 종료 Background Thread 시작', CONST_TRESULT_SUCC, tmsg_body=log_info_message)

            if need_stop_monitor:
                if use_thread:
                    # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL_stoppingmonitor)

                    if instanceDict.get('onebox_id') == "KtPnf":
                        # PNF type
                        pass
                    else:
                        # Other type
                        # com_dict = {}
                        # com_dict['onebox_type'] = req_info.get('onebox_type')
                        # com_dict['action_type'] = ActionType.DELNS
                        # com_dict['nsr_data'] = instanceDict
                        # com_dict['nsr_status'] = NSRStatus.DEL_stoppingmonitor
                        # com_dict['server_dict'] = None
                        # com_dict['server_status'] = None
                        #
                        # orch_comm.getFunc('update_nsr_status', com_dict)
                        # com_dict.clear()
                        pass

                if e2e_log:
                    e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_NONE, tmsg_body="NS 모니터링 종료 요청")

                # monitor_result, monitor_response = stop_nsr_monitor(mydb, instanceDict['nsseq'], e2e_log)
                com_dict = {}
                com_dict['serverseq'] = server_data.get('serverseq')
                com_dict['onebox_id'] = server_data.get('onebox_id')        # 21.04.09 추가 : 모니터 stop 시 DB 조회용(customerseq 로 조회시 문제가 있음)
                com_dict['onebox_type'] = server_data.get('nfsubcategory')
                com_dict['nsr_id'] = instanceDict.get('nsseq', None)
                com_dict['customerseq'] = server_data.get('customerseq')
                com_dict['e2e_log'] = e2e_log
                com_dict['del_vnfs'] = None
                com_dict['wf_monitorconnector'] = plugins.get('wf_monitorconnector')
                monitor_result, monitor_response = orch_comm.getFunc('stop_nsr_monitor', com_dict)
                com_dict.clear()

                if monitor_result < 0:
                    log.error("failed to stop monitor for %d: %d %s" % (instanceDict.get('nsseq', None), monitor_result, str(monitor_response)))
                    if e2e_log:
                        e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_FAIL,
                                    tmsg_body="NS 모니터링 종료 요청 실패\n원인: %d %s" % (monitor_result, monitor_response))
                        # return monitor_result, monitor_response
                else:
                    if e2e_log:
                        e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_SUCC,
                                    tmsg_body="NS 모니터링 종료 요청 완료")

            if use_thread:
                # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL_deletingvr)

                # PNF 에서는 ns가 없고, server status 변경이 없으면 pass
                # com_dict = {}
                # com_dict['onebox_type'] = req_info.get('onebox_type')
                # com_dict['action_type'] = ActionType.DELNS
                # com_dict['nsr_data'] = instanceDict
                # com_dict['nsr_status'] = NSRStatus.DEL_deletingvr
                # com_dict['server_dict'] = None
                # com_dict['server_status'] = None
                #
                # orch_comm.getFunc('update_nsr_status', com_dict)
                # com_dict.clear()
                pass

            if req_info.get('onebox_type') == "KtPnf":
                # PNF type
                pass
            else:
                # # return back license and request to finish VNF
                # if not only_orch: # TODO : 제어시스템에서만 삭제하는 조건 추가...
                #     if onebox_chk_status != SRVStatus.DSC:
                #         for vnf in instanceDict['vnfs']:
                #             if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
                #                 log.debug("[HJC] Deleting GiGA Office Solution for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
                #                 try:
                #                     go_result, go_content = _delete_nsr_GigaOffice(mydb, vnf, server_data['serverseq'], instanceDict['nsseq'], e2e_log)
                #                 except Exception, e:
                #                     log.exception("Exception: %s" % str(e))
                #                     go_result = -HTTP_Internal_Server_Error
                #                     go_content = None
                #
                #                 if go_result < 0:
                #                     log.warning("failed to finish GiGA Office Solution %s: %d %s" % (vnf['name'], go_result, go_content))
                #
                #             result, data = return_license(mydb, vnf.get('license'))
                #             if result < 0:
                #                 log.warning("Failed to return license back for VNF %s and License %s" % (vnf['name'], vnf.get('license')))
                #
                #             result, data = _finish_vnf_using_ktvnfm(mydb, server_data['serverseq'], vnf['vdus'], e2e_log)
                #
                #             if result < 0:
                #                 log.error("Failed to finish VNF %s: %d %s" % (vnf['name'], result, data))
                #                 if result == -HTTP_Not_Found:
                #                     log.debug("One-Box is out of control. Skip finishing VNFs")
                #                 else:
                #                     raise Exception("Failed to finish VNF %s: %d %s" % (vnf['name'], result, data))
                #
                #     # delete heat stack
                #     if onebox_chk_status != SRVStatus.DSC:
                #         time.sleep(10)
                #
                #         result, vims = get_vim_connector(mydb, instanceDict['vimseq'])
                #
                #         if result < 0:
                #             log.error("nfvo.delete_nsr_thread() error. vim not found")
                #             log.debug("One-Box is out of control. Skip deleting Heat Stack")
                #             #raise Exception("Failed to establish VIM connection: %d %s" % (result, vims))
                #         else:
                #             myvim = vims.values()[0]
                #
                #             cc_result, cc_content = myvim.check_connection()
                #             if cc_result < 0:
                #                 log.debug("One-Box is out of control. Skip deleting Heat Stack")
                #             else:
                #                 result, stack_uuid = myvim.delete_heat_stack_v4(instanceDict['uuid'], instanceDict['name'])
                #
                #                 if result == -HTTP_Not_Found:
                #                     log.error("Not exists. Just Delete DB Records")
                #                 elif result < 0:
                #                     log.error("failed to delete stack from Heat because of " + stack_uuid)
                #
                #                     if result != -HTTP_Not_Found:
                #                         raise Exception("failed to delete stack from Heat because of " + stack_uuid)
                #
                # result, c = orch_dbm.delete_nsr(mydb, instanceDict['nsseq'])
                #
                # if result < 0:
                #     log.error("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))
                #     raise Exception("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))

                pass

            server_data.pop('nsseq')

            if use_thread:
                com_dict = {}
                com_dict['onebox_type'] = req_info.get('onebox_type')
                com_dict['action_type'] = ActionType.DELNS
                com_dict['nsr_data'] = None
                com_dict['nsr_status'] = None

                if onebox_chk_status == SRVStatus.DSC:
                    # update_nsr_status(mydb, ActionType.DELNS, nsr_data=None, nsr_status=None, server_dict=server_data, server_status=SRVStatus.DSC)

                    com_dict['server_dict'] = server_data
                    com_dict['server_status'] = SRVStatus.DSC

                else:
                    # update_nsr_status(mydb, ActionType.DELNS, nsr_data=None, nsr_status=None, server_dict=server_data, server_status=SRVStatus.RDS)

                    com_dict['server_dict'] = server_data
                    com_dict['server_status'] = SRVStatus.RDS

                com_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_nsr_status', com_dict)
                com_dict.clear()

            if not only_orch:
                # resume_monitor_wan 처리를 명시적으로 해준다.
                # result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=server_data['onebox_id'])

                # TODO : 삭제일때, 초소형의 경우는 agent 에 삭제 관련 api 호출 필요한지 검토
                if req_info['onebox_type'] == "KtPnf":
                    # PNF type
                    pass
                else:
                    # Other type
                    # comm_dict = {'onebox_id': server_data['onebox_id'], 'onebox_type': req_info['onebox_type']}
                    # result, ob_agents = orch_comm.getFunc('get_onebox_agent', comm_dict)
                    #
                    # if result < 0:
                    #     log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
                    #     return result, str(ob_agents)
                    #
                    # myoba = ob_agents.values()[0]
                    # rs_result, rs_content = myoba.resume_monitor_wan()
                    # if rs_result < 0:
                    #     log.error("Failed to resume monitoring WAN of the One-Box: %d %s" %(rs_result, rs_content))
                    pass

            if use_thread:
                log_info_message = "Deleting NS - Thread Finished (%s)" % instanceDict.get('name')
                log.info(log_info_message.center(80, '='))

            if e2e_log:
                e2e_log.job('NS 종료 처리 완료', CONST_TRESULT_SUCC, tmsg_body="NS 종료 처리 완료")
                e2e_log.finish(CONST_TRESULT_SUCC)

            return 1, 'NSR ' + str(instanceDict.get('nsseq')) + ' deleted'

        except Exception, e:
            if use_thread:
                log_info_message = "Deleting NS - Thread Finished with Error Exception: %s" % str(e)
                log.exception(log_info_message.center(80, '='))
            else:
                log.exception("Exception: %s" % str(e))

            com_dict = {}
            com_dict['onebox_type'] = req_info.get('onebox_type')
            com_dict['action_type'] = ActionType.DELNS
            com_dict['nsr_data'] = instanceDict
            com_dict['nsr_status'] = NSRStatus.DEL_deletingvr
            com_dict['server_dict'] = None

            if onebox_chk_status == SRVStatus.DSC:
                # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.DSC)

                com_dict['server_status'] = SRVStatus.DSC
            else:
                # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR)

                com_dict['server_status'] = SRVStatus.ERR

            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            if e2e_log:
                e2e_log.job('NS 종료 처리 실패', CONST_TRESULT_FAIL, tmsg_body=str(e))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)
