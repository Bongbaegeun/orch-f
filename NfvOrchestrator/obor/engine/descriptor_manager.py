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

import datetime
import json
import os
import random
import threading
import time
import paramiko
import yaml
from scp import SCPClient
import sys
import tarfile

import db.orch_db_manager as orch_dbm
from db.orch_db import HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found

from engine.descriptor_status import DescriptorStatus as DSCRTStatus
from engine.vim_manager import get_vim_connector
import common_manager

from utils import auxiliary_functions as af
from utils.config_manager import ConfigManager
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from image_status import ImageStatus
from utils.e2e_logger import e2elogger, CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
from engine.server_status import SRVStatus

global global_config

def _check_vnf_descriptor(mydb, vnf_descriptor):
    global global_config
    #TODO:
    #We should check if the info in external_connections matches with the one in the vnfcs
    #We should check if the info in internal_connections matches with the one in the vnfcs
    #We should check that internal-connections of type "ptp" have only 2 elements
    #We should check if the name exists in the NFVO database (vnfs table)
    #We should check if the path where we should store the YAML file already exists. In that case, we should return error.
    vnf_filename=global_config['vnf_repository'] + "/vnfd/" +vnf_descriptor['vnf']['name'] + ".vnfd"
    if os.path.exists(vnf_filename):
        log.warning("WARNING: The VNF descriptor already exists in the VNF repository")

    #vnfd_name_version = vnf_descriptor['vnf']['name']+"_ver"+str(vnf_descriptor['vnf'].get("version", 0))
    vnfd_info = {"vnfd_name": vnf_descriptor['vnf']['name'], "vnfd_version": vnf_descriptor['vnf'].get("version", 1)}
    result, data = orch_dbm.get_vnfd_general_info_with_name(mydb, vnfd_info)
    if result > 0:
        log.debug("VNFD of %s is already exist." % vnf_descriptor['vnf']['name'])
        return 214, data
    
    return 200, None

# def check_vnf_imagefile(vnf_image_descriptor):
#     filename = vnf_image_descriptor.get('location')
#     if filename != None and os.path.exists(filename):
#         return 200
#     else:
#         return -HTTP_Not_Found

# def generate_action_tid():
#     return datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + str(random.randint(1,99)).zfill(2)

####################################################    for KT One-Box Service   #############################################
def new_nfd(mydb, nf_descriptor, public=True, physical=False, vim=None, vim_tenant=None):
    try:
        log_info_message = "Onboarding VNF Started (%s)" % nf_descriptor['vnf']['name']
        log.info(log_info_message.center(80, '='))

        # Step 1. Check the type of NF Catalog: PNF or VNF
        # TODO
        
        # Step 2. Check the NF descriptor
        vnfd_already_exist = False
        
        log.debug("[Onboarding][VNF] 1. Check the VNF Descriptor")
        result, existing_vnfd = _check_vnf_descriptor(mydb, nf_descriptor)
        if result < 0:
            log.error("[Onboarding][VNF]  : error, %s" %existing_vnfd)
            return result, "VNF de: %s" %existing_vnfd
        if result == 214:
            log.debug("Already Exists")
            vnfd_already_exist = True

        log.debug("[Onboarding][VNF]  1. success")
        
        # Step 3. Check the version and start onboarding
        if nf_descriptor['vnf'].get('descriptor_version', "1.0") == "2.0":
            #return _new_vnfd_v2(mydb, nf_descriptor, public, vim, vim_tenant)
            return -HTTP_Bad_Request, "Descriptor of version2 is Not Supported"
        else:
            if vnfd_already_exist:
                return _update_vnfd_v1(mydb, nf_descriptor, public, vim, vim_tenant, existing_vnfd['nfcatseq'])
            else:
                return _new_vnfd_v1(mydb, nf_descriptor, public, vim, vim_tenant) # KT VNFD # KT VNFD
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "VNFD 등록이 실패하였습니다. 원인: %s" %str(e)


def _update_vnfd_v1(mydb, vnf_descriptor, public, vim, vim_tenant, existing_vnfd_id=None):

    if existing_vnfd_id is None:
        log.error("[Updating][VNFD] failed to find the id of the existing VNFD")
        return -HTTP_Bad_Request, "failed to update VNFD - No VNFD found"
    
    update_dict = {'nfcatseq': existing_vnfd_id}
    
    # Step 2. Review the descriptor and add missing  fields for tb_nfcatalogs DB
    log.debug("[Updating][VNF] 2. Parsing VNF General Info")
    vnf_name = vnf_descriptor['vnf']['name']
    update_dict['display_name'] = vnf_descriptor['vnf'].get("display_name", vnf_name)
    update_dict['vendor'] = vnf_descriptor['vnf'].get("vendor")
    update_dict['description'] = vnf_descriptor['vnf'].get("description", vnf_name)
    update_dict['resource_template_type'] = vnf_descriptor['vnf'].get("resource_template_type", "hot")
    update_dict['resource_template'] = vnf_descriptor['vnf'].get("resource_template","none")
    update_dict['virtual'] = vnf_descriptor['vnf'].get("virtual", True)
    update_dict['public'] = vnf_descriptor['vnf'].get("public", True)
    #update_dict['status'] = DSCRTStatus.CRT_parsing
    
    vnf_category = vnf_descriptor['vnf'].get("class", "Server_One-Box")
    update_dict['nfmaincategory'] = vnf_category.split("_")[0]
    update_dict['nfsubcategory'] = vnf_category.split("_")[1]
    
    result, vnf_id = orch_dbm.update_vnfd(mydb, update_dict)
    if result < 0:
        log.error("[Updating][VNF]  : error, %s" %str(vnf_id))

    return result, str(vnf_id)


def _new_vnfd_v1(mydb, vnf_descriptor, public, vim, vim_tenant):

    # Step 2. Review the descriptor and add missing  fields for tb_nfcatalogs DB
    log.debug("[Onboarding][VNF] 2. Parsing VNF General Info")
    vnf_name = vnf_descriptor['vnf']['name']
    vnf_descriptor['vnf']['display_name'] = vnf_descriptor['vnf'].get('display_name', vnf_name)
    vnf_descriptor['vnf']['description'] = vnf_descriptor['vnf'].get("description", vnf_name)
    vnf_descriptor['vnf']['version'] = vnf_descriptor['vnf'].get("version", 0)
    vnf_descriptor['vnf']['resource_template_type'] = vnf_descriptor['vnf'].get("resource_template_type", "hot")
    vnf_descriptor['vnf']['resource_template'] = vnf_descriptor['vnf'].get("resource_template","none")
    vnf_descriptor['vnf']['virtual'] = vnf_descriptor['vnf'].get("virtual", True)
    vnf_descriptor['vnf']['public'] = vnf_descriptor['vnf'].get("public", True)
    vnf_descriptor['vnf']['status'] = DSCRTStatus.CRT_parsing
    
    vnf_category = vnf_descriptor['vnf'].get("class", "Server_One-Box")
    vnf_descriptor['vnf']['nfmaincategory'] = vnf_category.split("_")[0]
    vnf_descriptor['vnf']['nfsubcategory'] = vnf_category.split("_")[1]

    if not vnf_descriptor['vnf']['public']:
        owners=vnf_descriptor['vnf'].get('owners', [])
        for owner in owners:
            #TODO: Check if valid owner or not
            #TODO: if owner does not exist, remove owner form owners
            log.debug("owner: %s" %str(owner))
        vnf_descriptor['vnf']['owners'] = owners
    
    result, vnf_id = orch_dbm.insert_vnfd_general_info(mydb, vnf_descriptor)
    if result < 0:
        log.error("[Onboarding][VNF]  : error, %s" %str(vnf_id))
        return result, str(vnf_id)

    log.debug("[Onboarding][VNF]  2. success, VNF Descriptor: \n"+json.dumps(vnf_descriptor, indent=4))
    
    use_thread = True
    vnf_descriptor['nfcatseq'] = vnf_id
    
    try:
        th = threading.Thread(target=_new_vnfd_v1_thread, args=(mydb, vnf_descriptor, public, vim, vim_tenant, use_thread))
        th.start()
    except Exception, e:
        error_msg = "failed invoke a Thread for onboarding VNF %s" %vnf_descriptor['vnf']['name']
        log.exception(error_msg)
        use_thread = False
    
    time.sleep(5) # Waiting for DB Update
    
    if use_thread:
        log_info_message = "Onboarding VNF - In Progress by a Thread (%s)" % vnf_descriptor['vnf']['name']
        log.info(log_info_message.center(80, '='))
        return 200, vnf_id
    else:
        return _new_vnfd_v1_thread(mydb, vnf_descriptor, public, vim, vim_tenant, use_thread=False)

