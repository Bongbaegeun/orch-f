# -*- coding: utf-8 -*-

from sbpm.plugin_spec.redis.GeneralRedisSpec import GeneralRedisSpec

import requests
import json
import sys
import time
import redis

# import db.dba_manager as orch_dbm

from httplib import HTTPException
from requests.exceptions import ConnectionError
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()


class GeneralRedis(GeneralRedisSpec):
    def __init__(self):
        self.host = 'localhost'
        self.port = 6379
        self.db = 0
        self.conn = None

        try:
            self.conn = redis.StrictRedis(host=self.host, port=self.port, db=self.db)
            # conn = redis.Redis(host=self.host, port=self.port, db=self.db)
        except Exception as e:
            log.debug('Redis DB connection error : ', e)

    # redis set data
    # def redis_set(self, conn, key, data, msg):
    def redis_set(self, key, data, msg, set_time=1800):
        # conn.set(key, json.dumps(data))
        try:
            self.conn.set(key, json.dumps(data), set_time)
            log.debug('[REDIS] Set : %s' % str(msg))
            return 200, "OK"
        except Exception as e:
            log.debug('[REDIS] Set error : %s' % str(e))
            return -1, e


    # redis get data
    # def redis_set(self, conn, key, data, msg):
    def redis_get(self, key):
        # conn.set(key, json.dumps(data))
        try:
            data = self.conn.get(key)
            # log.debug('[REDIS] Get : %s' % str(msg))
            return 200, data
        except Exception as e:
            log.debug('[REDIS] Get error : %s' % str(e))
            return -1, e

    # redis delete data
    def redis_del(self, key):
        try:
            data = self.conn.delete(key)
            return 200, data
        except Exception as e:
            log.debug('[REDIS] Get error : %s' % str(e))
            return -1, e


    # diff noti
    def diff_noti(self, diff_dict):
        server_id = diff_dict.get('server_id')
        http_content = diff_dict.get('http_content')

        # DB 정상 동작을 위해 초기값
        rtn_result, rtn_msg = 200, None

        try:
            # if self.conn.ping() is None:
            #     log.debug('Redis connection is Fail')
            #     raise Exception('Redis DB error')

            if self.conn.exists(server_id) is None:
                rtn_msg = 'not save noti data... redis save data and proceed...'
                # result, content = self.redis_set(self.conn, server_id, http_content, rtn_msg)
                #
                # if result < 0:
                #     raise Exception(content)
            else:
                if self.conn.get(server_id) != json.dumps(http_content):
                    rtn_msg = 'differ in save data... redis save data and proceed...'
                    # result, content = self.redis_set(self.conn, server_id, http_content, rtn_msg)
                    #
                    # if result < 0:
                    #     raise Exception(content)
                else:
                    rtn_result = -1
                    rtn_msg = 'No processing... noti data is same!'
        except Exception as e:
            log.debug('Redis DB error : ', e)
            rtn_msg = e

        return rtn_result, rtn_msg
