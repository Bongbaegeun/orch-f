# -*- coding: utf-8 -*-

from sbpm.plugin_spec.odm.GeneralOdmSpec import GeneralOdmSpec
import requests
import json
import sys
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils.config_manager import ConfigManager
from db.orch_db import HTTP_Internal_Server_Error

# 구현
class GeneralOdm(GeneralOdmSpec):

    def __init__(self):
        self.url = self._get_default_url_from_config()

    def _get_default_url_from_config(self):
        try:
            cfgManager = ConfigManager.get_instance()
            odm_config = cfgManager.get_config()

            return odm_config.get('odm_url')
        except Exception, e:
            log.exception("Failed to get the default URL of Order Manager: %s" %str(e))
            return None

    def get_version(self):
        log.debug("IN get_version()")
        return 1, "v0.0.1"

    def inform_onebox_status(self, onebox_id, onebox_status, e2e_log=None):

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = self.url + "/onebox/status"

        reqDict = {"onebox_id": onebox_id, "status": onebox_status}
        payload_req = json.dumps(reqDict)
        log.debug("Request Body: %s" %str(payload_req))

        try:
            log.debug("URLrequest = %s" % URLrequest)
            noti_response = requests.put(URLrequest, headers = headers_req, data=payload_req, timeout=5, verify=False)
        except Exception, e:
            log.exception("failed to inform One-Box's status due to HTTP Error %s" %(str(e)))
            return -500, str(e)

        return self._parse_response(noti_response)

    def _parse_response(self, odm_response):
        try:
            log.debug("Response from Order Manager = %s" %str(odm_response.text))
            log.debug("Response HTTP Code from Order Manager = %s" %str(odm_response.status_code))

            content = odm_response.json()
            log.debug("_parse_response() response body: %s" %str(content))
        except Exception, e:
            log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'

        try:
            if odm_response.status_code == 200:
                return odm_response.status_code, content
            else:
                if 'error' in content:
                    return -odm_response.status_code, content['error'].get('description')
                else:
                    return -odm_response.status_code, "Invalid Response"
        except (KeyError, TypeError) as e:
            log.exception("_parse_response() exception while parsing response %s" %str(e))

        return -HTTP_Internal_Server_Error, "Unknown Error"