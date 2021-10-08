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
import orch_schemas
from utils import auxiliary_functions as af
import utils.log_manager as log_manager

log = log_manager.LogManager.get_instance()

import engine.descriptor_manager as nfvo
from engine.common_manager import get_vnfm_version, sync_image_for_server
from utils import db_conn_manager as dbmanager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t="/orch"


OPCODE_IMAGE_REGLIST_GET = "IMAGE_REG_LIST"
OPCODE_IMAGE_DEPLOYLIST_GET = "IMAGE_DEPLOY_LIST"
OPCODE_IMAGE_ONEBOX_LIST_GET = "IMAGE_ONEBOX_LIST"

OPCODE_IMAGE_CHECK_POST = "IMAGE_CHECK"

OPCODE_IMAGE_SAVE_POST = "IMAGE_SAVE"
OPCODE_IMAGE_DEPLOY_POST = "IMAGE_DEPLOY"
OPCODE_IMAGE_SYNC_GET = "IMAGE_SYNC"

OPCODE_VNFM_VERSION_GET = "VNFM_VERSION"
OPCODE_PATCH_SAVE_POST = "PATCH_SAVE"
OPCODE_PATCH_DEPLOY_POST = "PATCH_DEPLOY"

def url(plugins):
    urls = [ (url_base_t + "/vnfd/([^/]*)", NfvOnboardingHandler),
             (url_base_t + "/vnfd", NfvOnboardingHandler, dict(plugins=plugins)),
             (url_base_t + "/vnfd/vnfdinfo", NfvOnboardingHandler),

             (url_base_t + "/nsd/([^/]*)", NsOnboardingHandler),
             (url_base_t + "/nsd", NsOnboardingHandler),
             (url_base_t + "/nsd/ofvnfs", NsOnboardingHandler),

             (url_base_t + "/vnfm/version/([^/]*)", VnfImageHandler, dict(opCode=OPCODE_VNFM_VERSION_GET)),

             (url_base_t + "/vnfd/image/([^/]*)/reg_list", VnfImageHandler, dict(opCode=OPCODE_IMAGE_REGLIST_GET)),
             (url_base_t + "/vnfd/image/([^/]*)/deploy_list", VnfImageHandler, dict(opCode=OPCODE_IMAGE_DEPLOYLIST_GET)),
             (url_base_t + "/vnfd/image/([^/]*)/onebox_list", VnfImageHandler, dict(opCode=OPCODE_IMAGE_ONEBOX_LIST_GET)),

             (url_base_t + "/vnfd/image/check", VnfImageHandler, dict(opCode=OPCODE_IMAGE_CHECK_POST)),
             (url_base_t + "/vnfd/([^/]*)/image", VnfImageHandler, dict(opCode=OPCODE_IMAGE_SAVE_POST)),
             (url_base_t + "/vnfd/([^/]*)/image/([^/]*)/action", VnfImageHandler, dict(opCode=OPCODE_IMAGE_DEPLOY_POST)),
             (url_base_t + "/vnfd/image/sync/([^/]*)", VnfImageHandler, dict(opCode=OPCODE_IMAGE_SYNC_GET)),

             (url_base_t + "/patch/save", VnfImageHandler, dict(opCode=OPCODE_PATCH_SAVE_POST)),
             (url_base_t + "/patch/deploy", VnfImageHandler, dict(opCode=OPCODE_PATCH_DEPLOY_POST))

             ]
    return urls


class NfvOnboardingHandler(RequestHandler):

    def initialize(self, plugins=None):
        self.plugins = plugins

    def post(self):

        # Web UI에서 요청한 Parameter정보(vnfd)를 schema에 맞게 가져온다.
        result, client_data = util.format_in(self.request, orch_schemas.vnfd_schema)
        if result < 0:
            msg = "vnfd파일의 포멧에 문제가 있습니다."
            self._send_response(result, msg)
            return

        log.debug("[NBI IN] Onboarding VNF: /orch/vnfd")

        # 기본 소스
        result, data = nfvo.new_nfd(mydb, client_data)

        # if client_data['vnf']['name'].find('ARM-') < 0:
        #     # 기본 소스
        #     result, data = nfvo.new_nfd(mydb, client_data)
        # else:
        #     # Arm-Box 용
        #     # result, data = nfvo.new_nfd_armbox(mydb, client_data)
        #     result, data = self.plugins.get('wf_des_manager').new_nfd(client_data, self.plugins)
        #     pass

        if result < 0:
            log.error("[NBI OUT] Onboarding VNF: Error %d %s" %(-result, data))
        else:
            log.debug("[NBI OUT] Onboarding VNF: OK")
        self._send_response(result, data)

    def get(self, vnfd=None):
            
        if vnfd is None:
            log.debug("[NBI IN] Get VNFD List: /orch/vnfd")
            result, content = orch_dbm.get_vnfd_list(mydb, [])

            if result < 0:
                log.error("http_get_vnfd Error", content)
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

                af.convert_str2boolean(content, ('virtualyn','publicyn',))
                data = {'vnfd' : content}
                self._send_response(result, data)
        elif vnfd == "vnfdinfo":
            arg_vnfd_name = self.get_argument("vnfd_name")
            arg_vnfd_version = self.get_argument("vnfd_version")
            log.debug("Requested VNF: %s %s" %(arg_vnfd_name, arg_vnfd_version))
            
            result, content = orch_dbm.get_vnfd_general_info_with_name(mydb, {"vnfd_name": arg_vnfd_name, "vnfd_version": arg_vnfd_version})
            
            if result < 0:
                log.error("http:_get_vnfd_with_name error %d %s" %(result, content))
            else:
                af.convert_datetime2str_psycopg2(content)
                
            self._send_response(result, content)
        else:
            log.debug("[NBI IN] Get VNFD : /orch/vnfd/%s" % str(vnfd))
            result, content = orch_dbm.get_vnfd_id(mydb, vnfd)

            if result < 0:
                log.error("http_get_vnfd_id error %d %s" % (result, content))

            self._send_response(result, content)
            return

    def delete(self, vnfd=None):
        log.debug("[NBI IN] Deleting VNFD: /orch/vnfd/%s" %str(vnfd))
        result, data = nfvo.delete_vnfd(mydb,vnfd)

        if result < 0:
            log.error("[NBI OUT] Deleting VNFD: Error %d %s" %(-result, data))
            self._send_response(result, data)
            return
        else:
            log.debug("[NBI OUT] Deleting VNFD: OK")
            self._send_response(result, {"result":"VNFD " + data + " deleted"})


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        # else:
        #     log.info("Success: response %s" % str(rsp_body))

        self.set_header('Content-Type', content_type)
        self.finish(body)



