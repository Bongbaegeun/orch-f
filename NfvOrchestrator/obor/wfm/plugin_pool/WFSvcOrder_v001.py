# -*- coding: utf-8 -*-

from wfm.plugin_spec.WFSvcOrderSpec import WFSvcOrderSpec

import requests
import json
import sys
import time
import uuid as myUuid
from httplib import HTTPException
from requests.exceptions import ConnectionError

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

import db.dba_manager as orch_dbm

from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

from engine.server_status import SRVStatus
from engine.action_status import ACTStatus
# from image_status import ImageStatus
from engine.action_type import ActionType

ORDER_TYPE_OB_NEW    = "ORDER_OB_NEW"
ORDER_TYPE_OB_UPDATE = "ORDER_OB_UPDATE"
ORDER_TYPE_OB_REMOVE = "ORDER_OB_REMOVE"


class WFSvcOrder(WFSvcOrderSpec):

    def get_version(self):
        log.debug("IN get_version()")
        return 1, "v0.0.1"

    # 함수 생성시마다 spec, manager 까지 수정할 필요없게 하기 위한 컨트롤 함수
    # def getFunc(self, funcNm=None, data_dict=None):
    #     log.debug('[Common] funcNm = %s' % str(funcNm))
    #
    #     if funcNm is not None:
    #         result, data = getattr(self, funcNm)(data_dict)
    #         return result, data


    # order 등록
    def add_service_order(self, req_info, plugins):
        log.debug('[WFSvcOrder] add_service_order Start............')

        log.debug('[WFSvcOrder] req_info : %s' %str(req_info))

        # common plugin 사용
        orch_comm = plugins.get('orch_comm')

        # Step 1. Check input data

        # Step 2. Create or Update Customer Info
        customer_seq = -1
        customer_result, customer_data = orch_dbm.get_customer_ename(req_info['customer']['customer_eng_name'])

        if customer_result < 0:
            log.error("[WFSvcOrder] add_service_order(): failed to get Customer info %d %s" % (customer_result, customer_data))
            return customer_result, customer_data
        elif customer_result == 0:
            log.debug("[WFSvcOrder] New Customer: %s" % str(req_info['customer']))

            customer_dict = {"customername": req_info['customer']['customer_name'], "customerename": req_info['customer']['customer_eng_name']}
            nc_result, nc_id = orch_dbm.insert_customer(customer_dict)

            if nc_result < 0:
                log.error("failed to insert customer info into DB: %d %s" % (nc_result, nc_id))
                return nc_result, nc_id

            customer_seq = nc_id

            # TODO: 2-1. Mapping Customer to All superusers(accounts)
            mp_result, mp_content = orch_dbm.insert_user_mp_customer(customer_seq)

        else:
            log.debug("Existing Customer: %s" % str(customer_data))

            customer_seq = customer_data['customerseq']
            # TODO: update Customer Info

        # Step 3. Create or Update Customer Office Info
        office_seq = -1
        if 'office' not in req_info:
            req_info['office'] = {"office_name": "본사"}

        office_result, office_data = orch_dbm.get_customeroffice_ofcustomer(customer_seq)

        if office_result < 0:
            log.error("failed to get customer office info from DB: %d %s" % (office_result, office_data))
            return office_result, office_data
        elif office_result > 0:
            log.debug("check existing office info")

            for office in office_data:
                officename = office['officename']
                so_officename = req_info['office']['office_name']

                # if type(officename) == str:
                #     officename = officename.decode("utf-8")
                # if type(so_officename) == str:
                #     so_officename = so_officename.decode("utf-8")

                if officename == so_officename:
                    log.debug("Existing Office: %s" % req_info['office']['office_name'])

                    office_seq = office['officeseq']
                    break

        if office_seq < 0:
            log.debug("New Customer Office: %s" % str(req_info['office']))

            office_dict = {"officename": req_info['office']['office_name'], 'customerseq': customer_seq}

            log.debug("[HJC] DB Insert DATA for customer office: %s" % str(office_dict))

            no_result, no_id = orch_dbm.insert_customeroffice(office_dict)

            if no_result < 0:
                log.error("failed to insert customer office into DB: %d %s" % (no_result, no_id))
                return no_result, no_id
            office_seq = no_id

        # Step 4. Create or Update One-Box Info
        onebox_seq = -1
        onebox_status = SRVStatus.IDLE

        filter_dict = {"onebox_id": req_info['one-box']['onebox_id']}
        filter_dict['onebox_type'] = req_info['onebox_type']

        onebox_result, onebox_data = orch_dbm.get_server_filters(filter_dict)

        log.debug('onebox_result = %d, onebox_data = %s' %(onebox_result, str(onebox_data)))

        if onebox_result < 0:
            log.error("failed to get onebox info from DB: %d %s" % (onebox_result, onebox_data))
            return onebox_result, onebox_data

        elif onebox_result == 0:
            if req_info['order_type'] == ORDER_TYPE_OB_REMOVE:
                return 200, "OK"
            else:
                log.debug("New Onebox: %s" % str(req_info['one-box']))

                onebox_dict = {
                    "servername": req_info['one-box']['onebox_id'],
                    "onebox_id": req_info['one-box']['onebox_id'],
                    "onebox_flavor": req_info['one-box'].get('model', "No Info")
                }

                if 'ob_service_number' in req_info['one-box']:
                    onebox_dict['ob_service_number'] = req_info['one-box']['ob_service_number']

                onebox_dict['status'] = SRVStatus.IDLE
                onebox_dict['state'] = "NOTSTART"
                onebox_dict['nfmaincategory'] = "Server"

                if 'nfsubcategory' in req_info['one-box']:
                    onebox_dict['nfsubcategory'] = req_info['one-box']['nfsubcategory']
                else:
                    onebox_dict['nfsubcategory'] = "One-Box"

                onebox_dict['customerseq'] = customer_seq
                onebox_dict['officeseq'] = office_seq
                # onebox_dict['orgnamescode'] = "목동"      # original code
                # 하드코딩으로 '목동'으로 썼지만 오더 등록시 받은 값으로 쓰도록 변경
                onebox_dict['orgnamescode'] = req_info['office']['office_name']

                nob_result, nob_id = orch_dbm.insert_server(onebox_dict)
                if nob_result < 0:
                    log.error("failed to insert onebox into DB: %d %s" % (nob_result, nob_id))
                    return nob_result, nob_id
                onebox_seq = nob_id
        else:
            log.debug("Exsiting Onebox: %s" % str(onebox_data[0]))
            onebox_seq = onebox_data[0]['serverseq']
            onebox_status = onebox_data[0]['status']

            if req_info['order_type'] == ORDER_TYPE_OB_REMOVE:
                if onebox_status == SRVStatus.ERR and onebox_data[0].get('nsseq') is None:
                    onebox_status = SRVStatus.HWE
            elif req_info['order_type'] == ORDER_TYPE_OB_UPDATE:
                # update_onebox_dict = {"serverseq": onebox_seq, "status":"N__UPDATE"}
                # orch_dbm.update_server_status(mydb, update_onebox_dict)
                pass

        # Step 4-2. Noti to Oder Manager
        server_status = onebox_status

        try_cnt = 3
        while server_status == SRVStatus.OOS:
            try_cnt -= 1
            if try_cnt < 0:
                return -500, "The status of server is out of service. Try again. If it still doesn't work, ask the manager."
            time.sleep(7)
            result, ob_data = orch_dbm.get_server_id(onebox_seq)
            server_status = ob_data["status"]

        if server_status == SRVStatus.IDLE:
            server_status = SRVStatus.LWT

        server_update_dict = {'serverseq': onebox_seq, 'status': server_status, 'onebox_id': req_info['one-box']['onebox_id'], "order_type": req_info['order_type']}
        # us_result, us_data = update_server_status(mydb, server_update_dict)

        com_dict = {}
        com_dict['server_dict'] = server_update_dict
        com_dict['is_action'] = False
        com_dict['e2e_log'] = None
        com_dict['action_type'] = None
        com_dict['wf_Odm'] = plugins.get('wf_Odm')

        us_result, us_data = orch_comm.getFunc('update_server_status', com_dict)
        com_dict.clear()

        if us_result < 0:
            log.error("failed to inform one-box's status to Order Manager: %d %s" % (us_result, us_data))

        # Step 5. Create or Update One-Box Network Line Info
        if 'net_line_list' in req_info['one-box'] and len(req_info['one-box']['net_line_list']) > 0:
            old_nline_list = []
            nline_result, nline_data = orch_dbm.get_onebox_line_ofonebox(onebox_seq)
            if nline_result < 0:
                log.warning("failed to get network line info of the One-Box: %s" % req_info['one-box']['onebox_id'])
            elif nline_result > 0:
                old_nline_list = nline_data

            for nline in req_info['one-box']['net_line_list']:
                log.debug("Old Onebox Lines: %s, new line: %s" % (str(old_nline_list), str(nline)))
                is_existing_nline = False
                for old_line in old_nline_list:
                    if old_line.get("line_number") == nline:
                        log.debug("Existing Network Line: %s" % nline)
                        is_existing_nline = True
                        break

                if not is_existing_nline:
                    nline_dict = {"line_number": nline, "name": nline, "display_name": nline, "serverseq": onebox_seq}
                    nl_result, nl_id = orch_dbm.insert_onebox_line(nline_dict)
                    if nl_result < 0:
                        log.warning("failed to insert network line info into DB: %d %s" % (nl_result, nl_id))

        return 200, "OK"


    # One-Box Update :
    def update_onebox_info(self, req_info, plugins):
        log.debug('[WFSvcOrder] update_onebox_info Start............')
        log.debug('[WFSvcOrder] req_info : %s' % str(req_info))

        onebox_id = req_info.get('onebox_id')

        onebox_result, onebox_data = orch_dbm.get_server_filters({"onebox_id": onebox_id, 'onebox_type':req_info.get('onebox_type')})

        if onebox_result < 0:
            log.error("failed to get onebox info from DB: %d %s" % (onebox_result, onebox_data))
            return onebox_result, onebox_data
        elif onebox_result == 0:
            log.warning("Not found One-Box: %s" % onebox_id)

            if req_info.get("order_handle") == "cancel" and req_info.get('order_type') == ORDER_TYPE_OB_NEW:
                return 200, "Not found: One-Box of %s" % onebox_id
            elif req_info.get("order_handle") == "stop" and req_info.get('order_type') == ORDER_TYPE_OB_NEW:
                return 200, "Not found: One-Box of %s" % onebox_id
            else:
                return -HTTP_Not_Found, "Not found: One-Box of %s" % onebox_id

        # WF : server_manager load
        req_info['serverseq'] = onebox_data[0]['serverseq']

        # TODO: Update One-Box Info
        # if update_info['one-box'].get('ob_service_number') is not None and update_info['one-box']['ob_service_number'] != onebox_data[0].get('ob_service_number'):
        #    update_dict_onebox = {'serverseq': onebox_data[0]['serverseq'], 'ob_service_number': update_info['one-box']['ob_service_number']}

        # Remove
        if req_info.get('order_type') == ORDER_TYPE_OB_REMOVE:

            if req_info.get("order_handle") == "cancel":
                log.debug("order_handle: cancel, order_type: ORDER_OB_REMOVE : process undefined")
                return 200, "OK"
            elif req_info.get("order_handle") == "stop":
                log.debug("order_handle: stop, order_type: ORDER_OB_REMOVE : process undefined")
                return 200, "OK"

            # TODO : 이 부분이 nsr 모니터 및 ns 정보 remove, 다시 확인 필요, 일단 주석
            if req_info.get('onebox_type') == "KtPnf":
                # PNF type

                # PNF 의 경우 NSR 이 없지만 order manager에 상태값 변경 이슈로 인하여 형태만 취한다
                # WF : server_manager load
                # wf_nsr_manager = wfm_nsr_manager.nsr_manager(req_info)
                wf_nsr_manager = plugins.get('wf_nsr_manager')

                req_info['nsseq'] = onebox_data[0]['nsseq']
                dn_result, dn_content = wf_nsr_manager.delete_nsr(req_info, plugins)
                if dn_result < 0:
                    log.error("failed to delete NSR of the One-Box: %d %s" % (dn_result, dn_content))
                    return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. One-Box 상태를 확인해 주세요."
            else:
                # Other type One-Box

                if onebox_data[0].get('nsseq') is not None:
                    if onebox_data[0].get('nfsubcategory') == 'KtArm':
                        # Arm-Box
                        del_dict = {}
                        del_dict['onebox_type'] = onebox_data[0].get('nfsubcategory')
                        del_dict['nsr'] = onebox_data[0]['nsseq']
                        del_dict['only_orch'] = False
                        del_dict['need_stop_monitor'] = True
                        del_dict['use_thread'] = False
                        del_dict['tid'] = None
                        del_dict['tpath'] = ""
                        del_dict['force_flag'] = True

                        wf_nsr_arm_manager = plugins.get('wf_nsr_arm_manager')
                        dn_result, dn_content = wf_nsr_arm_manager.delete_nsr(del_dict, plugins)
                    else:
                        # dn_result, dn_content = delete_nsr(onebox_data[0]['nsseq'], need_stop_monitor=True, use_thread=False, tid=None, tpath="", force_flag=True)
                        dn_result, dn_content = 200, "OK"

                    if dn_result < 0:
                        log.error("failed to delete NSR of the One-Box: %d %s" % (dn_result, dn_content))
                        return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. One-Box 상태를 확인해 주세요."

            # 기존 소스 주석
            # del_result, del_data = delete_server(onebox_data[0]['serverseq'])

            managers = {}
            managers['orch_comm'] = plugins.get('orch_comm')
            managers['wf_server_manager'] = plugins.get('wf_server_manager')
            managers['wf_monitorconnector'] = plugins.get('wf_monitorconnector')
            managers['wf_Odm'] = plugins.get('wf_Odm')

            if req_info.get('onebox_type') == "KtPnf":
                wf_server_manager = plugins.get('wf_server_manager')
                del_result, del_data = wf_server_manager.delete_server(req_info, managers)
            else:
                wf_server_arm_manager = plugins.get('wf_server_arm_manager')
                del_result, del_data = wf_server_arm_manager.delete_server(req_info, managers)

            if del_result < 0:
                log.error("failed to delete One-Box from DB: %d %s" % (del_result, del_data))
                return del_result, del_data

            # 고객삭제 여부 처리
            if req_info.get("is_customer_delete", False):
                # 고객이 다른 One-Box를 사용하고 있는지 체크하고 없으면 삭제.
                result, contents = orch_dbm.get_server_filters({"customerseq": onebox_data[0]['customerseq'], 'onebox_type':req_info.get('onebox_type')})
                if result < 0:
                    log.error("failed to get server data from DB: %d %s" % (result, contents))
                    return result, contents
                elif result > 0:  # 다른 One-Box를 사용하는 경우
                    return 200, "OTHER"

                # 삭제오더에서 is_customer_delete=True 인 경우 고객을 삭제한다.
                # 삭제되는 고객의 account_id를 Web단으로 넘겨줘야한다. (NMS 삭제처리때문인듯...)
                # account_id 가 존재하는 경우에만 넘겨주고, 없으면 그냥 "OK"를 넘겨주기로 한다.
                account_id = "OK"
                rst_ac, data_ac = orch_dbm.get_account_id_of_customer({"customerseq": onebox_data[0]['customerseq']})
                if rst_ac > 0:
                    account_id = data_ac["account_id"]

                del_result, del_data = orch_dbm.delete_customer(onebox_data[0]['customerseq'])
                if del_result < 0:
                    log.error("failed to delete customer from DB: %d %s" % (del_result, del_data))
                    return del_result, del_data

                return 200, account_id

        else:
            # ORDER_TYPE_OB_NEW OR ORDER_TYPE_OB_UPDATE

            # '취소' 처리
            if req_info.get("order_handle") == "cancel":
                if req_info.get('order_type') == ORDER_TYPE_OB_NEW and onebox_data[0]["status"] == SRVStatus.LWT:

                    ############    상태값 변경 후, 오더매니저에도 상태값 변경을 보내는 부분에서 에러가 남. 일단 주석처리   ##############################
                    # # 서버 삭제 전 상태값 변경 및 order manager 상태값 변경 처리
                    # req_info['customerseq'] = onebox_data[0]['customerseq']
                    # # orch_comm = common_manager.common_manager(req_info)
                    # orch_comm = plugins.get('orch_comm')
                    #
                    # server_update_dict = {'serverseq': onebox_data[0]['serverseq'], 'status': SRVStatus.DSC, 'onebox_id': req_info.get('onebox_id'),
                    #                       "order_type": ActionType.DELNS}
                    #
                    # com_dict = {}
                    # com_dict['server_dict'] = server_update_dict
                    # com_dict['is_action'] = False
                    # com_dict['e2e_log'] = None
                    # com_dict['action_type'] = None
                    # com_dict['wf_Odm'] = plugins.get('wf_Odm')
                    #
                    # us_result, us_data = orch_comm.getFunc('update_server_status', com_dict)
                    # com_dict.clear()
                    ##############################################################################################################################

                    # 서버삭제
                    # del_result, del_data = delete_server(mydb, onebox_data[0]['serverseq'])

                    managers = {}
                    managers['orch_comm'] = plugins.get('orch_comm')
                    managers['wf_server_manager'] = plugins.get('wf_server_manager')
                    managers['wf_monitorconnector'] = plugins.get('wf_monitorconnector')
                    managers['wf_Odm'] = plugins.get('wf_Odm')

                    del_result, del_data = plugins.get('wf_server_manager').delete_server(req_info, managers)

                    if del_result < 0:
                        log.error("failed to delete One-Box from DB: %d %s" % (del_result, del_data))
                        return del_result, del_data

                    # 고객삭제
                    # 고객이 다른 One-Box를 사용하고 있는지 체크하고 없으면 삭제.
                    log.debug('###########      customer delete start           ################################')

                    log.debug('1. get server : customerseq = %s' %str(onebox_data[0]['customerseq']))

                    result, contents = orch_dbm.get_server_filters_wf({"customerseq": onebox_data[0]['customerseq']})
                    if result < 0:
                        log.error("failed to get server data from DB: %d %s" % (result, contents))
                        log.debug("failed to get server data from DB: %d %s" % (result, contents))
                        return result, contents
                    elif result > 0:  # 다른 One-Box를 사용하는 경우
                        log.debug('used other onebox')
                        return 200, "OTHER"


                    log.debug('2. get account id of customer : customerseq = %s' %str(onebox_data[0]['customerseq']))
                    # 삭제되는 고객의 account_id를 Web단으로 넘겨줘야한다. (NMS 삭제처리때문인듯...)
                    # account_id 가 존재하는 경우에만 넘겨주고, 없으면 그냥 "OK"를 넘겨주기로 한다.
                    account_id = "OK"
                    rst_ac, data_ac = orch_dbm.get_account_id_of_customer({"customerseq": onebox_data[0]['customerseq']})
                    if rst_ac > 0:
                        account_id = data_ac["account_id"]

                    log.debug('data_ac = %s' %str(data_ac))

                    log.debug('3. delete customer : customerseq = %s' %str(onebox_data[0]['customerseq']))
                    del_result, del_data = orch_dbm.delete_customer(onebox_data[0]['customerseq'])
                    if del_result < 0:
                        log.error("failed to delete customer from DB: %d %s" % (del_result, del_data))
                        return del_result, del_data

                    return 200, account_id

                elif req_info.get('order_type') == ORDER_TYPE_OB_UPDATE:
                    log.debug("order_handle: cancel, order_type: ORDER_OB_UPDATE : process undefined")

                return 200, "OK"

            # '중단' 처리
            elif req_info.get("order_handle") == "stop":
                if req_info.get('order_type') == ORDER_TYPE_OB_NEW:

                    # 서버상태가 "N__PROVISIONING", "" 이면 중지 안됨.
                    if onebox_data[0]['status'] == SRVStatus.PVS or onebox_data[0]['status'] == SRVStatus.LPV:
                        log.debug("_____ 현재 설치가 진행중. 중지 오더를 수행할 수 없음.")
                        # return 200, "ING"
                        return -HTTP_Internal_Server_Error, "ING"

                    if req_info.get('onebox_type') == "KtPnf":
                        # PNF type

                        # PNF 의 경우 NSR 이 없지만 order manager에 상태값 변경 이슈로 인하여 형태만 취한다
                        # WF : server_manager load
                        # wf_nsr_manager = wfm_nsr_manager.nsr_manager(req_info)
                        wf_nsr_manager = plugins.get('wf_nsr_manager')

                        req_info['nsseq'] = onebox_data[0]['nsseq']

                        managers = {}
                        managers['orch_comm'] = plugins.get('orch_comm')
                        managers['wf_server_manager'] = plugins.get('wf_server_manager')
                        managers['wf_monitorconnector'] = plugins.get('wf_monitorconnector')
                        managers['wf_Odm'] = plugins.get('wf_Odm')

                        result, message = wf_nsr_manager.delete_nsr(req_info, managers)
                        # result, message = delete_nsr(onebox_data[0]['nsseq'], use_thread=False, force_flag=True)
                        if result < 0:
                            log.error("[NBI OUT] Deleting NSR: Error %d %s" % (-result, message))
                            return result, message
                        log.debug("[NBI OUT] Deleting NSR: OK")

                        # # UTM 모니터 stop
                        # req_info['customerseq'] = onebox_data[0]['customerseq']
                        # orch_comm = common_manager.common_manager(req_info)
                        #
                        # dn_result, dn_content = orch_comm.getFunc('stop_nsr_monitor', req_info)
                        #
                        # if dn_result < 0:
                        #     log.error("[NBI OUT] Stop NSR Monitor : Error %d, %s" % (dn_result, str(dn_content)))
                        #     return dn_result, dn_content
                        #
                        # log.debug("[NBI OUT] Stop NSR Monitor : OK")
                    else:
                        # Other type
                        # NS삭제/OB삭제
                        if onebox_data[0]['nsseq'] is not None:

                            if onebox_data[0].get('nfsubcategory') == 'KtArm':
                                # delete_nsr(self, nsr_id, need_stop_monitor=True, only_orch=False, use_thread=True, tid=None, tpath="", force_flag=False):

                                # Arm-Box
                                del_dict = {}
                                del_dict['onebox_type'] = onebox_data[0].get('nfsubcategory')
                                del_dict['nsr'] = onebox_data[0]['nsseq']
                                del_dict['only_orch'] = False
                                del_dict['need_stop_monitor'] = True
                                del_dict['use_thread'] = False
                                del_dict['tid'] = None
                                del_dict['tpath'] = ""
                                del_dict['force_flag'] = True

                                wf_nsr_arm_manager = plugins.get('wf_nsr_arm_manager')
                                result, message = wf_nsr_arm_manager.delete_nsr(del_dict, plugins)
                            else:
                                # result, message = delete_nsr(onebox_data[0]['nsseq'], use_thread=False, force_flag=True)
                                result, message = 200, "OK"

                            if result < 0:
                                log.error("[NBI OUT] Deleting NSR: Error %d %s" % (-result, message))
                                return result, message
                            log.debug("[NBI OUT] Deleting NSR: OK")

                    # del_result, del_data = delete_server(mydb, onebox_data[0]['serverseq'])

                    managers = {}
                    managers['orch_comm'] = plugins.get('orch_comm')
                    managers['wf_server_manager'] = plugins.get('wf_server_manager')
                    managers['wf_monitorconnector'] = plugins.get('wf_monitorconnector')
                    managers['wf_Odm'] = plugins.get('wf_Odm')

                    del_result, del_data = plugins.get('wf_server_manager').delete_server(req_info, managers)

                    if del_result < 0:
                        log.error("failed to delete One-Box from DB: %d %s" % (del_result, del_data))
                        return del_result, del_data
                return 200, "OK"

            # '준공' 처리
            if 'vnf_list' in req_info and len(req_info['vnf_list']) > 0:
                if req_info.get('onebox_type') == "KtPnf":
                    # PNF type
                    pass
                else:
                    # Other type

                    if onebox_data[0].get('nsseq') is None:
                        log.error("The One-Box does not have any VNF installed")
                        return -HTTP_Not_Found, "The One-Box does not have any VNF installed"

                    nsr_result, nsr_data = orch_dbm.get_nsr_id(onebox_data[0]['nsseq'])
                    if nsr_result < 0:
                        log.error("failed to get NSR, VNF Info from DB: %d %s" % (nsr_result, nsr_data))
                        return nsr_result, nsr_data

                    # # 준공정보를 RLT에 저장처리
                    # result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_data["nsseq"])
                    # if result < 0:
                    #     log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
                    #     raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))
                    #
                    # rlt_dict = rlt_data["rlt"]

                    for vnf in nsr_data['vnfs']:
                        update_dict = {"nfseq": vnf['nfseq']}
                        for vnf_info in req_info['vnf_list']:
                            if vnf_info.get('vnfd_name') == vnf['vnfd_name']:
                                if vnf_info.get('service_number') is not None: update_dict['service_number'] = vnf_info['service_number']
                                if vnf_info.get('service_period') is not None: update_dict['service_period'] = vnf_info['service_period']
                                if vnf_info.get('service_start_dttm') is not None: update_dict['service_start_dttm'] = vnf_info['service_start_dttm']
                                if vnf_info.get('service_end_dttm') is not None: update_dict['service_end_dttm'] = vnf_info['service_end_dttm']

                                # for rlt_vnf in rlt_dict["vnfs"]:
                                #     if vnf['vnfd_name'] == rlt_vnf["vnfd_name"]:
                                #         if update_dict.get('service_number'):   rlt_vnf["service_number"] = update_dict['service_number']
                                #         if update_dict.get('service_period'):   rlt_vnf["service_period"] = update_dict['service_period']
                                #         if update_dict.get('service_start_dttm'):   rlt_vnf["service_start_dttm"] = update_dict['service_start_dttm']
                                #         if update_dict.get('service_end_dttm'):   rlt_vnf["service_end_dttm"] = update_dict['service_end_dttm']
                                #         break
                                break

                        update_result, update_data = orch_dbm.update_nsr_vnf(update_dict)

                        if update_result < 0:
                            log.error("failed to update VNF: %d %s" % (update_result, update_data))
                            return update_result, update_data

                    # rlt_data_up = json.dumps(rlt_dict)
                    #
                    # result, rltseq = orch_dbm.update_rlt_data(mydb, rlt_data_up, rlt_seq=rlt_data['rltseq'])
                    # if result < 0:
                    #     log.error("failed to DB Update RLT: %d %s" % (result, rltseq))

                if req_info.get('order_type') == ORDER_TYPE_OB_NEW:
                    # 준공일 업데이트
                    orch_dbm.update_server_delivery_dttm(onebox_data[0]['serverseq'])

            # PNF 준공일 업데이트
            if req_info.get('onebox_type') == "KtPnf":
                # PNF type
                if req_info.get('order_type') == ORDER_TYPE_OB_NEW:
                    # 준공일 업데이트
                    orch_dbm.update_server_delivery_dttm(onebox_data[0]['serverseq'])

        return 200, "OK"

