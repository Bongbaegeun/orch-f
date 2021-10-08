# coding=utf-8

import json
import time, datetime
import threading
import sys
import random
import base64
from scp import SCPClient
import os, commands

from utils import auxiliary_functions as af
from wfm.plugin_spec.WFActSpec import WFActSpec

from utils.config_manager import ConfigManager

from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import db.dba_manager as orch_dbm

from utils.e2e_logger import e2elogger, CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from engine.server_status import SRVStatus
from engine.action_status import ACTStatus
from engine.nsr_status import NSRStatus
from engine.action_type import ActionType

from engine.nsr_manager import handle_default_nsr

global global_config


class WFAct(WFActSpec):
    def get_version(self):
        return 2

    # Backup process
    def backup(self, req_info, plugins, use_thread=True):
        log.debug('[WF - Action] Backup Start............')

        log.debug('[WF - Action] req_info = %s' %str(req_info))

        # tpath = None

        orch_comm = plugins.get('orch_comm')

        try:
            # Step.1 Check arguments
            backup_settings = req_info['backup']

            if req_info['onebox_id'] is None:
                log.error("One-Box ID is not given")
                return -HTTP_Bad_Request, "One-Box ID is required."

            if req_info.get('tid') is not None:
                action_tid = req_info.get('tid')
            else:
                action_tid = af.create_action_tid()

            if req_info.get('tpath') is None:
                tpath = "/orch_onebox-backup"
            else:
                tpath = req_info.get('tpath') + "/orch_onebox-backup"

            log.debug("[WF - Action] Action TID : %s, TPATH : %s" % (action_tid, tpath))

            # Step.2 Get One-Box info. and check status
            ob_result, ob_data = orch_dbm.get_server_id(req_info['onebox_id'])  # common_manager.get_server_all_with_filter(mydb, onebox_id)
            if ob_result <= 0:
                log.error("[WF - Action] get_server_with_filter Error : server_id = %s, %d %s" % (req_info['onebox_id'], ob_result, ob_data))
                return ob_result, ob_data

            # ob_data = ob_content[0]

            if ob_data['status'] == SRVStatus.LWT or ob_data['status'] == SRVStatus.PVS or ob_data['status'] == SRVStatus.OOS or ob_data['status'] == SRVStatus.ERR:
                return -HTTP_Bad_Request, "Cannot backup the One-Box in the status of %s" % (ob_data['status'])

            if ob_data['action'] is None or ob_data['action'].endswith("E"):  # NGKIM: Use RE for backup
                pass
            else:
                return -HTTP_Bad_Request, "The One-Box is in Progress for another action: status= %s action= %s" % (ob_data['status'], ob_data['action'])

            ob_org_status = ob_data['status']

            # Step.3 Update One-Box status
            action_dict = {'tid': action_tid}
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
            error_msg = "failed invoke a Thread for backup VNF %s" % str(e)
            log.exception(error_msg)
            return -HTTP_Internal_Server_Error, error_msg

        try:
            comm_dict = {}
            comm_dict['actiontype'] = ActionType.BACUP
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.STRT
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = SRVStatus.OOS
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            # Step 4. Start One-Box backup
            if use_thread:
                th = threading.Thread(target=self._backup_onebox_thread, args=(req_info, ob_data, ob_org_status, action_dict, plugins, backup_settings, e2e_log, True))
                th.start()

                return_data = {"backup": "OK", "status": "DOING"}
            else:
                return self._backup_onebox_thread(req_info, ob_data, ob_org_status, action_dict, plugins, backup_settings, e2e_log=e2e_log, use_thread=False)
        except Exception, e:
            log.exception("Exception: %s" % str(e))

            comm_dict = {}
            comm_dict['actiontype'] = ActionType.BACUP
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.FAIL
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = ob_org_status
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            return -HTTP_Internal_Server_Error, "One-Box 백업이 실패하였습니다. 원인: %s" % str(e)

        return 200, return_data


    # Backup Thread
    def _backup_onebox_thread(self, req_info, ob_data, ob_org_status, action_dict, plugins, backup_settings={}, e2e_log=None, use_thread=True):

        if use_thread:
            log.debug("[WF - Action] THREAD START...........")

        is_onebox_backup_successful = True

        global global_config

        onebox_id = req_info['onebox_id']
        orch_comm = plugins.get('orch_comm')
        wf_obconnector = plugins.get('wf_obconnector')

        try:
            # Step.1 initialize variables

            # Step.2 Get One-Box Agent connector
            # result, ob_agents = len(wf_obconnector), wf_obconnector
            result, ob_agents = 1, wf_obconnector

            log.debug('[Action :: Backup] result = %d' % result)

            if result < 0:
                log.error("Error. One-Box Agent not found")
                log.debug("Error. One-Box Agent not found")
                is_onebox_backup_successful = False
            elif result > 1:
                is_onebox_backup_successful = False
                log.error("Error. Several One-Box Agents available, must be identify")
                log.debug("Error. Several One-Box Agents available, must be identify")

            log.debug("[WF - Action] D__________0 %s _backup_onebox_thread >> get_onebox_agent" % ob_data['onebox_id'])

            # One-Box agent load failed
            if is_onebox_backup_successful is False:
                comm_dict = {}
                comm_dict['actiontype'] = ActionType.BACUP
                comm_dict['action_dict'] = action_dict
                comm_dict['action_status'] = ACTStatus.FAIL
                comm_dict['ob_data'] = ob_data
                comm_dict['ob_status'] = ob_org_status
                comm_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_onebox_status_internally', comm_dict)
                comm_dict.clear()

                if e2e_log:
                    e2e_log.job('One-Box backup Fail', CONST_TRESULT_FAIL,
                                tmsg_body="serverseq: %s\nResult: One-Box backup이 실패하였습니다. 원인: %s" % (
                                str(ob_data['serverseq']), "Cannot establish One-Box Agent Connector"))
                    e2e_log.finish(CONST_TRESULT_FAIL)

                return -HTTP_Not_Found, "Cannot establish One-Box Agent Connector"

            # ob_agent = ob_agents.values()[0]

            # Step.3 Update One-Box status
            comm_dict = {}
            comm_dict['actiontype'] = ActionType.BACUP
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.INPG
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = SRVStatus.OOS
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            log.debug("[WF - Action] D__________1 %s _backup_onebox_thread >> update_onebox_status_internally : ACTStatus.INPG:%s" % (ob_data['onebox_id'], ACTStatus.INPG))

            # Step.4 Backup One-Box
            result = 200
            backup_content = None

            # 4-1. composing backup request info

            cfgManager = ConfigManager.get_instance()
            config = cfgManager.get_config()
            cfg_backup_server = config["backup_server"]
            cfg_backup_repository = config["backup_repository"]

            req_dict = {"onebox_id": ob_data['onebox_id']}
            req_dict['name'] = ob_data.get('onebox_id')
            req_dict['obagent_base_url'] = ob_data.get('obagent_base_url')
            req_dict['onebox_type'] = "General"
            req_dict['tid'] = None
            req_dict['tpath'] = None
            req_dict['backup_server'] = backup_settings.get('backup_server', cfg_backup_server)

            # log.debug('[Action] Backup : backup_onebox call > req_dict = %s' % str(req_dict))

            if af.check_valid_ipv4(req_dict['backup_server']) is False:
                req_dict['backup_server'] = cfg_backup_server

            req_dict['remote_location'] = cfg_backup_repository
            req_dict['local_location'] = cfg_backup_repository

            # if 'backup_location' in backup_settings:
            #     req_dict['backup_location'] = backup_settings['backup_location']
            #
            # if 'local_location' in backup_settings:
            #     req_dict['local_location'] = cfg_backup_server_local

            log.debug('[WFAct] req_dict = %s' %str(req_dict))

            # log.debug("D__________2 %s _backup_onebox_thread >> ob_agent.backup_onebox BEFORE: req_dict = %s" % (ob_data['onebox_id'],req_dict))

            # backup_result, backup_data = ob_agent.backup_onebox(req_dict)
            backup_result, backup_data = ob_agents.onebox_backup(req_dict)

            # log.debug('[WF - Action] Backup > backup_result = %d, backup_data = %s' %(backup_result, str(backup_data)))

            if backup_result < 0:
                # result = backup_result
                # log.error("Failed to backup One-Box %s: %d %s" %(ob_data['onebox_id'], backup_result, backup_data))
                # common_manager.update_onebox_status_internally(mydb, "B", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)
                # return result, backup_data
                raise Exception("[WF - Action] Failed to backup One-Box %s: %d %s" % (ob_data['onebox_id'], backup_result, backup_data))
            # elif backup_data.get('backup_data') is None:
            #     # log.error("No Backup Data in the response from One-Box Agent")
            #     # return -HTTP_Internal_Server_Error, "No Backup Data in the response from One-Box Agent"
            #     raise Exception("No Backup Data in the response from One-Box Agent")
            elif backup_data.get('result') is "FAIL":
                raise Exception("[WF - Action] No Backup Data in the response from One-Box Agent")
            else:
                log.debug("[WF - Action] Completed to send backup command to the One-Box Agent for %s" % (ob_data['onebox_id']))
                # common_manager.update_onebox_status_internally(mydb, "B", action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data, ob_status=ob_org_status)

                # 저장 하기 위해서 backup_content 의 backup_file(base64 encoding 된 data 압축파일)을 변수에 저장 후, 배열에서 빼낸다
                backup_file = backup_data.get('backup_file')
                backup_data.pop('backup_file')

                # backup directory 변경 (실제 mount 된 서버는 동일 /var/onebox/backup, 로컬만 변경) : /var/onebox/backup -> /var/onebox/backup_pnf
                tmp_remote_location = backup_data['remote_location']
                tmp_remote_location = tmp_remote_location.replace('/var/onebox/backup', '/var/onebox/backup_pnf')
                backup_data['remote_location'] = tmp_remote_location

                backup_content = json.dumps(backup_data, indent=4)

            # log.debug("D__________3 %s _backup_onebox_thread >> ob_agent.backup_onebox AFTER: result = %d %s" % (ob_data['onebox_id'], backup_result, backup_data))

            if e2e_log:
                e2e_log.job('Backup One-Box by Agent', CONST_TRESULT_SUCC,
                            tmsg_body="onebox_id: %s\nBackup Contents:%s" % (str(ob_data['onebox_id']), backup_content))

            # 4-2. DB insert: backup info
            backup_dict = {'serverseq': ob_data['serverseq'], 'nsseq': ob_data['nsseq'], 'category': "onebox"}
            backup_dict['server_name'] = ob_data['onebox_id']
            backup_dict['backup_server'] = req_dict['backup_server']
            backup_dict['backup_location'] = backup_data.get('remote_location')
            backup_dict['backup_local_location'] = backup_data.get('local_location')
            backup_dict['description'] = "One-Box %s backup file" %str(req_dict['onebox_type'])
            backup_dict['creator'] = backup_settings.get('user', "admin")
            backup_dict['trigger_type'] = backup_settings.get('trigger_type', "manual")
            backup_dict['status'] = "Completed"
            backup_dict['backup_data'] = backup_content
            
            # web download 경로 변경(웹에서 config 파일만 직접 다운로드 처리 하기로 함) - 변경은 하지만 PNF 형태에서는 의미없음
            backup_dict['download_url'] = "http://" + backup_dict['backup_server'] + backup_dict['backup_location'].replace("/var/onebox/backup", "/backup", 1)

            db_result, db_data = orch_dbm.insert_backup_history(backup_dict)
            if db_result < 0:
                raise Exception("[WF - Action] Failed to insert backup history into DB : %d %s" % (db_result, db_data))

            # log.debug("D__________4 %s _backup_onebox_thread >> insert_backup_history END" % ob_data['onebox_id'])

            if e2e_log:
                e2e_log.job('Insert backup history to DB', CONST_TRESULT_SUCC,
                            tmsg_body="serverseq: %s\nInserted data:%s" % (str(ob_data['serverseq']), backup_dict))

            # 4-3. base64 decode and save backup file to repo server(using scp)
            self._base64_decode_save(backup_data, backup_file)

            # 4-4. update One-Box status and record action history
            comm_dict = {}
            comm_dict['actiontype'] = ActionType.BACUP
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.SUCC
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = ob_org_status
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            log.debug("[WF - Action] D__________SUCC %s _backup_onebox_thread >> END" % str(ob_data['onebox_id']))

            if e2e_log:
                e2e_log.job('One-Box Backup Finished', CONST_TRESULT_SUCC, tmsg_body="")
                e2e_log.finish(CONST_TRESULT_SUCC)

        except Exception, e:
            log.error("[WF - Action] D__________E %s : %s" % (str(ob_data['onebox_id']), str(e)))

            # is_onebox_backup_successful = False

            comm_dict = {}
            comm_dict['actiontype'] = ActionType.BACUP
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.FAIL
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = ob_org_status
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            if e2e_log:
                e2e_log.job('One-Box backup Fail', CONST_TRESULT_FAIL,
                            tmsg_body="serverseq: %s\nResult: One-Box backup이 실패하였습니다. 원인: %s" % (str(ob_data['serverseq']), str(e)))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, str(e)

        if use_thread:
            log.debug("[WF - Action] THREAD FINISHED.................")

        return 200, "OK"

    # Restore process
    def restore(self, req_info, plugins, use_thread=True):
        log.debug('[WF] Restore Start............')

        log.debug('[WF] req_info = %s' %str(req_info))

        e2e_log = None
        onebox_id = None
        request = req_info.get('restore')

        try:
            # Step.1 Check arguments and initialize variables
            if req_info.get('onebox_id') is None:
                log.error("One-Box ID is not given")
                raise Exception(-HTTP_Bad_Request, "One-Box ID is required.")

            try:
                if not req_info.get('tid'):
                    e2e_log = e2elogger(tname='One-Box Restore', tmodule='orch-f', tpath="orch_onebox-restore")
                else:
                    e2e_log = e2elogger(tname='One-Box Restore', tmodule='orch-f', tid=req_info.get('tid'), tpath=req_info.get('tpath') + "/orch_onebox-restore")
            except Exception, e:
                log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
                e2e_log = None

            if e2e_log:
                e2e_log.job('One-Box 복구 API Call 수신 처리 시작', CONST_TRESULT_SUCC,
                            tmsg_body="Server ID: %s\nOne-Box Restore Request Body:%s" % (str(req_info.get('onebox_id')), json.dumps(request, indent=4)))
                action_tid = e2e_log['tid']
            else:
                action_tid = self._generate_action_tid()

            # Step.2 Get One-Box info and Check Status
            ob_result, ob_content = orch_dbm.get_server_id(req_info.get('onebox_id'))
            if ob_result <= 0:
                log.error("get_server_all_with_filter Error %d %s" % (ob_result, ob_content))
                raise Exception(ob_result, ob_content)

            onebox_id = ob_content["onebox_id"]

            # if ob_data['status'] == SRVStatus.LWT or ob_data['status'] == SRVStatus.PVS or ob_data['status'] == SRVStatus.OOS or ob_data['status'] == SRVStatus.DSC:
            if ob_content['status'] == SRVStatus.LWT or ob_content['status'] == SRVStatus.PVS:
                raise Exception(-HTTP_Bad_Request, "Cannot restore the One-Box in the status of %s" % (ob_content['status']))

            if ob_content['action'] is None or ob_content['action'].endswith("E"):  # NGKIM: Use RE for backup
                pass
            else:
                raise Exception(-HTTP_Bad_Request, "The One-Box is in Progress for another action: status= %s action= %s" % (ob_content['status'], ob_content['action']))

            if e2e_log:
                e2e_log.job('Get One-Box info and Check Status', CONST_TRESULT_SUCC,
                            tmsg_body="One-Box ID: %s\nOne-Box DB DATA:%s" % (str(onebox_id), ob_content))

            # Step.3 Get backup info
            target_dict = {'serverseq': ob_content['serverseq']}

            if 'backup_id' in request and len(request['backup_id']) > 0:
                target_dict['backupseq'] = request['backup_id']
                backup_result, backup_data = orch_dbm.get_backup_history_id(target_dict)
            else:
                target_dict['category'] = 'onebox'
                backup_result, backup_data = orch_dbm.get_backup_history_lastone(target_dict)

            if backup_result < 0:
                log.warning("Failed to get backup history for %d %s" % (backup_result, backup_data))
                raise Exception(-HTTP_Bad_Request, "Cannot find a Backup File")
            elif backup_result == 0:
                log.debug("No One-Box Backup Data found: %d %s" % (backup_result, str(backup_data)))
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
            request_data = {"user": request.get("user", "admin"), "mgmt_ip": request.get('mgmt_ip'), "tid": action_tid}

            if request.get("wan_mac", None):
                request_data["wan_mac"] = request.get("wan_mac", None)

            # Step.4 Start restoring One-Box Thread
            th = threading.Thread(target=self._restore_onebox_thread, args=(req_info, onebox_id, ob_content, plugins, request_data, backup_data, True, e2e_log))
            th.start()

            return_data = {"restore": "OK", "status": "DOING"}
        except Exception, e:
            log.warning("Exception: %s" % str(e))
            if e2e_log:
                e2e_log.job('One-Box 복구 Thread 시작 실패', CONST_TRESULT_FAIL, tmsg_body=None)
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "One-Box 복구가 실패하였습니다. 원인: %s" % str(e)

        return 200, return_data


    # Restore Thread
    def _restore_onebox_thread(self, req_info, onebox_id, ob_data, plugins, request_data, backup_data=None, use_thread=True, e2e_log=None):

        log.debug("[_RESTORE_ONEBOX_THREAD - %s] BEGIN" % onebox_id)

        action_dict = {'tid': request_data["tid"]}
        action_dict['category'] = "OBRestore"
        action_dict['action_user'] = request_data["user"]
        action_dict['server_name'] = ob_data['servername']
        action_dict['server_seq'] = ob_data['serverseq']

        orch_comm = plugins.get('orch_comm')

        try:
            ob_org_status = ob_data["status"]

            comm_dict = {}
            comm_dict['actiontype'] = ActionType.RESTO
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.STRT
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = SRVStatus.OOS
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            # get_onebox_info request dict
            info_dict = {}
            info_dict['onebox_id'] = onebox_id
            info_dict['obagent_base_url'] = ob_data.get('obagent_base_url')

            # Step.1 initialize variables
            is_agent_successful = True

            # Step.2 Get One-Box Agent Connector
            wf_obconnector = plugins.get('wf_obconnector')
            # result, ob_agents = len(wf_obconnector), wf_obconnector
            result, ob_agents = 1, wf_obconnector

            if result < 0:
                log.error("Error. One-Box Agent not found")
                is_agent_successful = False
            elif result > 1:
                log.error("Error. Several One-Box Agents available, must be identify")
                is_agent_successful = False

            if is_agent_successful is False:
                ob_data_temp = {"serverseq": action_dict["server_seq"]}

                comm_dict = {}
                comm_dict['actiontype'] = ActionType.RESTO
                comm_dict['action_dict'] = action_dict
                comm_dict['action_status'] = ACTStatus.FAIL
                comm_dict['ob_data'] = ob_data_temp
                comm_dict['ob_status'] = ob_org_status
                comm_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_onebox_status_internally', comm_dict)
                comm_dict.clear()

                raise Exception("Cannot establish One-Box Agent Connector")

            # ob_agent = ob_agents.values()[0]

            if e2e_log:
                e2e_log.job('Get One-Box Agent Connector', CONST_TRESULT_SUCC, tmsg_body="onebox_id: %s\nob_agents:%s" % (onebox_id, ob_agents))

            if request_data.get('mgmt_ip') is not None:
                is_change_server_info = False
                server_dict = {"serverseq": ob_data["serverseq"]}

                # tb_server mgmt_ip 와 다르면 agent 접속을 위해 obagent_base_url 만 변경처리, mgmt_ip는 new_server에서 처리하도록 한다(모니터링 업데이트)
                if request_data['mgmt_ip'] != ob_data["mgmtip"]:
                    is_change_server_info = True

                    old_obagent_base_url = ob_data["obagent_base_url"]
                    new_obagent_base_url = request_data['mgmt_ip']
                    if old_obagent_base_url.find("://") >= 0:
                        new_obagent_base_url = old_obagent_base_url[0:old_obagent_base_url.index("://") + 3] + new_obagent_base_url

                    if old_obagent_base_url.find(":", 7) >= 0:
                        new_obagent_base_url += old_obagent_base_url[old_obagent_base_url.index(":", 7):]

                    server_dict["obagent_base_url"] = new_obagent_base_url
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] Update obagent_base_url:%s" % (onebox_id, new_obagent_base_url))

                if request_data.get("wan_mac", None) and request_data['wan_mac'] != ob_data["publicmac"]:
                    is_change_server_info = True
                    server_dict["publicmac"] = request_data['wan_mac']
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] Update publicmac:%s" % (onebox_id, request_data['wan_mac']))

                if is_change_server_info:
                    result, content = orch_dbm.update_server(server_dict)
                    if result < 0:
                        log.error("failed to update the server %d %s" % (result, content))

                    #############################################################################################################################
                    # one-box 정보를 직접 얻어와서 new_server 호출
                    # - server, vim, monitor update 필요
                    # - 뒷단에서 _restore_nsr_reprov 하면서 NS는 새로 구성하므로 변경 프로세스는 수행하지 않아도 된다.
                    #
                    time.sleep(5)  # agent가 아직 부팅되지 않았거나, 정보를 제대로

                    result, server_info = ob_agents.get_onebox_info(info_dict)
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] The result of getting onebox info: %d %s" % (onebox_id, result, str(server_info)))

                    if result < 0:
                        # log.error("Failed to get onebox info from One-Box Agent: %d %s" %(result, server_info))
                        raise Exception("Failed to get onebox info from One-Box Agent: %d %s" % (result, server_info))

                    # public_ip, mgmt_ip 정보 validation check
                    if server_info.get("public_ip") is None or server_info.get("mgmt_ip") is None:
                        time.sleep(10)

                        log.debug("_____ Try getting onebox info again")

                        result, server_info = ob_agents.get_onebox_info(info_dict)

                        log.debug("[_RESTORE_ONEBOX_THREAD - %s] The result of getting onebox info: %d %s" % (onebox_id, result, str(server_info)))

                        if result < 0:
                            raise Exception("Failed to get onebox info from One-Box Agent: %d %s" % (result, server_info))

                        if server_info.get("public_ip") is None or server_info.get("mgmt_ip") is None:
                            raise Exception("IP data from agent is wrong!!!")

                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ First NEW_SERVER _____ BEGIN" % onebox_id)

                    su_result, su_data = plugins.get('wf_server_manager').new_server(server_info, plugins, use_thread=False, forced=True)

                    if su_result < 0:
                        log.error("Failed to update One-Box Info: %d %s" % (su_result, su_data))
                        raise Exception("Failed to update One-Box Info: %d %s" % (su_result, su_data))
                    else:
                        log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ First NEW_SERVER _____ END" % onebox_id)
                    #############################################################################################################################

            # DB server 정보 조회 : 변경된 정보가 있을 수 있어서 다시 조회한다.
            # ob_result, ob_content = common_manager.get_server_all_with_filter(mydb, onebox_id)  # 뒷단에 vims 정보를 활용하므로 이 함수로 호출

            comm_dict = {}
            comm_dict['onebox_id'] = onebox_id
            comm_dict['onebox_type'] = req_info.get('onebox_type')

            ob_result, ob_content = orch_comm.getFunc('get_server_all_with_filter', comm_dict)
            comm_dict.clear()

            if ob_result <= 0:
                log.error("get_server_all_with_filter Error %d %s" % (ob_result, ob_content))
                raise Exception("get_server_all_with_filter Error %d %s" % (ob_result, ob_content))

            ob_data = ob_content[0]

            # Step.3 Stop One-Box Monitoring >>>>> Change to call Suspend One-Box Monitoring
            # som_result, som_data = suspend_onebox_monitor(mydb, ob_data, e2e_log)


            # TODO : PNF 의 경우 monitor suspend 일단 pass
            # comm_dict = {}
            # comm_dict['ob_data'] = ob_data
            # comm_dict['e2e_log'] = e2e_log
            #
            # som_result, som_data = orch_comm.getFunc('suspend_onebox_monitor', comm_dict)
            # comm_dict.clear()
            #
            # if som_result < 0:
            #     log.warning("Failed to stop One-Box monitor. False Alarms are expected")
            #
            # if e2e_log:
            #     e2e_log.job('Suspend One-Box Monitoring', CONST_TRESULT_SUCC, tmsg_body=None)


            # Step.4 Remove NSR
            comm_dict = {}
            comm_dict['actiontype'] = ActionType.RESTO
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.INPG
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = SRVStatus.OOS
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            # nsr 관련 처리 안에 nsr monitor 는 PNF의 경우 무시한다
            if req_info.get('onebox_type') == "KtPnf":
                # PNF type
                pass
            else:
                # Other type

                # is_nsr_exist = True
                # nsr_check_result, nsr_check_data = _check_nsr_exist(mydb, ob_data)
                # if nsr_check_result < 0:
                #     log.warning("failed to check NSR in the One-Box: %d %s" % (nsr_check_result, nsr_check_data))
                # else:
                #     is_nsr_exist = nsr_check_data.get("nsr_exist", True)
                #
                # nsr_name = None
                #
                # if is_nsr_exist:
                #     nsr_data = nsr_check_data["nsr_data"]
                #     nsr_name = nsr_data["name"]
                #
                #     update_nsr_status(mydb, ActionType.RESTO, nsr_data=nsr_data, nsr_status=NSRStatus.RST)
                #
                #     log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_DELETE _____ BEGIN" % onebox_id)
                #     dnsr_result, dnsr_data = _restore_nsr_delete(mydb, nsr_data, ob_data['serverseq'], False, e2e_log=e2e_log)
                #     if dnsr_result < 0:
                #         log.error("failed to delete NSR: %d %s" % (dnsr_result, dnsr_data))
                #         update_nsr_status(mydb, ActionType.RESTO, nsr_data=nsr_data, nsr_status=NSRStatus.ERR)
                #         raise Exception("failed to delete NSR: %d %s" % (dnsr_result, dnsr_data))
                #     log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_DELETE _____ END" % onebox_id)
                #     if e2e_log:
                #         e2e_log.job('Remove NSR', CONST_TRESULT_SUCC, tmsg_body=None)
                pass

            if backup_data is not None:
                # Step.5 Request Restoring One-Box to the One-Box Agent
                # 5-1 Compose Request Message
                req_dict = {"onebox_id": ob_data['onebox_id']}
                req_dict['obagent_base_url'] = ob_data.get('obagent_base_url')

                action_dict['server_backup_seq'] = backup_data['backupseq']
                req_dict['backup_server'] = backup_data["backup_server"]
                if 'backup_location' in backup_data: req_dict['backup_location'] = backup_data["backup_location"]
                if 'backup_local_location' in backup_data: req_dict['backup_local_location'] = backup_data["backup_local_location"]
                # if 'backup_data' in backup_data: req_dict['backup_data'] = backup_data['backup_data']

                # 파일을 찾아서 base64 인코딩 후 리턴
                req_dict['backup_file'] = self._get_backup_file(req_dict['backup_location'])

                # 5-2. Call API of One-Box Agent: Restore One-Box
                # update_onebox_status_internally(mydb, "R", action_dict=None, action_status=None, ob_data=ob_data, ob_status=SRVStatus.OOS)

                # WF OB agent restore_onebox method call
                restore_result, restore_data = ob_agents.onebox_restore(req_dict)
                if restore_result < 0:
                    result = restore_result
                    log.error("Failed to restore One-Box %s: %d %s" % (ob_data['onebox_id'], restore_result, restore_data))
                    # common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data,
                    #                                                ob_status=SRVStatus.ERR)

                    comm_dict = {}
                    comm_dict['actiontype'] = ActionType.RESTO
                    comm_dict['action_dict'] = action_dict
                    comm_dict['action_status'] = ACTStatus.FAIL
                    comm_dict['ob_data'] = ob_data
                    comm_dict['ob_status'] = SRVStatus.ERR
                    comm_dict['wf_Odm'] = plugins.get('wf_Odm')

                    orch_comm.getFunc('update_onebox_status_internally', comm_dict)
                    comm_dict.clear()

                    raise Exception(restore_data)

                req_dict['request_type'] = "restore"
                req_dict['transaction_id'] = restore_data.get('transaction_id')

                if e2e_log:
                    e2e_log.job('Call API of One-Box Agent: Restore One-Box', CONST_TRESULT_SUCC, tmsg_body=None)

                # 5-3 Wait for Restoring One-Box
                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Completed to send restore command to the One-Box Agent : %s" % (ob_data['onebox_id'], str(restore_data)))
                if restore_data['status'] == "DOING":
                    action = "restore"
                    trial_no = 1
                    pre_status = "UNKNOWN"

                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] Wait for restore One-Box by Agent" % (ob_data['onebox_id']))
                    time.sleep(10)

                    check_status = ""

                    while trial_no < 30:
                        log.debug("[_RESTORE_ONEBOX_THREAD - %s] Checking the progress of restore (%d):" % (onebox_id, trial_no))

                        # One-Box Agent 진행 상태 조회
                        result, check_status = self._check_onebox_agent_progress(ob_agents, action, req_dict)
                        if check_status != "DOING":
                            if check_status == "ERROR":
                                log.debug("Failed to restore One-Box by Agent")
                            else:
                                log.debug("Completed to restore One-Box by Agent")

                            break
                        else:
                            log.debug("Restore in Progress")

                        trial_no += 1
                        time.sleep(10)

                    if check_status == "ERROR":
                        log.error("Failed to restore One-Box %s: %s" % (str(ob_data['onebox_id']), str(check_status)))

                        comm_dict = {}
                        comm_dict['actiontype'] = ActionType.RESTO
                        comm_dict['action_dict'] = action_dict
                        comm_dict['action_status'] = ACTStatus.FAIL
                        comm_dict['ob_data'] = ob_data
                        comm_dict['ob_status'] = SRVStatus.ERR
                        comm_dict['wf_Odm'] = plugins.get('wf_Odm')

                        orch_comm.getFunc('update_onebox_status_internally', comm_dict)
                        comm_dict.clear()

                        except_msg = "Failed to restore One-Box : response error = ERROR"
                        raise Exception(except_msg)

            # TODO : PNF 의 경우 resume monitor 일단 pass
            # Step.6 Resume Monitor One-Box >> API Call Changed
            # log.debug("[_RESTORE_ONEBOX_THREAD - %s] RESUME_ONEBOX_MONITOR BEGIN" % onebox_id)
            # # monitor_result, monitor_data = resume_onebox_monitor(mydb, ob_data['serverseq'], e2e_log)
            #
            # comm_dict = {}
            # comm_dict['ob_data'] = ob_data
            # comm_dict['e2e_log'] = e2e_log
            #
            # monitor_result, monitor_data = orch_comm.getFunc('resume_onebox_monitor', comm_dict)
            # comm_dict.clear()
            #
            # if monitor_result < 0:
            #     log.warning("Failed to start monitor: %d %s" % (monitor_result, monitor_data))
            #
            # log.debug("[_RESTORE_ONEBOX_THREAD - %s] RESUME_ONEBOX_MONITOR END" % onebox_id)
            #
            # if e2e_log:
            #     e2e_log.job('Resume Monitor One-Box', CONST_TRESULT_SUCC, tmsg_body=None)


            # nsr 관련 처리 안에 nsr monitor 는 PNF의 경우 무시한다
            if req_info.get('onebox_type') == "KtPnf":
                # PNF type

                comm_dict = {}
                comm_dict['actiontype'] = ActionType.RESTO
                comm_dict['action_dict'] = action_dict
                comm_dict['action_status'] = ACTStatus.SUCC
                comm_dict['ob_data'] = ob_data
                comm_dict['ob_status'] = SRVStatus.INS
                comm_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_onebox_status_internally', comm_dict)
                comm_dict.clear()
            else:
                # Other type

                # Step.7 Restore NSR
                # if is_nsr_exist:
                #     more_progress = True
                #     # 7-1 Get backup info
                #     log.debug("[_RESTORE_ONEBOX_THREAD - %s] Get NSR backup info" % onebox_id)
                #     result_backup, rlt_backup = _restore_nsr_get_backup_data(mydb, nsr_check_data['nsseq'], {"force_restore": True})
                #     if result_backup == HTTP_Not_Found:
                #         log.debug("No NSR found. Skip restoring NSR")
                #         more_progress = False
                #     if result_backup < 0:
                #         raise Exception("Failed to get Backup Data and NSR data")
                #
                #     if e2e_log:
                #         e2e_log.job('Get NSR backup info', CONST_TRESULT_SUCC, tmsg_body="rlt_backup : %s" % rlt_backup)
                #
                #     if more_progress:
                #         # 7-2. Reprovisioning NS
                #         log.debug("[_RESTORE_ONEBOX_THREAD - %s] Reprovisioning NSR" % onebox_id)
                #
                #         # 임시코드 - 기존에 프로비져닝된 rlt의 값을 보정하기 위해 사용. 새로 프로비져닝 된 rlt는 문제 없도록 수정되었음.
                #         # 기존 rlt 의 nsr name이 잘못들어간 부분 수정처리
                #         if rlt_backup["name"] != nsr_name:
                #             rlt_backup["name"] = nsr_name
                #         # 임시코드 END - 해당 로직 이전에 프로비져닝 된 항목이 없을 경우 제거가능
                #
                #         log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_REPROV _____ BEGIN" % onebox_id)
                #         new_nsr_result, new_nsr_data = _restore_nsr_reprov(mydb, rlt_backup, rlt_backup['name'], rlt_backup['description']
                #                                                            , {"vim_id": ob_data['vims'][0]['vimseq'], "server_id": ob_data['serverseq'],
                #                                                               "server_name": ob_data["servername"]}
                #                                                            , e2e_log)
                #         log.debug("[_RESTORE_ONEBOX_THREAD - %s] _____ _RESTORE_NSR_REPROV _____ END" % onebox_id)
                #         if new_nsr_result < 0:
                #             log.error("_restore_nsr_thread() failed to re-create NSR %d %s" % (new_nsr_result, new_nsr_data))
                #             raise Exception("_restore_nsr_thread() failed to re-create NSR %d %s" % (new_nsr_result, new_nsr_data))
                #
                #         if e2e_log:
                #             e2e_log.job("Reprovisioning NSR", CONST_TRESULT_SUCC, tmsg_body=None)
                #
                #         # 7-3 Restore VNFs
                #         if 'backupseq' in rlt_backup:
                #             log.debug("[_RESTORE_ONEBOX_THREAD - %s] Restore VNFs" % onebox_id)
                #
                #             # TODO: nfr_name
                #             vnf_name = ""
                #             for vnf_data in rlt_backup['vnfs']:
                #                 vnf_name = vnf_name + " " + vnf_data['name']
                #             action_dict['nfr_name'] = vnf_name
                #
                #             update_nsr_status(mydb, ActionType.RESTO, nsr_data=rlt_backup, nsr_status=NSRStatus.RST_restoringvnf)
                #             request = {'parentseq': rlt_backup['backupseq'], "process_name": "onebox_restore"}
                #
                #             result, request['needWanSwitch'] = _need_wan_switch(mydb, {"serverseq": ob_data['serverseq']})
                #
                #             restore_result, restore_data = _restore_nsr_vnf_thread(mydb, ob_data['serverseq'], new_nsr_data, action_dict, request, None, e2e_log)
                #
                #             if restore_result < 0:
                #                 log.warning("_restore_nsr_thread() error. failed to restore VNFs: %d %s" % (restore_result, restore_data))
                #                 if e2e_log:
                #                     e2e_log.job("Restore VNFs", CONST_TRESULT_FAIL, tmsg_body=None)
                #                     # update_nsr_status(mydb, "R", action_dict, ACTStatus.FAIL, new_nsr_data, NSRStatus.RUN)
                #             else:
                #                 if e2e_log:
                #                     e2e_log.job("Restore VNFs", CONST_TRESULT_SUCC, tmsg_body=None)
                #                     # update_nsr_status(mydb, "R", action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.RUN)
                #         else:
                #             log.debug("[_RESTORE_ONEBOX_THREAD - %s] No Backup Data. Skip restoring VNFs" % onebox_id)
                #             # update_nsr_status(mydb, "R", action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.RUN)
                #
                #         # 7-4 Resume monitoring >> Change API Call
                #         log.debug("[_RESTORE_ONEBOX_THREAD - %s] Resume NSR Monitoring" % onebox_id)
                #         update_nsr_status(mydb, ActionType.RESTO, nsr_data=new_nsr_data, nsr_status=NSRStatus.RST_resumingmonitor)
                #
                #         # nm_result, nm_data = start_nsr_monitoring(mydb, ob_data['serverseq'], new_nsr_data, e2e_log=None)
                #         nm_result, nm_data = resume_nsr_monitor(mydb, ob_data['serverseq'], new_nsr_data, e2e_log)
                #         if nm_result < 0:
                #             log.debug("Failed %d %s" % (nm_result, nm_data))
                #             update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.ERR)
                #         else:
                #             update_nsr_status(mydb, ActionType.RESTO, action_dict, ACTStatus.SUCC, new_nsr_data, NSRStatus.RUN)
                #
                #             if e2e_log:
                #                 e2e_log.job("Resume NSR Monitoring", CONST_TRESULT_SUCC, tmsg_body=None)
                #
                # # Step.8 Update VNF status and record action history
                # if ob_data['nsseq'] is None:
                #     common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.SUCC, ob_data=ob_data,
                #                                                    ob_status=SRVStatus.RDS)
                # else:
                #     common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.SUCC, ob_data=ob_data,
                #                                                    ob_status=SRVStatus.INS)

                pass

            # 복구중 변경된 정보가 있을 수 있으므로, 최종적으로 new_server를 한번 호출해준다.
            result, server_info = ob_agents.get_onebox_info(info_dict)
            if result < 0:
                log.warning("Failed to get onebox info from One-Box Agent: %d %s" % (result, server_info))
            else:
                log.debug("[Restore] new_server() Start...")
                server_info['restore'] = True

                su_result, su_data = plugins.get('wf_server_manager').new_server(server_info, plugins)

        except Exception, e:
            error_code = -HTTP_Internal_Server_Error
            error_msg = str(e)

            log.exception("Exception: %s" % error_msg)
            ob_data_temp = {"serverseq": action_dict["server_seq"]}

            comm_dict = {}
            comm_dict['actiontype'] = ActionType.RESTO
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.FAIL
            comm_dict['ob_data'] = ob_data_temp
            comm_dict['ob_status'] = SRVStatus.ERR
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            if e2e_log:
                e2e_log.job('One-Box 복구 Thread 처리 실패', CONST_TRESULT_FAIL, tmsg_body="Cause: %s" % (str(e)))
                e2e_log.finish(CONST_TRESULT_FAIL)
            return error_code, "One-Box 복구가 실패하였습니다. 원인: %s" % error_msg

        if e2e_log:
            e2e_log.job('One-Box 복구 Thread 완료', CONST_TRESULT_SUCC, tmsg_body="Result: Success")
            e2e_log.finish(CONST_TRESULT_SUCC)

        log.debug("[_RESTORE_ONEBOX_THREAD END - %s]" % onebox_id)

        return 200, "OK"

    
    # Reboot Process
    def reboot(self, req_info, plugins, use_thread=True):
        log.debug('[WF | %s] Reboot Start............' % str(req_info.get('onebox_id')))

        log.debug('[WF | %s] req_info = %s' %(str(req_info.get('onebox_id')), str(req_info)))

        e2e_log = None
        onebox_id = None
        request = req_info.get('reboot')

        try:
            # Step.1 Check arguments and initialize variables
            if req_info.get('onebox_id') is None:
                log.error("One-Box ID is not given")
                raise Exception(-HTTP_Bad_Request, "One-Box ID is required.")

            try:
                if not req_info.get('tid'):
                    e2e_log = e2elogger(tname='One-Box Reboot', tmodule='orch-f', tpath="orch_onebox-reboot")
                else:
                    e2e_log = e2elogger(tname='One-Box Reboot', tmodule='orch-f', tid=req_info.get('tid'), tpath=req_info.get('tpath') + "/orch_onebox-reboot")
            except Exception, e:
                log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
                e2e_log = None

            if e2e_log:
                # e2e_log.job('One-Box Reboot API Call 수신 처리 시작', CONST_TRESULT_SUCC,
                #             tmsg_body="Server ID: %s\nOne-Box Restore Request Body:%s" % (str(req_info.get('onebox_id')), json.dumps(request, indent=4)))
                action_tid = e2e_log['tid']
                pass
            else:
                action_tid = self._generate_action_tid()

            # Step.2 Get One-Box info and Check Status
            ob_result, ob_content = orch_dbm.get_server_id(req_info.get('onebox_id'))

            log.debug('[Reboot] ob_result = %d, ob_content = %s' %(ob_result, str(ob_content)))

            if ob_result <= 0:
                log.error("get_server_id Error %d %s" % (ob_result, ob_content))
                raise Exception(ob_result, ob_content)

            onebox_id = ob_content["onebox_id"]

            # 원박스 상태 체크하여 예외 처리 (기본 설치 전 reboot 시 - 상태값 : LINE_WAIT / PROVISIONING / LOCAL_PROVISIONING)
            if ob_content['status'] == SRVStatus.LWT or ob_content['status'] == SRVStatus.PVS or ob_content['status'] == SRVStatus.LPV:
                raise Exception(-HTTP_Bad_Request, "Cannot reboot the One-Box in the status of %s" % (ob_content['status']))

            if ob_content['action'] is None or ob_content['action'].endswith("E"):  # NGKIM: Use RE for backup
                pass
            else:
                raise Exception(-HTTP_Bad_Request, "The One-Box is in Progress for another action: status= %s action= %s" % (ob_content['status'], ob_content['action']))

            if e2e_log:
                e2e_log.job('Get One-Box info and Check Status', CONST_TRESULT_SUCC,
                            tmsg_body="One-Box ID: %s\nOne-Box DB DATA:%s" % (str(onebox_id), ob_content))

        except Exception, e:
            error_code = -HTTP_Internal_Server_Error
            if len(e.args) == 2:
                error_code, error_msg = e
            else:
                error_msg = str(e)

            log.warning("Exception: %s" % error_msg)
            if e2e_log:
                e2e_log.job('One-Box Reboot API Call 수신 처리 실패', CONST_TRESULT_FAIL,
                            tmsg_body="One-Box ID: %s\nOne-Box Restore Request Body:%s\nCause: %s" % (str(onebox_id), json.dumps(request, indent=4), str(e)))
                e2e_log.finish(CONST_TRESULT_FAIL)
            return error_code, "One-Box Restart 가 실패하였습니다. 원인: %s" % error_msg

        try:
            request_data = {"user": request.get("user", "admin"), "mgmt_ip": request.get('mgmt_ip'), "tid": action_tid}

            if request.get("wan_mac", None):
                request_data["wan_mac"] = request.get("wan_mac", None)

            # Step.4 Start restoring One-Box Thread
            th = threading.Thread(target=self._reboot_onebox_thread, args=(req_info, onebox_id, ob_content, request_data, plugins, True, e2e_log))
            th.start()

            return_data = {"reboot": "OK", "status": "DOING"}
        except Exception, e:
            log.warning("Exception: %s" % str(e))
            if e2e_log:
                e2e_log.job('One-Box Restart Thread 시작 실패', CONST_TRESULT_FAIL, tmsg_body=None)
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "One-Box Restart 가 실패하였습니다. 원인: %s" % str(e)

        # return 200, return_data
        return 200, "OK"


    # Reboot Theread
    def _reboot_onebox_thread(self, req_info, onebox_id, ob_data, request_data, plugins, use_thread=True, e2e_log=None):

        log.debug("[_REBOOT_ONEBOX_THREAD - %s] BEGIN" % onebox_id)

        action_dict = {'tid': request_data["tid"]}
        action_dict['category'] = "OBReboot"
        action_dict['action_user'] = request_data["user"]
        action_dict['server_name'] = ob_data['servername']
        action_dict['server_seq'] = ob_data['serverseq']

        orch_comm = plugins.get('orch_comm')
        wf_obconnector = plugins.get('wf_obconnector')
        wf_monitorconnector = plugins.get('wf_monitorconnector')

        try:
            ob_org_status = ob_data["status"]

            comm_dict = {}
            comm_dict['actiontype'] = ActionType.REBOT
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.STRT
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = SRVStatus.OOS
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            # Step.1 initialize variables
            is_agent_successful = True

            # Step.2 Get One-Box Agent Connector
            # comm_dict = {'onebox_id': onebox_id, 'onebox_type': req_info['onebox_type']}
            # result, ob_agents = orch_comm.getFunc('get_onebox_agent', comm_dict)

            result, ob_agents = 1, wf_obconnector

            if result < 0:
                log.error("Error. One-Box Agent not found")
                is_agent_successful = False
            elif result > 1:
                log.error("Error. Several One-Box Agents available, must be identify")
                is_agent_successful = False

            if is_agent_successful is False:
                ob_data_temp = {"serverseq": action_dict["server_seq"]}

                comm_dict = {}
                comm_dict['actiontype'] = ActionType.REBOT
                comm_dict['action_dict'] = action_dict
                comm_dict['action_status'] = ACTStatus.FAIL
                comm_dict['ob_data'] = ob_data_temp
                comm_dict['ob_status'] = ob_org_status
                comm_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_onebox_status_internally', comm_dict)
                comm_dict.clear()

                raise Exception("Cannot establish One-Box Agent Connector")

            # ob_agent = ob_agents.values()[0]

            if e2e_log:
                e2e_log.job('Get One-Box Agent Connector', CONST_TRESULT_SUCC, tmsg_body="onebox_id: %s\nob_agents:%s" % (onebox_id, ob_agents))

            # 모니터 일시 정지
            comm_dict = {}
            comm_dict['ob_data'] = ob_data
            comm_dict['e2e_log'] = e2e_log
            comm_dict['wf_monitorconnector'] = wf_monitorconnector

            som_result, som_data = orch_comm.getFunc('suspend_onebox_monitor', comm_dict)
            comm_dict.clear()

            if som_result < 0:
                log.warning("Failed to stop One-Box monitor. False Alarms are expected")

            if e2e_log:
                e2e_log.job('Suspend One-Box Monitoring', CONST_TRESULT_SUCC, tmsg_body=None)

            # Step.4 Remove NSR
            comm_dict = {}
            comm_dict['actiontype'] = ActionType.REBOT
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.INPG
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = SRVStatus.OOS
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            # 5-2. Call API of One-Box Agent: Restore One-Box
            log.debug('ob_data = %s' %str(ob_data))
            req_dict = {"onebox_id": ob_data['onebox_id']}
            req_dict['obagent_base_url'] = ob_data.get('obagent_base_url')

            reboot_result, reboot_data = ob_agents.onebox_reboot(req_dict)
            if reboot_result < 0:
                result = reboot_result
                log.error("Failed to restore One-Box %s: %d %s" % (ob_data['onebox_id'], reboot_result, reboot_data))

                comm_dict = {}
                comm_dict['actiontype'] = ActionType.REBOT
                comm_dict['action_dict'] = action_dict
                comm_dict['action_status'] = ACTStatus.FAIL
                comm_dict['ob_data'] = ob_data
                comm_dict['ob_status'] = SRVStatus.ERR
                comm_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_onebox_status_internally', comm_dict)
                comm_dict.clear()

                raise Exception(reboot_data)
            else:
                req_dict['request_type'] = "reboot"
                req_dict['transaction_id'] = reboot_data.get('transaction_id')

            if e2e_log:
                e2e_log.job('Call API of One-Box Agent: Restore One-Box', CONST_TRESULT_SUCC, tmsg_body=None)

            # 5-3 Wait for Restoring One-Box
            log.debug("[_REBOOT_ONEBOX_THREAD - %s] Completed to send reboot command to the One-Box Agent : %s" % (ob_data['onebox_id'], str(reboot_data)))

            # TODO : response 값 확인 할것...
            # if reboot_data['status'] == "DOING":
            if reboot_data['result'] == "OK":
                action = "reboot"
                trial_no = 1
                pre_status = "UNKNOWN"

                log.debug("[_REBOOT_ONEBOX_THREAD - %s] Wait for reboot One-Box by Agent" % (ob_data['onebox_id']))
                time.sleep(10)

                while trial_no < 30:
                    log.debug("[_REBOOT_ONEBOX_THREAD - %s] Checking the progress of reboot (%d):" % (onebox_id, trial_no))

                    # One-Box Agent 진행 상태 조회
                    result, check_status = self._check_onebox_agent_progress(ob_agents, action, req_dict)
                    if check_status != "DOING":
                        log.debug("Completed to reboot One-Box by Agent")
                        break
                    else:
                        log.debug("Reboot in Progress")

                    trial_no += 1
                    time.sleep(10)

            # Step.6 Resume Monitor One-Box >> API Call Changed
            log.debug("[_REBOOT_ONEBOX_THREAD - %s] RESUME_ONEBOX_MONITOR BEGIN" % onebox_id)
            # monitor_result, monitor_data = resume_onebox_monitor(mydb, ob_data['serverseq'], e2e_log)

            # TODO (추후 기간을 두고 개발) : resume_onebox_monitor 실패시 server state 값을 변경
            # TODO (추후 기간을 두고 개발) : UTM monitor resume 실행 / 실패시 state값을 OSSTART 로 변경(나중에 noti 들어올 때, UTM 모니터 시작할 수 있도록)
            # resume onebox monitor : Orch-F 에서는 server 만 resume, 초소형의 경우 모니터에서 server, utm 한번에 resume 처리 해준다.
            comm_dict = {}
            comm_dict['ob_data'] = ob_data
            comm_dict['e2e_log'] = e2e_log
            comm_dict['wf_monitorconnector'] = wf_monitorconnector

            monitor_result, monitor_data = orch_comm.getFunc('resume_onebox_monitor', comm_dict)
            comm_dict.clear()

            if monitor_result < 0:
                log.warning("Failed to start monitor: %d %s" % (monitor_result, monitor_data))

            # resume utm monitor
            # comm_dict = {}
            # comm_dict['ob_data'] = ob_data
            # comm_dict['e2e_log'] = e2e_log
            #
            # nsr_monitor_result, nsr_monitor_data = orch_comm.getFunc('resume_nsr_monitor', comm_dict)
            # comm_dict.clear()

            # server status 변경
            comm_dict = {}
            comm_dict['actiontype'] = ActionType.REBOT
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.SUCC
            comm_dict['ob_data'] = ob_data
            comm_dict['ob_status'] = SRVStatus.INS
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            log.debug("[_RESTORE_ONEBOX_THREAD - %s] RESUME_ONEBOX_MONITOR END" % onebox_id)

            if e2e_log:
                e2e_log.job('Resume Monitor One-Box', CONST_TRESULT_SUCC, tmsg_body=None)

        except Exception, e:
            error_code = -HTTP_Internal_Server_Error
            error_msg = str(e)

            log.exception("Exception: %s" % error_msg)
            ob_data_temp = {"serverseq": action_dict["server_seq"]}

            # common_manager.update_onebox_status_internally(mydb, ActionType.RESTO, action_dict=action_dict, action_status=ACTStatus.FAIL, ob_data=ob_data_temp,
            #                                                ob_status=SRVStatus.ERR)

            comm_dict = {}
            comm_dict['actiontype'] = ActionType.REBOT
            comm_dict['action_dict'] = action_dict
            comm_dict['action_status'] = ACTStatus.FAIL
            comm_dict['ob_data'] = ob_data_temp
            comm_dict['ob_status'] = SRVStatus.ERR
            comm_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_onebox_status_internally', comm_dict)
            comm_dict.clear()

            if e2e_log:
                e2e_log.job('One-Box 재시작 Thread 처리 실패', CONST_TRESULT_FAIL, tmsg_body="Cause: %s" % (str(e)))
                e2e_log.finish(CONST_TRESULT_FAIL)
            return error_code, "One-Box Restart 가 실패하였습니다. 원인: %s" % error_msg

        if e2e_log:
            e2e_log.job('One-Box 재시작 Thread 완료', CONST_TRESULT_SUCC, tmsg_body="Result: Success")
            e2e_log.finish(CONST_TRESULT_SUCC)

        log.debug("[_REBOOT_ONEBOX_THREAD END - %s]" % onebox_id)

        return 200, "OK"


    # Check Process (동작 점검)
    def onebox_check(self, req_info, plugins):
        log.debug('[WF] Check Start............')

        log.debug('[WF] req_info = %s' %str(req_info))

        force = True
        global global_config

        onebox_id = req_info.get('onebox_id')

        orch_comm = plugins.get('orch_comm')
        wf_obconnector = plugins.get('wf_obconnector')

        try:
            # Step.1 Check arguments
            if onebox_id == None:
                log.error("One-Box ID is not given")
                return -HTTP_Bad_Request, "One-Box ID is required."

            action_tid = af.create_action_tid()
            log.debug("Action TID: %s" % action_tid)

            # Step.2 Get One-Box info. and Status
            comm_dict = {}
            comm_dict['onebox_id'] = onebox_id
            comm_dict['onebox_type'] = req_info.get('onebox_type')

            ob_result, ob_content = orch_comm.getFunc('get_server_all_with_filter', comm_dict)
            comm_dict.clear()

            if ob_result <= 0:
                log.error("get_server_with_filter Error %d %s" % (ob_result, ob_content))
                return ob_result, ob_content
            ob_data = ob_content[0]
            ob_org_status = ob_data['status']
            onebox_id = ob_data['onebox_id']  # onebox_id가 serverseq값으로 들어온 경우를 위해 실제 onebox_id로 교체처리.

            result_data = {"status": ob_data['status']}

            # Step.3 Check connections to One-Box Agents
            if ob_data['status'] != SRVStatus.ERR or force == True:
                result_data['status'] = "DONE"
                result_data['detail'] = []

                # 3-1. One-Box Agent
                # comm_dict = {'onebox_id': onebox_id, 'onebox_type': req_info['onebox_type']}
                # result, ob_agents = orch_comm.getFunc('get_onebox_agent', comm_dict)
                # comm_dict.clear()

                result, ob_agents = 1, wf_obconnector

                log.debug('[Action - Check] get_onebox_agent : result = %d, ob_agents = %s' %(result, str(ob_agents)))

                if result < 0 or result > 1:
                    log.error("Error. Invalid DB Records for the One-Box Agent: %s" % str(onebox_id))
                    result_data['status'] = "FAIL"
                    result_data['detail'].append({'agent_connection': "NOK"})
                else:
                    # ob_agent = ob_agents.values()[0]

                    check_dict = {}
                    check_dict['onebox_id'] = ob_data.get('onebox_id')
                    check_dict['obagent_base_url'] = ob_data.get('obagent_base_url')

                    result, check_content = ob_agents.connection_check(check_dict)

                    log.debug("The result of checking a connection to One-Box Agent: %d %s" % (result, str(check_content)))

                    if result < 0:
                        result_data['status'] = "FAIL"
                        result_data['detail'].append({'agent_connection': "NOK"})
                    else:
                        result_data['detail'].append({'agent_connection': "OK"})

                # 3-2. VNFM Agent
                # TODO : PNF 경우 - vnf 가 없지만 포멧 유지 (필요시 기존 소스 참조, 여기에선 소스 삭제)
                result_data['detail'].append({'vnfm_connection': "N/A"})

                # 3-3. VIM
                # TODO : PNF 경우 - vim 이 없지만 포멧 유지 (필요시 기존 소스 참조, 여기에선 소스 삭제)
                result_data['detail'].append({'vim_connection': "N/A"})

            return 200, result_data
        except Exception, e:
            error_msg = "One-Box 연결 확인이 실패하였습니다. One-Box 연결상태를 확인하세요."
            log.exception(error_msg)
            return -515, error_msg

    # mac addr reset
    def reset_mac(self, request_dict, plugins):
        force = True
        onebox_id = request_dict.get('onebox_id')

        orch_comm = plugins.get('orch_comm')
        wf_server_manager = plugins.get('wf_server_manager')
        wf_obconnector = plugins.get('wf_obconnector')

        log.debug("[HJC] IN with One-Box ID = %s" % onebox_id)

        # tb_server update
        log.debug("[HJC] 1. get One-Box info from DB")
        filter_dict = {'onebox_id': onebox_id, 'onebox_type': request_dict.get('onebox_type')}

        result, data = orch_dbm.get_server_filters(filter_dict)
        if result < 0:
            log.error("failed to get One-Box Info from DB: %d %s" % (result, str(data)))
            return -HTTP_Not_Found, str(data)
        elif result == 0:
            log.error("%s Not found: %d %s" % (onebox_id, result, str(data)))
            return -HTTP_Not_Found, "%s Not found" % (onebox_id)

        onebox_db = data[0]
        log.debug("[HJC] Succeed to get One-Box info from DB: %s" % str(onebox_db))

        # log.debug("[HJC] 2. reset mac addrss in DB")
        # server_dict = {'serverseq': onebox_db['serverseq'], 'publicmac': ""}
        # result, data = orch_dbm.update_server(mydb, server_dict)
        # if result < 0:
        #    log.error("failed to reset mac due to DB Error: %d %s" %(result, data))
        #    return result, data
        # log.debug("[HJC] Succeed to reset mac addrss in DB")

        # request to update OB Info to OBA
        try:
            log.debug("[HJC] 3. get one-box info from One-Box Agent")

            # comm_dict = {'onebox_id': onebox_id, 'onebox_type': request_dict['onebox_type']}
            # result, ob_agents = orch_comm.getFunc('get_onebox_agent', comm_dict)
            result, ob_agents = 1, wf_obconnector

            if result < 0 or result > 1:
                log.error("Error. Invalid DB Records for the One-Box Agent: %s" % str(onebox_id))
                raise Exception("Error. Invalid DB Records for the One-Box Agent: %s" % str(onebox_id))

            # ob_agent = ob_agents.values()[0]
            info_dict = {}
            info_dict['onebox_id'] = onebox_id
            info_dict['obagent_base_url'] = onebox_db.get('obagent_base_url')
            result, content = ob_agents.get_onebox_info(info_dict)
            # log.debug("The result of getting onebox info: %d %s" % (result, str(content)))
            if result < 0:
                log.error("Failed to get onebox info from One-Box Agent: %d %s" % (result, content))
                raise Exception("Failed to get onebox info from One-Box Agent: %d %s" % (result, content))

            server_info = content
            log.debug("[HJC] Succeed to get one-box info from One-Box Agent: %s" % str(server_info))
        except Exception, e:
            log.exception("Exception: %s" % str(e))

            log.debug("reset mac addrss in DB")
            server_dict = {'serverseq': onebox_db['serverseq'], 'publicmac': ""}
            result, data = orch_dbm.update_server(server_dict)
            if result < 0:
                log.error("failed to reset mac due to DB Error: %d %s" % (result, data))
                return result, data
            log.debug("Succeed to reset mac addrss in DB")
            rtn_msg = "MAC주소 초기화 동작 중 Agent에 접속이 안되고 있습니다.\n" \
                      "Agent에서 서버정보를 보내주면 MAC 주소가 자동으로 초기화 됩니다.(몇분 이상 걸릴 수 있습니다.)\n" \
                      "만약 해결되지 않으면 관리자에게 문의하세요."

            return -HTTP_Internal_Server_Error, rtn_msg

        # update server info
        try:
            log.debug("[HJC] 4. update one-box info into DB")
            # result, data = new_server(mydb, server_info, filter_data=onebox_id, use_thread=True, forced=True)

            # first_nitify 처리하기 위해서 강제로 True로 바꿔준다
            server_info['first_notify'] = True

            log.debug('[Reset Mac] server_info = %s' % str(server_info))

            result, data = wf_server_manager.new_server(server_info, plugins, use_thread=True, forced=True)

            if result < 0:
                raise Exception("failed to update onebox-info to DB: %d %s" % (result, data))
            log.debug("[HJC] Succeed to update one-box info into DB")
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, str(e)

        log.debug("[HJC] OUT with One-Box ID = %s" % onebox_id)
        return 200, "OK"


    def _generate_action_tid(self):
        return datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + str(random.randint(1, 99)).zfill(2)


    # One-Box Agent 진행 상태 조회
    def _check_onebox_agent_progress(self, ob_agent, action, req_dict):
        result = 200
        data = "DOING"

        try:
            # req_type = req_dict.get('request_type') # "restore"
            req_type = action # "restore"
            trans_id = req_dict.get('transaction_id')

            # One-Box Agent 진행 상태 조회
            progress_dict = {}
            progress_dict['onebox_id'] = req_dict.get('onebox_id')
            progress_dict['obagent_base_url'] = req_dict.get('obagent_base_url')

            check_result, check_data = ob_agent.wf_check_onebox_agent_progress(progress_dict=progress_dict, request_type = req_type, transaction_id=trans_id)
        except Exception, e:
            log.exception("Exception: %s" %str(e))
            check_result = -500
            check_data = {'status':"UNKNOWN", 'error':str(e)}

        if check_result < 0:
            result = check_result
            data = "DOING"
            log.debug("Error %d, %s" %(check_result, str(check_data)))
        else:
            if action == "restore":
                log.debug("Progress form One-Box by Agent: %s" %(check_data['status']))
                if check_data['status'] == "DONE":
                    data = "DONE"
                elif check_data['status'] == "ERROR":
                    data = "ERROR"
                else:
                    data = check_data['status']
            else:   # reboot : oba_baseurl/version
                data = "DONE"

        return result, data


    ##########  File encode & decode base64, scp get & put  ###########################################

    # backup file base64 decode saving
    def _base64_decode_save(self, backup_data, backup_file):
        remote_location = backup_data.get('remote_location').split('/')
        filename = remote_location[-1]
        save_path = backup_data.get('remote_location').replace('/' + filename, '')

        log.debug('_base64_decode_save : local_path = %s' %str(save_path))

        # 폴더가 없으면 생성한다
        try:
            if not os.path.isdir(save_path):
                os.makedirs(os.path.join(save_path))
                log.debug('[Action] Backup > _base64_decode_save : diretory creation succeeded!')
        except OSError as e:
            log.debug('Failed to create directory : %s' % str(save_path))
            raise

        # base64 decode
        rev_data = base64.b64decode(backup_file)

        # save file
        e = open(save_path + '/' + filename, 'wb')
        e.write(rev_data)
        e.close()


    # return backup file : backup file base64 encode
    def _get_backup_file(self, backup_local_location):
        # file check exist
        if not os.path.isfile(backup_local_location):
            log.debug('[Restore] _get_backup_file : remote_location change from (%s)' % str(backup_local_location))
            backup_local_location = backup_local_location.replace('/var/onebox/backup/', '/var/onebox/backup_pnf/')
            log.debug('[Restore] _get_backup_file : remote_location change to (%s)' % str(backup_local_location))

        # file encode base64
        with open(backup_local_location, "rb") as f:
            bytes = f.read()
            encoded = base64.b64encode(bytes)

        return encoded

    ##########  File encode & decode base64, scp get & put  ###########################################
