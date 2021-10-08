# -*- coding: utf-8 -*-

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
import time, datetime
import sys
from tornado.web import RequestHandler

import orch_schemas
import db.orch_db_manager as orch_dbm
import orch_core

from handlers_t.http_response import HTTPResponse
import handler_utils as util

from utils import db_conn_manager as dbmanager
from utils import auxiliary_functions as af
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from engine import server_manager, vim_manager, serviceorder_manager, descriptor_manager

global mydb
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t="/rs"

OPCODE_NSD_ACTION = "NSD_ACTION"
OPCODE_NSR_INFO = "NSR_INFO"
OPCODE_NSR_MONITOR = "NSR_MONITOR"
OPCODE_NSR_ACTION = "NSR_ACTION"

FLAG_ROADSHOW = False

def url():
    urls = [ (url_base_t + "/nsd/([^/]*)", RsNSDHandler),
             (url_base_t + "/nsd/([^/]*)/action", RsNSDHandler),
             (url_base_t + "/nsr/([^/]*)", RsNSRHandler, dict(opCode=OPCODE_NSR_INFO)),
             (url_base_t + "/nsr/([^/]*)/monitor", RsNSRHandler, dict(opCode=OPCODE_NSR_MONITOR)),
             (url_base_t + "/nsr/([^/]*)/action", RsNSRHandler, dict(opCode=OPCODE_NSR_ACTION)),
             (url_base_t + "/customer/([^/]*)", RsCustomerHandler),
             (url_base_t + "/test/go/([^/]*)", TestGoHandler),
             (url_base_t + "/test/sdn/([^/]*)", TestSdnHandler)
             ]

    return urls

