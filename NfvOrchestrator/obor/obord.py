#!/usr/bin/env python
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
One-Box Orchestrator (OBOR) Server
Main program that implements a reference NFVO (Network Functions Virtualisation Orchestrator).

It loads the configuration file and launches the http_server thread that will listen requests using OBOR Orch API.
'''
__author__="Jechan Han"
__date__ ="$15-feb-2016 17:47:29$"
__version__="0.0.1"
version_date="Feb 2016"     #hjc
database_version="0.4"      #expected database schema version, hjc

import getopt
import os
import sys
import time

import yaml
from jsonschema import validate as js_v, exceptions as js_e

from orch_schemas import config_schema
# import orch_nbi
from orch_nbi_t import httpserver

import db.orch_db_manager as orch_dbm
from db import orch_db

from utils import auxiliary_functions as af
from utils.config_manager import ConfigManager
import utils.log_manager as log_manager
from utils.aes_chiper import AESCipher

import orch_core
from engine import event_manager
from engine import server_manager
from engine import descriptor_manager
from engine import common_manager
from engine import nsr_manager

global global_config


###     Work Flow Managers      #########################################
from utils.config_manager import ConfigManager
from wfm.wfm_managers import common_manager as wfm_common_manager
from wfm.wfm_managers import svcorder_manager as wfm_svcorder_manager
from wfm.wfm_managers import server_manager as wfm_svr_manager
from wfm.wfm_managers import act_manager as wfm_act_manager
from wfm.wfm_managers import nsr_manager as wfm_nsr_manager
from wfm.wfm_managers import work_manager as wfm_work_manager

# KT All Common
from wfm.wfm_managers import server_ktcomm_manager as wfm_svr_ktcomm_manager

# ArmBox
from wfm.wfm_managers import server_arm_manager as wfm_svr_arm_manager
from wfm.wfm_managers import nsr_arm_manager as wfm_nsr_arm_manager

# from utils.config_manager import ConfigManager

from sbpm.sbpm_connectors import obconnector as wfm_obconnector
from sbpm.sbpm_connectors import odmconnector as wfm_odmconnector
from sbpm.sbpm_connectors import monitorconnector as wfm_monitorconnector
from sbpm.sbpm_connectors import redisconnector as wfm_redisconnector
from sbpm.sbpm_connectors import sshconnector as wfm_sshconnector


def load_configuration(configuration_file):
    default_tokens ={'http_port':9090, 'http_host':'localhost'}
    try:
        #Check config file exists
        if not os.path.isfile(configuration_file):
            return (False, "Error: Configuration file '"+configuration_file+"' does not exists.")
            
        #Read file
        (return_status, code) = af.read_file(configuration_file)
        if not return_status:
            return (return_status, "Error loading configuration file '"+configuration_file+"': "+code)
        #Parse configuration file
        try:
            config = yaml.load(code)
        except yaml.YAMLError, exc:
            error_pos = ""
            if hasattr(exc, 'problem_mark'):
                mark = exc.problem_mark
                error_pos = " at position: (%s:%s)" % (mark.line+1, mark.column+1)
            return (False, "Error loading configuration file '"+configuration_file+"'"+error_pos+": content format error: Failed to parse yaml format")

        #Validate configuration file with the config_schema
        try:
            js_v(config, config_schema)
        except js_e.ValidationError, exc:
            error_pos = ""
            if len(exc.path)>0: error_pos=" at '" + ":".join(map(str, exc.path))+"'"
            return False, "Error loading configuration file '"+configuration_file+"'"+error_pos+": "+exc.message 
        
        #Check default values tokens
        for k,v in default_tokens.items():
            if k not in config: config[k]=v
    
    except Exception,e:
        return (False, "Error loading configuration file '"+configuration_file+"': "+str(e))
                
    return (True, config)

def usage():
    print "Usage: ", sys.argv[0], "[options]"
    print "      -v|--version: prints current version"
    print "      -c|--config [configuration_file]: loads the configuration file (default: obord.cfg)"
    print "      -h|--help: shows this help"
    print "      -p|--port [port_number]: changes port number and overrides the port number in the configuration file (default: 9090)"
    print "      -P|--adminport [port_number]: changes admin port number and overrides the port number in the configuration file (default: 9095)"
    print "      -V|--vnf-repository: changes the path of the vnf-repository and overrides the path in the configuration file"
    return

if __name__=="__main__":
    # Read parameters and configuration file 
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvc:V:p:P:", ["config", "help", "version", "port", "vnf-repository", "adminport"])
    except getopt.GetoptError, err:
        #print "Error:", err # will print something like "option -a not recognized"
        usage()
        sys.exit(2)
    
    #log = logger.singleton(logger.ko_logger).get_instance()
    log = log_manager.LogManager.get_instance()
    log.info("Obor Daemon Starts! %s" % "for test")

    port=None
    port_admin = None
    config_file = 'obord.cfg'
    vnf_repository = None
    
    for o, a in opts:
        if o in ("-v", "--version"):
            #print "OBOR version", __version__, version_date
            #print "(c) Copyright KT"
            sys.exit()
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-V", "--vnf-repository"):
            vnf_repository = a
        elif o in ("-c", "--config"):
            config_file = a
        elif o in ("-p", "--port"):
            port = a
        elif o in ("-P", "--adminport"):
            port_admin = a
        else:
            assert False, "Unhandled option"

    try:
        
        cfgManager = ConfigManager.get_instance(config_file)
        global_config = cfgManager.get_config()
        log.debug("[HJC] Global Config = %s" %str(global_config))
        
        # Override parameters obtained by command line
        if port is not None: global_config['http_port'] = port
        if port_admin is not None: global_config['http_admin_port'] = port_admin
        if vnf_repository is not None:
            global_config['vnf_repository'] = vnf_repository
        else:
            if not 'vnf_repository' in global_config:  
                #print os.getcwd()
                global_config['vnf_repository'] = os.getcwd()+'/vnfrepo'
        
        if not os.path.exists(global_config['vnf_repository']):
            #print "Creating folder vnf_repository folder: '%s'." % global_config['vnf_repository']
            try:
                os.makedirs(global_config['vnf_repository'])
            except Exception,e:
                #print "Error '%s'. Ensure the path 'vnf_repository' is properly set at %s" %(e.args[1], config_file)
                exit(-1)
        
        # Initialize DB connection
        cipher = AESCipher.get_instance()
        db_passwd = cipher.decrypt(global_config['db_passwd'])
        mydb = orch_db.orch_db(global_config['db_host'], global_config['db_user'], db_passwd, global_config['db_name'], global_config['db_port'])
        if mydb.connect() == -1:
            log.error("Error connecting to database %s " % (global_config['db_name']))
            exit(-1)
        else:
            mydb.disconnect()
    
        orch_core.global_config=global_config
        orch_dbm.global_config=global_config
        server_manager.global_config=global_config
        descriptor_manager.global_config=global_config
        common_manager.global_config=global_config
        nsr_manager.global_config=global_config

        ##Obsoleted: Start Bottle HTTP Server as NBI
        # httpthread = orch_nbi.httpserver(mydb, False, global_config['http_host'], global_config['http_port'])
        #
        # httpthread.start()
        # if 'http_admin_port' in global_config:
        #     httpthreadadmin = orch_nbi.httpserver(mydb, True, global_config['http_host'], global_config['http_admin_port'])
        #     httpthreadadmin.start()


        ############      Load Work Flow Plugins        #####################################################################
        # common manager
        comm_info = {'onebox_type': 'Common'}
        orch_comm = wfm_common_manager.common_manager(comm_info)

        # service Order Manager
        general_info = {"onebox_type": "General"}
        wf_svcorder_manager = wfm_svcorder_manager.svcorder_manager(general_info)


        ## PNF type     -----------------------------
        req_info = {'onebox_type': 'KtPnf'}

        # server manager
        wf_server_manager = wfm_svr_manager.server_manager(req_info)

        # action manager
        wf_act_manager = wfm_act_manager.act_manager(req_info)

        # nsr manager
        wf_nsr_manager = wfm_nsr_manager.nsr_manager(req_info)


        # KT All Common type     -----------------------------
        req_info = {'onebox_type': 'KtComm'}
        # server kt all common manager
        wf_svr_ktcomm_manager = wfm_svr_ktcomm_manager.server_ktcomm_manager(req_info)


        # ARM-Box type     -----------------------------
        req_info = {'onebox_type': 'KtArm'}
        # server armbox manager
        wf_server_arm_manager = wfm_svr_arm_manager.server_arm_manager(req_info)

        # nsr arm manager
        wf_nsr_arm_manager = wfm_nsr_arm_manager.nsr_arm_manager(req_info)


        # work manager     -----------------------------
        req_info = {'onebox_type': 'Work'}
        wf_work_manager = wfm_work_manager.work_manager(req_info)


        ##  SBPM        ---------------------------------
        # monitor connector
        cfgManager = ConfigManager.get_instance()
        config = cfgManager.get_config()
        host_ip = config["monitor_ip"]
        host_port = config["monitor_port"]
        wf_monitorconnector = wfm_monitorconnector.monitorconnector({"onebox_type": "General", "host": host_ip, "port": host_port})

        # One-Box agent connector
        obconn_dict = {'onebox_type':"General"}
        wf_obconnector = wfm_obconnector.obconnector(obconn_dict)

        # Order Manager connector
        wf_Odm = wfm_odmconnector.odmconnector({"onebox_type": "General"})

        # Redis Manager connector
        wf_redis = wfm_redisconnector.redisconnector({"onebox_type": "General"})

        # SSH Manager connector
        wf_ssh = wfm_sshconnector.sshconnector({"onebox_type": "General"})

        plugins = {}
        plugins['orch_comm'] = orch_comm
        plugins['wf_svcorder_manager'] = wf_svcorder_manager
        plugins['wf_server_manager'] = wf_server_manager
        plugins['wf_act_manager'] = wf_act_manager
        plugins['wf_nsr_manager'] = wf_nsr_manager     # pnf type
        plugins['wf_work_manager'] = wf_work_manager   # work manager : 작업 및 코드 테스트용
        plugins['wf_monitorconnector'] = wf_monitorconnector
        plugins['wf_obconnector'] = wf_obconnector
        plugins['wf_Odm'] = wf_Odm
        plugins['wf_redis'] = wf_redis
        plugins['wf_ssh'] = wf_ssh

        # KT All Common
        plugins['wf_svr_ktcomm_manager'] = wf_svr_ktcomm_manager

        # ArmBox
        plugins['wf_server_arm_manager'] = wf_server_arm_manager
        plugins['wf_nsr_arm_manager'] = wf_nsr_arm_manager  # ArmBox

        ############     Load Work Flow Plugins        #####################################################################

        # Start Event Manager
        log.info("Create Event Manager Thread")
        eventmgr_thread = event_manager.EventManager(plugins)
        eventmgr_thread.start()
        log.info("Event Manager Thread Started")


        # TODO: use Tornado not bottle    
        # Start Tornado HTTP Server as NBI
        log.info("Process Number: %d" %global_config['http_proc_num'])
        tornadothread = httpserver(global_config['http_host'], global_config['http_port'], global_config['http_proc_num'], global_config.get('http_ssl', True), plugins)
        tornadothread.start()
        

        time.sleep(1)
        print 'Waiting for http clients'
        print 'obord ready'
        print '===================='
        log.info("OBOR Daemon is Running Now!")
        time.sleep(20)
        sys.stdout.flush()

        while True:
            time.sleep(86400)      

    except (KeyboardInterrupt, SystemExit):
        #print 'Exiting obord'
        exit()


