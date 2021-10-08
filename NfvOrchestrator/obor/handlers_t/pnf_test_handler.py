# coding=utf-8

from tornado.web import RequestHandler

import datetime
import copy
import handler_utils as util
import orch_schemas
import orch_core as nfvo
import utils.log_manager as log_manager
from utils import db_conn_manager as dbmanager
log = log_manager.LogManager.get_instance()
from engine import pnf_test_manager
from engine import server_manager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()
from utils import auxiliary_functions as af
import db.orch_db_manager as orch_dbm


url_base_t = "/orch"

OPCODE_PNFTEST_SERVER = "SERVER"
OPCODE_NOVATEST_SERVER = "NOVATEST"

OPCODE_VNF_IMAGE_ACTION = "VNF_IMAGE_ACTION"

OPCODE_ODROID_SET = "ODROID_SET"
OPCODE_ODROID_STATUS = "ODROID_STATUS"
OPCODE_ODROID_RESET = "ODROID_RESET"

# status check(icmp/ping/next hop)
OPCODE_SERVER_STT = "STATUS_CHECK"


def url():
    urls = [
        (url_base_t + "/server/([^/]*)/([^/]*)/pnf_test", PnfTestHandler, dict(opCode=OPCODE_PNFTEST_SERVER)),
        (url_base_t + "/server/([^/]*)/nova_test", PnfTestHandler, dict(opCode=OPCODE_NOVATEST_SERVER)),

        # status check(icmp/ping/next hop)
        (url_base_t + "/server/([^/]*)/status_check", PnfTestHandler, dict(opCode=OPCODE_SERVER_STT)),

        # vnf version 자동 업데이트 테스트
        (url_base_t + "/server/([^/]*)/vnf_image_action", VnfImgActHandler, dict(opCode=OPCODE_VNF_IMAGE_ACTION)),

        # Odroid (ArmBox) 테스트 용
        (url_base_t + "/odroid/([^/]*)/set", OdroidHandler, dict(opCode=OPCODE_ODROID_SET)),       # 설치
        (url_base_t + "/odroid/([^/]*)/reset", OdroidHandler, dict(opCode=OPCODE_ODROID_RESET))      # DB reset
        ]
    return urls

class PnfTestHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode

    def post(self, server_id=None, day=None):
        if self.opCode == OPCODE_PNFTEST_SERVER:
            # OneBox Agent에서 호출하는 API
            # tb_server에 필요한 정보를 등록처리.
            self._http_post_pnftest_server(server_id, day)
        elif self.opCode == OPCODE_NOVATEST_SERVER:
            self._http_post_novatest(server_id)
        elif self.opCode == OPCODE_SERVER_STT:
            # status check(icmp/ping/next hop)
            self._http_post_stt(server_id)
        else:
            raise Exception("[BG] Impossible to reach here.")

    # PNF test
    def _http_post_pnftest_server(self, server_id, day):
        server_result, server_data = server_manager.get_server_with_filter(mydb, server_id)
        self._auto_backup_scheduler(server_data[0], day)


    # NOVA test
    def _http_post_novatest(self, server_id=None):
        result, data = pnf_test_manager.nova_test(mydb, filter_data=server_id)

        self._send_response(result, data)


    # status check(icmp/ping/next hop)
    def _http_post_stt(self, server_id=None):
        # log.debug('server_id = %s' %str(server_id))
        result, data = pnf_test_manager.status_check(mydb, filter_data=server_id)

        self._send_response(result, data)

    # def _http_post_pnftest_server(self, server_id=None):
    #     # 1. request body 수용하는 schema 새로 작성
    #     is_report = True
    #     result, http_content = util.format_in(self.request, orch_schemas.pnf_test_server_schema, is_report)
    #
    #     if result < 0:
    #         self._send_response(result, http_content)
    #         return result, http_content
    #
    #     # check server info
    #     chk_result, chk_msg = self._server_info_check(http_content)
    #
    #     if chk_result < 0:
    #         log.error("Invalid One-Box Info: %s" % str(chk_msg))
    #         self._send_response(chk_result, chk_msg)
    #     else:
    #         # 2. tb_server 기본정보 update
    #         if server_id:
    #             server_id = str(server_id)
    #             result, data = pnf_test_manager.new_pnf_test_server(mydb, http_content, filter_data=server_id)
    #         else:
    #             result, data = pnf_test_manager.new_pnf_test_server(mydb, http_content)
    #
    #         if result > 0:
    #             server_result, server_data = server_manager.get_server_with_filter(mydb, data)
    #             data = server_data
    #         elif not is_report and 0 > result != -400:
    #             log.warning("OBA Call Problem for this request \n  - REQUEST URL: %s" %str(self.request.uri))
    #             log.warning("  - REQUEST METHOD: %s" %str(self.request.method))
    #             log.warning("  - BODY: %s" %str(self.request.body))
    #
    #         self._send_response(result, data)

    # auto backup scheduler
    def _auto_backup_scheduler(self, server_data, day=None):
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
            if day is None:
                backup_day = data[0].get('hhmm')
            else:
                backup_day = day

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

            log.debug('insert_data = %s' %str(insert_data))

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


    def _server_info_check(self, server_info):
        if server_info.get("public_ip") is None or len(server_info["public_ip"]) < 5:
            return -400, "Invalid public_ip: %s" % str(server_info.get("public_ip"))
        if server_info.get("public_gw_ip") is None or len(server_info["public_gw_ip"]) < 5:
            return -400, "Invalid public_gw_ip: %s" % str(server_info.get("public_gw_ip"))
        if server_info.get("mgmt_ip") is None or len(server_info["mgmt_ip"]) < 5:
            return -400, "Invalid mgmt_ip: %s" % str(server_info.get("mgmt_ip"))

        return 200, "OK"

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        # log.debug("Response Body: %s" %body)

        self.set_header('Content-Type', content_type)
        self.finish(body)


