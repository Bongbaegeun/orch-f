# -*- coding: utf-8 -*-

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from wfm.wfm_main import get_wf_manager

WF_CATEGORY = "WFAct"

class act_manager():
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

    def action(self, req_info, managers, sub_category=None):
        # 1. check req_info
        # log.debug("IN action(): check input parameters > req_info = %s" %str(req_info))

        result, content = 200, "OK"

        plugins = {}
        plugins['orch_comm'] = managers.get('orch_comm')

        if sub_category == "Backup":
            # 백업
            plugins['wf_obconnector'] = managers.get('wf_obconnector')
            result, content = self.plugin_object.backup(req_info, plugins)
        elif sub_category == "Restore":
            # 복구
            plugins['wf_server_manager'] = managers.get('wf_server_manager')
            plugins['wf_obconnector'] = managers.get('wf_obconnector')
            plugins['wf_monitorconnector'] = managers.get('wf_monitorconnector')
            plugins['wf_Odm'] = managers.get('wf_Odm')
            result, content = self.plugin_object.restore(req_info, plugins)
        elif sub_category == "Reboot":
            # 재시작
            plugins['wf_monitorconnector'] = managers.get('wf_monitorconnector')
            plugins['wf_obconnector'] = managers.get('wf_obconnector')
            plugins['wf_Odm'] = managers.get('wf_Odm')
            result, content = self.plugin_object.reboot(req_info, plugins)
        elif sub_category == "Check":
            # 동작점검
            plugins['wf_obconnector'] = managers.get('wf_obconnector')
            result, content = self.plugin_object.onebox_check(req_info, plugins)
        elif sub_category == "ResetMac":
            # reset mac address
            plugins['wf_server_manager'] = managers.get('wf_server_manager')
            plugins['wf_obconnector'] = managers.get('wf_obconnector')
            plugins['wf_monitorconnector'] = managers.get('wf_monitorconnector')
            plugins['wf_Odm'] = managers.get('wf_Odm')
            result, content = self.plugin_object.reset_mac(req_info, plugins)

        # backup or restore 일때 : base64 인코딩으로 로그가 너무 많아서 뺀다
        # if sub_category == "Backup" or sub_category == "Restore":
        #     pass
        # else:
        #     log.debug("OUT action(): result = %d, content = %s" %(result, str(content)))

        # 5. check result and return them
        return result, content
