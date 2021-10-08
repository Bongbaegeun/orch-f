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
import engine.ha_manager as ha_manager
import engine.server_manager as server_manager
import orch_schemas
from handlers_t.http_response import HTTPResponse
from utils import auxiliary_functions as af

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils import db_conn_manager as dbmanager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t="/orch"

OPCODE_COMPOSE_HA_POST = "OPCODE_COMPOSE_HA_POST"
OPCODE_CLEAR_HA_POST = "OPCODE_CLEAR_HA_POST"



def url():
    urls = [
             ################   HA 관련   ###########################################################################
             # HA 구성
             (url_base_t + "/compose/ha", HaHandler, dict(opCode=OPCODE_COMPOSE_HA_POST)),

             # HA 구성 해제
             (url_base_t + "/clear/ha", HaHandler, dict(opCode=OPCODE_CLEAR_HA_POST))
             ########################################################################################################

             ]
    return urls

class HaHandler(RequestHandler):

    def __init__(self, application, request, **kwargs):
        self.opCode = None
        self.plugins = None
        super(HaHandler, self).__init__(application, request, **kwargs)

    def initialize(self, opCode, plugins=None):
        self.opCode = opCode
        self.plugins = plugins


    def post(self, id=None):
        log.debug("IN post() with opCode = %s" % str(self.opCode))

        if str(self.opCode).endswith("POST"):
            # HA 구성
            if str(self.opCode) == OPCODE_COMPOSE_HA_POST:
                self._http_post_compose_ha()
            elif str(self.opCode) == OPCODE_CLEAR_HA_POST:
                self._http_post_clear_ha()


    def get(self):
        log.debug("IN get() with opCode = %s" % str(self.opCode))


    def delete(self):
        log.debug("IN delete() with opCode = %s" % str(self.opCode))


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


    # HA 구성
    def _http_post_compose_ha(self):
        result, http_content = util.format_in(self.request, orch_schemas.set_ha_schema)
        log.debug("_____ _http_post_compose_ha : http_content = %s" % http_content)
        if result < 0:
            self._send_response(result, http_content)
            return

        server_use = True
        rt_result, rt_data = None, None

        # HA cluster 구성에 필요한 OneBox중 모두 존재할 경우 처리 되도록 OneBox 존재 체크
        for cl in http_content['cluster_list']:
            # string을 integer로 형변환
            cl['serverseq'] = int(cl['serverseq'])
            cl['cluster_id'] = int(cl['cluster_id'])

            server_result, server_data = server_manager.get_server_with_filter(mydb, cl.get('serverseq'))

            if server_result < 0:
                log.debug("No Search One-Box data")
                server_use = False
                rt_result, rt_data = server_result, server_data[0]
                break

            # log.debug('server_data = %s' %str(server_data))

            cl['nsseq'] = server_data[0]['nsseq']

        if server_use is False:
            self._send_response(rt_result, rt_data)
            return

        # log.debug('setting ha start....')

        # HA cluster 구성 시작
        result, content = ha_manager.set_ha(mydb, http_content)
        if result < 0:
            self._send_response(result, content)
            return
        else:
            self._send_response(result, {"result": 200, "msg": content})
            return


    # HA 구성 해제
    def _http_post_clear_ha(self):
        result, http_content = util.format_in(self.request, orch_schemas.clear_ha_schema)
        log.debug("_____ _http_post_clear_ha : http_content = %s" % http_content)
        if result < 0:
            self._send_response(result, http_content)
            return

        server_use = True
        rt_result, rt_data = None, None

        # HA cluster 구성에 필요한 OneBox중 모두 존재할 경우 처리 되도록 OneBox 존재 체크
        for cl in http_content['cluster_list']:
            # string을 integer로 형변환
            cl['serverseq'] = int(cl['serverseq'])

            server_dict = {}
            server_dict['serverseq'] = cl.get('serverseq')

            server_result, server_data = orch_dbm.get_server_filters_wf(mydb, server_dict)

            if server_result < 0:
                log.debug("No Search One-Box data")
                server_use = False
                rt_result, rt_data = server_result, server_data[0]
                break

            # log.debug('server_data = %s' %str(server_data))

            cl['nsseq'] = server_data[0]['nsseq']
            cl['onebox_id'] = server_data[0]['onebox_id']
            cl['uuid'] = server_data[0]['serveruuid']
            cl['public_ip'] = server_data[0]['publicip']

            if server_data[0]['master_seq'] is None:
                cl['mode'] = 'master'
            else:
                cl['mode'] = 'slave'

        if server_use is False:
            self._send_response(rt_result, rt_data)
            return

        # log.debug('setting ha start....')

        # HA cluster 구성 해제 시작
        result, content = ha_manager.clear_ha(mydb, http_content)
        if result < 0:
            self._send_response(result, content)
            return
        else:
            self._send_response(result, {"result": 200, "msg": content})
            return