# -*- coding: utf-8 -*-

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from wfm.wfm_main import get_wf_manager

WF_CATEGORY = "WFSvrKtComm"

class server_ktcomm_manager():
    def __init__(self, req_info):
        result, content = self._check_input(req_info)
        if result < 0:
            raise SyntaxError
        else:
            self.req_dict = req_info

        self.plugin_object = self._get_manager()
        if self.plugin_object is None:
            raise NotImplementedError

        # self.plugin_object["host"] = req_info["host"]
        # self.plugin_object["port"] = req_info["port"]


    def _check_input(self, req_info):
        try:
            if req_info.get("onebox_type") is None:
                return -1, "No One-Box Type given"

            req_info["category"] = WF_CATEGORY
        except Exception, e:
            return -1, str(e)

        return 0, "OK"


    def _get_manager(self):
        # 3. request sbpm for sbpm_oba_connector object
        # log.debug("get connector object")

        manager = get_wf_manager(self.req_dict)

        if manager is None:
            log.debug("No connector found. retry with General Category")
            self.req_dict["onebox_type"] = WF_CATEGORY
            manager = get_wf_manager(self.req_dict)

        return manager



    def server_rcc(self, req_info, plugins):
        result, content = self.plugin_object.server_rcc(req_info, plugins)
        return result, content


    def server_rcc_reserve_delete(self, req_info, plugins):
        result, content = self.plugin_object.server_rcc_reserve_delete(req_info, plugins)
        return result, content


    def server_rcc_scheduler(self, redis_key, plugins):
        result, content = self.plugin_object.server_rcc_scheduler(redis_key, plugins)
        return result, content


    def server_change_ip(self, req_info, plugins):
        result, content = self.plugin_object.server_change_ip(req_info, plugins)
        return result, content


    def mms_send(self, req_info, plugins):
        result, content = self.plugin_object.mms_send(req_info, plugins)
        return result, content


    def server_scheduler_sync_mms_send(self, plugins):
        result, content = self.plugin_object.server_scheduler_sync_mms_send(plugins)
        return result, content
