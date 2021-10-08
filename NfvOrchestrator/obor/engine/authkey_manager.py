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

import os
import sched
import time
import threading

from Crypto.PublicKey import RSA
import datetime
import db.orch_db_manager as orch_dbm
from db.orch_db import HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found
from utils.config_manager import ConfigManager
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()
import paramiko
from engine.server_status import SRVStatus
from scp import SCPClient


def create_account(mydb, ob_account, grp_seq):

    try:
        key_manager = AuthKeyOrderManager(mydb, ob_account)
        key_manager.prepare_create(grp_seq)
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"


def update_authkey(mydb, ob_account):

    try:
        key_manager = AuthKeyOrderManager(mydb, ob_account)
        key_manager.prepare_update()
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"


def delete_account(mydb, ob_account):

    try:
        key_manager = AuthKeyOrderManager(mydb, ob_account)
        key_manager.prepare_delete()
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"


def deploy_order(mydb, auth_deploy_seq):
    """
    배포 항목 하나를 배포처리한다.
    :param mydb:
    :param auth_deploy_seq: 배포할 항목의 배포테이블 키값
    :return:
    """
    try:
        key_manager = AuthKeyDeployManager(mydb)
        key_manager.deploy_order(auth_deploy_seq)
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"


def deploy_fail(mydb, deploy_fail_seq):
    """
    배포실패 항목 하나를 배포처리한다.
    :param mydb:
    :param deploy_fail_seq: 배포할 항목의 배포테이블 키값
    :return:
    """
    try:
        key_manager = AuthKeyDeployManager(mydb)
        key_manager.deploy_fail(deploy_fail_seq)
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"


def reserve_deploy_batch(mydb, ymdh, batch_type):

    batch_reserve = BatchReserve()
    try:
        batch_reserve.reserve_batch(mydb, ymdh, batch_type)
    except Exception, e:
        return -HTTP_Internal_Server_Error, str(e)
    batch_reserve.start()

    return 200, "OK"


def deploy_batch(mydb, ymdh):

    try:
        key_manager = AuthKeyDeployManager(mydb)
        key_manager.deploy_batch(ymdh)
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"


def deploy_fail_batch(mydb, ymdh):

    try:
        key_manager = AuthKeyDeployManager(mydb)
        key_manager.deploy_fail_batch(ymdh)
    except Exception, e:
        log.error(str(e))
        return -HTTP_Internal_Server_Error, str(e)

    return 200, "OK"



