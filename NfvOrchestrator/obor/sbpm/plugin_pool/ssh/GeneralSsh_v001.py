# -*- coding: utf-8 -*-

from sbpm.plugin_spec.ssh.GeneralSshSpec import GeneralSshSpec

import requests
import json
import sys
import time
import paramiko

# import db.dba_manager as orch_dbm

from httplib import HTTPException
from requests.exceptions import ConnectionError
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


class GeneralSsh(GeneralSshSpec):
    def __init__(self):
        self.host = None
        self.port = 9922
        self.user = None
        self.pwd = None
        self.cmd = None


    def execute_cmd(self, cmdInfo=None):
        log.debug("execute_cmd IN!")
        log.debug("cmdInfo = %s" %str(cmdInfo))

        self.host = cmdInfo.get("host")
        self.port = cmdInfo.get("port")
        self.user = cmdInfo.get("user")
        self.pwd = cmdInfo.get("pwd")

        if cmdInfo.get("cmdMode") == "pre-viledge" or cmdInfo.get("cmdMode") == "start-shell":
            self_cmd = "%s\nregain privilege\n" %str(self.pwd)

            if cmdInfo.get("cmdMode") == "start-shell":
                self_cmd += "start-shell\n"

            self.cmd = self_cmd
        else:
            self.cmd = cmdInfo.get("cmd")

        ssh = None
        channel = None

        try:
            ssh = self._get_ssh()
            channel = ssh.invoke_shell()
            channel.send(self.cmd)
            output, errdata = self._waitStrems(channel, wait_time=3)      # 로그인 대기 시간 문제로 3초

            # log.debug("[execute_cmd] output = %s" % str(output))

            if cmdInfo.get("cmdMode") == "pre-viledge" or cmdInfo.get("cmdMode") == "start-shell":
                wait_time = 1

                # Axgate UTM 접속 시 : 실제 실행될 command
                getCmd = cmdInfo.get("cmd").split("[INSOFT]")
                cmdOutput = ""

                tmpCmd = None
                tmpWaitTime = None

                if cmdInfo.get("cmdMode") == "start-shell":
                    # iperf 하나만 있기 때문에 배열의 첫번째를 선택
                    # iperf 는 time option(-t) 가 없을 경우 default 10초 이므로 출력값 대기시간을 10초로 한다
                    # option(-t) 뒤에 다른 명령이 있을경우가 있으므로 다시 split 한다
                    wait_time = 10

                    if " -t " in getCmd[0]:
                        tmpCmd = getCmd[0].split(" -t ")
                        # tmpCmd2 = tmpCmd[1].split(" ")
                        # wait_time = int(tmpCmd2[0])

                        # option(-t) 뒤에 다른 명령이 있을경우가 있으므로 다시 split 한다
                        tmpWaitTime = tmpCmd[1].split(" ")

                        # wait_time = int(tmpCmd[1])
                        wait_time = int(tmpWaitTime[0])

                if cmdInfo.get("cmdMode") == "pre-viledge" and cmdInfo.get("cmdType") == "set":
                    getCmd.append("wr")

                for cmd in getCmd:
                    if cmd == "end":
                        wait_time = 3

                    # log.debug("cmd = %s" % str(cmd))
                    # log.debug("wait_time = %s" %str(wait_time))

                    channel.send(cmd + "\n")

                    # iperf 마지막 출력값을 가져오는 대기시간 1초 추가
                    if cmdInfo.get("cmdMode") == "start-shell":
                        wait_time = wait_time + 1

                    output, errdata = self._waitStrems(channel, wait_time)

                    # log.debug("output = %s" % str(output))

                    cmdOutput = cmdOutput + "\n" + output

                # log.debug("cmdOutput : %s" % str(cmdOutput))
                return 200, cmdOutput
            else:
                return 200, output
        except Exception, e:
            log.error("failed to ssh command Error %s" % str(e))
            return -500, str(e)
        finally:
            log.debug("close channel and ssh connection")

            # close channel
            if channel is not None:
                self._close_channel(channel)

            # close ssh connection
            if ssh is not None:
                self._close_ssh(ssh)


    def _get_ssh(self):
        try:
            # log.debug("_get_ssh :: >> %s, %s, %s, %s" % (str(self.host), str(self.port), str(self.user), str(self.pwd)))
            # ssh client create
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # connect
            ssh.connect(hostname=self.host, port=self.port, username=self.user, password=self.pwd, timeout=10)
        except Exception as e:
            print(e)
            raise e

        return ssh


    def _close_ssh(self, ssh):
        ssh.close()


    def _close_channel(self, channel):
        channel.close()


    def _waitStrems(self, chan, wait_time=1):
        time.sleep(wait_time)
        output = errdata = ""

        while chan.recv_ready():
            output += chan.recv(65535).decode("utf-8")

        while chan.recv_stderr_ready():
            errdata += chan.recv_stderr(1000)

        return output, errdata


