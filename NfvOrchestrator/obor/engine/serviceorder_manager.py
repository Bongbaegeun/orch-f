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

'''
NFVO engine, implementing all the methods for the creation, deletion and management of vnfs, scenarios and instances
'''
__author__="Jechan Han"
__date__ ="$05-Nov-2015 22:05:01$"

import json
import yaml
import os
import uuid as myUuid
import time, datetime
import sys
import threading

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found,\
    HTTP_Conflict
import db.orch_db_manager as orch_dbm

from engine.server_manager import new_server, delete_server, backup_onebox
from engine.common_manager import update_server_status
from engine.server_status import SRVStatus

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from orch_core import delete_nsr, backup_nsr

ORDER_TYPE_OB_NEW    = "ORDER_OB_NEW"
ORDER_TYPE_OB_UPDATE = "ORDER_OB_UPDATE"
ORDER_TYPE_OB_REMOVE = "ORDER_OB_REMOVE"

####################################################    for KT One-Box Service   #############################################

def _generate_customer_english_name(customer_name, customer_id):
    # TODO: check the characters of the customer_name
    # TODO: if customer_id is invalid, generate a random number
    customerename = "C"+str(customer_id)
    log.debug("Automatically generated Customer's English Name: %s" %customerename)
    return 200, customerename  
    
    
def new_customer(mydb, customer_dict):
    if 'order_id' in customer_dict:
        # check if ITSM order exists
        order_result, order_data = get_itsm_order_orderid(mydb, customer_dict['order_id'])
        if order_result < 0:
            return order_result, order_data
        
        customer_dict = {'customername': order_data['customername'], 'customerename':order_data.get('customerename', order_data['customername'])}
        #if 'cust_id' in order_data: customer_data['cust_id']=order_data['cust_id']
        if 'customerid' in order_data: customer_dict['customer_id']=order_data['customerid']
        if 'customeraddress' in order_data: customer_dict['customer_address']=order_data['customeraddress']
        if 'tenantid' in order_data: customer_dict['tenantid']=order_data['tenantid']
        # check if customer already exists
        cust_result, cust_data = get_customer_with_filters(mydb, customer_dict)
        if cust_result < 0 or cust_result > 1:
            return -HTTP_Internal_Server_Error, "DB Error: %d %s" %(cust_result, str(cust_data))
        elif cust_result == 1:
            log.debug("Customer already exists: %s" %str(cust_data))
            return cust_result, cust_data[0]['customerseq']
        # add
        
        pass
    else:
        # check if the requested Customer already exists
        c_result, c_content = orch_dbm.get_customer_id(mydb, customer_dict['customername'])
        log.debug("[HJC] check customer info from DB: %d %s" %(c_result, c_content))
        if c_result < 0:
            return -HTTP_Internal_Server_Error, "Failed to check Customer DB Table"+str(c_content)
        elif c_result == 0:
            # add Customer
            #customer_dict['customerename'] = customer_dict.get('customerename', customer_dict['customername'])
            #customer_dict['tenantid'] = customer_dict.get('tenantid', customer_dict['customerename'])
                
            result, customer_id = orch_dbm.insert_customer(mydb, customer_dict)
            if result < 0:
                log.error("failed to insert a DB record for a new customer:\n"+customer_id)
                return result, customer_id
            
            if 'customerename' not in customer_dict:
                result, customerename = _generate_customer_english_name(customer_dict['customername'], customer_id)
                customer_update = {'customerename': customerename, 'tenantid': customer_dict.get('tenantid', customerename)}
                customer_update['customerseq'] = customer_id
                
                result, update_id = orch_dbm.update_customer(mydb, customer_update)
                if result < 0:
                    log.error("failed to save the customerename for a new customer: %d %s" %(result, str(update_id)))
                    return result, str(update_id)
                        
            server_info = {'customer_name': customer_dict['customername']}
            srv_result, srv_data = new_server(mydb, server_info)
            log.debug("the result of new_server: %d %s" %(srv_result, srv_data))
            if srv_result < 0:
                log.warning("Failed to create a server for the customer, %s. Cause: %s" %(server_info['customer_name'], srv_data))
        else:
            log.debug("[HJC] Update Customer Info: new Customer Info: %s" %str(customer_dict))
            
            if c_content.get('customerseq') is None or c_content.get('customername') is None:
                log.error("Failed to get Customer Info of %s" %str(customer_dict['customername']))
                return -HTTP_Internal_Server_Error, "Invalid DB Record for the customer, %s" %str(customer_dict['customername']) 
            
            customer_id = c_content['customerseq']
            update_dict={'customerseq':customer_id}
            if 'emp_cnt' in customer_dict: update_dict['emp_cnt'] = customer_dict['emp_cnt']
            if 'email' in customer_dict: update_dict['email'] = customer_dict['email']
            if 'keymanname' in customer_dict: update_dict['keymanname'] = customer_dict['keymanname']
            if 'keymantelnum' in customer_dict: update_dict['keymantelnum'] = customer_dict['keymantelnum']
            if 'detailaddr' in customer_dict: update_dict['detailaddr'] = customer_dict['detailaddr']
            
            result, update_data = orch_dbm.update_customer(mydb, update_dict)
            if result < 0:
                log.error("failed to update a DB record for the customer:\n"+update_data)
                return result, update_data            
    
    return 200, customer_id