class AuthKeyOrderManager(object):


    def __init__(self, mydb, ob_account):
        self.mydb = mydb
        self.ob_account = ob_account


    def prepare_create(self, grp_seq):

        # 1. 인증키 파일 생성
        result, path_info = self._make_keys()
        if result < 0:
            raise Exception(path_info)

        # 2. 접속정보 생성
        auth_dict = {"ob_account":self.ob_account, "status":"R"}
        if grp_seq is not None and grp_seq > 0: # 관리자는 그룹이 없으므로 0으로 처리함. 계정은 onebox 사용.
            auth_dict["account_group_seq"] = grp_seq

        result, q_data = orch_dbm.insert_onebox_auth(self.mydb, auth_dict)
        if result < 0:
            raise Exception(q_data)

        # 3. 오더 생성
        auth_deploy_dict = {"ob_account":self.ob_account, "status":"R"}
        auth_deploy_dict["privatekey_path"] = path_info["privatekey_path"]
        auth_deploy_dict["publickey_path"] = path_info["publickey_path"]
        auth_deploy_dict["deploy_type"] = "C"

        result, q_data = orch_dbm.insert_onebox_auth_deploy(self.mydb, auth_deploy_dict)
        if result < 0:
            raise Exception(q_data)

        return result, "OK"


    def prepare_delete(self):

        if self.ob_account == "onebox": # 관리자 계정은 삭제할 수 없다.
            raise Exception("관리자 계정은 삭제할 수 없습니다.")

        # 1. 배포 전인지 후인지 체크 : 생성오더가 배포완료 되었는지 확인
        result, auth_info = orch_dbm.get_onebox_auth(self.mydb, {"ob_account":self.ob_account})
        if result < 0:
            raise Exception(auth_info)
        elif result == 0:
            raise Exception("삭제할 접속계정이 존재하지 않습니다.")

        if auth_info["status"] == "R":
            # 2. 배포전인 경우 : 배포전인 경우는 생성오더가 배포되기 전뿐이다.
            # CHECK : 한 계정의 완료되지 않은 오더는 1개 이상 존재해선 안된다.
            result, auth_deploy_info = orch_dbm.get_onebox_auth_deploy(self.mydb, {"ob_account":self.ob_account, "status":"R", "deploy_type":"C"})
            if result <= 0:
                raise Exception("Failed to get auth deploy info : %s" % str(auth_deploy_info))

            # 2.1. 생성된 인증키파일 삭제
            self._delete_keys(auth_deploy_info["privatekey_path"], auth_deploy_info["publickey_path"])
            # 2.2. 생성오더 삭제
            result, content = orch_dbm.delete_onebox_auth_deploy(self.mydb, {"auth_deploy_seq":auth_deploy_info["auth_deploy_seq"]})
            if result < 0:
                raise Exception("Failed to delete auth deploy info : %s" % str(content))
            # 2.3. 접속정보 삭제
            result, content = orch_dbm.delete_onebox_auth(self.mydb, {"ob_account":self.ob_account})
            if result < 0:
                raise Exception("Failed to delete auth info : %s" % str(content))
        else:
            # 중복이 있는경우 처리
            result, auth_deploy_info = orch_dbm.get_onebox_auth_deploy(self.mydb, {"ob_account":self.ob_account, "status":"R", "deploy_type":"D"})
            if result > 0:
                raise Exception("계정삭제 이미 접수되어있습니다.")

            # 3. 배포완료인 경우
            # 3.1. 삭제 오더 생성
            auth_deploy_dict = {"ob_account":self.ob_account, "status":"R"}
            auth_deploy_dict["deploy_type"] = "D"

            result, q_data = orch_dbm.insert_onebox_auth_deploy(self.mydb, auth_deploy_dict)
            if result < 0:
                raise Exception(q_data)

        return result, "OK"

    def prepare_update(self):

        # 1. 배포 전인지 후인지 체크 : 생성오더가 배포완료 되었는지 확인
        result, auth_info = orch_dbm.get_onebox_auth(self.mydb, {"ob_account":self.ob_account})
        if result < 0:
            raise Exception(auth_info)
        elif result == 0:
            raise Exception("변경할 대상 계정이 존재하지 않습니다 : %s" % self.ob_account)

        if auth_info["status"] == "R":
            raise Exception("변경할 대상 계정이 아직 생성[배포]되지 않습니다 : %s" % self.ob_account)

        # 완료되지 않은 다른 오더가 존재하는지 체크.
        result, auth_deploy_info = orch_dbm.get_onebox_auth_deploy(self.mydb, {"ob_account":self.ob_account, "status":"R"})
        if result > 0:
            if auth_deploy_info["deploy_type"] == "D":
                deploy_str = "계정삭제"
            elif auth_deploy_info["deploy_type"] == "U":
                deploy_str = "인증서변경"
            else:
                raise Exception("인증서 생성 절차가 잘못되었습니다. 관리자에게 문의하세요.")

            raise Exception("이미 %s 배포준비 중입니다." % deploy_str)

        # 2. 새 인증키 파일 생성
        result, path_info = self._make_keys()
        if result < 0:
            raise Exception(path_info)

        # 3. 변경 오더 생성
        auth_deploy_dict = {"ob_account":self.ob_account, "status":"R"}
        auth_deploy_dict["privatekey_path"] = path_info["privatekey_path"]
        auth_deploy_dict["publickey_path"] = path_info["publickey_path"]
        auth_deploy_dict["deploy_type"] = "U"

        result, q_data = orch_dbm.insert_onebox_auth_deploy(self.mydb, auth_deploy_dict)
        if result < 0:
            raise Exception(q_data)

        return result, "OK"

    def _make_keys(self):

        key = RSA.generate(2048)
        private_key = key.exportKey('PEM')
        public_key = key.publickey().exportKey('OpenSSH')

        cfgManager = ConfigManager.get_instance()
        config = cfgManager.get_config()
        MOUNT_PATH = config.get('image_mount_path', "")

        auth_keys_path = os.path.join(MOUNT_PATH, "auth_keys")
        log.debug("auth_keys_path = %s" % auth_keys_path)
        try:
            if not os.path.exists(auth_keys_path):
                os.makedirs(auth_keys_path, mode=0777)
        except Exception, e1:
            log.error(str(e1))
            return -500, str(e1)

        now = datetime.datetime.now()
        now_date = now.strftime('%Y%m%d%H%M%S')

        pri_fn = "%s_%s_rsa" % (self.ob_account, now_date)
        pri_fn = os.path.join(auth_keys_path, pri_fn)

        log.debug("pri_fn = %s" % pri_fn)

        try:
            pri_f = open(pri_fn, "wb")
            pri_f.write(private_key)
            pri_f.close()

            pub_fn = pri_fn + ".pub"
            pub_f = open(pub_fn, "wb")
            pub_f.write("%s %s@%s" % (public_key, self.ob_account, "OneBox"+os.linesep))

            pub_f.close()
        except Exception, e2:
            log.error(str(e2))
            return -500, str(e2)

        return 200, {"privatekey_path":pri_fn, "publickey_path":pub_fn}


    @staticmethod
    def _delete_keys(private_key, public_key):
        os.remove(private_key)
        os.remove(public_key)


