from yapsy.IPlugin import IPlugin
from yapsy.PluginManager import PluginManager

from sbpm.plugin_spec.oba import *
from sbpm.plugin_spec.orchm import *
from sbpm.plugin_spec.odm import *
from sbpm.plugin_spec.redis import *
from sbpm.plugin_spec.ssh import *
from sbpm.plugin_spec.account import *

from sbpm.sbpm_selector import get_plugin

import time
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


def get_sbpm_connector(req_info, mydb=None):
    # log.debug("IN get_sbpm_connector")

    # log.debug('req_info = %s' %str(req_info))

    # 1. Get WFM (test code only)
    sbpm = create_sbpm(req_info)

    # 2. Parse Request Info & Take Workflow category, onebox type, etc.
    if req_info.get("onebox_type") is None:
        log.debug("No Info. about onebox_type")
        onebox_type = "default"
        sbpm_category = None
        log.debug("Need DB access to get req_info. But Skip it for now!!")
    else:
        onebox_type = req_info.get("onebox_type")
        sbpm_category = onebox_type + req_info.get("category")
        # log.debug("sbpm_category = %s" %sbpm_category)

    # 3. Select Plugin for the request and return it as wf_manager
    selected_sbpm_connector = get_plugin(sbpm, sbpm_category)

    log.debug("OUT get_sbpm_connector")
    return selected_sbpm_connector

def create_sbpm(req_info):
    #TODO: Get Plugin Spec List Dynamically from pulgin_spec directory
    categories_filter = {"Default":IPlugin}

    # log.debug("[create_sbpm] req_info : %s" %str(req_info))

    if req_info.get("category") == "Oba":
        categories_filter["GeneralOba"] = GeneralObaSpec.GeneralObaSpec
    elif req_info.get("category") == "Orchm":
        categories_filter["GeneralOrchm"] = GeneralOrchmSpec.GeneralOrchmSpec
    elif req_info.get("category") == "Redis":
        categories_filter["GeneralRedis"] = GeneralRedisSpec.GeneralRedisSpec
    elif req_info.get("category") == "Ssh":
        categories_filter["GeneralSsh"] = GeneralSshSpec.GeneralSshSpec
    elif req_info.get("category") == "Account":
        categories_filter["GeneralAccount"] = GeneralAccountSpec.GeneralAccountSpec
    else:
        categories_filter["GeneralOdm"] = GeneralOdmSpec.GeneralOdmSpec

    # log.debug('[create_sbpm] categories_filter = %s' %str(categories_filter))

    sbpm_manager = PluginManager(categories_filter=categories_filter)
    sbpm_manager.setPluginPlaces(["/root/NfvOrchestrator/obor/sbpm/plugin_pool"])
    sbpm_manager.collectPlugins()

    return sbpm_manager

def reload_plugins(sbpm):
    #TODO
    sbpm.collectPlugins()
