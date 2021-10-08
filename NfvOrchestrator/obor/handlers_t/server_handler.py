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
import utils.log_manager as log_manager
from handlers_t.http_response import HTTPResponse
from utils import auxiliary_functions as af
from utils import db_conn_manager as dbmanager
log = log_manager.LogManager.get_instance()
import copy

from engine import server_manager, vim_manager, nsr_manager, authkey_manager
import orch_core as nfvo

import json

mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

import sqlite3

url_base_t = "/orch"

OPCODE_SERVER = "SERVER"
OPCODE_SERVER_ACTION = "SERVER_ACTION"
OPCODE_SERVER_ASSOCIATE = "SERVER_ASSOCIATE"
OPCODE_SERVER_PROGRESS = "SERVER_PROGRESS"
OPCODE_SERVER_BACKUPDATA = "SERVER_BACKUP_DATA"
# OPCODE_VPORT_PROGRESS = "VPORT_PROGRESS"

OPCODE_VIM = "VIM"
OPCODE_VIM_TENANT = "VIM_TENANT"
OPCODE_VIM_NETWORK = "VIM_NET"
OPCODE_VIM_IMAGE = "VIM_IMG"
OPCODE_VIM_ACTION = "VIM_ACT"
OPCODE_VIM_VDU = "VIM_VDU"
OPCODE_FLAVOR = "FLAVOR"
OPCODE_ACCOUNT = "ACCOUNT"

OPCODE_VNF_IMAGE_POST = "VNF_IMAGE"

OPCODE_AUTHKEY = "AUTHKEY"
OPCODE_AUTHKEY_MAKE = "AUTHKEY_MAKE"
OPCODE_AUTHKEY_UPDATE = "AUTHKEY_UPDATE"
OPCODE_AUTHKEY_DEPLOY = "AUTHKEY_DEPLOY"
OPCODE_AUTHKEY_DEPLOY_BATCH = "AUTHKEY_DEPLOY_BATCH"
OPCODE_AUTHKEY_FAIL_DEPLOY = "AUTHKEY_FAIL_DEPLOY"
OPCODE_AUTHKEY_FAIL_DEPLOY_BATCH = "AUTHKEY_FAIL_DEPLOY_BATCH"

OPCODE_TEST_POST = "TEST_POST"


def url(plugins):
    urls = [ (url_base_t + "/server/([^/]*)", ServerHandler, dict(opCode=OPCODE_SERVER, plugins=plugins)),
             (url_base_t + "/server", ServerHandler, dict(opCode=OPCODE_SERVER, plugins=plugins)),
             (url_base_t + "/server/([^/]*)/action", ServerHandler, dict(opCode=OPCODE_SERVER_ACTION, plugins=plugins)),
             (url_base_t + "/server/([^/]*)/customer", ServerHandler, dict(opCode=OPCODE_SERVER_ASSOCIATE)),
             (url_base_t + "/server/([^/]*)/progress", ServerHandler, dict(opCode=OPCODE_SERVER_PROGRESS)),     # 작업 상태 조회
             # (url_base_t + "/server/([^/]*)/progress/([^/]*)", ServerHandler, dict(opCode=OPCODE_VPORT_PROGRESS)),
             (url_base_t + "/server/([^/]*)/backup", ServerHandler, dict(opCode=OPCODE_SERVER_BACKUPDATA)),     # 백업 데이터 조회
             (url_base_t + "/vim", VimHandler, dict(opCode=OPCODE_VIM)),
             (url_base_t + "/vim/([^/]*)", VimHandler, dict(opCode=OPCODE_VIM)),
             (url_base_t + "/vim/([^/]*)/network", VimHandler, dict(opCode=OPCODE_VIM_NETWORK)),
             (url_base_t + "/vim/([^/]*)/image", VimHandler, dict(opCode=OPCODE_VIM_IMAGE)),
             (url_base_t + "/vim/([^/]*)/action", VimHandler, dict(opCode=OPCODE_VIM_ACTION)),
             (url_base_t + "/vim/([^/]*)/tenant", VimHandler, dict(opCode=OPCODE_VIM_TENANT)),
             (url_base_t + "/vim/([^/]*)/image/vnfd/vdu/([^/]*)", VimHandler, dict(opCode=OPCODE_VIM_VDU)),
             (url_base_t + "/onebox/flavor", FlavorHandler, dict(opCode=OPCODE_FLAVOR)),
             (url_base_t + "/onebox/flavor/([^/]*)", FlavorHandler, dict(opCode=OPCODE_FLAVOR)),
             (url_base_t + "/onebox/account", AccountHandler, dict(opCode=OPCODE_ACCOUNT)),
             (url_base_t + "/onebox/account/([^/]*)", AccountHandler, dict(opCode=OPCODE_ACCOUNT)),
             (url_base_t + "/server/([^/]*)/vnf/image", ServerHandler, dict(opCode=OPCODE_VNF_IMAGE_POST)),     #

             (url_base_t + "/onebox/authkey/([^/]*)", AuthkeyHandler, dict(opCode=OPCODE_AUTHKEY)),
             (url_base_t + "/onebox/authkey/([^/]*)/grp/([^/]*)/make", AuthkeyHandler, dict(opCode=OPCODE_AUTHKEY_MAKE)),
             (url_base_t + "/onebox/authkey/([^/]*)/update", AuthkeyHandler, dict(opCode=OPCODE_AUTHKEY_UPDATE)),
             (url_base_t + "/onebox/authkey/([^/]*)/deploy", AuthkeyHandler, dict(opCode=OPCODE_AUTHKEY_DEPLOY)),
             (url_base_t + "/onebox/authkey/batch-deploy/([^/]*)", AuthkeyHandler, dict(opCode=OPCODE_AUTHKEY_DEPLOY_BATCH)),
             (url_base_t + "/onebox/authkey/([^/]*)/fail-deploy", AuthkeyHandler, dict(opCode=OPCODE_AUTHKEY_FAIL_DEPLOY)),
             (url_base_t + "/onebox/authkey/batch-fail-deploy/([^/]*)", AuthkeyHandler, dict(opCode=OPCODE_AUTHKEY_FAIL_DEPLOY_BATCH)),

             (url_base_t + "/test/([^/]*)", TestHandler, dict(opCode=OPCODE_TEST_POST))

             ]
    return urls