##########################################################################################################
#   배포처리
##########################################################################################################
class AuthKeyDeployManager(object):

    def __init__(self, mydb):
        self.mydb = mydb
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.load_system_host_keys()

        # nova endpoint url update 변수
        self.sc_path="/var/onebox/tmp"
        self.sc_fn="endpoint.sh"
        self.nova_deploy_path = "/var/onebox/novaurl_update/endpoint.sh"


    def __del__(self):
        if self.ssh is not None:
            # self.ssh.close()
            self.ssh = None

    def deploy_order(self, auth_deploy_seq):
        """
        deploy 계정 한 건에 대해 처리한다.
        :param auth_deploy_seq:
        :return:
        """

        result, auth_deploy_info = orch_dbm.get_onebox_auth_deploy(self.mydb, {"auth_deploy_seq":auth_deploy_seq})
        if result <= 0:
            raise Exception("배포할 대상 정보가 존재하지 않습니다.")

        if auth_deploy_info["deploy_type"] not in ["C", "D", "U"]:
            raise Exception("The deploy_type is invalid")

        if auth_deploy_info["status"] == "R":

            # ob_account = auth_deploy_info["ob_account"]
            # deploy_type = auth_deploy_info["deploy_type"]

            th = threading.Thread(target=self._deploy_order_thread, args=(auth_deploy_info,))
            th.start()

        else:
            raise Exception("Already deployed")

    def _deploy_order_thread(self, auth_deploy_info):

        ob_account = auth_deploy_info["ob_account"]
        deploy_type = auth_deploy_info["deploy_type"]

        # 전처리 : 해당 계정의 기존 실패 이력 삭제.
        target_dict = {"ob_account" : ob_account}
        orch_dbm.delete_onebox_auth_deploy_fail(self.mydb, target_dict)

        # 한계정 : 모든 원박스
        result, servers = orch_dbm.get_server_filters(self.mydb)

        # 원박스 리스트 루프
        succ_cnt, fail_cnt = 0, 0
        total_server_cnt = len(servers)
        self._update_deploy_status(auth_deploy_info["auth_deploy_seq"], status="R", target_ob_cnt=total_server_cnt)

        for server_info in servers:
            # Test용
            # if server_info["servername"] != "KEYTEST.OB1":
            #     continue

            try:
                if server_info["status"] == SRVStatus.DSC:
                    raise Exception("One-Box의 연결상태가 DISCONNECTED 입니다.")

                if deploy_type == "C":
                    self._deploy_create(server_info["mgmtip"], ob_account, auth_deploy_info["publickey_path"])

                elif deploy_type == "D":
                    self._deploy_delete(server_info["mgmtip"], ob_account)

                elif deploy_type == "U":
                    self._deploy_update(server_info["mgmtip"], ob_account, auth_deploy_info["publickey_path"])

                succ_cnt += 1

            except Exception, e:
                fail_cnt += 1
                self._insert_onebox_auth_deploy_fail(auth_deploy_info, server_info["serverseq"], str(e))

            # 진행률 상태값 업데이트
            cur_per = (succ_cnt+fail_cnt) * 10 / total_server_cnt
            if cur_per == 0: cur_per = 1
            elif cur_per == 10: cur_per = 9
            cur_status = "I__%d__10" % cur_per
            self._update_deploy_status(auth_deploy_info["auth_deploy_seq"], status=cur_status)

        log.debug("@@@@@@@@@@ DB처리 시작 : 성공 %d 건, 실패 %d 건" % (succ_cnt, fail_cnt))

        # DB처리
        # 상태값 완료 처리
        self._update_deploy_status(auth_deploy_info["auth_deploy_seq"], status="C", target_ob_cnt=total_server_cnt)

        if deploy_type == "D":
            # 접속정보테이블 삭제
            auth_dict = {"ob_account":ob_account}
            orch_dbm.delete_onebox_auth(self.mydb, auth_dict)
        else:
            # 접속정보테이블에 키정보 저장 : 생성 / 변경
            self._update_auth_key_info(auth_deploy_info["ob_account"], auth_deploy_info["privatekey_path"], auth_deploy_info["publickey_path"])


    def deploy_fail(self, deploy_fail_seq):

        result, auth_deploy_fail_info = orch_dbm.get_onebox_auth_deploy_fail(self.mydb, {"deploy_fail_seq":deploy_fail_seq})
        if result <= 0:
            raise Exception("배포할 대상 정보가 존재하지 않습니다.")

        result, server_info = orch_dbm.get_server_id(self.mydb, auth_deploy_fail_info["serverseq"])
        if result < 0:
            raise Exception("해당 One-Box가 존재하지 않습니다.")

        ob_account = auth_deploy_fail_info["ob_account"]
        deploy_type = auth_deploy_fail_info["deploy_type"]
        if deploy_type == "C":
            self._deploy_create(server_info["mgmtip"], ob_account, auth_deploy_fail_info["publickey_path"])

        elif deploy_type == "D":
            self._deploy_delete(server_info["mgmtip"], ob_account)

        elif deploy_type == "U":
            self._deploy_update(server_info["mgmtip"], ob_account, auth_deploy_fail_info["publickey_path"])

        # DB 처리 : 배포 완료 되었으면, 실패항목을 테이블에서 삭제한다.
        target_dict = {"deploy_fail_seq" : deploy_fail_seq}
        orch_dbm.delete_onebox_auth_deploy_fail(self.mydb, target_dict)


    def _deploy_create(self, mgmtip, ob_account, publickey_path):

        try:
            self.ssh.connect(mgmtip, port=9922, timeout=5)
        except Exception, e:
            raise Exception("One-Box SSH접속 실패 : %s" % str(e))

        try:
            # 1. 원박스에 계정 생성
            # 1.1. 계정 중복확인
            is_exist_user = self._dup_user(ob_account)

            # 1.2. 계정생성
            if not is_exist_user:
                self._create_user(ob_account)

            # 1.3. nopasswd 적용
            self. _append_nopasswd(ob_account)

            # 2. 공유키 등록
            # 2.1. '.ssh' 경로가 있는지 체크
            self._make_ssh_directory(ob_account)

            # 2.2. authorized_keys 생성
            self._make_authorized_keys(ob_account, publickey_path)

        except Exception, e:
            log.error("Failed to create user and make authorized_keys in the One-Box : %s" % str(e))
            raise Exception(str(e))

        finally:
            if self.ssh is not None:
                self.ssh.close()


    def _deploy_delete(self, mgmtip, ob_account):

        try:
            self.ssh.connect(mgmtip, port=9922, timeout=5)
        except Exception, e:
            raise Exception("One-Box SSH접속 실패 : %s" % str(e))

        try:
            # 원박스에 계정 삭제
            self._delete_user(ob_account)

        except Exception, e:
            log.error("Failed to delete user in the One-Box: %s" % str(e))
            raise Exception(str(e))
        finally:
            if self.ssh is not None:
                self.ssh.close()


    def _deploy_update(self, mgmtip, ob_account, publickey_path):

        try:
            self.ssh.connect(mgmtip, port=9922, timeout=5)
        except Exception, e:
            raise Exception("One-Box SSH접속 실패 : %s" % str(e))

        try:
            # 1. 원박스에 계정이 생성되지 않은 상태(생성실패 케이스)인지 확인
            # 1.1. 계정 중복확인
            is_exist_user = self._dup_user(ob_account)

            # 1.2. 계정 생성
            if not is_exist_user:
                self._create_user(ob_account)

            # 1.3. nopasswd 적용
            self. _append_nopasswd(ob_account)

            # 2. 공유키 업데이트
            # 2.1. '.ssh' 경로가 있는지 체크
            self._make_ssh_directory(ob_account)

            # 2.2. authorized_keys 생성
            # 현재는 authorized_keys 파일을 새로 만드는 것으로 한다.
            # 추후에 필요한 경우, 기존 authorized_keys 안에 public key 문자열을 수정하는 방식으로 바꿀수 있음.
            self._make_authorized_keys(ob_account, publickey_path)

        except Exception, e:
            log.error("Failed to update authorized_keys in the One-Box: %s" % str(e))
            raise Exception(str(e))
        finally:
            if self.ssh is not None:
                self.ssh.close()


    def deploy_batch(self, ymdh):

        # 배치테이블에 예약 당시의 값이 존재하는 체크
        result, batch = orch_dbm.get_onebox_auth_batch(self.mydb, {"batch_type":"B"})
        if result <= 0:
            return
        else:
            if batch[0]["reserve_dtt"] == ymdh:
                pass
            else:
                return

        # 배포 테이블 조회
        result, batch_items = orch_dbm.get_onebox_auth_deploy_batch(self.mydb)
        if result <= 0:
            raise Exception(batch_items)

        for batch_item in batch_items:
            self.deploy_order(batch_item["auth_deploy_seq"])

        orch_dbm.delete_onebox_auth_batch(self.mydb, {"batch_type":"B"})


    def deploy_fail_batch(self, ymdh):

        # 배치테이블에 예약 당시의 값이 존재하는 체크
        result, batch = orch_dbm.get_onebox_auth_batch(self.mydb, {"batch_type":"F"})
        if result <= 0:
            return
        else:
            if batch[0]["reserve_dtt"] == ymdh:
                pass
            else:
                return

        # 배포 테이블 조회
        result, batch_items = orch_dbm.get_onebox_auth_deploy_fail_batch(self.mydb)
        if result <= 0:
            raise Exception(batch_items)

        for batch_item in batch_items:
            try:
                result, server_info = orch_dbm.get_server_id(self.mydb, batch_item["serverseq"])
                if result < 0:  # 이런경우는 없지만...
                    continue
                elif server_info["status"] == SRVStatus.DSC:    # I__DISCONNECTED 이면 스킵
                    continue

                self.deploy_fail(batch_item["deploy_fail_seq"])
            except Exception, e:
                log.debug("Failed to batch fail-item : %s, %s" % (batch_item["deploy_fail_seq"], str(e)))

        orch_dbm.delete_onebox_auth_batch(self.mydb, {"batch_type":"F"})


    def _update_auth_key_info(self, ob_account, privatekey_path, publickey_path):
        auth_dict = {"ob_account":ob_account}
        auth_dict["privatekey_path"] = privatekey_path
        auth_dict["publickey_path"] = publickey_path
        auth_dict["status"] = "C"
        orch_dbm.update_onebox_auth(self.mydb, auth_dict)


    def _update_deploy_status(self, auth_deploy_seq, status="C", target_ob_cnt=None):
        auth_deploy_dict = {"auth_deploy_seq":auth_deploy_seq}
        auth_deploy_dict["status"] = status
        if target_ob_cnt:
            auth_deploy_dict["target_ob_cnt"] = target_ob_cnt
        orch_dbm.update_onebox_auth_deploy(self.mydb, auth_deploy_dict)


    def _insert_onebox_auth_deploy_fail(self, auth_deploy_info, serverseq, description):

        deploy_fail_dict = {"auth_deploy_seq" : auth_deploy_info["auth_deploy_seq"]}
        deploy_fail_dict["serverseq"] = serverseq
        deploy_fail_dict["ob_account"] = auth_deploy_info["ob_account"]
        deploy_fail_dict["deploy_type"] = auth_deploy_info["deploy_type"]
        if auth_deploy_info["deploy_type"] != "D":
            deploy_fail_dict["privatekey_path"] = auth_deploy_info["privatekey_path"]
            deploy_fail_dict["publickey_path"] = auth_deploy_info["publickey_path"]
        deploy_fail_dict["description"] = description

        orch_dbm.insert_onebox_auth_deploy_fail(self.mydb, deploy_fail_dict)


    def _dup_user(self, ob_account):

        # 계정중복체크
        # cat /etc/passwd | grep -wc insoft
        log.debug("@@@@@@@@@@ 계정 중복체크")
        is_exist_user = False
        try:
            ssh_cmd = "cat /etc/passwd | grep -wc %s" % ob_account
            log.debug("@@@@@@@@@@ 계정중복체크 : %s" % ssh_cmd)
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)
            if output[0].find("1") >= 0:
                is_exist_user = True
        except Exception, e:
            log.error(str(e))
            raise Exception("계정중복체크 실패 : %s" % str(e))
        return is_exist_user


    def _delete_user(self, ob_account):
        log.debug("@@@@@@@@@@ 계정삭제시작")
        try:
            # 계정삭제
            ssh_cmd = "deluser --remove-home %s" % ob_account
            log.debug("@@@@@@@@@@ 계정삭제 : %s" % ssh_cmd)
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            # error = stderr.readlines()
            # log.debug("ssh ommand error = %s" % error)
        except Exception, e:
            log.error(str(e))
            raise Exception("계정삭제(deluser) 실패 : %s" % str(e))

        try:
            # sudoers 내용제거
            ssh_cmd = "sed -i '/%s ALL=NOPASSWD/d' /etc/sudoers" % ob_account
            log.debug("@@@@@@@@@@ sudoers 내용제거 : %s" % ssh_cmd)
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)
        except Exception, e:
            log.error(str(e))
            raise Exception("sudoers 내용제거(NOPASSWD) 실패 : %s" % str(e))


    def _create_user(self, ob_account):
        log.debug("@@@@@@@@@@ 계정생성시작")
        try:
            # 계정생성 : password 옵션 -p sa92bmSdtSBk6 <== crypt.crypt("kt@ne130X","sa")
            ssh_cmd = "useradd -m -s /bin/bash -d /home/%s %s" % (ob_account, ob_account)
            log.debug("@@@@@@@@@@ 계정생성 : %s" % ssh_cmd)
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)
        except Exception, e:
            log.error(str(e))
            raise Exception("계정생성(useradd) 실패 : %s" % str(e))


    def _append_nopasswd(self, ob_account):
        #############################################################################
        # 개발용 임시코드 : 개발서버에 테스트중 잘못 들어간 값 정리하는 로직
        # TODO : 상용적용시에는 반드시 삭제 처리
        try:
            ssh_cmd = "sed -i '/ALL=NOPASSWD ALL/d' /etc/sudoers"
            log.debug("@@@@@@@@@@ 잘못들어간 sudoers 내용제거 : %s" % ssh_cmd)
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)

            ssh_cmd = "sed -i '/ALL=NOPASSSWD/d' /etc/sudoers"
            log.debug("@@@@@@@@@@ 잘못들어간 sudoers 내용제거 : %s" % ssh_cmd)
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)
        except Exception, e:
            log.error(str(e))
            raise Exception("sudoers 적용(NOPASSWD) 실패 : %s" % str(e))
        #############################################################################

        try:
            is_exist_sudo = False
            ssh_cmd = "cat /etc/sudoers | grep -wc '%s ALL=NOPASSWD: ALL'" % ob_account
            log.debug("@@@@@@@@@@ sudoers 중복체크 : %s" % ssh_cmd)
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)
            if output[0].find("1") >= 0:
                is_exist_sudo = True

            if not is_exist_sudo:
                # sudoers 적용
                ssh_cmd = "echo '%s ALL=NOPASSWD: ALL' >> /etc/sudoers" % ob_account
                log.debug("@@@@@@@@@@ sudoers 적용 : %s" % ssh_cmd)
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
                output = stdout.readlines()
                log.debug("ssh ommand output = %s" % output)
                error = stderr.readlines()
                log.debug("ssh ommand error = %s" % error)
        except Exception, e:
            log.error(str(e))
            raise Exception("sudoers 적용(NOPASSWD) 실패 : %s" % str(e))


    def _make_ssh_directory(self, ob_account):
        log.debug("@@@@@@@@@@ .ssh 경로 생성 시작")
        try:
            ssh_cmd = "ls -a /home/%s | grep -wc .ssh" % ob_account
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)
            if output[0].find("0") >= 0:
                ssh_cmd = "mkdir -m 700 /home/%s/.ssh" % ob_account
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
                ssh_cmd = "chown %s.%s /home/%s/.ssh" % (ob_account, ob_account, ob_account)
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
        except Exception, e:
            log.error(str(e))
            raise Exception(".ssh 경로 생성 실패 : %s" % str(e))

    def _make_authorized_keys(self, ob_account, publickey_path):
        log.debug("@@@@@@@@@@ authorized_keys 생성 시작")
        scp = None
        try:
            # 파일 전송
            scp = SCPClient(self.ssh.get_transport())
            scp.put(publickey_path, "/home/%s/.ssh/authorized_keys" % ob_account)
        except Exception, e:
            log.error(str(e))
            raise Exception("authorized_keys 생성실패 : %s" % str(e))
        finally:
            if scp is not None:
                scp.close()


    ###########     NOVA ENDPOINT URL UPDATE    START       #####################################################################
    def scp_nova_deploy(self):
        scp = None
        try:
            # 파일 전송
            scp = SCPClient(self.ssh.get_transport())
            scp.put(self.nova_deploy_path, "%s/" %str(self.sc_path))
        except Exception, e:
            log.error(str(e))
            raise Exception("NOVA Endpoint URL UPDATE 파일 전송 실패 : %s" % str(e))
        finally:
            if scp is not None:
                scp.close()

    def nova_endpoint_update(self, origin_ip, mgmt_ip):

        # ssh connection
        try:
            self.ssh.connect(mgmt_ip, port=9922, timeout=5)
        except Exception, e:
            raise Exception("One-Box SSH접속 실패 : %s" % str(e))

        # mysql update(keystone.endpoint) : nova endpoint url update
        try:
            # 1. update 할 스크립트 배포
            self.scp_nova_deploy()

            # 2. 스크립트 파일이 있는지 체크
            ssh_cmd = "ls -a %s | grep -wc %s" %(str(self.sc_path), str(self.sc_fn))
            stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)
            output = stdout.readlines()
            log.debug("ssh ommand output = %s" % output)
            error = stderr.readlines()
            log.debug("ssh ommand error = %s" % error)

            # 3. 스크립트 파일이 있으면, 실행 후 스크립트 파일 삭제
            if output[0].find("1") >= 0:
                # 권한 설정
                ssh_cmd = "chmod 700 %s/%s" %(str(self.sc_path), str(self.sc_fn))
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)

                # script 실행
                ssh_cmd = "sh %s/%s %s %s" % (str(self.sc_path), str(self.sc_fn), str(origin_ip), str(mgmt_ip))
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)

                # script 파일 삭제
                ssh_cmd = "rm -f %s/%s" %(str(self.sc_path), str(self.sc_fn))
                stdin, stdout, stderr = self.ssh.exec_command(ssh_cmd, timeout=10)

        except Exception, e:
            log.error("Failed to update nova endpoint url in the One-Box : %s" % str(e))
            raise Exception(str(e))

        finally:
            if self.ssh is not None:
                self.ssh.close()
    ###########     NOVA ENDPOINT URL UPDATE    END       #####################################################################


