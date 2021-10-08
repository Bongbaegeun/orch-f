# -*- coding: utf-8 -*-

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from wfm.wfm_main import get_wf_manager

WF_CATEGORY = "WFNsr"

class nsr_manager():
    def __init__(self, req_info):
        result, content = self._check_input(req_info)
        if result < 0:
            raise SyntaxError
        else:
            self.req_dict = req_info

        self.plugin_object = self._get_manager()
        if self.plugin_object is None:
            raise NotImplementedError

    def _check_input(self, req_info):
        # log.debug("TODO: Check Input Parameter")
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
        # log.debug('[svcorder_manager] req_dict = %s' % str(self.req_dict))

        manager = get_wf_manager(self.req_dict)

        if manager is None:
            log.debug("No connector found. retry with General Category")
            self.req_dict["onebox_type"] = WF_CATEGORY
            manager = get_wf_manager(self.req_dict)

        return manager


    def delete_nsr(self, req_info, plugins):
        # 1. check req_info
        # log.debug("IN delete_nsr(): check input parameters")

        result, content = self.plugin_object.delete_nsr(req_info, plugins, need_stop_monitor=True, use_thread=False, tid=None, tpath="", force_flag=True)
        # log.debug("OUT delete_nsr(): result = %d, content = %s" % (result, str(content)))

        # 5. check result and return them
        return result, content