def _new_vnfd_v1_thread(mydb,vnf_descriptor,public=True,physical=False,vim=None,vim_tenant=None, use_thread=True):
    global global_config

    try:
        if use_thread:
            log_info_message = "Onboarding VNF - Thread Started (%s)" % vnf_descriptor['vnf']['name']
            log.info(log_info_message.center(80, '='))
        
        # Step 3. Get the URL of the VIM from the orch_tenant and the vim
        log.debug("[Onboarding][VNF] 3. Get VIM of %s" %vim)
        
        result, vims = get_vim_connector(mydb, vim_id=vim) #TODO: result, vims = get_vim_v4(mydb, orch_tenant, vim, None, vim_tenant)
        
        if result < 0:
            log.error("[Onboarding][VNF]  : error, failed to get VIM of %s" %vim)
            #update status
            #vnf_descriptor["status"] = DSCRTStatus.ERR
            #update_result, update_content = orch_dbm.update_vnfd(mydb, vnf_descriptor)
            #return result, vims
            vims = []

        log.debug("[Onboarding][VNF]  3. success")
        
        log.debug("[Onboarding][VNF]  : Processing License")
        license=vnf_descriptor['vnf'].get("license")
        if license is not None:
            if license['type'] == "server" or license['type'] == "key_server":
                if 'server_url' in license and len(license['server_url'])>0:
                    log.debug("there is server_url for license: %s" % license['server_url'])
                else:
                    log.debug("warning no server url for licnese")

            if license.get('name'):
                log.debug("License Name: %s" %license['name'])
                vnf_descriptor['license_name'] = license['name']

        #vnfcItem['licenseseq']=license_id
        log.debug("[Onboarding][VNF]   : skip, TBD")

        # Parsing App ID/Passwd
        # account 정보는 기존 XMS VNF 에서 사용하였으나, 현재는 XMS를 사용하지 않는다. 삭제 예정.
        CONST_ACCOUNT_TYPE_PREDEFINED = "predefined"
        if 'account' in vnf_descriptor['vnf']:
            account_info = vnf_descriptor['vnf']['account']
            log.debug("[Onboarding][VNF] VNF App account info = %s" %str(account_info))
            if account_info.get('type') == CONST_ACCOUNT_TYPE_PREDEFINED:
                vnf_descriptor['vnf']['webaccount_id'] = account_info.get('id')
                vnf_descriptor['vnf']['webaccount_password'] = account_info.get('password')

        # Step 4. Review and parse the HOT template (TODO: General Template Parser)
        log.debug("[Onboarding][VNF] 4. Parsing and Processing VNF Template (HOT)")
        
        if vnf_descriptor['vnf']['resource_template_type'] == "hot":
            res, vnf_template_dict = parse_vnfd_template(mydb, vnf_descriptor['vnf']['name'], vnf_descriptor['vnf']['resource_template'])
            
            if res < 0:
                log.error("[Onboarding][VNF]    : error, %d %s" % (res, vnf_template_dict))
            
            vnf_descriptor['vnf']['resource_template_id'] = vnf_template_dict['resourcetemplate_seq']
            log.debug("[Onboarding][VNF]  4. success, Template UUID: %s" %str(vnf_template_dict['resourcetemplate_seq']))
        else:
            vnf_template_dict = None
            log.debug("[Onboarding][VNF]  4. skip because it belongs to the Other Service System: %s" %vnf_descriptor['vnf']['resource_template_type'])

        # Step 5. Review the descriptor and add missing fields for tb_vduds DB, register image to VIM
        log.debug("[Onboarding][VNF] 5. Parsing and Processing VNF Components")
        res, VNFCDict = parse_vnfd_component(vnf_descriptor['vnf']['VNFC'], vnf_template_dict)
        
        if res < 0:
            log.error("[Onboarding][VNF]  : error, %s" %VNFCDict)

            #update status
            vnf_descriptor["status"] = DSCRTStatus.ERR #hjc
            update_result, update_content = orch_dbm.update_vnfd(mydb, vnf_descriptor)

            #_, message = rollback(mydb, vims, rollback_list)
            #log.debug("[Onboarding][VNF]    rollback list:\n"+json.dumps(rollback_list, indent=4)+"\n      result: "+message)
            return res, VNFCDict

        log.debug("[Onboarding][VNF]  5. success")
        
        # Step 6. DB Insert
        log.debug("[Onboarding][VNF] 6. DB Insert VNF Info (except VNF Template)")
        #update status
        vnf_descriptor["status"] = DSCRTStatus.CRT_processingdb #hjc
        update_result, update_content = orch_dbm.update_vnfd(mydb, vnf_descriptor)

        # log.debug("__________ vnf_descriptor : %s" % vnf_descriptor)
        result, vnf_id = orch_dbm.insert_vnfd_as_a_whole(mydb, vnf_descriptor, VNFCDict)
        
        if result < 0:
            log.error("[Onboarding][VNF]  : error, %s" %str(vnf_id))

            #update status
            vnf_descriptor["status"] = DSCRTStatus.ERR #hjc
            update_result, update_content = orch_dbm.update_vnfd(mydb, vnf_descriptor)

            #_, message = rollback(mydb, vims, rollback_list)
            #log.debug("[Onboarding][VNF]  rollback list:\n"+json.dumps(rollback_list, indent=4)+"\n    result: "+message)
            return result, str(vnf_id)

        # 현재 사용하지 않음. 로직과 테이블은 남겨 놓았으나 데이타없음. ###################################################
        # parsing and saving metadata
        result, content = orch_dbm.insert_vnfd_metadata(mydb, vnf_id, vnf_descriptor['vnf'].get('metadata'))
        if result < 0:
            log.warning("[Onboarding][VNF] failed to db insert VNFD metadata, %s" %str(content))
        
        result, content = orch_dbm.insert_vnfd_report(mydb, vnf_id, vnf_descriptor['vnf'].get('report'))
        if result < 0:
            log.warning("[Onboarding][VNF] failed to db insert report items of VNFD: %d %s" %(result, content))
        
        result, content = orch_dbm.insert_vnfd_action(mydb, vnf_id, vnf_descriptor['vnf'].get('action'))
        if result < 0:
            log.warning("[Onboarding][VNF] failed to db insert action items of VNFD: %d %s" %(result, content))
        # END ###################################################

        log.debug("[Onboarding][VNF]  6. success")

        # Step 7. register VNFD to Orch-M
        vnf_result, vnf = orch_dbm.get_vnfd_id(mydb, vnf_id)
        if vnf_result < 0:
            log.warning("[Onboarding][VNF] failed to get VNF Info. from DB: %d %s" %(vnf_result, vnf))
        else:
            # mtarget_result, mtarget_content = setup_monitor_for_vnfd(mydb, vnf['vnfd'])
            #TODO: valid check of VNFD-Target ID
            for vdud in vnf['vnfd']['VNFC']:
                for vdud_req in vnf_descriptor["vnf"]["VNFC"]:
                    if vdud["name"] == vdud_req["name"]:
                        target_id = vdud_req["monitor"][0]["target_id"]
                        mtarget_result, mtarget_content = _check_monitor_target_seq(target_id)
                        if mtarget_result < 0:
                            log.warning("[Onboarding][VNF] failed to get monitor target seq: %d %s" %(mtarget_result, mtarget_content))
                            return -HTTP_Internal_Server_Error, "failed to get monitor target seq"
                        vdud["monitor_target_seq"] = target_id
                        break

            for vdud in vnf['vnfd']['VNFC']:
                orch_dbm.update_vnfd_vdud(mydb, vdud)
        
        # Step 8. update nfcatalog's status
        vnf_descriptor['nfcatseq'] = vnf_id
        vnf_descriptor["status"] = DSCRTStatus.RDY
        result, update_content = orch_dbm.update_vnfd(mydb, vnf_descriptor)
        
        if use_thread:
            log_info_message = "Onboarding VNF - Thread Finished (%s)" % str(vnf_id)
        else:
            log_info_message = "Onboarding VNF Finished (%s)" % str(vnf_id)
        log.info(log_info_message.center(80, '='))
        
        return 200, vnf_id
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "VNFD 등록이 실패하였습니다. 원인: %s" %str(e)

# def _create_or_use_license(mydb, license, rollback_list=[]):
#     pass

def parse_vnfd_template(mydb, vnf_name, vnf_template_raw):
    vnf_template = {}
    try:
        vnf_template=yaml.load(vnf_template_raw)
    except yaml.YAMLError as exc:
        if hasattr(exc, 'problem_mark'):
            mark = exc.problem_mark
            log.exception("[Onboarding][VNF]  : error, Yaml Data at line %s, column %s." %(mark.line, mark.column+1))
        else:
            log.exception("[Onboarding][VNF]  : Unknown Error with Yaml Data.")
    
    vnf_template['name'] = vnf_name
    vnf_template['version'] = vnf_template['heat_template_version']
    
    af.convert_datetime2str(vnf_template)
    #log.debug("[Onboarding][VNF]  : success to parse VNF Template(HOT): \n"+json.dumps(vnf_template, indent=4))
    
    log.debug("[Onboarding][VNF]  : DB Insert VNF Template(HOT) Data")
    res,content = orch_dbm.insert_vnfd_resource_template(mydb, vnf_template)
    if res>0:
        log.debug("tb_resourcetemplate seq  = %s" % str(content))
        vnf_template['resourcetemplate_seq'] = content
        return 200, vnf_template
    else:
        log.error("failed to db insert tb_resourcetemplate  = " + str(content))
        return res, content

def parse_vnfd_component(vnfc_raw, vnf_resources=None):
    VNFCDict = {}
    try:
        global global_config
        deploy_order = 1
        for vnfc in vnfc_raw:
            vnfcItem = {}
            vnfcItem['name'] = vnfc['name']
            vnfcItem['description'] = vnfc.get("description", vnfc['name'])
            vnfcItem['deploy_order'] = deploy_order
            deploy_order += 1
            
            if 'vm_account' in vnfc:
                vnfcItem['vm_access_id'] = vnfc['vm_account'].get('vm_id')
                vnfcItem['vm_access_passwd'] = vnfc['vm_account'].get('vm_passwd')

            log.debug("[Onboarding][VNF]  : Processing Image")

            if 'image' in vnfc:
                image = vnfc['image']
                vnfcItem["image_metadata"] = image.get("metadata")

            # parse web_url
            web_url_config = vnfc.get('web_url')
            if web_url_config:
                log.debug("Parsing web_url: %s" %str(web_url_config))
                web_url_dict = {}
                web_url_dict['name'] = web_url_config['name']
                web_url_dict['type'] = web_url_config.get('type', "main")
                web_url_dict['protocol'] = web_url_config.get('protocol', "http")
                web_url_dict['ip_addr'] = web_url_config.get('ip_addr', "NotGiven")
                web_url_dict['port'] = web_url_config.get('port', -80)
                web_url_dict['resource'] = web_url_config.get('resource', "NotGiven")
                vnfcItem['web_url'] = web_url_dict
            
            # parse cp
            if vnf_resources != None:
                cpd_list = []
                for resource_key in vnf_resources['resources']:
                    log.debug("CPD: check Resource %s for %s" %(resource_key, vnfcItem['name']))
                    cp = {}
                    if resource_key.find("PORT_") == 0:
                        cp['name'] = resource_key
                        cp['vdud_name'] = vnfcItem['name']
                        log.debug("CPD: add CPD %s for %s" %(cp['name'], cp['vdud_name']))
                        cpd_list.append(cp)

                vnfcItem['cps'] = cpd_list

            log.debug("[Onboarding][VNF]  : Parsing VNF Config and VNF Monitor")
            config = vnfc.get("config")
            if config != None:
                config_order = 1
                for c in config:
                    c['performorder'] = config_order
                    config_order += 1
                    
                    script_list = c.get("scripts")
                    if script_list != None:
                        script_order = 1
                        for s in script_list:
                            s['performorder'] = script_order
                            script_order += 1

                vnfcItem['configs'] = config

            monitor = vnfc.get("monitor")
            if monitor != None:
                vnfcItem['monitors']=monitor

            VNFCDict[vnfc['name']]=vnfcItem

    except (KeyError, TypeError) as e:
        log.exception("[Onboarding][VNF]  : error, " + str(e))
        return -HTTP_Internal_Server_Error, "Error while creating a VNF, Key Error " + str(e)
    
    return 200, VNFCDict


def delete_vnfd(mydb,vnf_id):
    try:
        result, vims = get_vim_connector(mydb)

        if result < 0:
            log.error("delete_vnfd error. No VIM found for tenant")
            vims = []

        # 2. Check if VNFD exists
        where_ = {"nfcatseq": vnf_id}
        result, content = orch_dbm.get_vnfd_id(mydb, vnf_id)

        if result < 0:
            log.error("delete_vnfd error %d %s" % (result, content))

        # undeletedItems = []

        # 3. Check if NSD using VNFD exists
        check_result, check_content = orch_dbm.get_nsd_using_vnfd(mydb, vnf_id)
        if check_result < 0:
            log.error("failed to check NSD using the VNFD %s" %str(vnf_id))
            return -HTTP_Internal_Server_Error, "Error from DB"
        elif check_result > 0:
            log.error("Cannot delete VNFD. Cause: There are NSDs using VNFD %s" %str(vnf_id))
            return -HTTP_Internal_Server_Error, "Cannot delete VNFD. Cause: There are NSDs using VNFD %s" %str(vnf_id)

        # delete a template record in tb_templates
        log.debug("delete_vnfd(): delete resource template")
        if content['vnfd'].get('resource_template_seq') is not None:

            log.debug("delete_vnfd: resource_template_seq: %s" %str(content['vnfd'].get('resource_template_seq')))

            result, content = orch_dbm.delete_vnfd_resourcetemplate(mydb, content['vnfd'].get('resource_template_seq'))

            if result == 0:
                log.warning("delete_vnfd failed to the resource template record")
            elif result >0:
                pass
            else:
                log.warning("delete_vnfd error %d %s" %(result, content))

        # # get image records from tb_vduds_images
        # result, image_list = orch_dbm.get_vnfd_imagelist(mydb, vnf_id)
        # if result < 0:
        #     log.warning("failed to get image list of the vnf %d %s" %(result, image_list))
        # elif result==0:
        #     log.warning("delete_vnf_v4 error. No images found for the VNF id '%s'" % str(vnf_id))

        # delete vnf records
        result, content = orch_dbm.delete_vnfd(mydb, vnf_id)

        if result == 0:
            return -HTTP_Not_Found, content
        elif result > 0:
            pass
        else:
            log.error("delete_vnfd error %d %s" %(result, content))
            return result, content

        # # delete image records from tb_vim_images
        # for image in image_list:
        #     #check if image is used by other vnf
        #     r,c = orch_dbm.get_vnfd_vdud_list(mydb, {'imageseq':image})
        #     if r < 0:
        #         log.error('delete_vnfd error. Not possible to delete VIM image "%s". %s' % (image,c))
        #         undeletedItems.append("image %s" % image)
        #     elif r > 0:
        #         log.debug('Image %s not deleted because it is being used by another VNF %s' %(image,str(c)))
        #         continue
        #     #image not used, must be deleted
        #     #delete at VIM
        #     r,c = orch_dbm.get_vim_images(mydb, vim_id=None, vdud_image_id=image)
        #     if r>0:
        #         for image_vim in c:
        #             if image_vim["vimseq"] not in vims:
        #                 continue
        #             if image_vim['createdyn']=='false': #skip this image because not created by openmano
        #                 continue
        #             myvim=vims[ image_vim["vimseq"] ]
        #             result, message = myvim.delete_tenant_image(image_vim["uuid"])
        #             if result < 0:
        #                 log.error('delete_vnfd error. Not possible to delete VIM image "%s". Message: %s' % (image,message))
        #                 if result != -HTTP_Not_Found:
        #                     undeletedItems.append("image %s from VIM %s" % (image_vim["uuid"], image_vim["vimseq"] ))
        #
        #     #delete image from Database, using table images and with cascade foreign key also at datacenters_images
        #     result, content = orch_dbm.delete_vnfd_vdu_image(mydb, image)
        #     if result <0:
        #         undeletedItems.append("image %s" % image)
        #
        # #TODO: delete Flavor

        # if undeletedItems:
        #     return 200, "delete_vnfd error. Undeleted: %s" %(undeletedItems)

        return 200,vnf_id
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "VNFD 삭제가 실패하였습니다. 원인: %s" %str(e)