def delete_customer(mydb, customer):
    """
        고객삭제
    :param mydb:
    :param customer:
    :return:
    """
    #get customer info
    result, customer_dict = orch_dbm.get_customer_id(mydb, customer)
    if result <= 0:
        log.error("failed to delete the customer %s, No DB Record" % customer)
        return result, customer_dict

    #check if there is any resource owned by the customer
    result, resources = _get_customer_resources(mydb, customer)
    if result < 0:
        log.error("failed to check the resources of the customer %d %s" % (result, resources))
        return result, resources
    
    if resources != "none" and len(resources) > 0:
        error_text = "need to delete or detach resources (%d) of the customer in advance" % len(resources)
        log.error(error_text)
        return -HTTP_Bad_Request, error_text
    
    result, customer_id = orch_dbm.delete_customer(mydb, customer_dict['customerseq'])
    if result < 0:
        log.error("failed to delete the DB record for %s" %customer_dict['customerseq'])
        return result, customer_id
    return 200, customer_id


def delete_customers_info(mydb, customers):

    return_data = []
    for customer_ename in customers:
        # account_id조회
        account_id = ""
        rst_ac, data_ac = orch_dbm.get_account_id_of_customer(mydb, {"customerename":customer_ename})
        if rst_ac > 0:
            account_id = data_ac["account_id"]

        result, content = delete_customerinfo(mydb, customer_ename)
        return_data.append({"customer":customer_ename, "result_code":result, "result_msg":content, "account_id":account_id})

    return 200, return_data


def delete_customerinfo(mydb, customer_ename):

    """
        UI 고객정보관리에서 고객 삭제할 경우

    :param mydb:
    :param customer_key:
    :return: 삭제성공 or 삭제고객없음 : (200, OK), 삭제불가 : (200, NOT), 실패 : (500, error_msg)
    """

    result, customer_dict = orch_dbm.get_customer_ename(mydb, customer_ename)
    if result < 0:
        log.error("failed to delete the customer %s, No DB Record" % customer_ename)
        return result, customer_dict
    elif result == 0:
        log.debug("Not found Customer %s" % customer_ename)
        return 200, "OK"

    #check if there is any resource owned by the customer
    result, resources = _get_customer_resources(mydb, customer_dict["customerseq"])
    if result < 0:
        log.error("failed to check the resources of the customer %d %s" % (result, resources))
        return result, resources

    if resources != "none" and len(resources) > 0:
        error_text = "need to delete or detach resources (%d) of the customer in advance" % len(resources)
        log.debug(error_text)
        return 200, "NOT"

    result, customer_id = orch_dbm.delete_customer(mydb, customer_dict['customerseq'])
    if result < 0:
        log.error("failed to delete the DB record for %s" %customer_dict['customerseq'])
        return result, customer_id

    result, office_id = orch_dbm.delete_customer_office(mydb, {"customerseq":customer_dict['customerseq']})
    if result < 0:
        log.error("failed to delete the DB record for %s" %customer_dict['customerseq'])
        return result, office_id

    return 200, "OK"

def _get_customer_resources(mydb, customer):
    #get customer info
    result, content = orch_dbm.get_customer_resources(mydb, customer)
    if result < 0:
        log.error("failed to get resources of the customer %d %s" % (result, content))
    if result == 0:
        return 200, "none"
    log.debug("The resources of the customer %s: %d" % (customer, result))
    for item in content:
        log.debug(" - %s" % item)
    af.convert_datetime2str_psycopg2(content)
    return 200, content

