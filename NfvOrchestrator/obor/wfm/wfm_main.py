# -*- coding: utf-8 -*-

from yapsy.IPlugin import IPlugin
from yapsy.PluginManager import PluginManager

# from wfm.plugin_spec import CommonSpec
# from wfm.plugin_spec import WFSvrSpec
# from wfm.plugin_spec import WFActSpec
# from wfm.plugin_spec import WFNsrSpec
# from wfm.plugin_spec import WFSvcOrderSpec
# from wfm.plugin_spec import WFSvrArmSpec
# from wfm.plugin_spec import WorkSpec

from wfm.plugin_spec import *
from wfm.wfm_selector import get_plugin

import time
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


def get_wf_manager(req_info):
    # log.debug("IN get_wf_manager()")

    # 1. Get WFM (test code only)
    # TODO : Singleton create 방식으로 변경
    wfm = create_wfm(req_info)

    # log.debug('plugin = %s ' %str(wfm.getPluginByName(name='Common', category='Common')))

    # for plugin in wfm.getAllPlugins():
    #     log.debug('plugin = %s' % str(plugin))

    # 2. Parse Request Info & Take Workflow category, onebox type, etc.
    if req_info.get("onebox_type") is None:
        log.debug("No Info. about onebox_type")
        onebox_type = "default"
        wf_category = None
        log.debug("Need DB access to get req_info. But Skip it for now!!")
    else:
        # onebox_type = req_info["onebox_type"]
        wf_category = req_info["category"]

        # log.debug("wf_category = %s" %wf_category)

    # 3. Select Plugin for the request and return it as wf_manager
    selected_wf_manager = get_plugin(wfm, wf_category)

    # log.debug('1. %s' %str(selected_wf_manager))
    # wfm.removePluginFromCategory(selected_wf_manager, 'Common')
    # log.debug('2. %s' %str(selected_wf_manager))

    # log.debug("OUT get_wf_manager()")
    return selected_wf_manager

def create_wfm(req_info):
    #TODO: Get Plugin Spec List Dynamically from pulgin_spec directory
    """category_filters = {'default' : IPlugin}"""
    category_filters = {}

    if req_info.get('category') == "WFAct":   category_filters["WFAct"] = WFActSpec.WFActSpec
    elif req_info.get('category') == "Common":   category_filters["Common"] = CommonSpec.CommonSpec
    elif req_info.get('category') == "WFSvcOrder": category_filters["WFSvcOrder"] = WFSvcOrderSpec.WFSvcOrderSpec
    elif req_info.get('category') == "WFNsr": category_filters["WFNsr"] = WFNsrSpec.WFNsrSpec
    elif req_info.get('category') == "Work": category_filters["Work"] = WorkSpec.WorkSpec

    # KT 전체 공통
    elif req_info.get('category') == "WFSvrKtComm": category_filters["WFSvrKtComm"] = WFSvrKtCommSpec.WFSvrKtCommSpec

    # Arm-Box
    elif req_info.get('category') == "WFSvrArm": category_filters["WFSvrArm"] = WFSvrArmSpec.WFSvrArmSpec
    elif req_info.get('category') == "WFNsrArm":   category_filters["WFNsrArm"] = WFNsrArmSpec.WFNsrArmSpec

    else :  category_filters["WFSvr"] = WFSvrSpec.WFSvrSpec

    wf_manager = PluginManager(categories_filter=category_filters)

    wf_path = ""

    # TODO : Common 정의 필요(현재 1안 사용) : 1. 공통으로 사용할지, 2. 원박스 종류별로 따로 두어야 할지
    if req_info.get('category') is "Common" or req_info.get('category') is "WFSvcOrder":
        # 공통 : Common, WFSvcOrder
        pass
    elif req_info.get('category') is "Work":
        # 작업 사전 테스트 용
        pass
    else:
        if req_info.get('onebox_type') == "KtPnf":
            wf_path = "/PNF"
        elif req_info.get('onebox_type') == "KtArm":
            wf_path = "/ARM"
        elif req_info.get('onebox_type') == "KtComm":
            wf_path = "/KtComm"
        else:
            pass

    # log.debug("wf_path = %s" %str(wf_path))

    wf_manager.setPluginPlaces(["/root/NfvOrchestrator/obor/wfm/plugin_pool%s" % str(wf_path)])
    wf_manager.collectPlugins()

    return wf_manager

def reload_plugins(wfm):
    #TODO
    wfm.collectPlugins()
