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

import yaml
import json
import threading
import datetime
import sys
import copy
from tornado.web import RequestHandler

import orch_schemas
import db.orch_db_manager as orch_dbm

from handlers_t.http_response import HTTPResponse
import handler_utils as util

from utils import db_conn_manager as dbmanager
from utils import auxiliary_functions as af
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from engine import serviceorder_manager
from engine import server_manager
from engine.common_manager import _delete_backup_scheduler

global mydb
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()


from connectors import accountconnector


url_base_t="/orch"

OPCODE_CUSTOMER_DELETE = "CUSTOMER_DELETE"
OPCODE_CUSTOMER_GET = "CUSTOMER_GET"
OPCODE_CUSTOMER_POST = "CUSTOMER_POST"
OPCODE_CUSTOMER_ACTION = "CUSTOMER_ACTION"

OPCODE_CUSTOMER_DELETE_MULTI = "CUSTOMER_DELETE_MULTI"
OPCODE_ONEBOX_UPDATE = "ONEBOX_UPDATE"
OPCODE_ONEBOX_UPDATE_SERVICENUMBER = "ONEBOX_UPDATE_SERVICENUMBER"

# get 으로 처리되던 부분을 post로 변경하기 위해 추가
OPCODE_ONEBOX_LIST = "OPCODE_ONEBOX_LIST"

def url(plugins):
    urls = [ (url_base_t + "/customer/([^/]*)", CustomerHandler, dict(opCode=OPCODE_CUSTOMER_ACTION)),
             (url_base_t + "/customer/([^/]*)/delete", CustomerHandler, dict(opCode=OPCODE_CUSTOMER_DELETE)),
             (url_base_t + "/customers/delete", CustomerHandler, dict(opCode=OPCODE_CUSTOMER_DELETE_MULTI)),
             (url_base_t + "/customer", CustomerHandler, dict(opCode=OPCODE_CUSTOMER_GET)),
             (url_base_t + "/order/([^/]*)", ServiceOrderHandler, dict(plugins=plugins)),
             (url_base_t + "/order", ServiceOrderHandler, dict(plugins=plugins)),

             (url_base_t + "/onebox", OneBoxHandler, dict(plugins=plugins)),        # GET
             # (url_base_t + "/onebox", OneBoxHandler, dict(opCode=OPCODE_ONEBOX_LIST, plugins=plugins)),       # POST

             (url_base_t + "/onebox/([^/]*)", OneBoxHandler, dict(plugins=plugins)),

             # change orgnamescode
             (url_base_t + "/onebox/update/([^/]*)", OneBoxHandler, dict(opCode=OPCODE_ONEBOX_UPDATE)),

             # change service number
             (url_base_t + "/onebox/servicenum/([^/]*)/([^/]*)", OneBoxHandler, dict(opCode=OPCODE_ONEBOX_UPDATE_SERVICENUMBER)),
             ]
    return urls