def new_nsd_with_vnfs(mydb, vnf_list, customer_eng_name = None, serverseq=None):
    try:
        number_of_vnfs = len(vnf_list)
        if number_of_vnfs == 0:
            log.error("VNF List is empty")
            return -HTTP_Bad_Request, "No VNF Info."

        log.debug("The number of VNFs: %d" %number_of_vnfs)

        # Step 1. Check if a NSD that includes all the vnfs exists
        nsd_result, nsd_list = orch_dbm.get_nsd_list(mydb, [])
        if nsd_result < 0:
            log.error("failed to get nsd info from DB: %d %s" %(nsd_result, nsd_list))
            return nsd_result, nsd_list

        for nsd in nsd_list:
            if nsd['vnfs'] is None or len(nsd['vnfs']) == 0:
                continue

            if len(nsd['vnfs']) != number_of_vnfs:
                log.debug("[*****HJC*****] not matched NSD: %s" %str(nsd))
                log.debug("[*****HJC*****] nsd vnf number: %d, requested vnf number: %d" %(len(nsd['vnfs']), number_of_vnfs))
                continue

            matched_vnf_counts = 0

            for req_vnf in vnf_list:
                for vnf in nsd['vnfs']:
                    if vnf['vnfd_name'] == req_vnf['vnfd_name'] and vnf['vnfd_version'] == req_vnf['vnfd_version']:
                        matched_vnf_counts += 1
                        log.debug("Found the VNFD: %s, the number of found VNFs: %d" %(vnf['vnfd_name'], matched_vnf_counts))
                        break

            if matched_vnf_counts == number_of_vnfs:
                log.debug("found the NSD: %s" %str(nsd))

                # ArmBox 의 경우 배포완료 된것으로 표시하기 위해 tb_server_vnfimage 테이블에 등록해준다
                if serverseq:
                    server_result, server_data = orch_dbm.get_server_id(mydb, serverseq)
                    if server_result:
                        if server_data.get('nfsubcategory') == 'KtArm':
                            for vnfs in nsd.get('vnfs'):
                                vdud_result, vdud_data = orch_dbm.get_vdud_by_vnfd_id(mydb, vnfs.get('nfcatseq'))
                                if vdud_result > 0:
                                    img_result, img_data = orch_dbm.get_vdud_image_list(mydb, vdud_data.get('vdudseq'))
                                    if img_result > 0:

                                        log.debug('[ArmBox] server vnf image insert!')
                                        log.debug('img_data = %s' %str(img_data))

                                        for img in img_data:
                                            insert_dict = {}
                                            insert_dict['serverseq'] = serverseq
                                            insert_dict['name'] = img.get('name')
                                            insert_dict['location'] = img.get('location')
                                            insert_dict['description'] = img.get('description')
                                            insert_dict['filesize'] = img.get('filesize')
                                            insert_dict['status'] = 'N__COMPLETE'
                                            insert_dict['checksum'] = img.get('checksum')
                                            insert_dict['metadata'] = img.get('metadata')
                                            insert_dict['vdudimageseq'] = img.get('vdudimageseq')
                                            result, data = orch_dbm.insert_server_vnfimage(mydb, insert_dict)

                return 200, nsd['nscatseq']

        # Step 2. Check VNFDs
        vnfd_result, db_vnfd_list = orch_dbm.get_vnfd_list(mydb, [])
        if vnfd_result < 0:
            log.error("failed to get VNFD List from DB: %d %s" %(vnfd_result, db_vnfd_list))
            return vnfd_result, db_vnfd_list

        for req_vnf in vnf_list:
            is_existing = False
            for vnfd in db_vnfd_list:
                if vnfd['name'] == req_vnf['vnfd_name'] and vnfd['version'] == req_vnf['vnfd_version']:
                    is_existing = True
                    break

            if not is_existing:
                log.error("Cannot find the requested VNFD: %s" %str(req_vnf))
                return -HTTP_Bad_Request, "Cannot find the requested VNFD: %s" %str(req_vnf)


        # Step 3. Compose New NSD Automatically

        # 3.1 auto-naming NSD
        if customer_eng_name:
            if len(customer_eng_name) > 10:
                nsd_name = "AUTO-NSD-"+customer_eng_name[:10]
            else:
                nsd_name = "AUTO-NSD-"+customer_eng_name
        else:
            nsd_name = "AUTO-NSD-" + str(random.randint(1, 99)).zfill(2)

        nsd_next_no = 1
        try:
            for nsd in nsd_list:
                if nsd['name'].find(nsd_name) >= 0:
                    nsd_name_list = nsd['name'].split("__")
                    if len(nsd_name_list) == 2:
                        nsd_no = int(nsd_name_list[1])
                        if nsd_no >= nsd_next_no:
                            nsd_next_no += nsd_no + 1
        except Exception, e:
            log.warning("failed to check duplication of nsd name: %s" %str(e))
            nsd_next_no += random.randint(1, 99)

        nsd_name += "__" + str(nsd_next_no)

        # 3.2 Check duplication
        for nsd in nsd_list:
            if nsd['name'] == nsd_name:
                log.error("Failed to create a new NSD due to Duplicated NSD Name: %s" %nsd_name)
                return -HTTP_Internal_Server_Error, "Failed to create a new NSD due to Duplicated NSD Name: %s" %nsd_name

        # 3.3 auto-naming VNF in NSD
        nsd_vnfds = []
        for req_vnf in vnf_list:
            vnfd_name = req_vnf['vnfd_name']
            vnfd_count = 0
            for nsd_vnf in nsd_vnfds:
                if nsd_vnf['vnfd_name'] == vnfd_name:
                    vnfd_count += 1

            vnf_name = req_vnf.get('vnf_name', vnfd_name)
            if req_vnf.get('vnf_name') is None: vnf_name += "-A" + str(vnfd_count+1)

            nsd_vnfds.append({"name":req_vnf['vnfd_name'], "vnfd_name": req_vnf['vnfd_name'], "vnfd_version": req_vnf['vnfd_version']})

        nsd_dict = {"name": nsd_name, "display_name": nsd_name, "description": "Auto Generated NSD", "version": "1", "resource_template_type":"hot", "public": True}
        nsd_dict['nsd'] = {"vnfds": nsd_vnfds}

        # Step 4. Onboarding NSD
        result, data = new_nsd(mydb, nsd_dict, False)

        if result < 0:
            log.error("Onboarding NS: Error %d %s" %(result, data))

        return result, data

    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "NSD 자동생성이 실패하였습니다. 원인: %s" %str(e)



def new_nsd(mydb, ns_descriptor, use_thread = True):
    try:
        log_info_message = "Onboarding NS Started (%s)" % ns_descriptor['name']
        log.info(log_info_message.center(80, '='))
        
        nsd_already_exist = False
        result, existing_nsd = orch_dbm.get_nsd_general_info(mydb, ns_descriptor['name'])
        if result > 0:
            log.debug("[Onboarding][NS] There is already the NSD %s. Update it" %ns_descriptor['name'])
            nsd_already_exist = True
        
        # Step 1. Check the descriptor version and start onboarding
        if ns_descriptor.get('descriptor_version',"1.0") == "2.0":
            #return _new_nsd_v2(mydb, ns_descriptor)
            return -HTTP_Bad_Request, "Descriptor of version2 is Not Supported"
        else:
            if nsd_already_exist:
                return _update_nsd_v1(mydb, ns_descriptor, existing_nsd['nscatseq'])
            else:
                return _new_nsd_v1(mydb, ns_descriptor, use_thread)
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "NSD 등록이 실패하였습니다. 원인: %s" %str(e)


def get_nsd_id(mydb, nsd_id):
    try:
        result, content = orch_dbm.get_nsd_id(mydb, nsd_id)
        if result < 0:
            log.error("Failed to get NSD Data from DB: %d %s" % (result, content))
        else:
            #remove duplicate parameters
            whole_params = content['parameters']
            display_params = []
            for param in whole_params:
                param_name = param.get('name')
                if param_name == None:
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
            content['parameters']=display_params

            #get metadata
            md_result, md_content = orch_dbm.get_nsd_metadata(mydb, nsd_id)
            if md_result < 0:
                log.warning("failed to get Metadata of NSD")
            else:
                content['metadata'] = {}
                for md in md_content:
                    if md.get('name'):
                        content['metadata'][md['name']] = md.get('value')

        return result, content
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "NSD 조회에 실패하였습니다. 원인: %s" %str(e)


def _update_nsd_v1(mydb, catalog, existing_nsd_id=None):
    if existing_nsd_id == None:
        log.error("[Updating][NSD] failed to find the id of the existing NSD")
        return -HTTP_Bad_Request, "failed to update NSD - No NSD found"
    
    update_dict = {'nscatseq': existing_nsd_id}
    update_dict['description'] = catalog.get("description", catalog['name'])
    update_dict['display_name'] = catalog.get("display_name", catalog['name'])
    update_dict['nscategory'] = catalog.get("class", "basic")
    update_dict['vendor'] = catalog.get("vendor")
    update_dict['resource_template_type'] = catalog.get("resource_template_type", "hot")
    if 'resource_template' in catalog: update_dict['resource_template'] = catalog['resource_template']
    if 'xy_graph' in catalog: update_dict['xy_graph'] = catalog.get("xy_graph", "none")
    #update_dict['status'] = DSCRTStatus.CRT_parsing
    
    result, nsd_id = orch_dbm.update_nsd_id(mydb, update_dict)
    if result < 0:
        log.error("[Updating][NSD] failed to update NSD %s: %d %s" %(catalog['name'], result, str(nsd_id)))

    return 200, nsd_id

