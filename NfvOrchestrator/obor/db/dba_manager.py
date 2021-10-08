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

"""
DB Access Manager implements all the methods to interact with WFM-DB for KT One-Box Service.
"""

import json
import yaml
import os
import time
import sys
import datetime

from utils import db_conn_manager as dbmanager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils import auxiliary_functions as af
from orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Conflict

from utils.aes_chiper import AESCipher

# global_config = None

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
    where = {}
    limit = 100
    select = []
    for k in qs:
        if k == 'field':
            select += qs.getall(k)
            for v in select:
                if v not in allowed:
                    # bottle.abort(HTTP_Bad_Request, "Invalid query string at 'field="+v+"'")
                    return -HTTP_Bad_Request, "Invalid query string at 'field=" + v + "'"
        elif k == 'limit':
            try:
                limit = int(qs[k])
            except Exception, e:
                log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
                return -HTTP_Bad_Request, "Invalid query string at 'limit=" + qs[k] + "'"
        else:
            if k not in allowed:
                # bottle.abort(HTTP_Bad_Request, "Invalid query string at '"+k+"="+qs[k]+"'")
                return -HTTP_Bad_Request, "Invalid query string at '" + k + "=" + qs[k] + "'"
            if qs[k] != "null":
                where[k] = qs[k]
            else:
                where[k] = None
    if len(select) == 0: select += allowed
    # change from http api to database naming
    for i in range(0, len(select)):
        k = select[i]
        if http2db and k in http2db:
            select[i] = http2db[k]
    if http2db:
        change_keys_http2db(where, http2db)

    return select, where, limit

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


def insert_server(server_dict):#, vim_dict=None, vim_tenant_dict=None, hardware_dict=None, software_dict=None, network_list=None, vnet_dict=None):

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


def update_server(server_dict):
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
    if 'onebox_flavor' in server_dict: update_['onebox_flavor'] = server_dict['onebox_flavor']
    if 'obagent_base_url' in server_dict: update_['obagent_base_url'] = server_dict['obagent_base_url']

    if 'status' in server_dict: update_['status'] = server_dict['status']
    if 'state' in server_dict: update_['state'] = server_dict['state']
    if 'serveruuid' in server_dict: update_['serveruuid'] = server_dict['serveruuid']

    # mgmt_nic, public_nic 처리
    if 'mgmt_nic' in server_dict: update_['mgmt_nic'] = server_dict['mgmt_nic']
    if 'public_nic' in server_dict: update_['public_nic'] = server_dict['public_nic']

    if 'description' in server_dict:
        # log.debug("Description: %s" %server_dict['description'])
        update_['description'] = server_dict['description']

    if 'action' in server_dict: update_['action'] = server_dict['action']

    # 초소형 One-Box 에서 추가된 column
    if 'web_url' in server_dict: update_['web_url'] = server_dict['web_url']

    # 초소형 One-Box 단계에서 필요하지 않은 항목들
    if 'nsseq' in server_dict: update_['nsseq'] = server_dict['nsseq']
    if 'vnfm_base_url' in server_dict: update_['vnfm_base_url'] = server_dict['vnfm_base_url']
    if 'vnfm_version' in server_dict: update_['vnfm_version'] = server_dict['vnfm_version']
    if 'serial_no' in server_dict: update_['serial_no'] = server_dict['serial_no']
    if 'obagent_version' in server_dict: update_['obagent_version'] = server_dict['obagent_version']
    if 'net_mode' in server_dict: update_['net_mode'] = server_dict['net_mode']
    if 'officeseq' in server_dict: update_['officeseq'] = server_dict['officeseq']
    if 'ob_service_number' in server_dict: update_['ob_service_number'] = server_dict['ob_service_number']

    # 무선(router/lte) 사용 시 : router = 'W'
    if 'router' in server_dict:
        update_['router'] = server_dict['router']
    else:
        # router 가 아닐 때, router 사용 하다가 장비 교체등의 이유로 사용하지 않게 되었을 때
        update_['router'] = None

    # Update 대상으로 포함해도 되는지 확인필요.
    # if 'customerseq' in server_dict: update_['customerseq'] = server_dict['customerseq']
    # if 'orgnamescode' in server_dict: update_['orgnamescode'] = server_dict['orgnamescode']

    if len(update_) == 0:
        return -HTTP_Bad_Request, "No Update Data"

    update_['modify_dttm'] = datetime.datetime.now()
    server_result, content = mydb.update_rows('tb_server', update_, where_)
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, content))
        return server_result, content

    return server_result, server_dict['serverseq']


def update_server_status(server_dict, is_action=False):
    WHERE_={'serverseq': server_dict['serverseq']}

    UPDATE_ = {}

    if 'status' in server_dict: # 필수값
        UPDATE_['status'] = server_dict['status']

    if is_action and 'action' in server_dict:
        UPDATE_['action'] = server_dict['action']

    # 서버 STATE 상태값 추가로 인하여 여기에서 STATE 값도 변경해준다.
    if 'chg_state' in server_dict:
        UPDATE_['state'] = server_dict['chg_state']

    UPDATE_['modify_dttm']=datetime.datetime.now()

    result, content =  mydb.update_rows('tb_server', UPDATE_, WHERE_)
    if result < 0:
        log.error('update_server_status Error ' + content + ' updating table tb_server: ' + str(server_dict['serverseq']))
    return result, server_dict['serverseq']


def get_server_wan_list(serverseq, kind="R"):
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


def get_customer_resources(id, onebox_id=None):
    r, customer_dict = get_customer_id(id)
    if r <= 0:
        log.error("failed to get customer Info from DB %d %s" % (r, customer_dict))
        return -HTTP_Not_Found, customer_dict

    # log.debug("customer_dict: %s" %str(customer_dict))

    resource_list = []

    # ponebox
    if onebox_id is not None:
        r, servers = mydb.get_table(FROM='tb_server', WHERE={'onebox_id': onebox_id})
    else:
        r, servers = mydb.get_table(FROM='tb_server', WHERE={'customerseq': customer_dict['customerseq']})

    if r < 0:
        return -HTTP_Internal_Server_Error, servers
    if r > 0:
        for item in servers:
            item['resource_type'] = 'server'
            resource_list.append(item)

            if item.get('nfsubcategory') == 'KtArm':
                r, vims = mydb.get_table(FROM='tb_vim', WHERE={'serverseq': item['serverseq']})
                if r < 0:
                    return -HTTP_Internal_Server_Error, vims
                if r > 0:
                    for vim in vims:
                        vim['resource_type'] = 'vim'
                        resource_list.append(vim)

    # log.debug("the number of resources for the customer %s: %d" % (id, len(resource_list)))
    return len(resource_list), resource_list


def delete_server(id):
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


def delete_server_wan(cond_dict, kind="R"):
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


def delete_customer(id):
    if type(id) is int or type(id) is long:
        del_column = 'customerseq'
    elif id.isdigit():
        del_column = 'customerseq'
    else:
        del_column = 'customername'

    # 추가 : tb_customer_account.customer_seq fk 제거로 인하여 tb_customer_account 삭제 추가됨
    rs, ct = _delete_customer_account(id)

    result, content = mydb.delete_row_seq("tb_customer", del_column, id, None, db_debug)
    if result < 0:
        log.error("delete_customer error %d %s" % (result, content))
    return result, content


def _delete_customer_account(customerseq):
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


def get_account_id_of_customer(customer_dict):

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