class RsNSDHandler(RequestHandler):
    #def initialize(self, opCode):
    #    self.opCode = opCode
    
    def post(self, nsd_id=None):
        log.debug("[ROADSHOW] IN: NSD Action - Provisioning NS")
        if nsd_id == None:
            log.error("[ROADSHOW] failed to provision NS: No NSD ID")
            self._send_response(-500, "No NSD ID")
            return
        
        result, http_content = util.format_in(self.request, orch_schemas.nsd_action_schema)
        log.debug("[ROADSHOW] Provisioning NS: %s, %s" %(str(nsd_id), str(http_content)))
        if result < 0:
            self._send_response(result, http_content)
            return
        
        r = af.remove_extra_items(http_content, orch_schemas.nsd_action_schema)
        if r is not None: 
            log.warning("Warning: remove extra items ", r)
            
        if "start" in http_content:
            
            #for Roadshow
            
            if FLAG_ROADSHOW:
                if str(http_content['start'].get('customer_id')) == "94": 
                    result, data = orch_dbm.get_nsr_id(mydb, 442)
                    
                    time.sleep(3)
                    self._send_response(result, data)
            
                    log.debug("[ROADSHOW] OUT: NSD Action - Provisioning NS")
                    return
            
                log.debug("[ROADSHOW] 1. Start SDN")
                
                if result < 0:
                    log.error("[ROADSHOW] Provisioning NS: failed: %d, %s" %(result, data))
                else:
                    log.debug("[ROADSHOW] SDN Switch Bandwidth: %s, Customer_id: %s" %(str(http_content['start'].get('sdn_switch_bw', 100)), str(http_content['start'].get('customer_id'))))
                    sdn_result, sdn_data = orch_core.start_sdn_switch(mydb, sdn_switch_bw = http_content['start'].get('sdn_switch_bw', 100),
                                                                      customer_id=http_content['start'].get('customer_id'))
            
            log.debug("[ROADSHOW] 2. Check Params")
            
            # Add Params
            p_result, p_content = orch_dbm.get_nsd_param_only(mydb, nsd_id)
            if p_result < 0:
                log.error("[ROADSHOW] Provisioning NS: failed to get parameters from DB: %d %s" %(result, data))
            
            given_param_list = http_content['start'].get('parameters').split(";")
            
            request_params = ""
            is_first_param = True
            for param in p_content:
                if param['name'].find("IPARM") >= 0 or param['name'].find("ROUT") >= 0:
                    continue
                
                desc_list = param['description'].split('__')
                if len(desc_list) >= 5:
                    param['value'] = str(desc_list[4])
                    log.debug("[ROADSHOW][HJC] Param Name: %s, Param Default Value: %s" %(param['name'], param['value']))
                
                for gp in given_param_list:
                    if gp.find(param['name']) >= 0:
                        param['value'] = str(gp.split("=")[1])
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Given Value: %s" %(param['name'], param['value']))
                        break
                
                
                #for Roadshow
                if FLAG_ROADSHOW:
                    '''
                    if param['name'] == 'RPARM_redFixedIp_Olleh-UTM':
                        param['value'] = "210.183.241.170"
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'CPARM_greenDhcp_Olleh-UTM':
                        param['value'] = 'off'
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))                    
                    '''

                    
                    if param['name'] == 'RPARM_redFixedIp_Olleh-UTM':
                        param['value'] = "210.183.241.174"
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'RPARM_redFixedMac_Olleh-UTM':
                        param['value'] = '14:02:ec:49:14:44'
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'APARM_appid_XMS':
                        param['value'] = 'kttest04'
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'CPARM_quotaid_GiGA-Storage':
                        param['value'] = 'CABeAAEAAADaBwAAAAAAEAUAAAAAAAAA='
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'APARM_appid_GiGA-Storage':
                        param['value'] = 'KIV'
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                else:
                    #for Dev
                    if param['name'] == 'RPARM_redFixedIp_Olleh-UTM':
                        param['value'] = "211.224.204.167"
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'RPARM_redFixedMac_Olleh-UTM':
                        param['value'] = '9c:b6:54:95:90:0c'
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'CPARM_redType_Olleh-UTM':
                        param['value'] = 'DHCP'
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'CPARM_greenDhcp_Olleh-UTM':
                        param['value'] = 'off'
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    if param['name'] == 'CPARM_quotaid_GiGA-Storage':
                        param['value'] = 'bmZ2LWFkbWluOm5mdmFkbWluOTkwMCYmKio='
                        log.debug("[ROADSHOW][HJC] Param Name: %s, Param Hard-coded Value: %s" %(param['name'], param['value']))
                    
                if param.get('value') != None:
                    log.debug("[ROADSHOW] OK Parameter Value for %s: %s" %(param['name'], param['value']))
                    
                    if is_first_param == False:
                        request_params += ";"
                    else:
                        is_first_param = False
                    
                    request_params = request_params + param['name'] + "=" + param['value']
                else:
                    log.error("[ROADSHOW] NEED Parameter Value for %s" %param['name'])
            
            log.debug("[ROADSHOW] Request Param: %s" %request_params)
            
            #TEST START
            #result = -404
            #data = "Under Testing"
            #self._send_response(result, data)
        
            #log.debug("[ROADSHOW] OUT: NSD Action - Provisioning NS")
            #return
            #TEST END
            
            log.debug("[ROADSHOW] 3. Start New NSR")
            result, data = orch_core.new_nsr(mydb, nsd_id, http_content['start'].get('instance_name', 'NotGiven'),
                                             http_content['start'].get('description', 'none'),
                                             customer_id=http_content['start'].get('customer_id'),
                                             customer_name=http_content['start'].get('customer_name'),
                                             vim=http_content['start'].get('vim'),
                                             params=request_params)
        else:
            result = -404
            data = "Not Supported Action"
        
        log.debug("[ROADSHOW] 4. Send Response")
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: NSD Action - Provisioning NS")
        return
        
    def get(self, nsd_id=None):
        log.debug("[ROADSHOW] IN: Get NSD Info")
        
        if nsd_id == None or nsd_id == "all":
            result, content = orch_dbm.get_nsd_list(mydb, {})
            if result < 0:
                data = content
                log.error("[ROADSHOW] failed to GET NSD List: %d %s" %(result, data))
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)
                af.convert_str2boolean(content, ('publicyn'))
                data={'nsd' : content}
        else:
            result, data = descriptor_manager.get_nsd_id(mydb, nsd_id)
            
            if result < 0:
                log.error("[ROADHSOW] failed to GET NSD Detail Info: %d %s" %(result, data))
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Get NSD Info")        
        return

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        
        #self.finish(body)
        self.write(body)
        self.flush()