class NsOnboardingHandler(RequestHandler):

    def post(self, nsd=None):
        log.debug("[NBI IN] Onboarding NS: /orch/nsd")

        if nsd is None:
            #result, client_data = util.format_in(self.request, orch_schemas.nsd_new_schema)
            result, client_data = util.format_in(self.request, orch_schemas.nsd_schema_v04)

            if result < 0:
                msg = "nsd파일의 포멧에 문제가 있습니다."
                self._send_response(result, msg)
                return
            
            result, data = nfvo.new_nsd(mydb, client_data)
            if result < 0:
                log.error("[NBI OUT] Onboarding NS: Error %d %s" %(-result, data))
                self._send_response(result, data)
                return

        elif nsd == "ofvnfs":
            log.debug("ofvnfs IN")
            result, client_data = util.format_in(self.request, orch_schemas.nsd_ofvnfs_new_schema)
            if result < 0:
                self._send_response(result, client_data)
                return
            
            result, data = nfvo.new_nsd_with_vnfs(mydb, client_data['vnf_list'], client_data.get('customer_eng_name'), client_data.get('serverseq'))
            if result < 0:
                self._send_response(result, data)
                return
        else:
            self._send_response(-400, "Invalid Request URL for onboarding NSD")
            return
        
        log.debug("[NBI OUT] Onboarding NS: OK")
        
        return self.get(data);

    def get(self, nsd=None):

        if nsd is not None:
            log.debug("[NBI IN] Get NSD : /orch/nsd/%s" % str(nsd))
            result, content = nfvo.get_nsd_id(mydb, nsd)

            if result < 0:
                log.error("http_get_nsd_id error %d %s" % (-result, content))
                self._send_response(result, content)
                return
            else:
                content = util.secure_passwd(content)
                self._send_response(result, {'nsd' : content})
                return
        else:
            log.debug("[NBI IN] Get NSD List: /orch/nsd")
            result, content = orch_dbm.get_nsd_list(mydb, [])

            if result < 0:
                log.error("http_get_nsd Error", content)
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

                af.convert_str2boolean(content, ('publicyn') )
                self._send_response(result, {'nsd' : content})


    def delete(self, nsd=None):
        log.debug("[NBI IN] Deleting NSD: /orch/nsd/%s" %str(nsd))
        result, data = orch_dbm.delete_nsd(mydb, nsd)

        if result < 0:
            log.error("[NBI OUT] Deleting NSD: Error %d %s" %(-result, data))
            self._send_response(result, data)
            return
        else:
            log.debug("[NBI OUT] Deleting NSD: OK")
            self._send_response(result, {"result":"NSD " + data + " deleted"})


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        # else:
        #     log.info("Success: response %s" % str(rsp_body))

        self.set_header('Content-Type', content_type)
        self.finish(body)


