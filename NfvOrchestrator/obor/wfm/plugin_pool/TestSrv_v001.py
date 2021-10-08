# coding=utf-8

from yapsy.IPlugin import IPlugin

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


class TestSvr(IPlugin):
    def new_server(self, iParam=None):
        log.debug("In new_server()")
        return 1, "TODO: Test New Server Done with %s" %str(iParam)

    def check_onebox_valid(self, iParam=None):
        log.debug("In check_onebox_valid")
        return 0, "Test check onebox valid. Not Supported, iParam=%s" %str(iParam)
