# coding=utf-8

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

from tornado.web import RequestHandler

import db.orch_db_manager as orch_dbm
import handler_utils as util
import orch_schemas
import json
from datetime import datetime, timedelta
import time
import utils.log_manager as log_manager
from handlers_t.http_response import HTTPResponse
from utils import auxiliary_functions as af
from utils import db_conn_manager as dbmanager
log = log_manager.LogManager.get_instance()

from engine import server_manager, vim_manager, nsr_manager, authkey_manager
import orch_core as nfvo

mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

from utils.config_manager import ConfigManager

url_base_t = "/orch"

# remote command control
OPCODE_SERVER_CONTROL = "WF_SERVER_CONTROL"
OPCODE_SERVER_CONTROL_RESERVE_DELETE = "OPCODE_SERVER_CONTROL_RESERVE_DELETE"

# MMS
OPCODE_SERVER_MMS_SEND = "OPCODE_SERVER_MMS_SEND"

# 초소형 원박스
OPCODE_SERVER_WF = "WF_SERVER"
OPCODE_SERVER_WF_ACT = "WF_ACTION"
OPCODE_SERVER_PROGRESS = "WF_SERVER_PROGRESS"
OPCODE_SERVER_BACKUP_DATA = "WF_SERVER_BACKUP_DATA"

# ArmBox
OPCODE_SERVER_WF_ARM = "WF_SERVER_ARM"

# rlt 조회용
OPCODE_RLT_WF = "WF_RLT"
OPCODE_ONEBOX_INFO = "ONEBOX_INFO"

# 작업 사전 테스트 용
OPCODE_WORK_BASE64_REQUEST = "BASE64_REQUEST"
OPCODE_WORK_BASE64_RESPONSE = "BASE64_RESPONSE"
OPCODE_WORK_JOB = "WORK_JOB"
OPCODE_WORK_MONITOR = "OPCODE_WORK_MONITOR"
OPCODE_WORK_BOND = "OPCODE_WORK_BOND"
# OPCODE_WORK_REMOTEIP_SAVE = "OPCODE_WORK_MONITOR"
OPCODE_SERVER_CHANGE_IP = "OPCODE_SERVER_CHANGE_IP"

def url(plugins):
    # Work Flow One-Box API List
    urls = [
        # 모든 OneBox 공통
        (url_base_t + "/server/auto/rcc", ServerHandler, dict(opCode=OPCODE_SERVER_CONTROL, plugins=plugins)),     # web->orch-F : remote command control(ssh command)
        (url_base_t + "/server/auto/rcc_reserve_del", ServerHandler, dict(opCode=OPCODE_SERVER_CONTROL_RESERVE_DELETE, plugins=plugins)),     # web->orch-F : remote command control Delete(ssh command)
        (url_base_t + "/server/mms/send", ServerHandler, dict(opCode=OPCODE_SERVER_MMS_SEND, plugins=plugins)),     # web->orch-F : mms send

        # post - PNF
        (url_base_t + "/server/([^/]*)/wf", ServerHandler, dict(opCode=OPCODE_SERVER_WF, plugins=plugins)),  # agent->orch-F : noti, new_server()
        (url_base_t + "/server/act/([^/]*)/([^/]*)", ServerHandler, dict(opCode=OPCODE_SERVER_WF_ACT, plugins=plugins)),  # action : backup, restore, check, reboot, ...

        # post - ArmBox
        (url_base_t + "/server/([^/]*)/arm", ServerHandler, dict(opCode=OPCODE_SERVER_WF_ARM, plugins=plugins)),  # agent->orch-F : noti, new_server()

        # get
        (url_base_t + "/server/progress/([^/]*)/([^/]*)", ServerHandler, dict(opCode=OPCODE_SERVER_PROGRESS, plugins=plugins)),  # 작업 상태 조회
        (url_base_t + "/server/backup/([^/]*)", ServerHandler, dict(opCode=OPCODE_SERVER_BACKUP_DATA, plugins=plugins)),  # 백업 데이터 조회

        # base64 test
        (url_base_t + "/server/work/base64_request", WorkHandler, dict(opCode=OPCODE_WORK_BASE64_REQUEST, plugins=plugins)),
        (url_base_t + "/server/work/base64_response", WorkHandler, dict(opCode=OPCODE_WORK_BASE64_RESPONSE, plugins=plugins)),

        # mac 초기화 위한 ip 변경 API
        (url_base_t + "/server/chgip/([^/]*)", ServerHandler, dict(opCode=OPCODE_SERVER_CHANGE_IP, plugins=plugins)),

        #####    테스트 전용     ############################################################################################################################
        (url_base_t + "/server/work/job", WorkHandler, dict(opCode=OPCODE_WORK_JOB, plugins=plugins)),
        # (url_base_t + "/server/work/remoteip", WorkHandler, dict(opCode=OPCODE_WORK_JOB)),
        (url_base_t + "/server/work/monitor/([^/]*)/([^/]*)", WorkHandler, dict(opCode=OPCODE_WORK_MONITOR, plugins=plugins)),

        # vnf init_config bonding script setting
        (url_base_t + "/server/work/bond", WorkHandler, dict(opCode=OPCODE_WORK_BOND, plugins=plugins)),

        # # get onebox_info
        # (url_base_t + "/server/([^/]*)/onebox_info", ServerHandler, dict(opCode=OPCODE_ONEBOX_INFO)),

        # rlt 조회용
        (url_base_t + "/server/([^/]*)/rlt", ServerHandler, dict(opCode=OPCODE_RLT_WF, plugins=plugins))

    ]

    return urls



