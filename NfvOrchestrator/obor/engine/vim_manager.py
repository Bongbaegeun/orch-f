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

from utils import auxiliary_functions as af
from db.orch_db import HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Conflict
import db.orch_db_manager as orch_dbm
from connectors import osconnector

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

####################################################    for KT One-Box Service   #############################################
def new_vim(mydb, vim_dict):
    result, vim_id = orch_dbm.insert_vim(mydb, vim_dict)
    if result < 0:
        log.error("failed to insert a DB record for a new VIM:\n"+json.dumps(vim_dict, indent=4))
        return result, vim_id
    
    return 200, vim_id

def delete_vim(mydb, vim):
    #get vim info
    result, vim_dict = orch_dbm.get_vim_id(mydb, vim)
    if result < 0:
        log.error("failed to delete the VIM %s. No DB Record" %vim)
        return result, vim_dict

    result, vim_id = orch_dbm.delete_vim(mydb, vim_dict['vimseq'])
    if result < 0:
        log.error("failed to delete the DB Record for the VIM %s" %vim_dict['vimseq'])
        return result, vim_id
    return 200, vim_id

def associate_vim_with_tenant(mydb, vim, vim_tenant_uuid=None, vim_tenant_name=None, vim_username=None, vim_password=None):
    
    result, vims = get_vim_connector(mydb, vim_id=vim)
    
    if result < 0:
        log.error("failed to associate VIM, %s, to the VIM Tenant. VIM not found" %vim)
        return result, vims
    elif result>1:
        log.error("failed to associate VIM, %s, to the VIM Tenant. More than one VIMs found" %vim)
        return -HTTP_Conflict, "More than one VIMs found, try to identify with uuid"
    
    vimseq=vims.keys()[0]
    myvim=vims[vimseq]
    vim_name=myvim["name"]

    vim_tenant_id_exist_atdb=False
    vim_tenants_dict = {}
    if vim_tenant_uuid!=None or vim_tenant_name!=None:
        result, vim_tenant_content = orch_dbm.get_vim_tenant_id(mydb, vim_tenant_uuid, vim_tenant_name, vimseq)
        if result < 0:
            return result, vim_tenant_content
        elif result>=1:
            vim_tenants_dict = vim_tenant_content[0]
            af.convert_datetime2str_psycopg2(vim_tenants_dict)
            vim_tenant_id_exist_atdb=True
            
    else: #if vim_tenant_uuid==None:
        #create tenant at VIM if not provided
        res, vim_tenant_uuid = myvim.new_tenant(vim_tenant_name, "created by kt nfvorch for VIM "+vim_name)
        if res < 0:
            log.error("failed to create VIM Tenant for VIM: %s" % vim_tenant_uuid)
            return res, vim_tenant_uuid
        vim_tenants_dict["createdyn"]="true"
    
    #fill vim_tenants table
    if not vim_tenant_id_exist_atdb:
        vim_tenants_dict["uuid"]   = vim_tenant_uuid
        vim_tenants_dict["name"] = vim_tenant_name
        vim_tenants_dict["username"]       = vim_username
        vim_tenants_dict["password"]        = vim_password
        vim_tenants_dict["vimseq"]          = vimseq
        res,id_ = orch_dbm.insert_vim_tenant(mydb, vim_tenants_dict)
        af.convert_datetime2str_psycopg2(vim_tenants_dict)
        
        if res<1:
            return -HTTP_Bad_Request, "Not possible to add %s to database tb_vim_tenants table %s " %(vim_tenant_uuid, id_)
        vim_tenants_dict["vimtenantseq"] = id_
        log.debug("Success to attach VIM Tenant to VIM"+json.dumps(vim_tenants_dict, indent=4))
    
    return 200, vimseq

def get_vim_connector(mydb, vim_id=None, vim_name=None):
    '''Obtain a dictionary of VIM (datacenter) classes with some of the input parameters
    return result, content:
        <0, error_text upon error
        NUMBER, dictionary with datacenter_id: vim_class with these keys: 
            'nfvo_tenant_id','datacenter_id','vim_tenant_id','vim_url','vim_url_admin','datacenter_name','type','user','passwd'
    '''
    
    result, content = orch_dbm.get_vim_and_vim_tenant(mydb, vim_id, vim_name)
    if result < 0:
        log.error("failed to get VIM info with vim tenants from DB: %d %s" % (result, content))
        return result, content
    
    vim_dict={}
    for vim in content:
        log.debug("get_vim_connector(): vim info = %s" %(str(vim)))
        extra={'vim_tenant_uuid': vim.get('vim_tenant_uuid')}
        if vim.get('authurl') is None:
            log.debug('vim authurl is None......')
            continue

        if vim["vimtypecode"]=="OpenStack-ANode":
            vim_auth_url = vim['authurl']
            # if vim['authurl'].find("/v3") > 0:
            #     vim_auth_url = vim['authurl'].split('/v3')[0] + "/v2.0"
            #     log.debug("Modified VIM Auth URL = %s" %vim_auth_url)
            # else:
            #     vim_auth_url = vim['authurl']
            #     log.debug("Original VIM Auth URL = %s" %vim_auth_url)
            
            vim_dict[ vim['vimseq'] ] = osconnector.osconnector(
                            uuid=vim['vimseq'], name=vim['name'],
                            tenant=vim.get('vim_tenant_name'), 
                            url=vim_auth_url, url_admin=vim['authurladmin'], 
                            user=vim.get('username'),passwd=vim.get('password'),
                            config=extra
                    )
        else:
            log.error("failed to create VIM Connector of %s" % vim['type'])
            return -HTTP_Internal_Server_Error, "Unknown vim type %s" % vim["type"]

    return len(vim_dict), vim_dict

