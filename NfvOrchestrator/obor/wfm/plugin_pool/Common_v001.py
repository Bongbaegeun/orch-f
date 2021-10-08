# -*- coding: utf-8 -*-

from wfm.plugin_spec.CommonSpec import CommonSpec

import requests
import json
import sys
import time
import uuid as myUuid
from httplib import HTTPException
from requests.exceptions import ConnectionError

from utils import auxiliary_functions as af

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

import db.dba_manager as orch_dbm
# from utils.config_manager import ConfigManager

from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

from engine.server_status import SRVStatus
from engine.action_status import ACTStatus
# from image_status import ImageStatus
from engine.action_type import ActionType
from engine.nfr_status import NFRStatus
from engine.nsr_status import NSRStatus

class Common(CommonSpec):
    def __init__(self):
        self.host = None
        self.port = None

    def __setitem__(self, key, value):
        if key=='host':
            self.host=value
        elif key=='port':
            self.port=value

    def get_version(self):
        log.debug("IN get_version()")
        return 1, "v0.0.1"

    # 함수 생성시마다 spec, manager 까지 수정할 필요없게 하기 위한 컨트롤 함수
    def getFunc(self, funcNm=None, data_dict=None):
        log.debug('[Common] funcNm = %s' % str(funcNm))

        if funcNm is not None:
            result, data = getattr(self, funcNm)(data_dict)
            return result, data

    # def _update_server_status(self, server_dict, is_action=False, e2e_log=None, action_type=None):
    def update_server_status(self, data_dict):
        """
        서버의 상태값 업데이트 및 오더매니져에 Inform
        :param data_dict: server_dict, is_action, e2e_log, action_tyhpe
        :return:
        """

        try:
            server_dict = data_dict['server_dict']
            is_action = data_dict['is_action']
            e2e_log = data_dict['e2e_log']
            action_type = data_dict['action_type']

            # Step 0. Check server_dict
            if server_dict.get('serverseq') is None:
                log.error("Cannot update server status due to no serverseq: %s" % str(server_dict))
                raise Exception("Cannot update server status due to no serverseq: %s" % str(server_dict))

            # Step 1. Get Server Data from DB
            os_result, os_data = orch_dbm.get_server_id(server_dict['serverseq'])
            if os_result < 0:
                log.error("failed to get Server Info from DB: %d %s" % (os_result, os_data))
                raise Exception("failed to get Server Info from DB: %d %s" % (os_result, os_data))

            # Step 2. Update Server Data in DB
            if os_data.get('status') == server_dict.get('status', None):
                # log.debug("Don't need to update Server Status: %s" %os_data.get('status'))
                return 200, os_data.get('status')

            if server_dict.get('onebox_id') is None or server_dict['onebox_id'] != os_data.get('onebox_id'):
                server_dict['onebox_id'] = os_data.get('onebox_id')

            us_result, us_data = orch_dbm.update_server_status(server_dict, is_action=is_action)
            if us_result < 0:
                log.error("failed to update Server Info from DB: %d %s" % (us_result, us_data))
                raise Exception("failed to update Server Info from DB: %d %s" % (us_result, us_data))
            else:
                log.debug("Succeed to update server status: %s" % server_dict.get('status'))

            # Step 3. Notify to Order Manager
            if "order_type" in server_dict and server_dict["order_type"] == "ORDER_OB_NEW":
                pass
            elif server_dict.get("status", None) and action_type != ActionType.BACUP:  # PROVS/DELNS/NSRUP
                # if action_type == ActionType.PROVS or action_type == ActionType.DELNS or action_type == ActionType.NSRUP:
                #     pass
                # myOdm = odmconnector.odmconnector({"onebox_type": "General"})
                myOdm = data_dict.get('wf_Odm')
                noti_result, noti_data = myOdm.inform_onebox_status(server_dict['onebox_id'], server_dict.get('status'))
                if noti_result < 0:
                    log.error("Failed to inform One-Box's Status to the Order Manager: %d %s" % (noti_result, noti_data))
                    raise Exception("Failed to inform One-Box's Status to the Order Manager: %d %s" % (noti_result, noti_data))
                else:
                    log.debug("Succeed to inform new server status to the Order Manager : %s" % server_dict['status'])
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, str(e)

        return 200, "OK"

    def update_onebox_status_internally(self, data_dict):
        try:
            action_dict = data_dict['action_dict']
            action_status = data_dict['action_status']
            action_type = data_dict['actiontype']
            ob_data = data_dict['ob_data']
            ob_status = data_dict['ob_status']

            if action_dict and action_status:
                action_dict['status'] = action_status
                if action_status == ACTStatus.FAIL or action_status == ACTStatus.SUCC:
                    action_dict['action'] = action_type + "E" # NGKIM: Use RE for restore
                else:
                    action_dict['action'] = action_type + "S" # NGKIM: Use RE for restore

                orch_dbm.insert_action_history(action_dict)

            if ob_data and ob_status:
                ob_data['status'] = ob_status
                if ob_status == SRVStatus.ERR or ob_status == SRVStatus.INS or ob_status == SRVStatus.RDS or ob_status == SRVStatus.RIS or ob_status == SRVStatus.DSC:
                    ob_data['action']= action_type + "E"
                else:
                    ob_data['action']= action_type + "S"

                sts_dict = {}
                sts_dict['server_dict'] = ob_data
                sts_dict['is_action'] = True
                sts_dict['e2e_log'] = None
                sts_dict['action_type'] = action_type
                sts_dict['wf_Odm'] = data_dict.get('wf_Odm')

                self.update_server_status(sts_dict)

        except Exception, e:
            log.exception("Exception: %s" %str(e))

        return 200, "OK"


    # def update_nsr_status(self, action_type, action_dict=None, action_status=None, nsr_data=None, nsr_status=None, server_dict=None, server_status=None, nsr_status_description=None):
    def update_nsr_status(self, req_dict=None):
        try:
            # log.debug('update_nsr_status : req_dict = %s' %str(req_dict))

            server_dict = req_dict.get('server_dict')
            server_status = req_dict.get('server_status')

            if req_dict.get('onebox_type') == "KtPnf":
                # PNF or ARM type
                pass
            else:
                # Other type
                action_dict = req_dict.get('action_dict')
                action_status = req_dict.get('action_status')
                action_type = req_dict.get('action_type')
                nsr_data = req_dict.get('nsr_data')
                nsr_status = req_dict.get('nsr_status')
                nsr_status_description = req_dict.get('nsr_status_description', None)

                if action_dict and action_status:
                    action_dict['status'] = action_status
                    if action_status == ACTStatus.FAIL or action_status == ACTStatus.SUCC:
                        action_dict['action'] = action_type + "E"
                    else:
                        action_dict['action'] = action_type + "S"

                    orch_dbm.insert_action_history(action_dict)

                if nsr_data and nsr_status:
                    nsr_data['status'] = nsr_status
                    if nsr_status == NSRStatus.ERR or nsr_status == NSRStatus.RUN:
                        nsr_data['action'] = action_type + "E"
                    else:
                        nsr_data['action'] = action_type + "S"

                    nsr_data['status_description'] = "Action: %s, Result: %s" % (action_type, nsr_status)
                    if nsr_status_description:
                        nsr_data['status_description'] += ", Cause: " + nsr_status_description

                    orch_dbm.update_nsr(nsr_data)
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
                                    orch_dbm.update_nsr_vnf(vnf_data)
                    except Exception, e:
                        log.exception("Exception: %s" % str(e))

            if server_dict and server_status:
                if req_dict.get('onebox_type') == "KtArm":
                    server_dict['status'] = server_status

                    update_dict = {}
                    update_dict['server_dict'] = server_dict
                    update_dict['is_action'] = None
                    update_dict['e2e_log'] = None
                    update_dict['action_type'] = None

                    update_dict['wf_Odm'] = req_dict['wf_Odm']
                    self.update_server_status(update_dict)
                else:
                    server_dict['status'] = server_status
                    server_dict['wf_Odm'] = req_dict['wf_Odm']
                    self.update_server_status(server_dict)

        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))

        return 200, "OK"


    def get_onebox_agent(self, data_dict):
        """
        Onebox Agent Connector 객체를 얻는다.
        :param data_dict: onebox_id, nsr_id
        :return:
        """

        onebox_id = data_dict.get('onebox_id')
        # nsr_id = data_dict['nsr_id']

        filter_dict = {}
        filter_dict['onebox_type'] = data_dict.get('onebox_type')
        if onebox_id:
            if type(onebox_id) is int or type(onebox_id) is long or (type(onebox_id) is unicode and onebox_id.isnumeric()):
                filter_dict['serverseq'] = onebox_id
            elif type(onebox_id) is str and onebox_id.isdigit():
                filter_dict['serverseq'] = onebox_id
            else:
                filter_dict['onebox_id'] = onebox_id
        # elif nsr_id:
        #     filter_dict['nsseq'] = nsr_id
        else:
            return -HTTP_Bad_Request, "Invalid Condition"

        # log.debug('[WF - Common] filter_dict = %s' %str(filter_dict))
        result, content = orch_dbm.get_server_filters(filter_dict)

        # log.debug('[Common] get_onebox_agent > get_server_filters : result = %d, content = %s' %(result, str(content)))

        if result < 0:
            log.error("get_onebox_agent error %d %s" % (result, content))
            return result, content
        elif result == 0:
            log.error("get_onebox_agent not found a valid One-Box Agent with the input params " + str(onebox_id))
            return -HTTP_Not_Found, "One-Box Agent not found for " + str(onebox_id)

        if content[0]['obagent_base_url'] is None:
            log.error("No Access URL. Cannot connect to the OB Agent of the One-Box %s" % str(onebox_id))
            return -HTTP_Not_Found, "No Access URL. Cannot connect to the OB Agent of the One-Box %s" % str(onebox_id)

        # obconn_dict = {}
        #
        # # wfm, sbpm 성격상 onebox_type 으로 플러그인 로드하지만, connector 의 경우 공통(General)으로 사용한다. 추후 필요시 추가하는 경우에 onebox_type은 변수로 사용한다.
        # obconn_dict['onebox_type'] = "General"
        #
        # obconn_dict['name'] = content[0]['servername']
        # obconn_dict['url'] = content[0]['obagent_base_url']
        # obconn_dict['host'] = None
        # obconn_dict['port'] = None
        # obconn_dict['uuid'] = None
        # obconn_dict['user'] = None
        # obconn_dict['passwd'] = None
        # obconn_dict['debug'] = True
        # obconn_dict['config'] = None
        #
        # # log.debug('[Common] get_onebox_agent called obconnector : obconn_dict = %s' %str(obconn_dict))

        ob_dict = {}
        # ob_dict[content[0]['serverseq']] = obconnector.obconnector(obconn_dict)
        ob_dict[content[0]['serverseq']] = data_dict.get('wf_obconnector')

        # log.debug('[Common] obconnector : len(ob_dict) = %d, ob_dict = %s' %(len(ob_dict), str(ob_dict)))

        return len(ob_dict), ob_dict

    def get_server_all_with_filter(self, filter_data=None):
        """
        서버정보와 해당 서버의 vim정보를 조회
        :param filter_data:
        :return:
        """

        onebox_id = filter_data.get('onebox_id')
        onebox_type = filter_data.get('onebox_type')

        filter_dict = {}
        if onebox_id is None:
            return -HTTP_Bad_Request, "Invalid Condition"
        elif type(onebox_id) is int or type(onebox_id) is long or (type(onebox_id) is unicode and onebox_id.isnumeric()):
            filter_dict['serverseq'] = onebox_id
        elif type(onebox_id) is str and onebox_id.isdigit():
            filter_dict['serverseq'] = onebox_id
        elif af.is_ip_addr(onebox_id):
            filter_dict['public_ip'] = onebox_id
        else:
            filter_dict['onebox_id'] = onebox_id

        filter_dict['onebox_type'] = onebox_type

        log.debug('[get_server_all_with_filter] filter_dict = %s' %str(filter_dict))

        result, content = orch_dbm.get_server_filters(filter_dict)

        if result <= 0:
            return result, content

        # content['vims'] = None

        # for c in content:
        #     vim_result, vim_content = orch_dbm.get_vim_serverseq(c['serverseq'])
        #     if vim_result <= 0:
        #         log.debug("No VIM info found for the Server: %s" % str(c['serverseq']))
        #     else:
        #         c['vims'] = vim_content

        return 200, content


    def get_server_all_with_filter_wf(self, filter_data=None):
        """
        서버정보와 해당 서버의 vim정보를 조회
        :param filter_data:
        :return:
        """

        onebox_id = filter_data.get('onebox_id')
        # onebox_type = filter_data.get('onebox_type', None)

        filter_dict = {}
        if onebox_id is None:
            return -HTTP_Bad_Request, "Invalid Condition"
        elif type(onebox_id) is int or type(onebox_id) is long or (type(onebox_id) is unicode and onebox_id.isnumeric()):
            filter_dict['serverseq'] = onebox_id
        elif type(onebox_id) is str and onebox_id.isdigit():
            filter_dict['serverseq'] = onebox_id
        elif af.is_ip_addr(onebox_id):
            filter_dict['public_ip'] = onebox_id
        else:
            filter_dict['onebox_id'] = onebox_id

        # filter_dict['onebox_type'] = onebox_type

        log.debug('[get_server_all_with_filter] filter_dict = %s' %str(filter_dict))

        result, content = orch_dbm.get_server_filters_wf(filter_dict)

        if result <= 0:
            return result, content

        return 200, content


    # 메모 처리
    def setMemo(self, memo_dict):
        log.debug('memo_dict = %s' %str(memo_dict))
        # result, memo_r = orch_dbm.get_memo_info({'serverseq': memo_dict['serverseq']})
        #
        # log.debug('[Common] setMemo : result = %d, memo_r = %s' %(result, str(memo_r)))
        #
        # if result < 0:
        #     log.debug("Failed to get memo : serverseq = %s" % memo_dict['serverseq'])
        #     log.error("Failed to get memo : serverseq = %s" % memo_dict['serverseq'])
        #     return result, memo_r
        # elif result == 0:
        #     log.debug('note = %s' %str(memo_dict.get('note')))
        #
        #     in_memo_dict = {"serverseq": memo_dict['serverseq']}
        #     in_memo_dict["contents"] = str(memo_dict.get('note'))
        #
        #     log.debug('in_memo_dict = %s' %str(in_memo_dict))
        #
        #     result, memoseq = orch_dbm.insert_memo(in_memo_dict)
        #
        #     log.debug('isnert memo : result = %d, memoseq = %s' %(result, str(memoseq)))
        #     if result < 0:
        #         log.debug("Failed to insert memo : serverseq = %s" % in_memo_dict['serverseq'])
        #         log.error("Failed to insert memo : serverseq = %s" % in_memo_dict['serverseq'])
        #         return result, memoseq
        # else:
        #     if memo_r[0]['contents'] is None:
        #         contents = str(memo_dict.get('note'))
        #     else:
        #         contents = str(memo_r[0]['contents'])
        #         contents += "\n" + str(memo_dict.get('note'))
        #
        #     log.debug('contents = %s' % str(contents))
        #
        #     memo_r[0]["contents"] = contents
        #     result, update_msg = orch_dbm.update_memo(memo_r[0])
        #     if result < 0:
        #         log.debug("Failed to update memo : memoseq = %s" % memo_r[0]['memoseq'])
        #         log.error("Failed to update memo : memoseq = %s" % memo_r[0]['memoseq'])
        #         return result, update_msg

        return 200, "OK"

    # 노트 처리
    def setNote(self, note_dict):
        log.debug('note_dict = %s' % str(note_dict))

        server_dict = {'serverseq' : note_dict['serverseq'], 'description': str(note_dict['note'])}
        desc_result, desc_data = orch_dbm.update_server(server_dict)
        if desc_result <= 0:
            log.debug("Failed to update description : servresume_onebox_monitorerseq = %s" % note_dict['serverseq'])
            log.error("Failed to update description : serverseq = %s" % note_dict['serverseq'])
            return desc_result, desc_data

        return 200, "OK"


    # File save : remote ip
    # def file_save_ip(self, save_dict):
    #     log.debug('[Common] file_save_ip : save_dict = %s' % str(save_dict))


    # One-Box or WEB-UI IP Check
    def CheckIP(self, req_dict):
        # log.debug('req_dict = %s' % str(req_dict))
        # log.debug('X-Forwarded-For = %s' % str(request.headers.get('X-Forwarded-For')))

        request = req_dict.get('req')

        ob_result, ob_data = orch_dbm.get_server_id(req_dict.get('server_id'))
        if ob_result < 0:
            log.error("failed to get server info from DB: %d %s" % (ob_result, ob_data))
            return ob_result, ob_data

        if ob_data.get('mgmtip') != str(request.headers.get('X-Forwarded-For')):
            log.error("[Common] Check IP failed =====> X-Forwarded-For: %s, One-Box: %s" % (str(request.headers.get('X-Forwarded-For')), str(ob_data.get('mgmtip'))))
            ret_msg = "failed to check One-Box(Web-UI) IP : %s" %str(request.headers.get('X-Forwarded-For'))
            return -HTTP_Not_Found, ret_msg

        return 200, "OK"

    # Router check
    def _private_ip_check(self, check_dict):
        check_public_ip = check_dict.get('mgmtip').split('.')
        check_ip = str(check_public_ip[0])

        # log.debug('public_ip = %s, check_ip = %s' %(str(public_ip), str(check_ip)))
        # log.debug(type(check_ip))

        ip_arr = ['192', '172', '10']

        for ipa in ip_arr:
            if check_ip != ipa:
                continue

            log.debug('check_ip : %s' % str(ipa))
            return -1, 'OK'

        return 200, 'OK'

    def clean_parameters(self, com_dict):
        """
        tb_nscatalog_param에서 조회한 Parameter정보 중 사용하지 않는 WAN의 Param 제거
        :param parameters: tb_nscatalog_param에서 조회한 Parameter 목록
        :param wan_dels: 사용하지 않는 WAN 리스트
        :return: 정리된 Parameter 목록
        """
        # RPARM_redFixedIpR1_KT-VNF
        # RPARM_redFixedMacR1_KT-VNF
        # RPARM_redSubnetR1_KT-VNF
        # CPARM_redCIDRR1_KT-VNF
        # CPARM_redTypeR1_KT-VNF
        # CPARM_defaultGwR1_KT-VNF
        # IPARM_redNetmaskR1_KT-VNF
        # IPARM_redBroadcastR1_KT-VNF

        PARAM_TEMPLATE = ["RPARM_redFixedIp", "RPARM_redFixedMac", "RPARM_redSubnet"
            , "CPARM_redCIDR", "CPARM_redType", "CPARM_defaultGw"
            , "IPARM_redNetmask", "IPARM_redBroadcast"]

        size = len(com_dict['parameters'])
        for idx in range(size - 1, -1, -1):
            param_name = com_dict['parameters'][idx]["name"]
            is_deleted = False
            for wr in com_dict['wan_dels']:
                for tmp in PARAM_TEMPLATE:
                    if param_name.find(tmp + wr) >= 0:
                        log.debug("_____ Clean Parameter : %s" % param_name)
                        del com_dict['parameters'][idx]
                        is_deleted = True
                        break
                if is_deleted:
                    break

        return com_dict['parameters']


    ### Monitor 관련  ######################################################################

    # def get_ktmonitor(self):
    #     cfgManager = ConfigManager.get_instance()
    #     config = cfgManager.get_config()
    #     host_ip = config["monitor_ip"]
    #     host_port = config["monitor_port"]
    #
    #     log.debug("get_ktmonitor(): Monitor IP: %s, Monitor Port: %s" % (host_ip, host_port))
    #     return monitorconnector.monitorconnector({"onebox_type": "General", "host": host_ip, "port": host_port})

    def first_notify_monitor(self, ob_data):
        # monitor = self.get_ktmonitor()
        monitor = ob_data.get('wf_monitorconnector')

        if monitor is None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        log.debug('[Monitor] first_notify_monitor : ob_data = %s' %str(ob_data))

        target_dict = {}
        target_dict['onebox_type'] = ob_data['onebox_type']
        target_dict['server_id'] = ob_data['serverseq']
        target_dict['onebox_id'] = ob_data['onebox_id']
        target_dict['server_ip'] = ob_data['mgmt_ip']

        result, data = monitor.first_notify_monitor(target_dict)

        if result < 0:
            log.error("Error %d %s" % (result, data))

        return result, data

    def start_onebox_monitor(self, data_dict):
        serverseq = data_dict['serverseq']

        # monitor = self.get_ktmonitor()
        monitor = data_dict.get('wf_monitorconnector')

        if monitor is None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        ob_result, ob_data = orch_dbm.get_server_id(serverseq)
        if ob_result < 0:
            log.error("Failed to get Server Info from DB: %d %s" % (ob_result, ob_data))
            return ob_result, ob_data

        target_dict = {}
        target_dict['server_id'] = ob_data['serverseq']
        target_dict['server_uuid'] = ob_data['serveruuid']
        target_dict['onebox_id'] = ob_data['onebox_id']
        target_dict['server_name'] = ob_data['servername']
        target_dict['server_ip'] = ob_data['mgmtip']
        target_dict['ob_service_number'] = ob_data['ob_service_number']
        target_dict['onebox_type'] = ob_data['nfsubcategory']

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
            log.warning("failed to get HW info: %d %s" % (hw_result, hw_content))
        else:
            target_dict['hw_model'] = hw_content[0]['model']

        os_result, os_content = orch_dbm.get_onebox_sw_serverseq(ob_data['serverseq'])
        if os_result <= 0:
            log.warning("failed to get OS info: %d %s" % (os_result, os_content))
        else:
            target_dict['os_name'] = os_content[0]['operating_system']

        sn_result, sn_content = orch_dbm.get_onebox_nw_serverseq(ob_data['serverseq'])
        if sn_result <= 0:
            log.warning("failed to get Server Net info: %d %s" % (sn_result, sn_content))
        else:
            target_dict['svr_net'] = []
            for sn in sn_content:
                target_dict['svr_net'].append({'name': sn['name'], 'display_name': sn['display_name']})

        log.debug('[PNF] Start_monitor_onebox : target_dict = %s' % str(target_dict))

        result, data = monitor.start_monitor_onebox(target_dict)

        if result < 0:
            log.error("Error %d %s" % (result, data))

        return result, data


    def update_onebox_monitor(self, data_dict):
        # monitor = self.get_ktmonitor()
        monitor = data_dict.get('wf_monitorconnector')

        if monitor is None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        result, data = monitor.update_monitor_onebox(data_dict['update_body_dict'])

        if result < 0:
            log.error("Error %d %s" % (result, data))

        return result, data


    def stop_onebox_monitor(self, ob_data):
        # monitor = self.get_ktmonitor()
        monitor = ob_data.get('wf_monitorconnector')

        if monitor is None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        target_dict = {}
        target_dict['server_id'] = ob_data['serverseq']
        target_dict['onebox_id'] = ob_data['onebox_id']
        target_dict['server_ip'] = ob_data['mgmtip']
        # target_dict['server_uuid'] = ob_data['serveruuid']
        # target_dict['server_name'] = ob_data['servername']

        result, data = monitor.stop_monitor_onebox(target_dict)

        if result < 0:
            log.error("Error %d %s" % (result, data))

        return result, data

    def suspend_onebox_monitor(self, data_dict):
        # monitor = self.get_ktmonitor()
        monitor = data_dict.get('wf_monitorconnector')

        if monitor == None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        target_dict = {}
        target_dict['server_id'] = data_dict['ob_data']['serverseq']
        target_dict['onebox_id'] = data_dict['ob_data']['onebox_id']
        target_dict['server_ip'] = data_dict['ob_data']['mgmtip']
        #target_dict['server_uuid'] = ob_data['serveruuid']
        #target_dict['vms'] = []

        target_dict['e2e_log'] = data_dict['e2e_log']

        result, data = monitor.suspend_monitor_onebox(target_dict)

        if result < 0:
            log.error("Error %d %s" %(result, data))

        return result, data

    def resume_onebox_monitor(self, resume_dict):
        # monitor = self.get_ktmonitor()
        monitor = resume_dict.get('wf_monitorconnector')

        if monitor is None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        e2e_log = resume_dict['e2e_log']
        serverseq = resume_dict['ob_data']['serverseq']
        # log.debug('[Common] resume_onebox_monitor : serverseq = %s' %str(type(serverseq)))

        ob_result, ob_data = orch_dbm.get_server_id(serverseq)
        if ob_result < 0:
            log.error("Failed to get Server Info from DB: %d %s" % (ob_result, ob_data))
            return ob_result, ob_data

        target_dict = {}
        target_dict['step'] = "resume"  # start 시에는 step 이 없음, resume monitor 시 다른 동작으로 추가됨
        target_dict['onebox_type'] = ob_data['nfsubcategory']
        target_dict['server_id'] = ob_data['serverseq']
        target_dict['server_uuid'] = ob_data['serveruuid']
        target_dict['onebox_id'] = ob_data['onebox_id']
        target_dict['server_name'] = ob_data['servername']
        target_dict['server_ip'] = ob_data['mgmtip']
        target_dict['ob_service_number'] = ob_data['ob_service_number']

        # vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(vim_id=None, vim_name=None, server_id=ob_data['serverseq'])
        # if vim_result <= 0:
        #     log.error("failed to get vim info of %s: %d %s" % (str(ob_data['serverseq']), vim_result, vim_content))
        #     return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
        # target_dict['vim_auth_url'] = vim_content[0]['authurl']
        # target_dict['vim_id'] = vim_content[0]['username']
        # target_dict['vim_passwd'] = vim_content[0]['password']
        # target_dict['vim_domain'] = vim_content[0]['domain']
        # target_dict['vim_typecod'] = vim_content[0]['vimtypecode']
        # target_dict['vim_version'] = vim_content[0]['version']
        #
        # target_dict['vim_net'] = []
        # vn_result, vn_content = orch_dbm.get_vim_networks(mydb, vim_content[0]['vimseq'])
        # if vn_result <= 0:
        #     log.warning("failed to get vim_net info: %d %s" % (vn_result, vn_content))
        # else:
        #     for vn in vn_content:
        #         target_dict['vim_net'].append(vn['name'])

        hw_result, hw_content = orch_dbm.get_onebox_hw_serverseq(ob_data['serverseq'])
        if hw_result <= 0:
            log.warning("failed to get HW info: %d %s" % (hw_result, hw_content))
        else:
            target_dict['hw_model'] = hw_content[0]['model']

        os_result, os_content = orch_dbm.get_onebox_sw_serverseq(ob_data['serverseq'])
        if os_result <= 0:
            log.warning("failed to get OS info: %d %s" % (os_result, os_content))
        else:
            target_dict['os_name'] = os_content[0]['operating_system']

        sn_result, sn_content = orch_dbm.get_onebox_nw_serverseq(ob_data['serverseq'])
        if sn_result <= 0:
            log.warning("failed to get Server Net info: %d %s" % (sn_result, sn_content))
        else:
            target_dict['svr_net'] = []
            for sn in sn_content:
                target_dict['svr_net'].append({'name': sn['name'], 'display_name': sn['display_name']})

        result, data = monitor.resume_monitor_onebox(target_dict, e2e_log)

        if result < 0:
            log.error("Error %d %s" % (result, data))

        return result, data


    def start_nsr_monitoring(self, nsr_dict=None):
        # monitor = self.get_ktmonitor()
        monitor = nsr_dict.get('wf_monitorconnector')

        if monitor == None:
            log.warning("failed to setup monitor")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Monitor"

        ob_result, ob_data = orch_dbm.get_server_id(nsr_dict.get('serverseq'))
        if ob_result < 0:
            log.error("Failed to get Server Info from DB: %d %s" % (ob_result, ob_data))
            return ob_result, ob_data

        nsr_dict['onebox_id'] = ob_data['onebox_id']
        nsr_dict['server_uuid'] = ob_data['serveruuid']
        nsr_dict['server_id'] = ob_data['serverseq']
        # nsr_dict['onebox_type'] = nsr_dict['onebox_type']

        # https://220.86.29.42:5556/v1
        obagent_base_url = ob_data['obagent_base_url'].split('/')
        obagent_ip = obagent_base_url[2].split(':')
        nsr_dict['server_ip'] = obagent_ip[0]

        # target model 추가
        if nsr_dict.get('onebox_type') == 'KtPnf':
            targetcode = 'pnf'
        else:
            targetcode = nsr_dict.get('onebox_type')

        montarget_dict = {'targetcode':targetcode, 'vendorcode':'axgate'}
        tg_result, tg_content = orch_dbm.get_pnf_montargetcat(montarget_dict)

        # log.debug('[Common] get_pnf_montargetcat : tg_result = %d, tg_content = %s' %(tg_result, str(tg_content)))
        if tg_result <= 0:
            log.warning("failed to get PNF target model info: %d %s" % (tg_result, tg_content))
        else:
            nsr_dict['targetmodel'] = tg_content[0]['targetmodel']

        # network 추가
        nw_result, nw_content = orch_dbm.get_onebox_nw_serverseq(nsr_dict.get('serverseq'))

        # log.debug('[Common] get_onebox_nw_serverseq : nw_result = %d, nw_content = %s' %(nw_result, str(nw_content)))
        if nw_result <= 0:
            log.warning("failed to get One-Box network lists info: %d %s" % (nw_result, nw_content))
        else:
            nw_list = []
            wan_list = []
            for nw in nw_content:
                nw_list.append(nw.get('name'))

                # dispaly_name 이 wan 이 아니면 continue
                if nw.get('display_name') != "wan":
                    continue

                wan_list.append(nw.get('name'))

            nsr_dict['vm_net'] = nw_list
            nsr_dict['wan_list'] = wan_list

        result, data = monitor.start_monitor_nsr(nsr_dict)

        if result < 0:
            log.error("Error %d %s" %(result, data))

        return result, data


    # def stop_nsr_monitor(self, nsr_id, e2e_log=None, del_vnfs=None):
    def stop_nsr_monitor(self, nsr_dict=None):
        log.debug('[Common] stop_nsr_monitor : nsr_dict = %s' %str(nsr_dict))

        result, customer_resources = orch_dbm.get_customer_resources(nsr_dict['customerseq'])
        log.debug('[Common] stop_nsr_monitor : get_customer_resources > customer_resources = %s' %str(customer_resources))
        if result <= 0:
            return result, customer_resources

        # monitor = self.get_ktmonitor()
        monitor = nsr_dict.get('wf_monitorconnector')
        if monitor is None:
            log.warning("failed to setup montior")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

        server_id = None
        server_uuid = None
        server_ip = None
        server_onebox_id = None

        for resource in customer_resources:
            if resource.get('nfsubcategory') == "KtPnf":
                # PNF type
                # PNF type 은 nsseq 값이 없으므로
                if resource['resource_type'] == 'server' and resource['serverseq'] == nsr_dict['serverseq']:
                    server_id = resource['serverseq']
                    server_uuid = resource['serveruuid']
                    server_onebox_id = resource['onebox_id']
                    server_ip = resource['mgmtip']
                    # log.debug("stop_nsr_monitor() serverseq: %d" %server_id)
                    break
            else:
                if resource['resource_type'] == 'server' and str(resource['nsseq']) == str(nsr_dict.get('nsr_id')):
                    server_id = resource['serverseq']
                    server_uuid = resource['serveruuid']
                    server_onebox_id = resource['onebox_id']
                    server_ip = resource['mgmtip']
                    # log.debug("stop_nsr_monitor() serverseq: %d" %server_id)
                    break

        if server_id is None:
            return -HTTP_Not_Found, "Cannot find Server Info"

        target_dict = {}
        # target_dict['name'] = nsr_content['name']
        target_dict['onebox_type'] = nsr_dict.get('onebox_type')
        target_dict['server_id'] = server_id
        target_dict['server_uuid'] = server_uuid
        target_dict['onebox_id'] = server_onebox_id
        target_dict['server_ip'] = server_ip

        log.debug("target_dict = %s" % str(target_dict))

        # target model 추가
        if nsr_dict.get('onebox_type') == 'KtPnf':
            targetcode = 'pnf'
        else:
            targetcode = nsr_dict.get('onebox_type')

        montarget_dict = {'targetcode':targetcode, 'vendorcode':'axgate', 'serverseq':nsr_dict.get('serverseq')}
        tg_result, tg_content = orch_dbm.get_pnf_montargetcat_2(montarget_dict)
        # tg_result, tg_content = orch_dbm.get_pnf_montargetcat(montarget_dict)

        if tg_result <= 0:
            log.warning("failed to get PNF target model info: %d %s" % (tg_result, tg_content))
        else:
            target_dict['target_seq'] = tg_content[0]['montargetcatseq']

        target_vm_list = []
        # for vnf in nsr_content['vnfs']:
        #
        #     # Update NS 에서 del_vnfs 가 있는 경우 처리...
        #     if del_vnfs is not None and len(del_vnfs) > 0:
        #         is_pass = False
        #         for del_vnf in del_vnfs:
        #             if vnf["vnfd_name"] == del_vnf["vnfd_name"] and vnf["version"] == del_vnf["vnfd_version"]:
        #                 is_pass = True
        #                 log.debug("[NS Update] Append VNF[%s %s] to target_vm_list for stopping monitor" % (del_vnf["vnfd_name"], del_vnf["vnfd_version"]))
        #                 break
        #         if is_pass:
        #             pass
        #         else:
        #             continue
        #
        #     for vm in vnf['vdus']:
        #         target_vm = {'vm_name': vm['name'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid'],
        #                      'monitor_target_seq': vm['monitor_target_seq']}
        #         target_vm_list.append(target_vm)

        target_dict['vms'] = target_vm_list

        result, data = monitor.stop_monitor_nsr(target_dict)

        if result < 0:
            log.error("stop_nsr_monitor(): error %d %s" % (result, data))

        return result, data

    def resume_nsr_monitor(self, nsr_dict):
        log.debug('[Common] resume_nsr_monitor : nsr_dict = %s' %str(nsr_dict))

        ob_data = nsr_dict.get('ob_data')
        e2e_log = nsr_dict.get('e2e_log')

        server_id = ob_data.get('serverseq')

        # monitor = self.get_ktmonitor()
        monitor = nsr_dict.get('wf_monitorconnector')
        if monitor is None:
            log.warning("failed to setup montior")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

        target_dict = {}
        # target_dict['nsr_name'] = nsr_dict['name']

        server_result, server_data = orch_dbm.get_server_id(server_id)
        if server_result <= 0:
            log.warning("failed to get server info of %d: %d %s" % (server_id, server_result, server_data))
            return -HTTP_Internal_Server_Error, "Cannot get Server Info from DB"
        target_dict['onebox_type'] = server_data['nfsubcategory']
        target_dict['server_id'] = server_data['serverseq']
        target_dict['server_uuid'] = server_data['serveruuid']
        target_dict['onebox_id'] = server_data['onebox_id']
        target_dict['server_ip'] = server_data['mgmtip']

        if server_data['nfsubcategory'] == "KtPnf":
            # # https://220.86.29.42:5556/v1
            # obagent_base_url = ob_data['obagent_base_url'].split('/')
            # obagent_ip = obagent_base_url[2].split(':')
            # nsr_dict['server_ip'] = obagent_ip[0]

            # target model 추가
            if target_dict.get('onebox_type') == 'KtPnf':
                targetcode = 'pnf'
            else:
                targetcode = nsr_dict.get('onebox_type')

            montarget_dict = {'targetcode': targetcode, 'vendorcode': 'axgate'}
            tg_result, tg_content = orch_dbm.get_pnf_montargetcat(montarget_dict)

            # log.debug('[Common] get_pnf_montargetcat : tg_result = %d, tg_content = %s' %(tg_result, str(tg_content)))
            if tg_result <= 0:
                log.warning("failed to get PNF target model info: %d %s" % (tg_result, tg_content))
            else:
                target_dict['targetmodel'] = tg_content[0]['targetmodel']
                target_dict['targetseq'] = tg_content[0]['montargetcatseq']

            # network 추가
            nw_result, nw_content = orch_dbm.get_onebox_nw_serverseq(server_id)

            # log.debug('[Common] get_onebox_nw_serverseq : nw_result = %d, nw_content = %s' %(nw_result, str(nw_content)))
            if nw_result <= 0:
                log.warning("failed to get One-Box network lists info: %d %s" % (nw_result, nw_content))
            else:
                nw_list = []
                wan_list = []
                for nw in nw_content:
                    nw_list.append(nw.get('name'))

                    # dispaly_name 이 wan 이 아니면 continue
                    if nw.get('display_name') != "wan":
                        continue

                    wan_list.append(nw.get('name'))

                target_dict['vm_net'] = nw_list
                target_dict['wan_list'] = wan_list

        # vim_result, vim_content = orch_dbm.get_vim_and_vim_tenant(mydb, vim_id=None, vim_name=None, server_id=server_data['serverseq'])
        # if vim_result <= 0:
        #     log.error("failed to get vim info of %d: %d %s" % (server_data['serverseq'], vim_result, vim_content))
        #     return -HTTP_Internal_Server_Error, "Cannot get VIM Info from DB"
        # target_dict['vim_auth_url'] = vim_content[0]['authurl']
        # target_dict['vim_id'] = vim_content[0]['username']
        # target_dict['vim_passwd'] = vim_content[0]['password']
        # target_dict['vim_domain'] = vim_content[0]['domain']
        #
        # target_vms = []
        # for vnf in nsr_dict['vnfs']:
        #     vnf_app_id = None
        #     vnf_app_passwd = None
        #     for param in nsr_dict['parameters']:
        #         if param['name'].find("appid_" + vnf['name']) >= 0:
        #             vnf_app_id = param['value']
        #         if param['name'].find("apppasswd_" + vnf['name']) >= 0:
        #             vnf_app_passwd = param['value']
        #
        #     for vm in vnf['vdus']:
        #         target_vm = {'vm_name': vm['name'], 'vdud_id': vm['vdudseq'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid'],
        #                      'monitor_target_seq': vm['monitor_target_seq'],
        #                      'vm_id': vm['vm_access_id'], 'vm_passwd': vm['vm_access_passwd']}
        #         if vnf_app_id: target_vm['vm_app_id'] = vnf_app_id
        #         if vnf_app_passwd: target_vm['vm_app_passwd'] = vnf_app_passwd
        #
        #         target_cps = []
        #         if 'cps' in vm:
        #             for cp in vm['cps']:
        #                 target_cp = {'cp_name': cp['name'], 'cp_vim_name': cp['vim_name'], 'cp_vim_uuid': cp['uuid'], 'cp_ip': cp['ip']}
        #                 target_cps.append(target_cp)
        #         target_vm['vm_cps'] = target_cps
        #
        #         target_vm['nfsubcategory'] = vnf['nfsubcategory']
        #
        #         target_vms.append(target_vm)
        # target_dict['vms'] = target_vms

        result, data = monitor.resume_monitor_nsr(target_dict, e2e_log)

        if result < 0:
            log.error("resume_nsr_monitor(): error %d %s" % (result, data))

        return result, data

    def suspend_nsr_monitor(self, nsr_content, customer_data, e2e_log=None):
        # monitor = self.get_ktmonitor()
        monitor = nsr_content.get('wf_monitorconnector')
        if monitor is None:
            log.warning("failed to setup montior")
            return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

        if customer_data.get('server_id') is None:
            return -HTTP_Not_Found, "Cannot find Server Info"

        target_dict = {}
        target_dict['name'] = nsr_content['name']
        target_dict['server_id'] = customer_data.get('server_id')
        target_dict['server_uuid'] = customer_data.get('server_uuid')
        target_dict['onebox_id'] = customer_data.get('server_onebox_id')
        target_dict['server_ip'] = customer_data.get('server_mgmt_ip')

        target_vm_list = []
        # for vnf in nsr_content['vnfs']:
        #     for vm in vnf['vdus']:
        #         target_vm = {'vm_name': vm['name'], 'vm_vim_name': vm['vim_name'], 'vm_vim_uuid': vm['uuid'],
        #                      'monitor_target_seq': vm['monitor_target_seq']}
        #         target_vm_list.append(target_vm)
        # target_dict['vms'] = target_vm_list

        result, data = monitor.suspend_monitor_nsr(target_dict, e2e_log)

        if result < 0:
            log.error("suspend_monitor_nsr(): error %d %s" % (result, data))

        return result, data

    ### Monitor 관련  ######################################################################