class RsNSRHandler(RequestHandler):
    def initialize(self, opCode):
        self.opCode = opCode
    
    def post(self, nsr_id=None):
        log.debug("[ROADSHOW] IN: NSR Action")
        if nsr_id == None:
            log.error("[ROADSHOW] failed to provision NS: No NSR ID")
            self._send_response(-500, "No NSR ID")
            return
        
        result, http_content = util.format_in(self.request, orch_schemas.nsr_action_schema)
        log.debug("[ROADSHOW] Action for NSR: %s, %s" %(str(nsr_id), str(http_content)))
        if result < 0:
            self._send_response(result, http_content)
            return
        
        #r = af.remove_extra_items(http_content, orch_schemas.nsr_action_schema)
        #if r is not None: 
        #    log.warning("Warning: remove extra items ", r)
            
        if "update" in http_content:
            log.debug("[ROADSHOW] UPDATE %s, %s" %(str(http_content['update'].get("storage_amount")), str(http_content['update'].get("sdn_switch_bw"))))
            result, data = orch_core.update_nsr_for_go(mydb, nsr_id, http_content['update'].get("storage_amount", -1), http_content['update'].get("sdn_switch_bw", -1))
            if result < 0:
                log.error("[ROADSHOW] failed to update NSR for GiGA Office: %d %s" %(result, data))
            else:
                data['result']="OK"
        elif "check_status" in http_content:
            log.debug("[ROADSHOW] CHECK STATUS")
            result, data = orch_dbm.get_nsr_general_info(mydb, nsr_id)
            if result < 0:
                log.error("[ROADSHOW] failed to get NSR General Info: %d %s" %(result, data))
            else:
                af.convert_datetime2str_psycopg2(data)
        else:
            result = -404
            data = "Not Supported Action"
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: NSR Action")
        return
        
    def get(self, nsr_id=None):
        log.debug("[ROADSHOW] IN: Get NSR Info")
        
        if self.opCode == OPCODE_NSR_MONITOR:
            if nsr_id == None or nsr_id == "all":
                log.error("[ROADSHOW] failed to get NSR Monitor: No NSR ID")
                result = -400
                data = "Non NSR ID"
            else:
                result, content = orch_core.get_nsr_monitor(mydb, nsr_id)
                if result < 0:
                    data = content
                    log.error("[ROADSHOW] failed to get NSR Monitor Data: %d %s" %(result, data))
                else:
                    data={'nsr_mon': content}            
        else:            
            if nsr_id == None or nsr_id == "all":
                result, content = orch_dbm.get_nsr(mydb, {})
                if result < 0:
                    data = content
                    log.error("[ROADSHOW] failed to GET NSR List: %d %s" %(result, data))
                else:
                    for c in content:
                        af.convert_datetime2str_psycopg2(c)
                    af.convert_str2boolean(content, ('publicyn', 'builtinyn'))
                    data={'nsr' : content}
            else:
                result, data = orch_dbm.get_nsr_id(mydb, nsr_id)
                
                if 'vnfs' in data:
                    sdn_dict = {'name': "SDN Switch", 'display_name': "SDN Switch", 'description': "Software Defined Network for KT GiGA Office", 'vendorcode':"kt", 'deploy_info':"GiGA Office", 'nfsubcategory':"SDN"}
                    sdn_dict['web_url'] = "http://210.183.241.184:8080/controller/BoD"
                    sdn_dict['vdus']=[{'reg_dttm': data['reg_dttm']}]
                    
                    sdn_result, sdn_info = orch_core.get_sdn_report_info()
                    if sdn_result < 0:
                        sdn_dict['report'] = [{'name':'bandwidth','display_name':"Bandwidth 제한 (Mbps)", 'value':"N/A"}]
                    else:
                        sdn_dict['report'] = [{'name':'bandwidth','display_name':"Bandwidth Limit (Mbps)", 'value':str(sdn_info.get('bandwidth'))},
                                              {'name':'usage','display_name':"Usage(%)",'value':str(sdn_info.get('usage'))}]
                    sdn_dict['ui_action'] = [{'name': "scale_bandwidth", "display_name": "Bandwidth Limit", 'description':"Limit the maximum user traffic over GiGA Office networks"}]
                    
                    data['vnfs'].append(sdn_dict)
                
                if result < 0:
                    log.error("[ROADHSOW] failed to GET NSR Detail Info: %d %s" %(result, data))
                    
                c_result, c_data = orch_dbm.get_customer_id(mydb, data['customerseq'])
                if c_result < 0:
                    log.debug("[ROADSHOW] failed to get customer info: %d %s" %(c_result, c_data))
                else:
                    data['customer']={'customername':c_data['customername'], 'detailaddr':c_data['detailaddr'], 'hp_num':c_data['hp_num']}
                    log.debug("[ROADSHOW] Customer: %s" %str(data['customer']))        
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Get NSR Info")
        return

    def delete(self, nsr_id=None):
        log.debug("[ROADSHOW] IN: Terminating NSR")
        
        if nsr_id == None:
            log.error("[ROADSHOW] failed to Terminating NSR: No NSR ID")
            self._send_response(-500, "No NSR ID")
            return
        
        log.debug("[ROADSHOW] SDN Switch Bandwidth: 100, NSR_id: %s" %str(nsr_id))
        sdn_result, sdn_data = orch_core.end_sdn_switch(mydb, nsr_id)
        
        log.debug("[ROADSHOW] Start Deleting NSR")    
        result, content = orch_core.delete_nsr(mydb, nsr_id)
        if result < 0:
            data = content
            log.error("[ROADHSOW] failed to terminate NSR: %d %s" %(result, data))
        else:
            data = {"result":"OK", "message": content, "nsseq": nsr_id}
        
        log.debug("[ROADSHOW] Send Response")   
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Terminating NSR")
        return
    
    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        
        #self.finish(body)
        self.write(body)
        self.flush()
        

