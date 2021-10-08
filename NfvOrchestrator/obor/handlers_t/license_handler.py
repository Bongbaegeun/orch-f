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
from engine import license_manager
from http_response import HTTPResponse
from utils import auxiliary_functions as af
log = log_manager.LogManager.get_instance()

from utils import db_conn_manager as dbmanager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t="/orch"

OPCODE_LICENSE = "LICENSE"
OPCODE_LICENSE_ACTION = "LICENSE_ACTION"

def url():
    urls = [ (url_base_t + "/license/([^/]*)/action", LicenseHandler, dict(opCode=OPCODE_LICENSE_ACTION)),
             (url_base_t + "/license", LicenseHandler, dict(opCode=OPCODE_LICENSE)),
             (url_base_t + "/license/([^/]*)", LicenseHandler, dict(opCode=OPCODE_LICENSE))
             ]
    return urls


class LicenseHandler(RequestHandler):

    def __init__(self, application, request, **kwargs):
        self.opCode = None
        super(LicenseHandler, self).__init__(application, request, **kwargs)


    def initialize(self, opCode):
        self.opCode = opCode


    def post(self, license=None):

        if self.opCode == OPCODE_LICENSE:
            self._http_post_license()
        elif self.opCode == OPCODE_LICENSE_ACTION:
            self._http_post_license_action(license)


    def _http_post_license(self):
        result, http_content = util.format_in(self.request, orch_schemas.license_schema)
        r = af.remove_extra_items(http_content, orch_schemas.license_schema)

        if r is not None:
            log.warning("http_post_license: Warning: remove extra items ", r)

        result, data = license_manager.new_license(mydb, http_content)

        if result < 0:
            log.error("http_post_license error %d %s" % (-result, data))
            self._send_response(result, data)
        else:
            log.info("http_post_license: new license %s" % data)
            self._send_response(result, str(data)+" licenses are added.")

    def _http_post_license_action(self, license):

        result, http_content = util.format_in(self.request, orch_schemas.license_action_schema)
        r = af.remove_extra_items(http_content, orch_schemas.license_action_schema)

        if r is not None:
            log.warning("http_post_license_action: Warning: remove extra items ", r)

        if 'check_license' in http_content:
            result = license_manager.check_license(mydb, license)
            if result:
                self._send_response(result, {"check_license":"OK"})
                return
            else:
                self._send_response(result, {"check_license":"NOK"})
                return
        else:
            log.error("http_post_license_action error")
            self._send_response(HTTPResponse.Bad_Request, "Not Supported Request")


    def get(self, license=None):

        if license is not None:
            result, content = license_manager.get_license_list(mydb, license)

            if result < 0:
                log.error("http_get_license_filter error %d %s" % (result, content))
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

            self._send_response(result, {'license_list' : content})

        else:
            result, content = license_manager.get_license_list(mydb)

            if result < 0:
                log.error("http_get_license_list Error: %s" %(content))
                self._send_response(result, content)
                return
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)

            self._send_response(result, {'license_list' : content})


    def delete(self, license=None):

        result, content = license_manager.delete_license(mydb, license)
        if result < 0:
            log.error("http_delete_license_filter error %d %s" % (-result, content))
            self._send_response(result, content)
        else:
            self._send_response(result, {"result":"license " + str(content) + " deleted"})


    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)

        if result < 0:
            log.error("Error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("Success: response %s" % str(rsp_body))

        self.set_header('Content-Type', content_type)
        self.finish(body)