class VnfImageHandler(RequestHandler):

    def __init__(self, application, request, **kwargs):
        self.opCode = None
        super(VnfImageHandler, self).__init__(application, request, **kwargs)

    def initialize(self, opCode):
        self.opCode = opCode

    def get(self, id=None):

        log.debug('request = %s' %str(self.request))

        log.debug("__________ VnfImageHandler get :  opCode=%s" % self.opCode)

        if self.opCode == OPCODE_IMAGE_REGLIST_GET:
            # id : vnfd id = nfcatseq
            result, content = nfvo.get_vdud_image_list_by_vnfd_id(mydb, id)
            if result < 0:
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

                data = {'list' : content}
                self._send_response(result, data)

        elif self.opCode == OPCODE_IMAGE_DEPLOYLIST_GET:
            # id : onebox id = serverseq
            result, content = nfvo.get_server_vnfimage_list(mydb, id)
            if result < 0:
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

                data = {'list' : content}
                self._send_response(result, data)

        elif str(self.opCode) == OPCODE_IMAGE_ONEBOX_LIST_GET:
            # id : onebox id = serverseq
            result, content = nfvo.get_deployed_and_deployable_list(mydb, id)
            if result < 0:
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

                data = {'list' : content}
                self._send_response(result, data)
        elif str(self.opCode) == OPCODE_IMAGE_SYNC_GET:
            try:
                # id : onebox id = serverseq
                result, content = sync_image_for_server(mydb, id)
                if result < 0:
                    self._send_response(result, content)
                    return

                data = {'sync' : content}
                self._send_response(result, data)
            except Exception, e:
                log.error("__________ %s Exception : %s" % (OPCODE_IMAGE_SYNC_GET, str(e)))

        elif str(self.opCode) == OPCODE_VNFM_VERSION_GET:
            # id : onebox id = serverseq
            result, content = get_vnfm_version(mydb, id)
            self._send_response(result, content)


    def post(self, vnfd_id=None, image_id=None):
        log.debug("[NBI IN] VnfImageHandler post : %s" % self.opCode)

        if str(self.opCode) == OPCODE_IMAGE_SAVE_POST:

            if vnfd_id is None:
                return -500, "Need vnfd_id"

            result, img_data = util.format_in(self.request, orch_schemas.vnf_image_file_schema)

            if result < 0:
                msg = "이미지 등록 요청 포멧에 문제가 있습니다."
                self._send_response(result, msg)
                return

            log.debug("__________ VNF Image 등록 : %s" % img_data)
            try:
                result, data = nfvo.save_vnf_image(mydb, vnfd_id, img_data)
                if result < 0:
                    log.error("[NBI OUT] Failed to regist vnf image : Error %d %s" %(-result, data))
                    self._send_response(result, data)
                    return
                self._send_response(result, {"result":data})

            except Exception, e:
                log.error("__________ Exception for save_vnf_image: %s" % str(e))

        elif str(self.opCode) == OPCODE_IMAGE_DEPLOY_POST:
            if vnfd_id is None:
                return -500, "Need vnfd_id"

            if image_id is None:
                return -500, "Need image_id"

            result, req_data = util.format_in(self.request, orch_schemas.vnf_image_deploy_schema)
            if result < 0:
                self._send_response(result, req_data)
                return

            result, data = nfvo.deploy_vnf_image(mydb, vnfd_id, image_id, req_data, tid=req_data.get('tid'), tpath=req_data.get('tpath', ""))
            if result < 0:
                log.error("[NBI OUT] Failed to deploy vnf image : Error %d %s" %(-result, data))
                self._send_response(result, data)
                return

            self._send_response(result, {"result":data})

        elif str(self.opCode) == OPCODE_IMAGE_CHECK_POST:

            result, req_data = util.format_in(self.request, orch_schemas.vnf_image_check_schema)
            if result < 0:
                self._send_response(result, req_data)
                return

            result, check_data = nfvo.check_vnfd_image_name(mydb, req_data)
            if result < 0:
                self._send_response(result, check_data)
                return
            else:
                self._send_response(result, {"result":check_data})

        elif str(self.opCode) == OPCODE_PATCH_SAVE_POST:

            result, patch_data = util.format_in(self.request, orch_schemas.patch_save_schema)

            if result < 0:
                msg = "패치파일 등록 요청 포멧에 문제가 있습니다."
                self._send_response(result, msg)
                return

            log.debug("__________ Patch File 등록 : %s" % patch_data)
            try:
                result, data = nfvo.save_patch_file(mydb, patch_data)
                if result < 0:
                    log.error("[NBI OUT] Failed to regist patch file : Error %d %s" %(-result, data))
                    self._send_response(result, data)
                    return
                self._send_response(result, {"result":data})

            except Exception, e:
                log.error("__________ Exception for save_patch_file: %s" % str(e))

        elif str(self.opCode) == OPCODE_PATCH_DEPLOY_POST:

            result, patch_data = util.format_in(self.request, orch_schemas.patch_deploy_schema)

            if result < 0:
                msg = "패치파일 적용 요청 포멧에 문제가 있습니다."
                self._send_response(result, msg)
                return

            log.debug("__________ Patch 적용 : %s" % patch_data)
            try:
                result, data = nfvo.deploy_patch_file(mydb, patch_data)
                if result < 0:
                    log.error("[NBI OUT] Failed to deploy patch file : Error %d %s" %(-result, data))
                    self._send_response(result, data)
                    return
                self._send_response(result, data)

            except Exception, e:
                log.error("__________ Exception for save_patch_file: %s" % str(e))

        log.debug("[NBI OUT] VnfImageHandler post: OK")


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        self.set_header('Content-Type', content_type)
        self.finish(body)

