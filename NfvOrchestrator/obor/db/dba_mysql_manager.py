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

"""
DB Access Manager implements all the methods to interact with WFM-DB for KT One-Box Service.
"""

import json
import yaml
import os
import time
import sys
import datetime
import  MySQLdb
from utils.config_manager import ConfigManager
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils import auxiliary_functions as af
from orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Conflict

from utils.aes_chiper import AESCipher


def _mysql_connect():
    # Initialize DB connection
    cfgManager = ConfigManager.get_instance()
    global_config = cfgManager.get_config()

    cipher = AESCipher.get_instance()
    db_passwd = cipher.decrypt(global_config['mysql_pw'])

    conn = MySQLdb.connect(db=global_config['mysql_db_name'], user=global_config['mysql_user'], passwd=db_passwd,
                           host=global_config['mysql_host'], port=global_config['mysql_port'])

    log.debug("mysql connect() Success!")

    return conn


def _mysql_close(conn):
    if conn is not None:
        conn.close()

    log.debug("mysql close!")

    return "OK"


# fetchType : 1-fetchone, 2-fetchall
def _get(conn, query, fetchType=1):
    try:
        conn.set_character_set('utf8')
        cur = conn.cursor()
        ret = cur.execute(query)

        if ret < 1:
            conn.rollback()
            cur.close()  # 2017.04.13 김승주전임 추가 요청, connection 문제
            return -1, ret
        else:
            conn.commit()

            if fetchType == 2:
                rows = cur.fetchall()
            else:
                rows = cur.fetchone()

            cur.close()  # 2017.04.13 김승주전임 추가 요청, connection 문제
            # return cur.lastrowid
            return 200, rows
    except Exception, e:
        log.debug(e)
        conn.rollback()
        return -1, e
    # finally:
    #     if cur != None: cur.close()
    #     if conn != None: conn.close()


def _insert(conn, sql):
    try:
        conn.set_character_set('utf8')
        cur = conn.cursor()
        ret = cur.execute(sql)

        if ret < 1:
            conn.rollback()
            cur.close()  # 2017.04.13 김승주전임 추가 요청, connection 문제
            return -1, ret
        else:
            conn.commit()
            rowId = cur.lastrowid
            cur.close()  # 2017.04.13 김승주전임 추가 요청, connection 문제
            return 200, rowId
    except Exception, e:
        log.debug(e)
        conn.rollback()
        return -1, e


# def getData(conn, TBNAME, COL, WHERE=None, ORDER=None, LIMIT=None):
def getData(conn, **sql_dict):
    # fetchType : 1 - fetchone, 2 - fetchall
    fetchType = 2

    select_ = "SELECT " + ("*" if 'SELECT' not in sql_dict else ",".join(map(str, sql_dict['SELECT'])))
    from_ = "FROM " + str(sql_dict['FROM'])
    order_ = "ORDER BY " + str(sql_dict['ORDER']) if 'ORDER' in sql_dict else ""

    if 'WHERE' in sql_dict and len(sql_dict['WHERE']) > 0:
        w = sql_dict['WHERE']
        where_ = "WHERE " + " AND ".join(
            map(lambda x: str(x) + (" is Null" if w[x] is None else "='" + str(w[x]) + "'"), w.keys()))
    else:
        where_ = ""

    if 'LIKE' in sql_dict and len(sql_dict['LIKE']) > 0:
        w = sql_dict['LIKE']
        where_2 = " AND ".join(
            map(lambda x: str(x) + (" is Null" if w[x] is None else " LIKE '" + str(w[x]) + "'"), w.keys()))
        if len(where_) == 0:
            where_ = "WHERE " + where_2
        else:
            where_ = where_ + " AND " + where_2

    if 'WHERE_NOT' in sql_dict and len(sql_dict['WHERE_NOT']) > 0:
        w = sql_dict['WHERE_NOT']
        where_2 = " AND ".join(
            map(lambda x: str(x) + (" is not Null" if w[x] is None else "<>'" + str(w[x]) + "'"), w.keys()))
        if len(where_) == 0:
            where_ = "WHERE " + where_2
        else:
            where_ = where_ + " AND " + where_2

    if 'WHERE_NOTNULL' in sql_dict and len(sql_dict['WHERE_NOTNULL']) > 0:
        w = sql_dict['WHERE_NOTNULL']
        where_2 = " AND ".join(map(lambda x: str(x) + " is not Null", w))
        if len(where_) == 0:
            where_ = "WHERE " + where_2
        else:
            where_ = where_ + " AND " + where_2

    if 'WHERE_IN' in sql_dict and len(sql_dict['WHERE_IN']) > 0:
        w = sql_dict['WHERE_IN']
        where_2 = " AND ".join(
            map(lambda x: str(x) + (" is Null" if w[x] is None else " IN (" + str(w[x]) + ")"), w.keys())
        )
        if len(where_) == 0:
            where_ = "WHERE " + where_2
        else:
            where_ = where_ + " AND " + where_2

    limit_ = "LIMIT " + str(sql_dict['LIMIT']) if 'LIMIT' in sql_dict else ""

    sql = " ".join((select_, from_, where_, order_, limit_))
    result, rows = _get(conn, sql, fetchType)

    if result < 0:
        log.error("get error : [%s] %d %s" % (str(sql_dict['FROM']), result, rows))
        return result, rows

    return result, rows


def insertData(conn, TBNAME, insertData):
    INSERT = "insert into %s " % str(TBNAME)
    cols = ""
    values = ""

    if insertData is not None:
        for key, val in insertData.items():
            # log.debug(key + " = '%s'" % str(val))
            if values != "":
                cols += ", "
                values += ", "

            cols += key
            values += "'%s'" % str(val)

    INSERT += " (%s) values(%s)" % (str(cols), str(values))

    # log.debug("insertData : query = %s" % str(INSERT))

    result, rowid = _insert(conn, INSERT)

    if result < 0:
        log.error("get error : [%s] %d %s" % (str(TBNAME), result, rowid))
        return result, rowid

    return result, rowid