# 본지사명 변경 : 기존 소스
def update_customer_info(mydb, so_id, update_info):
    customer_result, customer_data = orch_dbm.get_customer_ename(mydb, so_id)
    if customer_result < 0:
        log.error("update_customer_info(): failed to get Customer info %d %s" %(customer_result, customer_data))
        return customer_result, customer_data
    
    if 'customer' in update_info and update_info['customer'].get('customer_name') is not None:
        update_dict_customer = {'customerseq': customer_data['customerseq']}
        
        if update_info['customer'].get('customer_name') != customer_data.get('customername'):
            update_dict_customer['customername'] = update_info['customer'].get('customer_name')
        
        uc_result, uc_data = orch_dbm.update_customer(mydb, update_dict_customer)
        if uc_result < 0:
            log.error("failed to update Customer Info: %d %s" %(uc_result, uc_data))
            return uc_result, uc_data
    
    office_result, office_list = orch_dbm.get_customeroffice_ofcustomer(mydb, customer_data['customerseq'])
    if office_result < 0:
        log.error("failed to get customer office info from DB: %d %s" %(office_result, office_list))
        return office_result, office_list
    elif 'office' in update_info and len(update_info['office']) > 0:
        for update_office in update_info['office']:
            if update_office.get('office_name') is not None and update_office.get('old_office_name') is not None:
                for office in office_list:
                    if update_office['old_office_name'] == office.get('officename'):
                        update_dict_office = {"officeseq":office['officeseq'], "officename":update_office['office_name']}
                        uo_result, uo_data = orch_dbm.update_customeroffice(mydb, update_dict_office)
                        if uo_result < 0:
                            log.error("failed to update Office Info: %d %s" %(uo_result, uo_data))
                            return uo_result, uo_data

                        # new add : change orgnamescode
                        filter_dict = {'officeseq' : office['officeseq']}
                        server_result, server_data = orch_dbm.get_server_filters_wf(mydb, filter_dict)

                        log.debug('server_result = %d, server_data = %s' % (server_result, str(server_data)))

                        if server_result <= 0:
                            log.debug("No Search One-Box data")
                            pass
                        else:
                            for slist in server_data:
                                log.debug('nfsubcategory = %s' %str(slist.get('nfsubcategory')))

                                update_orgname = {}
                                update_orgname['nfsubcategory'] = slist.get('nfsubcategory')
                                update_orgname['org_name'] = update_office['office_name']
                                update_orgname['onebox_id'] = slist.get('onebox_id')
                                result, data = order_update(mydb, update_orgname)

                                if result < 0:
                                    log.error("failed to get onebox Info: %d %s" % (result, data))
                                    return result, data

                        break
    
    #TODO: Update Onebox Info
    
    return 200, "OK"

# 본지사명 변경 : 신규추가 2020.03.16
def update_customer_info_new(mydb, so_id, update_info):
    log.debug('update_customer_info_new : update_info = %s' %str(update_info))

    if 'office' in update_info and len(update_info['office']) > 0:
        for office in update_info['office']:
            if 'servername' in office:
                update_orgname = {}
                update_orgname['org_name'] = office.get('office_name')
                update_orgname['onebox_id'] = office.get('servername')
                result, data = order_update(mydb, update_orgname)

                if result < 0:
                    log.error("failed to get onebox Info: %d %s" % (result, data))
                    return result, data

    return 200, "OK"