class BatchReserve(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.scheduler = sched.scheduler(time.time, time.sleep)

    def run(self):
        self.scheduler.run()

    def reserve_batch(self, mydb, ymdh, batch_type):

        reserve_dtt = datetime.datetime.strptime(ymdh, "%Y%m%d%H")

        if reserve_dtt > datetime.datetime.now():
            term = reserve_dtt - datetime.datetime.now()
            remained_seconds = term.seconds
        else:
            raise Exception("예약시간은 현재시간 이후 시간만 가능합니다.")
            # remained_seconds = 0

        # 마지막 예약만 남긴다.
        result, batch = orch_dbm.get_onebox_auth_batch(mydb, {"batch_type":batch_type})
        if result > 0:
            orch_dbm.delete_onebox_auth_batch(mydb, {"batch_type":batch_type})

        # 배치 테이블 저장
        batch_dict = {"batch_type":batch_type, "reserve_dtt":ymdh}
        orch_dbm.insert_onebox_auth_batch(mydb, batch_dict)

        if batch_type == "B":
            log.debug("인증키 배포 예약 : %s" % ymdh)
            self.scheduler.enter(remained_seconds, 1, deploy_batch, (mydb, ymdh,))
        else:
            log.debug("인증키 실패항목 배포 예약 : %s" % ymdh)
            self.scheduler.enter(remained_seconds, 1, deploy_fail_batch, (mydb, ymdh,))