# VNF Image action test
class VnfImgActHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode

    def post(self, nfseq=None):
        if self.opCode == OPCODE_VNF_IMAGE_ACTION:
            self._http_post_vnf_image_action(nfseq)
        else:
            raise Exception("[BG] Impossible to reach here.")

    def _http_post_vnf_image_action(self, id):
        # id : vnf_id = nfcatseq
        result, http_content = util.format_in(self.request, orch_schemas.vnf_image_action_schema)
        log.debug("_____ _http_post_vnf_image_action : http_content = %s" % http_content)
        if result < 0:
            self._send_response(result, http_content)
            return

        r = af.remove_extra_items(http_content, orch_schemas.vnf_image_action_schema)
        if r is not None: log.error("_http_post_vnf_image_action: Warning: remove extra items: %s", str(r))

        server_result, server_data = server_manager.get_server_with_filter(mydb, http_content["version"]["serverseq"])
        if server_result < 0:
            log.error("Failed to get server Info: %d %s" % (server_result, server_data))
            return server_result, server_data

        log.debug('_http_post_vnf_image_action > server_data = %s' %str(server_data))

        server_manager.vnf_image_sync(mydb, server_data[0])

        self._send_response(200, "OK")
        return

        #
        # if "update" in http_content:
        #     result, content = nfvo.upgrade_vnf_with_image(mydb, id, http_content['update'], tid=http_content.get('tid'), tpath=http_content.get('tpath', ""))
        #     if result < 0:
        #         self._send_response(result, content)
        #         return
        #     else:
        #         self._send_response(result, {"result":200, "msg":content})
        #         return
        # elif "version" in http_content:
        #     result, content = nfvo.get_vnf_image_version_by_vnfm(mydb, id, http_content["version"]["serverseq"])
        #
        #     log.debug("[PNF TEST] _http_post_vnf_image_action > result = %d, content = %s" %(result, str(content)))
        #     self._send_response(result, content)
        #     return


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        # log.debug("Response Body: %s" %body)

        self.set_header('Content-Type', content_type)
        self.finish(body)



class OdroidHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode

    def post(self, server_id=None):
        if self.opCode == OPCODE_ODROID_SET:
            # OneBox Agent에서 호출하는 API
            # tb_server에 필요한 정보를 등록처리.
            self._http_post_odroid_set(server_id)
        elif self.opCode == OPCODE_ODROID_RESET:
            self._http_post_odroid_reset(server_id)
        else:
            raise Exception("[BG] Impossible to reach here.")


    # Odroid set
    def _http_post_odroid_set(self, server_id):
        result, data = pnf_test_manager.odroid_set(mydb, filter_data=server_id)

        self._send_response(result, data)


    # Odroid DB reset
    def _http_post_odroid_reset(self, server_id):
        result, data = pnf_test_manager.odroid_reset(mydb, filter_data=server_id)

        self._send_response(result, data)


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        # log.debug("Response Body: %s" %body)

        self.set_header('Content-Type', content_type)
        self.finish(body)

