# coding=utf-8

import json
import copy
import sched
import time, datetime

import db.dba_manager as orch_dbm
import db.dba_mysql_manager as orch_mysql_dbm
import threading
from utils.config_manager import ConfigManager
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from engine.server_status import SRVStatus
from utils import auxiliary_functions as af
from wfm.plugin_spec.WFSvrKtCommSpec import WFSvrKtCommSpec
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

from engine.server_status import SRVStatus
from engine.nsr_status import NSRStatus
from engine.mms_result import MMSResultCode


class WFSvrKtComm(WFSvrKtCommSpec):
    # 메인 #########################################################################################################################
    def server_rcc(self, req_info, plugins, use_thread=True):
        log.debug("             ##########       Server Auto Remote Command Control       ############################")

        # plugin load : orch_comm
        orch_comm = plugins.get('orch_comm')

        # port set
        port = 9922
        if req_info.get("cmdMode") == "pre-viledge" or req_info.get("cmdMode") == "start-shell":
            port = 2233

        # conn info
        connInfo = req_info.get("connInfo").split("||")
        conn_user = connInfo[0]
        conn_pwd = connInfo[1]

        # default data set
        rcc_data = {
            "tid": req_info.get("tid"),
            "userid": req_info.get("userid"),
            "username": req_info.get("username"),
            "cmd" : req_info.get("cmdTxt"),
            "cmdMode" : req_info.get("cmdMode"),
            "cmdType" : req_info.get("cmdType"),
            "port": port,
            "user": conn_user,
            "pwd": conn_pwd,
            "target_onebox": "",
            "server" : [],
            "reservation": {
                "reserve": req_info.get("reserve").strip(),
                "reserve_date": req_info.get("reserve_date"),
                "reserve_hour": req_info.get("reserve_hour"),
            }
        }

        SvrLst = copy.deepcopy(req_info.get('serverList'))

        ################    TEST Code   ################################################################
        # if (req_info.get("userid") == "whiteheads"):
        #     TS = req_info.get('serverList').split("|")
        #     chgServerList = copy.deepcopy(req_info.get('serverList'))
        #
        #     end = 50 / len(TS)
        #
        #     for i in range(end):
        #         chgServerList += "|" + req_info.get('serverList')
        #
        #     SvrLst = chgServerList
        #
        #     log.debug("SvrLst = %s" % str(SvrLst))
        ################    TEST Code   ################################################################

        target_onebox = ""
        targetNo = 0
        serverList = SvrLst.split("|")

        for onebox in serverList:
            # DB get onebox info : publicip
            com_dict = {'onebox_id': onebox}
            ob_result, ob_content = orch_comm.getFunc('get_server_all_with_filter_wf', com_dict)
            com_dict.clear()

            if ob_result <= 0:
                log.error("get_server_with_filter Error %d %s" % (ob_result, ob_content))
                return ob_result, ob_content

            ob_data = ob_content[0]

            ct_result, ct_content = orch_dbm.get_customer_id(ob_data.get('customerseq'))

            if ct_result <= 0:
                log.error("get_customer_id Error %d %s" % (ct_result, ct_content))
                return ct_result, ct_content

            apdata = {
                "onebox_id": onebox,
                "public_ip": ob_data.get("publicip"),
                # "nsseq": ob_data.get("nsseq"),
                "customername": ct_content.get("customername"),
                "orgnamescode": ob_data.get("orgnamescode")
            }

            if targetNo > 0:
                target_onebox += "|"

            target_onebox += onebox

            rcc_data['server'].append(apdata)
            targetNo += 1

        rcc_data['target_onebox'] = target_onebox

        # log.debug("rcc_data = %s" %str(rcc_data))

        # threading start
        try:

            log_key = "[Auto Remote Command : %s]" % str(rcc_data.get("tid"))

            # DB insert : tb_auto_cmd
            log.debug("%s tb_auto_cmd insert" % str(log_key))

            ins_cmdType = rcc_data.get("cmdMode")
            if rcc_data.get("cmdMode") == "pre-viledge":
                if rcc_data.get("cmdType") == "show":
                    ins_cmdType = "[단일명령] " + rcc_data.get("cmdMode")
                elif rcc_data.get("cmdType") == "set":
                    ins_cmdType = "[설정] " + rcc_data.get("cmdMode")

            ins_auto_cmd = {
                "cmd_text": rcc_data.get("cmd"),
                "userid": rcc_data.get("userid"),
                "username": rcc_data.get("username"),
                "cmdType": ins_cmdType,
                "target_onebox": rcc_data.get("target_onebox"),
                "reserve": rcc_data.get("reservation").get("reserve"),
                "reserve_date": rcc_data.get("reservation").get("reserve_date"),
                "reserve_hour": rcc_data.get("reservation").get("reserve_hour"),
                "rcc_data": json.dumps(rcc_data)
            }

            db_result, db_data = orch_dbm.insert_table_data("tb_auto_cmd", ins_auto_cmd)
            if db_result <= 0:
                log.debug("%s Error tb_auto_cmd insert" % str(log_key))
                return db_result, db_data

            sac_seq = db_data
            rcc_data['sac_seq'] = sac_seq
            rcc_data['reserve'] = req_info.get("reserve")

            if req_info.get("reserve") == "Y":
                if use_thread:
                    th = threading.Thread(target=self._reserve_auto_command_control, args=(rcc_data, plugins, use_thread))
                    th.start()
            else:
                if use_thread:
                    th = threading.Thread(target=self._auto_command_control, args=(rcc_data, plugins))
                    th.start()
                else:
                    return self._auto_command_control(rcc_data, plugins)
        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "One-Box 서버 등록이 실패하였습니다. 원인: %s" % str(e)

        rt_dict = {'result': "OK"}
        return 200, rt_dict


    # 예약실행 삭제
    def server_rcc_reserve_delete(self, req_info, plugins):
        log_key = "[Auto Remote Command]"

        # redis 삭제
        redis_conn = plugins.get("wf_redis")
        redis_key = "auto_cmd_sched.%s" % str(req_info.get('sac_seq'))
        rd_result, rd_data = redis_conn.redis_del(redis_key)

        # DB 삭제
        db_result, db_data = orch_dbm.delete_table_data("tb_auto_cmd", "sac_seq", req_info.get('sac_seq'))
        if db_result <= 0:
            log.debug("%s Error tb_auto_cmd delete" % str(log_key))
            return db_result, db_data

        rt_dict = {'result': "OK"}
        return 200, rt_dict


    # 예약 실행 스케쥴러
    def server_rcc_scheduler(self, redis_key, plugins):
        log.debug("redis_key = %s" %str(redis_key))

        redis_result, redis_data = plugins.get("wf_redis").redis_get(redis_key)

        log.debug("redis_data = %s" % str(redis_data))

        if redis_data is not None:
            rcc_data = json.loads(redis_data)
            self._auto_command_control(rcc_data, plugins)

            # 예약실행 처리 후 redis 삭제
            plugins.get("wf_redis").redis_del(redis_key)

        return 200, "OK"


    def server_change_ip(self, req_info, plugins):
        log.debug("             ##########       Server Change IP       ############################")

        # plugin load : orch_comm
        orch_comm = plugins.get('orch_comm')

        # DB get onebox info : publicip
        com_dict = {'onebox_id': req_info.get("onebox_id")}
        ob_result, ob_content = orch_comm.getFunc('get_server_all_with_filter_wf', com_dict)
        com_dict.clear()

        if ob_result <= 0:
            log.error("get_server_with_filter Error %d %s" % (ob_result, ob_content))
            return ob_result, ob_content

        ob_data = ob_content[0]
        log.debug("ob_data = %s" %str(ob_data))

        old_public_ip = ob_data.get("publicip")
        old_mgmt_ip = ob_data.get("publicip")
        old_public_gw = ob_data.get("publicgwip")
        old_obagent_base_url = ob_data.get("obagent_base_url")
        old_web_url = ob_data.get("web_url")

        if old_mgmt_ip != req_info.get("mgmt_ip") and old_public_ip != req_info.get("public_ip"):
            server_dict = {
                'serverseq': ob_data.get("serverseq"),
                'mgmtip': req_info.get("mgmt_ip"),
                'publicip': req_info.get("public_ip"),
                'publicgwip': req_info.get("public_gw"),
            }

            if old_obagent_base_url is not None:
                server_dict['obagent_base_url'] = old_obagent_base_url.replace(old_public_ip, req_info.get("public_ip"))

            if old_web_url is not None:
                server_dict['web_url'] = old_web_url.replace(old_public_ip, req_info.get("public_ip"))

            log.debug("server_dict = %s" %str(server_dict))

            result, data = orch_dbm.update_server(server_dict)
            if result < 0:
                log.error("server_change_ip() failed to DB Update for Server")
                return result, data

        return 200, "OK"


    def mms_send(self, req_info, plugins, use_thread=True):
        log.debug("             ##########       MMS : SEND       ############################")

        # plugin load : orch_comm
        orch_comm = plugins.get('orch_comm')

        # get next mmsseq
        select_ = "max(mmsseq) + 1 as nextseq"
        db_result, db_data = orch_dbm.get_table_data("tb_mms_send", select=select_)

        # log.debug("db_data = %s" %str(db_data))

        if db_result <= 0:
            log.debug("Error tb_mms_send get max seq")
            return db_result, db_data

        req_info['mmsseq'] = int(db_data[0].get('nextseq'))

        # threading start
        try:
            if use_thread:
                th = threading.Thread(target=self._thread_mms_send, args=(req_info, plugins))
                th.start()
            else:
                return self._thread_mms_send(req_info, plugins)

        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "MMS 발송이 실패하였습니다. 원인: %s" % str(e)

        rt_dict = {'result': "OK"}
        return 200, rt_dict


    # 내장함수 #########################################################################################################################
    def _auto_command_control(self, rcc_data, plugins):
        log.debug("             ##########       Thread Start :: Server Auto Remote Command Control       ############################")
        log_key = "[Auto Remote Command : %s]" %str(rcc_data.get("tid"))

        log.debug("rcc_data = %s" % str(rcc_data))

        sac_seq = rcc_data.get("sac_seq")

        ssh_data = {
            "host": None,
            "port": rcc_data.get("port"),
            "user": rcc_data.get("user"),
            "pwd": rcc_data.get("pwd"),
            "cmd": rcc_data.get("cmd"),
            "cmdMode": rcc_data.get("cmdMode"),
            "cmdType": rcc_data.get("cmdType"),
        }

        rt_result, rt_data = 0, None

        for onebox in rcc_data.get("server"):
            # DB insert : tb_auto_cmd_target
            log.debug("%s tb_auto_cmd_target insert" % str(log_key))

            target_data = {
                "sac_seq": sac_seq,
                "onebox_id": onebox.get("onebox_id"),
                "public_ip": onebox.get("public_ip"),
                "result": "",
                # "result_text": "",
                "customername": onebox.get("customername"),
                "orgnamescode": onebox.get("orgnamescode")
            }

            db_result, db_data = orch_dbm.insert_table_data("tb_auto_cmd_target", target_data)
            if db_result <= 0:
                log.debug("%s Error tb_auto_cmd_target insert" % str(log_key))
                return db_result, db_data

            act_seq = db_data

            # ssh command excute start
            ssh_data['host'] = onebox.get("public_ip")
            ssh_result, ssh_output = plugins.get("wf_ssh").execute_cmd(ssh_data)

            # log.debug("%s ssh_output = %s" % (str(log_key), str(ssh_output)))

            if ssh_result < 0:
                ###     error excute command      ####################################################

                # DB update : tb_auto_cmd_target
                rt_result, rt_data = -HTTP_Internal_Server_Error, ssh_output
                log.debug("%s tb_auto_cmd_target fail update" % str(log_key))

                result_text = json.dumps({"result_text": str(ssh_output)}, ensure_ascii=False)

                target_data = {
                    "result": "Fail",
                    "result_text": result_text,
                }

                target_where = {
                    "act_seq": act_seq
                }

                db_result, db_data = orch_dbm.update_table_data("tb_auto_cmd_target", target_data, target_where)
                if db_result < 0:
                    log.debug("%s Error tb_auto_cmd_target update" % str(log_key))
                    return db_result, db_data

                log.debug("%s Error execute_cmd : %d, %s" %(str(log_key), rt_result, str(rt_data)))
            else:
                ###     success excute command      ####################################################
                # DB update : tb_auto_cmd_target
                log.debug("%s tb_auto_cmd_target success update" % str(log_key))

                result_text = json.dumps({"result_text": str(ssh_output)}, ensure_ascii=False)

                target_data = {
                    "result": "OK",
                    "result_text": result_text,
                }

                target_where = {
                    "act_seq": act_seq
                }

                # log.debug("%s target_data = %s" % (str(log_key), str(target_data)))

                db_result, db_data = orch_dbm.update_table_data("tb_auto_cmd_target", target_data, target_where)
                if db_result < 0:
                    log.debug("%s Error tb_auto_cmd_target update" % str(log_key))
                    return db_result, db_data

        log.debug("             ##########       Thread Finished :: Server Auto Remote Command Control       ############################")

        return 200, "OK"


    def _reserve_auto_command_control(self, rcc_data=None, plugins=None, use_thread=None):
        log.debug("             ##########       Thread Start :: Server Auto Remote Command Control Reserve       ############################")
        log.debug("args = %s" %str(rcc_data))

        # now = datetime.datetime.now()
        # now_time = time.time()
        # reserve_date = rcc_data.get("reservation").get("reserve_date").replace("-", "") + rcc_data.get("reservation").get("reserve_hour") + "0000"
        #
        # reserve_dtt = datetime.datetime.strptime(reserve_date, "%Y%m%d%H%M%S")
        # log.debug("예약일시 = %s" % str(reserve_dtt))
        # log.debug("현재시간 = %s" % str(datetime.datetime.now()))
        #
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


        now_time = time.time()
        reserve_date = rcc_data.get("reservation").get("reserve_date").replace("-", "") + rcc_data.get("reservation").get("reserve_hour") + "0000"
        reserve_dtt = datetime.datetime.strptime(reserve_date, "%Y%m%d%H%M%S")

        reserve_timestamp = time.mktime(reserve_dtt.timetuple())
        term = int(reserve_timestamp - now_time)

        log.debug("예약일시 : %s" % str(reserve_dtt))
        log.debug("현재시간 : %s" % str(datetime.datetime.now()))
        log.debug("스케쥴 예약 초 : %s" % str(term))



        # redis data save
        redis_key = "auto_cmd_sched.%s" %str(rcc_data.get("sac_seq"))
        redis_setTime = term + 10
        redis_msg = "Schedule data save : %s, expire : %s" % (str(rcc_data.get("sac_seq")), str(redis_setTime))
        redis_result, redis_data = plugins.get("wf_redis").redis_set(redis_key, rcc_data, redis_msg, redis_setTime)


        # scheduler insert
        log.debug("     Scheduler Insert Start!!!     ")

        s = sched.scheduler(time.time, time.sleep)
        s.enter(term, 1, self.server_rcc_scheduler, argument=(redis_key, plugins))
        log.debug("sched.queue = %s" % str(s.queue))
        s.run()

        log.debug("     Scheduler Insert Success!!!     ")


    def _thread_reserve(self, rcc_data=None, plugins=None, use_thread=None):
        log.debug("     Scheduler Test Success!!!     ")


    def _thread_mms_send(self, req_info, plugins):
        log.debug("     ##########       Thread Start :: MMS SNED       ############################")

        # Initialize DB connection
        cfgManager = ConfigManager.get_instance()
        global_config = cfgManager.get_config()

        # mysql connect
        mysql_conn = orch_mysql_dbm._mysql_connect()

        tbname = "SDK_MMS_SEND"
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        surveyType = "서비스센터 만족도"
        mms_seq = req_info.get('mmsseq')

        if int(req_info.get('surveyType')) == 2:
            surveyType = "상품 만족도"

        insertData = {
            'USER_ID': global_config['sms_id'],
            'SCHEDULE_TYPE': 0,  # 0:즉시전송, 1:예약전송
            'SUBJECT': "설문조사 MMS 발송 : %s" % str(surveyType),
            'CALLBACK': global_config['sms_callback'],  # 콜백번호(회신번호)
            'DEST_COUNT': 1,  # 수신자 카운트(최대 100건 까지 가능)
            'DEST_INFO': '',  # 고객사|연락처(-)없이
            'MMS_MSG': '',  # 메세지 내용(최대 4000 byte)
            'MSG_TYPE': 0,  # 메세지 타입(0일 경우 text 타입 그대로 단말에 표현)
        }

        postData = copy.deepcopy(insertData)

        for c in req_info.get('customerList'):
            mms_msg = req_info.get('mms_msg') + '\n\n' + c.get('surveyUrl') + "?cs=%s" % str(mms_seq)
            dest_info = c.get('customerNm') + '^' + c.get('phone')

            postData['customerNm'] = c.get('customerNm')
            postData['customerseq'] = c.get('customerSeq')
            postData['MMS_MSG'] = mms_msg
            # postData['DEST_INFO'] = dest_info
            postData['mms_type'] = 1            # mms_type : 0-기본, 1-설문조사

            # postgresql 먼저 입력 후, rowid 를 mms id(MSG_ID) 로 저장
            db_result, db_data = orch_dbm.insert_table_data("tb_mms_send", postData)
            if db_result <= 0:
                log.debug("Error tb_mms_send insert")
                return db_result, db_data

            insertData['MSG_ID'] = mms_seq
            insertData['MMS_MSG'] = mms_msg   # mms 발송 내용
            insertData['DEST_INFO'] = dest_info
            insertData['NOW_DATE'] = timestamp          # DB 입력시간: YYYYMMDDHHMMSS
            insertData['SEND_DATE'] = timestamp         # 발송 희망시간: YYYYMMDDHHMMSS

            result, content = orch_mysql_dbm.insertData(mysql_conn, tbname, insertData)
            if result < 0:
                # mysql close
                orch_mysql_dbm._mysql_close(mysql_conn)

                log.debug("get data error %s" % str(content))
                return result, {'result': content}

            mms_seq += 1

        # mysql close
        orch_mysql_dbm._mysql_close(mysql_conn)


        # scheduler insert
        log.debug("     Scheduler Insert Start!!!     ")

        s = sched.scheduler(time.time, time.sleep)
        log.debug("sched.queue = %s" % str(s.queue))
        s.enter(300, 1, self.server_scheduler_sync_mms_send, argument=(plugins,))
        log.debug("sched.queue = %s" % str(s.queue))
        s.run()

        log.debug("     Scheduler Insert Success!!!     ")

        log.debug("     ##########       Thread Finished :: MMS SNED       ############################")
        return 200, "OK"


    def server_scheduler_sync_mms_send(self, plugins):
        log.debug("[IN] Scheduler : MMS Send status sync")

        try:
            # MMS Send status sync process

            # mysql connect
            mysql_conn = orch_mysql_dbm._mysql_connect()

            result, contents = orch_dbm.get_table_data("tb_mms_send", "mmsseq", {"send_result": 0})
            if result < 0:
                log.debug("Error tb_mms_send get")
                return result, contents

            # log.debug("get table data = %s" %str(contents))

            _in = ""
            for con in contents:
                if _in != "":
                    _in += ", "
                else:
                    _in += ""

                _in += str(con.get("mmsseq"))

            where_in = {"MSG_ID": _in}

            # log.debug("where_in = %s" % str(where_in))

            tbname = "SDK_MMS_REPORT_DETAIL"
            select = "MSG_ID, RESULT"
            result, rows = orch_mysql_dbm.getData(mysql_conn, FROM=tbname, SELECT=(select,), WHERE_IN=where_in)
            if result < 0:
                log.debug("get data error : %s" % str(rows))

                # mysql close
                orch_mysql_dbm._mysql_close(mysql_conn)

                return result, {'result': rows}
            elif result == 0:
                log.debug("no search data : %s" % str(rows))

                # mysql close
                orch_mysql_dbm._mysql_close(mysql_conn)

                return result, {'result': rows}

            # log.debug("mysql db select : %s" % str(rows))

            if rows:
                resultcode = MMSResultCode()

                succ_seq = ""
                fail_seq = ""

                for row in rows:
                    # result 컬럼 비교후 postgres tb_mms_send status update
                    if resultcode.getResult(row[1]).find("WAIT") < 0:
                        if resultcode.getResult(row[1]) == "SUCC":
                            if succ_seq != "":
                                succ_seq += ", "
                            succ_seq += str(row[0])
                        else:
                            if fail_seq != "":
                                fail_seq += ", "
                            fail_seq += str(row[0])

                # log.debug("succ_seq = %s" % str(succ_seq))
                # log.debug("fail_seq = %s" % str(fail_seq))

                tbname = "tb_mms_send"
                if succ_seq != "":
                    sql = "update %s set send_result = 1 where mmsseq in (%s)" % (str(tbname), str(succ_seq))
                    db_result, db_data = orch_dbm.update_table_data_free(sql)
                    if db_result < 0:
                        log.debug("Error tb_mms_send success update")
                        return db_result, db_data

                    log.debug("Success data Update tb_mms_send target : %s" % str(succ_seq))

                if fail_seq != "":
                    sql = "update %s set send_result = 2 where mmsseq in (%s)" % (str(tbname), str(fail_seq))
                    db_result, db_data = orch_dbm.update_table_data_free(sql)
                    if db_result < 0:
                        log.debug("Error tb_mms_send failed update")
                        return db_result, db_data

                    log.debug("Failed data Update tb_mms_send target : %s" % str(fail_seq))


            # mysql close
            orch_mysql_dbm._mysql_close(mysql_conn)

        except Exception, e:
            log.exception("Exception: %s" % str(e))
            return -HTTP_Internal_Server_Error, "Failed to add next event for Auto Command Scheduler"

        # log.debug("[OUT] Next Event: MMS Send status sync Scheduler After 1 Hour")
        return 200, "OK"