def deassociate_vim_from_tenant(mydb, vim, vim_tenant_id=None):
    
    result, vims = get_vim_connector(mydb, vim_id=vim)
    
    if result < 0:
        log.error("nfvo.deassociate_vim_from_tenant() error. VIM not found")
        return result, vims
    elif result>1:
        log.error("nfvo.deassociate_vim_from_tenant() error. More than one VIM found")
        return -HTTP_Conflict, "More than one VIM found, try to identify with uuid"
    vimseq=vims.keys()[0]
    myvim=vims[vimseq]
    
    result, vims_tenants_list = orch_dbm.get_vim_tenant_list(mydb, vimseq)
    if result < 0:
        log.error("failed to deassociate the VIM Tenants from the VIM. Failed to get VIM Tenants from DB")
        return result, vims_tenants_list

    warning=''
    result, data = orch_dbm.delete_vim_tenant(mydb, vims_tenants_list[0]['vimtenantseq'])
    if result<0:
        pass #the error will be caused because dependencies, vim_tenant can not be deleted
    elif vims_tenants_list[0]['createdyn']=='true':
            #delete tenant at VIM if created by NFVO
            res, vim_tenant_id = myvim.delete_tenant(vims_tenants_list[0]['uuid'])
            if res < 0:
                warning = " Not possible to delete vim_tenant %s from VIM: %s " % (vims_tenants_list[0]['uuid'], vim_tenant_id)
                log.warning(warning)
                
    return 200, "vim %s detached.%s" %(vimseq, warning)

def vim_action(mydb, vim, action_dict):
    result, vims = get_vim_connector(mydb, vim_id=vim)
    if result < 0:
        log.error("failed to vim_action. VIM not found")
        return result, vims
    elif result>1:
        log.error("failed to vim_action. More than one VIMs found")
        return -HTTP_Conflict, "More than one VIMs found, try to identify with uuid"
    vimseq=vims.keys()[0]
    myvim=vims[vimseq]

    if 'net-update' in action_dict:
        #result, content = myvim.get_network_list_v4(filter_dict={'shared': True, 'admin_state_up': True, 'status': 'ACTIVE'})
        result, content = myvim.get_network_list_v4(filter_dict={'admin_state_up': True, 'status': 'ACTIVE'})
        if result < 0:
            log.error("Not possible to get_network_list from VIM: %s " % (content))
            return -HTTP_Internal_Server_Error, content
        #update nets Change from VIM format to NFVO format
        net_list=[]
        for net in content:
            net_nfvo={'vimseq': vimseq}
            net_nfvo['name']       = net['name']
            #net_nfvo['description']= net['description']
            net_nfvo['uuid'] = net['id']
            net_nfvo['type']       = 'e-lan' # TODO: transform OpenStack's type to one of e-lan, e-line, or e-tree
            net_nfvo['sharedyn']     = net['shared']
            net_nfvo['multipointyn'] = False if net_nfvo['type']=='e-line' else True
            net_list.append(net_nfvo)
        result, content = orch_dbm.update_vim_networks(mydb, vim, net_list)
        if result < 0:
            return -HTTP_Internal_Server_Error, content
        log.debug("Inserted %d nets, deleted %d old nets" % (result, content))
                
        return 200, result
    elif 'net-edit' in action_dict:
        net = action_dict['net-edit'].pop('net')
        what = 'vim_net_id' if af.check_valid_uuid(net) else 'name'
        result, content = mydb.update_rows('tb_vim_net', action_dict['net-edit'], 
                                WHERE={'vimseq':vimseq, what: net})
        return result, content
    elif 'net-delete' in action_dict:
        net = action_dict['net-delete'].get('net')
        what = 'vim_net_id' if af.check_valid_uuid(net) else 'name'
        result, content = mydb.delete_row_by_dict(FROM='tb_vim_net', 
                                WHERE={'vimseq':vimseq, what: net})
        return result, content
    elif 'net-create' in action_dict:
        log.debug("net-create IN")
        reqNet = action_dict['net-create']
        if reqNet.get('name') == None or reqNet.get('physical_network') == None:
            return -1, "Error creating network: No Name"
        # create virtual network in VIM
        result, network_id = myvim.new_tenant_network(reqNet.get('name'), reqNet.get('network_type'), reqNet.get('physical_network'), 
                                                      reqNet.get('sharedyn', True), reqNet.get('segmentation'), reqNet.get('cidr'), reqNet.get('dhcp', False))
        if result < 0:
           log.error("Error creating network: %s." %network_id)
           return result, "Error creating network: "+ network_id
        
        # insert new record into DB
        vim_action(mydb, vim, {'net-update': None})
    elif 'image-update' in action_dict:
        result, content = myvim.get_image_list_v4(filter_dict={'status': 'ACTIVE'}) # filter_dict={'admin_state_up': True, 'status': 'ACTIVE'}
        if result < 0:
            log.error("Not possible to get_image_list_v4 from VIM: %s " % content)
            return -HTTP_Internal_Server_Error, content
        #update images Change from VIM format to NFVO format
        image_list=[]
        for image in content:
            image_nfvo={'vimseq': vimseq}
            image_nfvo['uuid'] = image['id']
            image_nfvo['vimimagename'] = image['name']
            image_list.append(image_nfvo)
        
        result, content = orch_dbm.update_vim_images(mydb, vim, image_list)
        if result < 0:
            log.error("Failed to update DB records for VIM images")
            return -HTTP_Internal_Server_Error, content
        
        return 200, result
    elif 'image-delete' in action_dict:
        #TODO
        return -HTTP_Bad_Request, "Not Ready Yet action " + str(action_dict)        
    else:
        return -HTTP_Bad_Request, "Unknown action " + str(action_dict)