def _new_nsd_v1(mydb, catalog, use_thread=True):

    rollback_list = []
    
    # Step 1. Check the NS Catalog is available
    vnf_list = catalog['nsd']['vnfds'] # fnds is list of vnfd names
    for vnf in vnf_list:
        r, vnf_db = orch_dbm.get_vnfd_general_info_with_name(mydb, vnf)
        if r < 0:
            log.error("  : error, failed to get VNF %s" %vnf)
            return -HTTP_Internal_Server_Error, "failed to get VNFD %s from DB" % vnf
        elif r == 0:
            log.error("  : error, VNF %s does not exist" % vnf)
            msg = "NSD가 등록되지 않은 VNF를 포함하고 있습니다.\nVNF(name=%s, version=%s)를 등록하세요." % (vnf.get("vnfd_name"), vnf.get("vnfd_version"))
            return -HTTP_Bad_Request, msg
    
    # Step 2. Review the NS Catalog and add missing fields for tb_nscatalogs DB
    log.debug("[Onboarding][NS] 2. Check NSD and DB insert general info")
    catalog['description'] = catalog.get("description", catalog['name'])
    catalog['display_name'] = catalog.get("display_name", catalog['name'])
    catalog['version'] = catalog.get("version", 1)
    catalog['nscategory'] = catalog.get("class", "basic")
    catalog['resource_template_type'] = catalog.get("resource_template_type", "hot")
    catalog['xy_graph'] = catalog.get("xy_graph", "none")
    catalog['status'] = DSCRTStatus.CRT_parsing
    
    result, ns_id = orch_dbm.insert_nsd_general_info(mydb, catalog)
    
    if result < 0:
        log.error("[Onboarding][NS]  : error, %s" % str(ns_id))
        return result, ns_id
    
    catalog['nscatseq'] = ns_id
    
    if use_thread:
        try:
            th = threading.Thread(target=_new_nsd_v1_thread, args=(mydb, catalog, rollback_list, use_thread))
            th.start()
        except Exception, e:
            error_msg = "failed to start a thread for onboarding NS %s " %catalog['name']
            log.exception(error_msg)
            use_thread = False
    
        time.sleep(5) # Waiting for DB Update

        log_info_message = "Onboarding NS - In Progress by a Thread (%s)" %catalog['name']
        log.info(log_info_message.center(80, '='))
        return 200, ns_id
    else:
        return _new_nsd_v1_thread(mydb, catalog, rollback_list, False)

def _new_nsd_v1_thread(mydb, catalog, rollback_list, use_thread=True):
    try:
        if use_thread:
            log_info_message = "Onboarding NS - Thread Started (%s)" % catalog['name']
            log.info(log_info_message.center(80, '='))
        
        # Step 3. get VNFs and Check that VNF are present at database table vnfs. Insert uuid, desctiption
        log.debug("[Onboarding][NS] 3. Get VNFDs")
        vnf_list = catalog['nsd']['vnfds'] # fnds is list of vnfd names
        vnfds = {}
        param_list = []
        deploy_order = 1
        for vnf in vnf_list:
            r, vnf_db = orch_dbm.get_vnfd_general_info_with_name(mydb, vnf)
            if r < 0:
                log.error("  : error, failed to get VNF %s" %str(vnf))
                #update status
                catalog['status'] = DSCRTStatus.ERR
                update_result, update_content = orch_dbm.update_nsd_id(mydb, catalog)
                return -HTTP_Internal_Server_Error, "failed to get VNFD %s from DB" %str(vnf)
            elif r==0:
                log.error("  : error, VNF %s is not present at DB" % str(vnf))
                #update status
                catalog['status'] = DSCRTStatus.ERR
                update_result, update_content = orch_dbm.update_nsd_id(mydb, catalog)
                return -HTTP_Bad_Request, "VNF %s is not present at DB" % str(vnf)
            
            vnfd = {}

            if type(vnf) == str:
                vnfd['name'] = vnf.split("_ver")[0]
            elif type(vnfd) == dict:
                vnfd['name'] = vnf['name']
                vnfd['graph'] = vnf.get('graph')

            vnfd['vnfd_name'] = vnf_db['name']
            vnfd['vnfd_version'] = vnf_db['version']
            vnfd['description'] = vnf_db['description']
            vnfd['deployorder'] = deploy_order
            vnfd['nfcatseq'] = vnf_db['nfcatseq']
            vnfd['resourcetemplatetype'] = vnf_db['resourcetemplatetype']
            
            if vnf_db['resourcetemplate'] is not None:
                log.debug("before Resource Template: %s" %vnf_db['resourcetemplate'])
                vnf_db['resourcetemplate'] = vnf_db['resourcetemplate'].replace(vnfd['vnfd_name'], vnfd['name'])
                log.debug("after Resource Template: %s" %vnf_db['resourcetemplate'])

            vnfd['resourcetemplate'] = vnf_db['resourcetemplate']
            deploy_order += 1
            vnfds[vnfd['name']]=vnfd

            #3.1 get VNFD Parameter info
            #3.1.1 get template parameters
            log.debug("[Onboarding][NS]   a. Get VNFDs' template(HOT) parameters for %s" %vnf)
            if vnf_db.get('resourcetemplateseq') is not None:
                vnf_template_param_r, template_params = orch_dbm.get_vnfd_resource_template_item(mydb, vnf_db['resourcetemplateseq'], 'parameter')
                
                if vnf_template_param_r < 0:
                    log.warning("[Onboarding][NS]      failed to get Resource Template Parameters")
                elif vnf_template_param_r == 0:
                    log.debug("[Onboarding][NS]      No Template Parameters")
                else:
                    for param in template_params:
                        param['category'] = 'vnf_template'
                        param['ownername'] = vnfd['name']
                        param['ownerseq'] = vnfd['nfcatseq']
                        param['name'] = param['name'].replace(vnfd['vnfd_name'], vnfd['name'])
                        param_list.append(param)

            # 현재 사용하지 않는 부분 : 추후 삭제 처리해도 무방함. #########################################################
            #3.1.2-1 get vnf parameters for account
            vnfd_param_r, vnfd_param_contents = orch_dbm.get_vnfd_param_only(mydb, vnfd['nfcatseq'])
            if vnfd_param_r < 0:
                log.warning("[Onboarding][NS]      failed to get VNFD Parameters")
                pass
            elif vnfd_param_r == 0:
                log.debug("[Onboarding][NS]      No VNF Parameters")
                pass
            
            for vnfd_param in vnfd_param_contents:
                vnfd_param['category'] = 'vnf_config'
                vnfd_param['ownername'] = vnfd['name']
                vnfd_param['ownerseq'] = vnfd['nfcatseq']
                vnfd_param['name'] = vnfd_param['name'].replace(vnfd['vnfd_name'], vnfd['name'])
                log.debug("[Onboarding][NS] VNFD Param: name = %s" %vnfd_param['name'])
                param_list.append(vnfd_param)
            # END : 현재 사용하지 않는 부분 : 추후 삭제 처리해도 무방함. #########################################################

            #3.1.2 get vnf config parameters
            vdud_r, vdud_contents = orch_dbm.get_vnfd_vdud_only(mydb, vnfd['nfcatseq'])
            if vdud_r < 0:
                log.warning("[Onboarding][NS]      failed to get VNF VDUD")
                pass
            elif vdud_r == 0:
                log.debug("[Onboarding][NS]      No VNF VDUD")
                pass
            
            for vdud in vdud_contents:
                vdud_config_param_r, vdud_config_params = orch_dbm.get_vnfd_vdud_config_only(mydb, vdud['vdudseq'], 'parameter')
                if vdud_config_param_r < 0:
                    log.warning("[Onboarding][NS]      failed to get VNF VDUD Config Parameters")
                elif vdud_config_param_r == 0:
                    log.debug("[Onboarding][NS]      No VNF VDUD Config Parameters")
                else:
                    for param in vdud_config_params:
                        if param['name'].find(vnfd['vnfd_name']) >= 0:
                            param['category'] = 'vnf_config'
                            param['ownername'] = vnfd['name']
                            param['ownerseq'] = vnfd['nfcatseq']
                            param['name'] = param['name'].replace(vnfd['vnfd_name'], vnfd['name'])
                            param_list.append(param)

            # 3.1.3 TODO vdud_monitor_param
            
            log.debug("_new_nsd_v1_thread() Parameter list: %s" %str(param_list))
        
        log.debug("[Onboarding][NS] 3. success")

        # Step 4. TODO: parse NS Parameters info   
        log.debug("[Onboarding][NS] 4. Parsing NS Parameters")
        log.debug("[Onboarding][NS] 4. skip (TBD)")
        
        # Step 5. TODO: parse VLDs and CPDs
        log.debug("[Onboarding][NS] 5. Parsing Virtual Links in NSD")
        vlds = None
        if 'vlds' in catalog['nsd']:
            vlds = catalog['nsd']['vlds']

        cpds = None
        if 'cpds' in catalog['nsd']:
            cpds = catalog['nsd']['cpds']
        log.debug("[Onboarding][NS] 5. success")
        
        # Step 6. TODO: compose Template using vnf templetes, Current: use the template in NSD 
        log.debug("[Onboarding][NS] 6. Composing NS Template (HOT) by using VNFDs' Templates")
        catalog['status'] = DSCRTStatus.CRT_processingdb
        update_result, update_content = orch_dbm.update_nsd_id(mydb, catalog)

        if "resource_template" in catalog:
            log.debug("[Onboarding][NS] 6. Success: Use HOT included by NSD")
        else:
            vnf_hot_list = []
            for vnfd_name, vnfd in vnfds.items():
                if vnfd['resourcetemplatetype'] != "hot":
                    log.debug("[HJC] skip getting resource template because it belongs to Other Service System")
                    continue
                
                vnf_template = {}
                try:
                    vnf_template=yaml.load(vnfd['resourcetemplate'])
                except yaml.YAMLError as exc:
                    if hasattr(exc, 'problem_mark'):
                        mark = exc.problem_mark
                        log.exception("[Onboarding][NS]  : error, Yaml Data at line %s, column %s." %(mark.line, mark.column+1))
                    else:
                        log.exception("[Onboarding][NS]  : Unknown Error with Yaml Data.")
                
                vnf_hot_list.append(vnf_template)
            
            ns_hot_result, ns_hot_value = compose_nsd_hot(catalog["name"], vnf_hot_list)
            if ns_hot_result < 0:
                return ns_hot_result, ns_hot_value
            
            catalog['resource_template'] = ns_hot_value
            log.debug("[Onboarding][NS] 6. Success: Create HOT for NSD using VNFD HOTs")
        
        # Step 7. insert scenario. filling tables tb_nscatalogs, tb_nfconstituents, scenarios,sce_vnfs,sce_interfaces,sce_nets
        log.debug("[Onboarding][NS] 7. DB Insert NS")
        r, nsd_id = orch_dbm.insert_nsd_as_a_whole(mydb, { 'vnfs':vnfds, 'vlds':vlds, 'cpds': cpds, 'name':catalog['name'], 'description':catalog.get('description',catalog['name']),'resource_template_type': catalog['resource_template_type'], 'resource_template':catalog['resource_template'] }, param_list)
        if r < 0:
            log.error("[Onboarding][NS]  : error, failed to insert a DB record %d %s" %(r, str(nsd_id)))
            #update status
            catalog['status'] = DSCRTStatus.ERR
            update_result, update_content = orch_dbm.update_nsd_id(mydb, catalog)
            return r, nsd_id
        
        # parsing and saving metadata
        result, content = orch_dbm.insert_nsd_metadata(mydb, nsd_id, catalog.get('metadata'))
        if result < 0:
            log.warning("[Onboarding][NS] failed to db insert NSD metadata, %s" %str(content))
        
        log.debug("[Onboarding][NS] 7. success")
        
        # Step 8. update nscatalog's status
        log.debug("[Onboarding][NS] 8. update the status of the NSD")
        catalog['nscatseq'] = nsd_id
        catalog['status'] = DSCRTStatus.RDY
        result, update_content = orch_dbm.update_nsd_id(mydb, catalog)
        log.debug("[Onboarding][NS] 8. success %d %s" %(result, str(update_content)))
        
        # Step 9. update tb_itsm_said
        #said_result, said_data = update_said(mydb, catalog)
        #if said_result < 0:
        #    log.warning("Failed to update tb_itsm_said %d %s" %(said_result, said_data))
        #else:
        #    log.debug("Update SAID: result = %d %s" %(said_result, said_data))

        if use_thread:
            log_info_message = "Onboarding NS - Thread Finished (%s)" %str(nsd_id)
        else:
            log_info_message = "Onboarding NS Completed (%s)" % str(nsd_id)
        log.info(log_info_message.center(80, '='))
        
        return 200,nsd_id
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "NSD 등록이 실패하였습니다. 원인: %s" %str(e)