def add_service_order(mydb, so_info):
    # Step 1. Check input data
    
    # Step 2. Create or Update Customer Info
    customer_seq = -1
    customer_result, customer_data = orch_dbm.get_customer_ename(mydb, so_info['customer']['customer_eng_name'])
    if customer_result < 0:
        log.error("add_service_order(): failed to get Customer info %d %s" %(customer_result, customer_data))
        return customer_result, customer_data
    elif customer_result == 0:
        log.debug("New Customer: %s" %str(so_info['customer']))
        customer_dict = {"customername": so_info['customer']['customer_name'], "customerename":so_info['customer']['customer_eng_name']}
        nc_result, nc_id = orch_dbm.insert_customer(mydb, customer_dict)
        if nc_result < 0:
            log.error("failed to insert customer info into DB: %d %s" %(nc_result, nc_id))
            return nc_result, nc_id
        customer_seq = nc_id

        # TODO: 2-1. Mapping Customer to All superusers(accounts)
        mp_result, mp_content = orch_dbm.insert_user_mp_customer(mydb, customer_seq)

    else:
        log.debug("Existing Customer: %s" %str(customer_data))
        customer_seq = customer_data['customerseq']
        #TODO: update Customer Info
    
    # Step 3. Create or Update Customer Office Info
    office_seq = -1
    if 'office' not in so_info:
        so_info['office'] = {"office_name": "본사"}
    
    office_result, office_data = orch_dbm.get_customeroffice_ofcustomer(mydb, customer_seq)
    if office_result < 0:
        log.error("failed to get customer office info from DB: %d %s" %(office_result, office_data))
        return office_result, office_data
    elif office_result > 0:
        log.debug("check existing office info")
        for office in office_data:
            officename = office['officename']
            so_officename = so_info['office']['office_name']

            # if type(officename) == str:
            #     officename = officename.decode("utf-8")
            # if type(so_officename) == str:
            #     so_officename = so_officename.decode("utf-8")

            if officename == so_officename:
                log.debug("Existing Office: %s" %so_info['office']['office_name'])
                office_seq = office['officeseq']
                break
        
    if office_seq < 0:
        log.debug("New Customer Office: %s" %str(so_info['office']))
        office_dict = {"officename": so_info['office']['office_name'], 'customerseq':customer_seq}
        log.debug("[HJC] DB Insert DATA for customer office: %s" %str(office_dict))
        no_result, no_id = orch_dbm.insert_customeroffice(mydb, office_dict)
        if no_result < 0:
            log.error("failed to insert customer office into DB: %d %s" %(no_result, no_id))
            return no_result, no_id
        office_seq = no_id

    # Step 4. Create or Update One-Box Info
    onebox_seq = -1
    onebox_status = SRVStatus.IDLE
    onebox_result, onebox_data = orch_dbm.get_server_filters(mydb, {"onebox_id": so_info['one-box']['onebox_id']})

    if onebox_result < 0:
        log.error("failed to get onebox info from DB: %d %s" %(onebox_result, onebox_data))
        return onebox_result, onebox_data

    elif onebox_result == 0:
        if so_info['order_type'] == ORDER_TYPE_OB_REMOVE:
            return 200, "OK"
        else:
            log.debug("New Onebox: %s" %str(so_info['one-box']))

            onebox_dict = {"servername":    so_info['one-box']['onebox_id'],
                           "onebox_id":     so_info['one-box']['onebox_id'],
                           "onebox_flavor": so_info['one-box'].get('model',"No Info")}

            if 'ob_service_number' in so_info['one-box']:
                onebox_dict['ob_service_number'] = so_info['one-box']['ob_service_number']

            onebox_dict['status'] = SRVStatus.IDLE
            onebox_dict['state'] = "NOTSTART"
            onebox_dict['nfmaincategory'] = "Server"

            if 'nfsubcategory' in so_info['one-box']:
                onebox_dict['nfsubcategory'] = so_info['one-box']['nfsubcategory']
            else:
                onebox_dict['nfsubcategory'] = "One-Box"

            onebox_dict['customerseq'] = customer_seq
            onebox_dict['officeseq'] = office_seq
            # onebox_dict['orgnamescode'] = "목동"      # original code
            # 하드코딩으로 '목동'으로 썼지만 오더 등록시 받은 값으로 쓰도록 변경
            onebox_dict['orgnamescode'] = so_info['office']['office_name']

            nob_result, nob_id = orch_dbm.insert_server(mydb, onebox_dict)
            if nob_result < 0:
                log.error("failed to insert onebox into DB: %d %s" %(nob_result, nob_id))
                return nob_result, nob_id
            onebox_seq = nob_id
    else:
        log.debug("Exsiting Onebox: %s" %str(onebox_data[0]))
        onebox_seq = onebox_data[0]['serverseq']
        onebox_status = onebox_data[0]['status']
        
        if so_info['order_type'] == ORDER_TYPE_OB_REMOVE:
            if onebox_status == SRVStatus.ERR and onebox_data[0].get('nsseq') is None:
                onebox_status = SRVStatus.HWE
        elif so_info['order_type'] == ORDER_TYPE_OB_UPDATE:
            #update_onebox_dict = {"serverseq": onebox_seq, "status":"N__UPDATE"}
            #orch_dbm.update_server_status(mydb, update_onebox_dict)
            pass
    
    # Step 4-2. Noti to Oder Manager
    server_status = onebox_status

    try_cnt = 3
    while server_status == SRVStatus.OOS:
        try_cnt -= 1
        if try_cnt < 0:
            return -500, "The status of server is out of service. Try again. If it still doesn't work, ask the manager."
        time.sleep(7)
        result, ob_data = orch_dbm.get_server_id(mydb, onebox_seq)
        server_status = ob_data["status"]

    if server_status == SRVStatus.IDLE:
        server_status = SRVStatus.LWT

    server_update_dict = {'serverseq': onebox_seq, 'status': server_status, 'onebox_id': so_info['one-box']['onebox_id'], "order_type": so_info['order_type']}
    us_result, us_data = update_server_status(mydb, server_update_dict)
    if us_result < 0:
        log.error("failed to inform one-box's status to Order Manager: %d %s" %(us_result, us_data))
    
    # Step 5. Create or Update One-Box Network Line Info
    if 'net_line_list' in so_info['one-box'] and len(so_info['one-box']['net_line_list']) > 0:
        old_nline_list = []
        nline_result, nline_data = orch_dbm.get_onebox_line_ofonebox(mydb, onebox_seq)
        if nline_result < 0:
            log.warning("failed to get network line info of the One-Box: %s" %so_info['one-box']['onebox_id'])
        elif nline_result > 0:
            old_nline_list = nline_data
            
        for nline in so_info['one-box']['net_line_list']:
            log.debug("Old Onebox Lines: %s, new line: %s" %(str(old_nline_list), str(nline)))
            is_existing_nline = False
            for old_line in old_nline_list:
                if old_line.get("line_number") == nline:
                    log.debug("Existing Network Line: %s" %nline)
                    is_existing_nline = True
                    break
            
            if not is_existing_nline:
                nline_dict = {"line_number": nline, "name": nline, "display_name": nline, "serverseq": onebox_seq}
                nl_result, nl_id = orch_dbm.insert_onebox_line(mydb, nline_dict)
                if nl_result < 0:
                    log.warning("failed to insert network line info into DB: %d %s" %(nl_result, nl_id))
            
    return 200, "OK"