class RsCustomerHandler(RequestHandler):
    #def initialize(self, opCode):
    #    self.opCode = opCode
    
    def post(self, customer_id=None):
        log.debug("[ROADSHOW] IN: Add Customer")
        
        result, http_content = util.format_in(self.request, orch_schemas.customer_schema)
        log.debug("[ROADSHOW] Customer Info: %s, %s" %(str(customer_id), str(http_content)))
        if result < 0:
            self._send_response(result, http_content)
            return
        
        r = af.remove_extra_items(http_content, orch_schemas.customer_schema)
        if r is not None: 
            log.warning("Warning: remove extra items ", r)
        
        result, data = serviceorder_manager.new_customer(mydb, http_content['customer'])
        if result < 0:
            log.error("[ROADSHOW] failed to add customer: %d %s" %(result, data))
            self._send_response(-500, "failed to add customer: %d %s" %(result, data))
            return
        else:
            c_result, c_data = orch_dbm.get_customer_id(mydb, data)
            if c_result < 0:
                self._send_response(-500, "failed to add customer: %d %s" %(result, data))
                return
            else:
                server_dict = {'customer_name': http_content['customer']['customername']}
                
                log.debug("[HJC] C_DATA-customername = %s" %c_data['customername'])
                if c_data['customername'] == "rs2016a":
                    log.debug("[HJC] customer name = %s" %str(http_content['customer'].get('customername')))
                    server_dict['public_ip'] = '211.224.204.167'
                    server_dict['mgmt_ip'] = '211.224.204.167'
                    server_dict['hardware'] = {'num_cores_per_cpu': 4, 'mem_size': 10240, 'num_cpus': 1, 'num_logical_cores': 4, 'model': 'HP DL XXX', 'cpu': 'E5-2609 0 @ 2.40GHz'}
                    server_dict['software'] = {'operating_system': 'Ubuntu 14.04'}
                    server_dict['obagent'] = {'version': '0.0.1', 'base_url': 'http://211.224.204.167:5556/v1'}
                    server_dict['vim'] = {'vim_tenant_username': 'admin', 'vim_tenant_passwd': 'onebox2016!', 'vim_type': 'OpenStack-ANode', 'vim_tenant_name': 'admin', 'vim_authurl': 'http://211.224.204.167:35357/v2.0'}
                    server_dict['vnfm'] = {'base_url': 'http://211.224.204.167:9014/ktvnfm/v1'}
                    server_dict['wan'] = {'nic': 'em1', 'mac': '9c:b6:54:95:90:0c', 'mode': 'host'}
                    server_dict['lan_office'] = {'nic': 'em2'}
                    server_dict['lan_server'] = {'nic': 'em3'}
                elif c_data['customername'] == "rs2016b":
                    log.debug("[HJC] customer name = %s" %str(http_content['customer'].get('customername')))
                    server_dict['public_ip'] = '210.183.241.170'
                    server_dict['mgmt_ip'] = '210.183.241.170'
                    server_dict['hardware'] = {'num_cores_per_cpu': 4, 'mem_size': 15944, 'num_cpus': 1, 'num_logical_cores': 8, 'model': 'NSA3130', 'cpu': 'Intel(R) Core(TM) i7-3770 CPU @ 3.40GHz with 8192 KB cache'}
                    server_dict['software'] = {'operating_system': 'Ubuntu 14.04'}
                    server_dict['obagent'] = {'version': '0.0.1', 'base_url': 'http://210.183.241.170:5556/v1'}
                    server_dict['vim'] = {'vim_tenant_username': 'admin', 'vim_tenant_passwd': 'onebox2016!', 'vim_type': 'OpenStack-ANode', 'vim_tenant_name': 'admin', 'vim_authurl': 'http://210.183.241.170:35357/v2.0'}
                    server_dict['vnfm'] = {'base_url': 'http://210.183.241.170:9014/ktvnfm/v1'}
                    server_dict['wan'] = {'nic': 'p4p1', 'mac': '00:10:f3:5a:91:86', 'mode': 'host'}
                    server_dict['lan_office'] = {'nic': 'p1p1'}
                    server_dict['lan_server'] = {'nic': 'p2p1'}
                elif c_data['customername'] == "KIV":
                    log.debug("[HJC] customer name = %s" %str(http_content['customer'].get('customername')))
                    server_dict['public_ip'] = '210.183.241.174'
                    server_dict['mgmt_ip'] = '210.183.241.174'
                    server_dict['hardware'] = {'num_cores_per_cpu': 4, 'mem_size': 15944, 'num_cpus': 1, 'num_logical_cores': 8, 'model': 'NSA3130', 'cpu': 'Intel(R) Core(TM) i7-3770 CPU @ 3.40GHz with 8192 KB cache'}
                    server_dict['software'] = {'operating_system': 'Ubuntu 14.04'}
                    server_dict['obagent'] = {'version': '0.0.1', 'base_url': 'http://210.183.241.174:5556/v1'}
                    server_dict['vim'] = {'vim_tenant_username': 'admin', 'vim_tenant_passwd': 'onebox2016!', 'vim_type': 'OpenStack-ANode', 'vim_tenant_name': 'admin', 'vim_authurl': 'http://210.183.241.174:35357/v2.0'}
                    server_dict['vnfm'] = {'base_url': 'http://210.183.241.174:9014/ktvnfm/v1'}
                    server_dict['wan'] = {'nic': 'p4p1', 'mac': '14:02:ec:49:14:44', 'mode': 'host'}
                    server_dict['lan_office'] = {'nic': 'p1p1'}
                    server_dict['lan_server'] = {'nic': 'p2p1'}

                else:
                    log.debug("[HJC] Unexpected customer name = %s" %str(http_content['customer'].get('customername')))
                    self._send_response(-404, "Not supported Customer. Use rs2016a or rs2016b for Roadshow")
                    return
            
            #s_result, s_data = server_manager.new_server(mydb, server_dict)
            #if s_result < 0:
            #    log.error("[ROADSHOW] failed to add One-Box server for the customer: %d %s" %(s_result, s_data))
            #    self._send_response(s_result, s_data)
            #    return
        
        self._send_response(result, {"customer": {"customerseq": data}})
        
        log.debug("[ROADSHOW] OUT: Add Customer")
        return
        
    def get(self, customer_id=None):
        log.debug("[ROADSHOW] IN: Get Customer Info")
        
        if customer_id == None or customer_id == "all":
            result, content = orch_dbm.get_customer_list(mydb, {})
            if result < 0:
                data = content
                log.error("[ROADSHOW] failed to GET Customer List: %d %s" %(result, data))
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)
                data={'customer' : content}
        else:
            result, data = orch_dbm.get_customer_id(mydb, customer_id)
            
            if result < 0:
                log.error("[ROADHSOW] failed to GET Customer Detail Info: %d %s" %(result, data))
            else:
                af.convert_datetime2str_psycopg2(data)
                    
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Get Customer Info")
        return

    def delete(self, customer_id=None):
        log.debug("[ROADSHOW] IN: Deleting Customer")
        
        data = {"result": "OK", "customerseq": customer_id}
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Deleting Customer")
        
        return
    
        # TODO        
        if customer_id == None:
            log.error("[ROADSHOW] failed to Deleting Customer: No Customer ID")
            self._send_response(-500, "No Customer ID")
            return
        
        srv_result, srv_content = orch_dbm.get_server_filters(mydb, {"customerseq": customer_id})
        if srv_result > 0 and len(srv_content) > 0:
            log.debug("delete servers for the Customer %s: %s" %(str(customer_id), str(srv_content)))
            for srv in srv_content:
                ds_result, ds_content = server_manager.delete_server(mydb, srv['serverseq'])
                if ds_result < 0:
                    log.warning("failed to delete server: %s" %str(srv['serverseq']))
        
        result, content = serviceorder_manager.delete_customer(mydb, customer_id)
        if result < 0:
            data = content
            log.error("[ROADHSOW] failed to delete Customer: %d %s" %(result, data))
        else:
            data = {"result": "OK", "customerseq": str(content)}
            
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Deleting Customer")
        return
        
    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        
        #self.finish(body)
        self.write(body)
        self.flush()
        
        