def compose_nsd_hot(nscatalog_name, vnf_hot_list):
    try:
        hot_template = "heat_template_version: 2014-10-16\n"
        hot_template += "description: Auto-created HOT for " + nscatalog_name+"\n"
        
        # compose parameters
        hot_template += "parameters:\n"
        done_param_list = []
        for vnf_hot in vnf_hot_list:
            if "parameters" in vnf_hot and vnf_hot['parameters'] is not None:
                for param_name, param_value in vnf_hot['parameters'].items():
                    already_added = False
                    for d in done_param_list:
                        if d == param_name:
                            already_added = True
                            break

                    if already_added: continue

                    param_template = "    " + param_name + ":\n"
                    param_template += "        type: " + param_value['type'] + "\n"
                    param_template += "        description: \"" + param_value['description'] + "\"\n"

                    hot_template += param_template
                    done_param_list.append(param_name)
        
        # compose resources
        hot_template += "resources:\n"
        done_resource_list = []

        # TODO: compose predefined resources

        # TODO: compose nsd resources

        # compose vnf resources - vNet
        for vnf_hot in vnf_hot_list:
            if "resources" in vnf_hot and vnf_hot['resources'] is not None:
                for resc_name, resc_value in vnf_hot['resources'].items():
                    if resc_value['type'].find("ProviderNet") >= 0 or resc_value['type'].find("Subnet") >= 0:
                        pass
                    else:
                        continue

                    already_added = False
                    for d in done_resource_list:
                        if d == resc_name:
                            already_added = True
                            break

                    if already_added: continue

                    resc_template = "    " + resc_name + ":\n"
                    resc_template += "        type: " + resc_value['type'] + "\n"
                    resc_template += "        properties:\n"
                    for prop_name, prop_value in resc_value['properties'].items():
                        if prop_name == "networks" or prop_name == "fixed_ips":
                            resc_template += "            " + prop_name + ":\n"
                            for pv in prop_value:
                                if 'ip_address' in pv:
                                    if 'get_param' in pv['ip_address']: resc_template += "            -   ip_address: { get_param: " + pv['ip_address']['get_param'] + " }\n"
                                    else: resc_template += "            -   ip_address: " + pv['ip_address'] + "\n"

                                if 'port' in pv:
                                    if 'get_param' in pv['port']: resc_template += "            -   port: { get_param: " + pv['port']['get_param'] + " }\n"
                                    elif 'get_resource' in pv['port']: resc_template += "            -   port: { get_resource: " + pv['port']['get_resource'] + " }\n"
                                    else: resc_template += "            -   port: " + pv['port']['get_resource'] + "\n"
                        elif prop_name == "user_data":
                            resc_template += "            " + prop_name + ": | \n"
                            pv_list = prop_value.split("\n")
                            for pv in pv_list:
                                resc_template += "                " + pv + "\n"
                        else:
                            resc_template += "            " + prop_name + ":"
                            if type(prop_value) is dict and "get_param" in prop_value:
                                resc_template += " { get_param: "+str(prop_value['get_param']) + " }\n"
                            elif type(prop_value) is dict and "get_resource" in prop_value:
                                resc_template += " { get_resource: " + str(prop_value['get_resource']) + " }\n"
                            else:
                                if prop_value is None:
                                    resc_template += " null\n"
                                else:
                                    resc_template += " " + str(prop_value) + "\n"

                    hot_template += resc_template
                    done_resource_list.append(resc_name)

        # compose vnf resources - vServer
        for vnf_hot in vnf_hot_list:
            if "resources" in vnf_hot and vnf_hot['resources'] is not None:
                for resc_name, resc_value in vnf_hot['resources'].items():
                    if resc_value['type'].find("ProviderNet") >= 0 or resc_value['type'].find("Subnet") >= 0:
                        continue

                    already_added = False
                    for d in done_resource_list:
                        if d == resc_name:
                            already_added = True
                            break

                    if already_added: continue

                    resc_template = "    " + resc_name + ":\n"
                    resc_template += "        type: " + resc_value['type'] + "\n"
                    resc_template += "        properties:\n"
                    for prop_name, prop_value in resc_value['properties'].items():
                        if prop_name == "networks" or prop_name == "fixed_ips":
                            resc_template += "            " + prop_name + ":\n"
                            for pv in prop_value:
                                if 'ip_address' in pv:
                                    if 'get_param' in pv['ip_address']: resc_template += "            -   ip_address: { get_param: " + pv['ip_address']['get_param'] + " }\n"
                                    else: resc_template += "            -   ip_address: " + pv['ip_address'] + "\n"

                                if 'port' in pv:
                                    if 'get_param' in pv['port']: resc_template += "            -   port: { get_param: " + pv['port']['get_param'] + " }\n"
                                    elif 'get_resource' in pv['port']: resc_template += "            -   port: { get_resource: " + pv['port']['get_resource'] + " }\n"
                                    else: resc_template += "            -   port: " + pv['port']['get_resource'] + "\n"
                        elif prop_name == "user_data":
                            resc_template += "            " + prop_name + ": | \n"
                            pv_list = prop_value.split("\n")
                            for pv in pv_list:
                                resc_template += "                " + pv + "\n"
                        else:
                            resc_template += "            " + prop_name + ":"
                            if type(prop_value) is dict and "get_param" in prop_value:
                                resc_template += " { get_param: "+str(prop_value['get_param']) + " }\n"
                            elif type(prop_value) is dict and "get_resource" in prop_value:
                                resc_template += " { get_resource: " + str(prop_value['get_resource']) + " }\n"
                            else:
                                resc_template += " " + str(prop_value) + "\n"

                    hot_template += resc_template
                    done_resource_list.append(resc_name)
        
        # compose outputs
        hot_template += "outputs:\n"
        done_output_list = []
        for vnf_hot in vnf_hot_list:
            if "outputs" in vnf_hot and vnf_hot['outputs'] is not None:
                for output_name, output_value in vnf_hot['outputs'].items():
                    already_added = False
                    for d in done_output_list:
                        if d == output_name:
                            already_added = True
                            break

                    if already_added: continue

                    output_template = "    " + output_name + ":\n"
                    output_template += "        description: " + str(output_value['description']) + "\n"
                    output_template += "        value: { get_attr: [ "
                    is_first_attr = True
                    for attr_value in output_value['value']['get_attr']:
                        if is_first_attr == False: output_template += ", "
                        output_template += str(attr_value)
                        is_first_attr = False
                    output_template += " ] }\n"

                    hot_template += output_template
                    done_output_list.append(output_name)

        return 200, hot_template
    except Exception, e:
        log.exception("Exception: %s" %str(e))
        return -HTTP_Internal_Server_Error, "Failed to compose NS HOT: %s" %str(e)

# def setup_monitor_for_vnfd(mydb, vnfd_dict):
#     monitor = get_ktmonitor()
#     if monitor is None:
#         log.warning("failed to setup montior")
#         return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"
#     target_dict = {}
#     target_dict['name'] = vnfd_dict['name']
#     target_dict['type'] = vnfd_dict['nfsubcategory']
#     target_dict['vendor'] = vnfd_dict['vendorcode']
#     target_dict['version'] = str(vnfd_dict['version'])
#     target_dict['vdus'] = vnfd_dict['VNFC']
#
#     result, data = monitor.get_monitor_vnf_target_seq(target_dict)
#
#     if result < 0:
#         log.error("setup_monitor_for_vnfd(): error %d %s" %(result, data))
#
#     return result, data

def _check_monitor_target_seq(monitor_target_seq):
    monitor = common_manager.get_ktmonitor()
    if monitor is None:
        log.warning("failed to check montior_target_seq")
        return -HTTP_Internal_Server_Error, "Cannot get a connection to Montior"

    result, data = monitor.check_monitor_target_seq(monitor_target_seq)
    log.debug("__________________check_monitor_target_seq %d %s" % (result, data))
    if result < 0:
        log.error("check_monitor_target_seq(): error %d %s" %(result, data))

    return result, data


def check_vnfd_image_name(mydb, req_data):
    """
        vnfd image name 중복체크
    :param mydb:
    :param req_data:
    :return:
    """
    # name 중복체크
    result, imgs = orch_dbm.get_vnfd_vdu_image(mydb, {"name" : req_data["name"]})
    if result < 0:
        log.error("Failed to get tb_vdud_image record : name = %s" % req_data["name"])
        return result, imgs
    elif result > 0:
        # 중복됨.
        log.debug("Already exist record : name = %s" % req_data["name"])
        return 200, "DUP_NAME"

    # location 중복체크
    result, imgs = orch_dbm.get_vnfd_vdu_image(mydb, {"location" : req_data["location"]})
    if result < 0:
        log.error("Failed to get tb_vdud_image record : location = %s" % req_data["location"])
        return result, imgs
    elif result > 0:
        # 중복됨.
        log.debug("Already exist record : location = %s" % req_data["location"])
        return 200, "DUP_LOCATION"
    return 200, "OK"


