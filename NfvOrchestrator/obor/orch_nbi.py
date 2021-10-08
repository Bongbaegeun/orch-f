# -*- coding: utf-8 -*-

##
# kt GiGA One-Box Orchestrator version 1.0
#
# Copyright 2016 kt corp. All right reserved
#
# This is a proprietary software of kt corp, and you may not use this file
# except in compliance with license agreement with kt corp.
#
# Any redistribution or use of this software, with or without modification
# shall be strictly prohibited without prior written approval of kt corp,
# and the copyright notice above does not evidence any actual or intended
# publication of such software.
##

'''
HTTP server implementing the orchestrator API. It will answer to POST, PUT, GET methods in the appropriate URLs
and will use the nfvo.py module to run the appropriate method.
Every YAML/JSON file is checked against a schema in openmano_schemas.py module.  
'''
__author__="Jechan Han"
__date__ ="$30-oct-2015 09:07:15$"


import bottle
import sys
import threading

# NGKIM: 
import handlers.handler_utils as util
import handlers.server_handler as server
import handlers.serviceorder_handler as serviceorder
import handlers.user_handler as user
import handlers.nfv_onboarding_handler as nfv_onboarding
import handlers.nfv_nsr_handler as nfv_nsr
import handlers.license_handler as license
import handlers.swrepo_handler as swrepo

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

global mydb
global url_base
url_base="/orch"
url_base_v20="/orch/v2"

HTTP_Bad_Request =          400
HTTP_Unauthorized =         401 
HTTP_Not_Found =            404 
HTTP_Forbidden =            403
HTTP_Method_Not_Allowed =   405 
HTTP_Not_Acceptable =       406
HTTP_Service_Unavailable =  503 
HTTP_Internal_Server_Error= 500 

class httpserver(threading.Thread):
    def __init__(self, db, admin=False, host='localhost', port=9090):
        #global url_base
        global mydb
        #initialization
        threading.Thread.__init__(self)
        self.host = host
        self.port = port   #Port where the listen service must be started
        if admin==True:
            self.name = "http_admin"
        else:
            self.name = "http"
            #self.url_preffix = 'http://' + host + ':' + str(port) + url_base
            mydb = db
        #self.first_usable_connection_index = 10
        #self.next_connection_index = self.first_usable_connection_index #The next connection index to be used 
        #Ensure that when the main program exits the thread will also exit
        self.daemon = True
        self.setDaemon(True)
        
        log.info("Orch httpserver started!")
         
    def run(self):
        bottle.run(host=self.host, port=self.port, debug=True) #quiet=True
           
def run_bottle(db, host_='localhost', port_=9090):
    '''used for launching in main thread, so that it can be debugged'''
    global mydb
    mydb = db
    bottle.run(host=host_, port=port_, debug=True) #quiet=True
    

@bottle.route(url_base + '/', method='GET')
def http_get():
    try:
        1/0
    except Exception, e:
        log.exception("Test Exception Logging")
        
    return 'works' #TODO: to be completed



@bottle.hook('after_request')
def enable_cors():
    '''Don't know yet if really needed. Keep it just in case'''
    bottle.response.headers['Access-Control-Allow-Origin'] = '*'

   
    
@bottle.error(400)
@bottle.error(401) 
@bottle.error(404) 
@bottle.error(403)
@bottle.error(405) 
@bottle.error(406)
@bottle.error(409)
@bottle.error(503) 
@bottle.error(500)
def error400(error):
    e={"error":{"code":error.status_code, "type":error.status, "description":error.body}}
    bottle.response.headers['Access-Control-Allow-Origin'] = '*'
    return util.format_out(e)

