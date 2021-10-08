# -*- coding: utf-8 -*-

class GeneralObaSpec(object):
    def get_version(self):
        return 0, "Not Implemented"

    def get_status(self):
        return 0, "Not Implemented"

    def onebox_backup(self, req_info):
        return 0, "Not Implemented"

    def onebox_restore(self, req_info):
        return 0, "Not Implemented"

    def get_onebox_info(self, req_info):
        return 0, "Not Implemented"

    def onebox_reboot(self, req_info):
        return 0, "Not Implemented"

    def wf_check_onebox_agent_progress(self, progress_dict, request_type=None, transaction_id=None):
        return 0, "Not Implemented"

    def connection_check(self, req_info):
        return 0, "Not Implemented"

    def provisionning_arm(self, req_info):
        return 0, "Not Implemented"

    def prov_check_onebox_agent_progress_arm(self, progress_dict, request_type=None, transaction_id=None):
        return 0, "Not Implemented"

    def delete_arm(self, req_info):
        return 0, "Not Implemented"
