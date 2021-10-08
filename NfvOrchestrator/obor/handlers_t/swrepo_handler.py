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

import handler_utils as util
import orch_schemas
import utils.log_manager as log_manager
from engine import swrepo_manager
from utils import auxiliary_functions as af

log = log_manager.LogManager.get_instance()

from utils import db_conn_manager as dbmanager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t="/orch"

def url():
    urls = [ (url_base_t + "/swrepo/([^/]*)", SwrepoHandler),
             (url_base_t + "/swrepo", SwrepoHandler)
             ]
    return urls


class SwrepoHandler(RequestHandler):

    def post(self, sw_id=None):

        result, http_content = util.format_in(self.request, orch_schemas.swrepo_sw_schema)
        r = af.remove_extra_items(http_content, orch_schemas.swrepo_sw_schema)

        if r is not None:
            log.warning("http_post_swrepo: Warning: remove extra items ", r)

        result, data = swrepo_manager.new_sw(mydb, http_content)

        if result < 0:
            log.error("http_post_swrepo error %d %s" % (-result, data))
            self._send_response(result, data)
        else:
            log.info("http_post_swrepo: new S/W %s" % data)
            self._send_response(result, {"result":str(data)+" S/W are added."})


    def get(self, sw_id=None):

        if sw_id is not None:
            result, data = swrepo_manager.get_sw_id(mydb, sw_id)

            if result < 0:
                log.error("http_get_swrepo_id error %d %s" % (result, data))
                self._send_response(result, data)
            else:
                af.convert_datetime2str_psycopg2(data)

            self._send_response(result, data)

        else:
            result, content = swrepo_manager.get_sw_list(mydb)

            if result < 0:
                log.error("http_get_swrepo_list Error: %s" %(content))
                self._send_response(result, content)
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

                self._send_response(result, {'sw_list' : content})


    def delete(self, sw_id=None):

        result, data = swrepo_manager.delete_sw_id(mydb, sw_id)
        if result < 0:
            log.error("http_delete_swrepo_sw_id error %d %s" % (-result, data))
            self._send_response(result, data)
        else:
            self._send_response(result, {"result":"S/W " + str(data) + " deleted"})


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        self.set_header('Content-Type', content_type)
        self.finish(body)