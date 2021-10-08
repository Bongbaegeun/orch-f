from sbpm.sbpm_connectors import monitorconnector

def test_create_conn_instance(req_info=None):
    return monitorconnector.monitorconnector(req_info)

if __name__ == "__main__":
    req_info = {"onebox_type": "Pnf"}

    print "Test: Create Connector Instance with %s" %str(req_info)
    conn_instance = test_create_conn_instance(req_info)

    result, output = conn_instance.get_version()
    print "Test get_version: result = %d, %s" %(result, output)

    result, output = conn_instance.get_monitor_vnf_target_seq()
    print "Test get_monitor_vnf_target_seq: result = %d, %s" %(result, output)
