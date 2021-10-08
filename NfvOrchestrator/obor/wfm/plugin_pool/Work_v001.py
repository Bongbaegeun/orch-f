# coding=utf-8

from yapsy.IPlugin import IPlugin

from wfm.plugin_spec.WorkSpec import WorkSpec
import gc

import base64
import requests
import json
import sys
import sched
import time
import os
import commands
import copy


from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import db.dba_manager as orch_dbm

from scp import SCPClient

from httplib import HTTPException
from requests.exceptions import ConnectionError
from db.orch_db import HTTP_Unauthorized, HTTP_Bad_Request, HTTP_Internal_Server_Error, HTTP_Not_Found, HTTP_Service_Unavailable, HTTP_Conflict

import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

class Work(WorkSpec):

    def job_test(self, req_info=None):
        log.debug("In job_test")

        import gc

        # request test : ip check
        # log.debug('req_info = %s' % str(req_info.headers.get('X-Forwarded-For')))

        req_info = {'onebox_type': 'Common'}
        orch_comm = common_manager.common_manager(req_info)

        log.debug('1. orch_comm = %s' %str(orch_comm))

        orch_comm = None
        gc.collect()

        log.debug('2. orch_comm = %s' % str(orch_comm))



        return 200, "OK"

        server_info = req_info
        server_dict = {}
        network_list = []

        wan_list = []
        office_list = []
        server_list = []
        other_list = []
        bridge_list = []

        server_dict['mgmtip'] = None

        if 'nic' in server_info:
            public_nic = None
            zone = None

            tmp_etc = {}
            tmp_bridge = []

            # 우선순위 결정을 위해 bridge 와 ethernet 을 분리한다
            # public 정보는 이 부분에서 처리
            for nic in server_info['nic']:
                if 'bridge' in nic.get('iface_name'):
                    tmp_bridge.append(nic)
                else:
                    # public 정보 처리
                    server_dict['ipalloc_mode_public'] = nic.get('ip_type')
                    server_info_ip = nic['ip_addr'].split('/')  # xxx.xxx.xxx.xxx/24

                    if len(server_info_ip) < 2:
                        p_ip = nic['ip_addr']
                        p_cidr = None
                    else:
                        p_ip = server_info_ip[0]
                        p_cidr = server_info_ip[1]

                    if nic.get('zone') == "uplink_main":
                        # public
                        if nic['mgmt_boolean'] is True:  # mgmt_boolean 이 True 가 아닌 경우가 있다.
                            server_dict['publicip'] = p_ip

                            if p_cidr:
                                server_dict['publiccidr'] = p_cidr

                            server_dict['mgmtip'] = p_ip
                            server_dict['publicgwip'] = nic['gw_ip_addr']
                            server_dict['public_nic'] = nic['iface_name']
                            server_dict['mgmt_nic'] = nic['iface_name']
                            server_dict['publicmac'] = nic['mac_addr']

                        public_nic = nic['iface_name']

                        zone = "wan"
                        wan_list.append(self._parseList(nic))
                        network_list.append({'name': nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(nic)})
                    else:
                        # etc 는 추가 검증을 위해 뽑아쓰기 편하도록 key-value 형태로 저장
                        tmp_etc[nic.get('iface_name')] = nic

            log.debug('tmp_bridge = %s' % str(tmp_bridge))
            log.debug('wan_list = %s' % str(wan_list))
            log.debug('network_list = %s' % str(network_list))
            log.debug('tmp_etc = %s' % str(tmp_etc))
            log.debug('1 ===========================================================================================================')

            # wan을 제외한 port들은 bridge sequrity zone 우선
            for bridge in tmp_bridge:
                # log.debug('tmp_bridge loop : bridge = %s' %str(bridge))

                if bridge.get('zone') == "uplink_main":
                    # 물리 nic 정보에 mgmt 가 없었으므로 bridge:uplink_main 에 있는 정보로 대체
                    if server_dict['mgmtip'] is None or len(server_dict['mgmtip']) <= 0:
                        # public 정보 처리
                        server_dict['ipalloc_mode_public'] = bridge.get('ip_type')
                        server_info_ip = bridge['ip_addr'].split('/')  # xxx.xxx.xxx.xxx/24

                        if len(server_info_ip) < 2:
                            p_ip = bridge['ip_addr']
                            p_cidr = None
                        else:
                            p_ip = server_info_ip[0]
                            p_cidr = server_info_ip[1]

                        server_dict['publicip'] = p_ip

                        if p_cidr:
                            server_dict['publiccidr'] = p_cidr

                        server_dict['mgmtip'] = p_ip
                        server_dict['publicgwip'] = bridge['gw_ip_addr']
                        # server_dict['publicmac'] = bridge['mac_addr']

                        # 아래 두 정보는 물리 nic 정보가 이미 들어있으므로 세팅하지 않는다
                        # server_dict['public_nic'] = bridge['iface_name']
                        # server_dict['mgmt_nic'] = bridge['iface_name']

                    # ethernet zone 설정은 없지만
                    # bridge : uplink_main 이 있는지 체크 -> 있으면 wan_list 에 포함
                    # mac addr 넣기 위한 처리 변수
                    is_mac_insert = False

                    for bridge_port in bridge.get('port'):
                        # log.debug('bridge : uplink_main : port = %s' %str(bridge_port))

                        # 이미 물리 nic 정보에서 빠진 port 이므로 pass
                        if bridge_port not in tmp_etc:
                            continue

                        # wan 중에서 하나만 public mac addr 로 설정
                        tmp_info = tmp_etc.get(bridge_port)
                        if tmp_info:
                            if is_mac_insert is False:
                                server_dict['publicmac'] = tmp_etc.get(bridge_port).get('mac_addr')
                                is_mac_insert = True

                        wan_list.append(self._parseList(tmp_etc.get(bridge_port)))
                        zone = "wan"

                        etc_nic = tmp_etc.get(bridge_port)
                        network_list.append({'name': etc_nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(etc_nic)})

                        # tmp_etc에 사용안한 nic 만 남긴다
                        tmp_etc.pop(bridge_port)

                    for tmp_wan in wan_list:
                        tmp_wan['public_ip'] = 'Bridge 사용 중'
                else:
                    for bridge_port in bridge.get('port'):
                        # log.debug('bridge : %s : bridge_port = %s' % (str(bridge.get('zone')), str(bridge_port)))
                        if bridge.get('zone') == "lan_office":
                            office_list.append(self._parseList(tmp_etc.get(bridge_port)))
                            zone = "office"
                        elif bridge.get('zone') == "lan_server":
                            server_list.append(self._parseList(tmp_etc.get(bridge_port)))
                            zone = "server"
                        else:
                            other_list.append(self._parseList(tmp_etc.get(bridge_port)))
                            zone = "other"

                        etc_nic = tmp_etc.get(bridge_port)
                        network_list.append({'name': etc_nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(etc_nic)})

                        # tmp_etc에 사용안한 nic 만 남긴다
                        tmp_etc.pop(bridge_port)

            log.debug('wan_list = %s' % str(wan_list))
            log.debug('network_list = %s' % str(network_list))
            log.debug('tmp_etc = %s' % str(tmp_etc))
            log.debug('2 ===========================================================================================================')

            # 남은 tmp_etc list 를 각 zone 에 추가
            # ethernet zone은 설정되어 있지만, bridge에 포함되지 않았을 경우 -> ethernet zone 설정으로 각 zone에 포함시켜준다.
            for ek, ev in tmp_etc.items():
                ps_nic = self._parseList(ev)
                # log.debug('key = %s, value = %s' % (str(ek), str(ev)))

                if ev.get('zone') is None or len(ev.get('zone')) <= 0:
                    log.debug('%s, not found zone value....' % str(ek))
                    continue

                if ev.get('zone'):
                    if ev.get('zone') == "lan_office":
                        office_list.append(ps_nic)
                        etc_zone = "office"
                    elif ev.get('zone') == "lan_server":
                        server_list.append(ps_nic)
                        etc_zone = "server"
                    else:
                        other_list.append(ps_nic)
                        etc_zone = "other"

                    network_list.append({'name': ev['iface_name'], 'display_name': etc_zone, 'metadata': json.dumps(ps_nic)})

            server_dict["wan_list"] = wan_list

            if office_list:
                server_dict["office_list"] = office_list
            if server_list:
                server_dict["server_list"] = server_list
            if other_list:
                server_dict["other_list"] = other_list

            r_num = 0
            for wan in wan_list:
                if wan["nic"] == public_nic:
                    wan["status"] = "A"
                else:
                    wan["status"] = "S"

                # wan_list 순서대로 R0~N 주는 방식으로 변경처리.
                wan["name"] = "R" + str(r_num)
                r_num += 1

            log.debug('==================   Change  ============================================')
            log.debug('wan_list = %s' % str(wan_list))
            log.debug('office_list = %s' % str(office_list))
            log.debug('server_list = %s' % str(server_list))
            log.debug('other_list = %s' % str(other_list))
            log.debug('server_dict = %s' % str(server_dict))

            # for nic in server_info['nic']:
            #     server_dict['ipalloc_mode_public'] = nic.get('ip_type')
            #     server_info_ip = nic['ip_addr'].split('/')  # xxx.xxx.xxx.xxx/24
            #
            #     if len(server_info_ip) < 2:
            #         p_ip = nic['ip_addr']
            #         p_cidr = None
            #     else:
            #         p_ip = server_info_ip[0]
            #         p_cidr = server_info_ip[1]
            #
            #     # public
            #     if nic['mgmt_boolean'] is True:
            #         server_dict['publicip'] = p_ip
            #
            #         if p_cidr:
            #             server_dict['publiccidr'] = p_cidr
            #
            #         server_dict['mgmtip'] = p_ip
            #         server_dict['publicgwip'] = nic['gw_ip_addr']
            #         server_dict['public_nic'] = nic['iface_name']
            #         server_dict['mgmt_nic'] = nic['iface_name']
            #         server_dict['publicmac'] = nic['mac_addr']
            #
            #         public_nic = nic['iface_name']
            #
            #     port = {"public_ip": p_ip, "public_cidr_prefix": p_cidr, "ipalloc_mode_public": nic.get('ip_type')}
            #     port["public_gw_ip"] = nic['gw_ip_addr']
            #     port["mac"] = nic['mac_addr']
            #     port["mode"] = nic['zone']  # ???
            #     port["nic"] = nic['iface_name']
            #     port["mgmt_boolean"] = nic['mgmt_boolean']
            #
            #     if nic["zone"] == "lan_office":
            #         office_list.append(port)
            #         zone = "office"
            #     elif nic["zone"] == "lan_server":
            #         server_list.append(port)
            #         zone = "server"
            #     elif nic['zone'] == "uplink_main":
            #         # if nic.get('gw_ip_addr') is None or len(nic.get('gw_ip_addr')) <= 0:
            #         #     continue
            #
            #         wan_list.append(port)
            #         zone = "wan"
            #     else:
            #         # etc
            #         other_list.append(port)
            #         zone = "other"
            #
            #     network_list.append({'name': nic['iface_name'], 'display_name': zone, 'metadata': json.dumps(nic)})
            #
            #
            # server_dict["wan_list"] = wan_list
            #
            # if office_list:
            #     server_dict["office_list"] = office_list
            # if server_list:
            #     server_dict["server_list"] = server_list
            # if other_list:
            #     server_dict["other_list"] = other_list

        return 200, "OK"

    def _proc(self):
        log.debug("It's _proc()")
        pass


    def _parseList(self, nic):
        rtn = {}

        server_info_ip = nic['ip_addr'].split('/')  # xxx.xxx.xxx.xxx/24

        if len(server_info_ip) < 2:
            p_ip = nic['ip_addr']
            p_cidr = None
        else:
            p_ip = server_info_ip[0]
            p_cidr = server_info_ip[1]

        port = {"public_ip": p_ip, "public_cidr_prefix": p_cidr, "ipalloc_mode_public": nic.get('ip_type')}
        port["public_gw_ip"] = nic['gw_ip_addr']
        port["mac"] = nic['mac_addr']
        port["mode"] = nic['zone']  # ???
        port["nic"] = nic['iface_name']
        port["mgmt_boolean"] = nic['mgmt_boolean']

        return port


    def base64_reqeust(self):
        log.debug("In base64_reqeust")
        # /var/onebox/backup/AXPNF.OB1/OneBox/190305-1536
        local_path = "/var/onebox/backup/AXPNF.OB1/OneBox/190305-1536/"
        # remote_path = "/var/onebox/backup/AXPNF.OB1/OneBox/test2"

        filename = local_path + "backup-190228-1536.tar.gz"

        with open(filename, "rb") as f:
            bytes = f.read()
            encoded = base64.b64encode(bytes)

        headers_req = {'Accept': 'application/json', 'content-type': 'application/json'}
        URLrequest = "https://211.224.204.203:9090/orch/server/work/base64_response"

        log.debug("Backup request URL: %s" % URLrequest)

        reqDict = {'backup_file': encoded}
        reqDict['remote_location'] = "/mnt/flash/data/onebox/onebox-agent/tmp/backup/190228-1536/backup-190228-1536.tar.gz"
        reqDict['local_location'] = "/var/onebox/backup/AXPNF.OB1/OneBox/190228-1536/backup-190228-1536.tar.gz"
        payload_req = json.dumps(reqDict)

        log.debug("Backup request body = %s" % str(payload_req))

        try:
            # ob_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False, timeout=120, cert=(CLIENT_ORCH_CRT, CLIENT_ORCH_KEY))
            ob_response = requests.post(URLrequest, headers=headers_req, data=payload_req, verify=False, timeout=120)
        except (HTTPException, ConnectionError), e:
            log.exception("failed to backup One-Box due to HTTP Error %s" % str(e))
            return -500, str(e)
        except Exception, e:
            log.error("Failed to backup One-Box : %s" % str(e))
            return -500, str(e)

        return self._parse_json_response(ob_response)


    def base64_response(self, req_info=None):
        log.debug("In base64_response")

        onebox_id = "AXPNF.OB1"
        local_location = req_info.get('local_location').split('/')
        filename = local_location[-1]
        local_path = req_info.get('local_location').replace('/' + filename, '')

        try:
            if not os.path.isdir(local_path):
                os.makedirs(os.path.join(local_path))
        except OSError as e:
            log.debug('Failed to create directory : %s' %str(local_path))
            raise

        # base64 decode
        rev_data = base64.b64decode(req_info['backup_file'])

        # save file
        e = open(local_path + '/' + filename, 'wb')
        e.write(rev_data)
        e.close()

        # 파일 전송
        # ssh_cmd = "scp %s root@211.224.204.156:%s" %(str(save_path), str(req_info.get('backup_location')))
        user = "root"
        host = "211.224.204.156"

        ssh_cmd = "scp -rp %s %s@%s:%s" %(str(local_path), str(user), str(host), str(local_path))
        log.debug('ssh_cmd = %s' %str(ssh_cmd))

        commands.getoutput(ssh_cmd)

        return 200, "OK"


    def work_monitor(self, kind, server, plugins=None):
        # Common load
        # req_info = {'onebox_type': "Common"}
        # orch_comm = common_manager.common_manager(req_info)
        orch_comm = plugins.get('orch_comm')

        ob_result, ob_content = orch_dbm.get_server_id(server)

        log.debug('[Reboot] ob_result = %d, ob_content = %s' % (ob_result, str(ob_content)))

        if ob_result <= 0:
            log.error("get_server_id Error %d %s" % (ob_result, ob_content))
            raise Exception(ob_result, ob_content)

        comm_dict = {}
        comm_dict['ob_data'] = ob_content
        comm_dict['e2e_log'] = None

        if kind == "resume":
            monitor_result, monitor_data = orch_comm.getFunc('resume_onebox_monitor', comm_dict)

            if monitor_result < 0:
                log.warning("Failed to start monitor: %d %s" % (monitor_result, monitor_data))

        elif kind == "suspend":
            # 모니터 일시 정지
            som_result, som_data = orch_comm.getFunc('suspend_onebox_monitor', comm_dict)

            if som_result < 0:
                log.warning("Failed to stop One-Box monitor. False Alarms are expected")

        comm_dict.clear()


        return 200, "OK"


    # vnf init_config script parsing & bond setting
    def work_bond(self, req_info=None):

        sc_tmp = self._set_bonding_script(req_info)

        log.debug('script = %s' %str(sc_tmp))

        return 200, "OK"

    def _set_bonding_script(self, req_info):
        tmp_scripts_uplink = []
        tmp_scripts_route = []

        origin_scripts = copy.deepcopy(req_info.get('scripts'))

        for sc in origin_scripts:
            if sc.get('name').find('uplink') > 0:
                tmp_scripts_uplink.append(sc)
            elif sc.get('name').find('route') > 0:
                tmp_scripts_route.append(sc)
            else:
                continue

        # 1. 라우팅 정보 제거 스크립트 추가
        cp_tmp_scripts_route = copy.deepcopy(tmp_scripts_route)
        cp_tmp_scripts_uplink = copy.deepcopy(tmp_scripts_uplink)

        for rsc in tmp_scripts_route:
            rsc['body'] = rsc['body'].replace('ip route', 'no ip route')

        # 2. interface 정보 제거 스크립트 추가
        default_route_list = []
        for usc in tmp_scripts_uplink:
            tmp_interface_name = None
            default_gw = usc.get('body_args')[2]
            tmp_body_int = usc.get('body').split('\\n')

            for b in tmp_body_int:
                if b.find('interface') < 0:
                    continue

                tmp_b = b.split(' ')
                tmp_interface_name = tmp_b[1]
                break

            drl_dict = {}
            drl_dict['interface'] = tmp_interface_name
            drl_dict['default_gw'] = default_gw

            if len(default_route_list) > 0:
                for dr_list in default_route_list:
                    if dr_list.get('default_gw') == default_gw:
                        continue

                    default_route_list.append(drl_dict)
            else:
                default_route_list.append(drl_dict)

            usc['body'] = usc['body'].replace('ip address', 'no ip address')
            usc['body'] = usc['body'].replace('ip gateway', 'no ip gateway')
            usc['body'] = usc['body'].replace('link-check', 'no link-check')
            # usc['body'] = usc['body'].replace('no shutdown', 'no security-zone\\nshutdown')
            usc['body'] = usc['body'].replace('no shutdown', 'no security-zone\\nno shutdown')

        # 1-1. 디폴트 라우팅 스크립트 추가
        default_route_list_append = []
        for drl in default_route_list:
            for cptsr in cp_tmp_scripts_route:
                cptsr_body = cptsr.get('body').split('\\n')
                cptsr_body_route = cptsr_body[1].split(' ')

                if cptsr_body_route[3] != drl.get('interface'):
                    continue

                tmp_cptsr_route = cptsr_body_route[0] + ' ' + cptsr_body_route[1] + ' ' + cptsr_body_route[2] + ' ' + drl.get('default_gw')
                cptsr['body'] = cptsr_body[0] + '\\n' + tmp_cptsr_route + '\\n' + cptsr_body[2]
                default_route_list_append.append(cptsr)
                break

        # 3. bonding 스크립트 추가
        sc_tmp = {}
        body = "cmd=configure terminal\\ninterface bond0\\nbonding mode active-backup primary-reselect always arp-validate all\\n" \
               "bonding link-check miimon 1\\n"
        primary_interface = None
        ip_addr = None

        cp_scripts = copy.deepcopy(req_info.get('scripts'))

        for sc in cp_tmp_scripts_uplink:
            interface_name = None
            tmp_body = sc.get('body').split('\\n')

            for b in tmp_body:
                if b.find('interface') < 0:
                    continue

                tmp_b = b.split(' ')
                interface_name = tmp_b[1]
                break

            body += "bonding slave %s\\n" % str(interface_name)

            if sc.get('name') == 'set_nic_uplink_static':
                sc_tmp = sc
                primary_interface = interface_name
                ip_addr = sc.get('body_args')[0] + '/' + sc.get('body_args')[1]

            if sc.get('name') == 'set_nic_uplinkR1_static':
                body += "bonding primary %s\\n" % str(primary_interface)
                body += "ip address %s\\n" % str(ip_addr)
                body += "ip address %s secondary\\n" % str(sc.get('body_args')[0] + '/' + sc.get('body_args')[1])

        body += "security-zone uplink_main\\nno shutdown\\nend"

        # log.debug('body = %s' % str(body))

        sc_tmp['body'] = body
        sc_tmp['body_args'] = []

        # log.debug('sc_tmp = %s' %str(sc_tmp))

        return_scripts = []

        for scripts in req_info.get('scripts'):
            # write_config 가 아닐때 기본 scripts 우선 append
            if scripts.get('name') != 'write_config':
                return_scripts.append(scripts)
                continue

            # default route 정보 제거 scripts append
            for tsr in tmp_scripts_route:
                return_scripts.append(tsr)

            # default interface 정보 제거 scripts append
            for tsu in tmp_scripts_uplink:
                return_scripts.append(tsu)

            # default route gateway 정보 scripts append : 이게 있어야 통신이 된다
            for drla in default_route_list_append:
                return_scripts.append(drla)

            # bonding 구성 scripts append
            return_scripts.append(sc_tmp)

            # 마지막으로 write_config 넣어준다
            return_scripts.append(scripts)

        # log.debug('return_scripts = %s' % str(return_scripts))

        return return_scripts


    def _parse_json_response(self, ob_response):
        try:
            log.debug("Response from One-Box Agent = %s" % str(ob_response.text))
            log.debug("Response HTTP Code from One-Box Agent = %s" % str(ob_response.status_code))
            # if ob_response.status_code == 200:
            content = ob_response.json()
        except Exception, e:
            log.exception("Exception: [%s] %s" % (str(e), sys.exc_info()))
            return -HTTP_Internal_Server_Error, 'Invalid Response Body'

        if ob_response.status_code == 200:
            result = 200
        else:
            result = -ob_response.status_code
            # return result, content['error']['description']
            return result, content['error_desc']

        return result, content
