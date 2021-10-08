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
import orch_core as nfvo
import orch_schemas
from handlers_t.http_response import HTTPResponse
from utils import auxiliary_functions as af
from engine.server_manager import get_server_with_filter
from engine.server_manager import vnf_image_sync

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils import db_conn_manager as dbmanager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t="/orch"

OPCODE_NSD_ACTION_POST = "NSD_ACTION_POST"

OPCODE_NSR_ACTIVE_GET = "NSR_ACTIVE_GET"
OPCODE_NSR_ALL_GET = "NSR_ALL_GET"
OPCODE_NSR_ID_GET = "NSR_ID_GET"
OPCODE_NSR_ACTION_POST = "NSR_ACTION_POST"
OPCODE_NSR_UPDATE_POST = "NSR_UPDATE_POST"
OPCODE_NSR_PARAMS_GET = "NSR_PARAMS_GET"
OPCODE_NSR_ONLY_ORCH_DELETE = "NSR_ONLY_ORCH_DELETE"

# OPCODE_NSR_MONITOR_START_POST = "NSR_MONITOR_START_POST"
# OPCODE_NSR_MONITOR_STOP_POST = "NSR_MONITOR_STOP_POST"

OPCODE_CONSOLE_URL_VDU_GET = "CONSOLE_URL_VDU_GET"
OPCODE_CONSOLE_URL_VNF_GET = "CONSOLE_URL_VNF_GET"
OPCODE_CONSOLE_URL_NSR_GET = "CONSOLE_URL_NSR_GET"

OPCODE_VNF_ACTION_POST = "VNF_ACTION_POST"
OPCODE_VDU_ACTION_POST = "VDU_ACTION_POST"
OPCODE_WAN_SWITCH_POST = "WAN_SWITCH_POST"

OPCODE_VNF_IMAGE_ACTION_POST = "VNF_IMAGE_ACTION_POST"

def url(plugins):
    urls = [ (url_base_t + "/nsd/([^/]*)/action", NfvNsrHandler, dict(opCode=OPCODE_NSD_ACTION_POST, plugins=plugins)),     # 프로비저닝

             (url_base_t + "/nsr", NfvNsrHandler, dict(opCode=OPCODE_NSR_ACTIVE_GET)),
             (url_base_t + "/nsr/all", NfvNsrHandler, dict(opCode=OPCODE_NSR_ALL_GET)),
             (url_base_t + "/nsr/([^/]*)", NfvNsrHandler, dict(opCode=OPCODE_NSR_ID_GET, plugins=plugins)), # delete 포함
             (url_base_t + "/nsr/([^/]*)/only_orch", NfvNsrHandler, dict(opCode=OPCODE_NSR_ONLY_ORCH_DELETE, plugins=plugins)), # delete 제어시스템쪽만 삭제...
             (url_base_t + "/nsr/([^/]*)/action", NfvNsrHandler, dict(opCode=OPCODE_NSR_ACTION_POST)),
             (url_base_t + "/nsr/([^/]*)/vnf_update", NfvNsrHandler, dict(opCode=OPCODE_NSR_UPDATE_POST)),
             (url_base_t + "/nsr/([^/]*)/parameter", NfvNsrHandler, dict(opCode=OPCODE_NSR_PARAMS_GET)),
             # (url_base_t + "/nsr/([^/]*)/monitor/start", NfvNsrHandler, dict(opCode=OPCODE_NSR_MONITOR_START_POST)),
             # (url_base_t + "/nsr/([^/]*)/monitor/stop", NfvNsrHandler, dict(opCode=OPCODE_NSR_MONITOR_STOP_POST)),
             (url_base_t + "/nsr/vnf/vdu/([^/]*)/vnc", NfvNsrHandler, dict(opCode=OPCODE_CONSOLE_URL_VDU_GET)),
             (url_base_t + "/nsr/vnf/([^/]*)/vdu/vnc", NfvNsrHandler, dict(opCode=OPCODE_CONSOLE_URL_VNF_GET)),
             (url_base_t + "/nsr/([^/]*)/vdu/vnc", NfvNsrHandler, dict(opCode=OPCODE_CONSOLE_URL_NSR_GET)),

             (url_base_t + "/nsr/vnf/([^/]*)/action", NfvNsrHandler, dict(opCode=OPCODE_VNF_ACTION_POST)),
             (url_base_t + "/nsr/vnf/vdu/([^/]*)/action", NfvNsrHandler, dict(opCode=OPCODE_VDU_ACTION_POST)),
             (url_base_t + "/switch/([^/]*)", NfvNsrHandler, dict(opCode=OPCODE_WAN_SWITCH_POST)),


             (url_base_t + "/nsr/vnf/([^/]*)/image/action", NfvNsrHandler, dict(opCode=OPCODE_VNF_IMAGE_ACTION_POST))
             ]
    return urls