def get_service_order(mydb):
    pass

def get_service_order_id(mydb, so_id):
    pass

def delete_service_order(mydb, so_id):
    pass

# def update_said(mydb, nscatalog_info, said=None):
#     if nscatalog_info == None or nscatalog_info.get('name') == None:
#         return -HTTP_Bad_Request, "No NS Catalog Info"
#
#     said_result, said_content = orch_dbm.get_serviceorder_said(mydb)
#     if said_result < 0:
#         return -HTTP_Internal_Server_Error, "DB Error: %d, %s" %(said_result, said_content)
#
#     if said:
#         said_name = said
#     else:
#         said_name = "KT-NFV-"+nscatalog_info['name']
#
#     already_exist = False
#     said_dict = {}
#     for s in said_content:
#         log.debug("[HJC] said record = %s" %str(s))
#         if s['nscatalog_name'] == nscatalog_info['name']:
#             return 200, s
#         if s['said'] == said_name:
#             already_exist = True
#             said_dict = {'said': s['said']}
#
#     if already_exist == True:
#         said_dict['nscatalog_name'] = nscatalog_info['name']
#         said_dict['nscatalog_version'] = nscatalog_info.get('version',"1")
#
#         log.debug("[HJC] said_dict for Update = %s" %str(said_dict))
#         result, content = orch_dbm.update_serviceorder_said(mydb, said_dict)
#     else:
#         said_dict['said'] = said_name
#         said_dict['nscatalog_name'] = nscatalog_info['name']
#         said_dict['nscatalog_version'] = nscatalog_info.get('version',"1")
#
#         log.debug("[HJC] said_dict for Insert = %s" %str(said_dict))
#         result, content = orch_dbm.insert_serviceorder_said(mydb, said_dict)
#
#     if result < 0:
#         log.error("Failed to update SAID: %d %s" %(result, content))
#
#     return result, content
    
def get_onebox_info(mydb, onebox_list=[]):
    if len(onebox_list) <= 0:
        return -HTTP_Bad_Request, "Need One-Box ID"
    
    result_list = []
    for onebox_id in onebox_list:
        onebox_info = {}
        
        # onebox_result, onebox_data = orch_dbm.get_server_filters(mydb, {"onebox_id": onebox_id})

        # 초소형 추가 되면서 쿼리 문제로 함수 추가
        onebox_result, onebox_data = orch_dbm.get_server_filters_wf(mydb, {"onebox_id": onebox_id})
        if onebox_result < 0:
            log.error("failed to get onebox info from DB: %d %s" %(onebox_result, onebox_data))
            return onebox_result, onebox_data
        elif onebox_result == 0:
            continue
        
        onebox_info['onebox_id'] = onebox_data[0]['onebox_id']

        # onebox_type 추가 : PNF 타입 추가로 인하여 수정
        onebox_info['nfsubcategory'] = onebox_data[0]['nfsubcategory']

        onebox_info['status'] = onebox_data[0]['status']
        onebox_info['model'] = onebox_data[0]['onebox_flavor']
        onebox_info['ob_service_number'] = onebox_data[0]['ob_service_number']
        onebox_info['net_line_list'] = []
        onebox_info['vnf_list'] = []
    
        nline_result, nline_data = orch_dbm.get_onebox_line_ofonebox(mydb, onebox_data[0]['serverseq'])
        if nline_result < 0:
            log.warning("failed to get network line info of the One-Box: %s" %onebox_data[0]['onebox_id'])
        elif nline_result == 0:
            log.debug("No Network lines found for %s" %onebox_data[0]['onebox_id'])
        elif len(nline_data) > 0:
            log.debug("nline_data = %s" %str(nline_data))
            for nline in nline_data:
                log.debug("nline = %s" %str(nline))
                onebox_info['net_line_list'].append(nline.get('line_number', "NONE"))
        
        if onebox_data[0].get('nsseq') is not None:
            nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, onebox_data[0]['nsseq'])
            if nsr_result < 0:
                log.error("failed to get NSR, VNF Info from DB: %d %s" %(nsr_result, nsr_data))
                return nsr_result, nsr_data
            
            for vnf in nsr_data['vnfs']:
                #af.convert_datetime2str_psycopg2(vnf)
                vnf_info = {"vnf_name": vnf['name'], "service_number": vnf['service_number'], "service_period": vnf['service_period']}
                vnf_info['service_start_dttm'] = vnf.get('service_start_dttm')
                vnf_info['service_end_dttm'] = vnf.get('service_end_dttm')
                
                vnf_info['vnfd_name'] = vnf['vnfd_name']
                vnf_info['vnfd_version'] = vnf['version']
                vnf_info['vnfd_display_name'] = vnf['display_name']
                if vnf_info['vnfd_display_name'] is None:
                    vnf_info['vnfd_display_name'] = vnf_info['vnfd_name'] + " (ver." + str(vnf_info['vnfd_version']) + ")"
                
                onebox_info['vnf_list'].append(vnf_info)
    
        result_list.append(onebox_info)
    
    return 200, result_list