def save_vnf_image(mydb, vnfd_id, img_data):
    """
        UI에서 vnfd 이미지 등록 요청을 받아서 DB에 저장
    :param mydb:
    :param vnfd_id:
    :param img_data:
    :return:
    """

    cfgManager = ConfigManager.get_instance()
    config = cfgManager.get_config()
    MOUNT_PATH = config.get('image_mount_path', "")
    REAL_PATH = config.get('image_real_path', "")

    location = img_data["location"]
    location = location.replace(REAL_PATH, MOUNT_PATH)

    log.debug("__________ 파일서버 마운트 경로 : %s" % location)

    # 1. 등록
    # 1.1. 파일 존재 확인
    is_exist = os.path.exists(location)
    #     - 없으면 : NONE
    if not is_exist:
        log.debug("__________ 파일이 존재하지 않음!!!")
        return 200, "NONE"
    #     - 있으면 file size get
    file_size = os.path.getsize(location)
    if int(img_data.get("filesize", 0)) == 0:
        img_data["filesize"] = file_size

    # 1.2. vdudseq 조회
    result, vdud_t = orch_dbm.get_vdud_by_vnfd_id(mydb, vnfd_id)
    if result < 0:
        return result, vdud_t

    log.debug("__________ vdud_t : %s" % vdud_t)

    img_data["vdudseq"] = vdud_t["vdudseq"]

    # metadata 처리
    # request body로 넘어온 metadata 중 값이 없는 경우("none"), vdud에 있는 기본 값(image_metadata)으로 대체한다.
    if "metadata" in img_data and vdud_t.get("image_metadata") is not None:
        metadata = json.loads(img_data["metadata"])
        image_metadata = json.loads(vdud_t["image_metadata"])

        for key, value in metadata.items():
            if str(value).lower() == "none" or len(str(value)) <= 0:
                if key in image_metadata:
                    metadata[key] = image_metadata[key]
                    log.debug("__________ metadata default value setting : %s %s" % (key, image_metadata[key]))
                else:
                    del metadata[key]

        img_data["metadata"] = metadata

    # vnf_image_version / vnf_sw_version
    image_id = os.path.splitext(os.path.split(img_data["location"])[1])[0]
    sep = "v."
    image_id_arr = image_id.split(sep, 1)

    if len(image_id_arr) > 1:
        image_version = sep + image_id_arr[1]
    else:
        sep = "_v"
        image_id_arr = image_id.split(sep, 1)
        if len(image_id_arr) > 1:
            image_version = "v" + image_id_arr[1]
        else:
            image_version = None
    if image_version:
        img_data['vnf_image_version'] = image_version

        if image_id_arr[1].count(".") >= 3:
            cnt = 0
            third_idx = 0
            while cnt < 3:
                third_idx = image_id_arr[1].find(".", third_idx+1)
                cnt += 1

            sw_version = image_id_arr[1][third_idx+1:]
        else:
            idx = image_version.rfind(".")
            sw_version = image_version[idx+1:]

        img_data["vnf_sw_version"] = sw_version

    # 1.2. DB에 등록 (tb_vdud_image)
    result, data = orch_dbm.insert_vnfd_vdu_image(mydb, img_data)
    if result < 0:
        log.error("Failed to insert vdud_image record : %s" % img_data)
        return result, data
    else:
        log.debug("Inserted vdud_image record")
        return 200, "OK"


def deploy_vnf_image(mydb, vnfd_id, image_id, req_data, tid=None, tpath="", e2e_log=None, use_thread=True):
    """

    :param mydb:
    :param vnfd_id:
    :param image_id:
    :param req_data:
    :param tid:
    :param tpath:
    :param e2e_log:
    :param use_thread:
    :return:
    """

    log.debug("____________ req_data : %s" % req_data)

    try:
        if e2e_log is None:
            if not tid:
                e2e_log = e2elogger(tname='Deploy VNF Image', tmodule='orch-f', tpath="orch_deploy-image")
            else:
                e2e_log = e2elogger(tname='Deploy VNF Image', tmodule='orch-f', tid=tid, tpath=tpath + "/orch_deploy-image")
    except Exception, e:
        log.exception("Failed to create an e2e_log: [%s] %s" % (str(e), sys.exc_info()))
        e2e_log = None

    if e2e_log:
        e2e_log.job('Deploy VNF Image Start', CONST_TRESULT_SUCC,
                    tmsg_body="vnfd_id: %s, image_id:%s\nRequest Body:%s" % (str(vnfd_id), str(image_id), req_data))

    # 1. vnfd image 정보 조회
    result, img_r = orch_dbm.get_vnfd_vdu_image(mydb, {"vdudimageseq" : image_id})
    if result <= 0:
        log.error("Failed to get tb_vdud_image record : vdudimageseq = %s" % image_id)
        return result, img_r
    else:
        vdud_image_t = img_r[0]

    # 1.1. vnfd 조회
    result, vnfd_t = orch_dbm.get_vnfd_general_info(mydb, vnfd_id)
    if result <= 0:
        log.error("Failed to get tb_nfcatalog record : nfcatseq = %s" % vnfd_id)
        return result, vnfd_t

    if e2e_log:
        e2e_log.job('Get VNFD Info', CONST_TRESULT_SUCC, tmsg_body="vnfd_id : %s" % (str(vnfd_id)))

    ob_list = req_data["release"]["target_onebox"]
    for ob_id in ob_list:

        if use_thread:
            try:
                th = threading.Thread(target=_deploy_vnf_image_thread, args=(mydb, vdud_image_t, vnfd_t, ob_id, e2e_log))
                th.start()
            except Exception, e:
                error_msg = "failed to start a thread for deploying vnfd image for Onebox %s : %s" % (ob_id, str(e))
                log.error(error_msg)
        else:
            return _deploy_vnf_image_thread(mydb, vdud_image_t, vnfd_t, ob_id, e2e_log)

    return 200, "OK"


