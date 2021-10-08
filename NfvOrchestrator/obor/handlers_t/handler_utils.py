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


import yaml
import json
import datetime
import sys
import psycopg2.extras

from jsonschema import validate as js_v, exceptions as js_e

from handlers_t.http_response import HTTPResponse
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

def format_out(request, data, code = 200):
    '''return string of dictionary data according to requested json, yaml, xml. By default json'''
    if code < 0:
        return error_out(data, -code)
    
    if request.headers.get('Accept') is not None and 'application/yaml' in request.headers.get('Accept'):
        content_type='application/yaml'
        return content_type, yaml.safe_dump(data, explicit_start=True, indent=4, default_flow_style=False, tags=False, encoding='utf-8', allow_unicode=True) #, canonical=True, default_style='"'
    else: #by default json
        content_type='application/json'
        return content_type, json.dumps(data, indent=4) + "\n"

# 추가 Bong : Work Flow Response Format
def format_out_wf(request, data, code=200):
    '''return string of dictionary data according to requested json, yaml, xml. By default json'''
    if code < 0:
        return error_out_wf(data, -code)

    if request.headers.get('Accept') is not None and 'application/yaml' in request.headers.get('Accept'):
        content_type = 'application/yaml'
        return content_type, yaml.safe_dump(data, explicit_start=True, indent=4, default_flow_style=False, tags=False, encoding='utf-8',
                                            allow_unicode=True)  # , canonical=True, default_style='"'
    else:  # by default json
        content_type = 'application/json'
        return content_type, json.dumps(data, indent=4) + "\n"


def error_out(msg, code):
    error_dict = {}
    error_dict['error']={'code':code, 'type':str(code), 'description':msg}
    
    content_type='application/json'
    return content_type, json.dumps(error_dict, indent=4) + "\n"

# Add 2019.02.16 Bong : Work Flow Response Format
def error_out_wf(msg, code):
    error_dict = {}
    error_dict['error'] = {'result': "FAIL", 'error_code': str(code), 'error_desc': msg}

    content_type = 'application/json'
    return content_type, json.dumps(error_dict, indent=4) + "\n"


def format_in(request, schema, is_report=True):
    try:
        format_type = request.headers.get('Content-Type', 'application/json')
        if 'application/json' in format_type:
            client_data = json.loads(request.body)
        elif 'application/yaml' in format_type:
            client_data = yaml.load(request.body)
        elif 'application/xml' in format_type:
            return -501, "Content-Type: application/xml not supported yet."
        else:
            return -HTTPResponse.Not_Acceptable, 'Content-Type ' + str(format_type) + ' not supported.'
        if is_report:
            api_call_report(request, client_data)

        js_v(client_data, schema)

        return 200, client_data
    except Exception, e:
        log.error("[HJC] format_in: Exception %s" %str(e))
        return -HTTPResponse.Internal_Server_Error, str(e)

def api_call_report(request, body):
    log_info_message = "API Call Info"
    log.info(log_info_message.center(80, '='))

    log.info("  - REQUEST URL: %s\n" %str(request.uri))
    log.info("  - REQUEST METHOD: %s\n" %str(request.method))
    log.info("  - BODY: %s" %str(request.body))

    log.info(log_info_message.center(80, '='))

def delete_nulls(var):
    if type(var) is dict:
        for k in var.keys():
            if var[k] is None: del var[k]
            elif type(var[k]) is dict or type(var[k]) is list or type(var[k]) is tuple: 
                if delete_nulls(var[k]): del var[k]
        if len(var) == 0: return True
    elif type(var) is list or type(var) is tuple:
        for k in var:
            if type(k) is dict: delete_nulls(k)
        if len(var) == 0: return True
    return False

def change_keys_http2db(data, http_db, reverse=False):
    pass

def filter_query_string(qs, http2db, allowed):
    pass


def _remove_passwd(data, key=None):

    if (type(data) == str or type(data) == unicode) and key is not None:
        if key == "vm_access_passwd":
            return 1
        elif key == "password":
            return 1

    elif type(data) == dict or type(data) == psycopg2.extras.RealDictRow:
        for key, value in data.items():
            result = _remove_passwd(value, key=key)
            if result == 1:
                del data[key]
    elif type(data) == list:
        for item in data:
            _remove_passwd(item)

    return 0

def secure_passwd(data):

    _remove_passwd(data)

    return data