class ServiceOrderHandler(RequestHandler):
    def initialize(self, plugins=None):
        # self.opCode = opCode
        self.plugins = plugins

    def post(self, so_id=None):
        """
        오더(신규/수정/삭제) 처리 API
        오더관리에서 호출
        :param so_id: 현재 사용안함.
        :return: 성공 : +200, 실패 : -value
        """
        log.debug("[HJC] *************************** IN ***************************")

        result, http_content = util.format_in(self.request, orch_schemas.service_order_schema)
        if result < 0:
            self._send_response(result, http_content)
            return

        r = af.remove_extra_items(http_content, orch_schemas.service_order_schema)
        if r is not None:
            log.warning("Warning: remove extra items : %s" % r)

        log.debug("[HJC]   %s" %str(http_content))

        # 기존 소스와 WF 분기, 여기에서만 nfsubcategory 를 받아서 처리한다.(다른 부분은 DB에서 nfsubcategory 받아서 처리)
        if 'nfsubcategory' in http_content['one-box']:
            if http_content['one-box']['nfsubcategory'] == 'One-Box':
                result, data = serviceorder_manager.add_service_order(mydb, http_content)
            else:
                # Work Flow Process
                http_content['onebox_type'] = http_content['one-box']['nfsubcategory']
                # wf_svcorder_manager = wfm_svcorder_manager.svcorder_manager(http_content)
                wf_svcorder_manager = self.plugins.get('wf_svcorder_manager')
                result, data = wf_svcorder_manager.add_service_order(http_content, self.plugins)
        else:
            result, data = serviceorder_manager.add_service_order(mydb, http_content)

        if result < 0:
            self._send_response(result, data)
            return

        log.debug("[HJC] *************************** OUT ***************************")
        self._send_response(result, {"result": data})


    def get(self, so_id=None):
        '''get customer list or details, can use both id or name'''
        if so_id is None or so_id == "all":
            result, content = serviceorder_manager.get_service_order(mydb)
            
            if result < 0:
                data = content
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)
                data={'serviceorder_list' : content}
        else:
            result, content = serviceorder_manager.get_service_order_id(mydb, so_id)
            
            if result < 0:
                data = content
            else:
                af.convert_datetime2str_psycopg2(content)
                data={'serviceorder' : content}
            
        self._send_response(result, data)

    def delete(self, so_id=None):
        '''delete a service order from database, can use both id or name'''
        #if so_id == None:
        #    self._send_response(HTTPResponse.Bad_Request, "No Target")
        #    return
        
        # result, http_content = util.format_in(self.request, orch_schemas.service_order_delete_schema)
        # if result < 0:
        #     self._send_response(result, http_content)
        #     return
        #
        # r = af.remove_extra_items(http_content, orch_schemas.service_order_delete_schema)
        # if r is not None:
        #     log.warning("Warning: remove extra items ", r)
        #
        # result, content = serviceorder_manager.delete_service_order(mydb, http_content)
        #
        # if result < 0:
        #     self.set_status(-result)
        #     data = content
        # else:
        #     data = {"result":"serviceorder " + content + " deleted"}
        #
        # self._send_response(result, data)
        pass

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        self.finish(body)


class CustomerHandler(RequestHandler):

    def __init__(self, application, request, **kwargs):
        self.opCode = None
        super(CustomerHandler, self).__init__(application, request, **kwargs)

    def initialize(self, opCode):
        self.opCode = opCode
        
    def post(self, customer_id=None):

        if self.opCode is not None and str(self.opCode) == OPCODE_CUSTOMER_ACTION:

            result, http_content = util.format_in(self.request, orch_schemas.customer_schema)
            if result < 0:
                self._send_response(result, http_content)
                return

            r = af.remove_extra_items(http_content, orch_schemas.customer_schema)
            if r is not None:
                log.warning("Warning: remove extra items ", r)

            result, data = serviceorder_manager.new_customer(mydb, http_content['customer'])

            if result > 0:
                customer_result, customer_data = orch_dbm.get_customer_id(mydb, data)
                if customer_result < 0:
                    result = customer_result
                    data = customer_data
                else:
                    af.convert_datetime2str_psycopg2(customer_data)
                    data={'customer' : customer_data}

            self._send_response(result, data)

        elif self.opCode is not None and str(self.opCode) == OPCODE_CUSTOMER_DELETE_MULTI:
            result, http_content = util.format_in(self.request, orch_schemas.customer_delete_multi_schema)
            if result < 0:
                self._send_response(result, http_content)
                return

            r = af.remove_extra_items(http_content, orch_schemas.customer_delete_multi_schema)
            if r is not None:
                log.warning("Warning: remove extra items ", r)

            result, data = serviceorder_manager.delete_customers_info(mydb, http_content['customers'])
            if result < 0:
                self._send_response(result, data)
                return

            self._send_response(result, {"result":data})
    
    def get(self, customer_id=None):
        '''get customer list or details, can use both id or name'''
        if customer_id is None or customer_id == "all":
            result, content = orch_dbm.get_customer_list(mydb)
            
            if result < 0:
                data = content
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)
                data={'customer' : content}
        else:
            result, content = orch_dbm.get_customer_id(mydb, customer_id)
            
            if result < 0:
                data = content
            else:
                af.convert_datetime2str_psycopg2(content)
                data={'customer' : content}
            
        self._send_response(result, data)
        

    def delete(self, customer_id=None):
        '''delete a customer from database, can use both id or name'''

        if customer_id is None:
            self._send_response(HTTPResponse.Bad_Request, "No Target")
            return

        log.debug("______ delete customer : %s" % customer_id)
        log.debug("______ self.opCode : %s" % self.opCode)


        if self.opCode is not None and str(self.opCode) == OPCODE_CUSTOMER_DELETE:

            result, content = serviceorder_manager.delete_customerinfo(mydb, customer_id) # customer_ename

            if result <= 0:
                self.set_status(-result)
                data = content
            else:
                data = {"result": content}

            self._send_response(result, data)

        else:

            result, content = serviceorder_manager.delete_customer(mydb, customer_id)

            if result <= 0:
                self.set_status(-result)
                data = content
            else:
                data = {"result":"customer " + content + " deleted"}

            self._send_response(result, data)
    
    def put(self, customer_id = None):
        log.debug("IN")
        
        result, http_content = util.format_in(self.request, orch_schemas.service_order_update_schema)
        if result < 0:
            self._send_response(result, http_content)
            return
        
        r = af.remove_extra_items(http_content, orch_schemas.service_order_update_schema)
        if r is not None: 
            log.warning("Warning: remove extra items ", r)
            
            
        if customer_id is None:
            result = -400
            data = "Need Customer English Name"
        else:
            is_default_process = True

            if 'office' in http_content and len(http_content.get('office')) > 0:
                for office in http_content.get('office'):
                    if 'servername' not in office:
                        continue

                    is_default_process = False
                    break


            if is_default_process:
                log.debug('___________________default process')
                result, data = serviceorder_manager.update_customer_info(mydb, customer_id, http_content)
            else:
                log.debug('___________________new process')
                result, data = serviceorder_manager.update_customer_info_new(mydb, customer_id, http_content)

            if result < 0:
                log.error("failed to update Customer Info: %d %s" %(result, data))
            else:
                data = {"result":"OK"}
        
        self._send_response(result,data)

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

