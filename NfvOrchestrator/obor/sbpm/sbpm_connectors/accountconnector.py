import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from sbpm.sbpm_main import get_sbpm_connector
from utils.config_manager import ConfigManager
DEFAULT_BASE_URL = "http://211.224.204.244:8080/api"
DEFAULT_BASE_DOMAIN = "kt"

SBPM_CATEGORY = "Account"
DEFAULT_ONEBOX_TYPE = "General" # or None

class accountconnector():

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

    def create_account(self, req_info):
        # No Parameters
        # id, pw, user_name=None
        result, content = self.plugin_object.create_account(req_info)
        log.debug("OUT: result = %d, content = %s" %(result, str(content)))

        return result, content

    # def _get_default_url_from_config(self):
    #     try:
    #         cfgManager = ConfigManager.get_instance()
    #         account_config = cfgManager.get_config()
    #         return account_config.get(self.name + '_url', DEFAULT_BASE_URL)
    #     except Exception, e:
    #         print e
    #         log.exception("Failed to get the default URL of %s Server: %s" % (self.name, str(e)))
    #     return DEFAULT_BASE_URL
    #
    # def _get_default_domain_from_config(self):
    #     try:
    #         cfgManager = ConfigManager.get_instance()
    #         account_config = cfgManager.get_config()
    #         return account_config.get(self.name + '_domain', DEFAULT_BASE_DOMAIN)
    #     except Exception, e:
    #         print e
    #         log.exception("Failed to get the default domain of %s Server: %s" % (self.name, str(e)))
    #     return DEFAULT_BASE_DOMAIN


    # def accountconnector(self, xms):
    #     # No Parameters
    #     result, content = self.plugin_object.accountconnector()
    #     log.debug("OUT: result = %d, content = %s" %(result, str(content)))
    #
    #     return result, content

