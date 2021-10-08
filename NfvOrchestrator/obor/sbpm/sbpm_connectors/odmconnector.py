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

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from sbpm.sbpm_main import get_sbpm_connector

SBPM_CATEGORY = "Odm"
DEFAULT_ONEBOX_TYPE = "General" # or None


class odmconnector(object):
    def __init__(self, req_info):

        result, content = self._check_input(req_info)
        if result < 0:
            raise SyntaxError
        else:
            self.req_dict = req_info

        self.plugin_object = self._get_connector()
        if self.plugin_object is None:
            raise NotImplementedError


    def _check_input(self, req_info):
        log.debug("TODO: Check Input Parameter")
        try:
            if req_info.get("onebox_type") is None:
                return -1, "No One-Box Type given"
            req_info["category"] = SBPM_CATEGORY
        except Exception, e:
            return -1, str(e)

        return 0, "OK"


    def _get_connector(self):
        # 3. request sbpm for sbpm_odm_connector object
        log.debug("get connector object")

        connector = get_sbpm_connector(self.req_dict)

        if connector is None:
            log.debug("No connector found. retry with General Category")
            self.req_dict["onebox_type"] = DEFAULT_ONEBOX_TYPE
            connector = get_sbpm_connector(self.req_dict)

        return connector


    def check_connection(self):
        return 0, "OK: No Action"


    def get_version(self):
        # No Parameters
        result, content = self.plugin_object.get_version()
        log.debug("OUT: result = %d, content = %s" %(result, str(content)))

        return result, content

    def inform_onebox_status(self, onebox_id, onebox_status, e2e_log=None):
        # target_dict = self.req_dict
        result, content = self.plugin_object.inform_onebox_status(onebox_id, onebox_status, e2e_log=None)
        log.debug("OUT: result = %d, content = %s" %(result, str(content)))

        return result, content





