import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from sbpm.sbpm_main import get_sbpm_connector

SBPM_CATEGORY = "Oba"
DEFAULT_ONEBOX_TYPE = "General" # or None

class obconnector():
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
        # 3. request sbpm for sbpm_oba_connector object
        log.debug("get connector object")

        connector = get_sbpm_connector(self.req_dict)

        if connector is None:
            log.debug("No connector found. retry with General Category")
            self.req_dict["onebox_type"] = DEFAULT_ONEBOX_TYPE
            connector = get_sbpm_connector(self.req_dict)

        return connector

    def onebox_backup(self, req_info={}):
        # self.plugin_object["name"] = req_info.get("name", None)
        # self.plugin_object["url"] = req_info.get("url", None)
        # self.plugin_object["host"] = req_info.get("host", None)
        # self.plugin_object["port"] = req_info.get("port", None)

        result, content = self.plugin_object.onebox_backup(req_info)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content

    def onebox_restore(self, req_info={}):
        result, content = self.plugin_object.onebox_restore(req_info)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content

    def onebox_reboot(self, req_info={}):
        result, content = self.plugin_object.onebox_reboot(req_info)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content

    def get_onebox_info(self, req_info={}):
        result, content = self.plugin_object.get_onebox_info(req_info)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content


    def wf_check_onebox_agent_progress(self, progress_dict, request_type=None, transaction_id=None):
        result, content = self.plugin_object.wf_check_onebox_agent_progress(progress_dict, request_type, transaction_id)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content

    def connection_check(self, req_info={}):
        result, content = self.plugin_object.connection_check(req_info)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content

    def get_version(self, req_info={}):
        # 1. check req_info
        log.debug("IN: check input parameters")

        # 2. get onebox type. if req_info does not include it, get onebox_type from DB
        if req_info.get("onebox_type") is None:
            log.debug("Skip getting  onebox_type")
            #req_info={"category":WF_CATEGORY, "onebox_type":"KtPnf"}

        # 3. request sbpm for sbpm_oba_connector object
        log.debug("get connector object")
        sbpm_oba_connector=get_sbpm_connector(req_info)

        # 4. run get_version () with sbpm_oba_connector
        if sbpm_oba_connector is None:
            log.debug("failed to get connector object. It is None!")
            return -1, "Not found connector"

        result, content = sbpm_oba_connector.get_version()
        log.debug("OUT: result = %d, content = %s" %(result, str(content)))

        # 5. check result and return them
        return result, content

    def get_status(self, req_info={}):
        # 1. check req_info
        log.debug("IN get_status()")

        # 2. get onebox type. if req_info does not include it, get onebox_type from DB
        req_info={"category":SBPM_CATEGORY, "onebox_type":DEFAULT_ONEBOX_TYPE}

        log.debug("[obconnector] get_status() : req_info = %s" %str(req_info))

        # 3. request sbpm for sbpm_oba_connector
        sbpm_oba_connector=get_sbpm_connector(req_info)

        # 4. run new_server () with wf_server_manager
        if sbpm_oba_connector is None:
            log.debug("failed to get connector object. It is None!")
            return -1, "Not found connector"

        result, content = sbpm_oba_connector.get_status()
        log.debug("OUT: result = %d, content = %s" %(result, str(content)))

        # 5. check result and return them
        return result, content


    # ArmBox
    def provisionning_arm(self, req_info={}):
        result, content = self.plugin_object.provisionning_arm(req_info)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content


    def prov_check_onebox_agent_progress_arm(self, progress_dict, request_type=None, transaction_id=None):
        result, content = self.plugin_object.prov_check_onebox_agent_progress_arm(progress_dict, request_type, transaction_id)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content


    def delete_arm(self, req_info={}):
        result, content = self.plugin_object.delete_arm(req_info)
        log.debug("OUT: result = %d, content = %s" % (result, str(content)))

        return result, content