def insert_server_wan(wan_dict):
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
    #if "status" in wan_dict: INSERT_["status"] = wan_dict["status"]
    #if "physnet_name" in wan_dict: INSERT_["physnet_name"] = wan_dict["physnet_name"]

    # status main : A, sub : S
    if "mgmt_boolean" in wan_dict:
        if wan_dict.get('mgmt_boolean') is True:
            INSERT_["physnet_name"] = "physnet_wan"
            INSERT_["status"] = "A"
        else:
            INSERT_["physnet_name"] = "physnet_extrawan1"
            INSERT_["status"] = "S"

    log.debug('[dba_manager] insert_server_wan : insert = %s' %str(INSERT_))

    try:
        result, content = mydb.new_row("tb_server_wan", INSERT_, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("tb_server_wan error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert tb_server_wan - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert tb_server_wan - %s" %str(e)

# wan_list update 처리 함수
def update_server_wan(wan_dict, wan_seq):
    WHERE_ = {'wan_seq' : wan_seq}

    try:
        result, content = mydb.update_rows('tb_server_wan', wan_dict, WHERE_)
        if result < 0:
            log.error("tb_server_wan update error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : update tb_server_wan - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert tb_server_wan - %s" %str(e)

# 준공일 업데이트
def update_server_delivery_dttm(server_id):
    update_ = {}
    update_['deliver_dttm'] = datetime.datetime.now()
    server_result, content = mydb.update_rows('tb_server', update_, {"serverseq":server_id})
    if server_result < 0:
        log.error("update_server error %d %s" % (server_result, content))
        return server_result, content

    return server_result, content


# def update_vim(vim_dict, vim_tenant_dict):
#     pre_vim_result, pre_vim_data = get_vim_serverseq(mydb, server_dict['serverseq'])
#     if pre_vim_result > 0:
#         #log.debug("update_server() vim already exists %s" %str(pre_vim_data[0]['vimseq']))
#         vim_dict['modify_dttm']=datetime.datetime.now()
#         vim_result, vim_data = mydb.update_rows('tb_vim', vim_dict, {"vimseq":pre_vim_data[0]['vimseq']})
#
#         if vim_result < 0:
#             log.error("update_server error %d %s" %(vim_result, vim_data))
#             return vim_result, vim_data
#
#         vimseq = pre_vim_data[0]['vimseq']
#     else:
#         #log.debug("update_server() insert DB into tb_vim")
#         vim_dict['serverseq']=server_dict['serverseq']
#
#         vim_result, vimseq = mydb.new_row("tb_vim", vim_dict, tenant_id=None, add_uuid=False, log=db_debug)
#
#         if vim_result < 0:
#             log.error("update_server error %d %s" %(vim_result, vimseq))
#             return vim_result, vimseq
#
#     # server_dict['vimseq'] = vimseq
#
#     if vim_tenant_dict:
#         pre_vt_result, pre_vt_data = get_vim_tenant_id(mydb, vim_tenant_id=None, vim_tenant_name=None, vim_id=vimseq)
#         if pre_vt_result > 0:
#             #log.debug("update_server() vim_tenant already exists %s" %str(pre_vt_data[0]['vimtenantseq']))
#             vim_tenant_dict['modify_dttm']=datetime.datetime.now()
#             vt_result, vt_seq = mydb.update_rows('tb_vim_tenant', vim_tenant_dict, {"vimtenantseq": pre_vt_data[0]['vimtenantseq']})
#         else:
#             #log.debug("update_server() insert DB into tb_vim_tenant")
#             vim_tenant_dict['vimseq']=vimseq
#             vt_result, vt_seq = mydb.new_row("tb_vim_tenant", vim_tenant_dict, None, add_uuid=False, log=db_debug)
#
#         if vt_result < 0:
#             log.error("update_server() error %d %s" %(vt_result, str(vt_seq)))
#             return vt_result, vt_seq
#
#     return 200, vimseq

def update_server_oba(server_dict, hardware_dict=None, software_dict=None, network_list=None):
    """
    server 정보 업데이트 [ OB Info Noti. ]
    :param server_dict:
    :param hardware_dict:
    :param software_dict:
    :param network_list:
    :return:
    """

    # server의 status 가 변경되지 않도록 status 항목을 제거한다.
    status_bak = None
    if "status" in server_dict:
        status_bak = server_dict['status']
        del server_dict['status']
    result, server_key = update_server(server_dict)
    if result < 0:
        raise Exception(server_key)
    # status 복구
    if status_bak:
        server_dict['status'] = status_bak

    # 회선이중화 : wan_list 저장
    if "wan_list" in server_dict:
        # tb_server_wan에 값이 없는 경우에만 저장처리.
        # 변경된 정보 수정처리는 뒷단에서 하므로 이 부분에서는 생략.

        is_create = False

        db_wan_result, db_wan_list = get_server_wan_list(server_dict["serverseq"])
        if db_wan_result < 0:
            return db_wan_result, db_wan_list
        elif db_wan_result > 0:
            # NSR 설치된 경우 : 기존 항목을 그대로 사용한다.
            # 설치가 안된 경우 : 추가/삭제된 경우(갯수가 달라진 경우) 기존 WAN 삭제 후 변경된 내용 저장처리
            if "nsseq" in server_dict:
                is_create = False
            else:
                # 기존 소스, wan 개수로만 판단, 개수가 다르면 무조건 삭제 후 재등록
                if db_wan_result != len(server_dict["wan_list"]):
                    # 기존 wan 전부 삭제
                    wan_result, wan_content = delete_server_wan({"serverseq":server_dict["serverseq"]}, kind="R")
                    if wan_result < 0:
                        return wan_result, wan_content

                    is_create = True

                    # 뒷단에서 wan 변경 체크 및 update를 하면 안된다.
                    server_dict["is_wan_count_changed"] = True
        else:
            # WAN 정보가 없는 경우.
            is_create = True

        if is_create:
            # 재 등록 (기존 소스, wan 개수로 판단하여 다를경우 삭제 후 재 등록)
            for wan in server_dict["wan_list"]:
                wan["serverseq"] = server_dict["serverseq"]
                wan["onebox_id"] = server_dict.get("onebox_id")

                wan_result, content = insert_server_wan(wan)
                if wan_result < 0:
                    return wan_result, content
        else:
            # 기존 소스의 경우, wan list count로만 판단하여, 실제 변동된 정보 비교가 없어 새 로직 추가
            if db_wan_result > 0:
                update_wan_list = []

                for wl in server_dict["wan_list"]:
                    chk_data={}

                    for dwl in db_wan_list:
                        if wl.get('nic') != dwl.get('nic'):
                            continue

                        chk_data['serverseq'] = server_dict["serverseq"]
                        chk_data['onebox_id'] = server_dict["onebox_id"]

                        if wl.get('public_gw_ip') != dwl.get('public_gw_ip'):   chk_data['public_gw_ip'] = wl.get('public_gw_ip')
                        if wl.get('public_ip') != dwl.get('public_ip'): chk_data['public_ip'] = wl.get('public_ip')
                        if wl.get('public_cidr_prefix') != dwl.get('public_cidr_prefix'): chk_data['public_cidr_prefix'] = wl.get('public_cidr_prefix')
                        if wl.get('ipalloc_mode_public') != dwl.get('ipalloc_mode_public'): chk_data['ipalloc_mode_public'] = wl.get('ipalloc_mode_public')
                        if wl.get('mac') != dwl.get('mac'): chk_data['mac'] = wl.get('mac')
                        if wl.get('mode') != dwl.get('mode'): chk_data['mode'] = wl.get('mode')
                        if wl.get('nic') != dwl.get('nic'): chk_data['nic'] = wl.get('nic')
                        if wl.get('name') != dwl.get('name'): chk_data['name'] = wl.get('name')

                        # status main : A, sub : S
                        if wl.get('mgmt_boolean') is True:
                            p_name = 'physnet_wan'
                            chk_status = "A"
                        else:
                            p_name = 'physnet_extrawan1'
                            chk_status = "S"

                        chk_data['physnet_name'] = p_name
                        if wl.get('status') != dwl.get('status'): chk_data['status'] = chk_status

                        if chk_data:
                            wan_result, content = update_server_wan(chk_data, dwl.get('wan_seq'))

                            if wan_result < 0:
                                return wan_result, content

                        break

    # if vim_dict:
    #     result, vim_key = update_vim(vim_dict, vim_tenant_dict)
    #     if result < 0:
    #         raise Exception(vim_key)
    #     server_dict['vimseq'] = vim_key

    if hardware_dict:
        pre_hw_result, pre_hw_data = get_onebox_hw_serverseq(server_dict['serverseq'])
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
        pre_sw_result, pre_sw_data = get_onebox_sw_serverseq(server_dict['serverseq'])
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

        # 해당 네트워크 리스트를 삭제한다
        deleted, content = mydb.delete_row_by_dict(FROM="tb_onebox_nw", WHERE=where_)

        if deleted < 0:
            log.error("Failed to update One-Box Network Info: %d %s" %(deleted, content))
            return deleted, content

        # 해당 네트워크 리스트를 삭제했으면, 다시 등록한다
        for new_net in network_list:
            new_net['serverseq'] = server_dict['serverseq']
            result, content = mydb.new_row('tb_onebox_nw', new_net, tenant_id=None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("Failed to update One-Box Networ for %s. Cause: %d %s" %(str(new_net), result, content))


    return 200, server_dict['serverseq']


def update_server_oba_arm(server_dict, vim_dict=None, vim_tenant_dict=None, hardware_dict=None, software_dict=None, network_list=None, vnet_dict=None):
    """
    server 정보 업데이트
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

    log.debug('(update_server_oba_arm) server update success!')

    # 회선이중화 : wan_list 저장 / WAN 추가/삭제 동작 중일때는 생략.
    # if "wan_list" in server_dict and not server_dict.get("is_wad", False):
    if "wan_list" in server_dict:
        # tb_server_wan에 값이 없는 경우에만 저장처리.
        # 변경된 정보 수정처리는 뒷단에서 하므로 이 부분에서는 생략.

        is_create = False

        db_wan_result, db_wan_list = get_server_wan_list(server_dict["serverseq"])

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
                    wan_result, wan_content = delete_server_wan({"serverseq": server_dict["serverseq"]}, kind="R")
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

                wan_result, content = insert_server_wan(wan)
                if wan_result < 0:
                    return wan_result, content

        log.debug('(update_server_oba_arm) wan list update success!')

    if "extra_wan_list" in server_dict:
        # tb_server_wan에 값이 없는 경우에만 저장처리.
        is_create = False
        db_wan_result, db_wan_list = get_server_wan_list(server_dict["serverseq"], kind="E")
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
                    wan_result, wan_content = delete_server_wan({"serverseq": server_dict["serverseq"]}, kind="E")
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

                wan_result, content = insert_server_wan(wan)
                if wan_result < 0:
                    return wan_result, content
    else:
        # extra_wan_list 가 설정되었다가 삭제되었을 경우 DB 에서 제거처리.
        db_wan_result, db_wan_list = get_server_wan_list(server_dict["serverseq"], kind="E")
        if db_wan_result > 0:
            if "nsseq" not in server_dict:
                log.warning("Delete old Extra WAN list!!!")
                wan_result, wan_content = delete_server_wan({"serverseq": server_dict["serverseq"]}, kind="E")
            else:
                try:
                    # resourcetemplate에서 extra_wan을 사용하는 vnf가 있는지 확인하고 없으면 삭제.
                    result, rsctp = get_resourcetemplate_nscatalog(server_dict["nsseq"])
                    if result > 0:
                        if str(rsctp["resourcetemplate"]).find("PNET_extrawan") >= 0:
                            log.warning("No extra_wan_list in OBA Info!!!")
                            pass
                        else:
                            result, content = delete_server_wan({"serverseq": server_dict["serverseq"]}, kind="E")
                except Exception, e1:
                    log.warning("Error in deleting extra_wan!!!")

    if vim_dict:
        pre_vim_result, pre_vim_data = get_vim_serverseq(server_dict['serverseq'])
        if pre_vim_result > 0:
            # log.debug("update_server() vim already exists %s" %str(pre_vim_data[0]['vimseq']))
            vim_dict['modify_dttm'] = datetime.datetime.now()
            vim_result, vim_data = mydb.update_rows('tb_vim', vim_dict, {"vimseq": pre_vim_data[0]['vimseq']})

            if vim_result < 0:
                log.error("update_server error %d %s" % (vim_result, vim_data))
                return vim_result, vim_data

            vimseq = pre_vim_data[0]['vimseq']
        else:
            # log.debug("update_server() insert DB into tb_vim")
            vim_dict['serverseq'] = server_dict['serverseq']

            vim_result, vimseq = mydb.new_row("tb_vim", vim_dict, tenant_id=None, add_uuid=False, log=db_debug)

            if vim_result < 0:
                log.error("update_server error %d %s" % (vim_result, vimseq))
                return vim_result, vimseq

        log.debug('(update_server_oba_arm) vim update success!')

        server_dict['vimseq'] = vimseq

        if vim_tenant_dict:
            pre_vt_result, pre_vt_data = get_vim_tenant_id(vim_tenant_id=None, vim_tenant_name=None, vim_id=vimseq)
            if pre_vt_result > 0:
                # log.debug("update_server() vim_tenant already exists %s" %str(pre_vt_data[0]['vimtenantseq']))
                vim_tenant_dict['modify_dttm'] = datetime.datetime.now()
                vt_result, vt_seq = mydb.update_rows('tb_vim_tenant', vim_tenant_dict, {"vimtenantseq": pre_vt_data[0]['vimtenantseq']})
            else:
                # log.debug("update_server() insert DB into tb_vim_tenant")
                vim_tenant_dict['vimseq'] = vimseq
                vt_result, vt_seq = mydb.new_row("tb_vim_tenant", vim_tenant_dict, None, add_uuid=False, log=db_debug)

            if vt_result < 0:
                log.error("update_server() error %d %s" % (vt_result, str(vt_seq)))
                return vt_result, vt_seq

            log.debug('(update_server_oba_arm) vim tenant update success!')

    if hardware_dict:
        pre_hw_result, pre_hw_data = get_onebox_hw_serverseq(server_dict['serverseq'])
        if pre_hw_result > 0:
            # log.debug("update_server() Hardware Info already exists %s" %str(pre_hw_data[0]['seq']))
            hardware_dict['modify_dttm'] = datetime.datetime.now()
            hw_result, hw_data = mydb.update_rows('tb_onebox_hw', hardware_dict, {"seq": pre_hw_data[0]['seq']})

            if hw_result < 0:
                log.warning("update_server error %d %s" % (hw_result, hw_data))
        else:
            hardware_dict['serverseq'] = server_dict['serverseq']

            hw_result, hwseq = mydb.new_row("tb_onebox_hw", hardware_dict, None, add_uuid=False, log=db_debug)

            if hw_result < 0:
                log.warning("update_server error %d %s" % (hw_result, hwseq))

        log.debug('(update_server_oba_arm) hardware update success!')

    if software_dict:
        pre_sw_result, pre_sw_data = get_onebox_sw_serverseq(server_dict['serverseq'])
        if pre_sw_result > 0:
            # log.debug("update_server() Software Info already exists %s" %str(pre_sw_data[0]['seq']))
            software_dict['modify_dttm'] = datetime.datetime.now()
            sw_result, sw_data = mydb.update_rows('tb_onebox_sw', software_dict, {"seq": pre_sw_data[0]['seq']})

            if sw_result < 0:
                log.warning("update_server error %d %s" % (sw_result, sw_data))
        else:
            # log.debug("update_server() insert DB into tb_onebox_sw")
            software_dict['serverseq'] = server_dict['serverseq']

            sw_result, swseq = mydb.new_row("tb_onebox_sw", software_dict, None, add_uuid=False, log=db_debug)

            if sw_result < 0:
                log.warning("update_server error %d %s" % (sw_result, swseq))

        log.debug('(update_server_oba_arm) software update success!')

    if network_list:
        where_ = {'serverseq': server_dict['serverseq']}
        deleted, content = mydb.delete_row_by_dict(FROM="tb_onebox_nw", WHERE=where_)
        if deleted < 0:
            log.error("Failed to update One-Box Network Info: %d %s" % (deleted, content))
            return deleted, content

        for new_net in network_list:
            new_net['serverseq'] = server_dict['serverseq']
            result, content = mydb.new_row('tb_onebox_nw', new_net, tenant_id=None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("Failed to update One-Box Networ for %s. Cause: %d %s" % (str(new_net), result, content))

        log.debug('(update_server_oba_arm) network update success!')

    if vnet_dict:
        where_ = {'serverseq': server_dict['serverseq']}
        deleted, content = mydb.delete_row_by_dict(FROM='tb_server_vnet', WHERE=where_)
        if deleted < 0:
            log.warning("Failed to delete old server_vnet: %d %s" % (deleted, content))
        else:
            vnet_dict['serverseq'] = server_dict['serverseq']
            result, content = mydb.new_row('tb_server_vnet', vnet_dict, tenant_id=None, add_uuid=False, log=db_debug)
            if result < 0:
                log.warning("Failed to insert new server_vnet: %d %s" % (result, content))

    return server_result, server_dict['serverseq']


def get_resourcetemplate_nscatalog(nsr_id):

    select_ = ("nscat.resourcetemplate as resourcetemplate",)
    from_ = " tb_nsr as nsr join tb_nscatalog as nscat on nsr.nscatseq=nscat.nscatseq "
    result, content = mydb.get_table(FROM=from_, SELECT=select_, WHERE={"nsr.nsseq":nsr_id})
    if result <= 0:
        return result, content
    return result, content[0]


def get_onebox_hw_serverseq(serverseq):
    result, content = mydb.get_table(FROM='tb_onebox_hw', WHERE={"serverseq":serverseq})

    return result, content


def get_onebox_sw_serverseq(serverseq):
    result, content = mydb.get_table(FROM='tb_onebox_sw', WHERE={"serverseq":serverseq})

    return result, content


# GET PNF UTM 모니터 모델
def get_pnf_montargetcat(get_dict):
    where_ = {}

    if 'targetcode' in get_dict:
        where_['targetcode'] = get_dict.get('targetcode')

    if 'vendorcode' in get_dict:
        where_['vendorcode'] = get_dict.get('vendorcode')

    where_['targettype'] = 'UTM'
    where_['targetmodel'] = 'pv1.0'

    # log.debug('get_pnf_montargetcat : where = %s' %str(where_))

    from_ = "tb_montargetcatalog"
    result, content = mydb.get_table(FROM=from_, WHERE=where_)

    return result, content


# GET PNF UTM 모니터 모델
def get_pnf_montargetcat_2(get_dict):
    where_ = {}

    if 'targetcode' in get_dict:
        where_['targetcode'] = get_dict.get('targetcode')

    if 'vendorcode' in get_dict:
        where_['vendorcode'] = get_dict.get('vendorcode')

    where_['targettype'] = 'UTM'
    where_['targetmodel'] = 'pv1.0'

    # select_ = ('montargetcatseq')
    from_ = "tb_montargetcatalog"
    result, content = mydb.get_table(FROM=from_, WHERE=where_)

    log.debug('tb_montargetcatalog = %s' %str(content))

    where_ = {}
    if 'serverseq' in get_dict:
        where_['serverseq'] = get_dict.get('serverseq')

    for con in content:
        if con['delete_dttm']:
            continue

        where_['montargetcatseq'] = con['montargetcatseq']
        break

    log.debug('get_pnf_montargetcat : where = %s' %str(where_))

    # select_ = ('montargetcatseq')
    from_ = "tb_moniteminstance"
    limit_ = 1
    result, content = mydb.get_table(FROM=from_, WHERE=where_, LIMIT=limit_)

    return result, content

def get_onebox_nw_serverseq(serverseq):
    result, content = mydb.get_table(FROM='tb_onebox_nw', WHERE={"serverseq":serverseq})

    return result, content


def get_server_vnet(serverseq):
    result, content = mydb.get_table(FROM='tb_server_vnet', WHERE={"serverseq":serverseq})
    if result <= 0:
        return result, content
    else:
        return result, content[0]



def update_backup_history(backup_dict, condition = None):
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


def get_server_filters(filter_data=None):
    if 'onebox_type' in filter_data:
        where_ = {'nfsubcategory':filter_data.get('onebox_type')}
    else:
        where_ = {'nfsubcategory': "One-Box"}

    if filter_data:
        if "serverseq" in filter_data:      where_['serverseq'] = filter_data['serverseq']
        if "customerseq" in filter_data:    where_['customerseq'] = filter_data['customerseq']
        if "onebox_id" in filter_data:      where_['onebox_id'] = filter_data['onebox_id']
        if "public_ip" in filter_data:      where_['publicip'] = filter_data['public_ip']
        if "nsseq" in filter_data:          where_['nsseq'] = filter_data['nsseq']
        if "public_mac" in filter_data:     where_['publicmac'] = filter_data['public_mac']

    result, content = mydb.get_table(FROM='tb_server', WHERE=where_)

    if result < 0:
        log.error("get_server error %d %s" % (result, content))

    return result, content


def get_server_filters_wf(filter_data=None):
    # log.debug("filter_data = %s" %str(filter_data))
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

    if filter_data:
        if "serverseq" in filter_data:      where_['serverseq'] = filter_data['serverseq']
        if "customerseq" in filter_data:    where_['customerseq'] = filter_data['customerseq']
        if "onebox_id" in filter_data:      where_['onebox_id'] = filter_data['onebox_id']
        if "public_ip" in filter_data:      where_['publicip'] = filter_data['public_ip']
        if "nsseq" in filter_data:          where_['nsseq'] = filter_data['nsseq']
        if "public_mac" in filter_data:     where_['publicmac'] = filter_data['public_mac']

    result, content = mydb.get_table(FROM='tb_server', WHERE=where_, WHERE_NOT=where_not_)

    if result < 0:
        log.error("get_server error %d %s" % (result, content))

    return result, content

def get_server_id(id):
    if type(id) is int or type(id) is long:
        where_ = {"serverseq":id}
    elif id.isdigit():
        where_ = {"serverseq":id}
    elif unicode(id).isnumeric():
        where_ = {"serverseq": id}
    else:
        where_ = {"servername":id}

    result, content = mydb.get_table(FROM='tb_server', WHERE=where_)

    if result < 0:
        log.error("get_server_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found Server with %s" %str(where_)

    return result, content[0]


def get_nsr_id(id):

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
        select_ = ('v.vduseq as vduseq', 'v.name as name', 'v.uuid as uuid', 'v.vim_name as vim_name', 'v.status as status', 'v.weburl as web_url'
                   , 'v.vdudseq as vdudseq', 'v.reg_dttm as reg_dttm', 'tb_vdud.name as vdud_name', 'v.mgmtip as mgmtip', 'tb_vdud.monitor_target_seq'
                   , 'tb_vdud.vm_access_id as vm_access_id', 'tb_vdud.vm_access_passwd as vm_access_passwd')
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
            r, configs = get_vnfd_vdud_config_only(vm['vdudseq'], 'config')
            if r <= 0:
                log.error("failed to get VNF VDU Config %d %s" % (r, configs))
            vm['configs']=configs

            #VNF Monitor
            r, monitors = get_vnfd_vdud_monitor_only(vm['vdudseq'], 'monitor')
            if r <=0:
                log.error('failed to get VNF VDU Monitor %d %s' %(r, monitors))
            vm['monitors']=monitors

        vnf['vdus'] = vdus

        r, report = get_vnf_report(vnf['nfseq'])
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

        r, action = get_vnf_action(vnf['nfseq'])
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

    return 1, instance_dict


def get_nsr_params(nsr_id, category=None):
    from_ = 'tb_nsr_param'

    if category:
        where_ = {'nsseq': nsr_id, 'category': category}
    else:
        where_ = {'nsseq': nsr_id}

    result, content = mydb.get_table(FROM=from_, WHERE=where_)

    if result < 0:
        log.error("get_nsr_params error %d %s" % (result, content))
    return result, content


def get_vnfd_vdud_config_only(vdud_id, type=None):
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


def get_vnfd_vdud_monitor_only(vdud_id, type=None):
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


# TODO : 사용하는지 확인후 필요없으면 제거
def get_vnf_report(vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfr_report', WHERE={'nfseq': vnf_id})
        if result <= 0:
            log.warning("failed to get report items for VNF Record: %s" %str(vnf_id))
            return -HTTP_Not_Found, []

        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return -HTTP_Internal_Server_Error, "Failed to get VNFR report items"


def get_vnf_action(vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfr_action', WHERE={'nfseq': vnf_id})
        if result <= 0:
            log.warning("failed to get action items for VNF Record: %s" %str(vnf_id))
            return -HTTP_Not_Found, []

        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return -HTTP_Internal_Server_Error, "Failed to get VNFR action items"


def get_onebox_flavor_name(name):
    where_ = {"name":name}

    result, content = mydb.get_table(FROM='tb_onebox_flavor', WHERE=where_)
    if result < 0:
        log.error("get_onebox_flavor_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found One-Box flavor with %s" % str(where_)
    return result, content[0]


def get_nsr_general_info(id):
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


def get_rlt_data(nsseq):
    """
    백업, 복구, vnf업데이트, 준공, 서버정보변경 Agent Call 시
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


def insert_nsr_general_info(nsr_name=None, nsr_description=None, rlt_dict=None, nsr_seq=None):
    # instance_scenarios
    INSERT_={'name': nsr_name,
        'description': nsr_description,
        'nscatseq': rlt_dict['nscatseq'],
        'customerseq': rlt_dict['customerseq'],
        'vimseq': rlt_dict['vimseq']
    }

    if rlt_dict['status'] is not None:
        INSERT_['status'] = rlt_dict['status']
        INSERT_['status_description'] = "Provisioning in progress"

    if rlt_dict['org_name']:
        INSERT_['orgnamescode'] = rlt_dict['org_name']

    INSERT_['modify_dttm'] = datetime.datetime.now()

    if nsr_seq:
        INSERT_['nsseq'] = nsr_seq
        result, nsr_id = mydb.new_row_seq('tb_nsr', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)
        if result < 0:
            pass
        else:
            nsr_id = nsr_seq
    else:
        result, nsr_id = mydb.new_row('tb_nsr', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)

    if result < 0:
        log.error("insert_nsr_general_info() Error inserting at table tb_nsrs: %s" % str(nsr_id))
    return result, nsr_id


def insert_nsr_as_a_whole(nsr_name, nsr_description, nsrDict):
    # instance_scenarios
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
            where_ = {'nsseq': instance_id}
            result, update_content = mydb.update_rows('tb_nsr', instanceDict, where_)
        else:
            result, instance_id = mydb.new_row('tb_nsr', instanceDict, None, False, db_debug)

        if result < 0:
            log.error('insert_nsr_as_a_whole Error inserting at table tb_nsr: %s' % str(instance_id))
            return result, instance_id
    except KeyError as e:
        log.exception("Error while creating a NSR. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while creating a NSR, KeyError " + str(e)

    nsrDict['nsseq'] = instance_id

    # instance_vnfs
    for vnf in nsrDict['vnfs']:
        vm_configs_json = json.dumps("{}", indent=4)
        for vm in vnf['vdus']:
            if 'configs' in vm:
                vm_configs = vm['configs']
                vm_configs_json = json.dumps(vm_configs, indent=4)
                break

        INSERT_ = {'nsseq': instance_id, 'nfcatseq': vnf['nfcatseq'], 'status': vnf['status'], 'name': vnf['name'], 'configsettings': vm_configs_json
            , 'description': vnf['description'], 'weburl': vnf.get('weburl', "None"), 'license': vnf.get('license', 'None')
            , 'webaccount': vnf.get('webaccount', "-")}

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
            result, imgs = get_vnfd_vdu_image({"name": vnf_image_name})
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

        r, instance_vnf_id = mydb.new_row('tb_nfr', INSERT_, None, False, db_debug)
        if r < 0:
            log.error('insert_nsr_as_a_whole() Error inserting at table tb_nfr: ' + instance_vnf_id)
            return r, instance_vnf_id
        vnf['nfseq'] = instance_vnf_id

        # instance_vms
        for vm in vnf['vdus']:
            INSERT_ = {'name': vm.get('name'), 'uuid': vm.get('uuid'), 'vim_name': vm.get('vim_name'),
                       'nfseq': instance_vnf_id, 'vdudseq': vm.get('vdudseq'), 'weburl': vm.get('weburl', "None")}
            INSERT_['mgmtip'] = vm.get('mgmtip')
            INSERT_['vm_access_id'] = vm.get("vm_access_id")
            INSERT_['vm_access_passwd'] = vm.get("vm_access_passwd")
            if 'orgnamescode' in vnf:
                INSERT_['orgnamescode'] = vm.get('orgnamescode')
            if 'status' in vm:
                INSERT_['status'] = vm.get('status')
            INSERT_['modify_dttm'] = datetime.datetime.now()
            r, instance_vm_id = mydb.new_row('tb_vdu', INSERT_, None, False, db_debug)
            if r < 0:
                log.error('insert_nsr_as_a_whole() Error inserting at table tb_vdu: ' + instance_vm_id)
                return r, instance_vm_id
            vm['vduseq'] = instance_vm_id

            # cp
            if 'cps' in vm:
                for cp in vm['cps']:
                    INSERT_ = {'name': cp.get('name'), 'uuid': cp.get('uuid'), 'vim_name': cp.get('vim_name'), 'vduseq': instance_vm_id, 'cpdseq': cp.get('cpdseq'), 'ip': cp.get('ip')}
                    log.debug("[HJC] DB Insert - CP: %s" % str(INSERT_))

                    INSERT_['modify_dttm'] = datetime.datetime.now()
                    r, instance_cp_id = mydb.new_row('tb_cp', INSERT_, None, False, db_debug)
                    if r < 0:
                        log.warning('insert_nsr_as_a_whole() Error failed to insert CP Record into tb_cp %d %s' % (r, instance_cp_id))
                    cp['cpseq'] = instance_cp_id

        if 'ui_action' in vnf:
            for action in vnf['ui_action']:
                INSERT_ = {'nfseq': vnf['nfseq'], 'name': action['name'], 'display_name': action['display_name'], 'api_resource': action['api_resource'],
                           'api_body_format': action['api_body_format'], 'api_body_param': action['api_body_param']}
                log.debug("[HJC] UI Action DB Insert: %s" % str(INSERT_))
                r, vnf_action_id = mydb.new_row('tb_nfr_action', INSERT_, None, False, db_debug)
                if r < 0:
                    log.warning("failed to insert nsr vnf action items: %d %s" % (r, vnf_action_id))

        if 'report' in vnf:
            for report in vnf['report']:
                INSERT_ = {'nfseq': vnf['nfseq'], 'name': report['name'], 'display_name': report['display_name'], 'data_provider': report['data_provider'],
                           'value': report.get('value')}
                log.debug("[HJC] UI Report DB Insert: %s" % str(INSERT_))
                r, vnf_report_id = mydb.new_row('tb_nfr_report', INSERT_, None, False, db_debug)
                if r < 0:
                    log.warning("failed to insert nsr vnf report items: %d %s" % (r, vnf_report_id))

    return result, instance_id


def get_vnfd_vdu_image(image_dict):

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


def insert_nfr_general_info(name, rlt_dict, nsr_seq, nfr_seq=None):
    # instance_scenarios
    INSERT_ = {
        'nsseq':nsr_seq,
        'name':name,
        'action':'BE',
        'license':'None'
    }

    log.debug('[PNF DB] insert : %s' % str(INSERT_))

    if 'status' in rlt_dict:
        INSERT_['status'] = rlt_dict['status']

    if 'org_name' in rlt_dict:
        INSERT_['orgnamescode'] = rlt_dict['org_name']

    INSERT_['modify_dttm'] = datetime.datetime.now()
    INSERT_['service_start_dttm'] = datetime.datetime.now()
    INSERT_['service_end_dttm'] = datetime.datetime.now()

    if nfr_seq:
        INSERT_['nfseq'] = nfr_seq
        result, nfr_id = mydb.new_row_seq('tb_nfr', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)
        if result < 0:
            pass
        else:
            nfr_id = nfr_seq
    else:
        result, nfr_id = mydb.new_row('tb_nfr', INSERT_, tenant_id=None, add_uuid=False, log=db_debug)

    if result < 0:
        log.error("insert_nfr_general_info() Error inserting at table tb_nfrs: %s" % str(nfr_id))
    return result, nfr_id


def update_nsr(instance_dict):
    if 'nsseq' not in instance_dict:
        return -HTTP_Not_Found, "No target seq in the request"

    UPDATE_ = {}
    if "status" in instance_dict:
        UPDATE_["status"] = instance_dict["status"]
    if "status_description" in instance_dict:
        UPDATE_["status_description"] = instance_dict["status_description"]
    if "uuid" in instance_dict:
        UPDATE_["uuid"] = instance_dict["uuid"]
    if "action" in instance_dict:
        UPDATE_["action"] = instance_dict["action"]

    result = -HTTP_Not_Found
    if len(UPDATE_) > 0:
        WHERE_ = {'nsseq': instance_dict['nsseq']}

        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_nsr', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nsr Error ' + content + ' updating table tb_nsr: ' + str(instance_dict['nsseq']))
    return result, instance_dict['nsseq']


def update_nsr_vnf(vnf_dict):
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


def update_nfr(instance_dict):
    if 'nfseq' not in instance_dict:
        return -HTTP_Not_Found, "No target seq in the request"

    UPDATE_ = {}
    if "status" in instance_dict:
        UPDATE_["status"] = instance_dict["status"]
    if "action" in instance_dict:
        UPDATE_["action"] = instance_dict["action"]

    result = -HTTP_Not_Found
    if len(UPDATE_) > 0:
        WHERE_ = {'nfseq': instance_dict['nfseq']}

        UPDATE_['modify_dttm'] = datetime.datetime.now()
        result, content = mydb.update_rows('tb_nfr', UPDATE_, WHERE_)
        if result < 0:
            log.error('update_nfr Error ' + content + ' updating table tb_nfr: ' + str(instance_dict['nfseq']))
    return result, instance_dict['nfseq']


def insert_action_history(action_dict):
    try:
        result, history_id = mydb.new_row('tb_action_history', action_dict, None, False, db_debug)
        if result < 0:
            log.warning('insert_action_history() Error inserting at table tb_action_history: ' + history_id)
            pass
    except KeyError as e:
        log.exception("Error while inserting action history into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while inserting action history into DB. KeyError: " + str(e)

    return result, history_id


def insert_backup_history(backup_dict):
    try:
        insert_ = {'serverseq': backup_dict['serverseq'], 'creator': backup_dict['creator'], 'trigger_type': backup_dict.get('trigger_type', "manual")}

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


def get_backup_history_id(condition):
    if 'ood_all' in condition:
        if 'ood_flag' in condition:
            del condition['ood_flag']
    else:
        condition['ood_flag'] = False
    result, content = get_backup_history(condition)

    log.debug("[*******HJC**********] %d, %s" % (result, str(content)))

    if result < 0:
        log.error("get_backup_history_id() failed to get backup history for %s" % str(condition))
        return result, content
    elif result == 0:
        log.error("get_backup_history_id() No backup history found for %s" % str(condition))
        return result, content

    return result, content[0]


def get_backup_history(condition):
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

        log.debug("get_backup_history() where_ = %s" % str(where_))
        result, content = mydb.get_table(FROM='tb_backup_history', ORDER='reg_dttm DESC', WHERE=where_)
        if result < 0:
            log.error("get_backup_history() failed to get backup history for %s" % str(where_))
    except KeyError as e:
        log.exception("Error while getting backup history into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while getting backup history into DB. KeyError: " + str(e)

    return result, content


def get_backup_history_lastone(condition):
    condition['ood_flag'] = False
    result, content = get_backup_history(condition)

    log.debug("[*******HJC**********] %d, %s" % (result, str(content)))

    if result < 0:
        log.error("get_backup_history_lastone() failed to get backup history for %s" % str(condition))
        return result, content
    elif result == 0:
        log.error("get_backup_history_lastone() No backup history found for %s" % str(condition))
        return result, content

    return result, content[0]


def get_customer_id(id):
    if type(id) is int or type(id) is long:
        where_ = {"customerseq": id}
    elif id.isdigit():
        where_ = {"customerseq": id}
    else:
        where_ = {"customername": id}

    result, content = mydb.get_table(FROM='tb_customer', WHERE=where_)
    if result < 0:
        log.error("get_customer_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return result, "Not found Customer with %s" % (str(where_))

    # TODO: use detailaddr rather than addr
    content[0]['addr'] = content[0]['detailaddr']

    return result, content[0]


def get_customer_ename(ename):
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

def insert_customer(data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_customer", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_customer error %d %s" % (result, content))
    return result, content

def insert_user_mp_customer(customerseq):

    result, user_list = get_user_list([])

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


def get_user_list(qs=None):
    if qs:
        select_, where_, limit_ = filter_query_string(qs, None, ('userid', 'username', 'role_id', 'reg_dttm', 'modify_dttm'))
    else:
        select_ = ('userid', 'username', 'role_id', 'reg_dttm', 'modify_dttm')
        where_ = {}
        limit_ = 100

    result, content = mydb.get_table(FROM='tb_user', SELECT=select_, WHERE=where_, LIMIT=limit_)
    if result < 0:
        log.debug("get_user_list error %d %s" % (result, content))
    return result, content

def get_customeroffice_ofcustomer(customerseq):
    where_ = {"customerseq": customerseq}

    result, content = mydb.get_table(FROM='tb_customer_office', WHERE=where_)
    if result < 0:
        log.error("get_customeroffice_ofcustomer error %d %s" % (result, content))
    elif result == 0:
        return result, "Not found Customer Office with %s" %(str(where_))

    return result, content

def insert_customeroffice(data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_customer_office", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_customeroffice error %d %s" % (result, content))
    return result, content

def get_onebox_line_ofonebox(serverseq):
    where_ = {"serverseq": serverseq}

    result, content = mydb.get_table(FROM='tb_onebox_line', WHERE=where_)
    if result < 0:
        log.error("get_onebox_line_ofonebox error %d %s" % (result, content))
    elif result == 0:
        return result, "Not found One-Box Network Line with %s" %(str(where_))

    return result, content


def get_vim_serverseq(serverseq):
    result, content = mydb.get_table(FROM='tb_vim', WHERE={"serverseq": serverseq})

    return result, content


def get_vim_tenant_id(vim_tenant_id=None, vim_tenant_name=None, vim_id=None):
    where_={"vimseq": vim_id}
    if vim_tenant_id is not None:
        where_["uuid"] = vim_tenant_id
    if vim_tenant_name is not None:
        where_["name"] = vim_tenant_name
    result, content = mydb.get_table(FROM='tb_vim_tenant', WHERE=where_)
    if result < 0:
        log.error("get_vim_tenant_id error %d %s" % (result, content))
    return result, content


def insert_onebox_line(data):
    data['modify_dttm']=datetime.datetime.now()
    result, content = mydb.new_row("tb_onebox_line", data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_onebox_line error %d %s" % (result, content))
    return result, content


def get_memo_info(cond_dict):
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


def insert_memo(data_dict):
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


def update_memo(data_dict):
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


def get_nsd_id(id, vim_id=None):
    if type(id) is int or type(id) is long:
        where_ = {'nscatseq': id}
    elif id.isdigit():
        where_ = {'nscatseq': id}
    else:
        where_ = {'name': id}

    result, content = mydb.get_table(FROM='tb_nscatalog', WHERE=where_)
    if result < 0 or result > 1:
        log.error("get_nsd_id error %d %s" % (result, content))
        return result, content
    elif result == 0:
        log.error("get_nsd_id error No NSD found %d %s" % (result, content))
        return -HTTP_Bad_Request, "No NSD Found"

    nsd_dict = content[0]

    # Get VNF info including vdu info tb_nfconstituents
    r, vnfs = mydb.get_table(FROM='tb_nfconstituent', SELECT=('name', 'vnfd_name', 'vnfd_version', 'nscatseq', 'nfcatseq', 'deployorder', 'graph'), ORDER='deployorder',
                             WHERE={'nscatseq': nsd_dict['nscatseq']})
    if r < 0:
        log.error("get_nsd_id error failed to get VNFDs included by NS %d %s" % (r, vnfs))
        return r, vnfs
    elif r == 0:
        # log.error("get get_nsd_id error No VNF Found %d %s" % (r,vnfs))
        # return -HTTP_Internal_Server_Error, "No VNF Found for the NSD"
        nsd_dict['vnfs'] = None
    else:
        nsd_dict['vnfs'] = vnfs

        for vnf in nsd_dict['vnfs']:
            # template_type & template
            r, general_data = get_vnfd_general_info(vnf['nfcatseq'])
            if r < 0:
                log.error("get_nsd_id error failed to get VNF %d %s" % (r, general_data))
                return -HTTP_Internal_Server_Error, general_data
            elif r == 0:
                log.error("get_nsd_id error failed to get VNF %d %s" % (r, general_data))
                return -HTTP_Not_Found, general_data

            vnf['resource_template_type'] = general_data['resourcetemplatetype']
            # vnf['resource_template']=general_data['resourcetemplate']
            vnf['vnfd_name'] = general_data['name']
            vnf['description'] = general_data['description']
            vnf['virtualyn'] = general_data['virtualyn']
            vnf['nfmaincategory'] = general_data['nfmaincategory']
            vnf['nfsubcategory'] = general_data['nfsubcategory']
            vnf['vendorcode'] = general_data['vendorcode']
            vnf['version'] = general_data['version']
            vnf['status'] = general_data['status']
            vnf['license_name'] = general_data['license_name']
            # vnf['nfcatseq'] = vnf['nfcatseq']
            vnf['display_name'] = vnf['name'] + " (ver." + str(vnf['version']) + ")"

            # vduds
            r, vdus = get_vnfd_vdud_only(vnf['nfcatseq'])
            if r <= 0:
                log.error("get_nsd_id error failed to get VNF VDUs %d %s" % (r, vdus))
                pass

            for vdud in vdus:
                af.convert_datetime2str_psycopg2(vdud)
                vdud['name'] = vdud['name'].replace(vnf['vnfd_name'], vnf['name'])
                if vim_id is not None:
                    r, images = get_vim_images(vim_id)
                    if r <= 0:
                        log.warning("get_nsd_id No VIM Image found %d %s" % (r, vdus))
                    else:
                        vdud['vim_image_id'] = images[0]['uuid']
                    # TODO: flavor
                    # self.cur.execute("SELECT vim_flavor_id FROM tb_vim_flavors WHERE flavor_id='%s' AND vim_id='%s'" %(vdud['flavor_id'],vim_id))
                    # if self.cur.rowcount==1:
                    #    vim_flavor_dict = self.cur.fetchone()
                    #    vdud['vim_flavor_id']=vim_flavor_dict['vim_id']

                # vdud cpds
                r, cpds = get_vnfd_cpd_only(vdud['vdudseq'])
                if r <= 0:
                    # log.warning("get_nsd_id NO VNF VDU CP Found %d %s" %(r, cpds))
                    pass
                else:
                    for cpd in cpds:
                        af.convert_datetime2str_psycopg2(cpd)
                        cpd['name'] = cpd['name'].replace(vnf['vnfd_name'], vnf['name'])
                    vdud['cps'] = cpds

                # vnf configs
                r, configs = get_vnfd_vdud_config_only(vdud['vdudseq'], 'config')
                if r <= 0:
                    # log.warning("get_nsd_id No VNF VDU Config found %d %s" % (r, configs))
                    pass
                else:
                    for config in configs:
                        for script in config['scripts']:
                            if script['paramorder'] is not None: script['paramorder'] = script['paramorder'].replace(vnf['vnfd_name'], vnf['name'])
                            if script['cookiedata'] is not None: script['cookiedata'] = script['cookiedata'].replace(vnf['vnfd_name'], vnf['name'])
                            if script['requestheaders_args'] is not None: script['requestheaders_args'] = script['requestheaders_args'].replace(vnf['vnfd_name'],
                                                                                                                                                vnf['name'])
                            if script['body_args'] is not None: script['body_args'] = script['body_args'].replace(vnf['vnfd_name'], vnf['name'])
                    vdud['configs'] = configs

                # vdud_weburl
                r, weburl = get_vnfd_vdud_weburl_only(vdud['vdudseq'])
                if r <= 0:
                    log.warning("get_nsd_id No VNF VDU Web URL found %d %s" % (r, weburl))
                    pass
                else:
                    if weburl[0]['ip_addr'] is not None:
                        weburl[0]['ip_addr'] = weburl[0]['ip_addr'].replace(vnf['vnfd_name'], vnf['name'])
                    if weburl[0]['resource'] is not None:
                        weburl[0]['resource'] = weburl[0]['resource'].replace(vnf['vnfd_name'], vnf['name'])
                    vdud['web_url'] = weburl[0]

                # vnf monitor
                r, monitors = get_vnfd_vdud_monitor_only(vdud['vdudseq'], 'monitor')
                if r <= 0:
                    # log.warning("get_nsd_id No VNF VDU Monitor found %d %s" % (r, monitors))
                    pass
                else:
                    vdud['monitors'] = monitors
            vnf['vdus'] = vdus

            r, report_list = get_vnfd_report(vnf['nfcatseq'])
            if r < 0:
                log.warning("[HJC] Failed to get Report Items from VNFD: %d %s" % (r, report_list))
            elif r > 0:
                vnf['report'] = report_list

            r, action_list = get_vnfd_action(vnf['nfcatseq'])
            if r < 0:
                log.warning("[HJC] Failed to get Action Items from VNFD: %d %s" % (r, action_list))
            elif r > 0:
                vnf['ui_action'] = action_list

                # Get VLD from tb_vld and cpds
    try:
        cpd_r, cpds = get_nsd_cpd_only(nsd_dict['nscatseq'])
        if cpd_r < 0:
            log.warning("failed to get NSD-CPDs: %d %s" % (cpd_r, str(cpds)))
        else:
            nsd_dict['cpds'] = cpds

        r, vlds = get_nsd_vld_only(nsd_dict['nscatseq'])
        if r <= 0:
            pass
        else:
            for vld in vlds:
                af.convert_datetime2str_psycopg2(vld)
                cp_r, cpds = get_nsd_vld_cp_only(vld['vldseq'])
                if cp_r < 0:
                    log.warning("failed to get VLD-CPs: %d %s" % (cp_r, str(cpds)))
                else:
                    vld['connection_points'] = cpds
            nsd_dict['vls'] = vlds

        # Get parameter info from tb_nscatalogs_params
        r, ns_params = get_nsd_param_only(nsd_dict['nscatseq'])
        if r <= 0:
            # log.warning("get_nsd_id No NS Parameters found %d %s" % (r, ns_params))
            pass
        nsd_dict['parameters'] = ns_params

        af.convert_datetime2str_psycopg2(nsd_dict)
        af.convert_str2boolean(nsd_dict, ('publicyn', 'builtinyn', 'multipointyn', 'externalyn', 'dhcpyn'))
    except Exception, e:
        log.exception("Exception: %s" % str(e))

    return 1, nsd_dict


def get_vnfd_general_info(vnfd):
    where_ = {"nfcatseq": vnfd}

    result, content = mydb.get_table(FROM='tb_nfcatalog', WHERE=where_)
    if result < 0:
        log.error("get_vnfd_general_info error %d %s" % (result, content))
        return result, content
    elif result == 0:
        return -HTTP_Not_Found, "Not found vnfd with %s = %s" % ("nfcatseq", vnfd)
    return result, content[0]


def get_vnfd_vdud_only(vnf_id):
    result, content = mydb.get_table(FROM='tb_vdud', ORDER='deployorder', WHERE={'nfcatseq':vnf_id})
    if result < 0:
        log.error("get_vnfd_vdud_only error %d %s" % (result, content))
    return result, content


def get_vim_images(vim_id=None):
    '''get images in the VIM, can use both uuid or name'''
    where_ = {}
    if vim_id:
        where_['vimseq'] = vim_id
    # if vdud_image_id: where_['imageseq'] = vdud_image_id

    result, content = mydb.get_table(FROM="tb_vim_image", WHERE=where_)

    if result < 0:
        log.error("get_vim_images error %d %s" % (result, content))

    return result, content


def get_vnfd_cpd_only(vdud_id):
    result, content = mydb.get_table(FROM='tb_cpd', WHERE={'vdudseq':vdud_id})
    if result < 0:
        log.error("get_vnfd_cpd_only error %d %s" %(result, content))
    return result, content


def get_vnfd_vdud_weburl_only(vdud_id):
    where_ = {'vdudseq': vdud_id}

    result, content = mydb.get_table(FROM='tb_vdud_weburl', WHERE=where_)
    if result <= 0:
        log.error("get_vnfd_vdud_weburl_only %d %s" % (result, content))

    return result, content


def get_vnfd_report(vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfcatalog_report', WHERE={'nfcatseq': vnf_id})
        if result <= 0:
            log.warning("failed to get report items for VNF: %s" % str(vnf_id))
            return -HTTP_Not_Found, []

        return result, content
    except Exception, e:
        log.exception("Exception: %s" % str(e))

    return -HTTP_Internal_Server_Error, "Failed to get VNFD report items"


def get_vnfd_action(vnf_id):
    try:
        result, content = mydb.get_table(FROM='tb_nfcatalog_action', WHERE={'nfcatseq': vnf_id})
        if result <= 0:
            log.warning("failed to get action items for VNF: %s" % str(vnf_id))
            return -HTTP_Not_Found, []

        return result, content
    except Exception, e:
        log.exception("Exception: %s" % str(e))

    return -HTTP_Internal_Server_Error, "Failed to get VNFD action items"


def get_nsd_cpd_only(nsd_id):
    result, content = mydb.get_table(FROM='tb_nscatalog_cpd', WHERE={'nscatseq':nsd_id})
    if result < 0:
        log.error("get_nsd_cpd_only error %d %s" %(result, content))
    return result, content


def get_nsd_vld_only(nsd_id):
    result, content = mydb.get_table(FROM='tb_vld', WHERE={'nscatseq':nsd_id})
    if result < 0:
        log.error("get_nsd_vld_only error %d %s" %(result, content))
    return result, content


def get_nsd_vld_cp_only(vld_id):
    result, content = mydb.get_table(FROM='tb_vld_cp', WHERE={'vldseq':vld_id})
    if result < 0:
        log.error("get_nsd_vld_cp_only error %d %s" %(result, content))
    return result, content


def get_nsd_param_only(nsd_id):
    result, content = mydb.get_table(FROM='tb_nscatalog_param', WHERE={'nscatseq': nsd_id})
    if result < 0:
        log.error("get_nsd_param_only() No NS Parameters found %d %s" % (result, content))

    if result == 0:
        content = []

    return result, content


def get_license_pool(condition={}):
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

        log.debug("get_license_pool() where_ = %s" % str(where_))
        result, content = mydb.get_table(FROM='tb_license_pool', ORDER='reg_dttm DESC', WHERE=where_)
        if result < 0:
            log.error("get_license_pool() failed to get license pool data for %s" % str(where_))
    except KeyError as e:
        log.exception("Error while getting license pool data from DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while getting license pool data from DB. KeyError: " + str(e)

    return result, content


def update_license_pool(license_dict):
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

        update_['modify_dttm'] = datetime.datetime.now()

        result, content = mydb.update_rows('tb_license_pool', update_, where_)
        if result < 0:
            log.error('update_license_pool Error: updating table tb_license_pool: %d %s' % (result, content))

        return result, ret_value

    except KeyError as e:
        log.exception("Error while updating license pool data into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while updating license pool data into DB. KeyError: " + str(e)


def insert_nsr_params(nsr_id, params):
    try:
        for param in params:
            INSERT_ = {'nsseq': nsr_id, 'name': param.get('name'), 'type': param.get('type'), 'description': param.get('description'), 'category': param.get('category'),
                       'value': param.get('value'), 'ownername': param.get('ownername')}

            # if len(str(param['value'])) > 28:
            #     log.debug("___________@@@@___________ insert_nsr_params ERROR : %s " % param)
            r, param_id = mydb.new_row('tb_nsr_param', INSERT_, None, False, db_debug)
            if r < 0:
                log.warning('insert_nsr_params() failed to insert at table tb_nsr_param: ' + param_id)
                pass
    except KeyError as e:
        log.exception("Error while inserting params into DB. KeyError: " + str(e))
        return -HTTP_Internal_Server_Error, "Error while inserting params into DB. KeyError: " + str(e)

    return 200, nsr_id


def get_server_account(serverseq):
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


def get_server_account_use(where_):
    try:
        result, content = mydb.get_table(FROM='tb_server_account_use', WHERE=where_)
        if result <= 0:
            log.error("Failed to get server_account_use data, where = %s" % str(where_))
            return result, content

        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))

    return -HTTP_Internal_Server_Error, "Failed to get server_account_use data"


def delete_server_account_use(accountuseseq):
    try:
        result, content = mydb.delete_row_seq("tb_server_account_use", "accountuseseq", accountuseseq, None, db_debug)
        if result < 0:
            log.error("delete_server_account_use error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : delete server account use - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : delete server account use - %s" %str(e)


def insert_server_account_use(data):
    try:
        result, content = mydb.new_row("tb_server_account_use", data, None, add_uuid=False, log=db_debug)
        if result < 0:
            log.error("tb_server_account_use error %d %s" % (result, content))
        return result, content
    except Exception, e:
        log.exception("Error : insert tb_server_account_use - %s" %str(e))
        return -HTTP_Internal_Server_Error, "Error : insert tb_server_account_use - %s" %str(e)


def delete_nsr(id):
    # instance table
    # if tenant_id is not None: where_['r.orch_tenant_id']=tenant_id
    where_ = {'nsseq': id}
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
        log.error("delete_nsr error %d %s" % (result, content))
    return result, content


def insert_table_data(tbname, data):
    if tbname != "tb_mms_send":
        data['modify_dttm'] = datetime.datetime.now()

    result, content = mydb.new_row(tbname, data, None, add_uuid=False, log=db_debug)
    if result < 0:
        log.error("insert_%s error %d %s" % (tbname, result, content))
    return result, content


def update_table_data(tbname, data, where_):
    if tbname != "tb_mms_send":
        data['modify_dttm'] = datetime.datetime.now()

    result, content = mydb.update_rows(tbname, data, where_)
    if result < 0:
        log.error("update_%s error %d %s" % (tbname, result, content))
        return result, content

    return result, content

def update_table_data_free(sql):
    result, content = mydb.update_rows(table=sql, UPDATE=None, WHERE=None, log=False, _free=True)
    if result < 0:
        log.error("%s %d %s" % (sql, result, content))
        return result, content

    return result, content


def get_table_data(tbname, select=None, where={}):
    if select is None:
        result, content = mydb.get_table(FROM=tbname, WHERE=where)
    else:
        result, content = mydb.get_table(FROM=tbname, SELECT=(select,), WHERE=where)

    if result <= 0:
        log.error("get_table_data() Not found Command Reservation %d %s" % (result, content))

    return result, content


def delete_table_data(tbname, del_column, sac_seq):
    result, content = mydb.delete_row_seq(tbname, del_column, sac_seq, None, db_debug)
    if result < 0:
        log.error("delete_table_data : %s error %d %s" % (tbname, result, content))
    return result, content


##################      VNFD 관련     ###############################################################################
# def get_vnfd_general_info_with_name(mydb, vnfd):
#     if type(vnfd) == str:
#         log.debug("[HJC] str-type vnfd = %s" % vnfd)
#         if vnfd.find("_ver") > 0:
#             vnfd_name = vnfd.split("_ver")[0]
#             vnfd_version = vnfd.split("_ver")[1]
#             # log.debug("vnfd name: %s, vnfd_version: %s" %(vnfd_name, vnfd_version))
#             where_ = {"name": vnfd_name, "version": vnfd_version}
#         else:
#             where_ = {"name": vnfd}
#     elif type(vnfd) == dict:
#         log.debug("[HJC] dict-type vnfd = %s" % str(vnfd))
#         where_ = {"name": vnfd.get('vnfd_name', "NotGiven"), "version": vnfd.get('vnfd_version', 1)}
#         log.debug("[HJC] where_ = %s" % str(where_))
#     else:
#         return -HTTP_Bad_Request, "Invalid VNFD Info: %s" % str(vnfd)
#
#     result, content = mydb.get_table(FROM='tb_nfcatalog', WHERE=where_)
#     if result < 0:
#         log.error("get_vnfd_general_info error %d %s" % (result, content))
#         return result, content
#     elif result == 0:
#         return result, "Not found vnfd with %s" % str(where_)
#
#     content[0]['vnfd_name'] = content[0]['name']
#     p_result, p_content = get_vnfd_parmeters(mydb, content[0])
#     if p_result < 0:
#         log.error("failed to get VNFD Parameters %d %s" % (p_result, p_content))
#         return p_result, p_content
#
#     display_params = []
#     for param in p_content:
#         param_name = param.get('name')
#         if param_name is None:
#             continue
#         if param_name.find('OUT_') >= 0:
#             continue
#         if param_name.find('IPARM_') >= 0:
#             continue
#         add_param = True
#         for dp in display_params:
#             if dp['name'] == param_name:
#                 add_param = False
#                 break
#         if add_param:
#             display_params.append(param)
#
#     content[0]['parameters'] = display_params
#
#     return result, content[0]
#
# def get_vnfd_parmeters(mydb, vnf_db):
#
#     param_list = []
#
#     #3.1 get VNFD Parameter info
#     #3.1.1 get template parameters
#     if vnf_db.get('resourcetemplateseq') is not None:
#         vnf_template_param_r, template_params = get_vnfd_resource_template_item(mydb, vnf_db['resourcetemplateseq'], 'parameter')
#
#         if vnf_template_param_r < 0:
#             log.warning("[Onboarding][NS]      failed to get Resource Template Parameters")
#         elif vnf_template_param_r == 0:
#             log.debug("[Onboarding][NS]      No Template Parameters")
#         else:
#             for param in template_params:
#                 param['category'] = 'vnf_template'
#                 param['ownername'] = vnf_db['name']
#                 param['ownerseq'] = vnf_db['nfcatseq']
#                 param['name'] = param['name'].replace(vnf_db['vnfd_name'], vnf_db['name'])
#                 param_list.append(param)
#
#     #3.1.2-1 get vnf parameters for account
#     vnfd_param_r, vnfd_param_contents = get_vnfd_param_only(mydb, vnf_db['nfcatseq'])
#     if vnfd_param_r < 0:
#         log.warning("[Onboarding][NS]      failed to get VNFD Parameters")
#         pass
#     elif vnfd_param_r == 0:
#         log.debug("[Onboarding][NS]      No VNF Parameters")
#         pass
#
#     for vnfd_param in vnfd_param_contents:
#         vnfd_param['category'] = 'vnf_config'
#         vnfd_param['ownername'] = vnf_db['name']
#         vnfd_param['ownerseq'] = vnf_db['nfcatseq']
#         vnfd_param['name'] = vnfd_param['name'].replace(vnf_db['vnfd_name'], vnf_db['name'])
#         log.debug("[Onboarding][NS] VNFD Param: name = %s" %vnfd_param['name'])
#         param_list.append(vnfd_param)
#
#     #3.1.2 get vnf config parameters
#     vdud_r, vdud_contents = get_vnfd_vdud_only(mydb, vnf_db['nfcatseq'])
#     if vdud_r < 0:
#         log.warning("[Onboarding][NS]      failed to get VNF VDUD")
#         pass
#     elif vdud_r == 0:
#         log.debug("[Onboarding][NS]      No VNF VDUD")
#         pass
#
#     for vdud in vdud_contents:
#         vdud_config_param_r, vdud_config_params = get_vnfd_vdud_config_only(mydb, vdud['vdudseq'], 'parameter')
#         if vdud_config_param_r < 0:
#             log.warning("[Onboarding][NS]      failed to get VNF VDUD Config Parameters")
#         elif vdud_config_param_r == 0:
#             log.debug("[Onboarding][NS]      No VNF VDUD Config Parameters")
#         else:
#             for param in vdud_config_params:
#                 if param['name'].find(vnf_db['vnfd_name']) >= 0:
#                     param['category'] = 'vnf_config'
#                     param['ownername'] = vnf_db['name']
#                     param['ownerseq'] = vnf_db['nfcatseq']
#                     param['name'] = param['name'].replace(vnf_db['vnfd_name'], vnf_db['name'])
#                     param_list.append(param)
#
#     # 3.1.3 TODO vdud_monitor_param
#
#     log.debug("_new_nsd_v1_thread() Parameter list: %s" %str(param_list))
#
#     return 200, param_list
##################      VNFD 관련     ###############################################################################