def update_onebox_info(mydb, onebox_id, update_info):

    onebox_result, onebox_data = orch_dbm.get_server_filters_wf(mydb, {"onebox_id": onebox_id})

    if onebox_result < 0:

        log.error("failed to get onebox info from DB: %d %s" %(onebox_result, onebox_data))
        return onebox_result, onebox_data

    elif onebox_result == 0:

        log.warning("Not found One-Box: %s" %onebox_id)

        if update_info.get("order_handle") == "cancel" and update_info.get('order_type') == ORDER_TYPE_OB_NEW:
            return 200, "Not found: One-Box of %s" % onebox_id
        elif update_info.get("order_handle") == "stop" and update_info.get('order_type') == ORDER_TYPE_OB_NEW:
            return 200, "Not found: One-Box of %s" % onebox_id
        else:
            return -HTTP_Not_Found, "Not found: One-Box of %s" %onebox_id

    # TODO: Update One-Box Info
    #if update_info['one-box'].get('ob_service_number') is not None and update_info['one-box']['ob_service_number'] != onebox_data[0].get('ob_service_number'):
    #    update_dict_onebox = {'serverseq': onebox_data[0]['serverseq'], 'ob_service_number': update_info['one-box']['ob_service_number']}

    if update_info.get('order_type') == ORDER_TYPE_OB_REMOVE:

        if update_info.get("order_handle") == "cancel":
            log.debug("order_handle: cancel, order_type: ORDER_OB_REMOVE : process undefined")
            return 200, "OK"
        elif update_info.get("order_handle") == "stop":
            log.debug("order_handle: stop, order_type: ORDER_OB_REMOVE : process undefined")
            return 200, "OK"

        if onebox_data[0].get('nsseq') is not None:
            dn_result, dn_content = delete_nsr(mydb, onebox_data[0]['nsseq'], need_stop_monitor=True, use_thread=False, tid=None, tpath="", force_flag=True)
            if dn_result < 0:
                log.error("failed to delete NSR of the One-Box: %d %s" %(dn_result, dn_content))
                return -HTTP_Internal_Server_Error, "NS 삭제가 실패하였습니다. One-Box 상태를 확인해 주세요."

        del_result, del_data = delete_server(mydb, onebox_data[0]['serverseq'])
        if del_result < 0:
            log.error("failed to delete One-Box from DB: %d %s" %(del_result, del_data))
            return del_result, del_data

        # 고객삭제 여부 처리
        if update_info.get("is_customer_delete", False):
            # 고객이 다른 One-Box를 사용하고 있는지 체크하고 없으면 삭제.
            result, contents = orch_dbm.get_server_filters_wf(mydb, {"customerseq":onebox_data[0]['customerseq']})
            if result < 0:
                log.error("failed to get server data from DB: %d %s" %(result, contents))
                return result, contents
            elif result > 0: # 다른 One-Box를 사용하는 경우
                return 200, "OTHER"

            # 삭제오더에서 is_customer_delete=True 인 경우 고객을 삭제한다.
            # 삭제되는 고객의 account_id를 Web단으로 넘겨줘야한다. (NMS 삭제처리때문인듯...)
            # account_id 가 존재하는 경우에만 넘겨주고, 없으면 그냥 "OK"를 넘겨주기로 한다.
            account_id = "OK"
            rst_ac, data_ac = orch_dbm.get_account_id_of_customer(mydb, {"customerseq":onebox_data[0]['customerseq']})
            if rst_ac > 0:
                account_id = data_ac["account_id"]

            del_result, del_data = orch_dbm.delete_customer(mydb, onebox_data[0]['customerseq'])
            if del_result < 0:
                log.error("failed to delete customer from DB: %d %s" %(del_result, del_data))
                return del_result, del_data

            return 200, account_id

    else:
        # ORDER_TYPE_OB_NEW OR ORDER_TYPE_OB_UPDATE

        # '취소' 처리
        if update_info.get("order_handle") == "cancel":
            if update_info.get('order_type') == ORDER_TYPE_OB_NEW and onebox_data[0]["status"] == SRVStatus.LWT:
                # 서버삭제
                del_result, del_data = delete_server(mydb, onebox_data[0]['serverseq'])
                if del_result < 0:
                    log.error("failed to delete One-Box from DB: %d %s" %(del_result, del_data))
                    return del_result, del_data

                # 고객삭제
                # 고객이 다른 One-Box를 사용하고 있는지 체크하고 없으면 삭제.
                result, contents = orch_dbm.get_server_filters_wf(mydb, {"customerseq":onebox_data[0]['customerseq']})
                if result < 0:
                    log.error("failed to get server data from DB: %d %s" %(result, contents))
                    return result, contents
                elif result > 0: # 다른 One-Box를 사용하는 경우
                    return 200, "OTHER"

                # 삭제되는 고객의 account_id를 Web단으로 넘겨줘야한다. (NMS 삭제처리때문인듯...)
                # account_id 가 존재하는 경우에만 넘겨주고, 없으면 그냥 "OK"를 넘겨주기로 한다.
                account_id = "OK"
                rst_ac, data_ac = orch_dbm.get_account_id_of_customer(mydb, {"customerseq":onebox_data[0]['customerseq']})
                if rst_ac > 0:
                    account_id = data_ac["account_id"]

                del_result, del_data = orch_dbm.delete_customer(mydb, onebox_data[0]['customerseq'])
                if del_result < 0:
                    log.error("failed to delete customer from DB: %d %s" %(del_result, del_data))
                    return del_result, del_data

                return 200, account_id

            elif update_info.get('order_type') == ORDER_TYPE_OB_UPDATE:
                log.debug("order_handle: cancel, order_type: ORDER_OB_UPDATE : process undefined")

            return 200, "OK"

        # '중단' 처리
        elif update_info.get("order_handle") == "stop":
            if update_info.get('order_type') == ORDER_TYPE_OB_NEW:

                # 서버상태가 "N__PROVISIONING" 이면 중지 안됨.
                if onebox_data[0]['status'] == SRVStatus.PVS:
                    log.debug("_____ 현재 설치가 진행중. 중지 오더를 수행할 수 없음.")
                    return 200, "ING"

                # NS삭제/OB삭제
                if onebox_data[0]['nsseq'] is not None:
                    result, message = delete_nsr(mydb, onebox_data[0]['nsseq'], use_thread=False, force_flag=True)
                    if result < 0:
                        log.error("[NBI OUT] Deleting NSR: Error %d %s" %(-result, message))
                        return result, message
                    log.debug("[NBI OUT] Deleting NSR: OK")

                del_result, del_data = delete_server(mydb, onebox_data[0]['serverseq'])
                if del_result < 0:
                    log.error("failed to delete One-Box from DB: %d %s" %(del_result, del_data))
                    return del_result, del_data
            return 200, "OK"

        # '준공' 처리
        if 'vnf_list' in update_info and len(update_info['vnf_list']) > 0:

            if onebox_data[0].get('nsseq') is None:
                log.error("The One-Box does not have any VNF installed")
                return -HTTP_Not_Found, "The One-Box does not have any VNF installed"

            nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, onebox_data[0]['nsseq'])
            if nsr_result < 0:
                log.error("failed to get NSR, VNF Info from DB: %d %s" %(nsr_result, nsr_data))
                return nsr_result, nsr_data

            # 준공정보를 RLT에 저장처리
            result, rlt_data = orch_dbm.get_rlt_data(mydb, nsr_data["nsseq"])
            if result < 0:
                log.error("failed to get RLT data from DB %d %s" % (result, rlt_data))
                raise Exception("failed to get RLT data from DB %d %s" % (result, rlt_data))

            rlt_dict = rlt_data["rlt"]

            for vnf in nsr_data['vnfs']:
                update_dict = {"nfseq": vnf['nfseq']}
                for vnf_info in update_info['vnf_list']:
                    if vnf_info.get('vnfd_name') == vnf['vnfd_name']:
                        if vnf_info.get('service_number') is not None: update_dict['service_number'] = vnf_info['service_number']
                        if vnf_info.get('service_period') is not None: update_dict['service_period'] = vnf_info['service_period']
                        if vnf_info.get('service_start_dttm') is not None: update_dict['service_start_dttm'] = vnf_info['service_start_dttm']
                        if vnf_info.get('service_end_dttm') is not None: update_dict['service_end_dttm'] = vnf_info['service_end_dttm']

                        for rlt_vnf in rlt_dict["vnfs"]:
                            if vnf['vnfd_name'] == rlt_vnf["vnfd_name"]:
                                if update_dict.get('service_number'):   rlt_vnf["service_number"] =  update_dict['service_number']
                                if update_dict.get('service_period'):   rlt_vnf["service_period"] =  update_dict['service_period']
                                if update_dict.get('service_start_dttm'):   rlt_vnf["service_start_dttm"] =  update_dict['service_start_dttm']
                                if update_dict.get('service_end_dttm'):   rlt_vnf["service_end_dttm"] =  update_dict['service_end_dttm']
                                break
                        break

                update_result, update_data = orch_dbm.update_nsr_vnf(mydb, update_dict)

                if update_result < 0:
                    log.error("failed to update VNF: %d %s" %(update_result, update_data))
                    return update_result, update_data

            rlt_data_up = json.dumps(rlt_dict)

            result, rltseq = orch_dbm.update_rlt_data(mydb, rlt_data_up, rlt_seq=rlt_data['rltseq'])
            if result < 0:
                log.error("failed to DB Update RLT: %d %s" %(result, rltseq))

            if update_info.get('order_type') == ORDER_TYPE_OB_NEW:
                # 준공일 업데이트
                orch_dbm.update_server_delivery_dttm(mydb, onebox_data[0]['serverseq'])

    return 200, "OK"


