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

import threading
import sched
import time
import datetime
import os
import json
import copy

import db.orch_db_manager as orch_dbm
import db.dba_manager as orch_dbm_plugins
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found,\
    HTTP_Conflict
    
from engine.server_status import SRVStatus
from engine.server_manager import check_onebox_valid
from engine.server_manager import check_onebox_valid_em
from engine.common_manager import update_server_status

from utils import auxiliary_functions as af
from utils.e2e_logger import e2elogger, CONST_TRESULT_NONE, CONST_TRESULT_SUCC, CONST_TRESULT_FAIL
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils.config_manager import ConfigManager

from utils import db_conn_manager as dbmanager
mydb = dbmanager.DBConnectionManager.get_instance().getConnection()

from engine.authkey_manager import deploy_batch, deploy_fail_batch

import redis


class EventManager(threading.Thread):


    def __init__(self, plugins=None):
        log.debug("Event Manager Init")
        threading.Thread.__init__(self)

        # work flow plugins
        self.plugins = plugins

        log.debug("Event Manager Init 2")
        self.event_scheduler = sched.scheduler(time.time, time.sleep)

        log.debug("Event Manager Init 3")
        self.event_scheduler.enter(30, 1, self.event_function_check_onebox, ())
        self.event_scheduler.enter(40, 1, self.event_function_clear_old_data, ())
        self.event_scheduler.enter(50, 1, self.event_function_backup_orch_f_log, ())
        self.event_scheduler.enter(60, 1, self.event_function_onebox_auth_batch, ())

        # scheduler : auto command
        self.event_scheduler.enter(70, 1, self.event_function_autocmd_scheduler, argument=(plugins,))

        # scheduler : MMS Send Status Sync
        self.event_scheduler.enter(80, 1, self.event_function_mms_send_status_sync, argument=(plugins,))


    def run(self):
        log.debug("Event Manager Start!")
        self.event_scheduler.run()
        
        
    def event_function_check_onebox(self):
        log.debug("[IN] Check One-Boxes")

        # redis connect
        redis_conn = redis.StrictRedis(host='localhost', port=6379, db=0)
        
        try:
            # Step 1. Get One-Box List
            log.debug("Get One-Box List")
            ob_db_result, ob_db_list = orch_dbm.get_server(mydb)
            if ob_db_result < 0:
                log.error("failed to get One-Box List from DB: %d %s" %(ob_db_result, ob_db_list))
            elif ob_db_result == 0:
                log.debug("No One-Box in DB")

            # Step 2. Select Target One-Boxes
            log.debug("Select Target One-Boxes")
            target_ob_list = []
            datetime_creteria = datetime.datetime.now() - datetime.timedelta(seconds=1800)
            for db_ob in ob_db_list:
                if db_ob['status'] == SRVStatus.RIS or db_ob['status'] == SRVStatus.RDS or db_ob['status'] == SRVStatus.INS:
                    if db_ob['modify_dttm'] is not None and db_ob['modify_dttm'] < datetime_creteria:
                        log.debug("Added into Target One-Box: %s, modify_dttm: %s" %(db_ob['onebox_id'], str(db_ob['modify_dttm'])))
                        target_ob_list.append(db_ob)
            
            #log.debug("Target OBs = %s" %str(target_ob_list))
            
            # Step 3. Check and Update One-Box Status
            log.debug("Check and Update One-Boxes")
            # log.debug('event > target_ob_list : %s' %str(target_ob_list))
            for ob in target_ob_list:
                ob_chk_result, ob_chk_data = check_onebox_valid(mydb, None, ob['onebox_id'], ob['nfsubcategory'])
                # log.debug('%s : ob_chk_result = %d, ob_chk_data = %s' %(str(ob), ob_chk_result, str(ob_chk_data)))

                if ob_chk_result == 0:
                    continue

                if ob_chk_result == -515:
                    log.debug("Cannot connect to the One-Box: %s" %ob['onebox_id'])
                    ob['status'] = SRVStatus.DSC
                    update_result, update_data = update_server_status(mydb, ob)
                    if update_result < 0:
                        log.error("failed to update One-Box Status for %s" %ob['onebox_id'])

                    # redis delete
                    redis_conn.delete(ob['onebox_id'])
                    log.debug("[REDIS] delete %s" %str(ob['onebox_id']))

                elif ob_chk_result < 0:
                    log.error("failed to check the One-Box Status: %s" %ob['onebox_id'])
                elif ob_chk_data.get('status') == "FAIL":
                    log.debug("%s Check Result is FAIL: %s" %(ob['onebox_id'], str(ob_chk_data)))
                    ob['status'] = SRVStatus.DSC
                    update_result, update_data = update_server_status(mydb, ob)
                    if update_result < 0:
                        log.error("failed to update One-Box Status for %s" %ob['onebox_id'])
                    #ob['status'] = SRVStatus.ERR
                    #update_result, update_data = update_server_status(mydb, ob)
                    #if update_result < 0:
                    #    log.error("failed to update One-Box Status for %s" %ob['onebox_id'])
                else:
                    log.debug("%s Check Result is OK: %s" %(ob['onebox_id'], str(ob_chk_data)))            
        except Exception, e:
            log.exception("Exception: %s" %str(e))            
        
        try:
            # Step 4. Schedule Next Event
            log.debug("[OUT] Next Event: Check One-Boxes After 1 Hour")
            self.event_scheduler.enter(7200, 1, self.event_function_check_onebox, ())
        except Exception, e:
            log.exception("Exception: %s" %str(e))
            return -HTTP_Internal_Server_Error, "Failed to add next event for checking One-Boxes"
        
        return 200, "OK"

    def event_function_check_onebox_new(self):
        log.debug("[IN] Check One-Boxes")

        # redis connect
        redis_conn = redis.StrictRedis(host='localhost', port=6379, db=0)

        try:
            # Step 1. Get One-Box List
            log.debug("Get One-Box List")
            # ob_db_result, ob_db_list = orch_dbm.get_server(mydb)
            ob_db_result, ob_db_list = orch_dbm.get_server_filters_wf(mydb, {})
            if ob_db_result < 0:
                log.error("failed to get One-Box List from DB: %d %s" % (ob_db_result, ob_db_list))
            elif ob_db_result == 0:
                log.debug("No One-Box in DB")

            # Step 2. Select Target One-Boxes
            log.debug("Select Target One-Boxes")
            target_ob_list = []
            datetime_creteria = datetime.datetime.now() - datetime.timedelta(seconds=1800)
            for db_ob in ob_db_list:
                if db_ob['status'] == SRVStatus.RIS or db_ob['status'] == SRVStatus.RDS or db_ob['status'] == SRVStatus.INS:
                    if db_ob['modify_dttm'] is not None and db_ob['modify_dttm'] < datetime_creteria:
                        log.debug("Added into Target One-Box: %s, modify_dttm: %s" % (db_ob['onebox_id'], str(db_ob['modify_dttm'])))
                        target_ob_list.append(db_ob)

            # log.debug("Target OBs = %s" %str(target_ob_list))

            # Step 3. Check and Update One-Box Status
            log.debug("Check and Update One-Boxes")
            # log.debug('event > target_ob_list : %s' %str(target_ob_list))
            for ob in target_ob_list:
                # ob_chk_result, ob_chk_data = check_onebox_valid(mydb, None, ob['onebox_id'], ob['nfsubcategory'])
                ob_chk_result, ob_chk_data = check_onebox_valid_em(mydb, None, ob['onebox_id'], ob)
                # log.debug('%s : ob_chk_result = %d, ob_chk_data = %s' %(str(ob), ob_chk_result, str(ob_chk_data)))

                if ob_chk_result == 0:
                    continue

                if ob_chk_result == -515:
                    log.debug("Cannot connect to the One-Box: %s" % ob['onebox_id'])
                    ob['status'] = SRVStatus.DSC
                    update_result, update_data = update_server_status(mydb, ob)
                    if update_result < 0:
                        log.error("failed to update One-Box Status for %s" % ob['onebox_id'])

                    # redis delete
                    redis_conn.delete(ob['onebox_id'])
                    log.debug("[REDIS] delete %s" % str(ob['onebox_id']))

                elif ob_chk_result < 0:
                    log.error("failed to check the One-Box Status: %s" % ob['onebox_id'])
                elif ob_chk_data.get('status') == "FAIL":
                    log.debug("%s Check Result is FAIL: %s" % (ob['onebox_id'], str(ob_chk_data)))
                    ob['status'] = SRVStatus.DSC
                    update_result, update_data = update_server_status(mydb, ob)
                    if update_result < 0:
                        log.error("failed to update One-Box Status for %s" % ob['onebox_id'])
                    # ob['status'] = SRVStatus.ERR
                    # update_result, update_data = update_server_status(mydb, ob)
                    # if update_result < 0:
                    #    log.error("failed to update One-Box Status for %s" %ob['onebox_id'])
                else:
                    log.debug("%s Check Result is OK: %s" % (ob['onebox_id'], str(ob_chk_data)))
        except Exception, e:
            log.exception("Exception: %s" % str(e))

        try:
            # Step 4. Schedule Next Event
            log.debug("[OUT] Next Event: Check One-Boxes After 1 Hour")
            self.event_scheduler.enter(7200, 1, self.event_function_check_onebox, ())
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "Failed to add next event for checking One-Boxes"

        return 200, "OK"


    def event_function_clear_old_data(self):
        log.debug("[IN] Clear Old Data")
        # Step 1. Clear Old Data of Backup Data
        
        # Step 2. Clear Old Date of Deleted Data
        
        # Last Step. Schedule Next Event
        log.debug("[OUT] Next Event: Clear Old Data After 10 Days")
        self.event_scheduler.enter(864000, 1, self.event_function_clear_old_data, ())
        pass


    def event_function_backup_orch_f_log(self):
        log.debug("[IN] Backup Orch-F Log")

        backup_date =  datetime.datetime.now() - datetime.timedelta(days=1)
        backup_date = backup_date.strftime("%Y-%m-%d")

        result = self._backup_orch_f_log(backup_date)
        if result < 0:
            self.event_scheduler.enter(3600, 1, self.event_function_backup_orch_f_log, ())
        else:
            tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
            tomorrow = tomorrow.strftime("%Y%m%d")
            next_time = datetime.datetime.strptime(tomorrow + "010000", "%Y%m%d%H%M%S")

            term = next_time -  datetime.datetime.now()
            self.event_scheduler.enter(term.seconds, 1, self.event_function_backup_orch_f_log, ())

            log.debug("[OUT] Next Event : Backup Orch-F Log after 1 day")


    def event_function_autocmd_scheduler(self, plugins):
        log.debug("[IN] Auto Command Scheduler")

        try:
            now = datetime.datetime.now()

            instance_dict = {}
            # query_string = "reserve = 'Y' AND reserve_date >= '%s' AND reserve_hour > '%s'" % (str(now.strftime('%Y-%m-%d')), str(now.strftime('%H')))
            query_string = "reserve = 'Y' AND (reserve_date > '%s' OR (reserve_date = '%s' AND reserve_hour > '%s'))"\
                           % (str(now.strftime('%Y-%m-%d')), str(now.strftime('%Y-%m-%d')), str(now.strftime('%H')))
            # log.debug("query_str = %s" %str(query_string))

            result, data = orch_dbm.get_table_data(mydb, instance_dict, 'tb_auto_cmd', query_string)

            # log.debug("data = %s" %str(data))

            target_list = []
            for d in data:
                auto_cmd_seq = {'sac_seq': d.get('sac_seq')}
                target_list.append(auto_cmd_seq)

            log.debug('target_list = %s' % str(target_list))

            if target_list:
                # wf_svr_ktcomm_manager
                wf_svr_ktcomm_manager = plugins['wf_svr_ktcomm_manager']

                # redis connect
                redis_conn = plugins.get("wf_redis")

                for d in data:
                    log.debug("sac_seq : %s" %str(d.get('sac_seq')))

                    # target list 조회하여 진행하지 않은 명령어 예약 재등록
                    t_instance_dict = {}
                    t_query_string = 'sac_seq = %s' %str(d.get('sac_seq'))

                    log.debug("t_query_string : %s" %str(t_query_string))

                    t_result, t_data = orch_dbm.get_table_data(mydb, t_instance_dict, 'tb_auto_cmd_target', t_query_string)
                    log.debug('t_data = %s' %str(len(t_data)))
                    
                    # target record 가 있는 경우는 진행중이거나 완료된 항목이므로 진행하지 않는다
                    if len(t_data) <= 0:
                        rcc_data = json.loads(d.get('rcc_data'))
    
                        rcc_data['sac_seq'] = d.get("sac_seq")
                        rcc_data['reserve'] = d.get("reserve")
    
                        # scheduler 등록을 위한 예약실행 시간 계산
    
                        # now = datetime.datetime.now()
                        now_time = time.time()
                        reserve_date = d.get("reserve_date").replace("-", "") + d.get("reserve_hour") + "0000"
                        reserve_dtt = datetime.datetime.strptime(reserve_date, "%Y%m%d%H%M%S")
    
                        # date_diff = reserve_dtt - now
                        #
                        # remained_days = date_diff.days
                        # remained_seconds = date_diff.seconds
                        #
                        # log.debug("remained_days = %s, remained_seconds = %s" % (str(remained_days), str(remained_seconds)))
                        # log.debug("일 차이를 초 단위로 변환 = %s" % str(remained_days * (60 * 60 * 24)))
                        #
                        # # 날짜를 초 단위로 변환 + 시/분/초를 초 단위로 변환
                        # term = (remained_days * (60 * 60 * 24)) + remained_seconds
                        #
                        # log.debug("term = %s" % str(term))
    
                        reserve_timestamp = time.mktime(reserve_dtt.timetuple())
                        term = int(reserve_timestamp - now_time)
    
                        log.debug("예약일시 : %s" % str(reserve_dtt))
                        log.debug("현재시간 : %s" % str(datetime.datetime.now()))
                        log.debug("스케쥴 예약 초 : %s" % str(term))

                        # redis get data
                        redis_key = "auto_cmd_sched.%s" % str(d.get("sac_seq"))
                        rd_result, rd_content = redis_conn.redis_get(redis_key)
                        # log.debug("%d, %s" % (rd_result, str(rd_content)))
    
                        if rd_content == None:
                            # redis data 가 없을때 다시 저장 : server_rcc_scheduler 에서 실행할 때 필요함
                            redis_setTime = term + 10
                            redis_msg = "Schedule data save : %s, expire : %s" % (str(d.get("sac_seq")), str(redis_setTime))
                            redis_result, redis_data = redis_conn.redis_set(redis_key, rcc_data, redis_msg, redis_setTime)
    
                        # scheduler 등록
                        self.event_scheduler.enter(term, 1, wf_svr_ktcomm_manager.server_rcc_scheduler, argument=(redis_key, plugins))
                        # log.debug("scheduler enter success : %s" % (str(self.event_scheduler.queue)))

        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "Failed to add next event for Auto Command Scheduler"

        log.debug("[OUT] Next Event: Auto Command Scheduler After 1 Hour")
        # self.event_scheduler.enter(3600, 1, self.event_function_autocmd_scheduler, argument=(plugins,))

        return 200, "OK"


    def event_function_mms_send_status_sync(self, plugins):
        log.debug("[IN] Scheduler : MMS Send status sync")

        try:
            # MMS Send status sync process

            # wf_svr_ktcomm_manager
            wf_svr_ktcomm_manager = plugins['wf_svr_ktcomm_manager']
            wf_svr_ktcomm_manager.server_scheduler_sync_mms_send(plugins)

            # scheduler 등록
            self.event_scheduler.enter(3600, 1, self.event_function_mms_send_status_sync, argument=(plugins,))
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "Failed to add next event for Auto Command Scheduler"

        log.debug("[OUT] Next Event: MMS Send status sync Scheduler After 1 Hour")
        return 200, "OK"


    @staticmethod
    def _backup_orch_f_log(backup_date):
        """
        backup_date 에 쌓인 로그를 모아 백업파일을 만든다.
        :param backup_date: YYYY-MM-DD 해당 날짜의 로그를 백업한다.
        :return:
        """
        ORCH_F_LOG_DIR = "/var/log/onebox"
        TITLE = "NFV-ORCH-F"
        try:
            cfgManager = ConfigManager.get_instance()
            config = cfgManager.get_config()
            MOUNT_PATH = config.get('image_mount_path', "")
            ORCH_F_BACKUP_DIR = os.path.join(MOUNT_PATH, "backup_log")
            # 0. 백업 디렉토리 생성
            if not os.path.exists(ORCH_F_BACKUP_DIR):
                log.debug("Create Backup directory!")
                os.mkdir(ORCH_F_BACKUP_DIR, 0755)

            if os.path.exists(os.path.join(ORCH_F_BACKUP_DIR, TITLE+"_"+backup_date+".log")):
                return 0
        except Exception, e:
            log.error(str(e))
            return -1

        try:
            end_date = datetime.datetime.strptime(backup_date, "%Y-%m-%d") + datetime.timedelta(days=1)
            end_date = end_date.strftime("%Y-%m-%d")

            # print "backup date : %s" % backup_date
            # print "end date : %s" % end_date

            backup_data = None
            log_files = map(lambda x : "NFV-ORCH-F.log" + ("" if x==0 else "."+str(x)) ,range(0, 11))
            for log_f_name in log_files:

                if not os.path.exists(os.path.join(ORCH_F_LOG_DIR, log_f_name)):
                    continue
                # print os.path.join(ORCH_F_LOG_DIR, log_f_name)
                log_fo = None
                try:
                    log_fo = open(os.path.join(ORCH_F_LOG_DIR, log_f_name), "rb")
                    log_contents = log_fo.read()
                except Exception, e:
                    raise Exception(str(e))
                finally:
                    if log_fo:
                        log_fo.close()

                start_idx = log_contents.find(backup_date)
                if start_idx > 0:
                    start_idx = log_contents.find("\n"+backup_date)
                    # print "다시 start_idx = %d" % start_idx
                # print "start_idx = %d" % start_idx

                if start_idx < 0:
                    continue

                end_idx = log_contents.find(end_date)
                if end_idx > 0:
                    end_idx = log_contents.find("\n"+end_date)
                    # print "다시 end_idx = %d" % end_idx
                # print "end_idx = %d" % end_idx

                if start_idx == 0 and end_idx > 0:
                    backup_data = log_contents[:end_idx-1]
                elif start_idx == 0 and end_idx < 0:
                    backup_data = log_contents + backup_data
                elif start_idx > 0 > end_idx:
                    backup_data = log_contents[start_idx+1:] + backup_data
                elif end_idx > start_idx > 0:
                    backup_data = log_contents[start_idx+1:end_idx-1]

            if backup_data:
                backup_fo = open(os.path.join(ORCH_F_BACKUP_DIR, TITLE+"_"+backup_date+".log"), "wb")
                backup_fo.write(backup_data)
                backup_fo.close()

        except Exception, e:
            log.error("Exception:%s" % str(e))
            return -1
        return 1


    def event_function_onebox_auth_batch(self):
        log.debug("[IN] Check One-Box auth_key batch")

        result, batch_data = orch_dbm.get_onebox_auth_batch(mydb, {})
        if result < 0:
            log.error("Failed to get One-Box auth-key batch data")
        elif result == 0:
            log.debug("No data of auth-key batch")
        else:

            for batch_info in batch_data:
                reserve_dtt = datetime.datetime.strptime(batch_info["reserve_dtt"], "%Y%m%d%H")
                if reserve_dtt > datetime.datetime.now():
                    term = reserve_dtt - datetime.datetime.now()
                    remained_seconds = term.seconds
                else:
                    # 배치 예약 시간이 이미 지나버린 경우 데이타 버리기로 함.
                    # remained_seconds = 0
                    orch_dbm.delete_onebox_auth_batch(mydb, {"batch_seq":batch_info["batch_seq"]})
                    return

                if batch_info["batch_type"] == "B":
                    self.event_scheduler.enter(remained_seconds, 1, deploy_batch, (mydb, batch_info["reserve_dtt"],))
                else:
                    self.event_scheduler.enter(remained_seconds, 1, deploy_fail_batch, (mydb, batch_info["reserve_dtt"],))

