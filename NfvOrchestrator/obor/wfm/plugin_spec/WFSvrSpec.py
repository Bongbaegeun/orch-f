# coding=utf-8

class WFSvrSpec(object):

    def new_server(self, req_info, plugins, use_thread=True, forced=False):
        return 0, "Not Implemented"

    def delete_server(self, req_info, plugins):
        return 0, "Not Implemented"

    def get_server_progress_with_filter(self, server_id):
        return 0, "Not Implemented"

    def get_server_backup_data(self, server_id):
        return 0, "Not Implemented"

    def rlt(self, req_info):
        return 0, "Not Implemented"


    def check_onebox_valid(self):
        return 0, "Not Implemented"