class NfvNsrHandler(RequestHandler):

    def __init__(self, application, request, **kwargs):
        self.opCode = None
        self.plugins = None
        super(NfvNsrHandler, self).__init__(application, request, **kwargs)

    def initialize(self, opCode, plugins=None):
        self.opCode = opCode
        self.plugins = plugins


    def post(self, id=None):

        log.debug("IN post() with opCode = %s" % str(self.opCode))

        if str(self.opCode).endswith("POST"):

            if self.opCode == OPCODE_NSD_ACTION_POST: # (url_base + '/nsd/<nsd>/action', method='POST')
                self._http_post_nsd_action(id)
            elif self.opCode == OPCODE_NSR_ACTION_POST: # (url_base + '/nsr/<nsr>/action', method='POST')
                self._http_post_nsr_action(id)
            # elif self.opCode == OPCODE_NSR_MONITOR_START_POST: # (url_base + '/nsr/<nsr>/monitor/start', method='POST')
            #     self._http_post_nsr_monitor_start(id)
            # elif self.opCode == OPCODE_NSR_MONITOR_STOP_POST: # (url_base + '/nsr/<nsr>/monitor/stop', method='POST')
            #     self._http_post_nsr_monitor_stop(id)
            elif self.opCode == OPCODE_VNF_ACTION_POST: # (url_base + '/nsr/vnf/<vnf_id>/action', method='POST')
                self._http_post_vnf_action(id)
            elif self.opCode == OPCODE_VDU_ACTION_POST: # (url_base + '/nsr/vnf/vdu/<vdu_id>/action', method='POST')
                self._http_post_vdu_action(id)
            elif self.opCode == OPCODE_NSR_UPDATE_POST: # (url_base + '/nsr/<nsr>/vnf_update', method='POST')
                self._http_post_nsr_update(id)
            elif self.opCode == OPCODE_WAN_SWITCH_POST:
                self._http_post_wan_switch(id)
            elif str(self.opCode) == OPCODE_VNF_IMAGE_ACTION_POST:
                self._http_post_vnf_image_action(id)


    def get(self, id=None):

        log.debug("IN get() with opCode = %s" % str(self.opCode))

        if str(self.opCode).endswith("GET"):
            if self.opCode == OPCODE_NSR_ACTIVE_GET: # (url_base + '/nsr', method='GET')
                self._http_get_active_nsr()
            elif self.opCode == OPCODE_NSR_ALL_GET: # (url_base + '/nsr/all', method='GET')
                self._http_get_nsr_all()
            elif self.opCode == OPCODE_NSR_ID_GET: # (url_base + '/nsr/<nsr>', method='GET')
                self._http_get_nsr_id(id)
            elif self.opCode == OPCODE_CONSOLE_URL_VDU_GET: # (url_base + '/nsr/vnf/vdu/<vdu_id>/vnc', method='GET')
                #if id == "vdu":
                #    return
                self._http_get_vnc_console_url(id)
            elif self.opCode == OPCODE_CONSOLE_URL_VNF_GET: # (url_base + '/nsr/vnf/<vnf_id>/vdu/vnc', method='GET')
                self._http_get_vnf_console_url(id)
            elif self.opCode == OPCODE_CONSOLE_URL_NSR_GET: # (url_base + '/nsr/<nsr>/vdu/vnc', method='GET')
                self._http_get_nsr_vnc_console_url(id)
            elif self.opCode == OPCODE_NSR_PARAMS_GET:
                self._http_get_nsr_parameter(id)


    def delete(self, nsr=None):
        """delete NSR instance from VIM and from database, can use both seq or name"""

        log.debug("[NBI IN] Deleting NSR: /nsr/%s" %str(nsr))
        log.debug("[NBI IN] Request Body = %s" %str(self.request.body))
        log.debug("[NBI IN] opCode = %s" %str(self.opCode))

        tid = self.get_argument("tid")
        tpath = self.get_argument("tpath")
        #tid = "TEST-TID-DELETE"
        #tpath = "/"
        only_orch = False
        if self.opCode == OPCODE_NSR_ONLY_ORCH_DELETE:
            only_orch = True

        filter_dict = {'nsseq': nsr}
        server_result, server_data = orch_dbm.get_server_filters_wf(mydb, filter_dict)

        log.debug('server_data = %s' %str(server_data))

        if server_data[0].get('nfsubcategory') == 'KtArm':
            # Arm-Box
            del_dict = {}
            del_dict['onebox_type'] = server_data[0].get('nfsubcategory')
            del_dict['nsr'] = nsr
            del_dict['only_orch'] = only_orch
            del_dict['tid'] = tid
            del_dict['tpath'] = tpath
            result, message = self.plugins.get('wf_nsr_arm_manager').delete_nsr(del_dict, self.plugins)
        else:
            result, message = nfvo.delete_nsr(mydb, nsr, only_orch=only_orch, tid=tid, tpath=tpath)  # hjc
        # result, message = nfvo.delete_nsr(mydb, nsr) #hjc

        if result < 0:
            log.error("[NBI OUT] Deleting NSR: Error %d %s" %(-result, message))
            self._send_response(result, message)
        else:
            log.debug("[NBI OUT] Deleting NSR: OK")
            self._send_response(result, {"result":message})


    ### POST method 처리 ###############################################################################################################################
    def _http_post_nsd_action(self, nsd=None):

        result, http_content = util.format_in(self.request, orch_schemas.nsd_action_schema)

        log.debug("[NBI IN] Provisioning NS: /nsd/%s/action" %str(nsd))
        log.debug("[NBI IN] Request Body = %s" %str(http_content))
        r = af.remove_extra_items(http_content, orch_schemas.nsd_action_schema)
        if r is not None:
            log.error("http_post_scenario_action_v4: Warning: remove extra items: %s", str(r))

        if "start" in http_content:
            result, data = nfvo.new_nsr(mydb, nsd, http_content['start'].get('instance_name','NotGiven'),
                                        http_content['start'].get('description','none'),
                                        customer_id=http_content['start'].get('customer_id',None),
                                        customer_name=http_content['start'].get('customer_name',None),
                                        vim=http_content['start'].get('vim'),
                                        params=http_content['start'].get('parameters'),
                                        tid=http_content["tid"], tpath=http_content["tpath"] ) # hjc
            if result < 0:
                log.error("[NBI OUT] Provisioning NS: Error %d %s" %(-result, data))
            else:
                log.debug("[NBI OUT] Provisioning NS: OK")

            self._send_response(result, data)
            return
        elif "start_v2" in http_content:
            bonding = None
            if 'bonding' in http_content['start_v2']:
                log.debug('##########   bonding 구성 처리   ################')
                bonding = http_content['start_v2']['bonding']

            is_arm_process = False
            ob_result, ob_data = orch_dbm.get_server_id(mydb, http_content['start_v2'].get('onebox_id'))

            if ob_result > 0:
                if ob_data.get('nfsubcategory') == 'KtArm':
                    is_arm_process = True
                    http_content['nsd'] = nsd
                    http_content['serverseq'] = ob_data.get('serverseq')
                    http_content['onebox_type'] = ob_data.get('nfsubcategory')

            if is_arm_process:
                # Arm-Box
                result, data = self.plugins.get('wf_nsr_arm_manager').new_nsr_arm(http_content, self.plugins)
            else:
                # 기존 소스
                result, data = nfvo.new_nsr(mydb, nsd, http_content['start_v2'].get('instance_name','NotGiven'),
                                            http_content['start_v2'].get('description','none'),
                                            customer_id=http_content['start_v2'].get('customer_id',None),
                                            customer_name=http_content['start_v2'].get('customer_name',None),
                                            vim=http_content['start_v2'].get('vim'),
                                            params=http_content['start_v2'].get('parameters'),
                                            onebox_id=http_content['start_v2'].get('onebox_id'),
                                            vnf_list=http_content['start_v2'].get('vnf_list'),
                                            tid=http_content["tid"], tpath=http_content["tpath"], bonding=bonding ) # hjc

            if result < 0:
                log.error("[NBI OUT] Provisioning NS: Error %d %s" %(-result, data))
            else:
                log.debug("[NBI OUT] Provisioning NS: OK")

            self._send_response(result, data)
            return
        elif "deploy" in http_content:   #Equivalent to start
            #TODO
            pass
        elif "reserve" in http_content:   #Reserve resources
            #TODO
            pass
        elif "verify" in http_content:   #Equivalent to start and then delete
            #TODO
            pass
        elif "prev_args" in http_content:
            result, data = nfvo.get_prev_arguments_for_ns(mydb, nsd, http_content['prev_args'].get('customer_id', None))
            if result < 0:
                log.error("[NBI_OUT] Getting Previous Arguments: Error %d %s" %(-result, data))
            else:
                log.debug("[NBI_OUT] Getting Previous Arguments: OK")

            self._send_response(result, data)
            return

        self._send_response(HTTPResponse.Bad_Request, 'Invalid Action Type')

    def _http_post_nsr_action(self, nsr):
        #parse input data
        result, http_content = util.format_in(self.request, orch_schemas.nsr_action_schema)

        log.debug("[NBI IN] Action for the NSR %s" %(str(nsr)))
        log.debug("[NBI IN] Request Body = %s" %str(http_content))

        r = af.remove_extra_items(http_content, orch_schemas.nsr_action_schema)
        if r is not None:
            log.error("http_post_nsr_action: Warning: remove extra items: %s", str(r))

        if "reinit_config" in http_content:

            result, data = nfvo.retry_init_config_vnfs(mydb, nsr)

            if result < 0:
                log.error("[NBI OUT] Action for the NSR, Reinit-Config: Error %d %s" %(-result, data))
            else:
                log.debug("[NBI OUT] Action for the NSR, Reinit-Config: OK")

            self._send_response(result, data)
            return

        elif "backup" in http_content:

            #########   version 동기화     S     #####################################
            filter_dict = {'nsseq': nsr}
            result, data = orch_dbm.get_server_filters_wf(mydb, filter_dict)
            server_result, server_data = get_server_with_filter(mydb, data[0].get('serverseq'))
            result, content = vnf_image_sync(mydb, server_data[0])
            #########   version 동기화     E     #####################################

            result, data = nfvo.backup_nsr(mydb, http_content['backup'], nsr, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Action for the NSR, Backup: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the NSR, Backup: OK")
                self._send_response(result, {"backup":data})
                return
        elif "restore" in http_content:
            result, data = nfvo.restore_nsr(mydb, nsr, http_content['restore'], tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Action for the NSR, Restore: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the NSR, Restore: OK")
                self._send_response(result, {"restore":data})
                return
        else:
            self._send_response(HTTPResponse.Bad_Request, "Not supported Action")
            return

    """
    def _http_post_nsr_monitor_start(self, nsr):
        log.debug("http_post_nsr_monitor_action() IN")

        result, data = nfvo.start_monitor(mydb, nsr)

        if result < 0:
            log.error("http_post_nsr_monitor_start() error %d: %s" % (-result, data))
            self._send_response(result, data)
        else:
            log.debug("http_post_nsr_monitor_start() OUT")
            self._send_response(result, data)

    def _http_post_nsr_monitor_stop(self, nsr):
        log.debug("http_post_nsr_monitor_stop() IN")

        result, data = nfvo.stop_monitor(mydb, nsr)

        if result < 0:
            log.error("http_post_nsr_monitor_stop() error %d: %s" % (-result, data))
            self._send_response(result, data)
        else:
            log.debug("http_post_nsr_monitor_stop() OUT")
            self._send_response(result, data)
    """

    def _http_post_vnf_action(self, vnf_id):

        #parse input data
        result, http_content = util.format_in(self.request, orch_schemas.vnf_action_schema)

        log.debug("[NBI IN] Action for the VNF %s" %(str(vnf_id)))
        log.debug("[NBI IN] Request Body = %s" %str(http_content))

        r = af.remove_extra_items(http_content, orch_schemas.vnf_action_schema)
        if r is not None: log.error("http_post_vnf_action: Warning: remove extra items: %s", str(r))

        if "start" in http_content:
            result, data = nfvo.action_vnf(mydb, vnf_id, 'start', http_content['start'].get('meta_data','NotGiven'))
            if result < 0:
                log.error("[NBI OUT] Action for the VNF, START: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the VNF, START: OK")
                self._send_response(result, data)
                return
        elif "stop" in http_content:   #Equivalent to start
            result, data = nfvo.action_vnf(mydb, vnf_id, 'stop', http_content['stop'].get('meta_data','NotGiven'))
            if result < 0:
                log.error("[NBI OUT] Action for the VNF, STOP: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the VNF, STOP: OK")
                self._send_response(result, data)
                return
        elif "reboot" in http_content:   #Reserve resources
            result, data = nfvo.action_vnf(mydb, vnf_id, 'reboot', http_content['reboot'].get('meta_data','NotGiven'))
            if result < 0:
                log.error("[NBI OUT] Action for the VNF, REBOOT: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the VNF, REBOOT: OK")
                self._send_response(result, data)
                return
        elif "verify" in http_content:   #Equivalent to start and then delete
            #TODO
            pass
        elif "backup" in http_content:
            result, data = nfvo.backup_nsr_vnf(mydb, http_content['backup'], vnf_id, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Action for the NSR-VNF, Backup: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the NSR-VNF, Backup: OK")
                self._send_response(result, {"backup":data})
                return
        elif "restore" in http_content:
            result, data = nfvo.restore_nsr_vnf(mydb, http_content['restore'], vnf_id, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Action for the NSR-VNF, Restore: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the NSR-VNF, Restore: OK")
                self._send_response(result, {"restore":data})
                return
        elif "check_license" in http_content:
            result, data = nfvo.action_vnf_check_license(mydb, vnf_id, http_content['check_license'])
            if result < 0:
                log.error("[NBI OUT] Action for the NSR-VNF, check license: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the NSR-VNF, check license: OK")
                self._send_response(result, {"license":data})
                return

        self._send_response(HTTPResponse.Bad_Request, "Invalid Action Type")


    def _http_post_vdu_action(self, vdu_id):

        result, http_content = util.format_in(self.request, orch_schemas.vdu_action_schema)

        log.debug("[NBI IN] Action for the VDU %s" %(str(vdu_id)))
        log.debug("[NBI IN] Request Body = %s" %str(http_content))

        r = af.remove_extra_items(http_content, orch_schemas.vdu_action_schema)
        if r is not None: log.error("http_post_vdu_action: Warning: remove extra items: %s", str(r))

        if "start" in http_content:
            result, data = nfvo.action_vdu(mydb, vdu_id, 'start', http_content['start'].get('meta_data','NotGiven'), tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Action for the VDU, START: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the VDU, START: OK")
                self._send_response(result, data)
                return
        elif "stop" in http_content:   #Equivalent to start
            result, data = nfvo.action_vdu(mydb, vdu_id, 'stop', http_content['stop'].get('meta_data','NotGiven'), tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Action for the VDU, STOP: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the VDU, STOP: OK")
                self._send_response(result, data)
                return
        elif "reboot" in http_content:   #Reserve resources
            result, data = nfvo.action_vdu(mydb, vdu_id, 'reboot', http_content['reboot'].get('meta_data','NotGiven'), tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Action for the VDU, REBOOT: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return
            else:
                log.debug("[NBI OUT] Action for the VDU, REBOOT: OK")
                self._send_response(result, data)
                return
        elif "verify" in http_content:   #Equivalent to start and then delete
            #TODO
            pass

        self._send_response(HTTPResponse.Bad_Request, "Invalid Action Type")


    def _http_post_nsr_update(self, nsr_id):

        log.debug("[NBI IN] VNF UPDATE: /nsr/%s/vnf_update" % str(nsr_id))

        # http_content = self.request.body
        # log.debug("request body\n%s" % http_content)

        result, http_content = util.format_in(self.request, orch_schemas.nsr_update_schema)
        log.debug("http_content %d\n%s" % (result,http_content))

        result, data = nfvo.update_nsr_for_vnfs(mydb, nsr_id, http_content, tid=http_content.get('tid'), tpath=http_content.get('tpath', ""), use_thread=True)

        if result < 0:
            log.error("[NBI OUT] Update NS: Error %d %s" %(-result, data))
        else:
            log.debug("[NBI OUT] Update NS: OK")

        self._send_response(result, data)


    def _http_post_wan_switch(self, onebox_id):

        log.debug("[NBI IN] WAN Switch for the OneBox %s" %(str(onebox_id)))


        result, data = nfvo.switch_wan(mydb, onebox_id)
        if result < 0:
            log.error("[NBI OUT] WAN Switch for the VDU : Error %d %s" %(-result, data))
            self._send_response(result, data)
            return
        else:
            log.debug("[NBI OUT] WAN Switch for the VDU : OK")
            self._send_response(result, {"result":data})
            return

    def _http_post_vnf_image_action(self, id=None):

        # id : vnf_id = nfcatseq
        result, http_content = util.format_in(self.request, orch_schemas.vnf_image_action_schema)
        log.debug("_____ _http_post_vnf_image_action : http_content = %s" % http_content)
        if result < 0:
            self._send_response(result, http_content)
            return

        r = af.remove_extra_items(http_content, orch_schemas.vnf_image_action_schema)
        if r is not None: log.error("_http_post_vnf_image_action: Warning: remove extra items: %s", str(r))

        if "update" in http_content:
            result, content = nfvo.upgrade_vnf_with_image(mydb, id, http_content['update'], tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
            if result < 0:
                self._send_response(result, content)
                return
            else:
                self._send_response(result, {"result":200, "msg":content})
                return
        elif "version" in http_content:
            result, content = nfvo.get_vnf_image_version_by_vnfm(mydb, id, http_content["version"]["serverseq"])
            self._send_response(result, content)
            return




    ### GET method 처리 ###############################################################################################################################
    def _http_get_active_nsr(self):
        """get nsr list"""
        result, data = orch_dbm.get_nsr(mydb, [])

        if result < 0:
            log.error("get_nsr error %d %s", (-result, data))
            self._send_response(result, data)
            return
        else:
            for d in data:
                af.convert_datetime2str_psycopg2(d)
            af.convert_str2boolean(data, ("publicyn", "builtinyn"))
            instances = {"nsr" : data}
            self._send_response(result, instances)


    def _http_get_nsr_all(self):

        """get nsr list including the deleted"""
        result, data = orch_dbm.get_nsr_all(mydb)

        if result < 0:
            log.error("http_get_nsr_all error %d %s" % (-result, data))
            self._send_response(result, data)
            return
        else:
            for d in data:
                af.convert_datetime2str_psycopg2(d)
            af.convert_str2boolean(data, ('publicyn','builtinyn') )
            instances={'nsr':data}
            self._send_response(result, instances)
            return


    def _http_get_nsr_id(self, nsr):
        """get NSR instances details, can use both uuid or name"""
        result, data = orch_dbm.get_nsr_id(mydb, nsr)

        if result < 0:
            log.error("http_get_nsr_id error %d %s" % (-result, data))

        data = util.secure_passwd(data)

        self._send_response(result, data)
        return


    def _http_get_vnc_console_url(self, vdu_id):
        log.debug("[NBI IN] Get the VNC Console URL of VDU %s" %(str(vdu_id)))
        result, data = nfvo.get_vdu_vnc_console_url(mydb, vdu_id)

        if result < 0:
            log.error("[NBI OUT] Get the VNC Console URL: Error %d: %s" %(-result, data))
            self._send_response(result, data)
        else:
            log.debug("[NBI OUT] Get the VNC Console URL: OK")
            self._send_response(result, data)


    def _http_get_vnf_console_url(self, vnf_id):
        log.debug("[NBI IN] Get the VNC Console URL List of VDUs in the VNFR %s" %(str(vnf_id)))
        result, data = nfvo.get_vnf_vnc_console_url(mydb, vnf_id)

        if result < 0:
            log.error("[NBI OUT] Get the VNC Console URL List: Error %d: %s" %(-result, data))
            self._send_response(result, data)
        else:
            log.debug("[NBI OUT] Get the VNC Console URL List: OK")
            self._send_response(result, data)


    def _http_get_nsr_vnc_console_url(self, nsr):
        log.debug("[NBI IN] Get the VNC Console URL List of VDUs in the NSR %s" %(str(nsr)))
        result, data = nfvo.get_nsr_vnc_console_url(mydb, nsr)

        if result < 0:
            log.error("[NBI OUT] Get the VNC Console URL List: Error %d: %s" %(-result, data))
            self._send_response(result, data)
        else:
            log.debug("[NBI OUT] Get the VNC Console URL List: OK")
            self._send_response(result, data)

    def _http_get_nsr_parameter(self, nsr):
        log.debug("[NBI IN] Get the Parameter List of the NSR %s" %(str(nsr)))
        result, data = nfvo.get_nsr_parameters(mydb, nsr)

        if result < 0:
            log.error("[NBI OUT] Get the Parameter List: Error %d: %s" %(-result, data))
            self._send_response(result, data)
        else:
            log.debug("[NBI OUT] Get the Parameter List: OK")
            self._send_response(result, {"nsr_params": data})

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


