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
DB Manager implements all the methods to interact with DB for KT One-Box Service.
'''
from setuptools.package_index import ContentChecker
from json.decoder import JSONDecoder
__author__="Jechan Han"
__date__ ="$02-Oct-2015 11:19:29$"

import json
import yaml
import os
import time
import sys
import datetime

from utils import auxiliary_functions as af
from orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Conflict

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils.aes_chiper import AESCipher

global global_config
db_debug = False

def filter_query_string(qs, http2db, allowed):
    """
    Process query string (qs) checking that contains only valid tokens for avoiding SQL injection
    Attributes:
        'qs': bottle.FormsDict variable to be processed. None or empty is considered valid
        'http2db': dictionary with change from http API naming (dictionary key) to database naming(dictionary value)
        'allowed': list of allowed string tokens (API http naming). All the keys of 'qs' must be one of 'allowed'
    Return: A tuple with the (select,where,limit) to be use in a database query. All of then transformed to the database naming
        select: list of items to retrieve, filtered by query string 'field=token'. If no 'field' is present, allowed list is returned
        where: dictionary with key, value, taken from the query string token=value. Empty if nothing is provided
        limit: limit dictated by user with the query string 'limit'. 100 by default
    abort if not permited, using bottel.abort
    """
    where={}
    limit=100
    select=[]
    for k in qs:
        if k=='field':
            select += qs.getall(k)
            for v in select:
                if v not in allowed:
                    #bottle.abort(HTTP_Bad_Request, "Invalid query string at 'field="+v+"'")
                    return -HTTP_Bad_Request, "Invalid query string at 'field="+v+"'"
        elif k=='limit':
            try:
                limit=int(qs[k])
            except Exception, e:
                log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
                return -HTTP_Bad_Request, "Invalid query string at 'limit="+qs[k]+"'"
        else:
            if k not in allowed:
                # bottle.abort(HTTP_Bad_Request, "Invalid query string at '"+k+"="+qs[k]+"'")
                return -HTTP_Bad_Request, "Invalid query string at '"+k+"="+qs[k]+"'"
            if qs[k]!="null":  where[k]=qs[k]
            else: where[k]=None 
    if len(select)==0: select += allowed
    #change from http api to database naming
    for i in range(0,len(select)):
        k=select[i]
        if http2db and k in http2db: 
            select[i] = http2db[k]
    if http2db:
        change_keys_http2db(where, http2db)
    
    return select,where,limit


def change_keys_http2db(data, http_db, reverse=False):
    '''Change keys of dictionary data acording to the key_dict values
    This allow change from http interface names to database names.
    When reverse is True, the change is otherwise
    Attributes:
        data: can be a dictionary or a list
        http_db: is a dictionary with hhtp names as keys and database names as value
        reverse: by default change is done from http api to database. If True change is done otherwise
    Return: None, but data is modified'''
    if type(data) is tuple or type(data) is list:
        for d in data:
            change_keys_http2db(d, http_db, reverse)
    elif type(data) is dict or type(data) is bottle.FormsDict:
        if reverse:
            for k,v in http_db.items():
                if v in data: data[k]=data.pop(v)
        else:
            for k,v in http_db.items():
                if k in data: data[v]=data.pop(k)


def insert_user(mydb, data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_user", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_user error %d %s" % (result, content))
    return result, content


def get_user_list(mydb, qs=None):
    if qs:
        select_,where_,limit_ = filter_query_string(qs, None,
                ('userid', 'username','role_id','reg_dttm','modify_dttm') )
    else:
        select_ = ('userid', 'username','role_id','reg_dttm','modify_dttm')
        where_ = {}
        limit_ = 100
        
    result, content = mydb.get_table(FROM='tb_user', SELECT=select_,WHERE=where_,LIMIT=limit_)
    if result < 0:
        log.debug("get_user_list error %d %s" % (result, content))
    return result, content


def get_user_id(mydb, id):
    where_ = {"userid":id}
    
    result, content = mydb.get_table(FROM='tb_user', WHERE=where_)
    if result < 0:
        log.error("get_user_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found User with %s" % str(where_)
    return result, content[0]


def delete_user_id(mydb, id):
    del_column = "userid"
        
    result, content = mydb.delete_row_seq("tb_user", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_user_id error %d %s" % (result, content))
    return result, content


def get_itsm_order_orderid(mydb, order_id):
    result, content = mydb.get_row("tb_itsm_orders", WHERE={"order_id":order_id})
    if result < 0:
        log.error("failed to get ITSM order: %d %s" %(result, content))
    return result, content


def insert_customer(mydb, data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_customer", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_customer error %d %s" % (result, content))
    return result, content


def update_customer(mydb, data):
    WHERE_={'customerseq': data['customerseq']}
    
    data['modify_dttm']=datetime.datetime.now()

    result, content =  mydb.update_rows('tb_customer', data, WHERE_)
    
    if result < 0:
        log.error("update_customer error %d %s" % (result, content))
    return result, content


def get_customer_list(mydb, qs=None):
    if qs:
        select_,where_,limit_ = filter_query_string(qs, None,
                ('customerseq','customername','detailaddr','addrseq','description','emp_cnt','reg_dttm','modify_dttm') )
    else:
        select_ = ('customerseq','customername','detailaddr','addrseq','description','emp_cnt','reg_dttm','modify_dttm')
        where_ = {}
        limit_ = 100
    
    result, content = mydb.get_table(FROM='tb_customer', SELECT=select_,WHERE=where_,LIMIT=limit_)
    if result < 0:
        log.error("get_customer_list error %d %s" % (result, content))
        return result, content
    
    # one-box info.
    for c in content:
        where_ = {"customerseq":c['customerseq']}
        server_result, server_data = mydb.get_table(FROM='tb_server', WHERE=where_)
        if server_result < 0:
            log.warning("get_customer_list failed to get server info %d %s" % (server_result, server_data))
            c['server_seq'] = None
            c['server_name'] = None
            c['server_uuid'] = None
            c['server_mgmtip'] = None
            c['server_reg_dttm'] = None
            c['server_status'] = None
            c['ob_service_number'] = None
            c['vimseq'] = None
        elif server_result == 0:
            #log.warning("Not found Server for the customer %d %s" %(server_result, server_data))
            c['server_seq'] = None
            c['server_name'] = None
            c['server_uuid'] = None
            c['server_mgmtip'] = None
            c['server_reg_dttm'] = None
            c['server_status'] = None
            c['ob_service_number'] = None
            c['vimseq'] = None
        else:
            if len(server_data) > 1:
                c['server_list'] = []
                for s in server_data:
                    s_item = {}
                    af.convert_datetime2str_psycopg2(s)
                    s_item['server_seq'] = s['serverseq']
                    s_item['server_name'] = s['servername']
                    s_item['server_uuid'] = s['serveruuid']
                    s_item['server_mgmtip'] = s['mgmtip']
                    s_item['server_reg_dttm'] = s['reg_dttm']
                    s_item['server_status'] = s['status']
                    s_item['ob_service_number'] = s['ob_service_number']

                    vim_result, vim_data = mydb.get_table(FROM='tb_vim', WHERE={"serverseq":s['serverseq']})
                    if vim_result <= 0:
                        log.warning("get_customer_list failed to get vim info %d %s" %(vim_result, vim_data))
                        s_item['vimseq'] = None
                    else:
                        s_item['vimseq'] = vim_data[0].get("vimseq")

                    c['server_list'].append(s_item)
            else:
                af.convert_datetime2str_psycopg2(server_data[0])

            c['server_seq'] = server_data[0]['serverseq']
            c['server_name'] = server_data[0]['servername']
            c['server_uuid'] = server_data[0]['serveruuid']
            c['server_mgmtip'] = server_data[0]['mgmtip']
            c['server_reg_dttm'] = server_data[0]['reg_dttm']
            c['server_status'] = server_data[0]['status']
            c['ob_service_number'] = server_data[0]['ob_service_number']

            vim_result, vim_data = mydb.get_table(FROM='tb_vim', WHERE={"serverseq":server_data[0]['serverseq']})
            if vim_result <= 0:
                log.warning("get_customer_list failed to get vim info %d %s" %(vim_result, vim_data))
                c['vimseq'] = None
            else:
                c['vimseq'] = vim_data[0].get("vimseq")


    # addr info
    for c in content:
        where_ = {"addrseq":c['addrseq']}
        addr_result, addr_data = mydb.get_table(FROM='tb_addr', WHERE=where_)
        if addr_result <= 0:
            #log.warning("Use tb_customer.detailaddr for ADDR field, because get_customer_list failed to get addr %d %s" %(addr_result, addr_data))
            c['addr'] = c['detailaddr']            
        else:
            if addr_data[0].get("addr1"):
                c['addr'] = addr_data[0].get("addr1")
            if addr_data[0].get("addr2"):
                c['addr'] = c['addr'] + " " + addr_data[0].get("addr2")
            if addr_data[0].get("addr3"):
                c['addr'] = c['addr'] + " " + addr_data[0].get("addr3")
            if addr_data[0].get("addr4"):
                c['addr'] = c['addr'] + " " + addr_data[0].get("addr4")
            
    return result, content    


def get_customer_id(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {"customerseq":id} 
    elif id.isdigit():
        where_ = {"customerseq":id}
    else:
        where_ = {"customername":id}
        
    result, content = mydb.get_table(FROM='tb_customer', WHERE=where_)
    if result < 0:
        log.error("get_customer_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return result, "Not found Customer with %s" %(str(where_))
    
    #TODO: use detailaddr rather than addr
    content[0]['addr'] = content[0]['detailaddr']
    
    return result, content[0]


def get_customer_ename(mydb, ename):
    where_ = {"customerename":ename}

    result, content = mydb.get_table(FROM='tb_customer', WHERE=where_)
    if result < 0:
        log.error("get_customer_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return result, "Not found Customer with %s" %(str(where_))

    #TODO: use detailaddr rather than addr
    content[0]['addr'] = content[0]['detailaddr']

    return result, content[0]


def delete_customer(mydb, id):
    if type(id) is int or type(id) is long:
        del_column = 'customerseq' 
    elif id.isdigit():
        del_column = 'customerseq'
    else:
        del_column = 'customername'

    # 추가 : tb_customer_account.customer_seq fk 제거로 인하여 tb_customer_account 삭제 추가됨
    rs, ct = _delete_customer_account(mydb, id)
    
    result, content = mydb.delete_row_seq("tb_customer", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_customer error %d %s" % (result, content))

    return result, content


def _delete_customer_account(mydb, customerseq):
    if type(customerseq) is int or type(customerseq) is long:
        del_column = 'customer_seq'
    elif customerseq.isdigit():
        del_column = 'customer_seq'
    else:
        del_column = 'customer_seq'

    result, content = mydb.delete_row_seq("tb_customer_account", del_column, customerseq, None, db_debug)
    if result < 0:
        log.debug("delete_customer_account error %d %s" % (result, content))
        log.error("delete_customer_account error %d %s" % (result, content))
    return result, content


def delete_customer_office(mydb, cond_dict):

    if "customerseq" in cond_dict:
        del_column = 'customerseq'
    elif "officeseq" in cond_dict:
        del_column = 'officeseq'
    else:
        return -HTTP_Bad_Request, cond_dict

    result, content = mydb.delete_row_seq("tb_customer_office", del_column, cond_dict[del_column], None, db_debug)
    if result < 0:
        log.error("delete_customer_office error %d %s" % (result, content))
    return result, content


def get_customer_resources(mydb, id, onebox_id=None):
    r, customer_dict = get_customer_id(mydb, id)
    if r <= 0:
        log.error("failed to get customer Info from DB %d %s" % (r, customer_dict))
        return -HTTP_Not_Found, customer_dict
    
    #log.debug("customer_dict: %s" %str(customer_dict))
    
    resource_list = []
    
    # ponebox
    if onebox_id is not None:
        r, servers = mydb.get_table(FROM='tb_server', WHERE={'onebox_id':onebox_id})
    else:
        r, servers = mydb.get_table(FROM='tb_server', WHERE={'customerseq':customer_dict['customerseq']})

    if r < 0:
        return -HTTP_Internal_Server_Error, servers
    if r > 0:
        for item in servers:
            item['resource_type']='server'
            resource_list.append(item)
            
            r, vims = mydb.get_table(FROM='tb_vim', WHERE={'serverseq':item['serverseq']})
            if r < 0:
                return -HTTP_Internal_Server_Error, vims
            if r > 0:
                for vim in vims:
                    vim['resource_type']='vim'
                    resource_list.append(vim)
        
    # ns_order
    
    # ns instances
    #r, nsrs = mydb.get_table(FROM='tb_nsr', WHERE={'customerseq':customer_dict['customerseq']})
    #if r < 0:
    #    return -HTTP_Internal_Server_Error, nsrs
    #if r > 0:
    #    for item in nsrs:
    #        item['resource_type']='nsr'
    #        resource_list.append(item)
    
    #log.debug("the number of resources for the customer %s: %d" % (id, len(resource_list)))
    return len(resource_list), resource_list 


def insert_customeroffice(mydb, data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_customer_office", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_customeroffice error %d %s" % (result, content))
    return result, content


def update_customeroffice(mydb, data):
    WHERE_={'officeseq': data['officeseq']}

    data['modify_dttm']=datetime.datetime.now()

    result, content =  mydb.update_rows('tb_customer_office', data, WHERE_)

    if result < 0:
        log.error("update_customeroffice error %d %s" % (result, content))
    return result, content


def get_customeroffice_id(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {"officeseq":id}
    elif id.isdigit():
        where_ = {"officeseq":id}
    else:
        where_ = {"officename":id}

    result, content = mydb.get_table(FROM='tb_customer_office', WHERE=where_)
    if result < 0:
        log.error("get_customeroffice_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return result, "Not found Customer Office with %s" %(str(where_))

    return result, content[0]


def get_customeroffice_ofcustomer(mydb, customerseq):
    where_ = {"customerseq": customerseq}

    result, content = mydb.get_table(FROM='tb_customer_office', WHERE=where_)
    if result < 0:
        log.error("get_customeroffice_ofcustomer error %d %s" % (result, content))
    elif result == 0:
        return result, "Not found Customer Office with %s" %(str(where_))

    return result, content


def insert_onebox_line(mydb, data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_onebox_line", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_onebox_line error %d %s" % (result, content))
    return result, content


def get_onebox_line_id(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {"seq":id}
    elif id.isdigit():
        where_ = {"seq":id}
    else:
        where_ = {"name":id}

    result, content = mydb.get_table(FROM='tb_onebox_line', WHERE=where_)
    if result < 0:
        log.error("get_onebox_line_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return result, "Not found One-Box Network Line with %s" %(str(where_))

    return result, content[0]


def get_onebox_line_ofonebox(mydb, serverseq):
    where_ = {"serverseq": serverseq}

    result, content = mydb.get_table(FROM='tb_onebox_line', WHERE=where_)
    if result < 0:
        log.error("get_onebox_line_ofonebox error %d %s" % (result, content))
    elif result == 0:
        return result, "Not found One-Box Network Line with %s" %(str(where_))

    return result, content


def insert_serviceorder_said(mydb, data):
    result, content = mydb.new_row("tb_itsm_said", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_serviceorder_said error %d %s" % (result, content))
    return result, content


def update_serviceorder_said(mydb, data):
    WHERE_={'said': data['said']}
    
    UPDATE_ = {}
    if 'nscatalog_name' in data:
        UPDATE_['nscatalog_name'] = data['nscatalog_name']
    if 'nscatalog_version' in data:
        UPDATE_['nscatalog_version'] = data['nscatalog_version']
    
    result, content =  mydb.update_rows('tb_itsm_said', UPDATE_, WHERE_)
    
    if result < 0:
        log.error("update_serviceorder_said error %d %s" % (result, content))
    return result, content


def get_serviceorder_said(mydb, nscatalog_name=None, qs=None):
    select_ = ('said','nscatalog_name','nscatalog_version')
    where_ = {}
    if nscatalog_name:
        where_['nscatalog_name']=nscatalog_name
    limit_ = 100
    
    result, content = mydb.get_table(FROM='tb_itsm_said', SELECT=select_,WHERE=where_,LIMIT=limit_)
    if result < 0:
        log.error("get_serviceorder_said error %d %s" % (result, content))
    return result, content


def insert_swrepo_sw(mydb, data):
    result, content = mydb.new_row("tb_global_sw", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_swrepo_sw error %d %s" % (result, content))
    return result, content


def get_swrepo_sw_list(mydb, qs=None):
    if qs:
        select_,where_,limit_ = filter_query_string(qs, None,
                ('seq', 'type','name','version','metadata','reg_dttm','modify_dttm') )
    else:
        select_ = ('seq', 'type','name','version','metadata','reg_dttm','modify_dttm')
        where_ = {}
        limit_ = 100
        
    result, content = mydb.get_table(FROM='tb_global_sw', SELECT=select_,WHERE=where_,LIMIT=limit_)
    if result < 0:
        log.debug("get_swrepo_sw_list error %d %s" % (result, content))
    return result, content


def get_swrepo_sw_id(mydb, id):
    where_ = {"seq":id}
    
    result, content = mydb.get_table(FROM='tb_global_sw', WHERE=where_)
    if result < 0:
        log.error("get_swrepo_sw_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found S/W with %s" % str(where_)
    return result, content[0]


def delete_swrepo_sw_id(mydb, id):
    del_column = "seq"
        
    result, content = mydb.delete_row_seq("tb_global_sw", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_swrepo_id error %d %s" % (result, content))
    return result, content


def insert_onebox_flavor(mydb, data):
    result, content = mydb.new_row("tb_onebox_flavor", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_onebox_flavor error %d %s" % (result, content))
    return result, content


def get_onebox_flavor_list(mydb, qs=None):
    if qs:
        select_,where_,limit_ = filter_query_string(qs, None,
                ('seq', 'name','hw_model','metadata','reg_dttm','modify_dttm', 'nfsubcategory') )
    else:
        select_ = ('seq', 'name','hw_model','metadata','reg_dttm','modify_dttm', 'nfsubcategory')
        where_ = {}
        limit_ = 100
        
    result, content = mydb.get_table(FROM='tb_onebox_flavor', SELECT=select_,WHERE=where_,LIMIT=limit_)
    if result < 0:
        log.debug("get_onebox_flavor_list error %d %s" % (result, content))
    return result, content


def get_onebox_flavor_name(mydb, name):
    where_ = {"name":name}

    result, content = mydb.get_table(FROM='tb_onebox_flavor', WHERE=where_)
    if result < 0:
        log.error("get_onebox_flavor_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found One-Box flavor with %s" % str(where_)
    return result, content[0]


def get_onebox_flavor_id(mydb, id):
    where_ = {"seq":id}
    
    result, content = mydb.get_table(FROM='tb_onebox_flavor', WHERE=where_)
    if result < 0:
        log.error("get_onebox_flavor_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found One-Box flavor with %s" % str(where_)
    return result, content[0]


def delete_onebox_flavor_id(mydb, id):
    del_column = "seq"
        
    result, content = mydb.delete_row_seq("tb_onebox_flavor", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_onebox_flavor_id error %d %s" % (result, content))
    return result, content


def insert_server(mydb, server_dict):#, vim_dict=None, vim_tenant_dict=None, hardware_dict=None, software_dict=None, network_list=None, vnet_dict=None):

    insert_server_ = {'servername':server_dict['servername']}
    if 'description' in server_dict:        insert_server_['description'] = server_dict['description']
    if 'orgnamescode' in server_dict:       insert_server_['orgnamescode'] = server_dict['orgnamescode']
    if 'nfmaincategory' in server_dict:     insert_server_['nfmaincategory'] = server_dict['nfmaincategory']
    if 'nfsubcategory' in server_dict:      insert_server_['nfsubcategory'] = server_dict['nfsubcategory']
    if 'mgmtip' in server_dict:             insert_server_['mgmtip'] = server_dict['mgmtip']
    if 'serveruuid' in server_dict:         insert_server_['serveruuid'] = server_dict['serveruuid']
    if 'nsseq' in server_dict:              insert_server_['nsseq'] = server_dict['nsseq']
    if 'state' in server_dict:              insert_server_['state'] = server_dict['state']
    if 'stock_dttm' in server_dict:         insert_server_['stock_dttm'] = server_dict['stock_dttm']
    if 'deliver_dttm' in server_dict:       insert_server_['deliver_dttm'] = server_dict['deliver_dttm']
    if 'customerseq' in server_dict:        insert_server_['customerseq'] = server_dict['customerseq']
    if 'action' in server_dict:             insert_server_['action'] = server_dict['action']
    if 'publicip' in server_dict:           insert_server_['publicip'] = server_dict['publicip']
    if 'serial_no' in server_dict:          insert_server_['serial_no'] = server_dict['serial_no']
    if 'vnfm_base_url' in server_dict:      insert_server_['vnfm_base_url'] = server_dict['vnfm_base_url']
    if 'obagent_base_url' in server_dict:   insert_server_['obagent_base_url'] = server_dict['obagent_base_url']
    if 'status' in server_dict:             insert_server_['status'] = server_dict['status']
    if 'onebox_id' in server_dict:          insert_server_['onebox_id'] = server_dict['onebox_id']
    if 'onebox_flavor' in server_dict:      insert_server_['onebox_flavor'] = server_dict['onebox_flavor']
    if 'vnfm_version' in server_dict:       insert_server_['vnfm_version'] = server_dict['vnfm_version']
    if 'obagent_version' in server_dict:    insert_server_['obagent_version'] = server_dict['obagent_version']
    if 'publicmac' in server_dict:          insert_server_['publicmac'] = server_dict['publicmac']
    if 'net_mode' in server_dict:           insert_server_['net_mode'] = server_dict['net_mode']
    if 'orgcustmcode' in server_dict:       insert_server_['orgcustmcode'] = server_dict['orgcustmcode']
    if 'officeseq' in server_dict:          insert_server_['officeseq'] = server_dict['officeseq']
    if 'ob_service_number' in server_dict:  insert_server_['ob_service_number'] = server_dict['ob_service_number']
    if 'ipalloc_mode_public' in server_dict:insert_server_['ipalloc_mode_public'] = server_dict['ipalloc_mode_public']
    if 'publicgwip' in server_dict:         insert_server_['publicgwip'] = server_dict['publicgwip']
    if 'publiccidr' in server_dict:         insert_server_['publiccidr'] = server_dict['publiccidr']
    if 'mgmt_nic' in server_dict:           insert_server_['mgmt_nic'] = server_dict['mgmt_nic']
    if 'public_nic' in server_dict:         insert_server_['public_nic'] = server_dict['public_nic']

    server_result, serverseq = mydb.new_row("tb_server", insert_server_, None, add_uuid=False, log=db_debug)
    if server_result < 0:
        log.error("insert_server error %d %s" % (server_result, server_result))
        return server_result, serverseq
    #server_dict['serverseq'] = serverseq

    # 이 함수가 server_dict 외에 다른 parameter를 받아서 살용하는 경우는 실제로 없다.
    # 아래 로직은 현재 적용되지 않는다. 일단 주석처리함.
    # if vim_dict:
    #     vim_dict['serverseq']=serverseq
    #     vim_result, vimseq = mydb.new_row("tb_vim", vim_dict, None, add_uuid=False, log=db_debug)
    #     if vim_result < 0:
    #         log.error("insert_server error %d %s" %(vim_result, vimseq))
    #         return vim_result, vimseq
    #
    #     server_dict['vimseq']=vimseq
    #
    #     if vim_tenant_dict:
    #         vim_tenant_dict['vimseq']=vimseq
    #         vim_tenant_result, vim_tenantseq = mydb.new_row("tb_vim_tenant", vim_tenant_dict, None, add_uuid=False, log=db_debug)
    #         if vim_tenant_result < 0:
    #             log.error("insert_server error %d %s" %(vim_tenant_result, vim_tenantseq))
    #             return vim_result, vimseq
    #
    # if hardware_dict:
    #     hardware_dict['serverseq']=serverseq
    #     hw_result, hwseq = mydb.new_row("tb_onebox_hw", hardware_dict, None, add_uuid=False, log=db_debug)
    #     if hw_result < 0:
    #         log.warning("insert_server error %d %s" %(hw_result, hwseq))
    #
    # if software_dict:
    #     software_dict['serverseq']=serverseq
    #     sw_result, swseq = mydb.new_row("tb_onebox_sw", software_dict, None, add_uuid=False, log=db_debug)
    #     if sw_result < 0:
    #         log.warning("insert_server error %d %s" %(sw_result, swseq))
    #
    # if network_list and len(network_list) > 0:
    #     for network_dict in network_list:
    #         network_dict['serverseq']=serverseq
    #         nw_result, nwseq = mydb.new_row('tb_onebox_nw', network_dict, None, add_uuid=False, log=db_debug)
    #         if nw_result < 0:
    #             log.warning("insert network info %d %s" %(nw_result, nwseq))
    #
    # if vnet_dict:
    #     result, content = mydb.new_row('tb_server_vnet', vnet_dict, tenant_id=None, add_uuid=False, log=db_debug)
    #     if result < 0:
    #         log.warning("Failed to insert new server_vnet: %d %s" %(result, content))

    return server_result, serverseq


def update_server(mydb, server_dict):
    """
    server 정보 업데이트
    :param mydb:
    :param server_dict:
    :return:
    """
    where_ = {'serverseq': server_dict['serverseq']}
    update_ = {}
    if 'mgmtip' in server_dict: update_['mgmtip'] = server_dict['mgmtip']
    if 'publicip' in server_dict: update_['publicip'] = server_dict['publicip']
    if 'ipalloc_mode_public' in server_dict: update_['ipalloc_mode_public'] = server_dict['ipalloc_mode_public']
    if 'publicmac' in server_dict: update_['publicmac'] = server_dict['publicmac']
    if 'publicgwip' in server_dict: update_['publicgwip'] = server_dict['publicgwip']
    if 'publiccidr' in server_dict: update_['publiccidr'] = server_dict['publiccidr']
    if 'serial_no' in server_dict: update_['serial_no'] = server_dict['serial_no']
    if 'onebox_flavor' in server_dict: update_['onebox_flavor'] = server_dict['onebox_flavor']
    if 'vnfm_base_url' in server_dict: update_['vnfm_base_url'] = server_dict['vnfm_base_url']
    if 'vnfm_version' in server_dict: update_['vnfm_version'] = server_dict['vnfm_version']
    if 'obagent_base_url' in server_dict: update_['obagent_base_url'] = server_dict['obagent_base_url']
    if 'obagent_version' in server_dict: update_['obagent_version'] = server_dict['obagent_version']
    if 'status' in server_dict: update_['status'] = server_dict['status']
    if 'state' in server_dict: update_['state'] = server_dict['state']
    if 'serveruuid' in server_dict: update_['serveruuid'] = server_dict['serveruuid']
    if 'net_mode' in server_dict: update_['net_mode'] = server_dict['net_mode']
    if 'officeseq' in server_dict: update_['officeseq'] = server_dict['officeseq']
    if 'ob_service_number' in server_dict: update_['ob_service_number'] = server_dict['ob_service_number']
    if 'description' in server_dict:
        log.debug("Description: %s" %server_dict['description'])
        update_['description'] = server_dict['description']

    # mgmt_nic, public_nic 처리
    if 'mgmt_nic' in server_dict: update_['mgmt_nic'] = server_dict['mgmt_nic']
    if 'public_nic' in server_dict: update_['public_nic'] = server_dict['public_nic']

    if 'customerseq' in server_dict: update_['customerseq'] = server_dict['customerseq']
    # if 'orgnamescode' in server_dict: update_['orgnamescode'] = server_dict['orgnamescode']
    if 'action' in server_dict: update_['action'] = server_dict['action']
    if 'nsseq' in server_dict: update_['nsseq'] = server_dict['nsseq']

    # ha 구성일 경우 : bonding or ha
    if 'ha' in server_dict: update_['ha'] = server_dict['ha']
    if 'master_seq' in server_dict: update_['master_seq'] = server_dict['master_seq']

    if len(update_) == 0:
        return -HTTP_Bad_Request, "No Update Data"

    update_['modify_dttm'] = datetime.datetime.now()
    server_result, content = mydb.update_rows('tb_server', update_, where_)
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, content))
        return server_result, content

    return server_result, server_dict['serverseq']

def order_update_server(mydb, update_dict, table_name):
    """
    server 정보 업데이트
    :param mydb:
    :param update_dict:
    :param table_name:
    :return:
    """

    # log.debug("table_name = %s, update_dict = %s" %(str(table_name), str(update_dict)))

    if table_name == "tb_nsr":
        where_ = {'nsseq': update_dict.get('nsseq')}
    elif table_name == 'tb_nfr':
        if 'nfseq' in update_dict:
            where_ = {'nfseq': update_dict.get('nfseq')}
        else:
            where_ = {'nsseq': update_dict.get('nsseq')}
    elif table_name == "tb_vdu":
        where_ = {'nfseq': update_dict.get('nfseq')}
    else:
        # tb_server
        where_ = {'serverseq': update_dict['serverseq']}

    update_ = {}

    for k, v in update_dict.items():
        # 필요없는 key 는 continue
        if k == 'serverseq' or k == 'onebox_id' or k == 'nsseq' or k == 'nfseq' or k == 'nfsubcategory':
            continue

        if k == "org_name":
            update_['orgnamescode'] = v
        else:
            if k == 'service_number':
                if table_name == 'tb_server':
                    update_['ob_service_number'] = v
                else:
                    update_[k] = v
            else:
                update_[k] = v

    if len(update_) == 0:
        return -HTTP_Bad_Request, "No Update Data"

    if table_name is not 'tb_moniteminstance':
        update_['modify_dttm'] = datetime.datetime.now()

    server_result, content = mydb.update_rows(table_name, update_, where_)
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, content))
        return server_result, content

    return server_result, "OK"


def update_server_oba(mydb, server_dict, vim_dict=None, vim_tenant_dict=None, hardware_dict=None, software_dict=None, network_list=None, vnet_dict=None):
    """
    server 정보 업데이트
    :param mydb:
    :param server_dict:
    :param vim_dict:
    :param vim_tenant_dict:
    :param hardware_dict:
    :param software_dict:
    :param network_list:
    :param vnet_dict:
    :return:
    """
    where_ = {'serverseq': server_dict['serverseq']}
    update_ = {}
    if 'mgmtip' in server_dict: update_['mgmtip'] = server_dict['mgmtip']
    if 'publicip' in server_dict: update_['publicip'] = server_dict['publicip']
    if 'ipalloc_mode_public' in server_dict: update_['ipalloc_mode_public'] = server_dict['ipalloc_mode_public']
    if 'publicmac' in server_dict: update_['publicmac'] = server_dict['publicmac']
    if 'publicgwip' in server_dict: update_['publicgwip'] = server_dict['publicgwip']
    if 'publiccidr' in server_dict: update_['publiccidr'] = server_dict['publiccidr']
    if 'serial_no' in server_dict: update_['serial_no'] = server_dict['serial_no']
    if 'onebox_flavor' in server_dict: update_['onebox_flavor'] = server_dict['onebox_flavor']
    if 'vnfm_base_url' in server_dict: update_['vnfm_base_url'] = server_dict['vnfm_base_url']
    if 'vnfm_version' in server_dict: update_['vnfm_version'] = server_dict['vnfm_version']
    if 'obagent_base_url' in server_dict: update_['obagent_base_url'] = server_dict['obagent_base_url']
    if 'obagent_version' in server_dict: update_['obagent_version'] = server_dict['obagent_version']
    if 'status' in server_dict: update_['status'] = server_dict['status']
    if 'state' in server_dict: update_['state'] = server_dict['state']
    if 'serveruuid' in server_dict: update_['serveruuid'] = server_dict['serveruuid']
    if 'net_mode' in server_dict: update_['net_mode'] = server_dict['net_mode']
    if 'officeseq' in server_dict: update_['officeseq'] = server_dict['officeseq']
    if 'ob_service_number' in server_dict: update_['ob_service_number'] = server_dict['ob_service_number']
    if 'description' in server_dict:
        # log.debug("Description: %s" %server_dict['description'])
        update_['description'] = server_dict['description']

    # 5G router 사용 여부
    if 'router' in server_dict:
        update_['router'] = server_dict['router']
    else:
        # router 가 아닐 때, router 사용 하다가 장비 교체등의 이유로 사용하지 않게 되었을 때
        update_['router'] = None

    # HA 구성 : bonding or HA
    if 'ha' in server_dict:
        update_['ha'] = server_dict['ha']

    # mgmt_nic, public_nic 처리
    if 'mgmt_nic' in server_dict: update_['mgmt_nic'] = server_dict['mgmt_nic']
    if 'public_nic' in server_dict: update_['public_nic'] = server_dict['public_nic']

    if len(update_) == 0:
        return -HTTP_Bad_Request, "No Update Data"
    
    update_['modify_dttm'] = datetime.datetime.now()

    # log.debug('update_ = %s' %str(update_))

    server_result, content = mydb.update_rows('tb_server', update_, where_)
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, content))
        return server_result, content


    # 회선이중화 : wan_list 저장 / WAN 추가/삭제 동작 중일때는 생략.
    if "wan_list" in server_dict and not server_dict.get("is_wad", False):
        # tb_server_wan에 값이 없는 경우에만 저장처리.
        # 변경된 정보 수정처리는 뒷단에서 하므로 이 부분에서는 생략.

        is_create = False

        db_wan_result, db_wan_list = get_server_wan_list(mydb, server_dict["serverseq"])

        if db_wan_result < 0:
            return db_wan_result, db_wan_list
        elif db_wan_result > 0:
            # NSR 설치된 경우 : 기존 항목을 그대로 사용한다.
            # 설치가 안된 경우 : 추가/삭제된 경우(갯수가 달라진 경우) 기존 WAN 삭제 후 변경된 내용 저장처리
            if "nsseq" in server_dict:
                is_create = False
            else:
                if db_wan_result != len(server_dict["wan_list"]):
                    # 기존 wan 전부 삭제
                    wan_result, wan_content = delete_server_wan(mydb, {"serverseq":server_dict["serverseq"]}, kind="R")
                    if wan_result < 0:
                        return wan_result, wan_content

                    is_create = True

                    # 뒷단에서 wan 변경 체크 및 update를 하면 안된다.
                    server_dict["is_wan_count_changed"] = True
        else:
            # WAN 정보가 없는 경우.
            is_create = True

        if is_create:
            for wan in server_dict["wan_list"]:
                wan["serverseq"] = server_dict["serverseq"]
                wan["onebox_id"] = server_dict.get("onebox_id")

                wan_result, content = insert_server_wan(mydb, wan)
                if wan_result < 0:
                    return wan_result, content

    if "extra_wan_list" in server_dict:
        # tb_server_wan에 값이 없는 경우에만 저장처리.
        is_create = False
        db_wan_result, db_wan_list = get_server_wan_list(mydb, server_dict["serverseq"], kind="E")
        if db_wan_result < 0:
            return db_wan_result, db_wan_list
        elif db_wan_result > 0:
            # NSR 설치된 경우 : 기존 항목을 그대로 사용한다.
            # 설치가 안된 경우 : 추가/삭제된 경우(갯수가 달라진 경우) 기존 WAN 삭제 후 변경된 내용 저장처리
            if "nsseq" in server_dict:
                is_create = False
            else:
                if db_wan_result != len(server_dict["extra_wan_list"]):
                    # 기존 extra wan 전부 삭제
                    wan_result, wan_content = delete_server_wan(mydb, {"serverseq":server_dict["serverseq"]}, kind="E")
                    if wan_result < 0:
                        return wan_result, wan_content
                    is_create = True

                    # 뒷단에서 extra_wan 변경 체크 및 update를 하면 안된다.
                    server_dict["is_extra_wan_count_changed"] = True
        else:
            is_create = True

        if is_create:
            for wan in server_dict["extra_wan_list"]:
                wan["serverseq"] = server_dict["serverseq"]
                wan["onebox_id"] = server_dict.get("onebox_id")

                wan_result, content = insert_server_wan(mydb, wan)
                if wan_result < 0:
                    return wan_result, content
    else:
        # extra_wan_list 가 설정되었다가 삭제되었을 경우 DB 에서 제거처리.
        db_wan_result, db_wan_list = get_server_wan_list(mydb, server_dict["serverseq"], kind="E")
        if db_wan_result > 0:
            if "nsseq" not in server_dict:
                log.warning("Delete old Extra WAN list!!!")
                wan_result, wan_content = delete_server_wan(mydb, {"serverseq":server_dict["serverseq"]}, kind="E")
            else:
                try:
                    # resourcetemplate에서 extra_wan을 사용하는 vnf가 있는지 확인하고 없으면 삭제.
                    result, rsctp = get_resourcetemplate_nscatalog(mydb, server_dict["nsseq"])
                    if result > 0:
                        if str(rsctp["resourcetemplate"]).find("PNET_extrawan") >= 0:
                            log.warning("No extra_wan_list in OBA Info!!!")
                            pass
                        else:
                            result, content = delete_server_wan(mydb, {"serverseq":server_dict["serverseq"]}, kind="E")
                except Exception, e1:
                    log.warning("Error in deleting extra_wan!!!")

    if vim_dict:
        pre_vim_result, pre_vim_data = get_vim_serverseq(mydb, server_dict['serverseq'])
        if pre_vim_result > 0:
            #log.debug("update_server() vim already exists %s" %str(pre_vim_data[0]['vimseq']))
            vim_dict['modify_dttm']=datetime.datetime.now()
            vim_result, vim_data = mydb.update_rows('tb_vim', vim_dict, {"vimseq":pre_vim_data[0]['vimseq']})
            
            if vim_result < 0:
                log.error("update_server error %d %s" %(vim_result, vim_data))
                return vim_result, vim_data
            
            vimseq = pre_vim_data[0]['vimseq']
        else:
            #log.debug("update_server() insert DB into tb_vim")
            vim_dict['serverseq']=server_dict['serverseq']
        
            vim_result, vimseq = mydb.new_row("tb_vim", vim_dict, tenant_id=None, add_uuid=False, log=db_debug)
            
            if vim_result < 0:
                log.error("update_server error %d %s" %(vim_result, vimseq))
                return vim_result, vimseq
        
        server_dict['vimseq'] = vimseq
        
        if vim_tenant_dict:
            pre_vt_result, pre_vt_data = get_vim_tenant_id(mydb, vim_tenant_id=None, vim_tenant_name=None, vim_id=vimseq)
            if pre_vt_result > 0:
                #log.debug("update_server() vim_tenant already exists %s" %str(pre_vt_data[0]['vimtenantseq']))
                vim_tenant_dict['modify_dttm']=datetime.datetime.now()
                vt_result, vt_seq = mydb.update_rows('tb_vim_tenant', vim_tenant_dict, {"vimtenantseq": pre_vt_data[0]['vimtenantseq']})
            else:
                #log.debug("update_server() insert DB into tb_vim_tenant")    
                vim_tenant_dict['vimseq']=vimseq
                vt_result, vt_seq = mydb.new_row("tb_vim_tenant", vim_tenant_dict, None, add_uuid=False, log=db_debug)
            
            if vt_result < 0:
                log.error("update_server() error %d %s" %(vt_result, str(vt_seq)))
                return vt_result, vt_seq
    
    if hardware_dict:
        pre_hw_result, pre_hw_data = get_onebox_hw_serverseq(mydb, server_dict['serverseq'])
        if pre_hw_result > 0:
            #log.debug("update_server() Hardware Info already exists %s" %str(pre_hw_data[0]['seq']))
            hardware_dict['modify_dttm']=datetime.datetime.now()
            hw_result, hw_data = mydb.update_rows('tb_onebox_hw', hardware_dict, {"seq":pre_hw_data[0]['seq']})
            
            if hw_result < 0:
                log.warning("update_server error %d %s" %(hw_result, hw_data))
        else:
            hardware_dict['serverseq']=server_dict['serverseq']
        
            hw_result, hwseq = mydb.new_row("tb_onebox_hw", hardware_dict, None, add_uuid=False, log=db_debug)
            
            if hw_result < 0:
                log.warning("update_server error %d %s" %(hw_result, hwseq))
    
    if software_dict:
        pre_sw_result, pre_sw_data = get_onebox_sw_serverseq(mydb, server_dict['serverseq'])
        if pre_sw_result > 0:
            #log.debug("update_server() Software Info already exists %s" %str(pre_sw_data[0]['seq']))
            software_dict['modify_dttm']=datetime.datetime.now()
            sw_result, sw_data = mydb.update_rows('tb_onebox_sw', software_dict, {"seq":pre_sw_data[0]['seq']})
            
            if sw_result < 0:
                log.warning("update_server error %d %s" %(sw_result, sw_data))
        else:
            #log.debug("update_server() insert DB into tb_onebox_sw")
            software_dict['serverseq']=server_dict['serverseq']
        
            sw_result, swseq = mydb.new_row("tb_onebox_sw", software_dict, None, add_uuid=False, log=db_debug)
            
            if sw_result < 0:
                log.warning("update_server error %d %s" %(sw_result, swseq))
    
    if network_list:
        where_ = {'serverseq': server_dict['serverseq']}
        deleted, content = mydb.delete_row_by_dict(FROM="tb_onebox_nw", WHERE=where_)
        if deleted < 0:
            log.error("Failed to update One-Box Network Info: %d %s" %(deleted, content))
            return deleted, content
        
        for new_net in network_list:
            new_net['serverseq'] = server_dict['serverseq']
            result, content = mydb.new_row('tb_onebox_nw', new_net, tenant_id=None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("Failed to update One-Box Networ for %s. Cause: %d %s" %(str(new_net), result, content))  
        
    if vnet_dict:
        where_ = {'serverseq': server_dict['serverseq']}
        deleted, content = mydb.delete_row_by_dict(FROM='tb_server_vnet', WHERE=where_)
        if deleted < 0:
            log.warning("Failed to delete old server_vnet: %d %s" %(deleted, content))
        else:
            vnet_dict['serverseq'] = server_dict['serverseq']
            result, content = mydb.new_row('tb_server_vnet', vnet_dict, tenant_id=None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("Failed to insert new server_vnet: %d %s" %(result, content))

    return server_result, server_dict['serverseq']


def update_server_status(mydb, server_dict, is_action=False):
    WHERE_={'serverseq': server_dict['serverseq']}

    UPDATE_ = {}

    if 'status' in server_dict: # 필수값
        UPDATE_['status'] = server_dict['status']

    if is_action and 'action' in server_dict:
        UPDATE_['action'] = server_dict['action']

    UPDATE_['modify_dttm']=datetime.datetime.now()

    result, content =  mydb.update_rows('tb_server', UPDATE_, WHERE_)
    if result < 0:
        log.error('update_server_status Error ' + content + ' updating table tb_server: ' + str(server_dict['serverseq']))
    return result, server_dict['serverseq']


def update_server_action(mydb, server_dict):

    WHERE_={'serverseq': server_dict['serverseq']}
    UPDATE_ = {}

    if 'action' in server_dict:
        UPDATE_['action'] = server_dict['action']
    else:
        return -500, "No action!!!"

    UPDATE_['modify_dttm']=datetime.datetime.now()

    result, content =  mydb.update_rows('tb_server', UPDATE_, WHERE_)
    if result < 0:
        log.error('update_server_action Error ' + content + ' updating table tb_server: ' + str(server_dict['serverseq']))
    return result, server_dict['serverseq']


def get_server(mydb, qs=None):

    select_ = ('serverseq','servername','description', 'serveruuid', 'reg_dttm', 'modify_dttm', 'customerseq','status', 'state', 'nfsubcategory', 'onebox_id', 'onebox_flavor', 'ob_service_number')
    # where_ = {'nfsubcategory':"One-Box"}
    where_ = {}
    where_not_ = {'nfsubcategory':"System"}
    limit_ = 100
    
    result, content = mydb.get_table(FROM='tb_server', SELECT=select_,WHERE=where_, WHERE_NOT=where_not_, LIMIT=limit_)
    if result < 0:
        log.error("get_server error %d %s" % (result, content))
    return result, content


def get_server_id(mydb, id):

    if type(id) is int or type(id) is long:
        where_ = {"serverseq":id} 
    elif id.isdigit():
        where_ = {"serverseq":id}
    else:
        where_ = {"servername":id}
            
    result, content = mydb.get_table(FROM='tb_server', WHERE=where_)
    if result < 0:
        log.error("get_server_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found Server with %s" %str(where_)
    return result, content[0]


def get_db_server(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {"serverseq": id}
    elif id.isdigit():
        where_ = {"serverseq": id}
    else:
        where_ = {"servername": id}

    result, content = mydb.get_table(FROM='tb_server', WHERE=where_)
    if result < 0:
        log.error("get_db_server error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found Server with %s" % str(where_)
    return result, content[0]


def get_server_filters(mydb, filter_data=None):
    where_not_ = {}

    if 'onebox_type' in filter_data:
        if filter_data.get('onebox_type') is not None:
            where_ = {'nfsubcategory':"%s" %str(filter_data.get('onebox_type'))}
        else:
            where_ = {'nfsubcategory': "One-Box"}
    else:
        where_ = {'nfsubcategory': "One-Box"}

    # where_ = {'nfsubcategory': "One-Box"}

    if filter_data:
        if "serverseq" in filter_data: where_['serverseq']=filter_data['serverseq']
        if "customerseq" in filter_data: where_['customerseq']=filter_data['customerseq']
        if "onebox_id" in filter_data: where_['onebox_id']=filter_data['onebox_id']
        if "public_ip" in filter_data: where_['publicip']=filter_data['public_ip']
        if "nsseq" in filter_data: where_['nsseq']=filter_data['nsseq']
        if "public_mac" in filter_data: where_['publicmac']=filter_data['public_mac']

    result, content = mydb.get_table(FROM='tb_server', WHERE=where_, WHERE_NOT=where_not_)
    
    if result < 0:
        log.error("get_server error %d %s" % (result, content))
    return result, content


def get_server_filters_wf(mydb, filter_data=None):
    where_not_ = {}

    if 'onebox_type' in filter_data:
        if filter_data.get('onebox_type') is not None:
            where_ = {'nfsubcategory': "%s" % str(filter_data.get('onebox_type'))}
        else:
            where_ = {'nfsubcategory': "One-Box"}
    else:
        # where_ = {'nfsubcategory': "One-Box"}
        where_ = {}
        where_not_ = {'nfsubcategory': "System"}

    # where_ = {'nfsubcategory': "One-Box"}

    if filter_data:
        if "serverseq" in filter_data: where_['serverseq'] = filter_data['serverseq']
        if "customerseq" in filter_data: where_['customerseq'] = filter_data['customerseq']
        if "onebox_id" in filter_data: where_['onebox_id'] = filter_data['onebox_id']
        if "public_ip" in filter_data: where_['publicip'] = filter_data['public_ip']
        if "nsseq" in filter_data: where_['nsseq'] = filter_data['nsseq']
        if "public_mac" in filter_data: where_['publicmac'] = filter_data['public_mac']
        if "officeseq" in filter_data: where_['officeseq'] = filter_data['officeseq']

    result, content = mydb.get_table(FROM='tb_server', WHERE=where_, WHERE_NOT=where_not_)

    if result < 0:
        log.error("get_server error %d %s" % (result, content))
    return result, content


def delete_server(mydb, id):
    if type(id) is int or type(id) is long:
        del_column = 'serverseq' 
    elif id.isdigit():
        del_column = 'serverseq'
    else:
        del_column = 'servername'
        
    result, content = mydb.delete_row_seq("tb_server", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_server error %d %s" % (result, content))
    return result, content


def get_onebox_hw_serverseq(mydb, serverseq):
    result, content = mydb.get_table(FROM='tb_onebox_hw', WHERE={"serverseq":serverseq})
    
    return result, content


def get_onebox_hw_model(mydb, hw_model):
    result, content = mydb.get_table(FROM='tb_onebox_hw', WHERE={"model": hw_model})

    return result, content

def get_onebox_sw_serverseq(mydb, serverseq):
    result, content = mydb.get_table(FROM='tb_onebox_sw', WHERE={"serverseq":serverseq})
    
    return result, content


def get_onebox_nw_serverseq(mydb, serverseq):
    result, content = mydb.get_table(FROM='tb_onebox_nw', WHERE={"serverseq":serverseq})
    
    return result, content


def get_server_vnet(mydb, serverseq):
    result, content = mydb.get_table(FROM='tb_server_vnet', WHERE={"serverseq":serverseq})
    if result <= 0:
        return result, content
    else:
        return result, content[0]


def insert_vim(mydb, data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_vim", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_vim error %d %s" % (result, content))
    return result, content


def get_vim_list(mydb):

    select_ = ('vimseq','name', 'serverseq', 'authurl','vimtypecode','reg_dttm','modify_dttm')
    where_ = {}
    limit_ = 100
    
    result, content = mydb.get_table(FROM='tb_vim', SELECT=select_,WHERE=where_,LIMIT=limit_)
    
    if result < 0:
        log.error("get_vim error %d %s" % (result, content))
    return result, content


def get_vim_id(mydb, id):
    '''get VIM details, can use both id or name'''
    #TODO check if server is seq or name, etc.
    if type(id) is int or type(id) is long:
        where_ = {"vimseq":id} 
    elif id.isdigit():
        where_ = {"vimseq":id}
    else:
        where_ = {"name":id}
        
    result, content = mydb.get_table(FROM='tb_vim', WHERE=where_)
    if result < 0:
        log.error("get_vim_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found Server with %s" %str(where_)
    elif result > 1: 
        return -HTTP_Bad_Request, "More than one VIM found with %s" %str(where_)
    
    return result, content[0]


def get_vim_serverseq(mydb, serverseq):
    result, content = mydb.get_table(FROM='tb_vim', WHERE={"serverseq":serverseq})
    
    return result, content


def delete_vim(mydb, id):
    if type(id) is int or type(id) is long:
        del_column = 'vimseq'
    elif id.isdigit():
        del_column = 'vimseq'
    else:
        del_column = 'name'
        
    result, content = mydb.delete_row_seq("tb_vim", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_server error %d %s" % (result, content))
    return result, content


def get_vim_and_vim_tenant(mydb, vim_id=None, vim_name=None, server_id=None):
    WHERE_dict={}
    if vim_id   is not None:  WHERE_dict['v.vimseq']  = vim_id
    if vim_name is not None:  WHERE_dict['v.name']  = vim_name
    if server_id is not None: WHERE_dict['v.serverseq'] = server_id
    
    # get vim_tenant_id
    f_tmp = 'tb_vim_tenant as vt join tb_vim as v on vt.vimseq=v.vimseq'
    s_tmp = ('vt.uuid as vim_tenant_uuid', 'vt.name as vim_tenant_name')
    r, c = mydb.get_table(FROM=f_tmp, SELECT=s_tmp, WHERE=WHERE_dict)

    if r > 0:
        from_= 'tb_vim as v join tb_vim_tenant as vt on v.vimseq=vt.vimseq'
        select_ = ('vimtypecode','v.vimseq as vimseq', 'authurl', 'authurladmin', 'v.name as name', 'v.version as version', 'serverseq', 'mgmtip',
                   'vt.uuid as vim_tenant_uuid','vt.name as vim_tenant_name','vt.vimtenantseq as vimtenantseq',
                   'vt.username as username','vt.password as password','vt.domain as domain')
    else:
        from_ = 'tb_vim as v'
        select_ = ('vimtypecode','vimseq', 'authurl', 'authurladmin', 'name', 'version', 'serverseq', 'mgmtip')

    # log.debug('[get_vim_and_vim_tenant] from_ = %s' %str(from_))
    # log.debug('[get_vim_and_vim_tenant] select_ = %s' %str(select_))
    # log.debug('[get_vim_and_vim_tenant] WHERE_dict = %s' %str(WHERE_dict))

    result, content = mydb.get_table(FROM=from_, SELECT=select_, WHERE=WHERE_dict )

    if result < 0:
        log.error("nfvo.get_vim_and_vim_tenant error %d %s" % (result, content))
        return result, content
    elif result==0:
        log.error("nfvo.get_vim_and_vim_tenant not found a valid VIM with the input params " + str(WHERE_dict))
        return -HTTP_Not_Found, "VIM not found for " +  json.dumps(WHERE_dict)
    
    #log.debug("VIM info with vim tenant: " + json.dumps(content, indent=4))
    return result, content


def insert_vim_tenant(mydb, data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row('tb_vim_tenant', data, None, add_uuid=False, log=db_debug)
    if result<1:
        return -HTTP_Bad_Request, "Not possible to add VIM Tenant to database tb_vim_tenants table %s " %(content)
    
    return result, content


def get_vim_tenant_list(mydb, vim_id):
    where_={"vimseq":vim_id}
    result,content = mydb.get_table(FROM='tb_vim_tenant', WHERE=where_)
    if result==0:
        return -HTTP_Not_Found, "VIM %s is not attached" %(vim_id)
    elif result<0:
        log.error("get_vim_tenant_list error %d %s" % (result, content))
    return result, content


def get_vim_tenant_id(mydb, vim_tenant_id=None, vim_tenant_name=None, vim_id=None):
    where_={"vimseq": vim_id}
    if vim_tenant_id is not None:
        where_["uuid"] = vim_tenant_id
    if vim_tenant_name is not None:
        where_["name"] = vim_tenant_name
    result, content = mydb.get_table(FROM='tb_vim_tenant', WHERE=where_)
    if result < 0:
        log.error("get_vim_tenant_id error %d %s" % (result, content))
    return result, content


def delete_vim_tenant(mydb, vim_tenant):
    #TODO check if server is seq or name, etc.
    result, content = mydb.delete_row_seq("tb_vim_tenant", "vimtenantseq", vim_tenant, None, db_debug)
    if result < 0:
        log.error("delete_vim_tenant error %d %s" % (result, content))
    return result, content


def get_vim_networks(mydb, id):
    '''get virtual networks in the VIM, can use both uuid or name'''
    if type(id) is int or type(id) is long:
        where_ = {"vimseq":id} 
    elif id.isdigit():
        where_ = {"vimseq":id}
    else:
        where_ = {"name":id}
    
    result, vim_dict = mydb.get_table(FROM='tb_vim', WHERE=where_)
    if result==0:
        return -HTTP_Not_Found, "VIM %s is not attached" %(id)
    elif result<0:
        log.error("get_vim_networks error %d %s" % (result, vim_dict))
        return result, vim_dict

    result, content =mydb.get_table(FROM='tb_vim_net',
                                    SELECT=('name','uuid','type','multipointyn','sharedyn','description', 'reg_dttm', 'modify_dttm', 'status','vimsubnetuuid'),
                                    WHERE={"vimseq":vim_dict[0]['vimseq']} )
    if result < 0:
        log.error("get_vim_networks error %d %s" %(result, content))
    return result, content


def update_vim_networks(mydb, id, net_list):
    if type(id) is int or type(id) is long:
        where_ = {"vimseq":id}
    elif id.isdigit():
        where_ = {"vimseq":id}
    else:
        where_ = {"name":id}
    
    deleted, content = mydb.delete_row_by_dict(FROM="tb_vim_net", WHERE=where_)
    if deleted < 0:
        return deleted, content
    
    for new_net in net_list:
        new_net['modify_dttm']=datetime.datetime.now()
        result, content = mydb.new_row('tb_vim_net', new_net, tenant_id=None, add_uuid=False, log=db_debug)
        if result < 0:
            return -HTTP_Internal_Server_Error, content        
    
    #log.debug("Inserted %d nets, deleted %d old nets" % (len(net_list), deleted))
    
    return len(net_list), deleted


def insert_vim_image(mydb, data_dict):
    INSERT_ = {}
    if 'vimimagename' in data_dict:
        INSERT_['vimimagename'] = data_dict['vimimagename']
    if 'uuid' in data_dict:
        INSERT_['uuid'] = data_dict['uuid']
    if 'imageseq' in data_dict:
        INSERT_['imageseq'] = data_dict['imageseq']
    if 'vimseq' in data_dict:
        INSERT_['vimseq'] = data_dict['vimseq']
    if 'createdyn' in data_dict:
        INSERT_['createdyn'] = data_dict['createdyn']

    INSERT_['modify_dttm']=datetime.datetime.now()
    try:
        result, content = mydb.new_row("tb_vim_image", INSERT_, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("Failed to insert tb_vim_image record : %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert tb_vim_image - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert tb_vim_image - %s" %str(e)


def get_vim_images(mydb, vim_id=None):
    '''get images in the VIM, can use both uuid or name'''
    where_ ={}
    if vim_id:
        where_['vimseq'] = vim_id
    # if vdud_image_id: where_['imageseq'] = vdud_image_id
    
    result, content = mydb.get_table(FROM="tb_vim_image", WHERE=where_)
    
    if result < 0:
        log.error("get_vim_images error %d %s" %(result, content))
    
    return result, content


def delete_vim_image(mydb, id):
    if type(id) is int or type(id) is long:
        del_column = 'vimimageseq'
    elif id.isdigit():
        del_column = 'vimimageseq'
    else:
        del_column = 'vimimagename'

    result, content = mydb.delete_row_seq("tb_vim_image", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_vim_image error %d %s" % (result, content))
    return result, content


def delete_vim_image_filters(mydb, data_dict):
    try:
        if "vimimageseq" in data_dict:
            result, content = mydb.delete_row_seq("tb_vim_image", "vimimageseq", data_dict['vimimageseq'], None, db_debug)
        else:
            where_ = {}
            if "imageseq" in data_dict:
                where_["imageseq"] = data_dict["imageseq"]
            result, content = mydb.delete_row_by_dict(FROM="tb_vim_image", WHERE=where_)
        if result < 0:
            log.error("delete_vim_image_filters error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : delete tb_vim_image - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete tb_vim_image - %s" %str(e)


def get_vim_images_vdu(mydb, vim_id=None, vdu_name=None):
    '''get images in the VIM, can use both uuid or name'''
    where_ ={}
    if vim_id: where_['vimseq'] = vim_id
    
    result, content = mydb.get_table(FROM="tb_vim_image", WHERE=where_)
    
    if result < 0:
        log.error("get_vim_images_vdu error %d %s" %(result, content))
        return result, content
    elif result == 0:
        log.warning("get_vim_images_vdu No image found %d %s" %(result, content))
        log.debug("get_vim_images_vdu: try to get all images in the VIM")
        all_result, all_content = get_vim_images(mydb, vim_id)
        if all_result < 0:
            log.error("get_vim_images_vdu error %d %s" %(all_result, all_content))
        return all_result, all_content
    else:
        vdu_images = []
        vdu_name_list = vdu_name.split("_")
        target_vdu_name = vdu_name_list.pop()
        log.debug("get_vim_images_vdu: target vdu name = %s" %target_vdu_name)
        
        for image in content:
            if image['vimimagename'].find(target_vdu_name) >= 0:
                log.debug("get_vim_images_vdu: found image %s for VDU %s" %(image['vimimagename'], vdu_name))
                vdu_images.append(image)
            else:
                log.debug("get_vim_images_vdu: other VDU image %s" %image['vimimagename'])
                pass
        return result, vdu_images


def update_vim_images(mydb, vim_id, image_list):
    deleted, content = mydb.delete_row_by_dict(FROM='tb_vim_image', WHERE={'vimseq': vim_id, 'createdyn': False})
    if deleted < 0:
        return deleted, content
    
    result, old_content =mydb.get_table(FROM='tb_vim_image',
                   SELECT=('imageseq', 'vimimagename','uuid','createdyn'),
                   WHERE={"vimseq":vim_id} )
    #log.debug("remaining image records:\n"+json.dumps(content, indent=4))
    
    remaining_no = result
    insert_count = 0
    for new_image in image_list:
        exist = False
        if remaining_no > 0:
            for record in old_content:
                if record['uuid'] == new_image['uuid']:
                    exist = True
                    break
        if not exist:
            if len(new_image['vimimagename']) > 36:
                #log.debug("new image: %s" %str(new_image))
                pass
            else:
                new_image['modify_dttm']=datetime.datetime.now()
                new_image['createdyn']=False #TODO: need to change
                result, content = mydb.new_row('tb_vim_image', new_image, tenant_id=None, add_uuid=False, log=db_debug)
                insert_count += 1
                if result < 0:
                    log.warning("failed to insert db record for vim image %s" %str(new_image))
    
    #log.debug("Inserted %d images, deleted %d old images" % (insert_count, deleted))
    
    return insert_count, deleted


def insert_vnfd_general_info(mydb, vnf_descriptor):
    try:
        myVNFDict = {}
        myVNFDict["name"] = vnf_descriptor['vnf']['name']
        myVNFDict["display_name"] = vnf_descriptor['vnf']['display_name']
        myVNFDict["virtualyn"] = vnf_descriptor['vnf']['virtual']
        myVNFDict["publicyn"] = vnf_descriptor['vnf']['public']
        myVNFDict["description"] = vnf_descriptor['vnf']['description']
        myVNFDict["nfmaincategory"] = vnf_descriptor['vnf']['nfmaincategory']
        myVNFDict["nfsubcategory"] = vnf_descriptor['vnf']['nfsubcategory']
        myVNFDict["version"] = vnf_descriptor['vnf']['version'] #hjc
        myVNFDict['modify_dttm'] = datetime.datetime.now()

        myVNFDict["repo_filepath"] = vnf_descriptor['vnf']['repo_filepath']
        
        if 'status' in vnf_descriptor: myVNFDict["status"] = vnf_descriptor['vnf']['status']
        
        # check vendor code
        vc_result, vc_data = mydb.get_table(FROM="tb_vendor", WHERE={"vendorname":vnf_descriptor['vnf']['vendor']})
        if vc_result < 0:
            log.error("Failed to check Vendor Code for the VNFD: %s" %(myVNFDict['name']))
            myVNFDict["vendorcode"]="kt" # use "kt" as the default vendor 
        elif vc_result == 0:
            myVNFDict["vendorcode"] = vnf_descriptor['vnf']['vendor']
            vci_result, vci_data = mydb.new_row('tb_vendor', {"vendorname":vnf_descriptor['vnf']['vendor'], "vendorcode":myVNFDict["vendorcode"]}, tenant_id=None, add_uuid=False, log=db_debug)
        else:
            myVNFDict["vendorcode"]=vc_data[0]['vendorcode']
        
        result, vnfdseq = mydb.new_row('tb_nfcatalog', myVNFDict, tenant_id=None, add_uuid=False, log=db_debug) 
        
        if result < 0:
            return result, "Error creating vnf in NFVO database: %s" %vnfdseq
    
    except KeyError as e:
        log.exception("Error while creating a VNF. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while creating a VNF, KeyError " + str(e)
        
    return 200, vnfdseq


def insert_vnfd_resource_template(mydb, template_dict):
    db_template_dict={'name':template_dict['name'], 'version':template_dict['version'],'description':template_dict['description']}
    res,content = mydb.new_row('tb_resourcetemplate', db_template_dict, tenant_id=None, add_uuid=False, log=db_debug)
    if res>0:
        template_dict['resourcetemplateseq']= content
    else:
        return res, content
    
    for param_key in template_dict['parameters']:
        db_template_param_dict=template_dict['parameters'][param_key]
        db_template_param_dict['name']=param_key
        db_template_param_dict['itemtype']='parameter'
        db_template_param_dict['resourcetemplateseq']=template_dict['resourcetemplateseq']
        
        res,content = mydb.new_row('tb_resourcetemplate_item', db_template_param_dict, tenant_id=None, add_uuid=False, log=db_debug)
        if res <= 0:
            log.warning("failed to db insert tb_resourcetemplate_item of parameter  = " + param_key)

    for output_key in template_dict['outputs']:
        db_template_output_dict={}
        db_template_output_dict['name']=output_key
        db_template_output_dict['description']=template_dict['outputs'][output_key]['description']
        db_template_output_dict['itemtype']='output'
        db_template_output_dict['resourcetemplateseq']=template_dict['resourcetemplateseq']
        
        res,content = mydb.new_row('tb_resourcetemplate_item', db_template_output_dict, tenant_id=None, add_uuid=False, log=db_debug)
        if res <= 0:
            log.warning("failed to db insert tb_resourcetemplate_item of output  = " + output_key)
            
    for resource_key in template_dict['resources']:
        db_template_resource_dict={}
        db_template_resource_dict['name']=resource_key
        db_template_resource_dict['type']=template_dict['resources'][resource_key]['type']
        db_template_resource_dict['itemtype']='resource'
        db_template_resource_dict['resourcetemplateseq']=template_dict['resourcetemplateseq']
        
        res,content = mydb.new_row('tb_resourcetemplate_item', db_template_resource_dict, tenant_id=None, add_uuid=False, log=db_debug)
        if res <= 0:
            log.warning("failed to db insert tb_resourcetemplate_item of resource  = " + resource_key)
    
    return 1, template_dict['resourcetemplateseq']


def insert_vnfd_vdu_image(mydb, image_dict):

    temp_image_dict={'name':image_dict['name'],
                     'location':image_dict['location'],
                     'vdudseq':image_dict['vdudseq'],
                     'description':image_dict.get('description',None),
                     'filesize':image_dict.get('filesize',None),
                     'checksum':image_dict.get('checksum',None)
                    }
    if "metadata" in image_dict:
        if type(image_dict["metadata"]) == dict:
            temp_image_dict["metadata"] = json.dumps(image_dict["metadata"])
        else:
            temp_image_dict["metadata"] = image_dict["metadata"]
    if "vnf_image_version" in image_dict:
        temp_image_dict["vnf_image_version"] = image_dict["vnf_image_version"]
    if "vnf_sw_version" in image_dict:
        temp_image_dict["vnf_sw_version"] = image_dict["vnf_sw_version"]

    temp_image_dict['modify_dttm'] = datetime.datetime.now()
    result, content = mydb.new_row('tb_vdud_image', temp_image_dict, tenant_id=None, add_uuid=False, log=db_debug)
    
    if result <= 0:
        log.error("insert_vnfd_vdu_image error %d %s" % (result, str(content)))

    return result, content


def get_vnfd_vdu_image(mydb, image_dict):

    if 'vdudimageseq' in image_dict:
        where_ = {'vi.vdudimageseq': image_dict['vdudimageseq']}
    else:
        if 'name' in image_dict:
            where_ = {'vi.name': image_dict['name']}
        elif 'location' in image_dict and str(image_dict['location']).lower() != 'none':
            where_ = {'vi.location':image_dict['location']}
        else:
            where_ = {}

    select_ = ('vi.vdudimageseq', 'vi.name', 'vi.location', 'vi.metadata', 'vi.vdudseq', 'vi.filesize', 'vi.checksum'
               , 'vi.description', 'vi.reg_dttm', 'vi.modify_dttm', 'v.nfcatseq', 'vi.vnf_image_version', 'vi.vnf_sw_version', 'vi.vdudimageseq')

    result, content = mydb.get_table(FROM='tb_vdud v join tb_vdud_image vi on v.vdudseq = vi.vdudseq'
                                     , SELECT=select_
                                     , WHERE=where_ )
    if result < 0:
        log.error("get_vnfd_vdu_image error %d %s" %(result, content))        
    return result, content


def insert_vnfd_as_a_whole(mydb, vnf_descriptor, VNFCDict):

    global global_config
    
    try:
        vnf_descriptor_dir = global_config['vnf_repository'] + "/vnfd"
        vnf_descriptor_filename = vnf_descriptor_dir + "/" + vnf_descriptor['vnf']['name'] + ".vnfd"
        
        if not os.path.exists(vnf_descriptor_dir):
            os.makedirs(vnf_descriptor_dir)
        
        if not os.path.exists(vnf_descriptor_filename):
            f = file(vnf_descriptor_filename, "w")
            f.write(json.dumps(vnf_descriptor, indent=4) + os.linesep)
            f.close()
    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    try:
        if 'nfcatseq' in vnf_descriptor:
            #log.debug("Onbaording VNF: vnf id %d" %vnf_descriptor['nfcatseq'])
            vnf_pre_exist, vnf_pre_data = get_vnfd_general_info(mydb, vnf_descriptor['nfcatseq'])
        else:
            vnf_pre_exist, vnf_pre_data = 0, None

        if vnf_pre_exist < 0:
            error_msg = "failed to check if there is pre-existing DB data for the VNF %s" %vnf_descriptor['vnf']['name']
            log.error(error_msg)
            return vnf_pre_exist, error_msg
            
        myVNFDict = {}
        myVNFDict["virtualyn"] = vnf_descriptor['vnf']['virtual']
        myVNFDict["publicyn"] = vnf_descriptor['vnf']['public']
        myVNFDict["description"] = vnf_descriptor['vnf']['description']
        myVNFDict["resourcetemplate"] = vnf_descriptor['vnf'].get('resource_template') #hjc
        myVNFDict["resourcetemplatetype"] = vnf_descriptor['vnf']['resource_template_type'] #hjc
        myVNFDict["resourcetemplateseq"] = vnf_descriptor['vnf'].get('resource_template_id') #hjc
        myVNFDict['license_name'] = vnf_descriptor.get('license_name')
        myVNFDict['app_id'] = vnf_descriptor['vnf'].get('webaccount_id')
        myVNFDict['app_passwd'] = vnf_descriptor['vnf'].get('webaccount_password')
        myVNFDict["modify_dttm"] = datetime.datetime.now()
        
        if vnf_pre_exist > 0:
            vnf_id = vnf_pre_data['nfcatseq']
            where_ = {'nfcatseq': vnf_id}
            # log.debug("myVNFDict : %s" % myVNFDict)
            result, update_content = mydb.update_rows('tb_nfcatalog', myVNFDict, where_)
            # log.debug("update_content : %s" % update_content)
        else:
            myVNFDict["name"] = vnf_descriptor['vnf']['name']
            myVNFDict["version"] = vnf_descriptor['vnf']['version'] #hjc
            result, vnf_id = mydb.new_row('tb_nfcatalog', myVNFDict, None, add_uuid=False, log=db_debug)
        
        if result < 0:
            return result, "Error creating vnf in NFVO database: %s" % vnf_id
        elif vnf_pre_exist == 0:    
            log.debug("VNF %s added to NFVO DB. VNF id: %s" % (vnf_descriptor['vnf']['name'],vnf_id))

        # XMS 관련 부분....필요없어짐...삭제필요. tb_nfcatalog_param 테이블도 안씀.
        # VNF App Account
        # if 'account' in vnf_descriptor['vnf'] and vnf_descriptor['vnf']['account'].get('type') == "parameter":
        #     account_params = vnf_descriptor['vnf']['account']['parameters']
        #     for param in account_params:
        #         vnf_account_param_dict = {}
        #         vnf_account_param_dict['name'] = param['name']
        #         vnf_account_param_dict['description'] = param.get('description', param['name'])
        #         vnf_account_param_dict['type'] = param['type']
        #         vnf_account_param_dict['nfcatseq'] = vnf_id
        #         param_r, param_id = mydb.new_row('tb_nfcatalog_param', INSERT=vnf_account_param_dict, tenant_id=None, add_uuid=False, log=db_debug)
        #         if param_r < 0:
        #             log.error("Error db insert tb_nfcatalog_param: %s" %param['name'])

    except KeyError as e:
        log.exception("Error while creating a VNF. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while creating a VNF, KeyError " + str(e)
    except Exception, e2:
        log.exception("Error while creating a VNF. Exception: " + str(e2))
        return -HTTP_Internal_Server_Error, "Error while creating a VNF, Exception " + str(e2)
    
    try:
        for _,vm in VNFCDict.iteritems():
            #log.debug("V4: VM name: %s. Description: %s" % (vm['name'], vm['description']))
            vm_dict = {}
            vm_dict['nfcatseq']=vnf_id
            vm_dict['name']=vm['name']
            vm_dict['deployorder']=vm['deploy_order']
            vm_dict['description']=vm.get('description', vm['name'])
            if 'flavor_id' in vm:
                vm_dict['flavorseq']=vm.get('flavor_id')
            # vm_dict['imageseq']=vm.get('image_id')
            
            vm_dict['vm_access_id']=vm.get('vm_access_id')
            vm_dict['vm_access_passwd']=vm.get('vm_access_passwd')
            
            vm_dict['modify_dttm']=datetime.datetime.now()

            # metadata 저장 : 2017/06/20
            if vm.get("image_metadata", None) is not None:
                vm_dict["image_metadata"] = json.dumps(vm.get("image_metadata"))

            result, vm_id = mydb.new_row('tb_vdud', vm_dict, None, add_uuid=False, log=db_debug) 
            if result < 0:
                return result, "V4: Error creating vm in NFVO database: %s" % vm_id
            
            if 'cps' in vm and vm['cps'] is not None:
                for cpd in vm['cps']:
                    cpd_dict = {}
                    cpd_dict['name'] = cpd['name']
                    cpd_dict['vdudseq'] = vm_id
                    cpd_dict['modify_dttm'] = datetime.datetime.now()
                    cpd_result, cpd_id = mydb.new_row('tb_cpd', cpd_dict, None, add_uuid=False, log=db_debug)
                    if cpd_result < 0:
                        log.warning("failed to insert a DB record for a CPD %d %s" %(cpd_result, cpd_id))
            
            vm_monitors = vm.get('monitors')
            
            if vm_monitors and len(vm_monitors) > 0:
                for monitor in vm_monitors:
                    vm_monitor_dict = {}
                    vm_monitor_dict['name'] = monitor['name']
                    vm_monitor_dict['description'] = monitor.get('description', monitor['name'])
                    vm_monitor_dict['type'] = monitor.get('type','unknown')
                    vm_monitor_dict['vdudseq'] = vm_id
                    vm_monitor_dict['builtinyn'] = monitor.get('builtin', True)
                    vm_monitor_dict['period'] = monitor.get('period', 30)
                    monitor_result, monitor_id = mydb.new_row('tb_vdud_monitor', INSERT=vm_monitor_dict, tenant_id=None, add_uuid=False,log=db_debug)
                    if result < 0:
                        log.warning("failed to insert a DB record for VNF Monitor %d %s" %(monitor_result, monitor_id))
                    else: # 현재 parameters/scripts/outputs 정보는 없어서 아래 로직은 패스된다.
                        if monitor.get('parameters') and len(monitor['parameters']) > 0:
                            for param in monitor['parameters']:
                                vm_monitor_param_dict = {}
                                vm_monitor_param_dict['name'] = param['name']
                                vm_monitor_param_dict['description'] = param.get('description', param['name'])
                                vm_monitor_param_dict['type'] = param['type']
                                vm_monitor_param_dict['vdudmonitorseq'] = monitor_id
                                param_result, param_id = mydb.new_row('tb_vdud_monitorparam', INSERT=vm_monitor_param_dict, tenant_id=None, add_uuid=False, log=db_debug)                  
                                if param_result < 0:
                                    log.warning("failed to insert a DB record for VNF Monitor Parameter %d %s" %(param_result, param_id))
                        if monitor.get('scripts') and len(monitor['scripts']) > 0:
                            for script in monitor['scripts']:
                                vm_monitor_script_dict = {}
                                vm_monitor_script_dict['name'] = script['name']
                                vm_monitor_script_dict['description'] = script.get('description', script['name'])
                                vm_monitor_script_dict['type'] = script['type']
                                vm_monitor_script_dict['body'] = script['body']
                                
                                script_output = ""
                                if script.get('output') and len(script['output']) > 0:
                                    for output in script['output']:
                                        if script_output == "":
                                            script_output = script_output + output['name']
                                        else:
                                            script_output = script_output + ";" + output['name']
                                if script_output != "":
                                    vm_monitor_script_dict['output'] = script_output
                                
                                if 'param_format' in script:
                                    vm_monitor_script_dict['paramformat'] = script['param_format'] 
                                if 'param_order' in script:
                                    if script['param_order'] != None and len(script['param_order']) > 0:
                                        vm_monitor_script_dict['paramorder'] = ";".join(script['param_order'])                    
                    
                                vm_monitor_script_dict['vdudmonitorseq'] = monitor_id
                                
                                script_result, script_id = mydb.new_row('tb_vdud_monitorscript', INSERT=vm_monitor_script_dict, tenant_id=None, add_uuid=False, log=db_debug)
                                if script_result < 0:
                                    log.warning("failed to insert a DB record for VNF Monitor Script %d %s" %(script_result, script_id))
                        if monitor.get('outputs') and len(monitor['outputs']) > 0:
                            for output in monitor['outputs']:
                                vm_monitor_output_dict = {}
                                vm_monitor_output_dict['name'] = output['name']
                                vm_monitor_output_dict['description'] = output.get('description', output['name'])
                                vm_monitor_output_dict['type'] = output.get('type', 'unknown')
                                vm_monitor_output_dict['vdudmonitorseq'] = monitor_id
                                output_result, output_id = mydb.new_row('tb_vdud_monitoroutput', INSERT=vm_monitor_output_dict, tenant_id=None, add_uuid=False, log=db_debug)
                                if output_result < 0:
                                    log.warning("failed to insert a DB record for VNF Monitor Output %d %s" %(output_result, output_id))
                                else:
                                    if output.get('fault_criteria') and len(output['fault_criteria']):
                                        for fault in output['fault_criteria']:
                                            vm_monitor_ouptut_fault_dict = {}
                                            vm_monitor_ouptut_fault_dict['name'] = fault['name']
                                            vm_monitor_ouptut_fault_dict['level'] = fault['level']
                                            vm_monitor_ouptut_fault_dict['condition'] = fault['condition']
                                            vm_monitor_ouptut_fault_dict['vdudmonitoroutputseq'] = output_id
                                            fault_result, fault_id = mydb.new_row('tb_vdud_monitoroutput_fault', INSERT=vm_monitor_ouptut_fault_dict, tenant_id=None, add_uuid=False, log=db_debug)
                                            if fault_result < 0:
                                                log.warning("failed to insert a DB record for VNF Monitor Output Fault %d %s" %(fault_result, fault_id))
                                        
            vm_configs = vm.get('configs')
            if vm_configs and len(vm_configs) > 0:
                for config in vm_configs:
                    vm_config_dict = {}
                    vm_config_dict['name'] = config['name']
                    vm_config_dict['description'] = config.get('description', config['name'])
                    vm_config_dict['type'] = config.get('type', "unknown")
                    vm_config_dict['vdudseq'] = vm_id
                    vm_config_dict['performorder'] = config['performorder']
                    result, config_id = mydb.new_row('tb_vdud_config', INSERT=vm_config_dict, tenant_id=None, add_uuid=False, log=db_debug)
                    if result < 0:
                        return result, "V4: Error creating vm_config in NFVO database: %s" % config_id
                    else:
                        if 'parameters' in config and len(config['parameters']) > 0:
                            for param in config['parameters']:
                                vm_config_param_dict = {}
                                vm_config_param_dict['name'] = param['name']
                                vm_config_param_dict['description'] = param.get('description', param['name'])
                                vm_config_param_dict['type'] = param['type']
                                vm_config_param_dict['vdudconfigseq'] = config_id
                                param_r, param_id = mydb.new_row('tb_vdud_configparam', INSERT=vm_config_param_dict, tenant_id=None, add_uuid=False, log=db_debug)
                                if param_r < 0:
                                    log.error("Error db insert tb_vduds_configs_params: %s" %param['name'])
                        
                        for script in config['scripts']:
                            vm_config_script_dict = {}
                            vm_config_script_dict['name'] = script['name']
                            vm_config_script_dict['description'] = script.get('description', script['name'])
                            vm_config_script_dict['performorder'] = script['performorder']
                            vm_config_script_dict['type'] = script['type']
                            vm_config_script_dict['builtinyn'] = script.get('builtin', True)
                            vm_config_script_dict['vdudconfigseq'] = config_id
                            
                            if 'condition' in script: vm_config_script_dict['condition'] = script['condition']

                            if 'request_url' in script: vm_config_script_dict['requesturl'] = script['request_url']

                            if 'body' in script:
                                vm_config_script_dict['body'] = script['body']
                            if 'body_args' in script:
                                if script['body_args'] != None and len(script['body_args']) > 0:
                                    vm_config_script_dict['body_args'] = ";".join(script['body_args'])
                            
                            if 'request_headers' in script:
                                vm_config_script_dict['requestheaders'] = script['request_headers']
                            if script.get('request_headers_args') != None and len(script['request_headers_args']) > 0:
                                vm_config_script_dict['requestheaders_args'] = ";".join(script['request_headers_args'])
                            
                            if 'output' in script:
                                if script['output'] != None and len(script['output']) > 0:
                                    vm_config_script_dict['output'] = ";".join(script['output'])
                            
                            if 'param_format' in script:
                                vm_config_script_dict['paramformat'] = script['param_format'] 
                            if 'param_order' in script:
                                if script['param_order'] != None and len(script['param_order']) > 0:
                                    vm_config_script_dict['paramorder'] = ";".join(script['param_order'])
                            
                            if 'cookie_format' in script:
                                vm_config_script_dict['cookieformat'] = script['cookie_format']                                
                            if 'cookie_data' in script:
                                if script['cookie_data'] != None and len(script['cookie_data']) > 0:
                                    vm_config_script_dict['cookiedata'] = ";".join(script['cookie_data'])
                            script_r, script_id = mydb.new_row('tb_vdud_configscript', INSERT=vm_config_script_dict, tenant_id=None, add_uuid=False, log=db_debug)
                            if script_r < 0:
                                log.error("Error db insert tb_vdud_configscript: %s" %script['name'])
                                
            web_url_dict = vm.get('web_url')
            if web_url_dict:
                log.debug("DB Inserting web_url: %s" %str(web_url_dict))
                
                web_url_dict['vdudseq'] = vm_id
                if web_url_dict['type'] == 'main':
                    web_url_dict['nfcatseq'] = vnf_id 
                
                web_url_r, web_url_id = mydb.new_row('tb_vdud_weburl', INSERT=web_url_dict, tenant_id=None, add_uuid=False, log=db_debug)
                if web_url_r < 0:
                    log.error("Error db insert tb_vdud_weburl: %s" %web_url_dict['name'])
        
    except KeyError as e:
        log.exception("Error while creating a VNF. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while creating a VNF, KeyError " + str(e)
    except Exception as e2:
        log.exception("Error while creating a VNF. Exception: " + str(e2))
        return -HTTP_Internal_Server_Error, "Error while creating a VNF, Exception " + str(e2)
    
    return 1, vnf_id


def get_vnfd_general_info(mydb, vnfd):
    where_ = {"nfcatseq":vnfd}
    
    result, content = mydb.get_table(FROM='tb_nfcatalog', WHERE=where_)
    if result < 0:
        log.error("get_vnfd_general_info error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found vnfd with %s = %s" %("nfcatseq", vnfd)
    return result, content[0]


def get_vnfd_general_info_with_name(mydb, vnfd):
    if type(vnfd) == str:
        log.debug("[HJC] str-type vnfd = %s" %vnfd)
        if vnfd.find("_ver") > 0:
            vnfd_name = vnfd.split("_ver")[0]
            vnfd_version = vnfd.split("_ver")[1]
            #log.debug("vnfd name: %s, vnfd_version: %s" %(vnfd_name, vnfd_version))
            where_ = {"name":vnfd_name, "version":vnfd_version}
        else:    
            where_ = {"name":vnfd}
    elif type(vnfd) == dict:
        log.debug("[HJC] dict-type vnfd = %s" %str(vnfd))
        where_ = {"name": vnfd.get('vnfd_name', "NotGiven"), "version": vnfd.get('vnfd_version', 1)}
        log.debug("[HJC] where_ = %s" %str(where_))
    else:
        return -HTTP_Bad_Request, "Invalid VNFD Info: %s" %str(vnfd)    
        
    result, content = mydb.get_table(FROM='tb_nfcatalog', WHERE=where_)
    if result < 0:
        log.error("get_vnfd_general_info error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return result, "Not found vnfd with %s" %str(where_)

    content[0]['vnfd_name'] = content[0]['name']
    p_result, p_content = get_vnfd_parmeters(mydb, content[0])
    if p_result < 0:
        log.error("failed to get VNFD Parameters %d %s" %(p_result, p_content))
        return p_result, p_content

    display_params = []
    for param in p_content:
        param_name = param.get('name')
        if param_name is None:
            continue
        if param_name.find('OUT_') >= 0:
            continue
        if param_name.find('IPARM_') >= 0:
            continue
        add_param = True
        for dp in display_params:
            if dp['name'] == param_name:
                add_param = False
                break
        if add_param:
            display_params.append(param)

    content[0]['parameters'] = display_params

    return result, content[0]
    

def update_vnfd(mydb, vnf_dict):
    if vnf_dict.get("nfcatseq", None) is None:
        return -500, "update_vnfd_id Error, No id"
    
    UPDATE_={}
    if "status" in vnf_dict:        UPDATE_["status"] = vnf_dict["status"]
    if "display_name" in vnf_dict:   UPDATE_["display_name"] = vnf_dict["display_name"]
    if "vendor" in vnf_dict:   UPDATE_["vendorcode"] = vnf_dict["vendor"]
    if "description" in vnf_dict:   UPDATE_["description"] = vnf_dict["description"]
    if "resource_template_type" in vnf_dict:   UPDATE_["resourcetemplatetype"] = vnf_dict["resource_template_type"]
    if "resource_template" in vnf_dict:   UPDATE_["resourcetemplate"] = vnf_dict["resource_template"]
    if "virtual" in vnf_dict:   UPDATE_["virtualyn"] = vnf_dict["virtual"]
    if "public" in vnf_dict:   UPDATE_["publicyn"] = vnf_dict["public"]
    if "nfmaincategory" in vnf_dict:   UPDATE_["nfmaincategory"] = vnf_dict["nfmaincategory"]
    if "nfsubcategory" in vnf_dict:   UPDATE_["nfsubcategory"] = vnf_dict["nfsubcategory"]
    
    if len(UPDATE_) > 0:
        WHERE_={'nfcatseq': vnf_dict['nfcatseq']}
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content =  mydb.update_rows('tb_nfcatalog', UPDATE_, WHERE_, db_debug)
        if result < 0:
            log.error('update_vnfd Error ' + content + ' updating table tb_nfcatalog: ' + str(vnf_dict['nfcatseq']))
    else:
        log.error("update_vnfd Error, No content")
        result = -500
    return result, vnf_dict['nfcatseq']


def update_vnfd_vdud(mydb, vdu_dict):
    UPDATE_ = {}
    if "monitor_target_seq" in vdu_dict:
        UPDATE_["monitor_target_seq"] = vdu_dict["monitor_target_seq"]
    
    if len(UPDATE_) > 0:
        WHERE_ = {'vdudseq': vdu_dict['vdudseq']}
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_vdud', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_vnfd_vdud Error ' + content + ' updating table tb_vdud: ' + str(vdu_dict['vdudseq']))
        return result, vdu_dict['vdudseq']
    else:
        return -500, "Not found column for updating"


def get_vnfd_list(mydb, qs):
    select_,where_,limit_ = filter_query_string(qs, None,
            ('nfcatseq','name', 'display_name', 'description','status', 'nfmaincategory', 'nfsubcategory', 'license_name as license', 'version', 'virtualyn as virtual','publicyn as public', "app_id", "reg_dttm", 'modify_dttm', 'resourcetemplatetype as resource_template_type','resourcetemplate as resource_template') )
    result, content = mydb.get_table(FROM='tb_nfcatalog', SELECT=select_,WHERE=where_,LIMIT=limit_)
    
    for c in content:
        if c.get('display_name') == None and c.get('version') != None:
            c['display_name'] = c['name'] + " (ver." + str(c['version']) + ")"
        if c.get('license') == None:
            c['license'] = '-'    
    
    if result < 0:
        log.error("get_vnfd_list error %d %s" %(result, content))
        
    return result, content


def get_vnfd_id(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {"nfcatseq":id}
    elif id.isdigit():
        where_ = {"nfcatseq":id}
    else:
        where_ = {"name":id}
    result, content = mydb.get_table(FROM='tb_nfcatalog', WHERE=where_)
    if result < 0:
        log.error("get_vnfd_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        log.error("Not found %d %s" %(result, content))
        return -HTTP_Not_Found, content

    vnfd_dict = content[0]
    vnf_seq=vnfd_dict["nfcatseq"]
    af.convert_str2boolean(vnfd_dict, ('virtualyn','publicyn',))
    af.convert_datetime2str_psycopg2(vnfd_dict)
    
    if 'display_name' in vnfd_dict:
        log.debug("[HJC] display name: %s" %(vnfd_dict['display_name']))
    elif 'version' in vnfd_dict:
        vnfd_dict['display_name'] = vnfd_dict['name'] + " (ver." + str(vnfd_dict['version']) + ")"
    
    if vnfd_dict.get('resourcetemplatetype', None):
        vnfd_dict['resource_template_type'] = vnfd_dict.pop('resourcetemplatetype')
    if vnfd_dict.get('resourcetemplateseq', None):    
        vnfd_dict['resource_template_seq'] = vnfd_dict.pop('resourcetemplateseq')
    if vnfd_dict.get('resourcetemplate', None):
        vnfd_dict['resouce_template'] = vnfd_dict.pop('resourcetemplate')
    
    data={'vnfd' : vnfd_dict}

    #hjc, get parameters from hot
    if data['vnfd'].get('resource_template_type','none') == 'hot' and data['vnfd'].get('resource_template_seq') is not None:
        select_=('name', 'type', 'description')
        where_={'resourcetemplateseq':data['vnfd']['resource_template_seq'], 'itemtype':'parameter'}
        r, content = mydb.get_table(FROM='tb_resourcetemplate_item', SELECT=select_,WHERE=where_)
        if r < 0:
            log.error("get_vnfd_id Error %s", str(content))
            data['vnfd']['resource_template_param']='none'
        else:
            data['vnfd']['resource_template_param']=content
    else:
        data['vnfd']['resource_template_param'] = 'none'

    #GET VM
    r,content = mydb.get_table(FROM='tb_nfcatalog join tb_vdud on tb_nfcatalog.nfcatseq=tb_vdud.nfcatseq',
            ORDER='tb_vdud.deployorder',
            SELECT=('tb_vdud.vdudseq as vdudseq','tb_vdud.name as name', 'tb_vdud.description as description', 'tb_vdud.vm_access_id as vm_access_id', 'tb_vdud.vm_access_passwd as vm_access_passwd'),
            WHERE={'tb_nfcatalog.nfcatseq': vnf_seq} ) #hjc
    if r < 0:
        log.error("get_vnfd_id error %d %s" % (r, str(content)))
        return r, content
    elif r==0:
        log.warning("get_vnfd_id vnf '%s' No VDUD" % vnf_seq)
        #return -HTTP_Not_Found, "vnf %s not found" % vnf_id
    
    for vnfc in content:
        # r, image_content = mydb.get_table(FROM='tb_vdud_image'
        #                                   , SELECT=('name as imagename', 'location as imagelocation', 'version as imageversion')
        #                                   , WHERE={'vdudimageseq':vnfc['imageseq']})
        # if r == 1:
        #     vnfc['imagename']=image_content[0]['imagename']
        #     vnfc['imagelocation']=image_content[0]['imagelocation']
        #     vnfc['imageversion']=image_content[0]['imageversion']
        # elif r > 0:
        #     vnfc['image_list']=[]
        #     for image in image_content:
        #         vnfc['image_list'].append(image)
                
        #monitor
        r, monitor_content = get_vnfd_vdud_monitor_only(mydb, vnfc['vdudseq'], 'monitor')
        if r <= 0:
            log.warning("failed to get VNF VDUD Monitor Info")
        else:
            vnfc['monitors']=monitor_content

    data['vnfd']['VNFC'] = content

    # get metadata
    md_result, md_content = get_vnfd_metadata(mydb, id)
    if md_result < 0:
        log.warning("failed to get VNF metadata: %d %s" %(md_result, str(md_content)))
    else:
        data['vnfd']['metadata'] = {}
        for md in md_content:
            if md.get('name'):
                data['vnfd']['metadata'][md['name']] = md.get('value')
    
    return result, data


def get_vnfd_resource_template_item(mydb, template_id, type=None):
    where_ = {}
    where_['resourcetemplateseq'] = template_id
    if type:
        where_['itemtype'] = type
            
    result, content = mydb.get_table(SELECT=('name', 'type', 'description'), FROM='tb_resourcetemplate_item', WHERE=where_)
    
    if result < 0:
        log.error("get_vnfd_resource_template_item error %d %s" %(result, content))
    return result, content


def get_vnfd_param_only(mydb, vnf_id):
    log.debug("get_vnfd_param_only: vnfd_id = %s" %str(vnf_id))
    select_ = ('name', 'type', 'description')
    result, content = mydb.get_table(FROM='tb_nfcatalog_param', SELECT=select_, WHERE={'nfcatseq':vnf_id})
    if result < 0:
        log.error("get_vnfd_param_only error %d %s" % (result, content))
    return result, content


def get_vnfd_vdud_only(mydb, vnf_id):
    result, content = mydb.get_table(FROM='tb_vdud', ORDER='deployorder', WHERE={'nfcatseq':vnf_id})
    if result < 0:
        log.error("get_vnfd_vdud_only error %d %s" % (result, content))
    return result, content


def get_vnfd_cpd_only(mydb, vdud_id):
    result, content = mydb.get_table(FROM='tb_cpd', WHERE={'vdudseq':vdud_id})
    if result < 0:
        log.error("get_vnfd_cpd_only error %d %s" %(result, content))
    return result, content


def get_vnfd_vdud_config_only(mydb, vdud_id, type=None):
    where_ = {'v.vdudseq':vdud_id}
    
    if type == 'parameter':
        from_ = 'tb_vdud_config as v join tb_vdud_configparam as p on v.vdudconfigseq = p.vdudconfigseq'
        select_ = ('p.name as name', 'p.type as type', 'p.description as description')
        result, content = mydb.get_table(SELECT=select_, FROM=from_, ORDER='v.performorder', WHERE=where_)
        if result <= 0:
            pass
        return result, content
    elif type == 'config':
        result, content = mydb.get_table(FROM='tb_vdud_config', ORDER='performorder', WHERE={'vdudseq':vdud_id})
        if result <= 0:
            log.error("get_vnfd_vdud_config_only %d %s" %(result, content))
            return result, content
        for config in content:
            r, scripts = mydb.get_table(FROM='tb_vdud_configscript', ORDER='performorder', WHERE={'vdudconfigseq':config['vdudconfigseq']})
            if r <= 0:
                log.error("get_vnfd_vdud_config_only No script found %d %s" % (r, scripts))
                config['scripts']=[]
            else:
                config['scripts']=scripts
        return result, content
    #TODO: config, config + parameter
    else:
        return -HTTP_Internal_Server_Error, "all type is TBD"


def get_vnfd_vdud_weburl_only(mydb, vdud_id):
    where_ = {'vdudseq':vdud_id}
    
    result, content = mydb.get_table(FROM='tb_vdud_weburl', WHERE=where_)
    if result <= 0:
        log.error("get_vnfd_vdud_weburl_only %d %s" %(result, content))
        
    return result, content


def get_vnfd_vdud_monitor_only(mydb, vdud_id, type=None):
    where_ = {'v.vdudseq':vdud_id}
    
    if type == 'parameter':
        from_ = 'tb_vdud_monitor as v join tb_vdud_monitorparam as p on v.vdudmonitorseq = p.vdudmonitorseq'
        select_ = ('p.name as name', 'p.type as type', 'p.description as description', 'p.defaultvalue as defaultvalue')
        result, content = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
        if result <= 0:
            #log.warning("get_vnfd_vdud_monitor_only %d %s" %(result, cotnent))
            pass
        return result, content
    elif type == 'monitor':
        result, content = mydb.get_table(FROM='tb_vdud_monitor', WHERE={'vdudseq':vdud_id})
        if result <= 0:
            #log.error("failed to get VDUD Monitor %d %s" %(result, content))
            return result, content
        
        for monitor in content:
            r, scripts = mydb.get_table(FROM='tb_vdud_monitorscript', WHERE={'vdudmonitorseq': monitor['vdudmonitorseq']})
            if r <= 0:
                #log.warning("failed to get VDUD Monitor Scripts %d %s" %(r, scripts))
                monitor['scripts']=[]
            else:
                monitor['scripts']=scripts
            
            r, outputs = mydb.get_table(FROM='tb_vdud_monitoroutput', WHERE={'vdudmonitorseq':monitor['vdudmonitorseq']})
            if r <= 0:
                #log.warning("failed to get VDUD Monitor Outputs %d %s" %(r, outputs))
                monitor['outputs']=[]
            else:
                monitor['outputs']=outputs
                for output in monitor['outputs']:
                    r, faults = mydb.get_table(FROM='tb_vdud_monitoroutput_fault', WHERE={'vdudmonitoroutputseq':output['vdudmonitoroutputseq']})
                    if r <= 0:
                        #log.warning("failed to get VDUD Monitor OUTPUT Fault Condition %d %s" %(r, faults))
                        output['fault_criteria'] = []
                    else:
                        output['fault_criteria'] = faults
                        
        return result, content
    else:
        log.error("get_vnfd_vdud_monitor_only all type is TBD")    
        return -HTTP_Internal_Server_Error, "all type is TBD"
        

def delete_vnfd(mydb, id):
    if type(id) is int or type(id) is long:
        del_column = "nfcatseq"
    elif id.isdigit():
        del_column = "nfcatseq"
    else:
        del_column = "name"
        
    result, content = mydb.delete_row_seq("tb_nfcatalog", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_vnfd error %d %s" % (result, content))
    return result, content


def delete_vnfd_vdu_image(mydb, image_id):
    result, content = mydb.delete_row_seq("tb_vdud_image", "vdudimageseq", image_id, None, db_debug)
    if result < 0:
        log.error("delete_vnfd_vdu_image error %d %s" % (result, content))
    return result, content


def delete_vnfd_resourcetemplate(mydb, resourcetemplate_id):
    if type(resourcetemplate_id) is int:
        column_name = 'resourcetemplateseq'
    else:
        column_name = 'name'
    
    result, content = mydb.delete_row_seq("tb_resourcetemplate", column_name, resourcetemplate_id, None, db_debug)
    if result < 0:
        log.error("delete_vnfd_resourcetemplate error %d %s" %(result, content))
    return result, content


def insert_nsd_general_info(mydb, nsd_dict):
    #tb_nscatalogs
    INSERT_={'name': nsd_dict['name'],'display_name': nsd_dict['display_name'], 'description': nsd_dict['description'], 'version':nsd_dict['version'], 'nscategory':nsd_dict['nscategory'],
    'resourcetemplatetype': nsd_dict['resource_template_type'], 'resourcetemplate': nsd_dict.get('resource_template', 'none')}
    INSERT_['xy_graph'] = nsd_dict.get('xy_graph', "none")
    
    if 'status' in nsd_dict: INSERT_['status'] = nsd_dict['status']
    
    INSERT_['modify_dttm']=datetime.datetime.now()
    result, nsd_id =  mydb.new_row('tb_nscatalog', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error('insert_nsd_general_info Error inserting at table tb_nscatalog: %s' %str(nsd_id))
    
    return result, nsd_id


def insert_nsd_as_a_whole(mydb, nsd_dict, param_list=[]):
    #tb_nscatalogs
    try:
        ns_pre_exist, ns_pre_data = get_nsd_general_info(mydb, nsd_dict['name'])
        if ns_pre_exist < 0:
            error_msg = "failed to check if there is pre-existing DB Data for the NS %s" %nsd_dict['name']
            log.error(error_msg)
            return ns_pre_exist, ns_pre_data
        
        nsdDict={'name': nsd_dict['name'],'description': nsd_dict['description'],
        'resourcetemplatetype': nsd_dict['resource_template_type'], 'resourcetemplate': nsd_dict.get('resource_template', 'none')} #hjc
        
        nsdDict['modify_dttm'] = datetime.datetime.now()
        if ns_pre_exist > 0:
            nsd_id = ns_pre_data['nscatseq']
            where_ = {'nscatseq': nsd_id}
            result, update_content = mydb.update_rows('tb_nscatalog', nsdDict, where_)
        else:
            result, nsd_id =  mydb.new_row('tb_nscatalog', nsdDict, tenant_id=None, add_uuid=False, log=db_debug)
        
        if result < 0:
            log.error('insert_nsd_as_a_whole Error, creating NS in NFVO database, tb_nscatalog: ' + str(nsd_id))
            return result, nsd_id
        elif ns_pre_exist == 0:
            #TODO update rollback_list
            pass
    except KeyError as e:
        log.exception("Error while creating a NS. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while creating a NS, KeyError " + str(e)
    
    #tb_nfconstituents
    for k,vnf in nsd_dict['vnfs'].items():
        INSERT_={'nscatseq': nsd_id,
                'name': k,
                'nfcatseq': vnf['nfcatseq'],
                'description': vnf['description'],
                'deployorder': vnf['deployorder'],
                "vnfd_version": vnf['vnfd_version'],
                "vnfd_name": vnf['vnfd_name']
            }
        if vnf.get("graph") is not None:
            INSERT_["graph"]=vnf["graph"]
        r,nsd_vnf_id =  mydb.new_row('tb_nfconstituent', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)
        if r<0:
            log.error('insert_nsd_as_a_whole Error inserting at table tb_nfconstituent: ' + str(nsd_vnf_id))
            return r, nsd_vnf_id
        
    #tb_nscatalogs_params
    for param in param_list:
        param['nscatseq'] = nsd_id
        log.debug("[DB] param = %s" %str(param))
        r, c = mydb.new_row('tb_nscatalog_param', param, tenant_id=None, add_uuid=False, log=db_debug)
        if r < 0:
            log.warning("insert_nsd_as_a_whole() failed to insert parameters into DB %d %s" % (r,str(c)))

    #tb_vlds and cpds
    try:
        if 'vlds' in nsd_dict and nsd_dict['vlds']:
            for vld in nsd_dict['vlds']:
                insert_={'nscatseq': nsd_id, 'name': vld['name'], 'description': vld.get("description", vld['name']), 'multipointyn': True}
                insert_['externalyn'] = vld.get('is_external', True)
                insert_['vnettype'] = vld.get('vnet_type', "ProviderNet")

                if 'connectity_type' in vld: insert_['connectivity_type'] = vld['connection_type']
                if vld.get('vnet_name') is not None: insert_['vnet_name'] = vld.get('vnet_name')

                if 'subnet_dhcp' in vld: insert_['dhcpyn'] = vld['subnet_dhcp']
                
                r, nsd_vld_id = mydb.new_row('tb_vld', insert_, tenant_id=None, add_uuid=False, log=db_debug)
                if r<0:
                    log.warning("failed to insert VLD info into DB %d %s" %(r, str(nsd_vld_id)))
                else:
                    if vld.get('connection_points') is not None and len(vld['connection_points']) > 0:
                        for cp in vld['connection_points']:
                            insert_cp_ = {'vldseq': nsd_vld_id, 'name': cp.get('name'), 'owner': cp.get('owner')}
                            if 'owner_type' in cp: insert_cp_['owner_type'] = cp['owner_type']

                            cp_r, cp_r_id = mydb.new_row('tb_vld_cp', insert_cp_, tenant_id=None, add_uuid=False, log=db_debug)
                            if cp_r < 0:
                                log.warning("failed to insert VLD-CP info into DB %d %s" %(cp_r, str(cp_r_id)))
        if 'cpds' in nsd_dict and nsd_dict['cpds']:
            for cpd in nsd_dict['cpds']:
                insert_={'nscatseq': nsd_id, 'name': cpd['name']}
                if 'network' in cpd: insert_['network'] = cpd['network']
                if 'physical_network' in cpd: insert_['physical_network'] = cpd['physical_network']
                if 'type' in cpd: insert_['type'] = cpd['type']
                if 'metadata' in cpd: insert_['metadata'] = cpd['metadata']

                cpd_r, cpd_id = mydb.new_row('tb_nscatalog_cpd', insert_, tenant_id=None, add_uuid=False, log=db_debug)
                if cpd_r < 0:
                    log.warning("failed to insert VLD-CP info into DB %d %s" %(cpd_r, str(cpd_id)))

    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    return result, nsd_id


def get_nsd_list(mydb, qs):
    select_, where_, limit_=filter_query_string(qs, None, ('nscatseq', 'name', 'display_name', 'nscategory', 'description', 'version', 'reg_dttm', 'modify_dttm', 'publicyn', 'status'))
    result, data = mydb.get_table(FROM='tb_nscatalog', SELECT=select_, LIMIT=limit_)

    if result < 0:
        log.error("get_nsd error %d %s" %(result, data))
        return result, data
        
    # Get VNF info including vdu info tb_nfconstituents
    for nsd in data:
        r, vnfs = mydb.get_table(FROM='tb_nfconstituent', SELECT=('name', 'vnfd_name', 'vnfd_version', 'description', 'nfcatseq', 'deployorder'), ORDER='deployorder', WHERE={'nscatseq':nsd['nscatseq']})
        if r < 0:
            log.error("get_nsd_list error failed to get VNFDs included by NS %d %s" % (r, vnfs))
            return r, vnfs
        elif r == 0:
            #log.error("get get_nsd_list error No VNF Found %d %s" % (r,vnfs))
            #return -HTTP_Internal_Server_Error, "No VNF Found for the NSD"
            nsd['vnfs'] = None
        else:
            for c in vnfs:
                if 'version' in c:
                    c['display_name'] = c['name'] + " (ver." + str(c['version']) + ")"
                else:
                    c['display_name'] = c['name']
            nsd['vnfs'] = vnfs
    
    return 200, data


def get_nsd_using_vnfd(mydb, vnfd):
    where_ = {'nfcatseq': vnfd}
    result, content = mydb.get_table(FROM='tb_nfconstituent', WHERE=where_)
    
    if result < 0:
        log.error("get_nsd_using_vnfd error %d %s" % (result, content))
    
    return result, content


def get_nsd_general_info(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {"nscatseq":id} 
    elif id.isdigit():
        where_ = {"nscatseq":id}
    else:
        where_ = {"name":id}
        
    result, content = mydb.get_table(FROM='tb_nscatalog', WHERE=where_)   
    
    if result < 0:
        log.error("get_nsd_general_info error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return result, "Not found"
    
    return result, content[0]


def get_nsd_id(mydb, id, vim_id=None):
    if type(id) is int or type(id) is long:
        where_={'nscatseq':id}
    elif id.isdigit():
        where_={'nscatseq':id}
    else:
        where_={'name':id}
        
    result, content = mydb.get_table(FROM='tb_nscatalog', WHERE=where_)
    if result < 0 or result > 1:
        log.error("get_nsd_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        log.error("get_nsd_id error No NSD found %d %s" % (result, content))
        return -HTTP_Bad_Request, "No NSD Found"
    
    nsd_dict = content[0]
    
    # Get VNF info including vdu info tb_nfconstituents
    r, vnfs = mydb.get_table(FROM='tb_nfconstituent', SELECT=('name', 'vnfd_name', 'vnfd_version', 'nscatseq', 'nfcatseq', 'deployorder', 'graph'), ORDER='deployorder', WHERE={'nscatseq':nsd_dict['nscatseq']})
    if r < 0:
        log.error("get_nsd_id error failed to get VNFDs included by NS %d %s" % (r, vnfs))
        return r, vnfs
    elif r == 0:
        #log.error("get get_nsd_id error No VNF Found %d %s" % (r,vnfs))
        #return -HTTP_Internal_Server_Error, "No VNF Found for the NSD"
        nsd_dict['vnfs'] = None
    else:
        nsd_dict['vnfs'] = vnfs

        for vnf in nsd_dict['vnfs']:
            #template_type & template
            r, general_data = get_vnfd_general_info(mydb, vnf['nfcatseq'])
            if r < 0:
                log.error("get_nsd_id error failed to get VNF %d %s" % (r, general_data))
                return -HTTP_Internal_Server_Error, general_data        
            elif r == 0:
                log.error("get_nsd_id error failed to get VNF %d %s" % (r, general_data))
                return -HTTP_Not_Found, general_data
            
            vnf['resource_template_type']=general_data['resourcetemplatetype']
            #vnf['resource_template']=general_data['resourcetemplate']
            vnf['vnfd_name']=general_data['name']
            vnf['description']=general_data['description']
            vnf['virtualyn']=general_data['virtualyn']
            vnf['nfmaincategory']=general_data['nfmaincategory']
            vnf['nfsubcategory']=general_data['nfsubcategory']
            vnf['vendorcode']=general_data['vendorcode']
            vnf['version']=general_data['version']
            vnf['status']=general_data['status']
            vnf['license_name']=general_data['license_name']
            #vnf['nfcatseq'] = vnf['nfcatseq']
            vnf['display_name'] = vnf['name'] + " (ver." + str(vnf['version']) + ")"
            
            #vduds
            r, vdus = get_vnfd_vdud_only(mydb, vnf['nfcatseq'])
            if r <= 0:
                log.error("get_nsd_id error failed to get VNF VDUs %d %s" % (r, vdus))
                pass
            
            for vdud in vdus:
                af.convert_datetime2str_psycopg2(vdud)
                vdud['name'] = vdud['name'].replace(vnf['vnfd_name'], vnf['name'])
                if vim_id is not None:
                    r, images = get_vim_images(mydb, vim_id)
                    if r <= 0:
                        log.warning("get_nsd_id No VIM Image found %d %s" % (r, vdus))
                    else:
                        vdud['vim_image_id']=images[0]['uuid']
                    #TODO: flavor
                    #self.cur.execute("SELECT vim_flavor_id FROM tb_vim_flavors WHERE flavor_id='%s' AND vim_id='%s'" %(vdud['flavor_id'],vim_id)) 
                    #if self.cur.rowcount==1:
                    #    vim_flavor_dict = self.cur.fetchone()
                    #    vdud['vim_flavor_id']=vim_flavor_dict['vim_id']
                
                # vdud cpds
                r, cpds = get_vnfd_cpd_only(mydb, vdud['vdudseq'])
                if r <= 0:
                    #log.warning("get_nsd_id NO VNF VDU CP Found %d %s" %(r, cpds))
                    pass
                else:
                    for cpd in cpds:
                        af.convert_datetime2str_psycopg2(cpd)
                        cpd['name'] = cpd['name'].replace(vnf['vnfd_name'], vnf['name'])
                    vdud['cps']=cpds
                
                # vnf configs
                r, configs = get_vnfd_vdud_config_only(mydb, vdud['vdudseq'], 'config')
                if r <= 0:
                    #log.warning("get_nsd_id No VNF VDU Config found %d %s" % (r, configs))
                    pass
                else:
                    for config in configs:
                        for script in config['scripts']:
                            if script['paramorder'] is not None: script['paramorder'] = script['paramorder'].replace(vnf['vnfd_name'], vnf['name'])
                            if script['cookiedata'] is not None: script['cookiedata'] = script['cookiedata'].replace(vnf['vnfd_name'], vnf['name'])
                            if script['requestheaders_args'] is not None: script['requestheaders_args'] = script['requestheaders_args'].replace(vnf['vnfd_name'], vnf['name'])
                            if script['body_args'] is not None: script['body_args'] = script['body_args'].replace(vnf['vnfd_name'], vnf['name'])
                    vdud['configs']=configs
                    
                # vdud_weburl
                r, weburl = get_vnfd_vdud_weburl_only(mydb, vdud['vdudseq'])
                if r <=0:
                    log.warning("get_nsd_id No VNF VDU Web URL found %d %s" %(r, weburl))
                    pass
                else:
                    if weburl[0]['ip_addr'] is not None:
                        weburl[0]['ip_addr'] = weburl[0]['ip_addr'].replace(vnf['vnfd_name'], vnf['name'])
                    if weburl[0]['resource'] is not None:
                        weburl[0]['resource'] = weburl[0]['resource'].replace(vnf['vnfd_name'], vnf['name'])
                    vdud['web_url']=weburl[0]
                
                # vnf monitor
                r, monitors = get_vnfd_vdud_monitor_only(mydb, vdud['vdudseq'], 'monitor')
                if r <= 0:
                    #log.warning("get_nsd_id No VNF VDU Monitor found %d %s" % (r, monitors))
                    pass
                else:
                    vdud['monitors'] = monitors
            vnf['vdus'] = vdus

            r, report_list = get_vnfd_report(mydb, vnf['nfcatseq'])
            if r < 0:
                log.warning("[HJC] Failed to get Report Items from VNFD: %d %s" %(r, report_list))
            elif r > 0:
                vnf['report'] = report_list
                
            r, action_list = get_vnfd_action(mydb, vnf['nfcatseq'])
            if r < 0:
                log.warning("[HJC] Failed to get Action Items from VNFD: %d %s" %(r, action_list))
            elif r > 0:
                vnf['ui_action'] = action_list            
    
    # Get VLD from tb_vld and cpds
    try:
        cpd_r, cpds = get_nsd_cpd_only(mydb, nsd_dict['nscatseq'])
        if cpd_r < 0:
            log.warning("failed to get NSD-CPDs: %d %s" %(cpd_r, str(cpds)))
        else:
            nsd_dict['cpds'] = cpds

        r, vlds = get_nsd_vld_only(mydb, nsd_dict['nscatseq'])
        if r <= 0:
            pass
        else:
            for vld in vlds:
                af.convert_datetime2str_psycopg2(vld)
                cp_r, cpds = get_nsd_vld_cp_only(mydb, vld['vldseq'])
                if cp_r < 0:
                    log.warning("failed to get VLD-CPs: %d %s" %(cp_r, str(cpds)))
                else:
                    vld['connection_points'] = cpds
            nsd_dict['vls'] = vlds

        # Get parameter info from tb_nscatalogs_params
        r, ns_params = get_nsd_param_only(mydb, nsd_dict['nscatseq'])
        if r <= 0:
            #log.warning("get_nsd_id No NS Parameters found %d %s" % (r, ns_params))
            pass
        nsd_dict['parameters'] = ns_params

        af.convert_datetime2str_psycopg2(nsd_dict)
        af.convert_str2boolean(nsd_dict, ('publicyn','builtinyn', 'multipointyn', 'externalyn', 'dhcpyn') )
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return 1, nsd_dict


def get_vnfs_detail_info(mydb, general_data, vim_id=None):

    vnf = {}

    vnf['name'] = general_data['name']
    vnf['resource_template_type'] = general_data['resourcetemplatetype']
    #vnf['resource_template']=general_data['resourcetemplate']
    vnf['vnfd_name'] = general_data['name']
    vnf['description'] = general_data['description']
    vnf['virtualyn'] = general_data['virtualyn']
    vnf['nfmaincategory'] = general_data['nfmaincategory']
    vnf['nfsubcategory'] = general_data['nfsubcategory']
    vnf['vendorcode'] = general_data['vendorcode']
    vnf['version'] = general_data['version']
    vnf['status'] = general_data['status']
    vnf['license_name'] = general_data['license_name']
    vnf['nfcatseq'] = general_data['nfcatseq']
    vnf['display_name'] = vnf['name'] + " (ver." + str(vnf['version']) + ")"

    #vduds
    r, vdus = get_vnfd_vdud_only(mydb, vnf['nfcatseq'])
    if r <= 0:
        log.error("get_nsd_id error failed to get VNF VDUs %d %s" % (r, vdus))
        pass

    for vdud in vdus:
        af.convert_datetime2str_psycopg2(vdud)
        vdud['name'] = vdud['name'].replace(vnf['vnfd_name'], vnf['name'])
        if vim_id is not None:
            r, images = get_vim_images(mydb, vim_id)
            if r <= 0:
                log.warning("get_nsd_id No VIM Image found %d %s" % (r, vdus))
            else:
                vdud['vim_image_id']=images[0]['uuid']
            #TODO: flavor
            #self.cur.execute("SELECT vim_flavor_id FROM tb_vim_flavors WHERE flavor_id='%s' AND vim_id='%s'" %(vdud['flavor_id'],vim_id))
            #if self.cur.rowcount==1:
            #    vim_flavor_dict = self.cur.fetchone()
            #    vdud['vim_flavor_id']=vim_flavor_dict['vim_id']

        # vdud cpds
        r, cpds = get_vnfd_cpd_only(mydb, vdud['vdudseq'])
        if r <= 0:
            #log.warning("get_nsd_id NO VNF VDU CP Found %d %s" %(r, cpds))
            pass
        else:
            for cpd in cpds:
                af.convert_datetime2str_psycopg2(cpd)
                cpd['name'] = cpd['name'].replace(vnf['vnfd_name'], vnf['name'])
            vdud['cps']=cpds

        # vnf configs
        r, configs = get_vnfd_vdud_config_only(mydb, vdud['vdudseq'], 'config')
        if r <= 0:
            #log.warning("get_nsd_id No VNF VDU Config found %d %s" % (r, configs))
            pass
        else:
            for config in configs:
                for script in config['scripts']:
                    if script['paramorder'] is not None: script['paramorder'] = script['paramorder'].replace(vnf['vnfd_name'], vnf['name'])
                    if script['cookiedata'] is not None: script['cookiedata'] = script['cookiedata'].replace(vnf['vnfd_name'], vnf['name'])
                    if script['requestheaders_args'] is not None: script['requestheaders_args'] = script['requestheaders_args'].replace(vnf['vnfd_name'], vnf['name'])
                    if script['body_args'] is not None: script['body_args'] = script['body_args'].replace(vnf['vnfd_name'], vnf['name'])
            vdud['configs']=configs

        # vdud_weburl
        r, weburl = get_vnfd_vdud_weburl_only(mydb, vdud['vdudseq'])
        if r <=0:
            log.warning("get_nsd_id No VNF VDU Web URL found %d %s" %(r, weburl))
            pass
        else:
            if weburl[0]['ip_addr'] is not None: weburl[0]['ip_addr'] = weburl[0]['ip_addr'].replace(vnf['vnfd_name'], vnf['name'])
            if weburl[0]['resource'] is not None: weburl[0]['resource'] = weburl[0]['resource'].replace(vnf['vnfd_name'], vnf['name'])
            vdud['web_url']=weburl[0]

        # vnf monitor
        r, monitors = get_vnfd_vdud_monitor_only(mydb, vdud['vdudseq'], 'monitor')
        if r <= 0:
            #log.warning("get_nsd_id No VNF VDU Monitor found %d %s" % (r, monitors))
            pass
        else:
            vdud['monitors'] = monitors
    vnf['vdus'] = vdus

    r, report_list = get_vnfd_report(mydb, vnf['nfcatseq'])
    if r < 0:
        log.warning("[HJC] Failed to get Report Items from VNFD: %d %s" %(r, report_list))
    elif r > 0:
        vnf['report'] = report_list

    r, action_list = get_vnfd_action(mydb, vnf['nfcatseq'])
    if r < 0:
        log.warning("[HJC] Failed to get Action Items from VNFD: %d %s" %(r, action_list))
    elif r > 0:
        vnf['ui_action'] = action_list

    return 200, vnf


def update_nsd_id(mydb, nsd_dict):
    UPDATE_={}
    if "status" in nsd_dict:
        UPDATE_["status"] = nsd_dict["status"]
    if "display_name" in nsd_dict:
        UPDATE_["display_name"] = nsd_dict["display_name"]
    if "description" in nsd_dict:
        UPDATE_["description"] = nsd_dict["description"]
    if "vendor" in nsd_dict:
        UPDATE_["vendorcode"] = nsd_dict["vendor"]
    if "nscategory" in nsd_dict:
        UPDATE_["nscategory"] = nsd_dict["nscategory"]
    if "resource_template_type" in nsd_dict:
        UPDATE_["resourcetemplatetype"] = nsd_dict["resource_template_type"]
    if "resource_template" in nsd_dict:
        UPDATE_["resourcetemplate"] = nsd_dict["resource_template"]
    
    if len(UPDATE_)>0:
        WHERE_={'nscatseq': nsd_dict['nscatseq']}
        UPDATE_['modify_dttm']=datetime.datetime.now()
        result, content =  mydb.update_rows('tb_nscatalog', UPDATE_, WHERE_, db_debug)
        if result < 0:
            log.error('update_nsd_id Error ' + content + ' updating table tb_nscatalog: ' + str(nsd_dict['nscatseq']))
    else:
        log.error("update_nsd_id Error, No content")
        result = -500
    return result, nsd_dict['nscatseq']


def get_nsd_param_only(mydb, nsd_id):
    result, content = mydb.get_table(FROM='tb_nscatalog_param', WHERE={'nscatseq':nsd_id})
    if result < 0:
        log.error("get_nsd_param_only() No NS Parameters found %d %s" % (result, content))
        
    if result == 0:
        content = []
    
    return result, content


def get_nsd_cpd_only(mydb, nsd_id):
    result, content = mydb.get_table(FROM='tb_nscatalog_cpd', WHERE={'nscatseq':nsd_id})
    if result < 0:
        log.error("get_nsd_cpd_only error %d %s" %(result, content))
    return result, content


def get_nsd_vld_only(mydb, nsd_id):
    result, content = mydb.get_table(FROM='tb_vld', WHERE={'nscatseq':nsd_id})
    if result < 0:
        log.error("get_nsd_vld_only error %d %s" %(result, content))
    return result, content


def get_nsd_vld_cp_only(mydb, vld_id):
    result, content = mydb.get_table(FROM='tb_vld_cp', WHERE={'vldseq':vld_id})
    if result < 0:
        log.error("get_nsd_vld_cp_only error %d %s" %(result, content))
    return result, content


def delete_nsd(mydb, id):
    #scenario table
    #if tenant_id is not None: where_['r.orch_tenant_id']=tenant_id
    if type(id) is int or type(id) is long:
        where_ = {'nscatseq': id}
    elif id.isdigit():
        where_ = {'nscatseq': id}
    else:
        where_ = {'name': id}
    
    r, c = mydb.get_table(FROM='tb_nscatalog', WHERE=where_)
    if r == 0:
        return -HTTP_Bad_Request, "No NSD found with this criteria %s" % str(id)
    elif r > 1:
        return -HTTP_Bad_Request, "More than one scenario found with this criteria %s" % str(id)
    elif r < 0:
        return -HTTP_Internal_Server_Error, "Internal Error, failed to get db records"
    
    # check if nsr exists
    check_result, check_content = mydb.get_table(FROM='tb_nsr', WHERE={'nscatseq':c[0]['nscatseq']})
    if check_result < 0:
        log.error("Cannot delete NSD due to DB Error")
        return -HTTP_Internal_Server_Error, "DB Error"
    elif check_result > 0:
        log.error("Cannot delete NSD. There are NSRs using the NSD %s" %str(c[0]['nscatseq']))
        return -HTTP_Bad_Request, "Cannot delete NSD. There are NSRs using the NSD %s" %str(c[0]['nscatseq'])
    
    result, content = mydb.delete_row_seq("tb_nscatalog", "nscatseq", c[0]['nscatseq'], None, db_debug)

    if result < 0:
        log.error("delete_nsd error %d %s" %(result, content))
    return result, content


def insert_nsr_general_info(mydb, nsr_name, nsr_description, rlt_dict, nsr_seq=None):
    #instance_scenarios
    INSERT_={'name': nsr_name,
        'description': nsr_description,
        'nscatseq': rlt_dict['nscatseq'],
        'customerseq': rlt_dict['customerseq'],
        'vimseq': rlt_dict['vimseq']
    }
    
    if rlt_dict['status'] is not None:
        INSERT_['status'] = rlt_dict['status']
        INSERT_['status_description'] = "Provisioning in progress"
    if rlt_dict['orgnamescode']:
        INSERT_['orgnamescode'] = rlt_dict['orgnamescode']
        
    INSERT_['modify_dttm'] = datetime.datetime.now()
    
    if nsr_seq:
        INSERT_['nsseq'] = nsr_seq
        result, nsr_id =  mydb.new_row_seq('tb_nsr', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)
        if result < 0:
            pass
        else:
            nsr_id = nsr_seq
    else:
        result, nsr_id =  mydb.new_row('tb_nsr', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)
        
    if result<0:
        log.error("insert_nsr_general_info() Error inserting at table tb_nsrs: %s" %str(nsr_id))
    return result, nsr_id


def insert_nsr_as_a_whole(mydb, nsr_name, nsr_description, nsrDict):
    #instance_scenarios
    try:
        # 프로비져닝시 : nsseq는 이미 존재, 디폴트NS설치시 : nsseq 없음.

        # nsr_pre_exist, nsr_pre_data = get_nsr_general_info(mydb, nsr_name)
        # if nsr_pre_exist < 0:
        #     error_msg = "failed to check if there is pre-existing DB data for the NSR %s" %nsr_name
        #     log.error(error_msg)
        #     return nsr_pre_exist, nsr_pre_data
        
        instanceDict = {'name': nsr_name,
                        'description': nsr_description,
                        'vimseq': nsrDict['vimseq'],
                        'uuid': nsrDict['uuid'],
                        'customerseq': nsrDict['customerseq']
                        }
        
        if nsrDict['status']:
            instanceDict['status'] = nsrDict['status']
        
        instanceDict['modify_dttm'] = datetime.datetime.now()

        if "nsseq" in nsrDict and nsrDict["nsseq"] is not None:
            instance_id = nsrDict['nsseq']
            where_={'nsseq':instance_id}
            result, update_content = mydb.update_rows('tb_nsr', instanceDict, where_)
        else:
            result, instance_id =  mydb.new_row('tb_nsr', instanceDict, None, False, db_debug)
            
        if result < 0:
            log.error('insert_nsr_as_a_whole Error inserting at table tb_nsr: %s' % str(instance_id))
            return result, instance_id
    except KeyError as e:
        log.exception("Error while creating a NSR. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while creating a NSR, KeyError " + str(e)
    
    nsrDict['nsseq'] = instance_id
    
    #instance_vnfs
    for vnf in nsrDict['vnfs']:
        vm_configs_json = json.dumps("{}", indent=4)
        for vm in vnf['vdus']:
            if 'configs' in vm:
                vm_configs = vm['configs']
                vm_configs_json = json.dumps(vm_configs, indent=4)
                break                
        
        INSERT_={'nsseq': instance_id, 'nfcatseq': vnf['nfcatseq'], 'status':vnf['status'], 'name':vnf['name'], 'configsettings':vm_configs_json
            , 'description':vnf['description'], 'weburl':vnf.get('weburl', "None"), 'license':vnf.get('license','None')
            , 'webaccount':vnf.get('webaccount', "-")}

        if 'orgnamescode' in vnf:
            INSERT_['orgnamescode'] = vnf['orgnamescode']
        if 'deploy_info' in vnf:
            INSERT_['deploy_info'] = vnf['deploy_info']
        if 'service_number' in vnf:
            INSERT_['service_number'] = vnf['service_number']
        if 'service_period' in vnf:
            INSERT_['service_period'] = vnf['service_period']

        # vnf image 정보저장 : vnf_image_version, vnf_sw_version
        vnf_image_name = None
        for param in nsrDict["parameters"]:
            if param["name"] == "RPARM_imageId_" + vnf["name"]:
                vnf_image_name = param["value"]
                break
        if vnf_image_name:
            result, imgs = get_vnfd_vdu_image(mydb, {"name" : vnf_image_name})
            if result < 0:
                log.error("Failed to get tb_vdud_image record : name = %s" % vnf_image_name)
                return result, imgs
            elif result == 0:
                log.error("Not Found VNF Image(%s). " % vnf_image_name)
                return -500, "Not Found VNF Image(%s). First, regist VNF Image!!!" % vnf_image_name

            img = imgs[0]
            INSERT_["vnf_image_version"] = img["vnf_image_version"]
            INSERT_["vnf_sw_version"] = img["vnf_sw_version"]
            INSERT_["vdudimageseq"] = img["vdudimageseq"]

        r,instance_vnf_id =  mydb.new_row('tb_nfr', INSERT_, None, False, db_debug)
        if r<0:
            log.error('insert_nsr_as_a_whole() Error inserting at table tb_nfr: ' + instance_vnf_id)
            return r, instance_vnf_id                
        vnf['nfseq'] = instance_vnf_id
        
        #instance_vms
        for vm in vnf['vdus']:
            INSERT_={'name':vm['name'], 'uuid': vm.get('uuid'), 'vim_name':vm.get('vim_name'), 'nfseq': instance_vnf_id,  'vdudseq': vm['vdudseq'], 'weburl':vm.get('weburl', "None") }
            INSERT_['mgmtip'] = vm.get('mgmtip')
            INSERT_['vm_access_id'] = vm.get("vm_access_id")
            INSERT_['vm_access_passwd'] = vm.get("vm_access_passwd")
            if 'orgnamescode' in vnf:
                INSERT_['orgnamescode'] = vm['orgnamescode']
            if 'status' in vm:
                INSERT_['status'] = vm['status']
            INSERT_['modify_dttm'] = datetime.datetime.now()
            r,instance_vm_id =  mydb.new_row('tb_vdu', INSERT_, None, False, db_debug)
            if r<0:
                log.error('insert_nsr_as_a_whole() Error inserting at table tb_vdu: ' + instance_vm_id)
                return r, instance_vm_id
            vm['vduseq']=instance_vm_id
            
            #cp
            if 'cps' in vm:
                for cp in vm['cps']:
                    INSERT_={'name':cp['name'], 'uuid':cp['uuid'], 'vim_name':cp['vim_name'], 'vduseq': instance_vm_id, 'cpdseq': cp['cpdseq'], 'ip':cp.get('ip')} 
                    log.debug("[HJC] DB Insert - CP: %s" %str(INSERT_))

                    INSERT_['modify_dttm'] = datetime.datetime.now()
                    r, instance_cp_id = mydb.new_row('tb_cp', INSERT_, None, False, db_debug)
                    if r<0:
                        log.warning('insert_nsr_as_a_whole() Error failed to insert CP Record into tb_cp %d %s' %(r, instance_cp_id))
                    cp['cpseq']=instance_cp_id
        
        if 'ui_action' in vnf:
            for action in vnf['ui_action']:
                INSERT_ = {'nfseq': vnf['nfseq'], 'name': action['name'], 'display_name': action['display_name'], 'api_resource': action['api_resource'], 'api_body_format': action['api_body_format'], 'api_body_param': action['api_body_param']}
                log.debug("[HJC] UI Action DB Insert: %s" %str(INSERT_))
                r, vnf_action_id = mydb.new_row('tb_nfr_action', INSERT_, None, False, db_debug)
                if r < 0:
                    log.warning("failed to insert nsr vnf action items: %d %s" %(r, vnf_action_id))
        
        if 'report' in vnf:
            for report in vnf['report']:
                INSERT_ = {'nfseq': vnf['nfseq'], 'name': report['name'], 'display_name': report['display_name'], 'data_provider': report['data_provider'], 'value': report.get('value')}
                log.debug("[HJC] UI Report DB Insert: %s" %str(INSERT_))
                r, vnf_report_id = mydb.new_row('tb_nfr_report', INSERT_, None, False, db_debug)
                if r < 0:
                    log.warning("failed to insert nsr vnf report items: %d %s" %(r, vnf_report_id))

    return result, instance_id


def insert_nsr_params(mydb, nsr_id, params):
    try:
        for param in params:
            INSERT_={'nsseq':nsr_id, 'name':param['name'], 'type':param['type'], 'description':param['description'], 'category':param['category'], 'value':param['value'], 'ownername':param['ownername']}

            # if len(str(param['value'])) > 28:
            #     log.debug("___________@@@@___________ insert_nsr_params ERROR : %s " % param)
            r,param_id = mydb.new_row('tb_nsr_param', INSERT_, None, False, db_debug)
            if r<0:
                log.warning('insert_nsr_params() failed to insert at table tb_nsr_param: ' + param_id)
                pass   
    except KeyError as e:
        log.exception("Error while inserting params into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while inserting params into DB. KeyError: " + str(e)
    
    return 200, nsr_id


def update_nsr_as_a_whole(mydb, nsr_name, nsr_description, nsrDict):
    #instance_scenarios
    instanceDict = {'nsseq':nsrDict['nsseq'],
                    'name': nsr_name,
                    'description': nsr_description,
                    'vimseq': nsrDict['vimseq'],
                    'uuid': nsrDict['uuid'],
                    'customerseq': nsrDict['customerseq']
                    }
    
    if nsrDict['status']: instanceDict['status'] = nsrDict['status']
   
    result, update_content = update_nsr(mydb, instanceDict)
        
    if result<0:
        log.error("update_nsr_as_a_whole Error inserting at table tb_nsr: %s" %str(nsrDict['nsseq']))
        return result, nsrDict['nsseq']

    #instance_vnfs
    for vnf in nsrDict['vnfs']:
        # vnf['nfseq'] 가 존재하면 update, 없으면 insert
        result, vnf_info = get_vnf_id(mydb, vnf['nfseq'])
        action_flag = "U"
        if result == -HTTP_Not_Found:
            action_flag = "C"

        if action_flag == "U":

            if 'weburl' in vnf:
                vnf['web_url'] = vnf['weburl']

            if 'web_url' in vnf:
                UPDATE_ = {'nfseq':vnf['nfseq']}
                UPDATE_['weburl'] = vnf['web_url']

                r, instance_vnf_id = update_vnf_weburl(mydb, UPDATE_)
                if r < 0:
                    log.error("failed to update vnf: %d %s" %(r, instance_vnf_id))
                    return r, instance_vnf_id

            #instance_vms
            for vm in vnf['vdus']:
                UPDATE_={'vduseq':vm['vduseq'], 'uuid': vm.get('uuid'), 'vim_name':vm.get('vim_name'), 'nfseq': vnf['nfseq'], 'mgmtip': vm.get('mgmtip')}

                if 'web_url' in vm:
                    if type(vm['web_url']) == str or type(vm['web_url']) == unicode:
                        UPDATE_['weburl'] = vm['web_url']
                    else:
                        if 'weburl' in vm and (type(vm['weburl']) == str or type(vm['web_url']) == unicode):
                            vm['web_url'] = vm['weburl']
                            UPDATE_['weburl'] = vm['web_url']

                r, instance_vm_id = update_nsr_vdu(mydb, UPDATE_)
                if r<0:
                    log.error('update_nsr_as_a_whole() Error updating vdu: ' + instance_vm_id)
                    return r, instance_vm_id

                #cp
                if 'cps' in vm:
                    result, content = mydb.delete_row_seq("tb_cp", "vduseq", vm['vduseq'], None)
                    if result < 0:
                        log.error("delete cp error %d %s" % (result, content))
                    else:
                        for cp in vm['cps']:
                            INSERT_={'name':cp['name'], 'uuid':cp['uuid'], 'vim_name':cp['vim_name'], 'vduseq': vm['vduseq'], 'cpdseq': cp['cpdseq'], 'ip':cp.get('ip')}
                            INSERT_['modify_dttm'] = datetime.datetime.now()
                            r, instance_cp_id = mydb.new_row('tb_cp', INSERT_)
                            if r < 0:
                                log.warning('update_nsr_as_a_whole() Error failed to insert CP Record into tb_cp %d %s' %(r, instance_cp_id))
                            cp['cpseq']=instance_cp_id
        else:
            vm_configs_json = json.dumps("{}", indent=4)
            for vm in vnf['vdus']:
                if 'configs' in vm:
                    vm_configs = vm['configs']
                    vm_configs_json = json.dumps(vm_configs, indent=4)
                    break

            INSERT_={'nfseq': vnf['nfseq'], 'nsseq': nsrDict['nsseq'], 'nfcatseq': vnf['nfcatseq'], 'status':vnf['status'], 'name':vnf['name'],
                     'configsettings':vm_configs_json, 'description':vnf['description'], 'weburl':vnf.get('weburl', "None"),
                     'license':vnf.get('license','None'), 'webaccount':vnf.get('webaccount', "-")}
            if 'orgnamescode' in vnf:
                INSERT_['orgnamescode'] = vnf['orgnamescode']
            if 'deploy_info' in vnf:
                INSERT_['deploy_info'] = vnf['deploy_info']
            if 'service_number' in vnf:
                INSERT_['service_number'] = vnf['service_number']
            if 'service_period' in vnf:
                INSERT_['service_period'] = vnf['service_period']

            # vnf image 정보저장 : vnf_image_version, vnf_sw_version
            vnf_image_name = None
            for param in nsrDict["parameters"]:
                if param["name"] == "RPARM_imageId_" + vnf["name"]:
                    vnf_image_name = param["value"]
                    break
            if vnf_image_name:
                result, imgs = get_vnfd_vdu_image(mydb, {"name" : vnf_image_name})
                if result < 0:
                    log.error("Failed to get tb_vdud_image record : name = %s" % vnf_image_name)
                    return result, imgs
                elif result == 0:
                    log.error("Not Found VNF Image(%s). " % vnf_image_name)
                    return -500, "Not Found VNF Image(%s). First, regist VNF Image!!!" % vnf_image_name

                img = imgs[0]
                INSERT_["vnf_image_version"] = img["vnf_image_version"]
                INSERT_["vnf_sw_version"] = img["vnf_sw_version"]
                INSERT_["vdudimageseq"] = img["vdudimageseq"]

            r,instance_vnf_id =  mydb.new_row_seq('tb_nfr', INSERT_)
            if r<0:
                log.error('insert_nsr_as_a_whole() Error inserting at table tb_nfr: ' + instance_vnf_id)
                return r, instance_vnf_id

            #instance_vms
            for vm in vnf['vdus']:
                INSERT_={'vduseq': vm['vduseq'],'name':vm['name'], 'uuid': vm.get('uuid'), 'vim_name':vm.get('vim_name'),
                         'nfseq': vnf['nfseq'],  'vdudseq': vm['vdudseq'], 'weburl':vm.get('weburl', "None") }
                INSERT_['mgmtip'] = vm.get('mgmtip')
                INSERT_['vm_access_id'] = vm.get("vm_access_id")
                INSERT_['vm_access_passwd'] = vm.get("vm_access_passwd")
                if 'orgnamescode' in vnf:
                    INSERT_['orgnamescode'] = vm['orgnamescode']
                INSERT_['modify_dttm'] = datetime.datetime.now()

                r,instance_vm_id =  mydb.new_row_seq('tb_vdu', INSERT_)
                if r<0:
                    log.error('insert_nsr_as_a_whole() Error inserting at table tb_vdu: ' + instance_vm_id)
                    return r, instance_vm_id

                #cp
                if 'cps' in vm:
                    for cp in vm['cps']:
                        INSERT_={'cpseq': cp['cpseq'],'name':cp['name'], 'uuid':cp['uuid'], 'vim_name':cp['vim_name'],
                                 'vduseq': vm['vduseq'], 'cpdseq': cp['cpdseq'], 'ip':cp.get('ip')}
                        INSERT_['modify_dttm'] = datetime.datetime.now()

                        r, instance_cp_id = mydb.new_row_seq('tb_cp', INSERT_)
                        if r<0:
                            log.warning('insert_nsr_as_a_whole() Error failed to insert CP Record into tb_cp %d %s' %(r, instance_cp_id))
    return 200, nsrDict['nsseq']


def insert_nsr_params_cache(mydb, server_id, nsd_id, params):
    try:
        for param in params:
            INSERT_ = {'serverseq':server_id, 'nscatseq':nsd_id, 'name':param['name'], 'type':param['type'], 'description':param['description'], 'category':param['category'], 'value':param['value']}
            r,param_id = mydb.new_row('tb_nsr_params_cache', INSERT_, None, False, db_debug)
            if r<0:
                #log.warning('insert_nsr_params_cache() Error inserting at table tb_nsr_params_cache: ' + param_id)
                pass   
    except KeyError as e:
        log.exception("Error while inserting params into Cache DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while inserting params into Cache DB. KeyError: " + str(e)
    
    return 200, nsd_id


def delete_nsr_params_cache(mydb, server_id, nsd_id):
    
    result, content = mydb.delete_row_by_dict(FROM="tb_nsr_params_cache", WHERE={"serverseq": server_id, "nscatseq":nsd_id})
    if result < 0:
        log.warning("delete_nsr_params_cache() error: %d %s" %(result, content))
    
    #log.debug("delete_nsr_params_cache() result: %d %s" %(result, content))
    
    return result, content


def get_nsr_params_cache(mydb, server_id, nsd_id):
    where_ = {"serverseq":server_id, "nscatseq":nsd_id}
    result, content = mydb.get_table(FROM='tb_nsr_params_cache', WHERE=where_)
    if result < 0:
        log.error("get_nsr_params_cache() error: %d %s" %(result, content))
    
    return result, content


def get_nsr(mydb, qs):
    select_, where_, limit_=filter_query_string(qs, None, ('nsseq', 'uuid', 'name', 'nscatseq', 'customerseq', 'description', 'reg_dttm', 'modify_dttm', 'status', 'action'))
    result, data = mydb.get_table(SELECT=select_, LIMIT=limit_, FROM='tb_nsr', ORDER='modify_dttm desc')

    if result < 0:
        log.error("get_nsr error %d %s" %(result, data))
        return result, data

    for d in data:
        customer_result, customer_data = get_customer_id(mydb, d['customerseq'])
        if result <= 0:
            log.warning("get_nsr() failed to get customer info")
            d['customername']="-"
        else:
            d['customername']=customer_data['customername']

        server_result, server_data = mydb.get_table(FROM='tb_server', SELECT=('onebox_id', 'ob_service_number', 'servername'), WHERE={'nsseq':d['nsseq']})
        if server_result < 0:
            log.warning("failed to get server info from DB")
            log.debug("failed to get server info from DB")
        else:
            d['onebox_id'] = server_data[0]['onebox_id']
            d['ob_service_number'] = server_data[0]['ob_service_number']
            d['servername'] = server_data[0]['servername']

        nfr_result, nfr_data = mydb.get_table(FROM='tb_nfr', SELECT=('name', 'description', 'nfcatseq', 'status', 'weburl', 'webaccount', 'license', 'reg_dttm', 'modify_dttm', 'service_number', 'service_period', 'service_start_dttm', 'service_end_dttm'), WHERE={'nsseq':d['nsseq']})
        if nfr_result < 0:
            log.warning("get_nsr() failed to get NFRs included by NSR %d %s" % (nfr_result, nfr_data))
            d['nfr'] = None
        elif nfr_result == 0:
            #log.error("get_nsr error No NFR Found %d %s" % (nfr_result,nfr_data))
            #return -HTTP_Internal_Server_Error, "No VNF Found for the NSD"
            d['nfr'] = None
        else:
            for nfr in nfr_data:
                af.convert_datetime2str_psycopg2(nfr)
            d['nfr'] = nfr_data
    
    return 200, data


def get_nsr_all(mydb):
    result, data = mydb.get_table(FROM='tb_nsr')
    
    if result < 0:
        log.error("get_nsr_all error %d %s" %(result, data))
        return result, data
    
    for d in data:
        customer_result, customer_data = get_customer_id(mydb, d['customerseq'])
        if result <= 0:
            log.warning("get_nsr_all() failed to get customer info")
            d['customername']="-"
        else:
            d['customername']=customer_data['customername']
        
        nfr_result, nfr_data = mydb.get_table(FROM='tb_nfr', SELECT=('name', 'description', 'nfcatseq', 'status', 'weburl', 'webaccount', 'license', 'reg_dttm', 'modify_dttm', 'service_number', 'service_period', 'service_start_dttm', 'service_end_dttm'), WHERE={'nsseq':d['nsseq']})
        if nfr_result < 0:
            log.warning("get_nsr_all() failed to get NFRs included by NSR %d %s" % (nfr_result, nfr_data))
            d['nfr'] = None
        elif nfr_result == 0:
            #log.error("get_nsr error No NFR Found %d %s" % (nfr_result,nfr_data))
            #return -HTTP_Internal_Server_Error, "No VNF Found for the NSD"
            d['nfr'] = None
        else:
            for nfr in nfr_data:
                af.convert_datetime2str_psycopg2(nfr)
            d['nfr'] = nfr_data
    
    # d_result, d_data = _get_deleted_item(mydb, "tb_nsr")
    # if result < 0:
    #     log.warning("get_nsr_all() no nsr found from tb_deleted")
    # else:
    #     for dd in d_data:
    #         c_result, c_data = get_customer_id(mydb, dd['customerseq'])
    #         if c_result <= 0:
    #             dd['customername']="Not Exist"
    #         else:
    #             dd['customername']=c_data['customername']
    #
    #         dd['status'] = 'deleted'
    #         dd.pop('userseq')
    #         dd.pop('item_backup1')
    #         dd.pop('item_backup2')
    #         dd.pop('item_backup3')
    #
    #         data.append(dd)
    
    return 200, data


def update_nsr(mydb, instance_dict):
    if 'nsseq' not in instance_dict:
        return -HTTP_Not_Found, "No target seq in the request"
    UPDATE_={}
    if "status" in instance_dict:
        UPDATE_["status"] = instance_dict["status"]
    if "status_description" in instance_dict:
        UPDATE_["status_description"] = instance_dict["status_description"]
    if "uuid" in instance_dict:
        UPDATE_["uuid"] = instance_dict["uuid"]
    if "action" in instance_dict:
        UPDATE_["action"] = instance_dict["action"]

    result = -HTTP_Not_Found
    if len(UPDATE_)>0:
        WHERE_={'nsseq': instance_dict['nsseq']}
        
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_nsr', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nsr Error ' + content + ' updating table tb_nsr: ' + str(instance_dict['nsseq']))
    return result, instance_dict['nsseq']


def update_vnf_weburl(mydb, vnf_dict):
    UPDATE_ = {}
    if "weburl" in vnf_dict:        UPDATE_["weburl"] = vnf_dict["weburl"]

    if len(UPDATE_) > 0:
        WHERE_ = {'nfseq': vnf_dict['nfseq']}
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_nfr', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_vnf_weburl Error ' + content + ' updating table tb_nfr: ' + str(vnf_dict['nfseq']))
    else:
        log.warning("No Update Data")
        result = 200

    return result, vnf_dict['nfseq']


def update_nsr_vnf(mydb, vnf_dict, chg_nfcatseq=False):
    UPDATE_ = {}
    if "status" in vnf_dict:        UPDATE_["status"] = vnf_dict["status"]
    if "action" in vnf_dict:        UPDATE_["action"] = vnf_dict["action"]
    # if "weburl" in vnf_dict:        UPDATE_["weburl"] = vnf_dict["weburl"]
    if "service_number" in vnf_dict: UPDATE_["service_number"] = vnf_dict["service_number"]
    if "service_period" in vnf_dict: UPDATE_["service_period"] = vnf_dict["service_period"]
    if vnf_dict.get("service_start_dttm"): UPDATE_["service_start_dttm"] = datetime.datetime.strptime(vnf_dict["service_start_dttm"], '%Y-%m-%d %H:%M:%S')
    if vnf_dict.get("service_end_dttm"): UPDATE_["service_end_dttm"] = datetime.datetime.strptime(vnf_dict["service_end_dttm"], '%Y-%m-%d %H:%M:%S')
    #if "status_description" in vnf_dict: UPDATE_["status_description"] = vnf_dict["status_description"]
    if vnf_dict.get("vnf_image_version"): UPDATE_["vnf_image_version"] = vnf_dict["vnf_image_version"]
    if vnf_dict.get("vnf_sw_version"): UPDATE_["vnf_sw_version"] = vnf_dict["vnf_sw_version"]
    if vnf_dict.get("vdudimageseq"): UPDATE_["vdudimageseq"] = vnf_dict["vdudimageseq"]

    if chg_nfcatseq:
        if vnf_dict.get("nfcatseq"): UPDATE_["nfcatseq"] = vnf_dict["nfcatseq"]

    if len(UPDATE_) > 0:
        WHERE_ = {'nfseq': vnf_dict['nfseq']}
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_nfr', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nsr_vnf Error ' + content + ' updating table tb_nfr: ' + str(vnf_dict['nfseq']))
    else:
        log.warning("No Update Data")
        result = 200

    return result, vnf_dict['nfseq']


def update_vnf_sw_version(mydb, vnf_dict):
    UPDATE_ = {}
    if "vnf_sw_version" in vnf_dict:
        UPDATE_["vnf_sw_version"] = vnf_dict["vnf_sw_version"]

    WHERE_ = {'vdudimageseq': vnf_dict['vdudimageseq']}
    UPDATE_['modify_dttm'] = datetime.datetime.now()
    result, content = mydb.update_rows('tb_nfr', UPDATE_, WHERE_)
    if result < 0:
        log.error('update_vnf_sw_version Error ' + content + ' updating table tb_nfr: ' + str(vnf_dict['vdudimageseq']))

    return result, vnf_dict['vdudimageseq']


def update_nsr_vnf_report(mydb, report_list):
    for report in report_list:
        if report.get('seq') is None:
            continue

        UPDATE_= {}

        if "value" in report:
            UPDATE_['value'] = report['value']
        
        if len(UPDATE_) > 0:
            WHERE_={'seq': report['seq']}
            result, content = mydb.update_rows('tb_nfr_report', UPDATE_, WHERE_)
            if result < 0:
                log.warning("update_nsr_vnf_report Error: %d %s" %(result, content))
            else:
                log.debug("update_nsr_vnf_report Success: %d %s" %(result, str(content)))
    
    return 200, "OK"


def update_nsr_vdu(mydb, vdu_dict):

    UPDATE_ = {}
    if "status" in vdu_dict: UPDATE_["status"]=vdu_dict["status"]
    if "uuid" in vdu_dict: UPDATE_["uuid"]=vdu_dict["uuid"]
    if "vim_name" in vdu_dict: UPDATE_["vim_name"]=vdu_dict["vim_name"]
    if "mgmtip" in vdu_dict: UPDATE_["mgmtip"]=vdu_dict["mgmtip"]
    if "weburl" in vdu_dict: UPDATE_["weburl"]=vdu_dict["weburl"]
    
    if len(UPDATE_) > 0:
        WHERE_ = {'vduseq': vdu_dict['vduseq']}
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_vdu', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nsr_vdu Error ' + content + ' updating table tb_vdu: ' + str(vdu_dict['vduseq']))
        return result, vdu_dict['vduseq']
    return -500, "Invalid Parameters : %s" % vdu_dict


def update_nsr_vdu_status(mydb, vdu_dict):

    UPDATE_ = {}
    if "status" in vdu_dict: UPDATE_["status"]=vdu_dict["status"]

    if len(UPDATE_) > 0:
        WHERE_ = {'vduseq': vdu_dict['vduseq']}
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_vdu', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nsr_vdu Error ' + content + ' updating table tb_vdu: ' + str(vdu_dict['vduseq']))
        return result, vdu_dict['vduseq']
    return -500, "No status"


def update_nsr_vdu_cp(mydb, cp_dict):
    UPDATE_ = {}
    if "uuid" in cp_dict: UPDATE_["uuid"]=cp_dict["uuid"]
    if "vim_name" in cp_dict: UPDATE_["vim_name"]=cp_dict["vim_name"]
    if "ip" in cp_dict: UPDATE_["ip"]=cp_dict["ip"]
    
    if len(UPDATE_) > 0:
        WHERE_ = {'cpseq': cp_dict['cpseq']}
        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_cp', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nsr_vdu_cp Error ' + content + ' updating table tb_cp: ' + str(cp_dict['cpseq']))
        return result, cp_dict['cpseq']
    return -500, "Invalid Parameters : %s" % cp_dict


def update_nsr_vnfvm(mydb, vnfvm_dict):
    UPDATE_ = {}
    if "status" in vnfvm_dict:
        UPDATE_["status"] = vnfvm_dict["status"]

    if len(UPDATE_)>0:
        WHERE_={'vduseq': vnfvm_dict['vduseq']}
        UPDATE_['modify_dttm']=datetime.datetime.now()
        result, content =  mydb.update_rows('tb_vdu', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nsr_vnfvm Error ' + content + ' updating table tb_vdu: ' + str(vnfvm_dict['vduseq']))
        return result, vnfvm_dict['vduseq']
    return -500, "No status"


# 단순 table 정보 조회
def get_table_data(mydb, instance_dict, table_name, query_string=None):
    if table_name == "tb_auto_cmd" or table_name == "tb_auto_cmd_target":
        where_free = query_string
        result, content = mydb.get_table_free(FROM=table_name, WHERE_FREE=where_free)

        if result < 0:
            log.error("get_%s_general_info error %d %s" % (str(table_name), result, content))
            return result, content
        return result, content
    else:
        where_ = {}
        if table_name == "tb_nsr" or table_name == "tb_nfr":
            where_ = {"nsseq": instance_dict.get('nsseq')}
        elif table_name == "tb_vdu":
            where_ = {"nfseq": instance_dict.get('nfseq')}
        elif table_name == "tb_server":
            where_ = {'serverseq': instance_dict.get('serverseq')}

        result, content = mydb.get_table(FROM=table_name, WHERE=where_)

        if result < 0:
            log.error("get_%s_general_info error %d %s" % (str(table_name), result, content))
            return result, content
        return result, content[0]


def get_nsr_general_info(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {'nsseq': id}
    elif id.isdigit():
        where_ = {'nsseq': id}
    else:
        where_ = {'name': id}
    
    result, content = mydb.get_table(FROM='tb_nsr', WHERE=where_)
    if result <= 0:
        log.error("get_nsr_general_info error %d %s" % (result, content))
        return result, content
    return result, content[0]


def get_vdu_id(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {'vduseq':id}
    elif id.isdigit():
        where_ = {'vduseq':id}
    else:
        where_ = {'name':id}
    
    result, content = mydb.get_table(FROM='tb_vdu', WHERE=where_)
    if result < 0:
        log.error("get_vdu_id error %d %s" %(result, content))
        return result, content
    elif result == 0:
        log.error("get_vdu_id error VDU Not Found")
        return -HTTP_Not_Found, "VDU Not Found"
    
    return result, content[0]


def get_vnf_cp_only(mydb, vdu_id):
    result, content = mydb.get_table(FROM='tb_cp', WHERE={'vduseq':vdu_id})
    if result < 0:
        log.error("get_vnf_cp_only error %d %s" %(result, content))
    return result, content


def get_nsr_general_info_with_nfr_id (mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {'f.nfseq':id}
    elif id.isdigit():
        where_ = {'f.nfseq':id}
    else:
        where_ = {'f.name':id}
        
    from_ = "tb_nsr as r join tb_nfr as f on r.nsseq=f.nsseq"
    select_ = ('r.name as ns_name', 'r.nsseq as nsseq', 'r.status as ns_status', 'r.vimseq as vimseq', 'f.name as nf_name')
    
    result, content = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
    
    if result < 0:
        log.error("get_nsr_general_info_with_nfr_id %d %s" %(result, content))
        return result, content
    elif result == 0:
        log.error("get_nsr_general_info_with_nfr_id error NSR Not Found")
        return -HTTP_Not_Found, "NSR for the VDU Not Found"
    
    return result, content[0]


def get_vnf_report(mydb, vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfr_report', WHERE={'nfseq': vnf_id})
        if result <= 0:
            log.warning("failed to get report items for VNF Record: %s" %str(vnf_id))
            return -HTTP_Not_Found, []
        
        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    return -HTTP_Internal_Server_Error, "Failed to get VNFR report items"


def update_vnf_report(mydb, report_dict):
    try:
        UPDATE_ = {}
        if "value" in report_dict:        UPDATE_["value"] = report_dict["value"]
    
        if len(UPDATE_)>0:
            WHERE_={'seq': report_dict['seq']}
            result, content =  mydb.update_rows('tb_nfr_report', UPDATE_, WHERE_)
            
            if result < 0:
                log.error("failed to update nfr report: %d %s" %(result, content))
                return result, content
            
            return result, report_dict['nfseq']

    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "Failed to update VNFR report items"


def get_vnf_action(mydb, vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfr_action', WHERE={'nfseq': vnf_id})
        if result <= 0:
            log.warning("failed to get action items for VNF Record: %s" %str(vnf_id))
            return -HTTP_Not_Found, []
        
        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    return -HTTP_Internal_Server_Error, "Failed to get VNFR action items"


def get_vnf_only(mydb, condition):
    try:
        if "nfseq" in condition:
            where_ = {'nfseq': condition['nfseq']}
        elif "name" in condition and "nsseq" in condition:
            where_ = {'name': condition['name'], 'nsseq': condition['nsseq']}
        else:
            return -HTTP_Bad_Request, "Not enough condition"

        result, content = mydb.get_table(FROM='tb_nfr', WHERE=where_)
        if result < 0:
            log.error("Failed to get nfr data, condition = %s" % str(condition))
            return result, content

        if content is None or len(content) <= 0:
            log.warning("Failed to get nfr data [No Data] , condition = %s" % str(condition))
            return result, content

        return result, content[0]
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return -HTTP_Internal_Server_Error, "Failed to get nfr data"


def get_vnf_id(mydb, id):
    if type(id) is int or type(id) is long:
        where_ = {'nfseq':id}
    elif id.isdigit():
        where_ = {'nfseq':id}
    else:
        where_ = {'nfseq':id}
        
    vnf_result, vnf_content = mydb.get_table(FROM='tb_nfr', WHERE=where_)
    
    if vnf_result < 0:
        return -HTTP_Internal_Server_Error, "failed to get VNF Info %s" %str(where_)
    elif vnf_result == 0:
        return -HTTP_Not_Found, "None VNF data %s" %str(where_)
    
    data = vnf_content[0]
    af.convert_datetime2str_psycopg2(data)
    
    #instance vms
    select_ = ('v.vduseq as vduseq', 'v.uuid as uuid', 'v.vim_name as vim_name', 'v.status as status', 'v.vdudseq as vdudseq', 'v.reg_dttm as reg_dttm', 'tb_vdud.name as name', 'v.mgmtip as mgmtip')
    from_ = "tb_vdu as v join tb_vdud on v.vdudseq=tb_vdud.vdudseq"
    where_ = {'v.nfseq':data['nfseq']}
    r, vdus = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
    
    if r <= 0:
        return -HTTP_Internal_Server_Error, "failed to get VNF VDU Info. for the VNF Instance %s" % str(id)
    
    for vm in vdus:
        af.convert_datetime2str_psycopg2(vm)
        #CP
        select_ = ('cpseq', 'cpdseq', 'name', 'uuid', 'vim_name', 'ip', 'vduseq', 'reg_dttm', 'modify_dttm')
        r, cps = mydb.get_table(SELECT=select_, FROM='tb_cp', WHERE={'vduseq':vm['vduseq']})
        if r<=0:
            log.warning("No CP Found for the VDU %s" %str(vm['vduseq']))
        
        for cp in cps:
            af.convert_datetime2str_psycopg2(cp)
        vm['cps']=cps
        
        #VNF Configuration
        r, configs = get_vnfd_vdud_config_only(mydb, vm['vdudseq'], 'config')
        if r <= 0:
            log.error("failed to get VNF VDU Config %d %s" % (r, configs))
        vm['configs']=configs
        
        #VNF Monitor
        r, monitors = get_vnfd_vdud_monitor_only(mydb, vm['vdudseq'], 'monitor')
        if r <=0:
            log.error('failed to get VNF VDU Monitor %d %s' %(r, monitors))
        vm['monitors']=monitors
        
    data['vdus'] = vdus
    
    return 200, data


def get_nsr_id(mydb, id):

    if id is None:
        return -HTTP_Bad_Request, "Invalid nsr_id"
    
    #instance table
    if type(id) is int or type(id) is long:
        log.debug("get_nsr_id() type of id is int or long")
        where_={'r.nsseq':id}
    elif id.isdigit():
        log.debug("get_nsr_id() type of id is string having a digit")
        where_={'r.nsseq':id}
    else:
        log.debug("get_nsr_id() type of id is string having a name")
        where_={'r.name':id}
        
    select_ = ('r.uuid as uuid', 'r.name as name', 'r.action as action', 'r.nscatseq as nscatseq', 'vimseq', 'r.nsseq as nsseq',
               's.name as nscatalog_name', 's.display_name as display_name', 'r.status as status', 'r.customerseq as customerseq',
               'r.description as description','r.reg_dttm as reg_dttm')
    from_ = "tb_nsr as r join tb_nscatalog as s on r.nscatseq=s.nscatseq"
    
    result, content = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
    
    log.debug("get_nsr_id() where = %s, result = %d, content = %s" %(str(where_), result, str(content)))
    
    if result == 0:
        return -HTTP_Not_Found, "No NSR found with this criteria " + str(id)
    elif result > 1:
        return -HTTP_Bad_Request, "More than one NSR found with this criteria " + str(id)
    elif result < 0:
        return -HTTP_Internal_Server_Error, "DB Error " + str(id)
    instance_dict = content[0]
    
    #instance_vnfs
    select_ = ('tb_nfr.nfseq as nfseq', 'tb_nfr.name as name', 'tb_nfr.description as description', 'tb_nfr.action as action', 'tb_nfr.nfcatseq as nfcatseq'
               , 'tb_nfr.status as status', 'tb_nfr.weburl as web_url', 'tb_nfr.webaccount as webaccount'
               , 'tb_nfr.license as license', 'tb_nfr.deploy_info as deploy_info'
               , 'tb_nfr.service_number as service_number', 'tb_nfr.service_period as service_period'
               , 'tb_nfr.service_start_dttm as service_start_dttm', 'tb_nfr.service_end_dttm as service_end_dttm'
               , 'tb_nfcatalog.name as nfcatalog_name', 'tb_nfcatalog.name as vnfd_name', 'tb_nfcatalog.nfsubcategory as nfsubcategory'
               , 'tb_nfcatalog.vendorcode as vendorcode', 'tb_nfcatalog.version as version', 'tb_nfcatalog.display_name as display_name')

    from_ = "tb_nfr join tb_nfcatalog on tb_nfr.nfcatseq=tb_nfcatalog.nfcatseq"
    r, vnfs = mydb.get_table(SELECT=select_, FROM=from_, WHERE={'tb_nfr.nsseq':instance_dict['nsseq']})
    
    if r < 0:
        return -HTTP_Internal_Server_Error, "failed to get VNF Records for NS Instance %s" %str(instance_dict['nsseq'])
    
    for vnf in vnfs:
        af.convert_datetime2str_psycopg2(vnf)        
    instance_dict['vnfs'] = vnfs
    
    for vnf in instance_dict['vnfs']:
        #instance vms
        select_ = ('v.vduseq as vduseq', 'v.name as name', 'v.uuid as uuid', 'v.vim_name as vim_name', 'v.status as status', 'v.weburl as web_url', 'v.vdudseq as vdudseq', 'v.reg_dttm as reg_dttm', 'tb_vdud.name as vdud_name', 'v.mgmtip as mgmtip', 'tb_vdud.monitor_target_seq', 'tb_vdud.vm_access_id as vm_access_id', 'tb_vdud.vm_access_passwd as vm_access_passwd')
        from_ = "tb_vdu as v join tb_vdud on v.vdudseq=tb_vdud.vdudseq"
        where_ = {'v.nfseq':vnf['nfseq']}
        r, vdus = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
        
        if r <= 0:
            return -HTTP_Internal_Server_Error, "failed to get VNF VDU Records for VNF Instance %s of NS Instance %s" % (vnf['nfseq'], instance_dict['nsseq'])
        
        for vm in vdus:
            af.convert_datetime2str_psycopg2(vm)
            #CP
            select_ = ('cpseq', 'cpdseq', 'name', 'uuid', 'vim_name', 'ip', 'vduseq', 'reg_dttm', 'modify_dttm')
            r, cps = mydb.get_table(SELECT=select_, FROM='tb_cp', WHERE={'vduseq':vm['vduseq']})
            if r<=0:
                log.warning("No CP Found for the VDU %s" %str(vm['vduseq']))
            
            for cp in cps:
                af.convert_datetime2str_psycopg2(cp)
            vm['cps']=cps
            
            #VNF Configuration
            r, configs = get_vnfd_vdud_config_only(mydb, vm['vdudseq'], 'config')
            if r <= 0:
                log.error("failed to get VNF VDU Config %d %s" % (r, configs))
            vm['configs']=configs
            
            #VNF Monitor
            r, monitors = get_vnfd_vdud_monitor_only(mydb, vm['vdudseq'], 'monitor')
            if r <=0:
                log.error('failed to get VNF VDU Monitor %d %s' %(r, monitors))
            vm['monitors']=monitors
            
        vnf['vdus'] = vdus
        
        r, report = get_vnf_report(mydb, vnf['nfseq'])
        if r > 0:
            log.debug("[HJC] VNF Report for %s: %s" %(str(vnf['nfseq']), str(report)))
            vnf['report'] = report
            if vnf['name'] == 'GiGA-Storage':
                log.debug("[HJC] GiGA-Storage Usage Report")
                rep_usage = {"name":"usage", "display_name":"Storage Usage(%)","value":"5"}
                for rep in vnf['report']:
                    if rep['name'] == 'storage_capacity':
                        if int(rep['value']) <= 500:
                            rep_usage = {"name":"usage", "display_name":"Storage Usage(%)", "value":"80"}
                        break
                vnf['report'].append(rep_usage)
        else:
            log.debug("[HJC] no VNF Report: %d %s" %(r, report))
        
        r, action = get_vnf_action(mydb, vnf['nfseq'])
        if r > 0:
            log.debug("[HJC] VNF Action for %s: %s" %(str(vnf['nfseq']), str(action)))
            vnf['ui_action'] = action
        else:
            log.debug("[HJC] no VNF Action: %d %s" %(r, action))
            
    select_ = ('vlseq','uuid','status')
    from_ = "tb_vl"
    where_ = {'nsseq':instance_dict['nsseq']}
    
    r, vlrs = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
    if r <=0:
        #log.warning("No Virtual Link Records for NS Instance %s" %instance_dict['nsseq'])
        pass
    
    for vl in vlrs:
        af.convert_datetime2str_psycopg2(vl)
    instance_dict['vls'] = vlrs
    
    af.convert_datetime2str_psycopg2(instance_dict)
    af.convert_str2boolean(instance_dict, ('publicyn','sharedyn') )

    # log.debug('instance_dict = %s' % str(instance_dict))
    
    return 1, instance_dict


def get_nsr_params(mydb, nsr_id, category=None):
    from_ = 'tb_nsr_param'
    
    if category:
        where_ = {'nsseq': nsr_id, 'category': category}
    else:
        where_= {'nsseq': nsr_id}
        
    result,content = mydb.get_table(FROM=from_, WHERE=where_)
    
    if result < 0:
        log.error("get_nsr_params error %d %s" % (result, content))
    return result, content


def delete_nsr(mydb, id):
    #instance table
    #if tenant_id is not None: where_['r.orch_tenant_id']=tenant_id
    where_ = {'nsseq':id}
    del_column = 'nsseq'
    
    r, content = mydb.get_table(FROM='tb_nsr', WHERE=where_)
    if r < 0:
        return -HTTP_Internal_Server_Error, "failed to get the NSR from DB %s" % str(id)
    elif r == 0:
        return -HTTP_Bad_Request, "No NSR found with this criteria %s" % str(id)
    elif r > 1:
        return -HTTP_Bad_Request, "More than one NSR found with this criteria %s" % str(id)
    
    result, content = mydb.delete_row_seq("tb_nsr", del_column, id, None, db_debug)
    
    if result < 0:
        log.error("delete_nsr error %d %s" %(result, content))
    return result, content


# def _insert_deleted_item(mydb, tb_name, item_id, item_name, userseq=None, customerseq=None, item_description=None, item_backup1=None, item_backup2=None, item_backup3=None):
#     try:
#         insert_ = {'tb_name':tb_name, 'item_id':item_id, 'item_name':item_name}
#         if userseq: insert_['userseq'] = userseq
#         if customerseq: insert_['customerseq'] = customerseq
#         if item_description: insert_['item_description'] = item_description
#         if item_backup1: insert_['item_backup1'] = _convert_backupdata_to_str(item_backup1)
#         if item_backup2: insert_['item_backup2'] = _convert_backupdata_to_str(item_backup2)
#         if item_backup3: insert_['item_backup3'] = _convert_backupdata_to_str(item_backup3)
#
#         result, deleted_id = mydb.new_row('tb_deleted', insert_, None, False, db_debug)
#         if result < 0:
#             log.warning('_insert_deleted_item() Error inserting at table tb_deleted: ' + deleted_id)
#             pass
#     except KeyError as e:
#         log.exception("Error while inserting deleted item into DB. KeyError: " + str(e))
#         return -HTTP_Internal_Server_Error, "Error while inserting deleted item into DB. KeyError: " + str(e)
#
#     return result, deleted_id


# def _get_deleted_item(mydb, tb_name):
#     select_ = ('item_name as name', 'item_id as seq', 'del_dttm as modify_dttm', 'item_description as description', 'customerseq', 'userseq', 'item_backup1', 'item_backup2', 'item_backup3' )
#
#     result, data = mydb.get_table(FROM='tb_deleted', SELECT=select_, WHERE={'tb_name':tb_name})
#
#     if result < 0:
#         return -HTTP_Internal_Server_Error, data
#     elif result == 0:
#         return -HTTP_Not_Found, data
#
#     return result, data
# def _convert_backupdata_to_str(backupdata):
#     if type(backupdata) is str:
#         return backupdata
#     else:
#         log.debug("type of the backup data is %s" %str(type(backupdata)))
#
#         try:
#             return json.dumps(backupdata, indent=4)
#         except Exception, e:
#             log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
#
#     log.warning("_convert_backupdata_to_str() failed to convert backup data to string")
#     return "Not supported format"
#
# def clear_deleted_items(mydb):
#     #TODO
#     pass
    

def insert_backup_history(mydb, backup_dict):
    try:
        insert_ = {'serverseq':backup_dict['serverseq'], 'creator':backup_dict['creator'], 'trigger_type':backup_dict.get('trigger_type',"manual")}
        if 'nsr_name' in backup_dict: insert_['nsr_name'] = backup_dict['nsr_name']
        if 'nsseq' in backup_dict: insert_['nsseq'] = backup_dict['nsseq']
        
        if 'vnf_name' in backup_dict: insert_['nfr_name'] = backup_dict['vnf_name']
        if 'nfseq' in backup_dict: insert_['nfseq'] = backup_dict['nfseq']
        
        if 'vdu_name' in backup_dict: insert_['vdu_name'] = backup_dict['vdu_name']
        if 'vduseq' in backup_dict: insert_['vduseq'] = backup_dict['vduseq']
        
        if 'category' in backup_dict: insert_['category'] = backup_dict['category']
        
        if 'backup_server' in backup_dict: insert_['backup_server'] = backup_dict['backup_server']
        if 'backup_location' in backup_dict: insert_['backup_location'] = backup_dict['backup_location']
        if 'backup_local_location' in backup_dict: insert_['backup_local_location'] = backup_dict['backup_local_location']
        if 'description' in backup_dict: insert_['description'] = backup_dict['description']
        
        if 'parentseq' in backup_dict: insert_['parentseq'] = backup_dict['parentseq']
        
        if 'status' in backup_dict: insert_['status'] = backup_dict['status']  
        
        if 'server_name' in backup_dict: insert_['server_name'] = backup_dict['server_name']
        if 'download_url' in backup_dict: insert_['download_url'] = backup_dict['download_url']
        
        if 'backup_data' in backup_dict: insert_['backup_data'] = backup_dict['backup_data']

        result, backup_id = mydb.new_row('tb_backup_history', insert_, None, False, db_debug)
        if result < 0:
            log.warning('insert_backup_history() Error inserting at table tb_backup_history: ' + backup_id)
            pass   
    except KeyError as e:
        log.exception("Error while inserting backup history into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while inserting backup history into DB. KeyError: " + str(e)
    except Exception as e:
        log.exception("Failed to insert backup history : %s" % str(e))
        return -HTTP_Internal_Server_Error, "Failed to insert backup history"
    
    return result, backup_id


def update_backup_history(mydb, backup_dict, condition = None):
    try:
        update_ = {}
        if 'serverseq' in backup_dict: update_['serverseq'] = backup_dict['serverseq']
        if 'creator' in backup_dict: update_['creator'] = backup_dict['creator']
        
        if 'nsr_name' in backup_dict: update_['nsr_name'] = backup_dict['nsr_name']
        if 'nsseq' in backup_dict: update_['nsseq'] = backup_dict['nsseq']
        
        if 'vnf_name' in backup_dict: update_['nfr_name'] = backup_dict['vnf_name']
        if 'nfseq' in backup_dict: update_['nfseq'] = backup_dict['nfseq']
        
        if 'vdu_name' in backup_dict: update_['vdu_name'] = backup_dict['vdu_name']
        if 'vduseq' in backup_dict: update_['vduseq'] = backup_dict['vduseq']
        
        if 'category' in backup_dict: update_['category'] = backup_dict['category']
        
        if 'backup_server' in backup_dict: update_['backup_server'] = backup_dict['backup_server']
        if 'backup_location' in backup_dict: update_['backup_location'] = backup_dict['backup_location']
        if 'backup_local_location' in backup_dict: update_['backup_local_location'] = backup_dict['backup_local_location']
        if 'description' in backup_dict: update_['description'] = backup_dict['description']
        
        if 'parentseq' in backup_dict: update_['parentseq'] = backup_dict['parentseq']
        
        if 'status' in backup_dict: update_['status'] = backup_dict['status']
        
        if 'ood_flag' in backup_dict: update_['ood_flag'] = backup_dict['ood_flag']

        if len(update_) == 0:
            raise Exception ("No Data to Update")

        if condition is None:
            if 'backupseq' not in backup_dict:
                return -HTTP_Not_Found, "No target seq in the request"

            where_ = {'backupseq': backup_dict['backupseq']}
        else:
            where_ = condition

        update_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_backup_history', update_, where_)
        if result < 0:
            log.error('update_backup_history() Error updating at table tb_backup_history: ' + content)

    except KeyError as e:
        log.exception("Error while updating backup history into DB. KeyError: " + str(e))
        result = -HTTP_Internal_Server_Error
        return result, "Error while updating backup history into DB. KeyError: " + str(e)
    
    return result, backup_dict.get('backupseq', 0)


def get_backup_history(mydb, condition):
    try:
        where_ = {}

        if 'ood_flag' in condition: where_['ood_flag'] = condition['ood_flag']

        if 'backupseq' in condition: where_['backupseq'] = condition['backupseq']
        if 'serverseq' in condition: where_['serverseq'] = condition['serverseq']
        if 'nsr_name' in condition: where_['nsr_name'] = condition['nsr_name']
        if 'vnf_name' in condition: where_['nfr_name'] = condition['vnf_name']
        if 'vdu_name' in condition: where_['vdu_name'] = condition['vdu_name']
        if 'vduseq' in condition: where_['vduseq'] = condition['vduseq']
        if 'nsseq' in condition: where_['nsseq'] = condition['nsseq']
        if 'category' in condition: where_['category'] = condition['category']
        if 'parentseq' in condition: where_['parentseq'] = condition['parentseq']

        log.debug("get_backup_history() where_ = %s" %str(where_))
        result, content = mydb.get_table(FROM='tb_backup_history', ORDER='reg_dttm DESC', WHERE=where_ )
        if result < 0:
            log.error("get_backup_history() failed to get backup history for %s" %str(where_))
    except KeyError as e:
        log.exception("Error while getting backup history into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while getting backup history into DB. KeyError: " + str(e)   
        
    return result, content


def get_backup_history_id(mydb, condition):
    if 'ood_all' in condition:
        if 'ood_flag' in condition:
            del condition['ood_flag']
    else:
        condition['ood_flag'] = False
    result, content = get_backup_history(mydb, condition)

    log.debug("[*******HJC**********] %d, %s" %(result, str(content)))

    if result < 0:
        log.error("get_backup_history_id() failed to get backup history for %s" %str(condition))
        return result, content
    elif result == 0:
        log.error("get_backup_history_id() No backup history found for %s" %str(condition))
        return result, content
    
    return result, content[0]


def get_backup_history_lastone(mydb, condition):
    condition['ood_flag'] = False
    result, content = get_backup_history(mydb, condition)

    log.debug("[*******HJC**********] %d, %s" %(result, str(content)))

    if result < 0:
        log.error("get_backup_history_lastone() failed to get backup history for %s" %str(condition))
        return result, content
    elif result == 0:
        log.error("get_backup_history_lastone() No backup history found for %s" %str(condition))
        return result, content
    
    return result, content[0]


# def delete_backup_history(mydb, condition):
#     try:
#         where_ = {'serverseq':condition['serverseq']}
#         if 'nsr_name' in condition: where_['nsr_name'] = condition['nsr_name']
#         if 'vdu_name' in condition: where_['vdu_name'] = condition['vdu_name']
#         if 'vduseq' in condition: where_['vduseq'] = condition['vduseq']
#
#         result, content = mydb.delete_row_by_dict(FROM="tb_backup_history", WHERE=where_)
#         if result < 0:
#             log.warning("delete_backup_history() error: %d %s" %(result, content))
#
#         log.debug("delete_backup_history() result: %d %s" %(result, content))
#     except KeyError as e:
#         log.exception("Error while deleting backup history into DB. KeyError: " + str(e))
#         return -HTTP_Internal_Server_Error, "Error while deleting backup history into DB. KeyError: " + str(e)
#
#     return result, content


# def clear_backup_histor(mydb):
#     try:
#         where_ = {"ood_flag": True}
#         result, content = mydb.delete_row_by_dict(FROM='tb_backup_history', WHERE=where_)
#         if result < 0:
#             log.warning("error: %d %s" %(result, content))
#     except Exception, e:
#         log.exception("Error while clearing backup history %s" %str(e))
#         return -HTTP_Internal_Server_Error, "Error while clearing backup history %s" %str(e)


def insert_action_history(mydb, action_dict):
    try:
        result, history_id = mydb.new_row('tb_action_history', action_dict, None, False, db_debug)
        if result < 0:
            log.warning('insert_action_history() Error inserting at table tb_action_history: ' + history_id)
            pass   
    except KeyError as e:
        log.exception("Error while inserting action history into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while inserting action history into DB. KeyError: " + str(e)
    
    return result, history_id


def insert_license_pool(mydb, license_dict):
    try:
        result, lp_id = mydb.new_row('tb_license_pool', license_dict, None, False, db_debug)
        if result < 0:
            log.warning('insert_license_pool() Error inserting at table tb_license_pool: ' + lp_id)
    except KeyError as e:
        log.exception("Error while inserting license pool data into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while inserting license pool data into DB. KeyError: " + str(e)
    
    return result, lp_id


def update_license_pool(mydb, license_dict):
    try:
        ret_value = None
        
        where_ = {}
        if 'seq' in license_dict:
            where_['seq'] = license_dict['seq']
            ret_value = license_dict['seq']
        if 'value' in license_dict:
            where_['value'] = license_dict['value']
            ret_value = license_dict['value']
            
        if ret_value == None:
            log.error("Failed to update tb_license_poo data. Cannot identify the Target")
            return -HTTP_Bad_Request, "Failed to update tb_license_poo data. Cannot identify the Target"
        
        update_ = {}
        if 'nfcatseq' in license_dict: update_['nfcatseq'] = license_dict['nfcatseq']
        if 'nfseq' in license_dict: update_['nfseq'] = license_dict['nfseq']
        if 'status' in license_dict: update_['status'] = license_dict['status']
        
        update_['modify_dttm']=datetime.datetime.now()
        
        result, content =  mydb.update_rows('tb_license_pool', update_, where_)
        if result < 0:
            log.error('update_license_pool Error: updating table tb_license_pool: %d %s' %(result, content))
        
        return result, ret_value
 
    except KeyError as e:
        log.exception("Error while updating license pool data into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while updating license pool data into DB. KeyError: " + str(e)


def get_license_pool(mydb, condition={}):
    try:
        where_ = {}
        if 'seq' in condition: where_['seq'] = condition['seq']
        if 'nfcatseq' in condition: where_['nfcatseq'] = condition['nfcatseq']
        if 'vendor' in condition: where_['vendor'] = condition['vendor']
        if 'type' in condition: where_['type'] = condition['type']
        if 'value' in condition: where_['value'] = condition['value']
        if 'status' in condition: where_['status'] = condition['status']
        if 'nfseq' in condition: where_['nfseq'] = condition['nfseq']
        if 'name' in condition: where_['name'] = condition['name']
        
        log.debug("get_license_pool() where_ = %s" %str(where_))
        result, content = mydb.get_table(FROM='tb_license_pool', ORDER='reg_dttm DESC', WHERE=where_ )
        if result < 0:
            log.error("get_license_pool() failed to get license pool data for %s" %str(where_))
    except KeyError as e:
        log.exception("Error while getting license pool data from DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while getting license pool data from DB. KeyError: " + str(e)   
        
    return result, content


def delete_license_pool(mydb, license):
    del_column = "seq"
        
    result, content = mydb.delete_row_seq("tb_license_pool", del_column, license, None, db_debug)
    if result < 0:
        log.error("delete_license_pool error %d %s" % (result, content))
    return result, content


def insert_vnfd_report(mydb, vnf_id, vnf_report):
    if vnf_report is None:
        return -HTTP_Bad_Request, "No content in the report item"
    
    try:
        for report in vnf_report:
            report_item={'nfcatseq':vnf_id, 'name': report['name'], 'display_name': report.get('display_name', report['name']), 'data_provider': report['data_provider']}
            result, content = mydb.new_row('tb_nfcatalog_report', report_item, None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("failed to db insert VNF Report Item: %d %s" %(result, content))
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, str(e)
    
    return 200, "OK"


def get_vnfd_report(mydb, vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfcatalog_report', WHERE={'nfcatseq': vnf_id})
        if result <= 0:
            log.warning("failed to get report items for VNF: %s" %str(vnf_id))
            return -HTTP_Not_Found, []
        
        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    return -HTTP_Internal_Server_Error, "Failed to get VNFD report items"


def insert_vnfd_action(mydb, vnf_id, vnf_action):
    if vnf_action is None:
        return -HTTP_Bad_Request, "No content in the action item"
    
    try:
        for action in vnf_action:
            action_item={'nfcatseq':vnf_id, 'name': action['name'], 'display_name': action.get('display_name', action['name']), 'description': action.get('description', action['name'])}
            if 'api_resource' in action: action_item['api_resource'] = action['api_resource']
            if 'api_body_format' in action: action_item['api_body_format'] = action['api_body_format']
            if 'api_body_param' in action:
                action_item['api_body_param'] = ";".join(action['api_body_param'])
            
            result, content = mydb.new_row('tb_nfcatalog_action', action_item, None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("failed to db insert VNF Action Item: %d %s" %(result, content))
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, str(e)
    
    return 200, "OK"


def get_vnfd_action(mydb, vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfcatalog_action', WHERE={'nfcatseq': vnf_id})
        if result <= 0:
            log.warning("failed to get action items for VNF: %s" %str(vnf_id))
            return -HTTP_Not_Found, []
        
        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    return -HTTP_Internal_Server_Error, "Failed to get VNFD action items"


def insert_vnfd_metadata(mydb, vnf_id, vnf_metadata):
    if vnf_metadata is None:
        return -HTTP_Bad_Request, "No Metadata"
    
    metadata_list = []
    
    try:
        for name, value in vnf_metadata.iteritems():
            metadata_item = {"nfcatseq": vnf_id, "name": name, "value": value}
            result, content = mydb.new_row('tb_nfcatalog_metadata', metadata_item, None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("failed to db insert VNFD Metadata: %s = %s" %(name, str(value)))
            metadata_list.append(metadata_item)        
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, str(e)
    
    return 200, metadata_list


def get_vnfd_metadata(mydb, vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfcatalog_metadata', WHERE={'nfcatseq': vnf_id})
        if result <= 0:
            log.warning("failed to get metadata for VNF: %s" %str(vnf_id))
            return -HTTP_Not_Found, []
        
        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    return -HTTP_Internal_Server_Error, "Failed to get VNFD metadata"


def insert_nsd_metadata(mydb, ns_id, ns_metadata):
    if ns_metadata is None:
        return -HTTP_Bad_Request, "No Metadata"
    
    metadata_list = []
    
    try:
        for name, value in ns_metadata.iteritems():
            metadata_item = {"nscatseq": ns_id, "name": name, "value": value}
            result, content = mydb.new_row('tb_nscatalog_metadata', metadata_item, None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("failed to db insert NSD Metadata: %s = %s" %(name, str(value)))
            metadata_list.append(metadata_item)        
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, str(e)
    
    return "200", metadata_list


def get_nsd_metadata(mydb, ns_id):
    try:
        result, content = mydb.get_table(FROM='tb_nscatalog_metadata', WHERE={'nscatseq': ns_id})
        if result <= 0:
            log.warning("failed to get metadata for NS: %s" %str(ns_id))
            return -HTTP_Not_Found, []
        
        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))
    
    return -HTTP_Internal_Server_Error, "Failed to get NSD metadata"


def insert_rlt_data(mydb, rlt_dict):

    # rlt_data 암호화 처리.
    rlt_data = json.dumps(rlt_dict)
    cipher = AESCipher.get_instance()
    rlt_data_enc = cipher.encrypt(rlt_data)
    rlt = {"data": rlt_data_enc}
    rlt_col = json.dumps(rlt)

    rlt_cols = {"rlt" : rlt_col}
    rlt_cols['modify_dttm'] = datetime.datetime.now()
    rlt_cols["nscatseq"] = rlt_dict["nscatseq"]
    rlt_cols["nsseq"] = rlt_dict["nsseq"]

    return mydb.new_row('tb_rlt', rlt_cols, None, add_uuid=False, log=db_debug)


def update_rlt_data(mydb, rlt_data, rlt_seq=None, nsseq=None):

    # rlt_data 암호화 처리.
    cipher = AESCipher.get_instance()
    rlt_data_enc = cipher.encrypt(rlt_data)
    rlt = {"data": rlt_data_enc}
    rlt_col = json.dumps(rlt)

    rlt_cols = {"rlt" : rlt_col}
    rlt_cols['modify_dttm'] = datetime.datetime.now()
    if rlt_seq is not None:
        where = {"rltseq" : rlt_seq}
    elif nsseq is not None:
        where = {"nsseq" : nsseq}
    else:
        return -HTTP_Internal_Server_Error, "Invalid Parameters : None Search Key"

    return mydb.update_rows('tb_rlt', rlt_cols, where, log=db_debug)


def get_rlt_data(mydb, nsseq):
    """
    백업, 복구, vnf업데이트, 준공, 서버정보변경 Agent Call 시 
    :param mydb:
    :param nsseq:
    :return:
    """
    try:
        result, content = mydb.get_table(FROM='tb_rlt', WHERE={'nsseq': nsseq})
        if result <= 0:
            log.warning("failed to get RLT data, nsseq = %s" % str(nsseq))
            return -HTTP_Not_Found, []

        if type(content[0]["rlt"]) is str:
            rlt_col = json.loads(content[0]["rlt"])
        else:
            rlt_col = content[0]["rlt"]

        rlt_data_enc = rlt_col["data"]

        # 복호화처리
        cipher = AESCipher.get_instance()
        rlt_data_dec = cipher.decrypt(rlt_data_enc)
        content[0]["rlt"] = json.loads(rlt_data_dec)

        return result, content[0]

    except Exception, e:
        log.exception("Exception: %s" %str(e))
    return -HTTP_Internal_Server_Error, "Failed to get RLT data"


def get_vnfd_parmeters(mydb, vnf_db):

    param_list = []

    #3.1 get VNFD Parameter info
    #3.1.1 get template parameters
    if vnf_db.get('resourcetemplateseq') is not None:
        vnf_template_param_r, template_params = get_vnfd_resource_template_item(mydb, vnf_db['resourcetemplateseq'], 'parameter')

        if vnf_template_param_r < 0:
            log.warning("[Onboarding][NS]      failed to get Resource Template Parameters")
        elif vnf_template_param_r == 0:
            log.debug("[Onboarding][NS]      No Template Parameters")
        else:
            for param in template_params:
                param['category'] = 'vnf_template'
                param['ownername'] = vnf_db['name']
                param['ownerseq'] = vnf_db['nfcatseq']
                param['name'] = param['name'].replace(vnf_db['vnfd_name'], vnf_db['name'])
                param_list.append(param)

    #3.1.2-1 get vnf parameters for account
    vnfd_param_r, vnfd_param_contents = get_vnfd_param_only(mydb, vnf_db['nfcatseq'])
    if vnfd_param_r < 0:
        log.warning("[Onboarding][NS]      failed to get VNFD Parameters")
        pass
    elif vnfd_param_r == 0:
        log.debug("[Onboarding][NS]      No VNF Parameters")
        pass

    for vnfd_param in vnfd_param_contents:
        vnfd_param['category'] = 'vnf_config'
        vnfd_param['ownername'] = vnf_db['name']
        vnfd_param['ownerseq'] = vnf_db['nfcatseq']
        vnfd_param['name'] = vnfd_param['name'].replace(vnf_db['vnfd_name'], vnf_db['name'])
        log.debug("[Onboarding][NS] VNFD Param: name = %s" %vnfd_param['name'])
        param_list.append(vnfd_param)

    #3.1.2 get vnf config parameters
    vdud_r, vdud_contents = get_vnfd_vdud_only(mydb, vnf_db['nfcatseq'])
    if vdud_r < 0:
        log.warning("[Onboarding][NS]      failed to get VNF VDUD")
        pass
    elif vdud_r == 0:
        log.debug("[Onboarding][NS]      No VNF VDUD")
        pass

    for vdud in vdud_contents:
        vdud_config_param_r, vdud_config_params = get_vnfd_vdud_config_only(mydb, vdud['vdudseq'], 'parameter')
        if vdud_config_param_r < 0:
            log.warning("[Onboarding][NS]      failed to get VNF VDUD Config Parameters")
        elif vdud_config_param_r == 0:
            log.debug("[Onboarding][NS]      No VNF VDUD Config Parameters")
        else:
            for param in vdud_config_params:
                if param['name'].find(vnf_db['vnfd_name']) >= 0:
                    param['category'] = 'vnf_config'
                    param['ownername'] = vnf_db['name']
                    param['ownerseq'] = vnf_db['nfcatseq']
                    param['name'] = param['name'].replace(vnf_db['vnfd_name'], vnf_db['name'])
                    param_list.append(param)

    # 3.1.3 TODO vdud_monitor_param

    log.debug("_new_nsd_v1_thread() Parameter list: %s" %str(param_list))

    return 200, param_list


def delete_nfr(mydb, condition):

    try:
        if "nfseq" in condition:
            result, content = mydb.delete_row_seq("tb_nfr", "nfseq", condition['nfseq'], None, db_debug)
        else:
            result, content = mydb.delete_row_by_dict(FROM="tb_nfr", WHERE={"name": condition["name"], "nsseq": condition["nsseq"]})
        if result < 0:
            log.error("delete_nfr error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : delete nfr - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete nfr - %s" %str(e)


def delete_nsr_param(mydb, condition):

    try:
        where_ = {'nsseq': condition['nsseq']}
        if "ownername" in condition:
            where_["ownername"] = condition["ownername"]

        deleted, content = mydb.delete_row_by_dict(FROM="tb_nsr_param", WHERE=where_)
        if deleted < 0:
            log.error("delete_nsr_param error %d %s" % (deleted, content))
        return deleted, content
    except Exception, e:
        log.exception("Error : delete nsr param - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete nsr param - %s" %str(e)


def insert_nsr_for_vnfs(mydb, rlt_dict, update_mode=False):
    """
    NS Update 시 vnf insert용
    :param mydb:
    :param rlt_dict:
    :param update_mode:
    :return:
    """

    for vnf in rlt_dict['vnfs']:
        # if update_mode and not vnf.get("isAdded", False):
        #     continue
        vm_configs_json = json.dumps("{}", indent=4)
        for vm in vnf['vdus']:
            if 'configs' in vm:
                vm_configs = vm['configs']
                vm_configs_json = json.dumps(vm_configs, indent=4)
                break

        INSERT_={'nsseq': rlt_dict["nsseq"],  'nfcatseq': vnf['nfcatseq'], 'status':vnf['status'], 'name':vnf['name'], 'configsettings':vm_configs_json, 'description':vnf['description'], 'weburl':vnf.get('weburl', "None"), 'license':vnf.get('license','None'), 'webaccount':vnf.get('webaccount', "-")}
        if 'orgnamescode' in vnf:
            INSERT_['orgnamescode'] = vnf['orgnamescode']
        if 'deploy_info' in vnf:
            INSERT_['deploy_info'] = vnf['deploy_info']
        if 'service_number' in vnf:
            INSERT_['service_number'] = vnf['service_number']
        if 'service_period' in vnf:
            INSERT_['service_period'] = vnf['service_period']

        # vnf image 정보저장 : vnf_image_version, vnf_sw_version
        vnf_image_name = None
        for param in rlt_dict["parameters"]:
            if param["name"] == "RPARM_imageId_" + vnf["name"]:
                vnf_image_name = param["value"]
                break
        if vnf_image_name:
            result, imgs = get_vnfd_vdu_image(mydb, {"name" : vnf_image_name})
            if result < 0:
                log.error("Failed to get tb_vdud_image record : name = %s" % vnf_image_name)
                return result, imgs
            elif result == 0:
                log.error("Not Found VNF Image(%s). " % vnf_image_name)
                return -500, "Not Found VNF Image(%s). First, regist VNF Image!!!" % vnf_image_name
            img = imgs[0]
            INSERT_["vnf_image_version"] = img["vnf_image_version"]
            INSERT_["vnf_sw_version"] = img["vnf_sw_version"]
            INSERT_["vdudimageseq"] = img["vdudimageseq"]

        r,instance_vnf_id =  mydb.new_row('tb_nfr', INSERT_, None, False, db_debug)
        if r<0:
            log.error('insert_nsr_as_a_whole() Error inserting at table tb_nfr: ' + instance_vnf_id)
            return r, instance_vnf_id
        vnf['nfseq'] = instance_vnf_id
        #instance_vms
        for vm in vnf['vdus']:
            INSERT_={'name':vm['name'], 'uuid': vm.get('uuid'), 'vim_name':vm.get('vim_name'), 'nfseq': instance_vnf_id,  'vdudseq': vm['vdudseq'], 'weburl':vm.get('weburl', "None") }
            INSERT_['mgmtip'] = vm.get('mgmtip')
            INSERT_['vm_access_id'] = vm.get("vm_access_id")
            INSERT_['vm_access_passwd'] = vm.get("vm_access_passwd")
            if 'orgnamescode' in vnf:
                INSERT_['orgnamescode'] = vm['orgnamescode']
            INSERT_['modify_dttm'] = datetime.datetime.now()
            r,instance_vm_id =  mydb.new_row('tb_vdu', INSERT_, None, False, db_debug)
            if r<0:
                log.error('insert_nsr_as_a_whole() Error inserting at table tb_vdu: ' + instance_vm_id)
                return r, instance_vm_id
            vm['vduseq']=instance_vm_id
            #cp
            if 'cps' in vm:
                for cp in vm['cps']:
                    INSERT_={'name':cp['name'], 'uuid':cp['uuid'], 'vim_name':cp['vim_name'], 'vduseq': instance_vm_id, 'cpdseq': cp['cpdseq'], 'ip':cp.get('ip')}
                    log.debug("[HJC] DB Insert - CP: %s" %str(INSERT_))

                    INSERT_['modify_dttm'] = datetime.datetime.now()
                    r, instance_cp_id = mydb.new_row('tb_cp', INSERT_, None, False, db_debug)
                    if r<0:
                        log.warning('insert_nsr_as_a_whole() Error failed to insert CP Record into tb_cp %d %s' %(r, instance_cp_id))
                    cp['cpseq']=instance_cp_id
        if 'ui_action' in vnf:
            for action in vnf['ui_action']:
                INSERT_ = {'nfseq': vnf['nfseq'], 'name': action['name'], 'display_name': action['display_name'], 'api_resource': action['api_resource'], 'api_body_format': action['api_body_format'], 'api_body_param': action['api_body_param']}
                log.debug("[HJC] UI Action DB Insert: %s" %str(INSERT_))
                r, vnf_action_id = mydb.new_row('tb_nfr_action', INSERT_, None, False, db_debug)
                if r < 0:
                    log.warning("failed to insert nsr vnf action items: %d %s" %(r, vnf_action_id))

        if 'report' in vnf:
            for report in vnf['report']:
                INSERT_ = {'nfseq': vnf['nfseq'], 'name': report['name'], 'display_name': report['display_name'], 'data_provider': report['data_provider'], 'value': report.get('value')}
                log.debug("[HJC] UI Report DB Insert: %s" %str(INSERT_))
                r, vnf_report_id = mydb.new_row('tb_nfr_report', INSERT_, None, False, db_debug)
                if r < 0:
                    log.warning("failed to insert nsr vnf report items: %d %s" %(r, vnf_report_id))
    return 200, "OK"


def insert_user_mp_customer(mydb, customerseq):

    result, user_list = get_user_list(mydb, [])

    for user in user_list:
        data = {"userid":user["userid"], "customerseq":customerseq}
        # 이미 데이타가 존재하는지 확인
        result, mp_data = mydb.get_table(FROM='tb_user_mp_customer', WHERE=data)
        if result > 0:
            log.warning("The mapping data already exists : userid=%s, customerseq=%s" % (user["userid"], customerseq))
            continue

        data["reg_userid"] = user["userid"]
        result, content = mydb.new_row("tb_user_mp_customer", data, None, add_uuid=False, log=db_debug, last_val=False)
        if result < 0:
            log.error("insert tb_user_mp_customer error %d %s" % (result, content))
    return result, "OK"


def update_ood_flag(mydb, nsseq):

    try:
        # condition 1: nsseq and category = ns
        # condition 2: [nsseq and ] [category = vnf and] parentseq = nsbackupseq
        where_ns = {"nsseq": nsseq, "category":"ns"}
        result, ns_list = mydb.get_table(FROM='tb_backup_history', WHERE=where_ns)
        update_ = {"ood_flag" : 'true'}
        for ns_item in ns_list:
            backupseq = ns_item["backupseq"]
            where_ = {"parentseq" : backupseq, "category":"vnf"}
            result, content = mydb.update_rows("tb_backup_history", update_, where_, log=db_debug)
            if result < 0:
                log.error("Error : update ood_flag of vnf %d %s" % (result, content))

        result, content = mydb.update_rows("tb_backup_history", update_, where_ns, log=db_debug)
        if result < 0:
            log.error("Error : update ood_flag of ns %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : update ood flag - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : update ood flag - %s" %str(e)


def insert_server_account(mydb, data):
    INSERT_ = {}
    if 'onebox_id' in data:
        INSERT_['onebox_id'] = data['onebox_id']
    if 'serverseq' in data:
        INSERT_['serverseq'] = data['serverseq']
    if 'account_id' in data:
        INSERT_['account_id'] = data['account_id']
    if 'account_pw' in data:
        INSERT_['account_pw'] = data['account_pw']
    if 'customerseq' in data:
        INSERT_['customerseq'] = data['customerseq']
    if 'metadata' in data:
        INSERT_['metadata'] = data['metadata']
    if 'account_type' in data:
        INSERT_['account_type'] = data['account_type']

    try:
        result, content = mydb.new_row("tb_server_account", INSERT_, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("tb_server_account error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert one-box account - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert one-box account - %s" %str(e)


def insert_server_account_use(mydb, data):
    try:
        result, content = mydb.new_row("tb_server_account_use", data, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("tb_server_account_use error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert tb_server_account_use - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert tb_server_account_use - %s" %str(e)


def get_server_account(mydb, serverseq):
    try:
        result, content = mydb.get_table(FROM='tb_server_account', WHERE={'serverseq': serverseq})
        if result < 0:
            log.error("Failed to get server account data, serverseq = %s" % str(serverseq))
            return result, content

        if content is None or len(content) <= 0:
            log.warning("Failed to get server account data [No Data] , onebox_id = %s" % str(serverseq))
            return result, content

        return result, content[0]
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return -HTTP_Internal_Server_Error, "Failed to get server account data"


def get_server_account_by_id(mydb, account_id):
    try:
        result, content = mydb.get_table(FROM='tb_server_account', WHERE={'account_id': account_id})
        if result < 0:
            log.error("Failed to get server account data, account_id = %s" % str(account_id))
            return result, content

        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return -HTTP_Internal_Server_Error, "Failed to get server account data"


def get_server_account_use(mydb, where_):
    try:
        result, content = mydb.get_table(FROM='tb_server_account_use', WHERE=where_)
        if result <= 0:
            log.error("Failed to get server_account_use data, where = %s" % str(where_))
            return result, content

        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return -HTTP_Internal_Server_Error, "Failed to get server_account_use data"


def delete_server_account(mydb, accountseq):
    try:
        result, content = mydb.delete_row_seq("tb_server_account", "accountseq", accountseq, None, db_debug)
        if result < 0:
            log.error("delete_server_account error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : delete server account - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete server account - %s" %str(e)


def delete_server_account_use(mydb, accountuseseq):
    try:
        result, content = mydb.delete_row_seq("tb_server_account_use", "accountuseseq", accountuseseq, None, db_debug)
        if result < 0:
            log.error("delete_server_account_use error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : delete server account use - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete server account use - %s" %str(e)


def get_vnfd_version_list(mydb, nsseq):

    try:
        # get vim_tenant_id
        from_ = 'tb_nfr a join tb_nfcatalog b on a.nfcatseq = b.nfcatseq'
        select_ = ('b.name as name', 'b.version as version')
        where_ = {"a.nsseq": nsseq}
        # get vnfd version
        result, content = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
        if result <= 0:
            log.error("Failed to get a list of (vnfd name, version)")
            return result, content

        return result, content
    except Exception, e:
        log.exception("Exception: %s" % str(e))

    return -HTTP_Internal_Server_Error, "Failed to get a list of (vnfd name, version)"


def get_server_wan_list(mydb, serverseq, kind="R"):
    """
    server wan 목록 조회
    :param mydb:
    :param serverseq:
    :param kind: "R", "E", "ALL"
    :return:
    """

    where_ = {'serverseq':serverseq}
    like_ = {}
    if kind != "ALL":
        like_["name"] = kind + "%"
    result, content = mydb.get_table(FROM='tb_server_wan', WHERE=where_, LIKE=like_)

    if result < 0:
        log.error("get_server_wan_list error %d %s" % (result, content))
        return result, content

    return result, content


def get_server_wan_seq(mydb, condition):
    if "wan_seq" in condition:
        where_ = {'wan_seq':condition["wan_seq"]}
    else:
        where_ = {'serverseq':condition['serverseq'], 'nic':condition['nic']}

    result, content = mydb.get_table(FROM='tb_server_wan', WHERE=where_)

    if result < 0:
        log.error("get_server_wan_list error %d %s" % (result, content))
    return result, content


def insert_server_wan(mydb, wan_dict):
    INSERT_ = {}
    if "serverseq" in wan_dict: INSERT_["serverseq"] = wan_dict["serverseq"]
    if "onebox_id" in wan_dict: INSERT_["onebox_id"] = wan_dict["onebox_id"]

    if "public_ip" in wan_dict: INSERT_["public_ip"] = wan_dict["public_ip"]
    if "public_cidr_prefix" in wan_dict: INSERT_["public_cidr_prefix"] = wan_dict["public_cidr_prefix"]
    if "public_gw_ip" in wan_dict: INSERT_["public_gw_ip"] = wan_dict["public_gw_ip"]

    if "ipalloc_mode_public" in wan_dict: INSERT_["ipalloc_mode_public"] = wan_dict["ipalloc_mode_public"]
    # if "public_ip_dhcp" in wan_dict: INSERT_["public_ip_dhcp"] = wan_dict["public_ip_dhcp"]
    if "mac" in wan_dict: INSERT_["mac"] = wan_dict["mac"]
    if "mode" in wan_dict: INSERT_["mode"] = wan_dict["mode"]
    if "nic" in wan_dict: INSERT_["nic"] = wan_dict["nic"]
    if "name" in wan_dict: INSERT_["name"] = wan_dict["name"]
    if "status" in wan_dict: INSERT_["status"] = wan_dict["status"]
    if "physnet_name" in wan_dict: INSERT_["physnet_name"] = wan_dict["physnet_name"]

    try:
        result, content = mydb.new_row("tb_server_wan", INSERT_, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("tb_server_wan error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert tb_server_wan - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert tb_server_wan - %s" %str(e)


def update_server_wan(mydb, where_dict, update_dict):
    """
        tb_server_wan update
    :param mydb:
    :param where_dict: 조건
    :param update_dict: 변경할 값
    :return:
    """

    UPDATE_ = {}

    if "public_ip" in update_dict: UPDATE_["public_ip"] = update_dict["public_ip"]
    if "public_cidr_prefix" in update_dict: UPDATE_["public_cidr_prefix"] = update_dict["public_cidr_prefix"]
    if "public_gw_ip" in update_dict: UPDATE_["public_gw_ip"] = update_dict["public_gw_ip"]
    if "ipalloc_mode_public" in update_dict: UPDATE_["ipalloc_mode_public"] = update_dict["ipalloc_mode_public"]
    if "mac" in update_dict: UPDATE_["mac"] = update_dict["mac"]
    if "nic" in update_dict: UPDATE_["nic"] = update_dict["nic"]
    if "mode" in update_dict: UPDATE_["mode"] = update_dict["mode"]
    if "status" in update_dict: UPDATE_["status"] = update_dict["status"]
    if "physnet_name" in update_dict: UPDATE_["physnet_name"] = update_dict["physnet_name"]
    if "name" in update_dict: UPDATE_["name"] = update_dict["name"]

    WHERE_ = {}
    if "wan_seq" in where_dict:
        WHERE_["wan_seq"] = where_dict["wan_seq"]
    else:
        if "serverseq" in where_dict:
            WHERE_["serverseq"] = where_dict["serverseq"]
        # if "nic" in where_dict:
        #     WHERE_["nic"] = where_dict["nic"]
        if "name" in where_dict:
            WHERE_["name"] = where_dict["name"]
        elif "physnet_name" in where_dict:
            WHERE_["physnet_name"] = where_dict["physnet_name"]

    result, content = mydb.update_rows('tb_server_wan', UPDATE_, WHERE_)
    if result < 0:
        log.error('update_server_wan Error ' + content + ' updating table tb_server_wan: %s' % where_dict)

    return result, content


def delete_server_wan(mydb, cond_dict, kind="R"):
    try:
        result = 0
        content = ""

        if "wan_seq" in cond_dict:
            result, content = mydb.delete_row_seq("tb_server_wan", "wan_seq", cond_dict['wan_seq'], None, db_debug)
        elif "serverseq" in cond_dict:
            where_ = {'serverseq': cond_dict['serverseq']}
            like_ = {}
            if kind != "ALL":
                like_["name"] = kind + "%"
            result, content = mydb.delete_row_by_dict(FROM="tb_server_wan", WHERE=where_, LIKE=like_)

        if result < 0:
            log.error("delete_server_wan error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : delete tb_server_wan record - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete tb_server_wan record - %s" %str(e)


def get_vdud_by_vnfd_id(mydb, vnfd_id):
    """
        nfcatseq 에 해당하는 vdud를 조회한다. 단, 1:N 관계지만 1:1로 가정하고 처리하므로 첫번째 row만 리턴한다.
        일단 vdudseq, image_metadata 만 필요하므로 두 데이타만 조회한다. 필요하면 더 추가하는 걸로...
    :param mydb:
    :param vnfd_id: tb_nfcatalog.nfcatseq
    :return:
    """

    select_ = ('tb_vdud.vdudseq as vdudseq', 'tb_vdud.image_metadata as image_metadata')
    from_ = 'tb_nfcatalog join tb_vdud on tb_nfcatalog.nfcatseq=tb_vdud.nfcatseq'
    where_ = {'tb_nfcatalog.nfcatseq': vnfd_id}

    r,content = mydb.get_table(FROM=from_, SELECT=select_, WHERE=where_)
    if r < 0:
        log.error("get_vdud_by_vnfd_id error %d %s" % (r, str(content)))
        return r, content
    elif r==0:
        log.warning("get_vdud_by_vnfd_id  '%s' No VDUD" % vnfd_id)
        return -HTTP_Not_Found, "vdud (nfcatseq=%s) not found" % vnfd_id

    return r, content[0]


def get_vdud_image_list(mydb, vdudseq):
    """
        tb_vdud_image record 조회.
    :param mydb:
    :param vdudseq:
    :return:
    """
    WHERE_dict={'vdudseq': vdudseq}

    result, content = mydb.get_table(FROM='tb_vdud_image', WHERE=WHERE_dict )
    if result < 0:
        log.error("get_vdud_image_list error %d %s" % (result, content))
        return -result, content

    return result, content


def get_vdud_image_to_nfcatseq(mydb, vnf_image_version):
    select_ = ('b.nfcatseq as nfcatseq',)
    from_ = " tb_vdud_image a left outer join tb_vdud b on a.vdudseq = b.vdudseq"
    from_ += " where a.location like '%" + vnf_image_version + "%'"

    result, content = mydb.get_table(FROM=from_, SELECT=select_)
    if result < 0:
        log.error('get_vdud_image_to_nfcatseq error %d %s' % (result, content))
        return -result, content

    return result, content[0]


def get_server_vnfimage(mydb, cond_dict):
    """
        배포된 이미지 목록을 조회.
    :param mydb:
    :param cond_dict:
    :return:
    """

    where_ ={}

    if "vnfimageseq" in cond_dict:
        where_["a.vnfimageseq"] = cond_dict["vnfimageseq"]
    else:
        if "serverseq" in cond_dict:
            where_["a.serverseq"] = cond_dict["serverseq"]

            if "location" in cond_dict:
                where_["a.location"] = cond_dict["location"]

            # if "name" in cond_dict:
            #     where_["a.name"] = cond_dict["name"]

    from_ = 'tb_server_vnfimage a join tb_nfcatalog b on a.nfcatseq = b.nfcatseq'
    select_ = ('a.vnfimageseq', 'a.serverseq', 'a.name', 'a.location', 'a.description', 'a.filesize', 'a.status'
               , 'a.checksum', 'a.metadata', 'a.reg_dttm', 'a.modify_dttm', 'a.nfcatseq', 'a.vdudimageseq', 'b.name as vnfd_name')

    # get vnfd version
    result, content = mydb.get_table(SELECT=select_, FROM=from_, WHERE=where_)
    if result < 0:
        log.error("get_server_vnfimage error %d %s" % (result, content))
    return result, content


def get_deployed_and_deployable_list(mydb, id):
    """
        해당 Onebox에 배포된 이미지와 배포 가능한 이미지 목록을 모두 조회
    :param mydb:
    :param id:
    :return:
    """

    select_ = ('n.name as vnfd_name', 'n.version', 'r.name', 'r.location', 'r.filesize', 'd.reg_dttm', 'd.status'
               , 'r.metadata', 'r.vdudseq', 'r.checksum', 'r.vdudimageseq', 'd.vnfimageseq', 'd.serverseq', 'n.nfcatseq', 'r.description')
    from_ = " tb_vdud_image r left outer join (select * from tb_server_vnfimage where serverseq='" + id + "') d on r.location=d.location, tb_vdud v, tb_nfcatalog n"
    from_ += " where r.vdudseq = v.vdudseq and v.nfcatseq = n.nfcatseq "
    result, content = mydb.get_table(FROM=from_, SELECT=select_)
    if result < 0:
        log.error("get_deployed_and_deployable_list error %d %s" % (result, content))
        return -result, content
    return result, content


def insert_server_vnfimage(mydb, data_dict):
    INSERT_ = {}
    if 'name' in data_dict:
        INSERT_['name'] = data_dict['name']
    if 'location' in data_dict:
        INSERT_['location'] = data_dict['location']
    if 'description' in data_dict:
        INSERT_['description'] = data_dict['description']
    if 'filesize' in data_dict:
        INSERT_['filesize'] = data_dict['filesize']
    if 'checksum' in data_dict:
        INSERT_['checksum'] = data_dict['checksum']
    if 'metadata' in data_dict:
        INSERT_['metadata'] = data_dict['metadata']
    if 'status' in data_dict:
        INSERT_['status'] = data_dict['status']
    if 'serverseq' in data_dict:
        INSERT_['serverseq'] = data_dict['serverseq']
    if 'nfcatseq' in data_dict:
        INSERT_['nfcatseq'] = data_dict['nfcatseq']
    if 'vdudimageseq' in data_dict:
        INSERT_['vdudimageseq'] = data_dict['vdudimageseq']

    try:
        result, content = mydb.new_row("tb_server_vnfimage", INSERT_, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("Failed to insert tb_server_vnfimage record : %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert server_vnfimage - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert server_vnfimage - %s" %str(e)


def update_server_vnfimage(mydb, data_dict, filesize=0):
    """
    tb_server_vnfimage status [,filesize] update
    :param mydb:
    :param data_dict:
    :return:
    """
    UPDATE_ = {}

    if "status" in data_dict:
        UPDATE_["status"] = data_dict["status"]

    if filesize > 0:
        UPDATE_["filesize"] = filesize

    UPDATE_['modify_dttm'] = datetime.datetime.now()

    WHERE_ = {}
    if "vnfimageseq" in data_dict:
        WHERE_["vnfimageseq"] = data_dict["vnfimageseq"]
    else:
        if "serverseq" in data_dict:
            WHERE_["serverseq"] = data_dict["serverseq"]

            if "location" in data_dict:
                WHERE_["location"] = data_dict["location"]
            elif "vdudimageseq" in data_dict:
                WHERE_["vdudimageseq"] = data_dict["vdudimageseq"]
            else:
                raise Exception("Failed to update tb_server_vnfimage record : Need location or vdudimageseq")
        else:
            raise Exception("Failed to update tb_server_vnfimage record : Need serverseq")

    result, content = mydb.update_rows('tb_server_vnfimage', UPDATE_, WHERE_)
    if result < 0:
        log.error('update_server_vnfimage Error ' + content + ' updating tb_server_vnfimage: %s' % data_dict)

    return result, content


def delete_server_vnfimage(mydb, data_dict):

    try:
        if "vnfimageseq" in data_dict:
            result, content = mydb.delete_row_seq("tb_server_vnfimage", "vnfimageseq", data_dict['vnfimageseq'], None, db_debug)
            if result < 0:
                raise Exception("Failed to delete tb_server_vnfimage record : vnfimageseq = %s" % data_dict['vnfimageseq'])
            return result, content
        else:
            if "name" in data_dict and "serverseq" in data_dict:
                result, content = mydb.delete_row_by_dict(FROM="tb_server_vnfimage", WHERE={"name": data_dict["name"], "serverseq": data_dict["serverseq"]})
                if result < 0:
                    raise Exception("Failed to delete tb_server_vnfimage record : name = %s, serverseq = %s" % (data_dict['name'], data_dict["serverseq"]))
                return result, content
            else:
                log.error("Conditions of where is wrong. Need name and serverseq")
                raise Exception("Conditions of where is wrong. Need name and serverseq")
    except Exception, e:
        log.exception("Error : delete tb_server_vnfimage - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete tb_server_vnfimage - %s" %str(e)


def get_memo_info(mydb, cond_dict):

    where_ = {}
    if "memoseq" in cond_dict:
        where_["memoseq"] = cond_dict["memoseq"]
    else:
        if "serverseq" in cond_dict:
            where_["serverseq"] = cond_dict["serverseq"]

    result, content = mydb.get_table(FROM='tb_memo', WHERE=where_)
    if result < 0:
        log.error("get_memo_info error %d %s" % (result, content))
    return result, content


def insert_memo(mydb, data_dict):
    INSERT_ = {}
    if 'serverseq' in data_dict:
        INSERT_['serverseq'] = data_dict['serverseq']
    if 'contents' in data_dict:
        INSERT_['contents'] = data_dict['contents']

    INSERT_['create_date'] = datetime.datetime.now()

    try:
        result, content = mydb.new_row("tb_memo", INSERT_, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("Failed to insert insert_memo record : %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert_memo - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert_memo - %s" %str(e)


def update_memo(mydb, data_dict):
    UPDATE_ = {}

    if "contents" in data_dict:
        UPDATE_["contents"] = data_dict["contents"]

    UPDATE_['update_date'] = datetime.datetime.now()

    WHERE_ = {}
    if "memoseq" in data_dict:
        WHERE_["memoseq"] = data_dict["memoseq"]
    else:
        if "serverseq" in data_dict:
            WHERE_["serverseq"] = data_dict["serverseq"]

    result, content = mydb.update_rows('tb_memo', UPDATE_, WHERE_)
    if result < 0:
        log.error('update_memo Error ' + content + ' updating tb_memo: %s' % data_dict)

    return result, content


def insert_vnf_image_history(mydb, history_dict):

    INSERT_ = {}
    if 'serverseq' in history_dict:
        INSERT_['serverseq'] = history_dict['serverseq']
    if 'server_name' in history_dict:
        INSERT_['server_name'] = history_dict['server_name']
    if 'nsseq' in history_dict:
        INSERT_['nsseq'] = history_dict['nsseq']
    if 'nsr_name' in history_dict:
        INSERT_['nsr_name'] = history_dict['nsr_name']
    if 'nfseq' in history_dict:
        INSERT_['nfseq'] = history_dict['nfseq']
    if 'nfr_name' in history_dict:
        INSERT_['nfr_name'] = history_dict['nfr_name']
    if 'vdudimageseq_old' in history_dict:
        INSERT_['vdudimageseq_old'] = history_dict['vdudimageseq_old']
    if 'vnf_image_version_old' in history_dict:
        INSERT_['vnf_image_version_old'] = history_dict['vnf_image_version_old']
    if 'vnf_sw_version_old' in history_dict:
        INSERT_['vnf_sw_version_old'] = history_dict['vnf_sw_version_old']
    if 'vdudimageseq_new' in history_dict:
        INSERT_['vdudimageseq_new'] = history_dict['vdudimageseq_new']
    if 'vnf_image_version_new' in history_dict:
        INSERT_['vnf_image_version_new'] = history_dict['vnf_image_version_new']
    if 'vnf_sw_version_new' in history_dict:
        INSERT_['vnf_sw_version_new'] = history_dict['vnf_sw_version_new']
    if 'memo' in history_dict:
        INSERT_['memo'] = history_dict['memo']
    if 'update_dt' in history_dict:
        INSERT_['update_dt'] = history_dict['update_dt']

    try:
        result, content = mydb.new_row("tb_vnf_image_history", INSERT_, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("Failed to insert tb_vnf_image_history record : %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert tb_vnf_image_history - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert tb_vnf_image_history - %s" %str(e)


def update_vdud_image(mydb, instance_dict):
    if 'vdudimageseq' not in instance_dict:
        return -HTTP_Not_Found, "No target seq in the request"
    UPDATE_={}
    # if "vnf_image_version" in instance_dict:
    #     UPDATE_["vnf_image_version"] = instance_dict["vnf_image_version"]
    if "vnf_sw_version" in instance_dict:
        UPDATE_["vnf_sw_version"] = instance_dict["vnf_sw_version"]

    result = -HTTP_Not_Found
    if len(UPDATE_)>0:
        WHERE_={'vdudimageseq': instance_dict['vdudimageseq']}

        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_vdud_image', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_vdud_image Error ' + content + ' updating table update_vdud_image: ' + str(instance_dict['vdudimageseq']))
    return result, instance_dict['vdudimageseq']


def insert_patch(mydb, file_dict):

    INSERT_ = {}
    if 'location' in file_dict:
        INSERT_['location'] = file_dict['location']
    if 'vnfm_version' in file_dict:
        INSERT_['vnfm_version'] = file_dict['vnfm_version']
    if 'agent_version' in file_dict:
        INSERT_['agent_version'] = file_dict['agent_version']
    if 'filesize' in file_dict:
        INSERT_['filesize'] = file_dict['filesize']
    if 'description' in file_dict:
        INSERT_['description'] = file_dict['description']

    INSERT_['modify_dttm'] = datetime.datetime.now()
    result, content = mydb.new_row('tb_patch', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)

    if result <= 0:
        log.error("insert_patch error %d %s" % (result, str(content)))

    return result, content


def update_patch(mydb, file_dict):
    UPDATE_ = {}
    if 'location' in file_dict:
        UPDATE_['location'] = file_dict['location']
    if 'vnfm_version' in file_dict:
        UPDATE_['vnfm_version'] = file_dict['vnfm_version']
    if 'agent_version' in file_dict:
        UPDATE_['agent_version'] = file_dict['agent_version']
    if 'filesize' in file_dict:
        UPDATE_['filesize'] = file_dict['filesize']
    if 'description' in file_dict:
        UPDATE_['description'] = file_dict['description']

    UPDATE_['modify_dttm'] = datetime.datetime.now()
    result, content = mydb.update_rows('tb_patch', UPDATE_, {"patch_seq":file_dict["patch_seq"]})
    if result < 0:
        log.error('update_patch Error ' + content + ' updating table patch: ' + str(file_dict['patch_seq']))
    return result, file_dict['patch_seq']


def insert_patch_target(mydb, target_dict):

    INSERT_ = {}
    if 'patch_seq' in target_dict:
        INSERT_['patch_seq'] = target_dict['patch_seq']
    if 'category' in target_dict:
        INSERT_['category'] = target_dict['category']
    if 'version' in target_dict:
        INSERT_['version'] = target_dict['version']

    result, content = mydb.new_row('tb_patch_target', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)

    if result <= 0:
        log.error("insert_patch_target error %d %s" % (result, str(content)))

    return result, content


def delete_patch_target(mydb, target_dict):

    result, content = mydb.delete_row_by_dict(FROM="tb_patch_target", WHERE={"patch_seq": target_dict["patch_seq"]})
    if result < 0:
        log.error("Failed to delete patch_target data")
    return result, content


def get_patch_file(mydb, cond_dict):

    where_ = {}
    if "patch_seq" in cond_dict:
        where_["patch_seq"] = cond_dict["patch_seq"]
    else:
        if "location" in cond_dict:
            where_["location"] = cond_dict["location"]

    result, content = mydb.get_table(FROM='tb_patch', WHERE=where_)
    if result <= 0:
        log.warning("Failed to get_patch_file %d %s" % (result, content))
        return result, content

    return result, content[0]


def get_account_id_of_customer(mydb, customer_dict):

    WHERE_dict={}
    if "customerseq" in customer_dict:
        WHERE_dict['cust.customerseq']  = customer_dict["customerseq"]
    elif "customerename" in customer_dict:
        WHERE_dict['cust.customerename']  = customer_dict["customerename"]

    f_tmp = 'tb_customer as cust join tb_customer_account as cust_ac on cust.customerseq=cust_ac.customer_seq '
    s_tmp = ('cust.customerseq as customerseq', 'cust_ac.account_id as account_id')
    result, content = mydb.get_table(FROM=f_tmp, SELECT=s_tmp, WHERE=WHERE_dict)
    if result <= 0:
        return result, content

    return result, content[0]


def get_resourcetemplate_nscatalog(mydb, nsr_id):

    select_ = ("nscat.resourcetemplate as resourcetemplate",)
    from_ = " tb_nsr as nsr join tb_nscatalog as nscat on nsr.nscatseq=nscat.nscatseq "
    result, content = mydb.get_table(FROM=from_, SELECT=select_, WHERE={"nsr.nsseq":nsr_id})
    if result <= 0:
        return result, content
    return result, content[0]


def update_server_delivery_dttm(mydb, server_id):
    update_ = {}
    update_['deliver_dttm'] = datetime.datetime.now()
    server_result, content = mydb.update_rows('tb_server', update_, {"serverseq":server_id})
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, content))
        return server_result, content

    return server_result, content


def insert_onebox_auth(mydb, auth_dict):

    INSERT_ = {}
    if 'ob_account' in auth_dict:
        INSERT_['ob_account'] = auth_dict['ob_account']
    else:
        return -HTTP_Bad_Request, "Need ob_account"

    if 'account_group_seq' in auth_dict:
        INSERT_['account_group_seq'] = auth_dict['account_group_seq']

    if 'status' in auth_dict:
        INSERT_['status'] = auth_dict['status']

    result, content = mydb.new_row('tb_onebox_auth', INSERT_, tenant_id=None, add_uuid=False, log=db_debug, last_val=False)

    if result <= 0:
        log.error("insert_onebox_auth error %d %s" % (result, str(content)))

    return result, content


def get_onebox_auth(mydb, auth_dict):
    where_ = {}
    if "ob_account" in auth_dict:
        where_["ob_account"] = auth_dict["ob_account"]

    result, content = mydb.get_table(FROM='tb_onebox_auth', WHERE=where_)
    if result <= 0:
        log.warning("Failed to get_onebox_auth %d %s" % (result, content))
        return result, content

    return result, content[0]


def update_onebox_auth(mydb, auth_dict):
    UPDATE_ = {}
    if 'ob_account' not in auth_dict:
        return -HTTP_Bad_Request, "Need ob_account"

    if 'privatekey_path' in auth_dict:
        UPDATE_['privatekey_path'] = auth_dict['privatekey_path']
    if 'publickey_path' in auth_dict:
        UPDATE_['publickey_path'] = auth_dict['publickey_path']
    if 'status' in auth_dict:
        UPDATE_['status'] = auth_dict['status']

    UPDATE_['modify_dttm'] = datetime.datetime.now()
    result, content = mydb.update_rows('tb_onebox_auth', UPDATE_, {"ob_account":auth_dict["ob_account"]})
    if result < 0:
        log.error('update_onebox_auth Error ' + content + ' updating table tb_onebox_auth: ' + str(auth_dict['ob_account']))
    return result, auth_dict['ob_account']


def delete_onebox_auth(mydb, target_dict):
    where_ = {}
    if "ob_account" in target_dict:
        where_["ob_account"] = target_dict["ob_account"]
    else:
        return -HTTP_Bad_Request, "Need condition for WHERE"

    result, content = mydb.delete_row_by_dict(FROM="tb_onebox_auth", WHERE=where_)
    if result < 0:
        log.error("Failed to delete onebox_auth data")
    return result, content


def insert_onebox_auth_deploy(mydb, auth_deploy_dict):

    INSERT_ = {}
    if 'ob_account' in auth_deploy_dict:
        INSERT_['ob_account'] = auth_deploy_dict['ob_account']
    else:
        return -HTTP_Bad_Request, "Need ob_account"

    if 'deploy_type' in auth_deploy_dict:
        INSERT_['deploy_type'] = auth_deploy_dict['deploy_type']
    if 'status' in auth_deploy_dict:
        INSERT_['status'] = auth_deploy_dict['status']

    if 'privatekey_path' in auth_deploy_dict:
        INSERT_['privatekey_path'] = auth_deploy_dict['privatekey_path']
    if 'publickey_path' in auth_deploy_dict:
        INSERT_['publickey_path'] = auth_deploy_dict['publickey_path']

    result, content = mydb.new_row('tb_onebox_auth_deploy', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)

    if result <= 0:
        log.error("insert_onebox_auth_deploy error %d %s" % (result, str(content)))

    return result, content


def update_onebox_auth_deploy(mydb, auth_deploy_dict):
    UPDATE_ = {}
    if 'auth_deploy_seq' not in auth_deploy_dict:
        return -HTTP_Bad_Request, "Need ob_account"

    if 'privatekey_path' in auth_deploy_dict:
        UPDATE_['privatekey_path'] = auth_deploy_dict['privatekey_path']
    if 'publickey_path' in auth_deploy_dict:
        UPDATE_['publickey_path'] = auth_deploy_dict['publickey_path']
    if 'status' in auth_deploy_dict:
        UPDATE_['status'] = auth_deploy_dict['status']
    if 'target_ob_cnt' in auth_deploy_dict:
        UPDATE_['target_ob_cnt'] = auth_deploy_dict['target_ob_cnt']

    UPDATE_['modify_dttm'] = datetime.datetime.now()
    result, content = mydb.update_rows('tb_onebox_auth_deploy', UPDATE_, {"auth_deploy_seq":auth_deploy_dict["auth_deploy_seq"]})
    if result < 0:
        log.error('update_onebox_auth_deploy Error ' + content + ' updating table tb_onebox_auth_deploy: ' + str(auth_deploy_dict['auth_deploy_seq']))
    return result, auth_deploy_dict['auth_deploy_seq']


def get_onebox_auth_deploy(mydb, auth_deploy_dict):
    where_ = {}
    if "auth_deploy_seq" in auth_deploy_dict:
        where_["auth_deploy_seq"] = auth_deploy_dict["auth_deploy_seq"]
    else:
        if "ob_account" in auth_deploy_dict:
            where_["ob_account"] = auth_deploy_dict["ob_account"]
        if "status" in auth_deploy_dict:
            where_["status"] = auth_deploy_dict["status"]
        if "deploy_type" in auth_deploy_dict:
            where_["deploy_type"] = auth_deploy_dict["deploy_type"]

    result, content = mydb.get_table(FROM='tb_onebox_auth_deploy', WHERE=where_)
    if result <= 0:
        log.warning("Failed to get_onebox_auth_deploy %d %s" % (result, content))
        return result, content

    return result, content[0]


def get_onebox_auth_deploy_batch(mydb):
    where_ = {"status":"R"}

    result, content = mydb.get_table(FROM='tb_onebox_auth_deploy', WHERE=where_)
    if result <= 0:
        log.warning("Failed to get_onebox_auth_deploy_batch %d %s" % (result, content))
        return result, content

    return result, content


def delete_onebox_auth_deploy(mydb, target_dict):
    where_ = {}
    if "auth_deploy_seq" in target_dict:
        where_["auth_deploy_seq"] = target_dict["auth_deploy_seq"]
    else:
        return -HTTP_Bad_Request, "Need condition for WHERE"

    result, content = mydb.delete_row_by_dict(FROM="tb_onebox_auth_deploy", WHERE=where_)
    if result < 0:
        log.error("Failed to delete auth_deploy data")
    return result, content


def get_onebox_auth_deploy_fail(mydb, auth_deploy_fail_dict):
    where_ = {}
    if "deploy_fail_seq" in auth_deploy_fail_dict:
        where_["deploy_fail_seq"] = auth_deploy_fail_dict["deploy_fail_seq"]
    else:
        if "auth_deploy_seq" in auth_deploy_fail_dict:
            where_["auth_deploy_seq"] = auth_deploy_fail_dict["auth_deploy_seq"]
        if "serverseq" in auth_deploy_fail_dict:
            where_["serverseq"] = auth_deploy_fail_dict["serverseq"]

    result, content = mydb.get_table(FROM='tb_onebox_auth_deploy_fail', WHERE=where_)
    if result <= 0:
        log.warning("Failed to get_onebox_auth_deploy_fail %d %s" % (result, content))
        return result, content

    return result, content[0]


def get_onebox_auth_deploy_fail_batch(mydb):

    result, content = mydb.get_table(FROM='tb_onebox_auth_deploy_fail',ORDER="auth_deploy_seq asc")
    if result <= 0:
        log.warning("Failed to get_onebox_auth_deploy_fail_batch %d %s" % (result, content))
        return result, content

    return result, content


def insert_onebox_auth_deploy_fail(mydb, deploy_fail_dict):
    INSERT_ = {}
    if 'auth_deploy_seq' in deploy_fail_dict:
        INSERT_['auth_deploy_seq'] = deploy_fail_dict['auth_deploy_seq']
    else:
        return -HTTP_Bad_Request, "Need auth_deploy_seq"

    if 'serverseq' in deploy_fail_dict:
        INSERT_['serverseq'] = deploy_fail_dict['serverseq']
    else:
        return -HTTP_Bad_Request, "Need serverseq"


    if 'ob_account' in deploy_fail_dict:
        INSERT_['ob_account'] = deploy_fail_dict['ob_account']
    if 'deploy_type' in deploy_fail_dict:
        INSERT_['deploy_type'] = deploy_fail_dict['deploy_type']

    if 'privatekey_path' in deploy_fail_dict:
        INSERT_['privatekey_path'] = deploy_fail_dict['privatekey_path']
    if 'publickey_path' in deploy_fail_dict:
        INSERT_['publickey_path'] = deploy_fail_dict['publickey_path']

    if 'description' in deploy_fail_dict:
        INSERT_['description'] = deploy_fail_dict['description']

    result, content = mydb.new_row('tb_onebox_auth_deploy_fail', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)

    if result <= 0:
        log.error("insert_onebox_auth_deploy_fail error %d %s" % (result, str(content)))

    return result, content


def delete_onebox_auth_deploy_fail(mydb, target_dict):
    where_ = {}
    if "ob_account" in target_dict:
        where_["ob_account"] = target_dict["ob_account"]
    elif "deploy_fail_seq" in target_dict:
        where_["deploy_fail_seq"] = target_dict["deploy_fail_seq"]
    else:
        return -HTTP_Bad_Request, "Need condition for WHERE"

    result, content = mydb.delete_row_by_dict(FROM="tb_onebox_auth_deploy_fail", WHERE=where_)
    if result < 0:
        log.error("Failed to delete tb_onebox_auth_deploy_fail data")
    return result, content


def insert_onebox_auth_batch(mydb, batch_dict):
    INSERT_ = {}
    if 'batch_type' in batch_dict:
        INSERT_['batch_type'] = batch_dict['batch_type']
    else:
        return -HTTP_Bad_Request, "Need batch_type"

    if 'reserve_dtt' in batch_dict:
        INSERT_['reserve_dtt'] = batch_dict['reserve_dtt']
    else:
        return -HTTP_Bad_Request, "Need reserve_dtt"

    result, content = mydb.new_row('tb_onebox_auth_batch', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)

    if result <= 0:
        log.error("insert_onebox_auth_batch error %d %s" % (result, str(content)))

    return result, content


def delete_onebox_auth_batch(mydb, target_dict):
    where_ = {}
    if "batch_seq" in target_dict:
        where_["batch_seq"] = target_dict["batch_seq"]
    elif "batch_type" in target_dict:
        where_["batch_type"] = target_dict["batch_type"]
    else:
        return -HTTP_Bad_Request, "Need condition for WHERE"

    result, content = mydb.delete_row_by_dict(FROM="tb_onebox_auth_batch", WHERE=where_)
    if result < 0:
        log.error("Failed to delete onebox_auth_batch data")
    return result, content


def get_onebox_auth_batch(mydb, target_dict):
    where_ = {}
    if "batch_type" in target_dict:
        where_["batch_type"] = target_dict["batch_type"]

    result, content = mydb.get_table(FROM='tb_onebox_auth_batch', WHERE=where_)
    if result <= 0:
        log.warning("Failed to get_onebox_auth_batch %d %s" % (result, content))
        return result, content

    return result, content


def get_backup_basetime(mydb):
    select_ = ('a.hhmm as hhmm', 'count( b.dayhh || b.daymm) as count')
    from_ = " tb_backup_basetime a LEFT OUTER JOIN tb_backup_scheduler AS b ON a.hhmm=b.dayhh || b.daymm AND b.category IN ( 'ONEBOX', 'NS' ) AND  b.dayuse_yn = 'Y'"
    group_ = " hhmm"
    order_ = "count, hhmm"
    limit_ = 1

    result, content = mydb.get_table_group(FROM=from_, SELECT=select_, GROUP=group_, ORDER=order_, LIMIT=limit_)
    if result < 0:
        log.error("get_deployed_and_deployable_list error %d %s" % (result, content))
        return -result, content
    return result, content

def get_backup_scheduler(mydb, get_dict):
    pass

def insert_backup_scheduler(mydb, in_dict):
    log.debug('(insert_backup_scheduler) in_dict = %s' %str(in_dict))

    where_ = {}
    where_["category"] = in_dict["category"]
    where_["categoryseq"] = in_dict["categoryseq"]

    result, content = mydb.get_table(FROM='tb_backup_scheduler', WHERE=where_)
    if result > 0:
        log.warning("exist tb_backup_scheduler : %s %d %s" % (in_dict["category"], result, content))
        log.debug("exist tb_backup_scheduler : %s %d %s" % (in_dict["category"], result, content))
        return 200, "OK"

    # result, content = mydb.new_row("tb_server_hanet", hanet_dict, None, add_uuid=False, log=db_debug)
    result, content = mydb.new_row('tb_backup_scheduler', in_dict, tenant_id=None, add_uuid=False, log=db_debug, last_val=False)

    if result <= 0:
        log.error("insert_backup_scheduler error %d %s" % (result, str(content)))

    return result, content

def delete_backup_scheduler(mydb, del_dict):
    log.debug('(delete_backup_scheduler) del_dict = %s' %str(del_dict))

    where_ = {}
    where_["category"] = del_dict["category"]
    where_["categoryseq"] = del_dict["categoryseq"]

    result, content = mydb.delete_row_by_dict(FROM="tb_backup_scheduler", WHERE=where_)
    if result < 0:
        log.error("Failed to delete backup scheduler %s" %str(del_dict.get('category')))
    return result, content


def pnftest_get_server_id(mydb, id, tbname="tb_server"):
    if type(id) is int or type(id) is long:
        where_ = {"serverseq": id}
    elif id.isdigit():
        where_ = {"serverseq": id}
    else:
        where_ = {"servername": id}

    select_ = None

    if tbname == "tb_server":
        select_ = ('serverseq',
                   'servername',
                   'mgmtip as mgmt_ip',
                   'publicip as public_ip',
                   'action',
                   'vnfm_base_url',
                   'obagent_base_url',
                   'obagent_version',
                   'publicmac',
                   'publicgwip as public_gw_ip',
                   'publiccidr as public_cidr_prefix',
                   'mgmt_nic',
                   'public_nic',
                   'onebox_id'
                   )
    elif tbname == "tb_onebox_hw":
        select_ = ('num_cores_per_cpu', 'mem_size', 'num_cpus', 'serverseq', 'num_logical_cores', 'model', 'cpu')
    elif tbname == "tb_onebox_sw":
        select_ = ('operating_system', 'onebox_vnfm_base_url as vnfm_base_url', 'onebox_agent_base_url as obagent_base_url', 'onebox_agent_version as obagent_version')

    if select_:
        result, content = mydb.get_table(FROM=tbname, SELECT=select_, WHERE=where_)
    else:
        result, content = mydb.get_table(FROM=tbname, WHERE=where_)

    if result < 0:
        log.error("get_server_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found Server with %s" % str(where_)

    return result, content[0]

def pnftest_update(mydb, id, data, tbname=None):
    if tbname is None:
        return -HTTP_Bad_Request, "No have data : tbname"

    if id is None:
        return -HTTP_Bad_Request, "No have data : id"

    if data is None:
        return -HTTP_Bad_Request, "No have data : data"

    WHERE_ = {'serverseq': id}

    data['modify_dttm'] = datetime.datetime.now()

    result, content = mydb.update_rows(tbname, data, WHERE_)

    if result < 0:
        log.error("update_customer error %d %s" % (result, content))
    return result, content


##################      Odroid TEST         ######################################################################
def odroid_update(mydb, update_dict):
    # tb_server
    update_ = {}
    update_['status'] = 'N__IN_SERVICE'
    update_['modify_dttm'] = datetime.datetime.now()

    server_result, server_content = mydb.update_rows('tb_server', update_, {"onebox_id": update_dict.get('onebox_id')})
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, server_content))
        return server_result, server_content

    # tb_nsr
    nsr_update = {}
    nsr_update['name'] = update_dict.get('ns_name')
    nsr_update['status'] = 'N__RUNNING'
    nsr_update['modify_dttm'] = datetime.datetime.now()

    nsr_result, nsr_content = mydb.update_rows('tb_nsr', nsr_update, {"nsseq": update_dict.get('nsseq')})
    if nsr_result < 0:
        log.error("update_nsr error %d %s" % (nsr_result, nsr_content))
        return nsr_result, nsr_content


    # tb_nfr
    nfr_update = {}
    nfr_update['status'] = 'N__RUNNING'
    nfr_update['modify_dttm'] = datetime.datetime.now()

    nfr_result, nfr_content = mydb.update_rows('tb_nfr', nfr_update, {"nsseq": update_dict.get('nsseq')})
    if nfr_result < 0:
        log.error("update_nfr error %d %s" % (nfr_result, nfr_content))
        return nfr_result, nfr_content

    return 200, "OK"

def odroid_reset(mydb, reset_dict):
    # tb_server
    update_ = {}
    update_['status'] = 'I__LINE_WAIT'
    update_['modify_dttm'] = datetime.datetime.now()

    server_result, server_content = mydb.update_rows('tb_server', update_, {"onebox_id": reset_dict.get('onebox_id')})
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, server_content))
        return server_result, server_content

    # tb_nsr
    nsr_update = {}
    nsr_update['name'] = '-'
    nsr_update['status'] = 'I__NONE'
    nsr_update['modify_dttm'] = datetime.datetime.now()

    nsr_result, nsr_content = mydb.update_rows('tb_nsr', nsr_update, {"nsseq": reset_dict.get('nsseq')})
    if nsr_result < 0:
        log.error("update_nsr error %d %s" % (nsr_result, nsr_content))
        return nsr_result, nsr_content

    # tb_nfr
    nfr_update = {}
    nfr_update['status'] = 'I__NONE'
    nfr_update['modify_dttm'] = datetime.datetime.now()

    nfr_result, nfr_content = mydb.update_rows('tb_nfr', nfr_update, {"nsseq": reset_dict.get('nsseq')})
    if nfr_result < 0:
        log.error("update_nfr error %d %s" % (nfr_result, nfr_content))
        return nfr_result, nfr_content

    return 200, "OK"
##################################################################################################################


##################      HA TEST         ##########################################################################

def get_server_hanet(mydb, serverseq):
    result, content = mydb.get_table(FROM='tb_server_hanet', WHERE={"serverseq":serverseq})
    if result <= 0:
        return result, content
    else:
        return result, content[0]


def delete_server_hanet(mydb, serverseq):
    del_column = "serverseq"

    result, content = mydb.delete_row_seq("tb_server_hanet", del_column, serverseq, None, db_debug)
    if result < 0:
        log.error("delete_server_hanet error %d %s" % (result, content))
    return result, content


def insert_server_hanet(mydb, hanet_dict):
    result, content = mydb.new_row("tb_server_hanet", hanet_dict, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("tb_server_hanet error %d %s" % (result, content))
    return result, content

##################################################################################################################