def backup_onebox_nsr(mydb, onebox_id):

    onebox_result, onebox_data = orch_dbm.get_server_filters(mydb, {"onebox_id": onebox_id})
    if onebox_result < 0:
        log.error("failed to get onebox info from DB: %d %s" %(onebox_result, onebox_data))
        return onebox_result, onebox_data

    # 오더 준공 시, One-Box 백업과 NS 백업을 자동 수행 (Thread로 수행)
    bo_result, bo_content = backup_onebox(mydb, {}, onebox_id, tid = None, tpath = None, use_thread=False)
    if bo_result < 0:
        log.error("Failed to backup One-Box: %d %s" %(bo_result, bo_content))
        return bo_result, bo_content

    nsr_result, nsr_content = backup_nsr(mydb, {}, onebox_data[0].get('nsseq'), tid=None, tpath=None, use_thread=True)
    if nsr_result < 0:
        log.error("Failed to backup NSR: Error %d %s" %(-nsr_result, nsr_content))
        return nsr_result, nsr_content

    return 200, "OK"


def order_update(mydb, server_dict):

    # log.debug("server_dict = %s" %str(server_dict))

    onebox_result, onebox_data = orch_dbm.get_server_filters_wf(mydb, {"onebox_id": server_dict.get('onebox_id')})

    if onebox_result < 0:
        log.error("failed to get onebox info from DB: %d %s" % (onebox_result, onebox_data))
        return onebox_result, onebox_data

    # log.debug("onebox_data = %s" %str(onebox_data))

    ob_data = onebox_data[0]

    if ob_data.get('nfsubcategory') == "KtPnf":
        target_table_name = {'tb_server'}
    else:
        target_table_name = {'tb_server', 'tb_nsr', 'tb_nfr', 'tb_vdu'}

    server_dict['serverseq'] = ob_data.get('serverseq')

    if ob_data.get('nsseq') is not None:
        server_dict['nsseq'] = ob_data.get('nsseq')

    for target in target_table_name:
        log.debug('target table name = %s' %str(target))

        if target == 'tb_nfr' or target == 'tb_nsr' or target == 'tb_vdu':
            if server_dict.get('nsseq') is None:
                continue

        if target == 'tb_nfr':
            # get table info
            get_result, get_data = orch_dbm.get_table_data(mydb, server_dict, table_name=target)

            if get_result < 0:
                log.debug("not found the onebox %s" %str(target))
                return get_result, get_data

            # log.debug("target = %s, get_data = %s" %(str(target), str(get_data)))

            server_dict['nfseq'] = get_data.get('nfseq')

        # update table data
        update_result, update_data = orch_dbm.order_update_server(mydb, server_dict, table_name=target)

        if update_result < 0:
            log.debug("no update to onebox %s" %str(target))
            return update_result, update_data

        log.debug('update OK : target table name = %s' % str(target))

    return 200, "OK"

def order_update_servicenum(mydb, server_dict):
    update_dict = {}
    update_dict['service_number'] = server_dict.get('service_number')

    if server_dict.get('kind') == "onebox":
        # change target DB : tb_server, tb_moniteminstance

        update_dict['serverseq'] = server_dict.get('onebox_id')

        # update table data : tb_server
        update_result, update_data = orch_dbm.order_update_server(mydb, update_dict, table_name="tb_server")

        if update_result < 0:
            log.debug("no update to onebox service number : tb_server")
            return update_result, update_data

        # update table data : tb_moniteminstance
        update_result, update_data = orch_dbm.order_update_server(mydb, update_dict, table_name="tb_moniteminstance")

        if update_result < 0:
            log.debug("no update to onebox service number : tb_moniteminstance")
            return update_result, update_data
    else:
        # change target DB : tb_nfr

        update_dict['nfseq'] = server_dict.get('onebox_id')

        # update table data : tb_moniteminstance
        update_result, update_data = orch_dbm.order_update_server(mydb, update_dict, table_name="tb_nfr")

        if update_result < 0:
            log.debug("no update to onebox service number : tb_nfr")
            return update_result, update_data

    return 200, "OK"