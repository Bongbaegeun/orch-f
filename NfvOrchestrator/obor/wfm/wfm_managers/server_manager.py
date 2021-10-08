# -*- coding: utf-8 -*-

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from wfm.wfm_main import get_wf_manager

WF_CATEGORY = "WFSvr"

class server_manager():
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


    def new_server(self, req_info, plugins, use_thread=True, forced=False):
        # 1. check req_info
        # log.debug("IN new_server(): check input parameters")

        result, content = self.plugin_object.new_server(req_info, plugins, use_thread, forced)
        # log.debug("OUT new_server(): result = %d, content = %s" % (result, str(content)))

        # 5. check result and return them
        return result, content


    def delete_server(self, req_info, plugins):
        # 1. check req_info
        # log.debug("IN delete_server(): check input parameters")

        result, content = self.plugin_object.delete_server(req_info, plugins)
        # log.debug("OUT delete_server(): result = %d, content = %s" % (result, str(content)))

        # 5. check result and return them
        return result, content


    def get_server_backup_data(self, server_id):
        # 1. check req_info
        # log.debug("IN get_server_backup_data(): check input parameters")

        result, content = self.plugin_object.get_server_backup_data(server_id)
        # log.debug("OUT get_server_backup_data(): result = %d, content = %s" % (result, str(content)))

        # 5. check result and return them
        return result, content


    def get_server_progress_with_filter(self, server_id):
        # 1. check req_info
        # log.debug("IN get_server_progress_with_filter(): check input parameters")

        result, content = self.plugin_object.get_server_progress_with_filter(server_id)
        # log.debug("OUT get_server_progress_with_filter(): result = %d, content = %s" % (result, str(content)))

        # 5. check result and return them
        return result, content


    # RLT 정보 확인용
    def rlt(self, req_info={}):
        # 1. check req_info
        # log.debug("IN rlt(): check input parameters")

        # 2. get onebox type. if req_info does not include it, get onebox_type from DB
        if req_info.get("onebox_type") is None:
            log.debug("Skip getting  onebox_type")
            #req_info={"category":WF_CATEGORY, "onebox_type":"KtPnf"}

        # 3. request wfm for wf_server_manager object
        # log.debug("rlt(): get manager object")
        req_info['category'] = WF_CATEGORY

        wf_server_manager=get_wf_manager(req_info)

        # 4. run new_server () with wf_server_manager
        if wf_server_manager is None:
            log.debug("rlt(): failed to get manager object. It is None!")
            return -1, "Not found manager"

        result, content = wf_server_manager.rlt(req_info)
        # log.debug("OUT rlt(): result = %d, content = %s" %(result, str(content)))

        # 5. check result and return them
        return result, content


    def check_onebox_valid(self, req_info={}):
        # 1. check req_info
        # log.debug("IN check_onebox_valid(): check input parameters")

        result, content = self.plugin_object.check_onebox_valid(req_info)
        # log.debug("OUT check_onebox_valid(): result = %d, content = %s" % (result, str(content)))

        # 5. check result and return them
        return result, content


    # def test_new_server():
    #     print "Test: new_server()"
    #     result, output = new_server()
    #
    #     print "Test Result: %d, %s" %(result, output)
    #
    # if __name__ == "__main__":
    #     test_new_server()
