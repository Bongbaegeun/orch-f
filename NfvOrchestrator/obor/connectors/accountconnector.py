#-*- coding: utf-8 -*-
import sys

import requests
from datetime import datetime

import utils.log_manager as log_manager
from db.orch_db import HTTP_Internal_Server_Error, HTTP_Service_Unavailable

log = log_manager.LogManager.get_instance()
from utils.config_manager import ConfigManager
DEFAULT_BASE_URL = "http://211.224.204.244:8080/api"
DEFAULT_BASE_DOMAIN = "kt"

class accountconnector:

    def __init__(self, name, url=None, host=None, port=None, user=None, passwd=None, domain=None, debug=True, config={}):

        self.name = name
        if not url:
            self.url = self._get_default_url_from_config()
        else:
            self.url = url
        self.host = host
        self.port = port
        self.user = user
        self.passwd = passwd
        if not domain:
            self.domain = self._get_default_domain_from_config()
        else:
            self.domain = domain
        self.config = config
        self.debug = debug


    def _get_default_url_from_config(self):
        try:
            cfgManager = ConfigManager.get_instance()
            account_config = cfgManager.get_config()
            return account_config.get(self.name+'_url', DEFAULT_BASE_URL)
        except Exception, e:
            print e
            log.exception("Failed to get the default URL of %s Server: %s" % (self.name, str(e)))
        return DEFAULT_BASE_URL


    def _get_default_domain_from_config(self):
        try:
            cfgManager = ConfigManager.get_instance()
            account_config = cfgManager.get_config()
            return account_config.get(self.name+'_domain', DEFAULT_BASE_DOMAIN)
        except Exception, e:
            print e
            log.exception("Failed to get the default domain of %s Server: %s" % (self.name, str(e)))
        return DEFAULT_BASE_DOMAIN


    def get_base_url(self):
        if self.url is not None:
            return self.url
        else:
            return "http://%s:%s/api" %(self.host, self.port)


    def check_validate(self, id, pw):

        headers_req = {'Accept': '*/*', 'content-type': 'application/x-www-form-urlencoded'}
        URLrequest = self.get_base_url() + "/checkAccount.json"

        payload_req = "domain="+self.domain+"&userId="+id+"&userPwd="+pw

        log.debug("Request Body: %s" %str(payload_req))

        try:
            noti_response = requests.post(URLrequest, headers = headers_req, data=payload_req, timeout=5)
        except Exception, e:
            log.exception("failed to check One-Box's account valid due to HTTP Error %s" %(str(e)))
            return -HTTP_Service_Unavailable, str(e)

        return self._parse_response(noti_response)


    def create_account(self, id, pw, user_name=None):

        headers_req = {'Accept': '*/*', 'content-type': 'application/x-www-form-urlencoded'}
        URLrequest = self.get_base_url() + "/registerAccount.json"

        if user_name is None:
            user_name = id

        try:
            cfgManager = ConfigManager.get_instance()
            account_config = cfgManager.get_config()
            admin_id = account_config.get(self.name+'_admin_id', "kttest25")
            admin_pw = account_config.get(self.name+'_admin_pw', "1234")
        except Exception, e:
            log.error("failed to get admin_id and admin_pw from config :%s %s" % (self.name, str(e)))
            admin_id = "kttest25"
            admin_pw = "1234"

        payload_req = "domain="+self.domain+"&userId="+id
        payload_req += '&userNm=%s&userPwd=%s&reqUserId=%s&reqPwd=%s&authStart=%s&authEnd=%s' \
                       % (user_name, pw, admin_id, admin_pw, datetime.now().strftime("%Y%m%d"), '99991231')

        log.debug("Request Body: %s" %str(payload_req))

        try:
            noti_response = requests.post(URLrequest, headers = headers_req, data=payload_req, timeout=5)
        except Exception, e:
            log.exception("failed to create %s account due to HTTP Error %s" % (self.name, str(e)))
            return -500, str(e)

        return self._parse_response(noti_response)


    def delete_account(self, id):

        headers_req = {'Accept': '*/*', 'content-type': 'application/x-www-form-urlencoded'}
        URLrequest = self.get_base_url() + "/deleteAccount.json"

        try:
            cfgManager = ConfigManager.get_instance()
            account_config = cfgManager.get_config()
            admin_id = account_config.get(self.name+'_admin_id', "kttest25")
            admin_pw = account_config.get(self.name+'_admin_pw', "1234")
        except Exception, e:
            log.error("failed to get admin_id and admin_pw from config :%s %s" % (self.name, str(e)))
            admin_id = "kttest25"
            admin_pw = "1234"

        payload_req = "domain="+self.domain+"&userId="+id
        payload_req += '&reqUserId=%s&reqPwd=%s' % (admin_id, admin_pw)

        log.debug("Request Body: %s" %str(payload_req))

        try:
            noti_response = requests.post(URLrequest, headers = headers_req, data=payload_req, timeout=5)
        except Exception, e:
            log.exception("failed to delete %s account due to HTTP Error %s" % (self.name, str(e)))
            return -500, str(e)

        return self._parse_response(noti_response)

    def view_account(self, id):

        headers_req = {'Accept': '*/*', 'content-type': 'application/x-www-form-urlencoded'}
        URLrequest = self.get_base_url() + "/viewAccount.json"

        try:
            cfgManager = ConfigManager.get_instance()
            account_config = cfgManager.get_config()
            admin_id = account_config.get(self.name+'_admin_id', "kttest25")
            admin_pw = account_config.get(self.name+'_admin_pw', "1234")
        except Exception, e:
            log.error("failed to get admin_id and admin_pw from config :%s %s" % (self.name, str(e)))
            admin_id = "kttest25"
            admin_pw = "1234"

        payload_req = "domain="+self.domain+"&userId="+id
        payload_req += '&reqUserId=%s&reqPwd=%s' % (admin_id, admin_pw)

        log.debug("Request Body: %s" %str(payload_req))

        try:
            noti_response = requests.post(URLrequest, headers = headers_req, data=payload_req, timeout=5)
        except Exception, e:
            log.exception("failed to get %s account due to HTTP Error %s" % (self.name, str(e)))
            return -500, str(e)

        return self._parse_response(noti_response)

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


if __name__ == '__main__':
    # conn = accountconnector("xms")
    # UID = 'kttest012'
    # UPW = '12341234'
    # result, data = conn.check_validate(UID, UPW)
    #
    # print "%d %s" % (result, data)
    pass