def _deploy_vnf_image_thread(mydb, vdud_image_t, vnfd_t, ob_id, e2e_log=None):

    log.debug("__________ _deploy_vnf_image_thread IN : %s" % ob_id)

    vnfimage_t = None

    try:
        # server 정보 조회 : serverseq, publicip 필요
        result, ob_data = orch_dbm.get_server_id(mydb, ob_id)
        if result < 0:
            log.error("Failed to get tb_server record")
            raise Exception(ImageStatus.ERROR, ob_data)

        vdud_image_t["serverseq"] = ob_data["serverseq"]

        # 1. tb_server_vnfimage 조회 : 진행 상태 업데이트
        result, vnfimage_r = orch_dbm.get_server_vnfimage(mydb, {"serverseq":ob_data["serverseq"], "location":vdud_image_t["location"]})
        log.debug("__________1. get_server_vnfimage : %s %s" % (result, vnfimage_r))
        if result < 0:
            log.error("Failed to get tb_server_vnfimage record")
            raise Exception(ImageStatus.ERROR, vnfimage_r)
        elif result == 0: # 신규
            # 1.1. 신규 배포 정보 저장
            vdud_image_t["status"] = ImageStatus.WAIT
            result, vnfimageseq = orch_dbm.insert_server_vnfimage(mydb, vdud_image_t)
            if result < 0:
                log.error("Failed to insert server_vnfimage : %s %s" % (result, vnfimageseq))
                raise Exception(ImageStatus.ERROR, vnfimageseq)
            log.debug("__________1.1. insert_server_vnfimage : %s %s" % (result, vnfimageseq))
            vnfimage_t = {"vnfimageseq":int(vnfimageseq)}

            if e2e_log:
                e2e_log.job('Insert VNF Image', CONST_TRESULT_SUCC, tmsg_body="vnfimageseq : %s" % (str(vnfimageseq)))

        else: # 재배포
            vnfimage_t = vnfimage_r[0]
            if e2e_log:
                e2e_log.job('Update VNF Image', CONST_TRESULT_SUCC, tmsg_body="vnfimageseq : %s" % (str(vnfimage_t["vnfimageseq"])))

        log.debug("__________1.2. vnfimage_t : %s" % vnfimage_t)

        # get vnfm connector
        result, vnfms = common_manager.get_ktvnfm(mydb, ob_id)
        if result < 0:
            log.error("Failed to establish a vnfm connection")
            raise Exception(ImageStatus.ERROR, "No KT VNFM Found")
        elif result > 1:
            log.error("Error, Several vnfms available, must be identify")
            raise Exception(ImageStatus.ERROR, "Several vnfms available, must be identify")

        myvnfm = vnfms.values()[0]

        # 2. VNFM 버전 조회 > 지원 가능 버전일 경우만 배포 프로세스 실행 : 버전의 최상위 값이 1 이상인 경우 지원 가능
        result, version_res = myvnfm.get_vnfm_version()
        if result < 0:
            log.error("Failed to get vnfm version %s %s" % (result, version_res))
            raise Exception(ImageStatus.ERROR, version_res)
        else:
            if version_res["kind"] == "NEW":
                if e2e_log:
                    e2e_log.job('Check VNFM version', CONST_TRESULT_SUCC, tmsg_body="VNFM version : %s" % version_res)
                pass
            else:
                if e2e_log:
                    e2e_log.job('Not supported VNFM version', CONST_TRESULT_SUCC, tmsg_body="VNFM version : %s" % version_res)
                raise Exception(ImageStatus.ERROR_NOTSUPPORTED, "Not supported version : %s" % version_res)

        log.debug("__________2. version = %s" % version_res)

        # 진행 상태 업데이트 : WAIT
        vnfimage_t["status"] = ImageStatus.WAIT
        result, msg = orch_dbm.update_server_vnfimage(mydb, vnfimage_t)
        if result < 0:
            log.error("Failed to update server_vnfimage : %s %s" % (result, msg))
            raise Exception(ImageStatus.ERROR, msg)

        # 3. VNFD 정보 등록
        log.debug("__________3. VNFD 정보 등록 전: %s " % vnfd_t)
        # repo_filepath 가 없는 경우 처리
        if vnfd_t['repo_filepath'] is None or len(vnfd_t['repo_filepath']) <= 0:
            log.error("__________ The repo_filepath is empty")
            raise Exception(ImageStatus.ERROR, "The repo_filepath is empty")

        result, vnfd_res = myvnfm.regist_vnfd_info(vnfd_t)
        if result < 0:
            log.error("Failed to regist vnfd by vnfm : %s %s" % (result, vnfd_res))
            raise Exception(ImageStatus.ERROR, vnfd_res)
        log.debug("__________3. VNFD 정보 등록 결과 : %s %s" % (result, vnfd_res))
        if e2e_log:
            e2e_log.job('Regist VNFD Info by vnfm', CONST_TRESULT_SUCC, tmsg_body="")

        # 4. 배포된 이미지 정보 요청 : VNFM-IMG-1
        result, deploy_img_data = myvnfm.get_deployed_images()
        if result < 0:
            log.error("Failed to get deployed images %s %s" % (result, deploy_img_data))
            raise Exception(ImageStatus.ERROR, deploy_img_data)
        log.debug("__________4. 배포된 이미지 정보 요청 : VNFM-IMG-1 : %s %s" % (result, deploy_img_data))

        if e2e_log:
            e2e_log.job('Get deployed images in One-Box', CONST_TRESULT_SUCC, tmsg_body="Images Info : %s" % deploy_img_data)

        # 5. image 배포상태와 VIM 등록 상태 조회
        status_val = None
        vnfm_img_dict = None
        if deploy_img_data is not None and "images" in deploy_img_data:
            for img_dict in deploy_img_data["images"]:
                if "location" in img_dict:
                    if img_dict["location"] == vdud_image_t["location"]:
                        if "status" not in img_dict:
                            raise Exception(ImageStatus.ERROR, "NOT exist 'status' item from [VNFM-IMG-1] API")
                        # 이미 서버에 배포된 이미지...status 값이 true__xxxx 이어야 함.
                        status_val = img_dict["status"]
                        if status_val is None or str(status_val).find("true__") < 0:
                            raise Exception(ImageStatus.ERROR, "The status value from [VNFM-IMG-1] API is WRONG ")
                        vnfm_img_dict = img_dict
                        break
        log.debug("__________ 5. status_val = %s" % status_val)

        need_scp = False
        if vnfm_img_dict is not None:
            # 예외사항 처리
            # 파일전송중 에러가 발생했을 경우 true__xxx로 응답이오는데 실제 파일이 제대로 전송되지 않았으므로 재전송해야한다.
            # 파일 크기를 비교해서 처리.
            s_fs = int(vnfm_img_dict.get("filesize", "0"))
            r_fs = int(vdud_image_t.get("filesize", "0"))
            log.debug("__________ 파일 크기 체크 : 등록파일크기 : %d , 서버파일크기: %d" % (r_fs, s_fs))
            if r_fs > 0 and r_fs > s_fs:
                need_scp = True
                log.debug("__________ 파일 재전송 필요!!!")
                if e2e_log:
                    e2e_log.job('파일 재전송이 필요한지 확인', CONST_TRESULT_SUCC, tmsg_body="재전송 필요함.")


        if status_val is None or need_scp:
            # 6. 배포할 경우

            # 6.1. 이미지 전송 실행 SCP > 진행률 업데이트
            # 이미지 파일 배포. SCP 전송

            cfgManager = ConfigManager.get_instance()
            config = cfgManager.get_config()
            MOUNT_PATH = config.get('image_mount_path', "")
            REAL_PATH = config.get('image_real_path', "")

            location = vdud_image_t["location"]
            mount_location = location.replace(REAL_PATH, MOUNT_PATH)

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.load_system_host_keys()

            # callback DEFINE
            def callback_deploy_progress(filename, size, sent):

                status_filetran = ImageStatus.get_filetran_progress(size, sent)
                if vnfimage_t["status"] != status_filetran:
                    vnfimage_t["status"] = status_filetran
                    filesize = 0
                    if size == sent:
                        filesize = size
                    result_uc, data_uc = orch_dbm.update_server_vnfimage(mydb, vnfimage_t, filesize)
                    if result_uc < 0:
                        log.error("Failed to update server_vnfimage : %s %s" % (result_uc, data_uc))
                    log.debug("__________ PROGRESS %s [%s] : %s / %s" % (filename, status_filetran, sent, size))
            # callback END

            log.debug("__________6. 이미지 전송 실행 START : %s %s" % (location, mount_location))

            scp = None
            try:
                ssh.connect(ob_data["mgmtip"], port=9922)
                scp = SCPClient(ssh.get_transport(), progress=callback_deploy_progress)
                scp.put(mount_location, location)
            except Exception, e:
                log.error("__________ SCP 전송에러  %s" % str(e))
                raise Exception(ImageStatus.ERROR, str(e))
            finally:
                if scp is not None:
                    scp.close()
                if ssh is not None:
                    ssh.close()

            if e2e_log:
                e2e_log.job('Transfer Image File', CONST_TRESULT_SUCC, tmsg_body="location : %s" % location)

            # 7. VNFM-IMG-1 재요청
            result, deploy_img_data = myvnfm.get_deployed_images()
            if result < 0:
                log.error("Failed to get deployed images %s %s" % (result, deploy_img_data))
            log.debug("__________7. VNFM-IMG-1 재요청 : %s %s" % (result, deploy_img_data))

            if "images" in deploy_img_data:
                for img_dict in deploy_img_data["images"]:
                    if img_dict["location"] == vdud_image_t["location"]:
                        if "status" not in img_dict:
                            raise Exception(ImageStatus.ERROR, "NOT exist 'status' item from [VNFM-IMG-1] API")
                        status_val = img_dict["status"]
                        vnfm_img_dict = img_dict
                        break
                log.debug("__________ 7.1. status_val = %s" % status_val)
                if status_val is None:
                    raise Exception(ImageStatus.ERROR, "No data in deployed image list received from vnfm")
            else:
                raise Exception(ImageStatus.ERROR, "The data in deployed image list received from vnfm is wrong")

        status_arr = status_val.split("__")
        if status_arr[0] != "true":
            log.error("Need to Check status from vnfm")
            raise Exception(ImageStatus.ERROR, "The status value from vnfm is wrong. NEED to CHECK!")

        if status_arr[1] == "false":
            # 8. VIM 등록
            # API : VNFM-IMG-2
            # POST http://ipv4_addr:9014/ktvnfm/v1/image

            # 진행상태 업데이트
            vnfimage_t["status"] = ImageStatus.VIMREG_start
            result_u, data_u = orch_dbm.update_server_vnfimage(mydb, vnfimage_t)
            if result_u < 0:
                log.error("Failed to update server_vnfimage : %s %s" % (result_u, data_u))

            # 8.1. VNFM-IMG-2 요청
            result, vim_image_res = myvnfm.deploy_image(vdud_image_t)
            if result < 0:
                log.error("Failed to deploy image via vnfm %s %s" % (result, vim_image_res))
                raise Exception(ImageStatus.ERROR_VIM, vim_image_res)
            log.debug("__________8.1. VNFM-IMG-2 요청 : %s %s" % (result, vim_image_res))

            if e2e_log:
                e2e_log.job('VIM 등록', CONST_TRESULT_SUCC, tmsg_body="")

            # 진행상태 업데이트
            vnfimage_t["status"] = ImageStatus.VIMREG_end
            result_u, data_u = orch_dbm.update_server_vnfimage(mydb, vnfimage_t)
            if result_u < 0:
                log.error("Failed to update server_vnfimage : %s %s" % (result_u, data_u))

            # 8.2. tb_vim 조회 : vimseq
            result, vim_r = orch_dbm.get_vim_serverseq(mydb, ob_data["serverseq"])
            if result < 0:
                log.error("Failed to get vim record , serverseq = %s : %s" % (ob_data["serverseq"], vim_r))
                raise Exception(ImageStatus.ERROR_VIM, vim_image_res)
            log.debug("__________8.2. tb_vim 조회 : vimseq : %s %s" % (result, vim_r))

            # 8.3. tb_vim_image에 vim정보 저장
            vim_image_data = {"vimseq":vim_r[0]["vimseq"], "vimimagename":vdud_image_t["name"]}
            vim_image_data["uuid"] = vim_image_res["vim_image"]["uuid"]
            vim_image_data["imageseq"] = vnfimage_t["vnfimageseq"]
            vim_image_data["createdyn"] = False

            result, vimimageseq = orch_dbm.insert_vim_image(mydb, vim_image_data)
            if result < 0:
                log.error("Failed to insert vim_image record : %s %s" % (result, vimimageseq))
                raise Exception(ImageStatus.ERROR_VIM, vimimageseq)
            log.debug("__________8.3. tb_vim_image에 vim정보 저장 : %s %s" % (result, vimimageseq))

            if e2e_log:
                e2e_log.job('Insert vim image data to DB', CONST_TRESULT_SUCC, tmsg_body="vimimageseq : %s" % str(vimimageseq))

        else:
            # 예외사항처리
            # - VIM 등록요청까지 정상적으로 되었는데, 그 후에 난 예외사항으로 ERROR처리 된후, 나중에 재배포 요청을 받을경우,
            # vnfm에서 status를 false__true로 줘서 배포 후 VNFM-IMG-1 재요청하면 true__true 가 되어서 DB에 vim_image정보 등록이 되어야하는 경우
            # => true로 오더라도 tb_vim_image에 정상적으로 정보가 있는지 확인필요

            # tb_vim 조회 : vimseq
            result, vim_r = orch_dbm.get_vim_serverseq(mydb, ob_data["serverseq"])
            if result <= 0:
                log.error("Failed to get vim record , serverseq = %s : %s" % (ob_data["serverseq"], vim_r))
                raise Exception(ImageStatus.ERROR_VIM, vim_r)

            # tb_vim_image 에 이미 등록되있는지 중복체크
            result, vim_image_r = orch_dbm.get_vim_images(mydb, vim_r[0]["vimseq"])
            if result < 0:
                log.error("Failed to get vim_image record, %s %s" % (result, vim_image_r))
                return result, vim_image_r

            if "vim_image" in vnfm_img_dict and "uuid" in vnfm_img_dict["vim_image"]:
                for vim_image in vim_image_r:
                    if vim_image["uuid"] == vnfm_img_dict["vim_image"]["uuid"]:
                        # 이미 존재
                        break
                else:
                    # tb_vim_image에 vim정보 저장
                    vim_image_data = {"vimseq":vim_r[0]["vimseq"], "vimimagename":vdud_image_t["name"]}
                    vim_image_data["uuid"] = vnfm_img_dict["vim_image"]["uuid"]
                    vim_image_data["imageseq"] = vnfimage_t["vnfimageseq"]
                    vim_image_data["createdyn"] = False

                    result, vimimageseq = orch_dbm.insert_vim_image(mydb, vim_image_data)
                    if result < 0:
                        log.error("Failed to insert vim_image record : %s %s" % (result, vimimageseq))
                        return result, vimimageseq
                    log.debug("__________ tb_vim_image에 vim정보 저장 : %s %s" % (result, vimimageseq))
                    if e2e_log:
                        e2e_log.job('Insert vim image data to DB : 예외사항', CONST_TRESULT_SUCC, tmsg_body="vimimageseq : %s" % str(vimimageseq))

        # 9. 결과 전송
        # 성공하면 배포완료 상태 업데이트 후 리턴
        vnfimage_t["status"] = ImageStatus.COMPLETE
        result_u, data_u = orch_dbm.update_server_vnfimage(mydb, vnfimage_t)
        if result_u < 0:
            log.error("Failed to update server_vnfimage : %s %s" % (result_u, data_u))
        log.debug("__________9. 결과 전송 END")

        if e2e_log:
            e2e_log.job('Success to deploy vnf image', CONST_TRESULT_SUCC, tmsg_body="")
            e2e_log.finish(CONST_TRESULT_SUCC)

        return 200, "OK"

    except Exception, ex:
        if len(ex.args) == 2:
            err_code, err_msg = ex
            log.error("Exception for deploying vnf-image : %s %s" % (err_code, err_msg))
            # 실패하면 error 상태 업데이트 후 리턴
            error_status = err_code
        else:
            log.error("Exception for deploying vnf-image(P) : %s" % str(ex))
            error_status = ImageStatus.ERROR

        if vnfimage_t is not None:
            vnfimage_t["status"] = error_status
            result_u, data_u = orch_dbm.update_server_vnfimage(mydb, vnfimage_t)
            if result_u < 0:
                log.error("Failed to update server_vnfimage : %s %s" % (result_u, data_u))

        if e2e_log:
            e2e_log.job('Failed to deploy vnf image', CONST_TRESULT_FAIL, tmsg_body="Result : %s" % ex)
            e2e_log.finish(CONST_TRESULT_FAIL)

        return -500, "FAIL"


def get_vdud_image_list_by_vnfd_id(mydb, vnfd_id):
    """
        vnfd_id 에 해당하는 image 목록을 조회한다.
        단, tb_nfcatalog 와 tb_vdud 의 관계가 1:N인데... 1:1로 가정하고 처리된다.
    :param mydb:
    :param vnfd_id:
    :return:
    """

    result, vdud_t = orch_dbm.get_vdud_by_vnfd_id(mydb, vnfd_id)
    if result < 0:
        return result, vdud_t

    result, contents = orch_dbm.get_vdud_image_list(mydb, vdud_t["vdudseq"])
    # if result < 0:
    #     return result, contents

    return result, contents


def get_server_vnfimage_list(mydb, onebox_id):

    result, content = orch_dbm.get_server_vnfimage(mydb, {"serverseq": onebox_id})
    # if result < 0:
    #     return result, content

    return result, content


def get_deployed_and_deployable_list(mydb, serverseq):
    result, content = orch_dbm.get_deployed_and_deployable_list(mydb, serverseq)

    return result, content


