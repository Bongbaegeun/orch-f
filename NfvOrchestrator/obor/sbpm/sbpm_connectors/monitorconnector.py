import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from sbpm.sbpm_main import get_sbpm_connector

SBPM_CATEGORY = "Orchm"
DEFAULT_ONEBOX_TYPE = "General" # or None

class monitorconnector():
    def __init__(self, req_info):
        result, content = self._check_input(req_info)
        if result < 0:
            raise SyntaxError
        else:
            self.req_dict = req_info

        self.plugin_object = self._get_connector()
        if self.plugin_object is None:
            raise NotImplementedError

        self.plugin_object["host"] = req_info["host"]
        self.plugin_object["port"] = req_info["port"]
    
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

    def check_connection(self):
        return 0, "OK: No Action"


    def get_monitor_vnf_target_seq(self):
        target_dict = self.req_dict
        result, content = self.plugin_object.get_monitor_vnf_target_seq(target_dict)
        log.debug("[get_monitor_vnf_target_seq] OUT: result = %d, content = %s" %(result, str(content)))

        return result, content

        
    def get_version(self):
        # No Parameters
        result, content = self.plugin_object.get_version()
        log.debug("OUT: result = %d, content = %s" %(result, str(content)))

        return result, content


    def first_notify_monitor(self, target_dict):
        result, content = self.plugin_object.first_notify_monitor(target_dict)
        log.debug("[start_monitor_onebox] OUT: result = %d, content = %s" %(result, str(content)))

        return result, content

    def start_monitor_onebox(self, target_dict):
        result, content = self.plugin_object.start_monitor_onebox(target_dict)
        log.debug("[start_monitor_onebox] OUT: result = %d, content = %s" %(result, str(content)))

        return result, content


    def stop_monitor_onebox(self, target_dict):
        result, content = self.plugin_object.stop_monitor_onebox(target_dict)
        log.debug("[stop_monitor_onebox] OUT: result = %d, content = %s" %(result, str(content)))

        return result, content


    def update_monitor_onebox(self, target_dict):
        result, content = self.plugin_object.update_monitor_onebox(target_dict)
        log.debug("[update_monitor_onebox] OUT: result = %d, content = %s" %(result, str(content)))

        return result, content

    def suspend_monitor_onebox(self, target_dict):
        result, content = self.plugin_object.suspend_monitor_onebox(target_dict)
        log.debug("[suspend_monitor_onebox] OUT: result = %d, content = %s" %(result, str(content)))

        return result, content


    def resume_monitor_onebox(self, target_dict, e2e_log):
        result, content = self.plugin_object.resume_monitor_onebox(target_dict, e2e_log)
        log.debug("[resume_monitor_onebox] OUT: result = %d, content = %s" %(result, str(content)))

        return result, content


    def start_monitor_nsr(self, target_dict):
        result, content = self.plugin_object.start_monitor_nsr(target_dict)
        log.debug("[start_monitor_nsr] OUT: result = %d, content = %s" % (result, str(content)))

        return result, content


    def stop_monitor_nsr(self, target_dict):
        result, content = self.plugin_object.stop_monitor_nsr(target_dict)
        log.debug("[start_monitor_nsr] OUT: result = %d, content = %s" % (result, str(content)))

        return result, content


    def resume_monitor_nsr(self, target_dict, e2e_log=None):
        result, content = self.plugin_object.resume_monitor_nsr(target_dict)
        log.debug("[resume_monitor_nsr] OUT: result = %d, content = %s" % (result, str(content)))

        return result, content


    def suspend_monitor_nsr(self, target_dict):
        result, content = self.plugin_object.suspend_monitor_nsr(target_dict)
        log.debug("[suspend_monitor_nsr] OUT: result = %d, content = %s" % (result, str(content)))

        return result, content
