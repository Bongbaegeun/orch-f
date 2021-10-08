from sbpm.sbpm_connectors import obconnector

def test_get_version():
    print "Test: get_version"
    result, output = obconnector.get_version()
    print "Test Result: %d, %s" %(result, output)

def test_get_status():
    print "Test: get_status()"
    result, output = obconnector.get_status()

    print "Test Result: %d, %s" %(result, output)

if __name__ == "__main__":
    test_get_version()

    test_get_status()

