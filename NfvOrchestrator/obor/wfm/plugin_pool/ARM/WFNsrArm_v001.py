# -*- coding: utf-8 -*-

from wfm.plugin_spec.WFNsrArmSpec import WFNsrArmSpec

import requests
import json
import sys
import time
import threading
import copy
import uuid as myUuid
from httplib import HTTPException
from requests.exceptions import ConnectionError

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

import db.dba_manager as orch_dbm
from utils.config_manager import ConfigManager

from engine.license_status import LicenseStatus
from utils import auxiliary_functions as af

from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

from engine.server_status import SRVStatus
from engine.action_status import ACTStatus
# from image_status import ImageStatus
from engine.action_type import ActionType
from engine.nfr_status import NFRStatus
from engine.nsr_status import NSRStatus

from utils.e2e_logger import e2elogger, CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL

global global_config

class WFNsrArm(WFNsrArmSpec):

    def new_nsr_arm(self, req_info, plugins):

        log.debug('req_info = %s' %str(req_info))

        # result, data = nfvo.new_nsr(mydb, nsd, http_content['start_v2'].get('instance_name', 'NotGiven'),
        #                             http_content['start_v2'].get('description', 'none'),
        #                             customer_id=http_content['start_v2'].get('customer_id', None),
        #                             customer_name=http_content['start_v2'].get('customer_name', None),
        #                             vim=http_content['start_v2'].get('vim'),
        #                             params=http_content['start_v2'].get('parameters'),
        #                             onebox_id=http_content['start_v2'].get('onebox_id'),
        #                             vnf_list=http_content['start_v2'].get('vnf_list'),
        #                             tid=http_content["tid"], tpath=http_content["tpath"], bonding=bonding)  # hjc

        # def new_nsr(mydb, nsd_id, instance_scenario_name, instance_scenario_description, customer_id=None, customer_name=None, vim=None, vim_tenant=None
        #             , startvms=True, params=None, use_thread=True, start_monitor=True, nsr_seq=None, onebox_id=None, vnf_list=[], tid=None, tpath="", bonding=None):

        orch_comm = plugins.get('orch_comm')

        nsd_id = req_info.get('nsd')
        tid = req_info.get('tid')
        tpath = req_info.get('tpath')

        start_v2 = req_info.get('start_v2')
        instance_scenario_name = start_v2.get('instance_name', 'NotGiven')
        instance_scenario_description = start_v2.get('description', 'none')
        customer_id = start_v2.get('customer_id', 'none')
        customer_name = start_v2.get('customer_name', 'none')
        vim = start_v2.get('vim', 'none')
        vim_tenant = None
        startvms = True
        params = start_v2.get('parameters', 'none')
        use_thread = True
        start_monitor = True
        nsr_seq = None
        onebox_id = start_v2.get('onebox_id', None)
        vnf_list = start_v2.get('vnf_list', [])
        bonding = None

        e2e_log = None

        try:
            log_info_message = "Provisioning NS Started (Name: %s)" % instance_scenario_name
            log.info(log_info_message.center(80, '='))
            # Step 1. Check arguments and initialize variables

            try:
                if not tid:
                    e2e_log = e2elogger(tname='NS Provisioning', tmodule='orch-f', tpath="orch_ns-prov")
                else:
                    e2e_log = e2elogger(tname='NS Provisioning', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_ns-prov")
            except Exception, e:
                log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
                e2e_log = None

            if e2e_log:
                e2e_log.job('Provisioning 생성 API Call 수신', CONST_TRESULT_SUCC,
                            tmsg_body="NS Name: %s\nParameters: %s" % (str(instance_scenario_name), params))

            # Step 2. Check Customer Info.
            log.debug("[Provisioning][NS] 2. Check Customer and Get VIM ID")
            result, customer_dict = self._new_nsr_check_customer(customer_id, onebox_id)

            log.debug('customer_dict = %s' %str(customer_dict))

            if result < 0:
                raise Exception("Customer is not ready to provision: %d %s" % (result, customer_dict))

            log.debug("[Provisioning][NS] 2. Success")
            if e2e_log:
                e2e_log.job("Check Customer Info", CONST_TRESULT_SUCC, tmsg_body=None)

            # Step 3. Check NS and Params
            log.debug("[Provisioning][NS] 3. Get and Check Scenario (NS) Templates")
            result, scenarioDict = orch_dbm.get_nsd_id(nsd_id)

            log.debug('scenarioDict = %s' %str(scenarioDict))

            if result < 0:
                log.error("[Provisioning][NS]  : Error, failed to get Scenario Info From DB %d %s" % (result, scenarioDict))
                raise Exception("Failed to get NSD from DB: %d %s" % (result, scenarioDict))
            elif result == 0:
                log.error("[Provisioning][NS]  : Error, No Scenario Found")
                raise Exception("Failed to get NSD from DB: NSD not found")

            # Step 3-1. save service number and service period from Order Manager in RLT
            if len(vnf_list) > 0:
                for vnf in scenarioDict['vnfs']:
                    for req_vnf in vnf_list:
                        if req_vnf['vnfd_name'] == vnf['vnfd_name'] and req_vnf['vnfd_version'] == vnf['version'] and vnf.get('service_number') is None:
                            vnf['service_number'] = req_vnf.get('service_number')
                            vnf['service_period'] = req_vnf.get('service_period')
                            break

            log.debug("[Provisioning][NS] 3. Success")
            if e2e_log:
                e2e_log.job("Check NS and Params", CONST_TRESULT_SUCC, tmsg_body=None)

            # check if the requested nsr already exists
            if instance_scenario_name == 'NotGiven':
                if onebox_id is not None:
                    instance_scenario_name = "NS-" + onebox_id + "." + scenarioDict['name']
                else:
                    instance_scenario_name = "NS-" + customer_dict['customerename'] + "." + scenarioDict['name']

            server_result, server_data = orch_dbm.get_server_id(customer_dict["server_id"])
            if server_result <= 0:
                raise Exception("Cannot do provisioning : %s" % server_result)
            else:
                if "nsseq" in server_data and server_data["nsseq"] is not None:
                    raise Exception("Cannot perform provisioning: NSR already exists : %d" % server_data["nsseq"])

            # check_result, check_data = orch_dbm.get_nsr_id(mydb, instance_scenario_name)
            # if check_result > 0:
            #     raise Exception("Cannot perform provisioning: NSR already exists")

            # # 회선 이중화 관련 Parameters 정리 및 resourcetemplate 정리
            # if params is not None and params != "":
            #     wan_dels = self._get_wan_dels(params)
            #     log.debug("_____ get_wan_dels : %s " % wan_dels)
            #     scenarioDict['parameters'] = common_manager.clean_parameters(scenarioDict['parameters'], wan_dels)
            #     log.debug("_____ clean_parameters END")
            #     if scenarioDict['resourcetemplatetype'] == "hot":
            #         rt_dict = _clean_wan_resourcetemplate(scenarioDict['resourcetemplate'], wan_dels)
            #         # 정리된 resourcetemplate dictionary 객체를 다시 yaml 포맷 문자열로 변경
            #         ns_hot_result, ns_hot_value = compose_nsd_hot(scenarioDict['name'], [rt_dict])
            #         if ns_hot_result < 0:
            #             log.error("[Provisioning][NS] Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
            #             raise Exception("Failed to compose nsd hot %d %s" % (ns_hot_result, ns_hot_value))
            #         scenarioDict['resourcetemplate'] = ns_hot_value
            #         log.debug("_____ clean_resourcetemplate END")

            check_param_result, check_param_data = self._new_nsr_check_param(customer_dict['vim_id'], scenarioDict['parameters'], params)

            if check_param_result < 0:
                raise Exception("Invalid Parameters: %d %s" % (check_param_result, check_param_data))

            # # Step 4. Check and Get Available VNF License Key
            # log.debug("[Provisioning][NS] 4. Check and Get Available VNF License Key")
            # check_license_result, check_license_data = self.new_nsr_check_license(scenarioDict['vnfs'])
            #
            # if check_license_result < 0:
            #     raise Exception("Failed to allocate VNF license: %d %s" % (check_license_result, check_license_data))
            #
            # log.debug("[Provisioning][NS] 4. Success")
            # if e2e_log:
            #     e2e_log.job("Check and Get Available VNF License Key", CONST_TRESULT_SUCC, tmsg_body="VNF license : %s" % check_license_data)

            # # XMS 계정 확인 및 생성 처리
            # result, msg = _create_account(mydb, customer_dict['server_id'], scenarioDict["parameters"], e2e_log)
            # if result < 0:
            #     pass

        except Exception, e:
            log.exception("[Provisioning][NS] Exception: %s" % str(e))

            if e2e_log:
                e2e_log.job('API Call 수신 처리 실패', CONST_TRESULT_FAIL,
                            tmsg_body="NS Name: %s\nParameters: %s\nResult:Fail, Cause:%s" % (str(instance_scenario_name), params, str(e)))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Bad_Request, "Failed to start Provisioning. Cause: %s" % str(e)

        # Add Following Fields Before Creating RLT 1: customerseq, vimseq, vim_tenant_name
        scenarioDict['customerseq'] = customer_dict['customerseq']
        scenarioDict['vimseq'] = customer_dict['vim_id']
        scenarioDict['vim_tenant_name'] = customer_dict['tenantid']

        update_server_dict = {}
        update_server_dict['serverseq'] = customer_dict['server_id']
        update_server_dict['onebox_type'] = server_data.get('nfsubcategory')
        update_server_dict['wf_Odm'] = plugins.get('wf_Odm')

        try:
            rollback_list = []

            # Step 5. Review and fill missing fields for DB 'tb_nsr'
            log.debug("[Provisioning][NS] 5. DB Insert: General Info. of the requested NS")

            scenarioDict['status'] = NSRStatus.CRT

            if instance_scenario_description == 'none':
                instance_scenario_description = scenarioDict.get('description', "No Description")
            if 'server_org' in customer_dict:
                scenarioDict['orgnamescode'] = customer_dict['server_org']
                scenarioDict['org_name'] = customer_dict['server_org']

            result, nsr_id = orch_dbm.insert_nsr_general_info(instance_scenario_name, instance_scenario_description, scenarioDict, nsr_seq)
            nsr_id = int(nsr_id)

            if result < 0:
                log.error("[Provisioning][NS]  : Error, failed to insert DB records %d %s" % (result, nsr_id))
                raise Exception("Failed to insert DB record for new NSR: %d %s" % (result, nsr_id))

            scenarioDict['nsseq'] = nsr_id
            scenarioDict['serverseq'] = customer_dict['server_id']

            # tb_server에 nsseq 저장.
            result, up_data = orch_dbm.update_server({"serverseq": customer_dict['server_id'], "nsseq": nsr_id})
            if result < 0:
                log.error("Failed to update nsr_id of server : %d %s" % (result, up_data))
                raise Exception("Failed to update nsr_id of server")

            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=scenarioDict, nsr_status=NSRStatus.CRT_parsing, server_dict=update_server_dict,
            #                   server_status=SRVStatus.PVS)

            instanceDict = {}
            instanceDict['onebox_type'] = server_data.get('nfsubcategory')

            com_dict = {}
            com_dict['onebox_type'] = server_data.get('nfsubcategory')
            com_dict['action_type'] = ActionType.PROVS
            com_dict['nsr_data'] = scenarioDict
            com_dict['nsr_status'] = NSRStatus.CRT_parsing
            com_dict['server_dict'] = update_server_dict
            com_dict['server_status'] = SRVStatus.PVS
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            log.debug("[Provisioning][NS] 5. success")

            if e2e_log:
                e2e_log.job("Review and fill missing fields for DB 'tb_nsr'", CONST_TRESULT_SUCC, tmsg_body=None)

            # # TODO Replace VNFD Name to VNF Name
            rlt_dict = copy.deepcopy(scenarioDict)
            rlt_dict["name"] = instance_scenario_name
            rlt_dict['onebox_type'] = server_data.get('nfsubcategory')

            pr = params.split(';')

            for p in pr:
                if p.find('imageId') > 0:
                    image_param = p.split('=')
                    rlt_dict['image_name'] = image_param[1]
                    continue

                if p.find('redFixedIp') > 0:
                    ip_param = p.split('=')
                    rlt_dict['main_ip_addr'] = ip_param[1]

            if use_thread:
                th = threading.Thread(target=self.new_nsr_thread, args=(nsd_id, instance_scenario_name, instance_scenario_description
                                                                   , rlt_dict, customer_dict['server_id'], vim_tenant
                                                                   , startvms, params, rollback_list, use_thread, start_monitor, e2e_log, bonding, plugins))
                th.start()
                return orch_dbm.get_nsr_id(nsr_id)
            else:
                return self.new_nsr_thread(nsd_id, instance_scenario_name, instance_scenario_description
                                      , rlt_dict, customer_dict['server_id'], vim_tenant
                                      , startvms, params, rollback_list, False, start_monitor, e2e_log, bonding, plugins)
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=scenarioDict, nsr_status=NSRStatus.ERR, server_dict=update_server_dict, server_status=SRVStatus.ERR)

            instanceDict = {}
            instanceDict['onebox_type'] = req_info.get('onebox_type')

            com_dict = {}
            com_dict['onebox_type'] = server_data.get('nfsubcategory')
            com_dict['action_type'] = ActionType.PROVS
            com_dict['nsr_data'] = instanceDict
            com_dict['action_status'] = NSRStatus.ERR
            com_dict['server_dict'] = update_server_dict
            com_dict['server_status'] = SRVStatus.DSC
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            if e2e_log:
                e2e_log.job('NS Prov - 전처리', CONST_TRESULT_FAIL,
                            tmsg_body="NS Name: %s\nParameters: %s\nResult:Fail, Cause:%s" % (str(instance_scenario_name), params, str(e)))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "NS 설치가 실패하였습니다. 원인: %s" % str(e)


    def new_nsr_thread(self, nsd_id, instance_scenario_name, instance_scenario_description, rlt_dict, server_id
                       , vim_tenant=None, startvms=True, params=None, rollback_list=[], use_thread=True, start_monitor=True, e2e_log=None, bonding=None, plugins=None):

        log.debug('[new_nsr_thread] IN......')
        orch_comm = plugins.get('orch_comm')

        update_server_dict = {}
        update_server_dict['serverseq'] = server_id
        update_server_dict['nsseq'] = rlt_dict.get('nsseq')

        try:

            # get OneBox info
            ob_result, ob_data = orch_dbm.get_server_id(server_id)
            if ob_result <= 0:
                raise Exception("Not found the Server : %s" %str(server_id))

            onebox_type = ob_data.get('nfsubcategory')

            # # Step 6. Get VIM Connector
            # log.debug("[Provisioning][NS] 6. Get VIM Connector")
            # if use_thread:
            #     log_info_message = "Provisioning NS - Thread Started (%s)" % instance_scenario_name
            #     log.info(log_info_message.center(80, '='))
            #
            # log.debug("[Provisioning][NS] : Connect to the Target VIM %s" % str(rlt_dict['vimseq']))
            #
            # result, vims = get_vim_connector(mydb, rlt_dict['vimseq'])
            # if result < 0:
            #     # log.error("[Provisioning][NS]  : Error, failed to connect to VIM")
            #     raise Exception("Failed to establish a VIM connection: %d %s" % (result, vims))
            # elif result > 1:
            #     # log.error("[Provisioning][NS]  : Error, Several VIMs available, must be identify the target VIM")
            #     raise Exception("Failed to establish a VIM connection:Several VIMs available, must be identify")
            #
            # myvim = vims.values()[0]
            # rlt_dict['vim_tenant_name'] = myvim['tenant']
            # rlt_dict['vimseq'] = myvim['id']
            #
            # log.debug("[Provisioning][NS] 6. Success")
            # if e2e_log:
            #     e2e_log.job("Get VIM Connector", CONST_TRESULT_SUCC, tmsg_body=None)
            #
            # # Step 7. Compose Arguments for Parameters
            # log.debug("[Provisioning][NS] 7. Compose Arguments for Parameters")
            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_parsing, server_dict=update_server_dict,
            #                   server_status=SRVStatus.PVS)
            #
            # # cache_nsr_parameters(mydb, server_id, nsd_id, rlt_dict['parameters'])
            #
            # vnf_name_list = []
            # for vnf in rlt_dict['vnfs']:
            #     vnf_name_list.append(vnf['name'])
            #
            # iparm_result, iparm_content = common_manager.compose_nsr_internal_params(vnf_name_list, rlt_dict['parameters'])
            # if iparm_result < 0:
            #     # log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
            #     raise Exception("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
            #
            # template_param_list = []
            # for param in rlt_dict['parameters']:
            #     if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
            #         template_param_list.append(param)
            #
            # log.debug("[Provisioning][NS] 7. Success")
            #
            # if e2e_log:
            #     e2e_log.job("Compose Arguments for Parameters", CONST_TRESULT_SUCC, tmsg_body="template_param_list = %s" % template_param_list)

            # Step 8. Create VMs Using Heat
            log.debug("[Provisioning][NS] 8. Create VMs Using the Heat")
            if e2e_log:
                e2e_log.job("Create VMs Using Heat", CONST_TRESULT_NONE, tmsg_body=None)

            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_creatingvr)

            com_dict = {}
            com_dict['onebox_type'] = onebox_type
            com_dict['action_type'] = ActionType.PROVS
            com_dict['nsr_data'] = rlt_dict
            com_dict['nsr_status'] = NSRStatus.CRT_creatingvr
            com_dict['server_dict'] = None
            com_dict['server_status'] = None
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            # stack_result, stack_data = _new_nsr_create_vm(myvim, rlt_dict, instance_scenario_name, rlt_dict['resourcetemplatetype'],
            #                                               rlt_dict['resourcetemplate'], template_param_list)

            create_dict = {}
            create_dict['serverseq'] = server_id
            create_dict['onebox_type'] = onebox_type
            create_dict['onebox_id'] = ob_data.get('onebox_id')
            create_dict['obagent_base_url'] = ob_data.get('obagent_base_url')
            create_dict['image_name'] = rlt_dict.get('image_name')
            create_dict['update_server_dict'] = update_server_dict
            create_dict['ob_agents'] = plugins.get('wf_obconnector')
            create_dict['odm'] = plugins.get('wf_Odm')
            create_dict['orch_comm'] = orch_comm
            create_dict['e2e_log'] = e2e_log

            stack_result, stack_data = self._new_nsr_create_vm(create_dict)

            if stack_result < 0:
                if e2e_log:
                    e2e_log.job("Create VMs Using Heat", CONST_TRESULT_FAIL, tmsg_body=None)
                raise Exception("Failed to create VMs for VNFs: %d %s" % (stack_result, stack_data))
            else:
                # rlt_dict['uuid'] = stack_data
                rlt_dict['uuid'] = ob_data.get('serveruuid')

            log.debug("[Provisioning][NS] 8. Success")
            if e2e_log:
                e2e_log.job("Create VMs Using Heat", CONST_TRESULT_SUCC, tmsg_body="Stack UUID : %s" % str(stack_data))

            # Step 9. compose web url for each VDUs and VNF info
            log.debug("[Provisioning][NS] 9. compose web url for each VDUs and VNF info")
            vnf_proc_result, vnf_proc_data = self.new_nsr_vnf_proc(rlt_dict)
            if vnf_proc_result < 0:
                log.warning("Failed to process vnf app information: %d %s" % (vnf_proc_result, vnf_proc_data))

            if e2e_log:
                e2e_log.job("Compose web url for each VDUs and VNF info", CONST_TRESULT_SUCC, tmsg_body=None)
            log.debug("[Provisioning][NS] 9. Success")

            # Step 10. DB Insert NS Instance
            log.debug("[Provisioning][NS] 10. Insert DB Records for NS Instance")
            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_processingdb)

            com_dict = {}
            com_dict['onebox_type'] = rlt_dict.get('onebox_type')
            com_dict['action_type'] = ActionType.PROVS
            com_dict['nsr_data'] = rlt_dict
            com_dict['nsr_status'] = NSRStatus.CRT_processingdb
            com_dict['server_dict'] = None
            com_dict['server_status'] = None
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            nsr_db_result, instance_id = self.new_nsr_db_proc(rlt_dict, instance_scenario_name, instance_scenario_description)

            if nsr_db_result < 0:
                error_txt = "Failed to insert DB Records %d %s" % (nsr_db_result, str(instance_id))
                # log.error("[Provisioning][NS]  : Error, %s" % error_txt)
                raise Exception(error_txt)

            log.debug("[Provisioning][NS] 10. Success")
            if e2e_log:
                e2e_log.job("DB Insert NS Instance", CONST_TRESULT_SUCC, tmsg_body="NS Instance ID : %s" % instance_id)

            # # Step 11. VNF Configuration
            # log.debug("[Provisioning][NS] 11. VNF Configuration")
            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_configvnf)
            #
            # if bonding is True:
            #     log.debug('##########   3. bonding 구성 처리   ################')
            #
            # vnf_confg_result, vnf_config_data = _new_nsr_vnf_conf(mydb, rlt_dict, server_id, e2e_log, bonding)
            # if vnf_confg_result < 0:
            #     # log.error("[Provisioning][NS]   : Error, %d %s" % (vnf_confg_result, vnf_config_data))
            #     raise Exception("Failed to init-config VNFs: %d %s" % (vnf_confg_result, vnf_config_data))
            #
            # log.debug("[Provisioning][NS] 11. Success")
            # if e2e_log:
            #     e2e_log.job("VNF Configuration", CONST_TRESULT_SUCC, tmsg_body=None)
            #
            # # Step 12. Verify NS Instance
            # log.debug("[Provisioning][NS] 12. Test NS Instance")
            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_testing)
            #
            # res, msg = _new_nsr_test(mydb, server_id, rlt_dict)
            #
            # log.debug("[Provisioning][NS]   : Test Result = %d, %s" % (res, msg))
            # if res < 0:
            #     error_txt = "NSR Test Failed %d %s" % (res, str(msg))
            #     # log.error("[Provisioning][NS]  : Error, %s" % error_txt)
            #     raise Exception(error_txt)

            log.debug("[Provisioning][NS] 12. Success")
            if e2e_log:
                e2e_log.job("Verify NS Instance", CONST_TRESULT_SUCC, tmsg_body=None)

            # # Step 13. Setup Monitor for the NS Instance
            # log.debug("[Provisioning][NS] 13. Setup Monitor")
            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.CRT_startingmonitor)
            #
            # if start_monitor:
            #     mon_result, mon_data = new_nsr_start_monitor(mydb, rlt_dict, server_id, e2e_log)
            #     if mon_result < 0:
            #         log.warning("[Provisioning][NS]   : Failed %d %s" % (mon_result, mon_data))
            #         # raise Exception("Failed to setup Monitor for the NS Instance %d %s" % (mon_result, mon_data))
            #         log.debug("[Provisioning][NS] 13. Failed")
            #         if e2e_log:
            #             e2e_log.job("Setup Monitor for the NS Instance", CONST_TRESULT_FAIL, tmsg_body=None)
            #     else:
            #         log.debug("[Provisioning][NS] 13. Success")
            #
            #         if e2e_log:
            #             e2e_log.job("Setup Monitor for the NS Instance", CONST_TRESULT_SUCC, tmsg_body=None)
            # # log.debug("[Provisioning][NS] 10. Skip")
            #
            # log.debug("[Provisioning][NS] 14. Insert RLT into DB")
            # ur_result, ur_data = common_manager.store_rlt_data(mydb, rlt_dict)
            # if ur_result < 0:
            #     # log.error("Failed to insert rlt data: %d %s" %(ur_result, ur_data))
            #     raise Exception("Failed to insert rlt data: %d %s" % (ur_result, ur_data))
            # log.debug("[Provisioning][NS] 14. Success")
            # if e2e_log:
            #     e2e_log.job("RLT - DB Insert", CONST_TRESULT_SUCC, tmsg_body="rlt_dict\n%s" % (json.dumps(rlt_dict, indent=4)))
            #
            # update_nsr_status(mydb, ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.RUN, server_dict=update_server_dict, server_status=SRVStatus.INS)

            com_dict = {}
            com_dict['onebox_type'] = rlt_dict.get('onebox_type')
            com_dict['action_type'] = ActionType.PROVS
            com_dict['nsr_data'] = rlt_dict
            com_dict['nsr_status'] = NSRStatus.RUN
            com_dict['server_dict'] = update_server_dict
            com_dict['server_status'] = SRVStatus.INS
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            if use_thread:
                log_info_message = "Provisioning NS - Thread Finished (%s) Status = %s" % (str(instance_id), rlt_dict.get('status'))
            else:
                log_info_message = "Provisioning NS Completed (%s) Status = %s" % (str(instance_id), rlt_dict.get('status'))
            log.info(log_info_message.center(80, '='))

            if e2e_log:
                e2e_log.job("Provisioning 완료", CONST_TRESULT_SUCC, tmsg_body=None)
                e2e_log.finish(CONST_TRESULT_SUCC)

            return orch_dbm.get_nsr_id(instance_id)

        except Exception, e:
            if use_thread:
                log_info_message = "Provisioning NS - Thread Finished with Error: Exception [%s] %s" % (str(e), sys.exc_info())
            else:
                log_info_message = "Provisioning NS Failed: Exception [%s] %s" % (str(e), sys.exc_info())
            log.exception(log_info_message.center(80, '='))

            # update_nsr_status(ActionType.PROVS, nsr_data=rlt_dict, nsr_status=NSRStatus.ERR, server_dict=update_server_dict, server_status=SRVStatus.ERR,
            #                   nsr_status_description=str(e))

            instanceDict = {}
            instanceDict['onebox_type'] = rlt_dict.get('onebox_type')

            com_dict = {}
            com_dict['onebox_type'] = rlt_dict.get('onebox_type')
            com_dict['nsr_status'] = NSRStatus.ERR
            com_dict['nsr_data'] = instanceDict
            # com_dict['action_status'] = None
            com_dict['server_dict'] = update_server_dict
            com_dict['server_status'] = SRVStatus.ERR
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            if e2e_log:
                e2e_log.job('NS Provisioning 실패', CONST_TRESULT_FAIL,
                            tmsg_body="NS Name: %s\nParameters: %s\nResult:Fail, Cause:%s" % (str(instance_scenario_name), params, str(e)))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "NS 설치가 실패하였습니다. 원인: %s" % str(e)


    # def delete_nsr(self, nsr_id, need_stop_monitor=True, only_orch=False, use_thread=True, tid=None, tpath="", force_flag=False):
    def delete_nsr(self, req_info, plugins):

        log.debug('[WF ArmBox] delete nsr Start *****')

        log.debug('[WF ArmBox] req_info = %s' %str(req_info))

        onebox_type = req_info.get('onebox_type')
        nsr_id = req_info.get('nsr')
        need_stop_monitor = req_info.get('need_stop_monitor', True)
        only_orch = req_info.get('only_orch', False)
        use_thread = req_info.get('use_thread', True)
        tid = req_info.get('tid', None)
        tpath = req_info.get('tpath', "")
        force_flag = req_info.get('tpath', False)

        orch_comm = plugins.get('orch_comm')

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

            # Step 1. get scenario instance from DB
            # log.debug ("Check that the nsr_id exists and getting the instance dictionary")
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

            if e2e_log:
                e2e_log.job("Get scenario instance from DB", CONST_TRESULT_SUCC,
                            tmsg_body="Scenario instance Info : %s" % (json.dumps(instanceDict, indent=4)))

            # Step 2. update the status of the scenario instance to 'DELETING'
            server_result, server_content = orch_dbm.get_server_filters({"nsseq": instanceDict['nsseq'], 'onebox_type': onebox_type})
            if server_result <= 0:
                log.warning("failed to get server info %d %s" % (server_result, server_content))
                server_content = None
                raise Exception("Failed to get server info.: %d %s" % (server_result, server_content))
            else:
                server_data = server_content[0]

            if use_thread:
                # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL, server_dict=server_data, server_status=SRVStatus.OOS)

                com_dict = {}
                com_dict['onebox_type'] = onebox_type
                com_dict['action_type'] = ActionType.DELNS
                com_dict['nsr_data'] = instanceDict
                com_dict['nsr_status'] = NSRStatus.DEL
                com_dict['server_dict'] = server_data
                com_dict['server_status'] = SRVStatus.OOS
                com_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_nsr_status', com_dict)
                com_dict.clear()

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
                                          args=(instanceDict, server_data, need_stop_monitor, use_thread, force_flag, e2e_log, only_orch, plugins))
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
                return self._delete_nsr_thread(instanceDict, server_data, need_stop_monitor=need_stop_monitor, use_thread=False, force_flag=force_flag, e2e_log=e2e_log,
                                               only_orch=only_orch, plugins=plugins)
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR,
            #                   nsr_status_description=str(e))

            com_dict = {}
            com_dict['onebox_type'] = onebox_type
            com_dict['action_type'] = ActionType.DELNS
            com_dict['nsr_data'] = instanceDict
            com_dict['nsr_status'] = NSRStatus.ERR
            com_dict['server_dict'] = server_data
            com_dict['server_status'] = SRVStatus.ERR
            com_dict['wf_Odm'] = plugins.get('wf_Odm')

            orch_comm.getFunc('update_nsr_status', com_dict)
            com_dict.clear()

            if e2e_log:
                e2e_log.job('NS 종료', CONST_TRESULT_FAIL, tmsg_body="NS 삭제가 실패하였습니다. 원인: %s" % str(e))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)


    def _delete_nsr_thread(self, instanceDict, server_data, need_stop_monitor=True, use_thread=True, force_flag=False, e2e_log=None, only_orch=False, plugins=None):
        log.debug('[ArmBox] delete nsr thread start *******************')

        # Check One-Box connectivity
        onebox_chk_status = server_data['status']
        onebox_type = server_data.get('nfsubcategory')

        orch_comm = plugins.get('orch_comm')

        # try:
        #     wf_svr_dict = {'check_settings': None, 'onebox_id': server_data['onebox_id'], 'onebox_type': onebox_type, 'force': True}
        #     wf_svr_dict['orch_comm'] = plugins.get('orch_comm')
        #     wf_svr_dict['wf_obconnector'] = plugins.get('wf_obconnector')
        #
        #     # wf_server_manager = wfm_server_manager.server_manager(req_info)
        #     wf_server_arm_manager = plugins.get('wf_server_arm_manager')
        #     ob_chk_result, ob_chk_data = wf_server_arm_manager.check_onebox_valid(wf_svr_dict)
        #     wf_svr_dict.clear()
        #
        #     if ob_chk_result < 0:
        #         log.error("failed to check One-Box Status for %s" % server_data['onebox_id'])
        #         raise Exception("Failed to check a connection to One-Box")
        #
        #     # ob_chk_result, ob_chk_data = check_onebox_valid(mydb, None, server_data['onebox_id'], True)
        #     # if ob_chk_result < 0:
        #     #     log.error("failed to check One-Box Status for %s" % server_data['onebox_id'])
        #     #     raise Exception("Failed to check a connection to One-Box")
        # except Exception, e:
        #     log.exception("Exception: %s" % str(e))
        #     onebox_chk_status = SRVStatus.DSC
        #     if force_flag is False:
        #         # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.DSC)
        #
        #         com_dict = {}
        #         com_dict['onebox_type'] = onebox_type
        #         com_dict['action_type'] = ActionType.DELNS
        #         com_dict['nsr_data'] = instanceDict
        #         com_dict['nsr_status'] = NSRStatus.ERR
        #         com_dict['server_dict'] = server_data
        #         com_dict['server_status'] = SRVStatus.DSC
        #         com_dict['wf_Odm'] = plugins.get('wf_Odm')
        #
        #         orch_comm.getFunc('update_nsr_status', com_dict)
        #         com_dict.clear()
        #
        #         return -HTTP_Internal_Server_Error, "Failed to check a connection to One-Box"
        #     # update_nsr_status(mydb, "D", nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR)

        try:
            if use_thread:
                log_info_message = "Deleting NS - Thread Started (%s)" % instanceDict['name']
                log.info(log_info_message.center(80, '='))

                if e2e_log:
                    e2e_log.job('NS 종료 Background Thread 시작', CONST_TRESULT_SUCC, tmsg_body=log_info_message)

            # if need_stop_monitor:
            #     if use_thread:
            #         update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL_stoppingmonitor)
            #
            #     if e2e_log:
            #         e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_NONE, tmsg_body="NS 모니터링 종료 요청")
            #
            #     monitor_result, monitor_response = stop_nsr_monitor(mydb, instanceDict['nsseq'], e2e_log)
            #
            #     if monitor_result < 0:
            #         log.error("failed to stop monitor for %d: %d %s" % (instanceDict['nsseq'], monitor_result, str(monitor_response)))
            #         if e2e_log:
            #             e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_FAIL,
            #                         tmsg_body="NS 모니터링 종료 요청 실패\n원인: %d %s" % (monitor_result, monitor_response))
            #             # return monitor_result, monitor_response
            #     else:
            #         if e2e_log:
            #             e2e_log.job('NS 모니터링 종료 요청', CONST_TRESULT_SUCC,
            #                         tmsg_body="NS 모니터링 종료 요청 완료")
            #
            # if use_thread:
            #     update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.DEL_deletingvr)

            # return back license and request to finish VNF
            if not only_orch:  # TODO : 제어시스템에서만 삭제하는 조건 추가...
            #     if onebox_chk_status != SRVStatus.DSC:
            #         for vnf in instanceDict['vnfs']:
            #             if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
            #                 log.debug("[HJC] Deleting GiGA Office Solution for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
            #                 try:
            #                     go_result, go_content = self._delete_nsr_GigaOffice(vnf, server_data['serverseq'], instanceDict['nsseq'], e2e_log)
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
            #             # raise Exception("Failed to establish VIM connection: %d %s" % (result, vims))
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
                # ArmBox-agent 에 vm 삭제 요청
                delete_dict = {}
                delete_dict['serverseq'] = server_data.get('serverseq')
                delete_dict['onebox_type'] = onebox_type
                delete_dict['onebox_id'] = server_data.get('onebox_id')
                delete_dict['obagent_base_url'] = server_data.get('obagent_base_url')
                delete_dict['update_server_dict'] = server_data
                delete_dict['ob_agents'] = plugins.get('wf_obconnector')
                delete_dict['odm'] = plugins.get('wf_Odm')
                delete_dict['orch_comm'] = orch_comm
                delete_dict['e2e_log'] = e2e_log

                result, data = self._nsr_delete_vm(delete_dict)
                if result == -HTTP_Not_Found:
                    log.error("Not exists. Just Delete DB Records")
                elif result < 0:
                    log.error("failed to delete stack from Heat because of " + data)

                    if result != -HTTP_Not_Found:
                        raise Exception("failed to delete stack from Heat because of " + data)

            result, c = orch_dbm.delete_nsr(instanceDict['nsseq'])

            if result < 0:
                log.error("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))
                raise Exception("failed to delete instance record from db: %s" % str(instanceDict['nsseq']))

            server_data.pop('nsseq')
            if use_thread:
                if onebox_chk_status == SRVStatus.DSC:
                    # update_nsr_status(mydb, ActionType.DELNS, nsr_data=None, nsr_status=None, server_dict=server_data, server_status=SRVStatus.DSC)

                    com_dict = {}
                    com_dict['onebox_type'] = onebox_type
                    com_dict['action_type'] = ActionType.DELNS
                    com_dict['nsr_data'] = None
                    com_dict['nsr_status'] = None
                    com_dict['server_dict'] = server_data
                    com_dict['server_status'] = SRVStatus.DSC
                    com_dict['wf_Odm'] = plugins.get('wf_Odm')

                    orch_comm.getFunc('update_nsr_status', com_dict)
                    com_dict.clear()
                else:
                    # update_nsr_status(mydb, ActionType.DELNS, nsr_data=None, nsr_status=None, server_dict=server_data, server_status=SRVStatus.RDS)

                    com_dict = {}
                    com_dict['onebox_type'] = onebox_type
                    com_dict['action_type'] = ActionType.DELNS
                    com_dict['nsr_data'] = None
                    com_dict['nsr_status'] = None
                    com_dict['server_dict'] = server_data
                    com_dict['server_status'] = SRVStatus.RDS
                    com_dict['wf_Odm'] = plugins.get('wf_Odm')

                    orch_comm.getFunc('update_nsr_status', com_dict)
                    com_dict.clear()

            # if not only_orch:
            #     # resume_monitor_wan 처리를 명시적으로 해준다.
            #     result, ob_agents = common_manager.get_onebox_agent(mydb, onebox_id=server_data['onebox_id'])
            #     if result < 0:
            #         log.error("Failed to get a connection to the One-Box Agent: %d %s" % (result, ob_agents))
            #         return result, str(ob_agents)
            #
            #     myoba = ob_agents.values()[0]
            #     rs_result, rs_content = myoba.resume_monitor_wan()
            #     if rs_result < 0:
            #         log.error("Failed to resume monitoring WAN of the One-Box: %d %s" % (rs_result, rs_content))

            if use_thread:
                log_info_message = "Deleting NS - Thread Finished (%s)" % instanceDict['name']
                log.info(log_info_message.center(80, '='))

            if e2e_log:
                e2e_log.job('NS 종료 처리 완료', CONST_TRESULT_SUCC, tmsg_body="NS 종료 처리 완료")
                e2e_log.finish(CONST_TRESULT_SUCC)

            return 1, 'NSR ' + str(instanceDict['nsseq']) + ' deleted'

        except Exception, e:
            if use_thread:
                log_info_message = "Deleting NS - Thread Finished with Error Exception: %s" % str(e)
                log.exception(log_info_message.center(80, '='))
            else:
                log.exception("Exception: %s" % str(e))

            if onebox_chk_status == SRVStatus.DSC:
                # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.DSC)

                com_dict = {}
                com_dict['onebox_type'] = onebox_type
                com_dict['action_type'] = ActionType.DELNS
                com_dict['nsr_data'] = instanceDict
                com_dict['nsr_status'] = NSRStatus.ERR
                com_dict['server_dict'] = server_data
                com_dict['server_status'] = SRVStatus.DSC
                com_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_nsr_status', com_dict)
                com_dict.clear()
            else:
                # update_nsr_status(mydb, ActionType.DELNS, nsr_data=instanceDict, nsr_status=NSRStatus.ERR, server_dict=server_data, server_status=SRVStatus.ERR)

                com_dict = {}
                com_dict['onebox_type'] = onebox_type
                com_dict['action_type'] = ActionType.DELNS
                com_dict['nsr_data'] = instanceDict
                com_dict['nsr_status'] = NSRStatus.ERR
                com_dict['server_dict'] = server_data
                com_dict['server_status'] = SRVStatus.ERR
                com_dict['wf_Odm'] = plugins.get('wf_Odm')

                orch_comm.getFunc('update_nsr_status', com_dict)
                com_dict.clear()

            if e2e_log:
                e2e_log.job('NS 종료 처리 실패', CONST_TRESULT_FAIL, tmsg_body=str(e))
                e2e_log.finish(CONST_TRESULT_FAIL)

            return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. 원인: %s" % str(e)


    ####################        내장 함수       ############################################################################

    def _get_wan_dels(self, req_params):
        """
        회선이중화 관련 작업. UI에서 받은 Parameters를 확인해서 사용하지 않는 WAN 리스트 작성
        :param req_params: UI에서 받은 Parameters
        :return: 사용하지 않는 WAN 리스트
        """

        wan_dels = ["R1", "R2", "R3"]
        param_list = req_params.split(';')
        for str_param in param_list:
            kv = str_param.split('=')
            # 전제조건 : RPARM_redFixedMac 값이 필수
            if kv[0].find("RPARM_redFixedMacR") >= 0:
                for num in range(1, 4, 1):  # R1 ~ R3
                    if kv[0].find("R" + str(num)) >= 0:
                        if kv[1] != "" and kv[1].lower() != "none":
                            # wan_opts.append("R" + str(num))
                            wan_dels.remove("R" + str(num))
                            break
        return wan_dels


    def _new_nsr_check_customer(self, customer_id, onebox_id=None, check_server=True):
        result, customer_dict = orch_dbm.get_customer_id(customer_id)

        if result < 0:
            log.error("[Provisioning][NS]  : Error, failed to get customer info from DB %d %s" % (result, customer_dict))
            return -HTTP_Internal_Server_Error, "Failed to get Customer Info. from DB: %d %s" % (result, customer_dict)
        elif result == 0:
            log.error("[Provisioning][NS]  : Error, Customer Not Found")
            return -HTTP_Not_Found, "Failed to get Customer Info. from DB: Customer not found"

        result, customer_inventory = orch_dbm.get_customer_resources(customer_id, onebox_id)
        if result <= 0:
            log.error("[Provisioning][NS]  : Error, failed to get resource info of the customer %s" % (str(customer_id)))
            return -HTTP_Internal_Server_Error, "failed to get resource info of the customer %s" % (str(customer_id))

        for item in customer_inventory:
            if item['resource_type'] == 'vim':
                customer_dict['vim_id'] = item['vimseq']

            if item['resource_type'] == 'server':
                log.debug("[Provisioning][NS] server info = %s" % str(item))

                customer_dict['server_id'] = item['serverseq']
                customer_dict['server_org'] = item.get('orgnamescode')
                if check_server:
                    server_check_result, server_check_msg = self._check_server_provavailable(item)

                    if server_check_result < 0:
                        return -HTTP_Bad_Request, "Cannot perform provisioning with the server: %d %s" % (server_check_result, server_check_msg)

        if customer_dict.get('vim_id') is None:
            log.error("[Provisioning][NS]  : Error, VIM Not Found for the Customer %s" % str(customer_id))
            return -HTTP_Internal_Server_Error, "Failed to get VIM Info."

        return 200, customer_dict


    def _check_server_provavailable(self, server_dict):
        if server_dict['status'] != SRVStatus.RDS:
            log.error("_check_server_provavailable() The One-Box server is not ready yet: %s" % server_dict['status'])
            return -HTTP_Bad_Request, "The One-Box server is not ready"

        if server_dict['nsseq']:
            log.error("_check_server_provavailable() The customer already has a NS: %s" % str(server_dict['nsseq']))
            return -HTTP_Bad_Request, "The customer already has a NS: %s" % str(server_dict['nsseq'])

        return 200, "OK"

    # One-Box Agent 진행 상태 조회
    def _status_onebox_agent_progress(self, ob_agent, action, req_dict):
        result = 200
        data = "DOING"

        try:
            # req_type = req_dict.get('request_type') # "restore"
            req_type = action  # "restore"
            trans_id = req_dict.get('transaction_id')

            # One-Box Agent 진행 상태 조회
            progress_dict = {}
            progress_dict['onebox_id'] = req_dict.get('onebox_id')
            progress_dict['obagent_base_url'] = req_dict.get('obagent_base_url')
            progress_dict['order'] = req_dict.get('order')

            check_result, check_data = ob_agent.prov_check_onebox_agent_progress_arm(progress_dict=progress_dict, request_type=req_type, transaction_id=trans_id)
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            check_result = -500
            check_data = {'status': "UNKNOWN", 'error': str(e)}

        if check_result < 0:
            result = check_result
            data = "DOING"
            log.debug("Error %d, %s" % (check_result, str(check_data)))
        else:
            if action == "prov":
                log.debug("Progress form One-Box by Agent: %s" % (check_data['status']))
                if check_data['status'] == "DONE":
                    data = "DONE"
                elif check_data['status'] == "ERROR":
                    data = "ERROR"
                else:
                    data = check_data['status']
            else:  # reboot : oba_baseurl/version
                data = "DONE"

        return result, data


    def _new_nsr_create_vm(self, create_dict):

        # onebox-agent
        result, ob_agents = 1, create_dict.get('ob_agents')

        server_id = create_dict.get('serverseq')
        onebox_type = create_dict.get('onebox_type')
        onebox_id = create_dict.get('onebox_id')
        obagent_base_url = create_dict.get('obagent_base_url')
        image_name = create_dict.get('image_name')
        update_server_dict = create_dict.get('update_server_dict')
        odm = create_dict.get('odm')
        orch_comm = create_dict.get('orch_comm')
        e2e_log = create_dict.get('e2e_log')

        if result < 0 or result > 1:
            log.error("Error. Invalid DB Records for the One-Box Agent: %s" % str(server_id))
            log.debug("Error. Invalid DB Records for the One-Box Agent: %s" % str(server_id))
            # raise Exception("Failed to OneBox Agent Connection")
            return -500, "Failed to OneBox Agent Connection"
        else:
            log.debug('[ob_agents] 프로비저닝 시작')

            prv_dict = {}
            prv_dict['onebox_id'] = onebox_id
            prv_dict['obagent_base_url'] = obagent_base_url
            prv_dict['image_name'] = image_name

            log.debug('prv_dict = %s' % str(prv_dict))

            prv_result, prv_content = ob_agents.provisionning_arm(prv_dict)

            if prv_result < 0:
                result = prv_result
                log.error("Failed to ArmBox Provisioning %s: %d %s" % (onebox_id, prv_result, prv_content))
                log.debug("Failed to ArmBox Provisioning %s: %d %s" % (onebox_id, prv_result, prv_content))

                # instanceDict = {}
                # instanceDict['onebox_type'] = onebox_type
                #
                # com_dict = {}
                # com_dict['onebox_type'] = onebox_type
                # com_dict['action_type'] = ActionType.PROVS
                # com_dict['nsr_data'] = instanceDict
                # com_dict['action_status'] = NSRStatus.ERR
                # com_dict['server_dict'] = update_server_dict
                # com_dict['server_status'] = SRVStatus.ERR
                # com_dict['wf_Odm'] = odm
                #
                # orch_comm.getFunc('update_nsr_status', com_dict)
                # com_dict.clear()

                # raise Exception(prv_content)
                return -500, "Failed to ArmBox Provisioning"

            if e2e_log:
                e2e_log.job('Call API of One-Box Agent: Restore One-Box', CONST_TRESULT_SUCC, tmsg_body=None)

            # 5-3 Wait for Restoring One-Box
            log.debug("[_RESTORE_ONEBOX_THREAD - %s] Completed to send restore command to the One-Box Agent : %s" % (onebox_id, str(prv_content)))
            if prv_content['status'] == "DOING":
                action = "prov"
                trial_no = 1
                pre_status = "UNKNOWN"

                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Wait for restore One-Box by Agent" % onebox_id)
                time.sleep(10)

                check_status = ""

                trial_max_no = 30
                while trial_no < trial_max_no:
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] Checking the progress of restore (%d):" % (onebox_id, trial_no))

                    # One-Box Agent 진행 상태 조회
                    req_dict = {}
                    req_dict['onebox_id'] = onebox_id
                    req_dict['obagent_base_url'] = obagent_base_url
                    req_dict['order'] = 'C'

                    result, check_status = self._status_onebox_agent_progress(ob_agents, action, req_dict)
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

                log.debug('trial_no = %s, check_status = %s' % (str(trial_no), str(check_status)))

                # 30번 상태체크 후에도 정상 응답('DONE', 'ERROR')이 없어 'DOING'인 경우 'ERROR' 처리
                if trial_no == trial_max_no:
                    if check_status == "DOING":
                        check_status = "ERROR"

                if check_status == "ERROR":
                    log.error("Failed to restore One-Box %s: %s" % (str(onebox_id), str(check_status)))

                    # instanceDict = {}
                    # instanceDict['onebox_type'] = onebox_type
                    #
                    # com_dict = {}
                    # com_dict['onebox_type'] = onebox_type
                    # com_dict['action_type'] = ActionType.PROVS
                    # com_dict['nsr_data'] = instanceDict
                    # com_dict['action_status'] = NSRStatus.ERR
                    # com_dict['server_dict'] = update_server_dict
                    # com_dict['server_status'] = SRVStatus.ERR
                    # com_dict['wf_Odm'] = odm
                    #
                    # orch_comm.getFunc('update_nsr_status', com_dict)
                    # com_dict.clear()

                    except_msg = "Failed to restore One-Box : response error = ERROR"
                    # raise Exception(except_msg)
                    return -500, except_msg

                return 200, "OK"

    def new_nsr_vnf_proc(self, rlt_dict):

        CONST_APP_ACCID = "APARM_appid"
        CONST_APP_ACCID_NONE = "-"

        for vnf in rlt_dict['vnfs']:
            if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
                log.debug("[HJC] Skip composing web URL for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))

                vnf['deploy_info'] = "GiGA Office"

                for vm in vnf['vdus']:
                    web_url_fullpath = None
                    web_url_type = None
                    web_url_config = vm.get('web_url')
                    log.debug("Web URL Config: %s" % str(web_url_config))

                    if web_url_config:
                        try:
                            web_url_ip = web_url_config.get('ip_addr', "NotGiven")
                            log.debug("[HJC] Web URL IP Addr = %s" % str(web_url_ip))

                            # TODO: check web_url_ip is valid IP address (ver 4)
                            if web_url_ip == 'NotGiven':
                                log.debug("Web URL: Cannot compose URL Full Path because get a valid IP Address")
                                continue

                            web_url_fullpath = web_url_config['protocol'] + "://" + web_url_ip
                            if web_url_config.get('port') is not None and web_url_config['port'] > 0:
                                web_url_fullpath += ":" + str(web_url_config['port'])
                            if web_url_config.get('resource', "NotGiven") != "NotGiven":
                                web_url_fullpath += web_url_config['resource']

                            web_url_type = web_url_config.get('type', "main")
                        except KeyError as e:
                            log.exception("Error while composing VDU Web URL. KeyError: " + str(e))
                            web_url_fullpath = None
                    if web_url_fullpath:
                        log.debug("Web URL Full Path: %s" % web_url_fullpath)
                        vm['weburl'] = web_url_fullpath
                        if web_url_type == 'main':
                            vnf['weburl'] = web_url_fullpath
            else:
                vnf['deploy_info'] = "GiGA One-Box"
                # web account id from parameter value
                vnf['webaccount'] = vnf.get('app_id', CONST_APP_ACCID_NONE)
                # log.debug("[HJC] Web Account ID: %s" % str(vnf['webaccount']))

                if vnf['webaccount'] == CONST_APP_ACCID_NONE:
                    # log.debug("[HJC] get Web Account ID from parameter value")
                    for param in rlt_dict['parameters']:
                        target_param_name = CONST_APP_ACCID + "_" + vnf['name']
                        if param['name'] == target_param_name:
                            vnf['webaccount'] = param.get('value', CONST_APP_ACCID_NONE)
                            # log.debug("[HJC] Web Account ID from parameter value %s" % vnf['webaccount'])
                            break

                for vm in vnf['vdus']:
                    web_url_fullpath = None
                    web_url_type = None
                    web_url_config = vm.get('web_url')
                    log.debug("Web URL Config: %s" % str(web_url_config))

                    if web_url_config:
                        try:
                            web_url_ip = web_url_config.get('ip_addr', "NotGiven")
                            if web_url_ip == 'NotGiven':
                                log.debug("Web URL: Cannot compose URL Full Path because IP Address is NotGiven")
                                continue
                            elif web_url_ip.find("PARM_") >= 0 or web_url_ip.find("ROUT_") >= 0:
                                for param in rlt_dict['parameters']:
                                    if param.get('name').find(web_url_ip) >= 0:
                                        web_url_ip = param.get('value')
                                        break
                            elif web_url_ip.find("PORT_") >= 0:
                                # log.debug("[HJC] get web url ip from CP of %s" % str(web_url_ip))
                                if 'cps' in vm:
                                    for cp in vm['cps']:
                                        if cp.get('name') == web_url_ip:
                                            web_url_ip = cp.get('ip')
                                            log.debug("[HJC] web_url_ip = %s" % str(web_url_ip))
                                            break
                            else:
                                log.debug("Web URL IP Addr = %s" % str(web_url_ip))

                            # TODO: check web_url_ip is valid IP address (ver 4)
                            if web_url_ip == 'NotGiven':
                                log.debug("Web URL: Cannot compose URL Full Path because get a valid IP Address")
                                continue

                            if web_url_ip is None:
                                web_url_ip = rlt_dict.get('main_ip_addr')

                            web_url_fullpath = web_url_config.get('protocol') + "://" + web_url_ip + ":" + str(web_url_config.get('port'))
                            if web_url_config.get('resource', "NotGiven") != "NotGiven":
                                web_url_fullpath += web_url_config.get('resource')

                            web_url_type = web_url_config.get('type', "main")
                        except KeyError as e:
                            log.exception("Error while composing VDU Web URL. KeyError: " + str(e))
                            web_url_fullpath = None
                    if web_url_fullpath:
                        log.debug("Web URL Full Path: %s" % web_url_fullpath)
                        vm['weburl'] = web_url_fullpath
                        if web_url_type == 'main':
                            vnf['weburl'] = web_url_fullpath

            if 'report' in vnf:
                for report in vnf['report']:
                    log.debug("[HJC] VNF Name: %s, Report: %s" % (vnf['name'], str(report)))
                    report['value'] = report['data_provider']
                    if report['data_provider'].find("PARM_") >= 0:
                        for param in rlt_dict['parameters']:
                            if param['name'] == report['data_provider']:
                                log.debug("[HJC] %s'value found: %s" % (report['data_provider'], param['value']))
                                report['value'] = param['value']
                                break

            if 'ui_action' in vnf:
                for action in vnf['ui_action']:
                    log.debug("[HJC] VNF Name: %s, UI_Action: %s" % (vnf['name'], str(action)))

        return 200, "OK"


    def new_nsr_db_proc(self, rlt_dict, instance_scenario_name, instance_scenario_description):

        result, instance_id = orch_dbm.insert_nsr_as_a_whole(instance_scenario_name, instance_scenario_description, rlt_dict)

        if result < 0:
            log.error("[Provisioning][NS]  : Error, failed to insert DB records %d %s" % (result, instance_id))
            # error_txt = "recordingDB", "Failed to insert DB Records %d %s" %(result, str(instance_id))

            return result, instance_id

        # # update license info
        # global global_config
        # if global_config.get("license_mngt", False):
        #     for vnf in rlt_dict['vnfs']:
        #         if vnf.get("nfmaincategory", "NONE") == "GiGA Office":
        #             log.debug("[HJC] Skip composing web URL for %s because its category is %s" % (vnf['name'], vnf.get("nfmaincategory")))
        #             continue
        #
        #         license_update_info = {'nfseq': vnf['nfseq']}
        #         log.debug("[HJC] update license %s with nfseq %s" % (vnf.get('license'), str(license_update_info)))
        #         self.update_license(vnf.get('license'), license_update_info)

        # calculate internal parameter values
        # vnf_list = []
        # for vnf in rlt_dict['vnfs']:
        #    vnf_list.append(vnf['name'])

        # iparm_result, iparm_content = _compose_nsr_internal_params(vnf_list, rlt_dict['parameters'])
        # if iparm_result < 0:
        #    log.error("Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content))
        #    return iparm_result, "Failed to compose internal parameter values: %d %s" % (iparm_result, iparm_content)

        rlt_dict['nsseq'] = instance_id
        orch_dbm.insert_nsr_params(rlt_dict['nsseq'], rlt_dict['parameters'])

        return 200, instance_id


    def _nsr_delete_vm(self, delete_dict):

        # onebox-agent
        result, ob_agents = 1, delete_dict.get('ob_agents')

        server_id = delete_dict.get('serverseq')
        onebox_type = delete_dict.get('onebox_type')
        onebox_id = delete_dict.get('onebox_id')
        obagent_base_url = delete_dict.get('obagent_base_url')
        update_server_dict = delete_dict.get('update_server_dict')
        odm = delete_dict.get('odm')
        orch_comm = delete_dict.get('orch_comm')
        e2e_log = delete_dict.get('e2e_log')

        if result < 0 or result > 1:
            log.error("Error. Invalid DB Records for the One-Box Agent: %s" % str(server_id))
            log.debug("Error. Invalid DB Records for the One-Box Agent: %s" % str(server_id))
            # raise Exception("Failed to OneBox Agent Connection")
            return -500, "Failed to OneBox Agent Connection"
        else:
            log.debug('[ob_agents] 프로비저닝 시작')

            del_dict = {}
            del_dict['onebox_id'] = onebox_id
            del_dict['obagent_base_url'] = obagent_base_url

            log.debug('del_dict = %s' % str(del_dict))

            del_result, del_content = ob_agents.delete_arm(del_dict)

            if del_result < 0:
                result = del_result
                log.error("Failed to restore One-Box %s: %d %s" % (onebox_id, del_result, del_content))

                # instanceDict = {}
                # instanceDict['onebox_type'] = onebox_type
                #
                # com_dict = {}
                # com_dict['onebox_type'] = onebox_type
                # com_dict['action_type'] = ActionType.DELNS
                # com_dict['nsr_data'] = instanceDict
                # com_dict['action_status'] = NSRStatus.ERR
                # com_dict['server_dict'] = update_server_dict
                # com_dict['server_status'] = SRVStatus.ERR
                # com_dict['wf_Odm'] = odm
                #
                # orch_comm.getFunc('update_nsr_status', com_dict)
                # com_dict.clear()

                # raise Exception(prv_content)
                return -500, del_content

            if e2e_log:
                e2e_log.job('Call API of One-Box Agent: Restore One-Box', CONST_TRESULT_SUCC, tmsg_body=None)

            # 5-3 Wait for Restoring One-Box
            log.debug("[_RESTORE_ONEBOX_THREAD - %s] Completed to send restore command to the One-Box Agent : %s" % (onebox_id, str(del_content)))
            if del_content['status'] == "DOING":
                action = "prov"
                trial_no = 1
                pre_status = "UNKNOWN"

                log.debug("[_RESTORE_ONEBOX_THREAD - %s] Wait for restore One-Box by Agent" % onebox_id)
                time.sleep(10)

                check_status = ""

                trial_max_no = 5
                while trial_no < trial_max_no:
                    log.debug("[_RESTORE_ONEBOX_THREAD - %s] Checking the progress of restore (%d):" % (onebox_id, trial_no))

                    # One-Box Agent 진행 상태 조회
                    req_dict = {}
                    req_dict['onebox_id'] = onebox_id
                    req_dict['obagent_base_url'] = obagent_base_url
                    req_dict['order'] = 'D'

                    result, check_status = self._status_onebox_agent_progress(ob_agents, action, req_dict)
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

                log.debug('trial_no = %s, check_status = %s' % (str(trial_no), str(check_status)))

                # 30번 상태체크 후에도 정상 응답('DONE', 'ERROR')이 없어 'DOING'인 경우 'ERROR' 처리
                if trial_no == trial_max_no:
                    if check_status == "DOING":
                        check_status = "ERROR"

                if check_status == "ERROR":
                    log.error("Failed to restore One-Box %s: %s" % (str(onebox_id), str(check_status)))

                    # instanceDict = {}
                    # instanceDict['onebox_type'] = onebox_type
                    #
                    # com_dict = {}
                    # com_dict['onebox_type'] = onebox_type
                    # com_dict['action_type'] = ActionType.PROVS
                    # com_dict['nsr_data'] = instanceDict
                    # com_dict['action_status'] = NSRStatus.ERR
                    # com_dict['server_dict'] = update_server_dict
                    # com_dict['server_status'] = SRVStatus.ERR
                    # com_dict['wf_Odm'] = odm
                    #
                    # orch_comm.getFunc('update_nsr_status', com_dict)
                    # com_dict.clear()

                    except_msg = "Failed to restore One-Box : response error = ERROR"
                    # raise Exception(except_msg)
                    return -500, except_msg

                return 200, "OK"

    def update_license(self, license, update_info):
        result, target_license = self.get_license_of_value(license)
        if result < 0:
            log.error("Failed to get License Data: %d, %s" % (result, target_license))
            return -HTTP_Internal_Server_Error, "Failed to get license data from DB"
        elif result == 0:
            return -HTTP_Not_Found, "No license found for the VNF "

        if 'nfseq' in update_info:
            target_license['nfseq'] = update_info['nfseq']
        if 'nfcatseq' in update_info:
            target_license['nfcatseq'] = update_info['nfcatseq']
        if 'status' in update_info:
            target_license['status'] = update_info['status']

        result, content = self._update_license(target_license)
        if result < 0:
            log.error("failed to update license info: %d %s" % (result, str(content)))

        return result, content

    def get_license_of_value(self, value):
        filter_dict = {'value': value}

        result, data = orch_dbm.get_license_pool(filter_dict)
        if result < 0:
            log.error("Failed to get License Data: %d, %s" % (result, data))
        elif result == 0:
            return -HTTP_Not_Found, "No License Found"

        return result, data[0]

    def _update_license(self, license_info):
        result, data = orch_dbm.update_license_pool(license_info)

        return result, data

    def _new_nsr_check_param(self, vim_id, scenarioDict_parameters, params):
        """
        Provision시 필요한 Parameter 값의 유효성 체크
        매개변수 scenarioDict_parameters는 회선 이중화 관련 WAN 사용 정보가 정리된 것(WAN 4개 중 사용하지 않는 것은 제거처리)으로 전제한다.
        :param mydb:
        :param vim_id:
        :param scenarioDict_parameters:
        :param params:
        :return:
        """
        log.debug("[HJC] Params: %s" % str(params))

        if params is None:
            log.error("Failed to NS Provisioning: Parameters are not given")
            return -HTTP_Bad_Request, "Failed to NS Provisioning: Parameters are not given"

        if params == "":
            log.warning("No Parameter Value Given")
            return 200, "OK"

        arg_dict = {}
        arg_list = params.split(';')
        for arg in arg_list:
            arg_dict[arg.split('=')[0]] = arg.split('=')[1]

        for param in scenarioDict_parameters:

            param['value'] = arg_dict.get(param['name'], 'none')

            if param['category'] == 'vnf_template' or param['category'] == 'ns_template':
                if param['value'] == 'none':
                    param_desc_list = param['description'].split("__")
                    log.debug("[*****HJC*******] Param Desc List: %s" % str(param_desc_list))
                    if param_desc_list[0] != "NONE" and param_desc_list[1] != "NONE":
                        error_msg = "No argument for the param: %s %s" % (param['name'], param['category'])
                        log.error("[Provisioning][NS]  : Error, " + error_msg)
                        return -HTTP_Bad_Request, error_msg

                # check image value
                if param['name'].find("imageId") >= 0:
                    check_result = False
                    log.debug("check the param, %s = %s" % (str(param['name']), str(param['value'])))
                    vi_result, vi_content = orch_dbm.get_vim_images(vim_id)

                    if vi_result < 0:
                        error_msg = "Internal Error: Cannot get VIM Image Info %d %s" % (vi_result, str(vi_content))
                        log.error("[Provisioning][NS]  : Error, " + error_msg)
                        return -HTTP_Internal_Server_Error, error_msg

                    if af.check_valid_uuid(param['value']):
                        # convert to name
                        for c in vi_content:
                            if c['uuid'] == param['value']:
                                param['value'] = c['vimimagename']
                                log.debug("the param, %s, value is changed to %s" % (str(param['name']), str(param['value'])))
                                check_result = True
                                break
                    else:
                        # check if there is vim-image
                        if vi_content:
                            for c in vi_content:
                                if c['vimimagename'] == param['value']:
                                    log.debug("found the vim image of name = %s" % str(param['value']))
                                    check_result = True
                                    break

                    check_result = True

                    if not check_result:
                        error_msg = "Invalid Value for %s: Need Image Name or UUID" % str(param['name'])
                        log.error("[Provisioning][NS]  : Error, " + error_msg)
                        return -HTTP_Bad_Request, error_msg

                if param['name'].find("FixedIp") >= 0:
                    log.debug("check the param, %s = %s" % (str(param['name']), str(param['value'])))
                    if not af.check_valid_ipv4(param['value']):
                        error_msg = "Invalid Value for %s: Need IPv4 Address" % str(param['name'])
                        log.error("[Provisioning][NS]  : Error, " + error_msg)
                        return -HTTP_Bad_Request, error_msg

            # Check GW IP Validation
            if param['name'].find('CPARM_defaultGw') >= 0 and (param['value'] == 'none' or param['value'] == 'NA'):
                wan_kind = ["R1", "R2", "R3"]
                r_kind = "_"
                for wk in wan_kind:
                    if param['name'].find(wk) >= 0:
                        r_kind = wk
                        break

                for ag in arg_list:
                    if ag.find("redType" + r_kind) >= 0 and ag.find("STATIC") >= 0:
                        error_msg = "Invalid GW IP Address for WAN: %s - %s" % (param['name'], param['value'])
                        log.error("[Provisioning][NS]  : Error, " + error_msg)
                        return -HTTP_Bad_Request, error_msg
                    elif ag.find("redType" + r_kind) >= 0 and ag.find("DHCP") >= 0:
                        log.debug("[Provisioning][NS] Red IP Alloc Type is DHCP")
                        break

        return 200, "OK"

    def new_nsr_check_license(self, vnf_list):
        global global_config
        if not global_config.get("license_mngt", False):
            return 200, "OK"

        for vnf in vnf_list:
            result, license_info = self.get_license_available(vnf.get('license_name'))
            if result <= 0:
                log.warning("Failed to get VNF License for %s %s" % (vnf['name'], vnf['license_name']))
                # TEMP
                # vnf['license'] = af.create_uuid()
                return -HTTP_Internal_Server_Error, "Failed to get VNF License for %s %s" % (vnf['name'], vnf['license_name'])
            else:
                vnf['license'] = license_info['value']
                result, data = self.take_license(license_info)
                log.debug("The Result of taking a license: %d %s" % (result, str(data)))

            log.debug("VNF %s uses the license %s" % (vnf['name'], vnf['license']))

        return 200, "OK"

    def get_license_available(self, condition):
        result, data = self.get_license_list(condition)
        if result < 0:
            log.error("Failed to get License Data: %d, %s" % (result, data))
            return -HTTP_Internal_Server_Error, "Failed to get license data from DB"
        elif result == 0:
            return -HTTP_Not_Found, "No license found for the VNF "

        for lk in data:
            if lk['status'] == LicenseStatus.AVAIL:
                return 200, lk

        return -HTTP_Not_Found, "No avaiable license found"

    def take_license(self, license_info):
        license_info['status'] = LicenseStatus.USED

        return self._update_license(license_info)


    def get_license_list(self, condition=None):
        filter_dict = {}
        if condition:
            if type(condition) is int or type(condition) is long:
                filter_dict['nfcatseq'] = condition
            elif type(condition) is str and condition.isdigit():
                filter_dict['nfcatseq'] = condition
            elif type(condition) is str:
                log.debug("[HJC] get_license_list condition 3 = %s" % str(condition))
                filter_dict['name'] = condition
            else:
                log.error("Invalid Identifier: %s, Use NFCatalog Seq." % str(condition))
                return -HTTP_Bad_Request, "Invalid Identifier: Use NFCatalog Seq."

        result, data = orch_dbm.get_license_pool(filter_dict)
        if result < 0:
            log.error("Failed to get License Data: %d, %s" % (result, data))
        elif result == 0:
            return -HTTP_Not_Found, "No License Found"

        return result, data

    def _delete_nsr_GigaOffice(self, vnf_dict, server_id, nsr_id, e2e_log=None):
        if vnf_dict is None:
            log.warning("No VNF Info Given")
            return -HTTP_Bad_Request, "No VNF Info"

        # log.debug("[HJC] IN with %s" % str(vnf_dict))
        try:
            if vnf_dict['name'].find("Storage"):
                log.debug("[HJC] GiGA Storage")
                # Get Quota ID
                quota_id = None
                p_result, p_content = orch_dbm.get_nsr_params(nsr_id)
                if p_result > 0:
                    for param in p_content:
                        if param['name'].find("quotaid_GiGA-Storage") >= 0:
                            quota_id = param['value']
                            break

                # Get GiGA-Storage
                mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_STORAGE)

                if quota_id:
                    result, content = mygo.finish_storage(quota_id)
                else:
                    result, content = mygo.finish_storage()

                if result < 0:
                    log.error("failed to finish GiGA Storage: %d %s" % (result, content))
                    return result, content
                log.debug("[HJC] SDN Switch")
                mygo = goconnector.goconnector("GOName", BASE_URL_SDN_SWITCH)
                result, content = mygo.finish_sdnswitch()
                if result < 0:
                    log.error("failed to finish SDN Switch: %d %s" % (result, content))
                    return result, content
            elif vnf_dict['name'].find("PC"):
                log.debug("[HJC] GiGA PC")
                mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_PC)
                result, content = mygo.finish_pc()
                if result < 0:
                    log.error("failed to finish GiGA PC: %d %s" % (result, content))
                    return result, content
            elif vnf_dict['name'].find("Server"):
                log.debug("[HJC] GiGA Server")
                mygo = goconnector.goconnector("GOName", BASE_URL_GIGA_SERVER)
                result, content = mygo.finish_server()
                if result < 0:
                    log.error("failed to finish GiGA Server: %d %s" % (result, content))
                    return result, content
            else:
                log.warning("Not supported GiGA-Office Solution")

        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -500, "Exception: %s" % str(e)

        return 200, "OK"