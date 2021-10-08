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

import os, paramiko
from scp import SCPClient

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

class ssh_connector:

    def __init__(self, host, port=9922):
        self.host = host
        self.port = port
        
    def run_ssh_command(self, script):
        
        result = 0
        output = ""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.load_system_host_keys()
            
            script_name = script['name']
            param_list = script['params']
            
            if param_list != None and len(param_list) > 0:
                params = " ".join(param_list)
            else:
                params = ""
                
            ssh_cmd="%s %s" % (script_name, params)
            log.debug("run_ssh_command host= %20s command= %s" % (self.host, ssh_cmd))
            
            ssh.connect(self.host, self.port)
            stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=60)
            
            output = stdout.readlines()
            log.debug("run_ssh_command output= %s" % output)
        except Exception,e:
            error_msg = "failed to compose a command (ssh type) %s" % str(script) 
            log.error(error_msg)
            log.exception("Exception: %s" %str(e))
            result = -500
        finally:
            if ssh is not None:
                ssh.close()
             
        return result, output

    def set_file_permission(self, ssh, permission, target):
        result = 0
        output = ""
        try:
            ssh_cmd="chmod %s %s/*" % (permission, target)
            log.debug("set_file_permission command= %s" % ssh_cmd)
            
            stdin, stdout, stderr = ssh.exec_command(ssh_cmd, timeout=60)
            
            output = stdout.readlines()
            log.debug("set_file_permission output= %s" % output)
        except Exception,e:
            error_msg = "failed to set_file_permission file= %s" % target 
            log.error(error_msg)
            log.exception("Exception: %s" %str(e))
            result = -500
        
        return result, output
        
    def run_scp_command(self, src, dst, permission="644", mode="PUT"):

        result = 0
        output = ""
        ssh = None
        scp = None
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.load_system_host_keys()
           
            ssh.connect(self.host, self.port)
            scp = SCPClient(ssh.get_transport())
                
            #scp.put('test.txt', 'test2.txt')
            src = src.rstrip('\n')
            if mode == "PUT":
                log.debug("[ssh_connector] put file to host= %s src= %s dst= %s" % (self.host, src, dst))
                scp.put(src, dst)
                #if permission != "": self.set_file_permission(ssh, permission, dst)
            else:
                log.debug("[ssh_connector] get file from host= %s src= %s" % (self.host, src))
                scp.get(src, dst)

            output = os.path.basename(src) # return filename
                
            #log.debug('scp location: %s' % location)
        except Exception,e:
            error_msg = "Failed to run a command (host= %s src= %s dst= %s)" % (self.host, src, dst) 
            log.error(error_msg)
            log.exception("Exception: %s" %str(e))
            result = -500
        finally:
            if scp is not None:
                scp.close()            
            if ssh is not None:
                ssh.close()
            
        return result, output
        
        