class ServerHandler(RequestHandler):

    def initialize(self, opCode, plugins=None):
        self.opCode = opCode
        self.plugins = plugins

    def post(self, server_id=None, onebox_type=None):

        if self.opCode == OPCODE_SERVER_ACTION:
            self._http_post_server_action(server_id)
        elif self.opCode == OPCODE_SERVER_ASSOCIATE:
            self._http_associate_server(server_id)
        elif self.opCode == OPCODE_VNF_IMAGE_POST:
            self._http_post_vnf_image(server_id)
        else:
            # OneBox Agent에서 호출하는 API
            # tb_server에 필요한 정보를 등록처리.
            self._http_post_server(server_id)

    def get(self, server_id=None):
        """get server list or details, can use both id or name"""
        
        if self.opCode == OPCODE_SERVER_PROGRESS:
            # One-Box 상태 체크
            # # log.debug('request = %s' % str(self.request))
            # comm_dict = {'req':self.request, 'server_id':server_id}
            # chk_result, chk_data = self.plugins.get('orch_comm').getFunc("CheckIP", comm_dict)
            # # comm_dict.clear()
            # comm_dict = None
            #
            # if chk_result < 0:
            #     log.error(chk_data)
            #     self._send_response(chk_result, chk_data)
            #     return

            result, content = server_manager.get_server_progress_with_filter(mydb, server_id)
            log.debug('progress : result = %d, content = %s' %(result, str(content)))
            if result < 0:
                log.error("failed to check the progress of the One-Box: %s" %server_id)
            data = content
        elif self.opCode == OPCODE_SERVER_BACKUPDATA:
            # One-Box 백업데이타 조회
            result, content = server_manager.get_server_backup_data (mydb, server_id)
            if result < 0:
                log.error("failed to get Backup Data for %s" %server_id)
            data = content
        # elif self.opCode == OPCODE_VPORT_PROGRESS:
        #     result, content = nfvo.get_server_vport_progress(mydb, server_id, action_id)
        #     if result < 0:
        #         log.error("failed to check the progress of changing vport : %s" % server_id)
        #     data = content
        else:
            if server_id is None or server_id == "all":
                result, content = orch_dbm.get_server(mydb)
                if result < 0:
                    data = content
                else:
                    for c in content:
                        af.convert_datetime2str_psycopg2(c)
                    data={'server' : content}
            else:
                server_id = str(server_id)
                result, content = server_manager.get_server_with_filter(mydb, server_id)
                
                if result < 0:
                    data = content
                else:
                    for c in content:
                        af.convert_datetime2str_psycopg2(c)
                    data = content

        self._send_response(result, data)
        return


    def delete(self, server_id=None):

        if self.opCode == OPCODE_SERVER_ASSOCIATE:
            self._http_deassociate_server(server_id)
        else:
            self._http_delete_server(server_id)


    ### DELETE 내부함수 ###########################################################################

    def _http_deassociate_server(self, server_id):
        """deassociate an existing ponebox server from a customer. """
        result, data = server_manager.deassociate_server_from_customer(mydb, server_id)
        if result < 0:
            log.error("http_deassociate_server error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            self._send_response(result, {"result":data})
            return


    def _http_delete_server(self, server_id):
        """delete a server from database, can use both id or name"""
        if server_id is None:
            self._send_response(-HTTPResponse.Bad_Request, "No Target")
            return

        server_id = str(server_id)
        result, content = server_manager.delete_server(mydb, server_id)
        if result < 0:
            data = content
        else:
            data = content

        self._send_response(result, data)

    ### DELETE 내부함수 END ###########################################################################

    ### POST 내부함수 #################################################################################

    def _http_post_server(self, server_id=None):
        """create a physical onebox server for One-Box Service"""

        # log.debug('[WF Handler] remote_ip = %s' % str(self.request.remote_ip))
        # log.debug('[WF Handler] remote_ip = %s' % str(self.request))
        # remote ip file save
        # orch_comm.getFunc("file_save_ip", {'onebox_id':server_id, 'remote_ip' : self.request.remote_ip})

        is_report = True
        result, http_content = util.format_in(self.request, orch_schemas.server_schema, is_report=is_report)
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

        #r = af.remove_extra_items(http_content, orch_schemas.server_schema)
        #if r is not None:
        #    log.debug("Warning: remove extra items ", r)


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

        # 5G 사용여부 : wan list check
        router_yn = None

        # log.debug('wan_list = %s' %str(http_content.get('wan_list')))

        # for wan in http_content.get('wan_list'):
        #     if 'public_ip' in wan:
        #         if self._private_ip_check(wan.get('public_ip')) > 0:
        #             continue
        #
        #         router_yn = 1
        #         break

        # if router_yn:
        #     http_content['router'] = 'W'

        # 라우터 통해서 들어온 경우 통신 가능 하도록 public ip 를 remote_ip 로 대체
        if self._private_ip_check(http_content.get('public_ip')) == -1:
            old_public_ip = http_content.get('public_ip')
            remote_ip = self.request.remote_ip

            # log.debug('origin data = %s' % str(http_content['obagent']['base_url']))

            http_content['public_ip'] = remote_ip
            http_content['mgmt_ip'] = remote_ip

            obagent_base_url = http_content['obagent']['base_url']
            http_content['obagent']['base_url'] = obagent_base_url.replace(old_public_ip, remote_ip)

            # log.debug('replace origin data = %s' %str(http_content['obagent']['base_url']))

            vnfm_base_url = http_content['vnfm']['base_url']
            http_content['vnfm']['base_url'] = vnfm_base_url.replace(old_public_ip, remote_ip)

            vim_auth_url = http_content['vim']['vim_authurl']
            http_content['vim']['vim_authurl'] = vim_auth_url.replace(old_public_ip, remote_ip)

            http_content['router'] = 'W'

            # log.debug('change http_content = %s' %str(http_content))

        # request body validation check
        chk_result, chk_msg = self._server_info_check(http_content)
        if chk_result < 0:
            log.error("Invalid One-Box Info: %s" %str(chk_msg))
            self._send_response(chk_result, chk_msg)
        else:
            #[HJC_2019][START]
            #if http_content.get("onebox_type", "UNKNOWN") != "UNKNOWN":
            #    result, data = wf_server_manager.new_server(mydb, http_content)
            #[HJC_2019][END]

            managers = {}
            managers['wf_redis'] = self.plugins.get('wf_redis')

            if server_id:
                server_id = str(server_id)
                result, data = server_manager.new_server(mydb, http_content, filter_data=server_id, managers=managers)
            else:
                result, data = server_manager.new_server(mydb, http_content, managers=managers)

            if result > 0:
                server_result, server_data = server_manager.get_server_with_filter(mydb, data)
                data = server_data
                server_data = None
                # log.debug('data = %s' %str(data))
                # log.debug('server_data = %s' %str(server_data))
            elif not is_report and 0 > result != -400:
                log.warning("OBA Call Problem for this request \n  - REQUEST URL: %s" %str(self.request.uri))
                log.warning("  - REQUEST METHOD: %s" %str(self.request.method))
                log.warning("  - BODY: %s" %str(self.request.body))

            self._send_response(result, data)

    def _http_post_server_action(self, server):
        # parse input data
        result, http_content = util.format_in(self.request, orch_schemas.server_action_schema)

        log.debug("[NBI IN] Action for the One-Box %s" %(str(server)))
        log.debug("[NBI IN] Request Body = %s" %str(http_content))

        r = af.remove_extra_items(http_content, orch_schemas.server_action_schema)
        if r is not None:
            log.error("http_post_server_action: Warning: remove extra items: %s", str(r))

        # Work Flow 분기
        # log.debug('[action - backup] server type = %s' %str(type(server)))
        server_result, server_data = server_manager.get_server_with_filter(mydb, server)

        log.debug('[WF] server_result = %d, server_data = %s' % (server_result, str(server_data)))

        if server_result == 1:
            if server_data[0].get('nfsubcategory') == "One-Box":
                # 기존 소스

                if "backup" in http_content:
                    try:
                        # backup
                        result, data = server_manager.backup_onebox(mydb, http_content['backup'], server, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
                        if result < 0:
                            log.error("[NBI OUT] Action for the One-Box, Backup: Error %d %s" %(-result, data))
                            self._send_response(result, data)
                            return
                        else:
                            log.debug("[NBI OUT] Action for the One-Box, Backup: OK")
                            self._send_response(result, data)
                            return
                    except Exception, e:
                        log.error("_____##### Error in backup-onebox : %s" % str(e))
                        self._send_response(-500, "Backup One-Box Exception")
                        return

                elif "restore" in http_content:
                    result, data = nfvo.restore_onebox(mydb, http_content['restore'], server, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
                    if result < 0:
                        log.error("[NBI OUT] Action for the One-Box, Restore: Error %d %s" %(-result, data))
                        self._send_response(result, data)
                        return
                    else:
                        log.debug("[NBI OUT] Action for the One-Box, Restore: OK")
                        self._send_response(result, data)
                        return
                elif "freset" in http_content:
                    #result, data = server_manager.freset_onebox(mydb, http_content['freset'], server)
                    result, data = nfvo.restore_onebox(mydb, http_content['freset'], server, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
                    if result < 0:
                        log.error("[NBI OUT] Action for the One-Box, Restore to Init: Error %d %s" %(-result, data))
                        self._send_response(result, data)
                        return
                    else:
                        log.debug("[NBI OUT] Action for the One-Box, Restore to Init: OK")
                        self._send_response(result, data)
                        return
                elif "check" in http_content:
                    result, data = server_manager.check_onebox_valid(mydb, http_content['check'], server)
                    if result < 0:
                        log.error("[NBI OUT] Action for the One-Box, Check One-Box: Error %d %s" %(-result, data))
                        self._send_response(result, data)
                        return
                    else:
                        ################## Test Code: Get Default NS Info ######################
                        # log.debug("[NBI TEST] Get Default NS Info")
                        # result, content = nsr_manager.handle_default_nsr(mydb, customer_id=89, onebox_id="INSDEV5.OB1", default_ns_id="9ace2b93-4141-4597-bff0-43a7b72a028e", server_dict=None, tid=None, tpath="")
                        # log.debug("[NBI TEST] Get Default NS Info - Result = %d, %s" %(result, str(content)))
                        ################## Test Code: Get Default NS Info ######################

                        log.debug("[NBI OUT] Action for the One-Box, Check One-Box: %s" %(str(data)))
                        self._send_response(result, {"check":data})
                        return
                elif "reset_mac" in http_content:
                    result, data = server_manager.reset_mac(mydb, http_content['reset_mac'], server)
                    if result < 0:
                        log.error("[NBI OUT] Action for the One-Box, Reset Mac Address: Error %d %s" %(-result, data))
                        self._send_response(result, data)
                        return
                    else:
                        log.debug("[NBI OUT] Action for the One-Box, Reset Mac Address: %s" %(str(data)))
                        self._send_response(result, {"result":"OK"})
                        return

                elif "nsrestore" in http_content: # 사용안함. 추후 삭제 : NS 복구는 NfvNsrHandler에서 처리.
                    result, data = nfvo.restore_onebox_nsr(mydb, http_content['nsrestore'], server)
                    if result < 0:
                        log.error("[NBI OUT] Action for the One-Box, NS Restore: Error %d %s" %(-result, data))
                        self._send_response(result, data)
                        return
                    else:
                        log.debug("[NBI OUT] Action for the One-Box, NS Restore: OK")
                        self._send_response(result, data)
                        return

                elif "nic_mod" in http_content: # 포트 추가삭제(설정변경). BTA에서 요청함.
                    # 라우터 통해서 들어온 경우 통신 가능 하도록 public ip 를 remote_ip 로 대체
                    origin_ip = copy.deepcopy(http_content['nic_mod'].get('public_ip'))
                    remote = {'origin_ip':origin_ip, 'public_ip':None, 'router':False}

                    if self._private_ip_check(http_content['nic_mod'].get('public_ip')) == -1:
                        old_public_ip = http_content['nic_mod'].get('public_ip')
                        remote_ip = self.request.remote_ip

                        # log.debug('origin data = %s' % str(http_content['obagent']['base_url']))

                        http_content['nic_mod']['public_ip'] = remote_ip
                        http_content['nic_mod']['mgmt_ip'] = remote_ip

                        obagent_base_url = http_content['nic_mod']['obagent']['base_url']
                        http_content['nic_mod']['obagent']['base_url'] = obagent_base_url.replace(old_public_ip, remote_ip)

                        # log.debug('replace origin data = %s' %str(http_content['obagent']['base_url']))

                        vnfm_base_url = http_content['nic_mod']['vnfm']['base_url']
                        http_content['nic_mod']['vnfm']['base_url'] = vnfm_base_url.replace(old_public_ip, remote_ip)

                        vim_auth_url = http_content['nic_mod']['vim']['vim_authurl']
                        http_content['nic_mod']['vim']['vim_authurl'] = vim_auth_url.replace(old_public_ip, remote_ip)

                        # 라우터 사용여부 추가
                        remote['public_ip'] = remote_ip
                        remote['router'] = True

                    result, data = nfvo.modify_nic(mydb, http_content['nic_mod'], server, remote=remote)
                    if result < 0:
                        log.error("[NBI OUT] Action for the One-Box, NIC modify: Error %d %s" %(-result, data))
                        self._send_response(result, data)
                        return
                    else:
                        log.debug("[NBI OUT] Action for the One-Box, NS Restore: OK")
                        self._send_response(result, data)
                        return
                else:
                    self._send_response(HTTPResponse.Bad_Request, "Not supported Action")
                    return
            else:
                # 초소형 PNF

                log.debug('[WF] update_onebox_info : http_content = %s' %str(http_content))

                if 'backup' in http_content:
                    action_category = "Backup"
                elif 'restore' in http_content:
                    action_category = "Restore"
                elif 'reset_mac' in http_content:
                    action_category = "ResetMac"
                # check, reboot 은 새로운 api 로 호출
                # elif 'check' in http_content:
                #     action_category = "Check"
                # elif 'reboot' in http_content:
                #     action_category = "Reboot"
                else:
                    action_category = ""

                try:
                    is_report = True
                    http_content['onebox_type'] = server_data[0].get('nfsubcategory')
                    http_content['onebox_id'] = server_data[0].get('onebox_id')

                    # KtPnf backup

                    managers = {}
                    managers['orch_comm'] = self.plugins.get('orch_comm')
                    managers['wf_server_manager'] = self.plugins.get('wf_server_manager')
                    managers['wf_act_manager'] = self.plugins.get('wf_act_manager')
                    managers['wf_monitorconnector'] = self.plugins.get('wf_monitorconnector')
                    managers['wf_obconnector'] = self.plugins.get('wf_obconnector')
                    managers['wf_Odm'] = self.plugins.get('wf_Odm')

                    result, data = self.plugins.get('wf_act_manager').action(http_content, managers, action_category)

                    if result < 0:
                        log.error("[NBI OUT] Action for the One-Box, Backup: Error %d %s" % (-result, data))
                        self._send_response(result, data)
                        return
                    else:
                        log.debug("[NBI OUT] Action for the One-Box, Backup: OK")
                        self._send_response(result, data)
                        return
                except Exception, e:
                    log.error("_____##### Error in %s backup-onebox : %s" % (str(server_data[0].get('nfsubcategory')), str(e)))
                    self._send_response(-500, "%s Action : %s One-Box Exception" % (str(server_data[0].get('nfsubcategory')), str(action_category)))
                    return
        else:
            log.debug("No Search One-Box data")
            result, data = server_result, server_data
            self._send_response(result, data)
            return


    def _http_associate_server(self, server):
        """associate an existing ponebox server to a customer. """
        result, http_content = util.format_in(self.request, orch_schemas.server_associate_schema)
        r = af.remove_extra_items(http_content, orch_schemas.server_associate_schema)

        if r is not None:
            log.error("http_associate_server: Warning: remove extra items ", r)

        result, data = server_manager.associate_server_with_customer(mydb, server, http_content['server'])

        if result < 0:
            log.error("http_associate_server error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            log.debug("http_associate_server data %s" % data)
            return self.get(data)


    def _http_post_vnf_image(self, onebox_id):

        log.debug("[NBI IN] Change VNF Image ID: /server/%s/vnf/image" % str(onebox_id))

        result, http_content = util.format_in(self.request, orch_schemas.vnf_image_id_schema)
        log.debug("http_content %d\n%s" % (result,http_content))

        result, data = server_manager.update_vnf_image_id(mydb, onebox_id, http_content, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))

        if result < 0:
            log.error("[NBI OUT] Change VNF Image ID: Error %d %s" %(-result, data))
        else:
            log.debug("[NBI OUT] Change VNF Image ID: OK")

        self._send_response(result, data)

    ### POST 내부함수 END ###########################################################################

    def _order_check_validation(self, server_id, http_content):
        result, data = orch_dbm.get_db_server(mydb, server_id)
        if result <= 0:
            return result, data, False
        else:
            if data.get('nfsubcategory') == "KtPnf":
                return -1001, data, False

        return 200, "OK", True

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

    def _server_info_check(self, server_info):
        if server_info.get("public_ip") is None or len(server_info["public_ip"]) < 5:
            return -400, "Invalid public_ip: %s" %str(server_info.get("public_ip"))
        if server_info.get("public_gw_ip") is None or len(server_info["public_gw_ip"]) < 5:
            return -400, "Invalid public_gw_ip: %s" %str(server_info.get("public_gw_ip"))
        if server_info.get("mgmt_ip") is None or len(server_info["mgmt_ip"]) < 5:
            return -400, "Invalid mgmt_ip: %s" %str(server_info.get("mgmt_ip"))

        return 200, "OK"

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



class VimHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode


    def post(self, vim_id=None):
        log.debug("IN POST with opCode = %s" %str(self.opCode))

        if self.opCode == OPCODE_VIM:
            self._http_post_vim()
        elif self.opCode == OPCODE_VIM_ACTION:
            self._http_vim_action(vim_id)
        elif self.opCode == OPCODE_VIM_TENANT:
            self._http_associate_vim(vim_id)

    def get(self, vim_id=None, vdu_name=None):

        """get server list or details, can use both id or name"""
        log.debug("IN GET with opCode = %s" %str(self.opCode))

        if self.opCode == OPCODE_VIM:

            # if vim_id == "/network" or vim_id == "/image":
            #     self._send_response(-HTTPResponse.Bad_Request, "No Target")
            #     return
            
            if vim_id is None or vim_id == "all":
                result, content = orch_dbm.get_vim_list(mydb)
                if result < 0:
                    data = content
                else:
                    for c in content:
                        af.convert_datetime2str_psycopg2(c)
                    data = {'vim_list' : content}
            else:
                vim_id = str(vim_id)
                result, content = orch_dbm.get_vim_id(mydb, vim_id)
                
                if result < 0:
                    data = content
                else:
                    af.convert_datetime2str_psycopg2(content)
                    data = {'vim' : content}

            self._send_response(result, data)

        elif self.opCode == OPCODE_VIM_NETWORK:
            self._http_getnetwork_vim(vim_id)

        elif self.opCode == OPCODE_VIM_IMAGE:
            self._http_getimage_vim(vim_id)

        elif self.opCode == OPCODE_VIM_VDU:
            self._http_getimage_vim_vdu(vim_id, vdu_name)

        else:
            self._send_response(-HTTPResponse.Not_Found, "Not Supported API")


    def delete(self, vim=None):

        if self.opCode == OPCODE_VIM:
            self._http_delete_vim(vim)
        elif self.opCode == OPCODE_VIM_TENANT:
            self._http_deassociate_vim(vim)



    ### VimHandler POST 내부함수 ############################################################################

    def _http_post_vim(self):
        """insert a VIM for an One-Box Server. """
        #parse input data
        result, http_content = util.format_in(self.request, orch_schemas.vim_schema )
        r = af.remove_extra_items(http_content, orch_schemas.vim_schema)

        if r is not None:
            log.debug("http_post_vim: Warning: remove extra items ", r)

        result, data = vim_manager.new_vim(mydb, http_content['vim'])

        if result < 0:
            log.error("http_post_vim error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            #return http_get_vim_id(data)
            self.opCode = OPCODE_VIM
            return self.get(data)


    def _http_vim_action(self, vim_id):

        log.debug("API Resource Variable: %s" %vim_id)

        if vim_id is None:
            self._send_response(-HTTPResponse.Bad_Request, "No Target")
            return

        result, http_content = util.format_in(self.request, orch_schemas.vim_action_schema )

        if result < 0:
            self._send_response(result, http_content)
            return

        r = af.remove_extra_items(http_content, orch_schemas.vim_action_schema)
        if r is not None:
            log.debug("Warning: remove extra items ", r)

        vim_id = str(vim_id)
        result, content = vim_manager.vim_action(mydb, vim_id, http_content)
        if result < 0:
            data = content
        elif 'net-update' in http_content:
            net_result, content = orch_dbm.get_vim_networks(mydb, vim_id)
            if net_result < 0:
                result = net_result
                data = content
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)
                af.convert_str2boolean(content, ('sharedyn', 'multipointyn', 'createdyn') )
                data={'vim_network' : content}
        elif 'image-update' in http_content:
            img_result, content = orch_dbm.get_vim_images(mydb, vim_id)
            if img_result < 0:
                result = img_result
                data = content
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)
                af.convert_str2boolean(content, ('createdyn') )
                data={'vim_image' : content}
        else:
            data = content

        self._send_response(result, data)


    def _http_associate_vim(self, vim_id):
        """associate an existing vim to a this tenant. """
        #parse input data
        result, http_content = util.format_in(self.request, orch_schemas.vim_associate_schema )
        r = af.remove_extra_items(http_content, orch_schemas.vim_associate_schema)

        if r is not None:
            log.error("http_associate_vim: Warning: remove extra items ", r)

        result, data = vim_manager.associate_vim_with_tenant(mydb, vim_id,
                                    http_content['vim_tenant'].get('uuid'),
                                    http_content['vim_tenant'].get('name'),
                                    http_content['vim_tenant'].get('username'),
                                    http_content['vim_tenant'].get('password')
                         )
        if result < 0:
            log.error("http_associate_vim error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            log.debug("http_associate_vim data %s" % data)
            #return http_get_vim_id(data)
            self.opCode = OPCODE_VIM
            return self.get(data)

    ### END : VimHandler POST 내부함수 ############################################################################

    ### VimHandler GET 내부함수 ############################################################################

    def _http_getnetwork_vim(self, vim_id):
        if vim_id is None:
            self._send_response(-HTTPResponse.Bad_Request, "No Target")
            return
        vim_id = str(vim_id)
        result, content = orch_dbm.get_vim_networks(mydb, vim_id)
        if result < 0:
            self._send_response(result, content)
            return
        else:
            for c in content:
                af.convert_datetime2str_psycopg2(c)

            af.convert_str2boolean(content, ('sharedyn', 'multipointyn', 'createdyn') )
            self._send_response(result, {'result_list' : content})
            return


    def _http_getimage_vim(self, vim_id):

        if vim_id is None:
            self._send_response(-HTTPResponse.Bad_Request, "No Target")
            return

        vim_id = str(vim_id)
        result, content = orch_dbm.get_vim_images(mydb, vim_id)
        if result < 0:
            self._send_response(result, content)
            return
        else:
            for c in content:
                af.convert_datetime2str_psycopg2(c)

            af.convert_str2boolean(content, ('createdyn') )
            self._send_response(result, {'result_list' : content})
            return


    def _http_getimage_vim_vdu(self, vim, vdu_name):
        result, content = orch_dbm.get_vim_images_vdu(mydb, vim, vdu_name)
        if result < 0:
            log.error("http_getimage_vim_vdu error %d %s" % (result, content))
            self._send_response(result, content)
            return

        for c in content:
            af.convert_datetime2str_psycopg2(c)
        af.convert_str2boolean(content, ('createdyn') )
        self._send_response(result, {'result_list' : content})
        return
    ### END : VimHandler GET 내부함수 ############################################################################

    ### VimHandler DELETE 내부함수 ############################################################################

    def _http_delete_vim(self, vim):
        """delete a vim from database, can use both uuid or name"""
        result, data = vim_manager.delete_vim(mydb, vim)

        if result < 0:
            log.error("http_delete_vim error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            self._send_response(result, {"result":"vim " + data + " deleted"})
            return

    def _http_deassociate_vim(self, vim_id):
        """deassociate an existing vim to a this tenant. """

        result, data = vim_manager.deassociate_vim_from_tenant(mydb, vim_id)
        if result < 0:
            log.error("http_deassociate_vim error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            self._send_response(result, {"result":data})
            return
     ### END : VimHandler DELETE 내부함수 ############################################################################



    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        self.finish(body)            



class FlavorHandler(RequestHandler):
    def initialize(self, opCode):
        self.opCode = opCode

    def post(self):

        result, http_content = util.format_in(self.request, orch_schemas.onebox_flavor_schema)
        r = af.remove_extra_items(http_content, orch_schemas.onebox_flavor_schema)

        if r is not None:
            log.debug("http_post_onebox_flavor: Warning: remove extra items ", r)

        result, data = server_manager.new_onebox_flavor(mydb, http_content)

        if result < 0:
            log.error("http_post_onebox_flavor error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            log.info("http_post_onebox_flavor: new S/W %s" % data)
            self._send_response(result, {"result": str(data)+" One-Box flavor are added."})
            return


    def get(self, flavor_id=None):

        if flavor_id is not None:
            result, data = server_manager.get_onebox_flavor_id(mydb, flavor_id)

            if result < 0:
                log.error("http_get_onebox_flavor_id error %d %s" % (result, data))
            else:
                af.convert_datetime2str_psycopg2(data)

            self._send_response(result, data)
            return

        else:
            result, content = server_manager.get_onebox_flavor_list(mydb)

            if result < 0:
                log.error("http_get_onebox_flavor_id error %d %s" % (result, content))
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

                self._send_response(result, {'onebox_flavor_list' : content})
                return


    def delete(self, flavor_id):

        result, data = server_manager.delete_onebox_flavor_id(mydb, flavor_id)
        if result < 0:
            log.error("http_delete_onebox_flavor_id error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            self._send_response(result, {"result":"One-Box flavor " + str(data) + " deleted"})
            return

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            #log.info("Success: response %s" % str(rsp_body))
            pass

        self.set_header('Content-Type', content_type)
        self.finish(body)


class AccountHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode

    def post(self):

        result, http_content = util.format_in(self.request, orch_schemas.vnf_account_schema)
        r = af.remove_extra_items(http_content, orch_schemas.vnf_account_schema)

        if r is not None:
            log.debug("http_post_onebox_account: Warning: remove extra items ", r)

        result, data = server_manager.new_onebox_account(mydb, http_content)

        if result < 0:
            log.error("http_post_onebox_account error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            self._send_response(result, data)
            return


    def delete(self, onebox_id):

        result, data = server_manager.delete_onebox_account(mydb, onebox_id, is_auto=False)

        if result < 0:
            log.error("delete_onebox_account error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            log.info("delete_onebox_account: made One-Box Account")
            self._send_response(result, {"result": "One-Box account deleted.", "msg" : data})
            return

    def get(self):

        log.debug("Request Body = %s" %str(self.request))

        account_id = self.get_argument("account_id")
        account_pw = self.get_argument("account_pw")

        if account_id is None:
            log.debug("Account ID is empty")
            self._send_response(HTTPResponse.Bad_Request, "")
            return

        result, data = server_manager.check_server_account(mydb, account_id, account_pw)

        if result < 0:
            log.error("check_server_account error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            self._send_response(result, data)
            return

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            pass

        self.set_header('Content-Type', content_type)
        self.finish(body)


class AuthkeyHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode

    def post(self, val, grp=None):

        # result, http_content = util.format_in(self.request, orch_schemas.vnf_account_schema)
        # r = af.remove_extra_items(http_content, orch_schemas.vnf_account_schema)
        #
        # if r is not None:
        #     log.debug("Warning: remove extra items ", r)

        if self.opCode == OPCODE_AUTHKEY_MAKE:
            # val : ob_account
            result, data = authkey_manager.create_account(mydb, val, grp)

        elif self.opCode == OPCODE_AUTHKEY_UPDATE:
            # val : ob_account
            result, data = authkey_manager.update_authkey(mydb, val)

        elif self.opCode == OPCODE_AUTHKEY_DEPLOY:
            # val : auth_deploy_seq
            result, data = authkey_manager.deploy_order(mydb, val)

        elif self.opCode == OPCODE_AUTHKEY_DEPLOY_BATCH:
            # val : YYYYMMDDHH - 배치시간
            result, data = authkey_manager.reserve_deploy_batch(mydb, val, "B")

        elif self.opCode == OPCODE_AUTHKEY_FAIL_DEPLOY:
            # val : 배포실패테이블 키 [deploy_fail_seq]
            result, data = authkey_manager.deploy_fail(mydb, val)

        elif self.opCode == OPCODE_AUTHKEY_FAIL_DEPLOY_BATCH:
            # val : YYYYMMDDHH - 배치시간
            result, data = authkey_manager.reserve_deploy_batch(mydb, val, "F")
        else:
            result, data = -500, "The URL is wrong"

        if result < 0:
            log.error("Error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            self._send_response(result, data)
            return


    def delete(self, ob_account):

        result, data = authkey_manager.delete_account(mydb, ob_account)

        if result < 0:
            log.error("delete_account error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            log.info("delete_account: made One-Box Account")
            self._send_response(result, {"result": "One-Box account deleted.", "msg" : data})
            return

    def get(self):

        log.debug("Request Body = %s" %str(self.request))


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            pass

        self.set_header('Content-Type', content_type)
        self.finish(body)


class TestHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode

    def post(self, id=None):

        # result, http_content = util.format_in(self.request, orch_schemas.vnf_account_schema)
        # r = af.remove_extra_items(http_content, orch_schemas.vnf_account_schema)
        #
        # if r is not None:
        #     log.debug("http_post_onebox_account: Warning: remove extra items ", r)

        log.debug("TestHandler : POST : %s" % self.request.body)
        # result, data = server_manager.test_function(mydb, id)
        # result, data = authkey_manager.create_account(mydb, "")
        #
        # if result < 0:
        #     log.error("test_function error %d %s" % (-result, data))
        #     self._send_response(result, data)
        #     return
        # else:
        #     self._send_response(result, data)
        #     return


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            pass

        self.set_header('Content-Type', content_type)
        self.finish(body)

