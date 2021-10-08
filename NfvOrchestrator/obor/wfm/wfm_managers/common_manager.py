# -*- coding: utf-8 -*-

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from wfm.wfm_main import get_wf_manager

WFM_CATEGORY = "Common"


class common_manager():
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
        log.debug("TODO: Check Input Parameter")
        try:
            if req_info.get("onebox_type") is None:
                return -1, "No One-Box Type given"

            req_info["category"] = WFM_CATEGORY
        except Exception, e:
            return -1, str(e)

        return 0, "OK"

    def _get_manager(self):
        # 3. request sbpm for sbpm_oba_connector object
        log.debug("get connector object")

        manager = get_wf_manager(self.req_dict)

        if manager is None:
            log.debug("No connector found. retry with General Category")
            self.req_dict["onebox_type"] = "Common"
            manager = get_wf_manager(self.req_dict)

        return manager

    def get_version(self):
        # No Parameters
        result, content = self.plugin_object.get_version()
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content

    def getFunc(self, funcNm=None, req_info=None):
        # TODO : 인자값을 name을 주어 받을지 딕셔너리 형태로 받을지에 대한 고민 > 일단은 딕셔너리 형태로 사용
        result, content = self.plugin_object.getFunc(funcNm, req_info)
        log.debug("OUT: getFunc[%s] > result = %d, content = %s" % (str(funcNm), result, str(content)))

        return result, content

    # def start_monitor_onebox(self, target_dict):
    #     result, content = self.plugin_object.start_monitor_onebox(target_dict)
    #     log.debug("OUT: result = %d, content = %s" % (result, str(content)))
    #
    #     return result, content
