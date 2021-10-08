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

import yaml
import json
import threading
import datetime
import sys
from tornado.web import RequestHandler

import orch_schemas
import db.orch_db_manager as orch_dbm

from handlers_t.http_response import HTTPResponse
import handler_utils as util

from utils import db_conn_manager as dbmanager
from utils import auxiliary_functions as af
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from engine import user_manager

global mydb
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

url_base_t = "/orch"

def url():
    urls = [ (url_base_t + "/user/([^/]*)/test", UserHandler, dict(opCode="T1")),
             (url_base_t + "/user/([^/]*)", UserHandler, dict(opCode="N1")),
             (url_base_t + "/user", UserHandler, dict(opCode="N1"))
             ]
    return urls

class UserHandler(RequestHandler):

    def initialize(self, opCode):
        self.opCode = opCode
        
    def post(self, user_id=None):
        arg_value = self.get_argument("user_id", default="none")
        
        log.debug("[HJC] UserHandler.POST() param = %s" %str(user_id))
        log.debug("[HJC] UserHandler.POST() argument = %s" %str(arg_value))
        
        log.debug("[HJC] UserHandler.POST() request = %s" %str(self.request))
        log.debug("[HJC] UserHandler.POST() request.headers = %s" %str(self.request.headers))
        log.debug("[HJC] UserHandler.POST() request.body = %s" %str(self.request.body))
        #log.debug("[HJC] UserHandler.POST() request.json = %s" %str(self.request.json))
        
        log.debug("[HJC] UserHandler.POST() opCode = %s" %self.opCode)
        
        result, http_content = util.format_in(self.request, orch_schemas.user_schema)
        
        log.debug("[HJC] UserHandler.POST() http_content = %s" %str(http_content))
        
        if result < 0:
            self._send_response(result, http_content)
            log.debug("[HJC] UserHandler.POST() OUT -1")
            return
        
        r = af.remove_extra_items(http_content, orch_schemas.user_schema)
        log.debug("[HJC] UserHandler.POST() af.remove_extra_items = %s" %str(r))
        
        if r is not None: 
            log.warning("http_post_user: Warning: remove extra items ", r)
        
        result, data = user_manager.new_user(mydb, http_content['user'])
        
        log.debug("[HJC] UserHandler.POST() after core processing = %s" %str(result))
        
        self._send_response(result, data)
        
        log.debug("[HJC] UserHandler.POST() OUT")

        return

    def get(self, user_id=None):
        '''get user details, can use both id or name'''
        if user_id == None or user_id == "all":
            result, content = orch_dbm.get_user_list(mydb)
            if result < 0:
                log.error("http_get_user_list Error", content)
                data = content
            else:
                for c in content:
                    af.convert_datetime2str_psycopg2(c)
                data={'user_list' : content}
        else:
            result, content = orch_dbm.get_user_id(mydb, user_id)
            
            if result < 0:
                log.error("http_get_user_id error %d %s" % (result, content))
                data = content
            else:
                af.convert_datetime2str_psycopg2(content)
                data={'user' : content}
            
        self._send_response(result, data)
        
        return

    def delete(self, user_id=None):
        '''delete a user from database, can use both id or name'''
        if user_id == None:
            self._send_response(-HTTPResponse.Bad_Request, "No Target")
            return
            
        result, content = user_manager.delete_user(mydb, user_id)
        if result < 0:
            log.error("UserHandler error %d %s" % (-result, content))
            self.set_status(-result)
            data = content
        else:
            data = {"result":"user " + content + " deleted"}
        
        self._send_response(result, data)

    def _send_response(self, result, rsp_body):
        content_type, body = util.format_out(self.request, rsp_body, result)
        
        if result < 0:
            log.error("UserHandler error %d %s" % (result, str(rsp_body)))
            self.set_status(-result)
        else:
            log.info("UserHandler: response %s" % str(rsp_body))
            
        self.set_header('Content-Type', content_type)
        self.finish(body)

            