class TestGoHandler(RequestHandler):
    #def initialize(self, opCode):
    #    self.opCode = opCode
    
    def post(self, storage=None):
        log.debug("[ROADSHOW] IN: Test GiGA Office - set Storage")
        if storage == None:
            int_storage = 10
        else:
            int_storage = int(str(storage))
        log.debug("[ROADSHOW] Test GiGA Office - set Storage to %d" %int_storage)
        
        
        result, data = orch_core.test_set_go_sdn(mydb, int_storage)
        
        if result < 0:
            log.error("[ROADSHOW] Test GiGA Office - set Storage: failed: %d, %s" %(result, data))
        else:
            log.debug("[ROADSHOW] Test GiGA Office - set Storage: succeed: %d, %s" %(result, data))
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Test GiGA Office - set Storage")
        return
        
    def get(self, storage_id=None):
        log.debug("[ROADSHOW] IN: Test GiGA Office - get Storage")
        
        result, data = orch_core.test_get_go(mydb, storage_id)
        
        if result < 0:
            log.error("[ROADSHOW] Test GiGA Office - get Storage: failed: %d, %s" %(result, data))
        else:
            log.debug("[ROADSHOW] Test GiGA Office - get Storage: succeed: %d, %s" %(result, data))
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Test GiGA Office - get Storage")
        return

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        
        #self.finish(body)
        self.write(body)
        self.flush()