def save_patch_file(mydb, img_data):

    """
        UI에서 patch file 등록 요청을 받아서 DB에 저장
    :param mydb:
    :param img_data:
    :return:
    """

    cfgManager = ConfigManager.get_instance()
    config = cfgManager.get_config()
    MOUNT_PATH = config.get('image_mount_path', "")
    REAL_PATH = config.get('image_real_path', "")

    location = img_data["location"]
    location = location.replace(REAL_PATH, MOUNT_PATH)

    log.debug("__________ 파일서버 마운트 경로 : %s" % location)

    paths = os.path.split(location)

    # 1. 등록
    # 1.1. 파일 존재 확인
    is_exist = os.path.exists(location)
    #     - 없으면 : NONE
    if not is_exist:
        log.debug("__________ 패치파일이 존재하지 않음!!!")
        return 200, "NONE"
    #     - 있으면 file size get
    file_size = os.path.getsize(location)
    if int(img_data.get("filesize", 0)) == 0:
        img_data["filesize"] = file_size

    # 파일 압축을 푼다.
    log.debug("__________ 압축풀기 시작")
    version_dep_path = None
    with tarfile.open(location, "r:*") as tar:
        for tarinfo in tar:
            if tarinfo.name.find("version.dep") >= 0:
                version_dep_path = tarinfo.name
                log.debug("__________ version_dep_path = %s" % version_dep_path)
                tar.extract(tarinfo, paths[0])

    # version.dep 파일을 읽어서 버젼 정보를 가져온다.
    vd_path = paths[0] + "/" + version_dep_path
    f = open(vd_path, "r")
    dep_info = f.read()
    f.close()

    dep_info = json.loads(dep_info)
    log.debug("__________ version.dep 정보 : %s" % dep_info)

    import shutil
    shutil.rmtree(os.path.split(vd_path)[0])

    if "update_version" in dep_info:
        if dep_info["update_version"].get("onebox-vnfm", None):
            img_data["vnfm_version"] = dep_info["update_version"]["onebox-vnfm"]
        if dep_info["update_version"].get("onebox-agent", None):
            img_data["agent_version"] = dep_info["update_version"]["onebox-agent"]
    log.debug("__________ update_version >> img_data : %s" % img_data)

    target_list = []
    if "target_version" in dep_info:
        if dep_info["target_version"].get("onebox-vnfm", None):
            for version in dep_info["target_version"]["onebox-vnfm"]:
                target_list.append({"category":"vnfm", "version":version})
        if dep_info["target_version"].get("onebox-agent", None):
            for version in dep_info["target_version"]["onebox-agent"]:
                target_list.append({"category":"agent", "version":version})
    log.debug("__________ target_list : %s" % target_list)

    # 1.2. DB에 등록 (tb_patch)
    result, patch_t = orch_dbm.get_patch_file(mydb, {"location":img_data["location"]})
    if result == 0:
        result, patch_seq = orch_dbm.insert_patch(mydb, img_data)
        if result < 0:
            log.error("Failed to insert patch record : %s" % img_data)
            return result, patch_seq
        else:
            log.debug("Inserted patch record")

            for target in target_list:
                target["patch_seq"] = patch_seq
                result, patch_target_seq = orch_dbm.insert_patch_target(mydb, target)

            return 200, "OK"

    elif result > 0:
        img_data["patch_seq"] = patch_t["patch_seq"]
        result, patch_seq = orch_dbm.update_patch(mydb, img_data)
        if result < 0:
            log.error("Failed to update patch record : %s" % img_data)
            return result, patch_seq
        else:
            log.debug("Updated patch record")

            orch_dbm.delete_patch_target(mydb, {"patch_seq":patch_t["patch_seq"]})

            for target in target_list:
                target["patch_seq"] = patch_t["patch_seq"]
                result, patch_target_seq = orch_dbm.insert_patch_target(mydb, target)

            return 200, "OK"
    else:
        return result, patch_t


def deploy_patch_file(mydb, patch_data, use_thread=True):
    try:
        result, server_info = orch_dbm.get_server_id(mydb, patch_data["onebox_id"])
        if result < 0:
            log.error("Failed to get server info : %s, Error : %s" % (patch_data["onebox_id"], server_info))
            raise Exception("DB에서 One-Box정보를 가져오는 중 에러가 발생했습니다.")

        if server_info['status'] == SRVStatus.DSC:
            log.error("The One-Box is not connected. Check One-Box: status = %s, action = %s" % (server_info['status'], server_info['action']))
            raise Exception("One-Box가 Disconnected 되어 있습니다. One-Box 상태를 확인하세요.")

        if server_info['action'] is None or server_info['action'].endswith("E"):
            pass
        else:
            log.error("The One-Box is in Progress for another action: status = %s, action = %s" % (server_info['status'], server_info['action']))
            raise Exception("다른 Action이 진행 중입니다. One-Box 상태를 확인하세요.")

        if server_info["nsseq"] is not None:
            nsr_result, nsr_data = orch_dbm.get_nsr_id(mydb, server_info["nsseq"])
            if nsr_result <= 0:
                log.error("failed to get NSR Info from DB : %d %s" % (nsr_result, nsr_data))
                raise Exception("DB정보를 가져오는 중 에러가 발생했습니다. 다시 시도해주세요.")

            if nsr_data['action'] is None or nsr_data['action'].endswith("E"):
                pass
            else:
                log.error("The NS is in Progress for another action: status= %s action= %s" % (nsr_data['status'], nsr_data['action']))
                raise Exception("다른 Action이 진행 중입니다. NSR 상태를 확인하세요.")

            for vnf_data in nsr_data["vnfs"]:
                if vnf_data['action'] is None or vnf_data['action'].endswith("E"):  # NGKIM: Use RE for backup
                    pass
                else:
                    log.error("The VNF is in Progress for another action: status= %s action= %s" % (vnf_data['status'], vnf_data['action']))
                    raise Exception("다른 Action이 진행 중입니다. VNF 상태를 확인하세요.")

        result, patch_info = orch_dbm.get_patch_file(mydb, {"patch_seq":patch_data["patch_id"]})
        if result <= 0:
            log.error("Failed to get patch file info : %s, Error : %s" % (patch_data["patch_id"], patch_info))
            raise Exception("DB에서 Patch File 정보를 가져오는 중 에러가 발생했습니다.")

        orch_dbm.update_server_status(mydb, {"serverseq":server_info["serverseq"], "status":SRVStatus.OBU, "action":"OS"}, is_action=True)

        if use_thread:
            try:
                th = threading.Thread(target=deploy_patch_file_thread, args=(mydb, patch_info, server_info))
                th.start()
            except Exception, e:
                error_msg = "failed to start a thread for deploying patch file for Onebox %s : %s" % (patch_data["onebox_id"], str(e))
                log.error(error_msg)
                raise Exception(error_msg)
        else:
            return deploy_patch_file_thread(mydb, patch_info, server_info)

    except Exception, e:
        log.error("_____ DEPLOY_PATCH_FILE _____ %s" % str(e))
        return -500, str(e)
    return 200, "OK"

status_filetran_old = ""
def deploy_patch_file_thread(mydb, patch_info, server_info):

    result_dict = {}
    ssh = None
    scp = None

    try:
        # patch file transfer
        cfgManager = ConfigManager.get_instance()
        config = cfgManager.get_config()
        MOUNT_PATH = config.get('image_mount_path', "")
        REAL_PATH = config.get('image_real_path', "")

        location = patch_info["location"]
        mount_location = location.replace(REAL_PATH, MOUNT_PATH)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.load_system_host_keys()

        # callback DEFINE
        def callback_patch_deploy_progress(filename, size, sent):
            global status_filetran_old
            status_filetran = ImageStatus.get_filetran_progress(size, sent)
            if status_filetran_old != status_filetran:
                status_filetran_old = status_filetran
                # server status update : 진행률
                orch_dbm.update_server_status(mydb, {"serverseq":server_info["serverseq"], "status":status_filetran})

                log.debug("__________ PROGRESS %s [%s] : %s / %s" % (filename, status_filetran, sent, size))
        # callback END

        try:
            ssh.connect(server_info["mgmtip"], port=9922, timeout=5)
        except Exception, e:
            result_dict["result"] = "FAIL"
            result_dict["msg"] = "접속이 실패했습니다."
            # return 200, result_dict
            raise Exception(str(e))

        patch_paths = os.path.split(location)
        try:
            scp = SCPClient(ssh.get_transport(), progress=callback_patch_deploy_progress)

            # 해당 경로가 있는지 체크
            sftp = paramiko.SFTPClient.from_transport(ssh.get_transport())
            try:
                sftp.chdir(patch_paths[0])
            except:
                sftp.mkdir(patch_paths[0])
                log.debug("__________ 경로 생성 : %s" % patch_paths[0])
            sftp.close()

            # 파일 전송
            scp.put(mount_location, location)
        except Exception, e:
            log.error("__________ Patch File SCP 전송에러  %s" % str(e))
            result_dict["result"] = "FAIL"
            result_dict["msg"] = "패치파일 전송에 실패하였습니다."

            raise Exception(str(e))

        try:
            orch_dbm.update_server_status(mydb, {"serverseq":server_info["serverseq"], "status":SRVStatus.OBP})

            # "tar xvzf /home/onebox/1.2.0_upgrade_patch_test.tar.gz -C /home/onebox/"
            ssh_cmd = "tar xvzf %s -C %s" % (location, patch_paths[0])
            stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=100)
            output = stdout.readlines()
            log.debug("run_ssh_command output= %s" % output)

            if location.find("tar.gz") >= 0:
                patch_dir = location[:location.find("tar.gz")-1]
                # "python /home/onebox/1.2.0_upgrade_patch/OBP_script_main.py"
                ssh_cmd = "python %s/OBP_script_main.py" % patch_dir
                stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=100)
                output = stdout.readlines()
                log.debug("run_ssh_command output= %s" % output)

                # 패치 스크립트 실행 결과:
                # 성공 시: 화면 출력 로그 마지막에 '=====Finished Updating One-Box: SUCCESS=====' 표시 됨.
                # 실패 시: 화면 출력 로그 마지막에 '=====Finished Updating One-Box: FAIL=====' 표시 됨.
                # 패치 실행 불가한 경우: 화면 출력 로그에 '====Aborted Updating: ... =====' 표시 됨.
                SUCCESS_MSG = '=====Finished Updating One-Box: SUCCESS====='
                FAIL_MSG = '=====Finished Updating One-Box: FAIL====='
                ABORT_MSG = '====Aborted Updating'

                out_len = len(output)
                for idx in range(out_len-1, -1, -1):
                    output_tmp = output[idx]
                    if output_tmp.find(SUCCESS_MSG) >= 0:
                        result_dict["result"] = "SUCCESS"
                        result_dict["msg"] = "업데이트 패치가 성공하였습니다."
                    elif output_tmp.find(FAIL_MSG) >= 0:
                        result_dict["result"] = "FAIL"
                        result_dict["msg"] = "업데이트 패치가 실패하였습니다."
                    elif output_tmp.find(ABORT_MSG) >= 0:
                        result_dict["result"] = "ABORT"
                        result_dict["msg"] = "업데이트 패치가 거부되었습니다."

                    if result_dict:
                        break
                else:
                    result_dict["result"] = "NONE"
                    result_dict["msg"] = "업데이트 패치가 정상동작하지 않았습니다."

        except Exception, e:
            log.error("__________ Patch File(tar.gz) 압축 풀기 및 Script 실행 오류 : %s" % str(e))
            result_dict["result"] = "FAIL"
            result_dict["msg"] = "업데이트 패치가 실패하였습니다."
            raise Exception(str(e))

    except Exception, e:
        log.error("_____ DEPLOY_PATCH_FILE _____ %s" % str(e))
        if "msg" not in result_dict:
            result_dict["result"] = "FAIL"
            result_dict["msg"] = "One-Box Update가 실패했습니다."
        return -500, str(e)
    finally:
        if scp is not None:
            scp.close()
        if ssh is not None:
            ssh.close()

        description = "[OBP][%s] %s" % (result_dict["result"], result_dict["msg"])
        orch_dbm.update_server(mydb, {"serverseq":server_info["serverseq"], "status":server_info["status"], "action":"OE", "description":description})

    return 200, result_dict

