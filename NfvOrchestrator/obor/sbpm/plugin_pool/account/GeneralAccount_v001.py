# -*- coding: utf-8 -*-

from sbpm.plugin_spec.account.GeneralAccountSpec import GeneralAccountSpec

import requests
import json
import sys
import time

from datetime import datetime

# import db.dba_manager as orch_dbm

from utils.config_manager import ConfigManager

from httplib import HTTPException
from requests.exceptions import ConnectionError
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


class GeneralAccount(GeneralAccountSpec):
    def __init__(self):
        self.host = ""
        self.port = ""
        self.name = ""
        self.url = ""
        self.user = ""
        self.passwd = ""
        self.domain = ""
        self.config = ""
        self.debug = ""

        # self.plugin_object["host"] = req_info["host"]
        # self.plugin_object["port"] = req_info["port"]
        #
        # self.name = req_info["name"]
        #
        # if not req_info["url"]:
        #     self.url = self._get_default_url_from_config()
        # else:
        #     self.url = req_info["url"]
        #
        # self.user = req_info["user"]
        # self.passwd = req_info["passwd"]
        #
        # if not req_info["domain"]:
        #     self.domain = self._get_default_domain_from_config()
        # else:
        #     self.domain = req_info["domain"]
        #
        # self.config = req_info["config"]
        # self.debug = req_info["debug"]



    def create_account(self, req_info):

        headers_req = {'Accept': '*/*', 'content-type': 'application/x-www-form-urlencoded'}
        URLrequest = self.get_base_url() + "/registerAccount.json"

        user_name = None

        if 'user_name' not in req_info:
            user_name = req_info.get('id')

        try:
            cfgManager = ConfigManager.get_instance()
            account_config = cfgManager.get_config()
            admin_id = account_config.get(self.name + '_admin_id', "kttest25")
            admin_pw = account_config.get(self.name + '_admin_pw', "1234")
        except Exception, e:
            log.error("failed to get admin_id and admin_pw from config :%s %s" % (self.name, str(e)))
            admin_id = "kttest25"
            admin_pw = "1234"

        payload_req = "domain=" + self.domain + "&userId=" + req_info.get('id')
        payload_req += '&userNm=%s&userPwd=%s&reqUserId=%s&reqPwd=%s&authStart=%s&authEnd=%s' \
                       % (user_name, req_info.get('pw'), admin_id, admin_pw, datetime.now().strftime("%Y%m%d"), '99991231')

        log.debug("Request Body: %s" % str(payload_req))

        try:
            noti_response = requests.post(URLrequest, headers=headers_req, data=payload_req, timeout=5)
        except Exception, e:
            log.exception("failed to create %s account due to HTTP Error %s" % (self.name, str(e)))
            return -500, str(e)

        return self._parse_response(noti_response)


    def get_base_url(self):
        if self.url is not None:
            return self.url
        else:
            return "http://%s:%s/api" %(self.host, self.port)


    def _parse_response(self, response):
        try:
            log.debug("Response = %s" %str(response.text))
            log.debug("Response HTTP Code = %s" %str(response.status_code))

            content = response.json()
            log.debug("_parse_response() response body: %s" %str(content))
        except Exception, e:
            log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'

        try:
            if response.status_code == 200:
                return response.status_code, content
            else:
                if 'error' in content:
                    return -response.status_code, content['error'].get('description')
                else:
                    return -response.status_code, "Invalid Response"
        except (KeyError, TypeError) as e:
            log.exception("_parse_response() exception while parsing response %s" %str(e))

        return -HTTP_Internal_Server_Error, "Unknown Error"