class TestSdnHandler(RequestHandler):
    #def initialize(self, opCode):
    #    self.opCode = opCode
    
    def post(self, bandwidth=None):
        log.debug("[ROADSHOW] IN: Test GiGA Office - set SDN")
        if bandwidth == None:
            int_bandwidth = 100
        else:
            int_bandwidth = int(str(bandwidth))
        log.debug("[ROADSHOW] Test GiGA Office - set SDN to %d" %int_bandwidth)
        
        
        result, data = orch_core.test_set_go_sdn(mydb, sdn_switch_bw=int_bandwidth)
        
        if result < 0:
            log.error("[ROADSHOW] Test GiGA Office - set SDN: failed: %d, %s" %(result, data))
        else:
            log.debug("[ROADSHOW] Test GiGA Office - set SDN: succeed: %d, %s" %(result, data))
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Test GiGA Office - set SDN")
        return
        
    def get(self, sdn_id=None):
        log.debug("[ROADSHOW] IN: Test GiGA Office - get SDN")
        
        result, data = orch_core.test_get_sdn(mydb, sdn_id)
        
        if result < 0:
            log.error("[ROADSHOW] Test GiGA Office - get SDN: failed: %d, %s" %(result, data))
        else:
            log.debug("[ROADSHOW] Test GiGA Office - get SDN: succeed: %d, %s" %(result, data))
        
        self._send_response(result, data)
        
        log.debug("[ROADSHOW] OUT: Test GiGA Office - get SDN")
        return

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        #self.finish(body)
        
        
