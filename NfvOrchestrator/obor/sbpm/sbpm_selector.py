import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


def get_plugin(manager, category):
    # 1. check input parameters

    # 2. Get plugin candidates with category and onebox_type
    if category is not None:
        plugin_list = manager.getPluginsOfCategory(category)
    else:
        plugin_list = manager.getAllPlugins()

    # log.debug('get_plugin : plugin_list = %s' %str(plugin_list))

    # 3. if there are plugins more than one, do something to select one.
    selected_plugin = None

    if plugin_list is None:
        log.error("SBPM is not working")
        return None
    elif len(plugin_list) == 1:
        log.debug("One Plugin is Selected!!! : category |   %s" %str(category))
        selected_plugin = plugin_list[0]
    elif len(plugin_list) > 1:
        log.debug("The number of plugin candidates: %d" %len(plugin_list))
        selected_plugin = plugin_list[0]
    else:
        log.debug("No Candidate found.")
        return None

    return selected_plugin.plugin_object

