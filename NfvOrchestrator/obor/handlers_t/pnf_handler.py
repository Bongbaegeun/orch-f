# coding=utf-8
# jshwang, 2019.01.10.Thu

from tornado.web import RequestHandler
import handler_utils as util
import orch_schemas
import utils.log_manager as log_manager
from utils import db_conn_manager as dbmanager
log = log_manager.LogManager.get_instance()
from engine import pnf_manager

mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t = "/orch"

OPCODE_PNF_SERVER = "PNF_SERVER"

def url():
    urls = [ (url_base_t + "/server/([^/]*)/pnf", PnfHandler, dict(opCode=OPCODE_PNF_SERVER)) ]

    return urls

class PnfHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode

    def post(self, pnf_server_id=None):
        log.debug("[JS] pnf_server_id: %s" % str(pnf_server_id))

        assert (self.opCode == OPCODE_PNF_SERVER)
        self._http_post_pnf_server(pnf_server_id)

    def _http_post_pnf_server(self, pnf_server_id=None):
        result, http_content = util.format_in(self.request, orch_schemas.pnf_test_server_schema, is_report=False)

        assert (pnf_server_id is not None)
        pnf_server_id = str(pnf_server_id)
        result, data = pnf_manager.new_pnf_server(mydb, http_content, filter_data=pnf_server_id)
        assert(result > 0)
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