class ServerHandler(RequestHandler):

    def initialize(self, opCode, plugins):
        self.opCode = opCode
        self.plugins = plugins

    def post(self, server_id=None, onebox_type=None):

        if self.opCode == OPCODE_SERVER_WF:     # 초소형 원박스 (KtPnf) - new_server()
            self._http_post_wf(server_id)
        elif self.opCode == OPCODE_SERVER_WF_ACT:       # 초소형 원박스 (KtPnf) - act(), backup/restore
            self._http_post_act_new(server_id, onebox_type)
        elif self.opCode == OPCODE_RLT_WF:             # BBG : RLT 조회용
            self._http_post_pnf_rltinfo()
        elif self.opCode == OPCODE_SERVER_WF_ARM:       # Arm-Box (Notify) - new_server_arm()
            self._http_post_wf_arm(server_id)
        elif self.opCode == OPCODE_SERVER_CONTROL:      # remote command control(ssh command)
            self._http_post_rcc()
        elif self.opCode == OPCODE_SERVER_CONTROL_RESERVE_DELETE:      # remote command control(ssh command)
            self._http_post_rcc_reserve_del()
        elif self.opCode == OPCODE_SERVER_CHANGE_IP:      # MAC 초기화 전 IP 변경 API
            self._http_post_server_change_ip(server_id)
        elif self.opCode == OPCODE_SERVER_MMS_SEND:      # MMS : SEND
            self._http_post_server_mms_send()
        else:
            # OneBox Agent에서 호출하는 API
            # tb_server에 필요한 정보를 등록처리.
            self._http_post_server(server_id)

    def get(self, server_id=None, onebox_type="KtPnf"):
        """get server list or details, can use both id or name"""

        log.debug('[WF Handler] request = %s' % str(self.request))

        if self.opCode == OPCODE_SERVER_PROGRESS:
            result, content = self.plugins.get('wf_server_manager').get_server_progress_with_filter(server_id)

            if result < 0:
                log.error("failed to check the progress of the One-Box: %s" % server_id)

            data = content
        elif self.opCode == OPCODE_SERVER_BACKUP_DATA:
            result, content = self.plugins.get('wf_server_manager').get_server_backup_data(server_id)
            if result < 0:
                log.error("failed to get Backup Data for %s" %server_id)
            data = content
        # elif self.opCode == OPCODE_ONEBOX_INFO:
        #     result, content = self.wf_server_manager.get_onebox_info(server_id)
        #     if result < 0:
        #         log.error("failed to get Backup Data for %s" %server_id)
        #     data = content
        else:
            if server_id is None or server_id == "all":
                result, content = orch_dbm.get_server(mydb)
                if result < 0:
                    data = content
                else:
                    for c in content:
                        af.convert_datetime2str_psycopg2(c)
                    data = {'server': content}
            else:
                server_id = str(server_id)
                result, content = server_manager.get_server_with_filter(mydb, server_id)

                if result < 0:
                    data = content
                else:
                    for c in content:
                        af.convert_datetime2str_psycopg2(c)
                    data = content

        # 기존 response format
        # self._send_response(result, data)

        # Work Flow response format
        self._send_response_wf(result, data)
        return

    ### POST 내부함수 #################################################################################

    ### Work Flow One-Box   ########################################################################
    def _http_post_wf(self, server_id=None):
        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.server_schema_pnf, is_report=is_report)
        if result < 0:
            # note 처리
            # server_result, server_data = server_manager.get_server_with_filter(mydb, server_id, onebox_type=None)
            # log.debug('server_data = %s' %str(server_data))
            #
            # note = "유효하지 않은 One-Box 정보가 수신되었습니다. One-Box 설정을 확인하세요."
            # # note = json.dumps(memo, indent=4)
            #
            # com_dict = {}
            # com_dict['serverseq'] = server_data[0]['serverseq']
            # com_dict["note"] = note
            #
            # memo_result, memo_content = orch_comm.getFunc('setNote', com_dict)
            # com_dict.clear()

            self._send_response(result, http_content)
            return

        # remote_ip 추가 : LTE 통해 들어온 경우 사설아이피로 오기 때문에 remote_ip 로 public_ip 대체하기 위함
        http_content['remote_ip'] = self.request.remote_ip

        ##############  REDIS   S   ################################################################################

        # noti 단순 비교, 변경점 있으면 저장하고 처리 시작. 변경점 없으면 api종료
        wf_redis = self.plugins.get('wf_redis')
        diff_dict = {'server_id' : server_id, 'http_content' : http_content}

        redis_result, redis_data = wf_redis.diff_noti(diff_dict)

        # redis_result 가 200 일 경우, redis 에 저장된 데이터가 없거나 저장된 데이터와 다른경우 설변으로 간주
        if redis_result < 0:
            self._send_response(200, redis_data)
            return

        ##############  REDIS   E   ################################################################################


        # TODO : Validattion Check - 필수 IP 값 존재여부 등.
        chk_result, chk_data, chk_boolean = self._wf_check_validation(server_id, http_content)

        # log.debug('[PNF] _wf_check_validation result : %d, data : %s' %(chk_result, str(chk_data)))

        if chk_result <= 0:
            ret = []

            if chk_boolean is False:
                if chk_result == -1001:     # order 와 noti 정보가 다른 경우 : order는 VNF, noti는 PNF 일 때
                    note = "R01:유효하지 않은 One-Box 정보가 수신되었습니다. One-Box 설정을 확인하세요."
                    # note = json.dumps(memo, indent=4)

                    if chk_data.get('description'):
                        desc = str(chk_data.get('description')) + '\n' + note
                    else:
                        desc = note

                    com_dict = {}
                    com_dict['serverseq'] = chk_data['serverseq']
                    com_dict["note"] = desc

                    memo_result, memo_content = self.plugins.get('orch_comm').getFunc('setNote', com_dict)
                    com_dict.clear()

                    self._send_response(memo_result, memo_content)
                    return
                else:
                    return_data = {'error': {'description': "Cannot found the Server : %s" %str(server_id)}}
            else:
                return_data = {'error': {'description': "mgmt_boolean is all false"}}

            ret.append(return_data)

            self._send_response(200, ret)
            return

        # 라우터 통해서 들어온 경우 통신 가능 하도록 public ip 를 remote_ip 로 대체 ==> new_server 안에서 처리(_parse_server_info)로 변경
        # if self._private_ip_check(http_content.get('public_ip')) == -1:
        #     old_public_ip = http_content.get('public_ip')
        #     remote_ip = self.request.remote_ip
        #
        #     # log.debug('origin data = %s' % str(http_content['obagent']['base_url']))
        #
        #     http_content['public_ip'] = remote_ip
        #     http_content['mgmt_ip'] = remote_ip
        #
        #     obagent_base_url = http_content['oba_baseurl']
        #     http_content['oba_baseurl'] = obagent_base_url.replace(old_public_ip, remote_ip)
        #
        #     # log.debug('replace origin data = %s' %str(http_content['obagent']['base_url']))
        #
        #     # vnfm_base_url = http_content['vnfm']['base_url']
        #     # http_content['vnfm']['base_url'] = vnfm_base_url.replace(old_public_ip, remote_ip)
        #     #
        #     # vim_auth_url = http_content['vim']['vim_authurl']
        #     # http_content['vim']['vim_authurl'] = vim_auth_url.replace(old_public_ip, remote_ip)
        #
        #     http_content['router'] = 'W'
        #
        #     # log.debug('change http_content = %s' %str(http_content))

        managers = {}
        managers['orch_comm'] = self.plugins.get('orch_comm')
        managers['wf_monitorconnector'] = self.plugins.get('wf_monitorconnector')
        managers['wf_Odm'] = self.plugins.get('wf_Odm')
        managers['wf_redis'] = self.plugins.get('wf_redis')

        result, data = self.plugins.get('wf_server_manager').new_server(http_content, managers, use_thread=True, forced=False)

        if result > 0:
            # server_result, server_data = server_manager.get_server_with_filter(mydb, data, http_content.get('onebox_type'))
            server_result, server_data = server_manager.get_server_with_filter(mydb, data.get('serverseq'), http_content.get('onebox_type'))

            # # 유무선 변경 시 터널링 리턴 정보
            # if 'tunnel' in data:
            #     server_data[0]['tunnel'] = data.get('tunnel')

            data = server_data

        elif not is_report and 0 > result != -400:
            log.warning("OBA Call Problem for this request \n  - REQUEST URL: %s" % str(self.request.uri))
            log.warning("  - REQUEST METHOD: %s" % str(self.request.method))
            log.warning("  - BODY: %s" % str(self.request.body))

        # self._send_response(result, data)
        self._send_response_wf(result, data)

    # 초소형 원박스 action : 동작점검(check), 재시작(reboot)
    # 백업(backup), 복구(restore) 는 기존 api 에서 분기처리 (/orch/server/<server_id>/action)
    def _http_post_act_new(self, server, onebox_type):
        # parse input data
        result, http_content = util.format_in(self.request, orch_schemas.server_action_schema_new)

        log.debug("[NBI IN] Action for the One-Box %s" %(str(server)))
        log.debug("[NBI IN] Request Body = %s" %str(http_content))

        # KtPnf 분기
        if onebox_type == 'KtPnf':

            if 'check' in http_content:
                action_category = "Check"
            elif 'reboot' in http_content:
                action_category = "Reboot"
            # backup, restore, resetmac 은 기존 소스에서 분기 된다
            # elif 'backup' in http_content:
            #     action_category = "Backup"
            # elif 'restore' in http_content:
            #     action_category = "Restore"
            else:
                action_category = ""

            try:
                is_report = True
                http_content['onebox_type'] = onebox_type
                http_content['onebox_id'] = server

                managers = {}
                managers['orch_comm'] = self.plugins.get('orch_comm')
                managers['wf_server_manager'] = self.plugins.get('wf_server_manager')
                managers['wf_act_manager'] = self.plugins.get('wf_act_manager')
                managers['wf_monitorconnector'] = self.plugins.get('wf_monitorconnector')
                managers['wf_obconnector'] = self.plugins.get('wf_obconnector')
                managers['wf_Odm'] = self.plugins.get('wf_Odm')

                # KtPnf backup
                log.debug('[WF - Action] action_category = %s' %str(action_category))
                result, data = self.plugins.get('wf_act_manager').action(http_content, managers, action_category)

                if result < 0:
                    log.error("[NBI OUT] Action for the One-Box, Backup: Error %d %s" %(-result, data))
                    self._send_response(result, data)
                    return
                else:
                    log.debug("[NBI OUT] Action for the One-Box, Backup: OK")
                    self._send_response(result, data)
                    return
            except Exception, e:
                log.error("_____##### Error in %s backup-onebox : %s" % (str(onebox_type), str(e)))
                self._send_response(-500, "%s Action : %s One-Box Exception" % (str(onebox_type), str(action_category)))
                return


    # rlt 조회용
    def _http_post_pnf_rltinfo(self):
        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.rlt_schema_pnf, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        result, data = self.wf_server_manager.rlt(http_content)

        if result > 0:
            server_result, server_data = server_manager.get_server_with_filter(mydb, data)
            data = server_data
        elif not is_report and 0 > result != -400:
            log.warning("OBA Call Problem for this request \n  - REQUEST URL: %s" % str(self.request.uri))
            log.warning("  - REQUEST METHOD: %s" % str(self.request.method))
            log.warning("  - BODY: %s" % str(self.request.body))

        self._send_response(result, data)


    ###     Arm-Box     ##################################################################################################

    def _http_post_wf_arm(self, server_id=None):
        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.server_schema_armbox, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        ##############  REDIS   S   ################################################################################
        # noti 단순 비교, 변경점 있으면 저장하고 처리 시작. 변경점 없으면 api종료
        # wf_redis = self.plugins.get('wf_redis')
        # diff_dict = {'server_id': server_id, 'http_content': http_content}
        #
        # redis_result, redis_data = wf_redis.diff_noti(diff_dict)
        #
        # # redis_result 가 200 일 경우, redis 에 저장된 데이터가 없거나 저장된 데이터와 다른경우 설변으로 간주
        # if redis_result < 0:
        #     self._send_response(200, redis_data)
        #     return
        ##############  REDIS   E   ################################################################################

        # TODO : 플러그인 오류 확인 필요, 임시로 주석처리
        # noti 가 다른 경우 : order 는 PNF, noti는 VNF 일 때
        result, data, chk_boolean = self._order_check_validation(server_id, http_content)
        if result == -1001:
            note = "R01:유효하지 않은 One-Box 정보가 수신되었습니다. One-Box 설정을 확인하세요."
            # note = json.dumps(memo, indent=4)

            if data.get('description'):
                desc = str(data.get('description')) + '\n' + note
            else:
                desc = note

            com_dict = {}
            com_dict['serverseq'] = data['serverseq']
            com_dict["note"] = desc

            memo_result, memo_content = self.plugins.get('orch_comm').getFunc('setNote', com_dict)
            com_dict.clear()

            self._send_response(memo_result, memo_content)
            return

        # request body validation check
        chk_result, chk_msg = self._server_info_check(http_content)
        if chk_result < 0:
            log.error("Invalid One-Box Info: %s" % str(chk_msg))
            self._send_response(chk_result, chk_msg)
        else:
            http_content['onebox_type'] = 'KtArm'

            managers = {}
            managers['orch_comm'] = self.plugins.get('orch_comm')
            managers['wf_monitorconnector'] = self.plugins.get('wf_monitorconnector')
            managers['wf_Odm'] = self.plugins.get('wf_Odm')
            managers['wf_redis'] = self.plugins.get('wf_redis')

            if server_id:
                http_content['onebox_id'] = str(server_id)
                result, data = self.plugins.get('wf_server_arm_manager').new_server_arm(http_content, plugins=managers)
            else:
                result, data = self.plugins.get('wf_server_arm_manager').new_server_arm(http_content, plugins=managers)

            if result > 0:
                server_result, server_data = server_manager.get_server_with_filter(mydb, data)
                data = server_data
                server_data = None
                # log.debug('data = %s' %str(data))
                # log.debug('server_data = %s' %str(server_data))
            elif not is_report and 0 > result != -400:
                log.warning("OBA Call Problem for this request \n  - REQUEST URL: %s" % str(self.request.uri))
                log.warning("  - REQUEST METHOD: %s" % str(self.request.method))
                log.warning("  - BODY: %s" % str(self.request.body))

            self._send_response(result, data)
    ###     Arm-Box     ##################################################################################################


    ###     Remote Command Control (ssh command)    START   ###############################################################################
    def _http_post_rcc(self):
        # log.debug("IN _http_post_rcc")
        # log.debug("http_content = %s" % str(self.request))

        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.server_remote_control, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        # log.debug("http_content = %s" %str(http_content))
        # http_content['onebox_type'] = "KtComm"

        managers = {}
        managers['orch_comm'] = self.plugins.get('orch_comm')
        managers['wf_ssh'] = self.plugins.get('wf_ssh')
        managers['wf_redis'] = self.plugins.get('wf_redis')
        managers['wf_svr_ktcomm_manager'] = self.plugins.get('wf_svr_ktcomm_manager')

        result, data = self.plugins.get('wf_svr_ktcomm_manager').server_rcc(http_content, plugins=managers)

        if result > 0:
            pass
        elif not is_report and 0 > result != -400:
            log.warning("OBA Call Problem for this request \n  - REQUEST URL: %s" % str(self.request.uri))
            log.warning("  - REQUEST METHOD: %s" % str(self.request.method))
            log.warning("  - BODY: %s" % str(self.request.body))

        self._send_response(result, data)


    def _http_post_rcc_reserve_del(self):

        # log.debug("IN _http_post_rcc")
        # log.debug("http_content = %s" % str(self.request))

        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.server_remote_control_reserve_delete, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        # log.debug("http_content = %s" %str(http_content))
        # http_content['onebox_type'] = "KtComm"

        managers = {}
        managers['orch_comm'] = self.plugins.get('orch_comm')
        # managers['wf_ssh'] = self.plugins.get('wf_ssh')
        managers['wf_redis'] = self.plugins.get('wf_redis')

        result, data = self.plugins.get('wf_svr_ktcomm_manager').server_rcc_reserve_delete(http_content, plugins=managers)

        if result > 0:
            pass
        elif not is_report and 0 > result != -400:
            log.warning("OBA Call Problem for this request \n  - REQUEST URL: %s" % str(self.request.uri))
            log.warning("  - REQUEST METHOD: %s" % str(self.request.method))
            log.warning("  - BODY: %s" % str(self.request.body))

        self._send_response(result, data)
    ###     Remote Command Control (ssh command)    END     ###############################################################################


    ###     Server Change IP    START     ###############################################################################
    def _http_post_server_change_ip(self, onebox_id=None):
        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.server_schema_change_ip, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        managers = {}
        managers['orch_comm'] = self.plugins.get('orch_comm')

        http_content['onebox_id'] = onebox_id
        result, data = self.plugins.get('wf_svr_ktcomm_manager').server_change_ip(http_content, plugins=managers)

        if result > 0:
            pass
        elif not is_report and 0 > result != -400:
            log.warning("API Call Problem for this request \n  - REQUEST URL: %s" % str(self.request.uri))
            log.warning("  - REQUEST METHOD: %s" % str(self.request.method))
            log.warning("  - BODY: %s" % str(self.request.body))

        self._send_response(result, data)

    ###     Server Change IP    END       ###############################################################################


    ###     MMS : SEND    START       ###############################################################################
    def _http_post_server_mms_send(self):
        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.server_mms_send, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        managers = {}
        managers['orch_comm'] = self.plugins.get('orch_comm')

        result, data = self.plugins.get('wf_svr_ktcomm_manager').mms_send(http_content, plugins=managers)

        if result > 0:
            pass
        elif not is_report and 0 > result != -400:
            log.warning("API Call Problem for this request \n  - REQUEST URL: %s" % str(self.request.uri))
            log.warning("  - REQUEST METHOD: %s" % str(self.request.method))
            log.warning("  - BODY: %s" % str(self.request.body))

        self._send_response(result, data)

    ###     MMS : SEND    END         ###############################################################################

    ### POST 내부함수 END ###########################################################################

    def _order_check_validation(self, server_id, http_content):
        result, data = orch_dbm.get_db_server(mydb, server_id)
        if result <= 0:
            return result, data, False
        else:
            if data.get('nfsubcategory') == "KtPnf" or data.get('nfsubcategory') == "One-Box":
                return -1001, data, False

        return 200, "OK", True

    def _server_info_check(self, server_info):
        if server_info.get("public_ip") is None or len(server_info["public_ip"]) < 5:
            return -400, "Invalid public_ip: %s" %str(server_info.get("public_ip"))
        if server_info.get("public_gw_ip") is None or len(server_info["public_gw_ip"]) < 5:
            return -400, "Invalid public_gw_ip: %s" %str(server_info.get("public_gw_ip"))
        if server_info.get("mgmt_ip") is None or len(server_info["mgmt_ip"]) < 5:
            return -400, "Invalid mgmt_ip: %s" %str(server_info.get("mgmt_ip"))

        return 200, "OK"

    # Router check
    def _private_ip_check(self, public_ip):
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

    def _wf_check_validation(self, server_id, content):
        result, data = orch_dbm.get_db_server(mydb, server_id)
        if result <= 0:
            return result, data, False
        else:
            if data.get('nfsubcategory') != content.get('onebox_type'):
                return -1001, data, False

        # server_id 가 없을 경우
        # server_result, server_data = server_manager.get_server_with_filter(mydb, server_id, content.get('onebox_type'))
        # if server_result <= 0:
        #     return server_result, server_data, False

        # nic list의 mgmt_boolean 값이 모두 false 일때 return : One-Box agent 에서 체크해서 넘어오지만 한번더 체크한다.
        is_mgmt = False
        for nic in content['nic']:
            if nic['mgmt_boolean'] is False:
                continue

            is_mgmt = True
            break

        if is_mgmt is False:
            result = -1
        else:
            result = 200

        return result, None, is_mgmt

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        # log.debug("Response Body: %s" %body)

        self.set_header('Content-Type', content_type)
        self.finish(body)

    def _send_response_wf(self, result, rsp_body):
        content_type, body = util.format_out_wf(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        # log.debug("Response Body: %s" %body)

        self.set_header('Content-Type', content_type)
        self.finish(body)


# 작업 사전 테스트 용
class WorkHandler(RequestHandler):
    def initialize(self, opCode, plugins):
        self.opCode = opCode
        self.plugins = plugins

        # log.debug(self.opCode)

        # ###     Load Plugins        #####################################################################
        # comm_info = {'onebox_type': 'Common'}
        # req_info = {'onebox_type': 'KtPnf'}
        # work_info = {'onebox_type': 'Work'}
        #
        # # common manager
        # self.orch_comm = self.orch_comm.common_manager(comm_info)
        #
        # # server manager
        # self.wf_server_manager = self.wf_server_manager.server_manager(req_info)
        #
        # # action manager
        # self.wf_act_manager = self.wf_act_manager.act_manager(req_info)
        #
        # # work manager
        # self.wf_work_manager = self.wf_work_manager.work_manager(work_info)
        # ###     Load Plugins        #####################################################################

    def post(self, job_kind=None, server=None):
        if self.opCode == OPCODE_WORK_BASE64_RESPONSE:  # base64_response
            self._base64_response()
        elif self.opCode == OPCODE_WORK_JOB:  # 기타 테스트 전용
            self._work_job()
        elif self.opCode == OPCODE_WORK_MONITOR:  # 기타 테스트 전용
            self._work_monitor(job_kind, server)
        elif self.opCode == OPCODE_WORK_BOND:   # vnf script parsing bonding set
            self._work_bond()
        else:
            pass

    def get(self):
        if self.opCode == OPCODE_WORK_BASE64_REQUEST:  # base64_request
            self._base64_request()
        else:
            pass

    # get
    def _base64_request(self):
        log.debug('[Work] IN base64_request')
        result, data = self.wf_work_manager.base64_reqeust()

        self._send_response_wf(result, data)

    # post
    def _base64_response(self):
        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.work_schema_base64, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        log.debug('[Work] IN base64_response')
        result, data = self.wf_work_manager.base64_response(http_content)

        self._send_response_wf(result, data)

    def _work_job(self):
        log.debug('self.request = %s' %str(self.request))
        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.work_schema_base64, is_report=is_report)
        if result < 0:
            self._send_response(result, http_content)
            return

        log.debug('[Work] IN _work_job')
        result, data = self.wf_work_manager.job_test(self.request)
        # result, data = wf_work_manager.job_test(http_content)

        self._send_response_wf(result, data)

    def _work_monitor(self, kind, server):
        """
        :param kind: 모니터 동작(start, stop, suspend, resume)
        :param server: One-Box ID or SEQ
        :return:
        """

        plugins = {}
        plugins['orch_comm'] = self.plugins.get('orch_comm')
        result, data = self.plugins.get('wf_work_manager').work_monitor(kind, server, plugins)

        self._send_response_wf(result, data)


    def _work_bond(self):
        """
        :return:
        """

        http_content = json.loads(self.request.body)
        # log.debug('request.body = %s' %str(http_content))

        # log.debug('plugins = %s' %str(self.plugins))

        result, data = self.plugins.get('wf_work_manager').work_bond(http_content)
        # result, data = 200, "OK"

        self._send_response_wf(result, data)


    def _send_response_wf(self, result, rsp_body):
        content_type, body = util.format_out_wf(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        self.set_header('Content-Type', content_type)
        self.finish(body)