class OneBoxHandler(RequestHandler):
    def initialize(self, opCode=None, plugins=None):
        self.opCode = opCode
        self.plugins = plugins
        
    def post(self, onebox_id = None, kind=None):
        if self.opCode == OPCODE_ONEBOX_UPDATE:
            self._onebox_update(onebox_id)
        elif self.opCode == OPCODE_ONEBOX_UPDATE_SERVICENUMBER:
            # kind : onebox or vnf
            # onebox_id : serverseq or nfseq
            self._onebox_update_servicenum(kind, onebox_id)
        else:
            # 오더 준공 시, One-Box 백업과 NS 백업을 자동 수행 (Thread로 수행)
            log.debug("IN Backup One-box and NSR")

            self._backup_onebox_nsr(onebox_id)


    def get(self, onebox_id = None):
        log.debug("IN")
        arg_onebox_list = self.get_argument("onebox_list")
        log.debug("Requested One-Box: %s" %str(arg_onebox_list))
        if len(arg_onebox_list) == 0:
            result = -400
            data = str(arg_onebox_list)
        else:
            onebox_list = arg_onebox_list.split(",")
            result, data = serviceorder_manager.get_onebox_info(mydb, onebox_list)
            if result < 0:
                log.error("failed to get onebox Info: %d %s" %(result, data))
        
        self._send_response(result, data)
    
    # 준공처리
    def put(self, onebox_id = None):
        log.debug("***************** OneBoxPut IN **********************")
        
        result, http_content = util.format_in(self.request, orch_schemas.service_order_schema)
        if result < 0:
            self._send_response(result, http_content)
            return
        
        r = af.remove_extra_items(http_content, orch_schemas.service_order_schema)
        if r is not None: 
            log.warning("Warning: remove extra items : %s" % r)

        if onebox_id is None:
            result = -400
            data = "Need One-Box ID"
        else:
            # Work Flow 분기
            server_result, server_data = server_manager.get_server_with_filter(mydb, onebox_id)

            log.debug('[WF] server_result = %d, server_data = %s' % (server_result, str(server_data)))

            if server_result == 1:
                if server_data[0].get('nfsubcategory') == "One-Box":
                    # 기존 소스
                    result, data = serviceorder_manager.update_onebox_info(mydb, onebox_id, http_content)
                else:
                    # 초소형 PNF
                    log.debug('[WF] update_onebox_info : http_content = %s' %str(http_content))

                    managers = {}
                    managers['orch_comm'] = self.plugins.get('orch_comm')
                    managers['wf_server_manager'] = self.plugins.get('wf_server_manager')
                    managers['wf_nsr_manager'] = self.plugins.get('wf_nsr_manager')
                    managers['wf_monitorconnector'] = self.plugins.get('wf_monitorconnector')
                    managers['wf_obconnector'] = self.plugins.get('wf_obconnector')
                    managers['wf_Odm'] = self.plugins.get('wf_Odm')

                    # ArmBox
                    managers['wf_server_arm_manager'] = self.plugins.get('wf_server_arm_manager')
                    managers['wf_nsr_arm_manager'] = self.plugins.get('wf_nsr_arm_manager')

                    http_content['onebox_type'] = server_data[0].get('nfsubcategory')
                    http_content['onebox_id'] = onebox_id

                    # wf_svcorder_manager = wfm_svcorder_manager.svcorder_manager(http_content)
                    result, data = self.plugins.get('wf_svcorder_manager').update_onebox_info(http_content, managers)

                # backup scheduler 삭제 : category = 'ONEBOX', categoryseq = serverseq
                if http_content.get('order_type') == 'ORDER_OB_REMOVE':
                    delete_result, delete_data = _delete_backup_scheduler(mydb, 'ONEBOX', server_data[0].get('serverseq'))
            else:
                log.debug("No Search One-Box data")
                result, data = server_result, server_data


            log.debug("_______________________________result, data = %d %s" % (result, data) )
            if result < 0:
                log.error("failed to update onebox Info: %d %s" %(result, data))
            else:
                if type(data) == str:
                    data = {"result":data}
                else:
                    data = {"result":"OK"}
        
        self._send_response(result,data)

    def delete(self, onebox_id = None):
        log.debug("IN")
        
        if onebox_id is None:
            self._send_response(HTTPResponse.Bad_Request, "No Target")
            return

        # 고객 계정 자동 삭제처리
        result, data = server_manager.delete_onebox_account(mydb, onebox_id, is_auto=True)
        if result < 0:
            log.error("delete_onebox_account error %d %s" % (-result, data))

        result, content = server_manager.delete_server(mydb, str(onebox_id))
        if result < 0:
            data = content
        else:
            data = {"result":"OK"}

        self._send_response(result, data)


    def _backup_onebox_nsr(self, onebox_id):
        # Work Flow 분기
        server_result, server_data = server_manager.get_server_with_filter(mydb, onebox_id)

        if server_result == 1:
            if server_data[0].get('nfsubcategory') == "One-Box":
                # 기존 소스
                result, data = serviceorder_manager.backup_onebox_nsr(mydb, onebox_id)
            else:
                # 초소형 PNF
                http_content = {}
                http_content['onebox_type'] = server_data[0].get('nfsubcategory')
                http_content['onebox_id'] = onebox_id
                http_content['backup'] = {}
                action_category = "Backup"

                log.debug('[WF] update_onebox_info : http_content = %s' % str(http_content))

                # wf_act_manager = wfm_act_manager.act_manager(http_content)
                managers = {}
                managers['orch_comm'] = self.plugins.get('orch_comm')
                managers['wf_server_manager'] = self.plugins.get('wf_server_manager')
                managers['wf_act_manager'] = self.plugins.get('wf_act_manager')
                managers['wf_monitorconnector'] = self.plugins.get('wf_monitorconnector')
                managers['wf_obconnector'] = self.plugins.get('wf_obconnector')
                managers['wf_Odm'] = self.plugins.get('wf_Odm')

                result, data = self.plugins.get('wf_act_manager').action(http_content, managers, action_category)
        else:
            log.debug("No Search One-Box data")
            result, data = server_result, server_data

        # result, data = serviceorder_manager.backup_onebox_nsr(mydb, onebox_id)
        if result < 0:
            log.error("failed to get onebox Info: %d %s" % (result, data))

        # backup scheduler 자동 등록
        self._auto_backup_scheduler(server_data[0])

        self._send_response(result, data)

        # log.debug("__________ self.request.files : %s" % self.request.files )
        # file1 = self.request.files['file1'][0]
        # log.debug("__________  file1['filename'] = %s" %  file1['filename'])
        # # Test Code
        # acc_conn = accountconnector.accountconnector("xms")
        # appid = onebox_id
        # apppasswd = onebox_id+"@"
        #
        # result, resultCd = acc_conn.check_validate(appid, apppasswd)
        #
        # log.debug("_______________ check_validate Account : %d %s" % (result, resultCd))
        #
        # result, resultCd = acc_conn.create_account(appid, apppasswd)
        #
        # log.debug("_______________create Account : %d %s" % (result, resultCd))

    # changing orgnamescode
    def _onebox_update(self, onebox_id):
        result, http_content = util.format_in(self.request, orch_schemas.service_onebox_update_schema)
        if result < 0:
            self._send_response(result, http_content)
            return

        # server_result, server_data = server_manager.get_server_with_filter(mydb, onebox_id)

        filter_dict = {'officeseq' : onebox_id}
        server_result, server_data = orch_dbm.get_server_filters_wf(mydb, filter_dict)

        # log.debug('server_result = %d, server_data = %s' %(server_result, str(server_data)))

        if server_result <= 0:
            log.debug("No Search One-Box data")
            result, data = server_result, server_data
        else:
            http_content['onebox_id'] = server_data[0].get('onebox_id')
            result, data = serviceorder_manager.order_update(mydb, http_content)

        if result < 0:
            log.error("failed to get onebox Info: %d %s" % (result, data))

        res_dict = {'result': data}
        self._send_response(result, res_dict)


    # changing service number
    def _onebox_update_servicenum(self, kind, onebox_id):
        result, http_content = util.format_in(self.request, orch_schemas.service_onebox_update_servicenum_schema)
        if result < 0:
            self._send_response(result, http_content)
            return

        http_content['onebox_id'] = onebox_id
        http_content['kind'] = kind

        result, data = serviceorder_manager.order_update_servicenum(mydb, http_content)

        if result < 0:
            log.error("failed to get onebox Info: %d %s" % (result, data))

        res_dict = {'result': data}
        self._send_response(result, res_dict)

    # auto backup scheduler
    def _auto_backup_scheduler(self, server_data):
        log.debug('(_auto_backup_scheduler) server_data = %s' % str(server_data))

        # default dict set
        insert_data = {}
        insert_data['category'] = None
        insert_data['categoryseq'] = None
        insert_data['mon'] = 'Y'
        insert_data['tue'] = 'Y'
        insert_data['wed'] = 'Y'
        insert_data['thur'] = 'Y'
        insert_data['fri'] = 'Y'
        insert_data['sat'] = 'Y'
        insert_data['sun'] = 'Y'
        insert_data['dayhh'] = None
        insert_data['daymm'] = None
        insert_data['monthday'] = 1
        insert_data['monthhh'] = None
        insert_data['monthmm'] = None
        insert_data['dayuse_yn'] = 'Y'
        insert_data['monthuse_yn'] = 'N'
        insert_data['reg_id'] = 'admin'
        # insert_data['reg_dttm'] = datetime.datetime.now()

        result, data = orch_dbm.get_backup_basetime(mydb)

        log.debug('data = %s' % str(data))

        if result > 0:
            backup_day = data[0].get('hhmm')

            obday = copy.deepcopy(backup_day)
            nsday = copy.deepcopy(backup_day)

            ob_dayhh = obday[:2]
            ob_daymm = obday[2:]

            dayhh = int(nsday[:2])
            daymm = int(nsday[2:]) + 10

            log.debug('dayhh = %s, daymm = %s' % (str(dayhh), str(daymm)))

            if daymm >= 60:
                dayhh = dayhh + 1
                daymm = daymm - 60

            dayhh = "0" + str(dayhh)

            if daymm < 10:
                daymm = "0" + str(daymm)

            log.debug('dayhh = %s, daymm = %s' % (str(dayhh), str(daymm)))

            # insert : onebox backup scheduler
            insert_data['category'] = 'ONEBOX'
            insert_data['categoryseq'] = server_data.get('serverseq')
            insert_data['dayhh'] = ob_dayhh
            insert_data['daymm'] = ob_daymm

            log.debug('insert_data = %s' % str(insert_data))

            in_result, in_data = orch_dbm.insert_backup_scheduler(mydb, insert_data)

            if in_result > 0:
                insert_data['category'] = 'NS'
                insert_data['categoryseq'] = server_data.get('nsseq')
                insert_data['dayhh'] = dayhh
                insert_data['daymm'] = daymm

                log.debug('insert_data = %s' % str(insert_data))

                if server_data.get('nfsubcategory') == 'One-Box':
                    # insert : ns backup scheduler
                    in_result, in_data = orch_dbm.insert_backup_scheduler(mydb, insert_data)

        
    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        self.finish(body)

