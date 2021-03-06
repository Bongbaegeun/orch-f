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
JSON schemas used by openmano httpserver.py module to parse the different files and messages sent through the API 
'''
__author__="Jechan Han"
__date__ ="$30-oct-2015 09:09:48$"


#hjc, for KT One-Box Service [START]

#Basis schemas
nameshort_schema={"type" : "string", "minLength":1, "maxLength":24, "pattern" : "^[^,;()'\"]+$"}
name_schema={"type" : ["string","null"], "minLength":1, "maxLength":50, "pattern" : "^[^,;'\"]+$"}
xml_text_schema={"type" : "string", "minLength":1, "maxLength":1000, "pattern" : "^[^']+$"}
description_schema={"type" : ["string","null"], "maxLength":500, "pattern" : "^[^'\"]+$"}
id_schema_fake = {"type" : "string", "minLength":2, "maxLength":36 }  #"pattern": "^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
id_schema = {"type" : "string", "pattern": "^[a-fA-F0-9]{8}(-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$"}
pci_schema={"type":"string", "pattern":"^[0-9a-fA-F]{4}(:[0-9a-fA-F]{2}){2}\.[0-9a-fA-F]$"}
http_schema={"type":"string", "pattern":"^https?://[^'\"=]+$"}
bandwidth_schema={"type":"string", "pattern" : "^[0-9]+ *([MG]bps)?$"}
memory_schema={"type":"string", "pattern" : "^[0-9]+ *([MG]i?[Bb])?$"}
integer0_schema={"type":"integer","minimum":0}
integer1_schema={"type":"integer","minimum":1}
path_schema={"type":"string", "pattern":"^(\.(\.?))?(/[^/"":{}\ \(\)]+)+$"}
vlan_schema={"type":"integer","minimum":1,"maximum":4095}
vlan1000_schema={"type":"integer","minimum":1000,"maximum":4095}
mac_schema={"type":"string", "pattern":"^[0-9a-fA-F][02468aceACE](:[0-9a-fA-F]{2}){5}$"}  #must be unicast LSB bit of MSB byte ==0 
#mac_schema={"type":"string", "pattern":"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$"}
ip_schema={"type":"string","pattern":"^([0-9]{1,3}.){3}[0-9]{1,3}$"}
port_schema={"type":"integer","minimum":1,"maximum":65534}

metadata_schema={
    "type":"object",
    "properties":{
        "architecture": {"type":"string"},
        "use_incremental": {"type":"string","enum":["yes","no"]},
        "vpci": pci_schema,
        "os_distro": {"type":"string"},
        "os_type": {"type":"string"},
        "os_version": {"type":"string"},
        "bus": {"type":"string"}
    }
}

#Schema for the configuration file
config_schema = {
    "title":"configuration response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "http_port": port_schema,
        "http_admin_port": port_schema,
        "http_host": name_schema,
        "http_ssl": {"type":"boolean"},
        "http_proc_num": {"type":"integer"},
        "vnf_repository": path_schema,
        "db_host": name_schema,
        "db_port": integer0_schema,
        "db_user": name_schema,
        "db_passwd": {"type":"string"},
        "db_name": name_schema,
        # Next fields will disappear once the MANO API includes appropriate primitives
        "vim_url": http_schema,
        "vim_url_admin": http_schema,
        "vim_name": nameshort_schema,
        "vim_tenant_name": nameshort_schema,
        "mano_tenant_name": nameshort_schema,
        "mano_tenant_id": id_schema,
        "backup_repository": {"type":"string"},
        "backup_server":{"type":"string"},
        "backup_server_local":{"type":"string"},
        "passwd_salt":{"type":"string"},
        "monitor_ip":{"type":"string"},
        "monitor_port": {"type":"string"},
        "e2emgr_url":{"type":"string"},
        "e2emgr_debug":{"type":"boolean"},
        "odm_url": {"type":"string"},
        "xms_url": {"type":"string"},
        "xms_admin_id": {"type":"string"},
        "xms_admin_pw": {"type":"string"},
        "xms_domain":{"type":"string"},
        "license_mngt":{"type":"boolean"},
        "license_code": {"type":"string"},
        "image_mount_path": {"type":"string"},
        "image_real_path": {"type":"string"},
        "mysql_host": name_schema,
        "mysql_port": integer0_schema,
        "mysql_user": name_schema,
        "mysql_pw": {"type":"string"},
        "mysql_db_name": name_schema,
        "sms_id": {"type":"string"},
        "sms_callback": {"type":"string"},
        "sms_report_chk": {"type":"integer"}
    },
    "required": ['db_host', 'db_user', 'db_passwd', 'db_name'],
    "additionalProperties": False
}

#
# public NBI
#

user_schema = {
    "title":"user information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "user":{
            "type":"object",
            "properties":{
                "userid": {"type":"string"},
                "username": name_schema,
                "description": description_schema,
                "password": {"type":"string"},
                "userauth": {"type":"integer"},
                "orgnamescode": {"type":"string"},
                "customerseq": {"type":"integer"},
                "role_id": name_schema,
                "failcount": {"type":"integer"},
                "failtime": {"type":"string"}
            },
            "required": ["userid", "username"],
            "additionalProperties": False
        }
    },
    "required": ["user"],
    "additionalProperties": False     
}

customer_schema = {
    "title":"customer information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "customer":{
            "type":"object",
            "properties":{
                "order_id": {"type":"string"},
                "customername": name_schema,
                "description": description_schema,
                "tenantid": name_schema,
                "emp_cnt": integer1_schema,
                "addrseq": {"type":"integer"},
                "detailaddr": {"type":"string"},
                "email":{"type":"string"},
                "hp_num": {"type":"string"},
                "keymanname": {"type":"string"},
                "keymantelnum": {"type":"string"},
                "said":{"type":"string"}
            },
            "required": ["customername"],
            "additionalProperties": True
        }
    },
    "required": ["customer"],
    "additionalProperties": False
}

swrepo_sw_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "type":{"type": "string"},
        "version":{"type":"string"},
        "metadata":{"type":"string"}
    },
    "required": ["name", "type","version"],
    "additionalProperties": False
}

onebox_flavor_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "hw_model":{"type": ["string","null"]},
        "metadata":{"type":"string"},
        "nfsubcategory":{"type":"string"}       #   ????????? ????????? ????????? ????????? ?????????
    },
    "required": ["name", "hw_model"],
    "additionalProperties": False
}

server_hardware_schema = {
    "type":"object",
    "properties":{
        "model": {"type":["string","null"]},
        "cpu": {"type":"string"},
        "num_cpus":{"type":"integer"},
        "num_cores_per_cpu":{"type":"integer"},
        "num_logical_cores":{"type":"integer"},
        "mem_size":{"type":"integer"}
    },
    "required":["model"],
    "additionalProperties": True
}

server_software_schema = {
    "type":"object",
    "properties":{
        "operating_system": {"type":["string","null"]}
    },
    "required":["operating_system"],
    "additionalProperties": True
}

server_network_schema = {
    "type":"object",
    "properties":{
        "name": {"type":["string","null"]},
        "display_name": {"type":["string","null"]},
        "metadata": {"type":"string"}
    },
    "required":["name", "display_name"],
    "additionalProperties": True
}

server_vim_schema = {
    "type":"object",
    "properties":{
        "vim_type": {"type":"string"},
        "vim_authurl": {"type":"string"},
        "vim_tenant_name": {"type":"string"},
        "vim_tenant_username": {"type":"string"},
        "vim_tenant_passwd": {"type":"string"},
        "vim_tenant_domain": {"type":"string"}
    },
    #"required":["vim_tenant_name"],
    "additionalProperties": True
}

server_vnfm_schema = {
    "type":"object",
    "properties":{
        "base_url": {"type":["string","null"]},
        "version": {"type":"string"}
    },
    "required":["base_url"],
    "additionalProperties": True
}

server_obagent_schema = {
    "type":"object",
    "properties":{
        "base_url": {"type":["string","null"]},
        "version": {"type":"string"}
    },
    "required":["base_url"],
    "additionalProperties": True
}

server_wan_schema = {
    "type":"object",
    "properties":{
        "nic": {"type":["string","null"]},
        "mode": {"type":["string","null"]},
        "mac": {"type":["string","null"]}
    },
    "required":["nic","mac"],
    "additionalProperties":True
}

server_lan_schema = {
    "type":"object",
    "properties":{
        "nic": {"type":["string","null"]},
        "mac": {"type":["string","null"]}
    },
    "required":["nic"],
    "additionalProperties":True
}

server_vnet_schema = {
    "type":"object",
    "properties":{
        "name": {"type":["string","null"]},
        "ip": {"type":["string","null"]},
        "subnet": {"type":["string", "null"]},
        "cidr_prefix": {"type":"integer"},
        "metadata": {"type":"string"}
    },
    "required":["name", "ip"],
    "additionalProperties": True
}

wan_list_schema={
    "type":"object",
    "properties":{
        "public_ip": {"type":["string", "null"]},
        "public_cidr_prefix": {"type":"integer"},
        "public_gw_ip": {"type":["string", "null"]},
        "public_ip_dhcp": {"type":"boolean"},
        "mac": {"type":["string","null"]},
        "mode": {"type":["string","null"]},
        "nic": {"type":["string","null"]},
        "physnet_name": {"type":["string","null"]}
    },
    "required":["mode", "nic", "mac", "public_ip_dhcp"],
    "additionalProperties": True
}

# HA cluster list schema
cluster_list_schema={
    "type":"object",
    "properties":{
        "serverseq": {"type":"string"},
        "onebox_id": {"type":"string"},
        "public_ip": {"type":"string"},
        "mode": {"type":"string"},
        "cluster_id": {"type":"string"},
        "vnet_ha_ip": {"type":"string"}
    },
    "additionalProperties": True
}

server_note_schema={
    "type":"object",
    "properties":{
        "noteCode": {"type":["string","null"]}
    },
    "required":["noteCode"],
    "additionalProperties": True
}

server_schema = {
    "title":"physical onebox server information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid": {"type":"string"},
        "tpath": {"type":"string"},
        "order_id": {"type":"string"},
        "servername": name_schema,
        "description": description_schema,
        "serveruuid": name_schema,
        "customerseq": integer1_schema,
        "customer_id": {"type":["string","null"]},
        "customer_name": name_schema,
        "mgmt_ip": {"type":["string","null"]},
        "public_ip": {"type":["string","null"]},
        "public_gw_ip": {"type":["string","null"]},
        "public_cidr_prefix": {"type":"integer"},
        "public_mac": {"type":["string","null"]},
        "public_ip_dhcp": {"type":"boolean"},
        "servercode": {"type":["string","null"]},
        "nfmaincategory": {"type":["string","null"]},
        "nfsubcategory": {"type":["string","null"]},
        "org_name": {"type":["string","null"]},
        "modify_dttm": {"type":["string","null"]},
        "stock_dttm": {"type":["string","null"]},
        "deliver_dttm": {"type":["string","null"]},
        "serial_no": {"type":["string","null"]},
        "onebox_flavor": {"type":["string","null"]},
        "vim": server_vim_schema,
        "vnfm": server_vnfm_schema,
        "obagent": server_obagent_schema,
        "software": server_software_schema,
        "hardware": server_hardware_schema,
        "network": {"type" : "array", "items": server_network_schema, "minItems":1},
        "wan": server_wan_schema,
        "lan_office1": server_lan_schema,
        "lan_office2": server_lan_schema,
        "lan_office": server_lan_schema,
        "lan_server": server_lan_schema,
        "lan_ha": server_lan_schema,
        "vnet": {"type":"array", "items":server_vnet_schema, "minItems":0},
        "mgmt_nic" : {"type":["string","null"]},
        "public_nic" : {"type":["string","null"]},
        "wan_list" : {"type":"array", "items":wan_list_schema, "minItems":0},
        "extra_wan_list" : {"type":"array", "items":wan_list_schema, "minItems":0},
        "note": {"type":"array", "items":server_note_schema, "minItems":0},
        "default_ns_id" : {"type":["string","null"]},
        "first_notify" : {"type": "boolean"}
    },
    "additionalProperties": False
}

server_associate_schema={
    "title":"server associate information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "server":{
            "type":"object",
            "properties":{
                "servername": name_schema,
                "mgmtip": {"type":"string"},
                "orgnamescode": name_schema,
                "customerseq": {"type":"integer"}
            },
            "required": ["customerseq", "mgmtip"],
            "additionalProperties": True
        }
    },
    "required": ["server"],
    "additionalProperties": False
}

vim_schema_properties={
    "name": name_schema,
    "description": description_schema,
    "vimtypecode": {"type":"string"},
    "authurl": description_schema,
    "authurladmin": description_schema,
    "serverseq": integer1_schema,
    "mgmtip": {"type":"string"},
    "pvimseq": integer1_schema
}

vim_schema = {
    "title":"VIM information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "vim":{
            "type":"object",
            "properties":vim_schema_properties,
            "required": ["name", "authurl", "serverseq"],
            "additionalProperties": True
        }
    },
    "required": ["vim"],
    "additionalProperties": False
}

vim_associate_schema={
    "title":"VIM associate information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "vim_tenant":{
            "type":"object",
            "properties":{
                "uuid": id_schema,
                "name": name_schema,
                "username": name_schema,
                "password": {"type":"string"},
            },
            "additionalProperties": True
        }
    },
    #"required": ["vim_tenant"],
    "additionalProperties": False
}

vim_action_schema = {
    "title":"vim action information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "net-update":{"type":"null",},
        "net-edit":{
            "type":"object",
            "properties":{
                "net": name_schema,  #name or uuid of net to change
                "name": name_schema,
                "description": description_schema,
                "shared": {"type": "boolean"}
            },
            "minProperties": 1,
            "additionalProperties": False
        },
        "net-delete":{
            "type":"object",
            "properties":{
                "net": name_schema,  #name or uuid of net to change
            },
            "required": ["net"],
            "additionalProperties": False
        },
        "net-create":{
            "type":"object",
            "properties": {
                "name": name_schema,
                "network_type": {"type":"string"},
                "physical_network": name_schema,
                "shared": {"type":"boolean"},
                "segmentation_id": vlan_schema,
                "cidr": {"type":"string"},
                "dhcp": {"type":"boolean"}
            }
        },
        "image-update":{"type":"null",},
        "image-delete":{
            "type":"object",
            "properties":{
                "image": name_schema
            },
            "required":["image"],
            "additionalProperties":False
        }
    },
    "minProperties": 1,
    "maxProperties": 1,
    "additionalProperties": False
}

so_customer_keyman_schema={
    "type":"object",
    "properties":{
        "name": name_schema,
        "telephone": {"type":"string"},
        "cellphone": {"type":"string"},
        "email": {"type":"string"},
        "dept": {"type":"string"},
        "accountid": {"type":"string"},
        "accountpasswd": {"type":"string"}
    },
    "required":["name"],
    "additionalProperties": True
}

so_ktmaster_schema={
    "type":"object",
    "properties":{
        "name": name_schema,
        "employeeid": {"type":"string"},
        "telephone": {"type":"string"},
        "cellphone": {"type":"string"},
        "email": {"type":"string"},
        "dept": {"type":"string"}
    },
    "required":["name", "employeeid"],
    "additionalProperties": True
}

so_customer_schema={
    "type":"object",
    "properties":{
        "id": {"type":"string"},
        "customer_name": name_schema,
        "customer_eng_name": name_schema,
        "telnum": {"type":"string"},
        "address": {"type":"string"},
        "keyman_info": so_customer_keyman_schema
    },
    "required":["customer_name", "customer_eng_name"],
    "additionalProperties": True
}

so_office_schema={
    "type":"object",
    "properties":{
        "office_name": name_schema,
        "address": {"type":"string"},
        "servername": {"type":"string"},
        "old_office_name": name_schema
    },
    "required":["office_name"],
    "additionalProperties": True
}

so_vnf_schema={
    "type":"object",
    "properties":{
        "vnf_name": name_schema,
        "vnfd_name": name_schema,
        "vnfd_version": {"type":"string"},
        "vnfd_display_name": {"type":"string"},
        "service_number": {"type":"string"},
        "service_period": {"type":"string"},
        "service_start_dttm": {"type":"string"},
        "service_end_dttm": {"type":"string"},
        "reg_dttm": {"type":"string"}#,
        # "vnf_account_id": {"type":"string"},
        # "vnf_account_pw": {"type":"string"},
        # "act_type":{"type":"string"}
    },
    "required":["vnfd_name", "vnfd_version"],
    "additionalProperties": True
}

so_onebox_schema={
    "type":"object",
    "properties":{
        "onebox_id": name_schema,
        "model": {"type":"string"},
        "net_line_list": {"type":"array","items":{"type":"string"},"minItems":0},
        "ob_service_number": {"type":"string"},
        "vnf_list": {"type":"array","items":so_vnf_schema,"minItems":0},
        "nfsubcategory": {"type":"string"},
    },
    "required":["onebox_id"],
    "additionalProperties": True
}

service_order_schema={
    "title":"service order information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "order_handle" : {"type":"string"},
        "order_type": {"type":"string"},
        "cooperation_office_name": {"type":"string"},
        "customer": so_customer_schema,
        "office": so_office_schema,
        "one-box": so_onebox_schema,
        "vnf_list": {"type":"array","items":so_vnf_schema,"minItems":0},
        "is_customer_delete": {"type":"boolean"}
    },
    "required":["one-box"],
    "additionalProperties": True
}

service_order_update_schema={
    "title":"service order information update schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "order_type": {"type":"string"},
        "cooperation_office_name": {"type":"string"},
        "customer": so_customer_schema,
        "office": {"type":"array","items":so_office_schema,"minItems":0},
        "one-box": so_onebox_schema,
        "vnf_list": {"type":"array","items":so_vnf_schema,"minItems":0}
    },
    "required":["customer"],
    "additionalProperties": True
}

hot_schema={"type":"string"}
#parameter_schema={"type":"string","pattern":"^[^\"]+$"}
parameter_schema={"type":"string"}

image_metadata_schema={
    "type":"object",
    "properties":{
        "container_format": {"type":"string"},
        "disk_format": {"type":"string"},
        "visibility": {"type":"string"},
        "hw_disk_bus": {"type":"string"},
        "hw_vif_model": {"type":"string"},
        "description": {"type":"string"}
    }
}

vnf_image_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "version":{"type": "integer"},
        "container_format":{"type":"string","enum":["ami","ari","aki","bare","ova", "ovf","any"]},
        "disk_format":{"type":"string","enum":["qcow2","ami","aki","vhd","vmdk","raw","iso","vdl"]},
        "is_public":{"type" : "boolean"},
        #"path":{"oneOf": [path_schema, http_schema]},
        "path":{"type":"string"},
        "metadata":image_metadata_schema
    },
    "required": ["disk_format"],
    "additionalProperties": False
}

vnf_license_key_schema = {"type" : "array", "items": name_schema, "minItems":1}

vnf_license_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "type":{"type": "string", "enum":["key","server","key_server"]},
        "value":vnf_license_key_schema, # only for type = key or key_server
        "server_url":http_schema # only for type = server or key_server
    },
    "required": ["name","type"],
    "additionalProperties": False
}

license_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "type":{"type": "string"},
        "values":{"type":"array","items":{"type":"string"},"minItems":1},
        "vnfd_id":{"type":"integer"},
        "vnfd_name":name_schema,
        "vnfd_version":{"type":"integer"},
        "vendor":name_schema
    },
    "required": ["name", "values"],
    "additionalProperties": False
}

license_action_schema = {
    "title":"License action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "check_license":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        }
    },
    "minProperties": 1,
    "maxProperties": 1,
    "additionalProperties": False
}

script_body_schema={"type":"string"}
script_output_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "type":{"type":"string"},
        "description":description_schema
    },
    "required": ["name", "type"],
    "additionalProperites": False
}

output_fault_reaction_schema = {
    "type": "object",
    "properties": {
        "name": name_schema,
        "builtin": {"type":"boolean"},
        "body": {"type":"string"} #TODO
    },
    "required": ["name"],
    "additionalProperties": True    
}

output_fault_schema = {
    "type": "object",
    "properties": {
        "name": name_schema,
        "level": name_schema, #TODO
        "condition": {"type":"string"}, #TODO
        "reaction":{"type":"array","items":output_fault_reaction_schema,"minItems":0}
    },
    "required": ["name"],
    "additionalProperties": False    
}

param_schema = {
    "type": "object",
    "properties": {
        "name": name_schema,
        "type": {"type": "string", "enum":["string","integer"]},
        "description": description_schema,
        "default_value":{"type":"string"}
    },
    "required": ["name"],
    "additionalProperties": False
}

config_script_schema = {
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "type": {"type": "string"},
        "builtin": {"type":"boolean"},
        "condition": {"type":"string"},
        "request_url": {"type":"string"},
        "request_headers": {"type":"string"},
        "request_headers_args": {"type":"array","items":name_schema,"minItems":0},
        "param_format": {"type":"string"},
        "param_order": {"type":"array","items":name_schema, "minItems":0},
        "cookie_format": {"type":"string"},
        "cookie_data": {"type":"array","items":{"type":"string"}, "minItems":0},
        "body": script_body_schema,
        "body_args": {"type":"array","items":name_schema,"minItems":0},
        "output":{"type":"array","items":name_schema,"minItems":0}
    },
    "required": ["name","type"],
    "additionalProperties": False    
}

monitor_script_schema = {
    "type": "object",
    "properties": {
        "name": name_schema,
        "description": description_schema,
        "type": {"type": "string"},
        "builtin":{"type":"boolean"},
        "param_order": {"type":"array","items":name_schema, "minItems":0},
        #"body": {"oneOf": [script_body_schema, path_schema]}
        "body": script_body_schema,
        "output_format":{"type":"string"},
        "output":{"type":"array","items":script_output_schema,"minItems":1}
    },
    "required": ["name","type","body"],
    "additionalProperties": True    
}


output_schema = {
    "type": "object",
    "properties": {
        "name": name_schema,
        "type": {"type": "string"},
        "fault_criteria":{"type":"array","items":output_fault_schema,"minItems":0}
    },
    "required": ["name","type"],
    "additionalProperties": False    
}

vnfd_vnfc_config_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "description":description_schema,
        "type":{"type":"string"},
        "method":{"type":"string"},
        "parameters":{"type": "array", "items":param_schema, "minItems":1},
        "scripts":{"type": "array", "items":config_script_schema, "minItems":1}
    },
    "required": ["name"],
    "additionalProperties": False
}

vnfd_vnfc_monitor_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "type":name_schema,
        "period":integer1_schema,
        "builtin":{"type":"boolean"},
        "parameters":{"type": "array", "items":param_schema, "minItems":1},
        "scripts":{"type": "array", "items":monitor_script_schema, "minItems":1},
        "outputs":{"type":"array", "items":output_schema, "minItems":1},
        "target_id": {"type":"integer"}
    },
    "required": ["name"],
    "additionalProperties": False                      
}

vnfd_vnfc_weburl_v04 = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "type":{"type":"string"},
        "protocol":{"type":"string"},
        "ip_addr":{"type":"string"},
        "port":{"type":"integer"},
        "resource":{"type":"string"}
    },
    "requried":["name"],
    "additionalProperties":False
}

vnfd_vnfc_account_v04 = {
    "type": "object",
    "properties": {
        "vm_id":name_schema,
        "vm_passwd":{"type":"string"}
    },
    "requried":["vm_id","vm_passwd"],
    "additionalProperties":False
}

vnfd_vnfc_schema_v04 = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "description":description_schema,
        "image":vnf_image_schema,
        "web_url":vnfd_vnfc_weburl_v04,
        "vm_account":vnfd_vnfc_account_v04,
        "config":{"type":"array","items":vnfd_vnfc_config_schema,"minItems":0},
        "monitor":{"type":"array","items":vnfd_vnfc_monitor_schema,"minItems":0}
    },
    "required": ["name"],
    "additionalProperties": True                      
}

vnfd_account_schema = {
    "type": "object",
    "properties": {
        "type": {"type":"string"},
        "parameters":{"type": "array", "items":param_schema, "minItems":1},
        "id":name_schema,
        "password":{"type":"string"}        
    },
    "required": ["type"],
    "additionalProperties": True                      
}

vnfd_report_schema = {
    "type": "object",
    "properties": {
        "name": {"type":"string"},
        "display_name": {"type":"string"},
        "data_provider": {"type":"string"}
    },
    "required": ["name"],
    "additionalProperties": True
}

vnfd_action_schema = {
    "type": "object",
    "properties": {
        "name": {"type":"string"},
        "display_name": {"type":"string"},
        "description": {"type":"string"},
        "api_resource": {"type":"string"},
        "api_body_format": {"type":"string"},
        "api_body_param": {"type":"array", "items":{"type":"string"}, "minItem":0}
    },
    "required": ["name"],
    "additionalProperties": True
}

vnfd_metadata_schema = {
    "type": "object",
    "properties": {
        "price": {"type":"integer"}
    },
    "additionalProperties": True
}

vnfd_schema = {
    "title":"vnfd information schema v0.4 for KT One-Box service",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "vnf":{
            "type":"object",
            "properties":{
                "name": name_schema,
                "display_name": name_schema,
                "description": description_schema,
                "version": {"type":"integer"},
                "resource_template_type": name_schema,
                #"resource_template": {"oneOf": [hot_schema,path_schema]},
                "resource_template":hot_schema,
                "class": {"type":"string"},
                "public": {"type" : "boolean"},
                "virtual": {"type" : "boolean"},
                "owners": {"type" : "array", "items": name_schema, "minItems":1},   # for KOB
                "license":vnf_license_schema,
                "web_url": {"type": "string"},
                'vendor': name_schema,
                'account': vnfd_account_schema,
                'report': {"type":"array", "items": vnfd_report_schema, "minItems":1},
                'action': {"type":"array", "items": vnfd_action_schema, "minItems":1},
                'meta_data': vnfd_metadata_schema,
                "VNFC":{"type":"array", "items": vnfd_vnfc_schema_v04, "minItems":1},
                "repo_filepath":{"type": "string"}
            },
            "required": ["name","resource_template_type"],
            "additionalProperties": True
        }
    },
    "required": ["vnf"],
    "additionalProperties": False
}

#vnfd_schema = {
#    "title":"vnfd information schema v0.2",
#    "$schema": "http://json-schema.org/draft-04/schema#",
#    #"oneOf": [vnfd_schema_v01, vnfd_schema_v02, vnfd_schema_v04] #hjc
#    "oneOf": [vnfd_schema_v04] #hjc
#}

connectionpoint_schema = {
    "type":"object",
    "properties": {
        "name":name_schema,
        "owner_type":{"type":"string"},
        "owner":name_schema
    },
    "required": ["name"],
    "additionalProperties": True                          
}

vld_schema = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "description":{"type":"string"},
        "connection_points": {"type":"array", "items":connectionpoint_schema},
        "connection_type": {"type": "string", "enum":["e-lan","e-line","e-tree"]},
        "vnet_type": {"type":"string"},
        "is_external": {"type":"boolean"},
        "vnet_name": name_schema,
        "network_type": {"type":"string"},
        "physical_network":name_schema,
        "segmentation_id":{"type":"integer"},
        "subnet_cidr": {"type":"string"},
        "subnet_dhcp": {"type":"boolean"},
        "subnet_ip_version": {"type":"integer"}
    },
    "required": ["name"],
    "additionalProperties": True 
}

nsd_vnfd_schema = {
    "type": "object",
    "properties": {
        "name": name_schema,
        "vnfd_name": name_schema,
        "vnfd_version": {"type":"integer"},
        "graph": {"type":"string"}
    },
    "addtionalProperties": True
}

nsd_cpd_schema = {
    "type": "object",
    "properties": {
        "name": {"type":"string"},
        "network": {"type":"string"},
        "physical_network": {"type":"string"}
    },
    "addtionalProperties": True
}

nscomponent_schema = {
    "type": "object",
    "properties": {
        "vnfds":{"type": "array", "items":nsd_vnfd_schema, "minItems":0},
        "vlds":{"type":"array","items":vld_schema},
        "cpds":{"type":"array", "items":nsd_cpd_schema}
    },
    # "required": ["vnfds"],
    "additionalProperties": True   
}

nsd_metadata_schema = {
    "type": "object",
    "properties": {
        "price": {"type":"integer"}
    },
    "additionalProperties": True
}

nsd_schema_v04 = {
    "title":"network scenario descriptor information schema v0.4 for KT One-Box Service",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "name":name_schema,
        "display_name":name_schema,
        "description": description_schema,
        "version":{"type":"integer"},
        "class":{"type":"string"},
        "public":{"type":"boolean"},
        "resource_template_type": name_schema, #hjc
        "resource_template": hot_schema, #hjc
        "nsd": nscomponent_schema,
        "metadata": nsd_metadata_schema,
        "xy_graph": {"type":"string"} # TBD
    },
    "required": ["name"],
    "additionalProperties": False
}

nsd_new_schema = {
    "title":"new scenario information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    #"oneOf": [nsd_schema_v01, nsd_schema_v02, nsd_schema_v04] #hjc
    "oneOf": [nsd_schema_v04] #hjc
}

nsd_ofvnfs_new_schema = {
    "type":"object",
    "properties":{
        "customer_eng_name": name_schema,
        "vnf_list": {"type":"array","items":so_vnf_schema,"minItems":1}
    },
    "required": ["vnf_list"],
    "additionalProperties": True
}

nsd_action_schema = {
    "title":"NSD action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "start":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "vim": {"type": "string"},
                "customer": {"type":"string"},
                "customer_id": {"type":"integer"},
                "sdn_switch_bw": {"type":"integer"},
                "parameters":parameter_schema #hjc
            },
            "required": ["customer_id"]
        },
        "start_v2": {
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "vim": {"type": "string"},
                "customer": {"type":"string"},
                "customer_id": {"type":"integer"},
                "sdn_switch_bw": {"type":"integer"},
                "parameters":parameter_schema,
                "onebox_id": name_schema,
                "vnf_list": {"type":"array","items":so_vnf_schema,"minItems":1},
                "bonding":{"type":"boolean"}    # 1: ??????????????????, 0: ?????? vnf
            },
            "required": ["onebox_id", "vnf_list"]
        },
        "deploy":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "vim": {"type": "string"},
                "customer": {"type":"string"},
                "customer_id": {"type":"integer"},
                "parameters":parameter_schema #hjc
            },
            "required": ["instance_name"]
        },
        "reserve":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "vim": {"type": "string"},
                "customer": {"type":"string"},
                "customer_id": {"type":"integer"},
                "parameters":parameter_schema #hjc
            },
            "required": ["instance_name"]
        },
        "verify":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "vim": {"type": "string"},
                "customer": {"type":"string"},
                "customer_id": {"type":"integer"},
                "parameters":parameter_schema #hjc
            },
            "required": ["instance_name"]
        },
        "prev_args": {
            "type":"object",
            "properties": {
                "customer": {"type":"string"},
                "customer_id": {"type":"integer"}
            },
            "required": ["customer_id"]
        }
    },
    "additionalProperties": False
}

vnf_action_schema = {
    "title":"VNF action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "start":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "stop":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "reboot":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "verify":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "check_license":{
            "type": "object",
            "properties": {
                "license_value":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "backup":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "trigger_type":{"type":"string"},
                "backup_server":{"type":"string"},
                "backup_location":{"type":"string"},
                "requester":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "restore":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "backup_id":{"type":"integer"},
                "type":{"type":"string"},
                "meta_data":{"type":"string"}
            },
            "additionalProperties": True
        }
    },
    "additionalProperties": False
}

vdu_action_schema = {
    "title":"VNF VDU action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "start":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "stop":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "reboot":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "verify":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        }
    },
    "minProperties": 1,
    # "maxProperties": 1,
    "additionalProperties": False
}

nsr_action_schema = {
    "title":"NSR action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "reinit_config":{
            "type": "object",
            "properties": {
                "meta_data":{"type":"string"}
            }
        },
        "backup":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "trigger_type":{"type":"string"},
                "backup_server":{"type":"string"},
                "backup_location":{"type":"string"},
                "requester":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "restore":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "force_restore":{"type":"boolean"},
                "backup_id":{"type":"integer"},
                "meta_data":{"type":"string"},
                "type":{"type":"string"}
            }
        },
        "update":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "force_restore":{"type":"boolean"},
                "meta_data":{"type":"string"}
            }
        },
        "check_status":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "force_restore":{"type":"boolean"},
                "meta_data":{"type":"string"}
            }
        }
    },
    "additionalProperties": False
}

server_action_schema = {
    "title":"One-Box server action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "requester":{"type":"string"},
        "backup":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "trigger_type":{"type":"string"},
                "backup_server":{"type":"string"},
                "backup_location":{"type":"string"},
                "requester":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "restore":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "force_restore":{"type":"boolean"},
                "backup_id":{"type":"string"},
                "requester":{"type":"string"},
                "mgmt_ip":{"type":"string"},
                "wan_mac":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "freset":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "force_reset":{"type":"boolean"},
                "meta_data":{"type":"string"}
            }
        },
        "check":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "reset_mac":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "nic_mod":server_schema
        # "nic_mod":{
        #     "type": "object",
        #     "properties": {
        #         "wan_list" : {"type":"array", "items":wan_list_schema, "minItems":0}
        #     }
        # }
    },
    "additionalProperties": False
}

#hjc, for KT One-Box Service [END]



#
# dev schema
#

tenant_schema = {
    "title":"tenant information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tenant":{
            "type":"object",
            "properties":{
                "name": name_schema,
                "description": description_schema,
                "role_id": name_schema,
                "org_id": name_schema,
                "authority": {"type":"string"},
                "password": {"type":"string"}
            },
            "required": ["name"],
            "additionalProperties": True
        }
    },
    "required": ["tenant"],
    "additionalProperties": False
}
tenant_edit_schema = {
    "title":"tenant edit information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tenant":{
            "type":"object",
            "properties":{
                "name": name_schema,
                "description": description_schema,
            },
            "additionalProperties": False
        }
    },
    "required": ["tenant"],
    "additionalProperties": False
}

                             
host_schema = {
    "type":"object",
    "properties":{
        "id":id_schema,
        "name": name_schema,
    },
    "required": ["id"]
}
image_schema = {
    "type":"object",
    "properties":{
        "id":id_schema,
        "name": name_schema,
    },
    "required": ["id","name"]
}

new_host_response_schema = {
    "title":"host response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "host": host_schema
    },
    "required": ["host"],
    "additionalProperties": False
}

get_images_response_schema = {
    "title":"openvim images response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "images":{
            "type":"array",
            "items": image_schema,
        }
    },
    "required": ["images"],
    "additionalProperties": False
}

get_hosts_response_schema = {
    "title":"openvim hosts response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "hosts":{
            "type":"array",
            "items": host_schema,
        }
    },
    "required": ["hosts"],
    "additionalProperties": False
}

get_host_detail_response_schema = new_host_response_schema # TODO: Content is not parsed yet

get_server_response_schema = {
    "title":"openvim server response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "servers":{
            "type":"array",
            "items": server_schema,
        }
    },
    "required": ["servers"],
    "additionalProperties": False
}

new_tenant_response_schema = {
    "title":"tenant response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tenant":{
            "type":"object",
            "properties":{
                "id":id_schema,
                "name": nameshort_schema,
                "description":description_schema,
                "enabled":{"type" : "boolean"}
            },
            "required": ["id"]
        }
    },
    "required": ["tenant"],
    "additionalProperties": False
}

new_network_response_schema = {
    "title":"network response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "network":{
            "type":"object",
            "properties":{
                "id":id_schema,
                "name":name_schema,
                "type":{"type":"string", "enum":["bridge_man","bridge_data","data", "ptp"]},
                "shared":{"type":"boolean"},
                "tenant_id":id_schema,
                "admin_state_up":{"type":"boolean"},
                "vlan":vlan1000_schema
            },
            "required": ["id"]
        }
    },
    "required": ["network"],
    "additionalProperties": False
}

new_port_response_schema = {
    "title":"port response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "port":{
            "type":"object",
            "properties":{
                "id":id_schema,
            },
            "required": ["id"]
        }
    },
    "required": ["port"],
    "additionalProperties": False
}

new_flavor_response_schema = {
    "title":"flavor response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "flavor":{
            "type":"object",
            "properties":{
                "id":id_schema,
            },
            "required": ["id"]
        }
    },
    "required": ["flavor"],
    "additionalProperties": False
}

new_image_response_schema = {
    "title":"image response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "image":{
            "type":"object",
            "properties":{
                "id":id_schema,
            },
            "required": ["id"]
        }
    },
    "required": ["image"],
    "additionalProperties": False
}

new_vminstance_response_schema = {
    "title":"server response information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "server":{
            "type":"object",
            "properties":{
                "id":id_schema,
            },
            "required": ["id"]
        }
    },
    "required": ["server"],
    "additionalProperties": False
}

internal_connection_element_schema = {
    "type":"object",
    "properties":{
        "VNFC": nameshort_schema,
        "local_iface_name": nameshort_schema
    }
}

internal_connection_schema = {
    "type":"object",
    "properties":{
        "name": name_schema,
        "description":description_schema,
        "type":{"type":"string", "enum":["bridge","data","ptp"]},
        "elements": {"type" : "array", "items": internal_connection_element_schema, "minItems":2}
    },
    "required": ["name", "type", "elements"],
    "additionalProperties": False
}

external_connection_schema = {
    "type":"object",
    "properties":{
        "name": name_schema,
        "type":{"type":"string", "enum":["mgmt","bridge","data"]},
        "VNFC": nameshort_schema,
        "local_iface_name": nameshort_schema ,
        "description":description_schema
    },
    "required": ["name", "type", "VNFC", "local_iface_name"],
    "additionalProperties": False
}

interfaces_schema={
    "type":"array",
    "items":{
        "type":"object",
        "properties":{
            "name":nameshort_schema,
            "dedicated":{"type":"string","enum":["yes","no","yes:sriov"]},
            "bandwidth":bandwidth_schema,
            "vpci":pci_schema,
            "mac_address": mac_schema
        },
        "additionalProperties": False,
        "required": ["name","dedicated", "bandwidth"]
    }
}

bridge_interfaces_schema={
    "type":"array",
    "items":{
        "type":"object",
        "properties":{
            "name": nameshort_schema,
            "bandwidth":bandwidth_schema,
            "vpci":pci_schema,
            "mac_address": mac_schema,
            "model": {"type":"string", "enum":["virtio","e1000","ne2k_pci","pcnet","rtl8139"]}
        },
        "additionalProperties": False,
        "required": ["name"]
    }
}

devices_schema={
    "type":"array",
    "items":{
        "type":"object",
        "properties":{
            "type":{"type":"string", "enum":["disk","cdrom","xml"] },
            "image": path_schema,
            "image metadata": metadata_schema, 
            "vpci":pci_schema,
            "xml":xml_text_schema,
        },
        "additionalProperties": False,
        "required": ["type"]
    }
}


#Future VNFD schema to be defined
vnfd_schema_v02 = {
    "title":"vnfd information schema v0.2",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "version": {"type": "string", "pattern":"^v0.2$"},
        "vnf":{
            "type":"object",
            "properties":{
                "name": name_schema,
            },
            "required": ["name"],
            "additionalProperties": True
        }
    },
    "required": ["vnf", "version"],
    "additionalProperties": False
}

get_processor_rankings_response_schema = {
    "title":"processor rankings information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "rankings":{
            "type":"array",
            "items":{
                "type":"object",
                "properties":{
                    "model": description_schema,
                    "value": integer0_schema
                },
                "additionalProperties": False,
                "required": ["model","value"]
            }
        },
        "additionalProperties": False,
        "required": ["rankings"]
    }
}


nsd_schema_v01 = {
    "title":"network scenario descriptor information schema v0.1",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "name":name_schema,
        "description": description_schema,
        "topology":{
            "type":"object",
            "properties":{
                "nodes": {
                    "type":"object",
                    "patternProperties":{
                        ".": {
                            "type": "object",
                            "properties":{
                                "type":{"type":"string", "enum":["VNF", "other_network", "network", "external_network"]}
                            },
                            "patternProperties":{
                                "^(VNF )?model$": {"type": "string"}
                            },
                            "required": ["type"]
                        }
                    }
                },
                "connections": {
                    "type":"object",
                    "patternProperties":{
                        ".": {
                            "type": "object",
                            "properties":{
                                "nodes":{"oneOf":[{"type":"object", "minProperties":2}, {"type":"array", "minLength":2}]}
                            },
                            "required": ["nodes"]
                        },
                    }
                }
            },
            "required": ["nodes"],
            "additionalProperties": False
        }
    },
    "required": ["name","topology"],
    "additionalProperties": False
}

#Future NSD schema to be defined
nsd_schema_v02 = {
    "title":"network scenario descriptor information schema v0.2",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "version": {"type": "string", "pattern":"^v0.2$"},
        "topology":{
            "type":"object",
            "properties":{
                "name": name_schema,
            },
            "required": ["name"],
            "additionalProperties": True
        }
    },
    "required": ["topology", "version"],
    "additionalProperties": False
}

scenario_new_schema = {
    "title":"new scenario information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    #"oneOf": [nsd_schema_v01, nsd_schema_v02, nsd_schema_v04] #hjc
    "oneOf": [nsd_schema_v04] #hjc
}

scenario_edit_schema = {
    "title":"edit scenario information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "name":name_schema,
        "description": description_schema,
        "topology":{
            "type":"object",
            "properties":{
                "nodes": {
                    "type":"object",
                    "patternProperties":{
                        "^[a-fA-F0-9]{8}(-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$": {
                            "type":"object",
                            "properties":{
                                "graph":{
                                    "type": "object",
                                    "properties":{
                                        "x": integer0_schema,
                                        "y": integer0_schema,
                                        "ifaces":{ "type": "object"}
                                    }
                                },
                                "description": description_schema,
                                "name": name_schema
                            }
                        }
                    }
                }
            },
            "required": ["nodes"],
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}

scenario_action_schema_v01 = {
    "title":"scenario action information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "start":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "datacenter": {"type": "string"},
                "parameters":parameter_schema #hjc
            },
            "required": ["instance_name"]
        },
        "deploy":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "datacenter": {"type": "string"}
            },
            "required": ["instance_name"]
        },
        "reserve":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "datacenter": {"type": "string"}
            },
            "required": ["instance_name"]
        },
        "verify":{
            "type": "object",
            "properties": {
                "instance_name":name_schema,
                "description":description_schema,
                "datacenter": {"type": "string"}
            },
            "required": ["instance_name"]
        }
    },
    "minProperties": 1,
    "maxProperties": 1,
    "additionalProperties": False
}

#scenario_action_schema = {
#    "title":"scenario action schema",
#    "$schema": "http://json-schema.org/draft-04/schema#",
#    #"oneOf": [scenario_action_schema_v01, scenario_action_schema_v04] #hjc
#    "oneOf": [scenario_action_schema_v04] #hjc
#}

instance_scenario_action_schema = {
    "title":"instance scenario action information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "start":{"type": "null"},
        "pause":{"type": "null"},
        "resume":{"type": "null"},
        "shutoff":{"type": "null"},
        "shutdown":{"type": "null"},
        "forceOff":{"type": "null"},
        "rebuild":{"type": "null"},
        "reboot":{
            "type": ["object","null"],
        },
        "vnfs":{"type": "array", "items":{"type":"string"}},
        "vms":{"type": "array", "items":{"type":"string"}}
    },
    "minProperties": 1,
    #"maxProperties": 1,
    "additionalProperties": False
}

#hjc2






ponebox_schema = {
    "title":"physical onebox information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "ponebox":{
            "type":"object",
            "properties":{
                "name": name_schema,
                "description": description_schema,
                "server_type": {"type":"string"},
                "mgmt_ip_addr": {"type":"string"},
                "install_org_id": name_schema,
                "state": {"type":"string"},
                "phy_net_id": name_schema,
                "customer_id": name_schema
            },
            "required": ["name"],
            "additionalProperties": True
        }
    },
    "required": ["ponebox"],
    "additionalProperties": False
}

ponebox_associate_schema={
    "title":"pOnebox associate information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "ponebox":{
            "type":"object",
            "properties":{
                "name": name_schema,
                "mgmt_ip_addr": {"type":"string"},
                "install_org_id": name_schema,
                "phy_net_id": name_schema,
                "customer_id": name_schema
            },
            "required": ["customer_id", "mgmt_ip_addr"],
            "additionalProperties": True
        }
    },
    "required": ["ponebox"],
    "additionalProperties": False
}


############### v20 Schemas for ETSI Descriptors #######################
vnfd_license_key_schema_v20 = {"type" : "array", "items": name_schema, "minItems":1}

vnfd_license_schema_v20 = {
    "type": "object",
    "properties": {
        "name":name_schema,
        "type":{"type": "string", "enum":["key","server","key-server"]},
        "value":vnfd_license_key_schema_v20, # only for type = key or key_server
        "server_url":http_schema # only for type = server or key_server
    },
    "required": ["name","type"],
    "additionalProperties": False
}

vnfd_image_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "version":{"type": "string"},
        "container_format":{"type":"string","enum":["ami","ari","aki","bare","ova", "ovf","any"]},
        "disk_format":{"type":"string","enum":["qcow2","ami","aki","vhd","vmdk","raw","iso","vdl"]},
        "public":{"type" : "boolean"},
        #"path":{"oneOf": [path_schema, http_schema]},
        "path":{"type":"string"},
        "metadata":{"type":"string"}
    },
    "required": ["disk_format"],
    "additionalProperties": False
}

vnfd_vdu_lifecycle_event_schema_v20 = vnfd_vnfc_config_schema
vnfd_vdu_monitoring_parameter_schema_v20 = vnfd_vnfc_monitor_schema
vnfd_vdu_vnfc_web_url_schema_v20 = vnfd_vnfc_weburl_v04
vnfd_dependency_schema_v20 = {"type":"string"}
vnfd_lifecycle_event_schema_v20 = vnfd_vnfc_config_schema
vnfd_monitoring_parameter_schema_v20 = {"type":"string"}
vnfd_deployment_flavour_schema_v20 = {"type":"string"}

vnfd_parameter_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "category":name_schema,
        "type": {"type":"string"},
        "description": description_schema,
        "default_value": {"type":"string"}
    },
    "required": ["id"],
    "additionalProperties": True                      
}

vnfd_output_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "category":name_schema,
        "type": {"type":"string"},
        "description": description_schema,
        "value": {"type":"string"},
        "default_value":{"type":"string"}
    },
    "required": ["id"],
    "additionalProperties": True                      
}

vnfd_vdu_vnfc_cp_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "virtual_link_reference":name_schema,
        "type":{"type":"string"},
        "parameter":{"type":"array", "items":vnfd_parameter_schema_v20, "minItems":0},
        "output":{"type":"array", "items":vnfd_output_schema_v20, "minItems":0},
        "graph":{"type":"string"}
    },
    "required": ["id"],                 
    "additionalProperties": True
}

vnfd_vdu_vnfc_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "description":description_schema,
        "web_url":vnfd_vdu_vnfc_web_url_schema_v20,
        "connection_point":{"type":"array","items":vnfd_vdu_vnfc_cp_schema_v20,"minItems":1},
        "graph":{"type":"string"}
    },
    "required": ["id"],
    "additionalProperties": True                      
}

vnfd_vdu_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "description":description_schema,
        "image":vnfd_image_schema_v20,
        "parameter":{"type":"array", "items":vnfd_parameter_schema_v20, "minItems":0},
        "lifecycle_event":{"type":"array","items":vnfd_vdu_lifecycle_event_schema_v20,"minItems":0},
        "monitoring_parameter":{"type":"array","items":vnfd_vdu_monitoring_parameter_schema_v20,"minItems":0},
        "vnfc": {"type":"array", "items":vnfd_vdu_vnfc_schema_v20, "minItems":1},
        "graph":{"type":"string"}
    },
    "required": ["id","image"],
    "additionalProperties": True                      
}

vnfd_vl_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "connectivity_type": {"type":"string"},
        "description": description_schema,
        "connection_point_references": {"type":"array", "items":name_schema, "minItems":0},
        "graph":{"type":"string"}
    },
    "required": ["id"],
    "additionalProperties": True                      
}

vnfd_cp_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "virtual_link_reference":name_schema,
        "type":{"type":"string"},
        "graph":{"type":"string"}
    },
    "required": ["id"],                 
    "additionalProperties": True
}

vnfd_schema_v20 = {
    "title":"vnfd information schema v2.0 for KT One-Box service Using ETSI Standard VNFD",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "vnf":{
            "type":"object",
            "properties":{
                "id": name_schema,
                "name": name_schema,
                "description": description_schema,
                "version": {"type":"string"},
                "descriptor_version": {"type":"string"},
                "category": {"type":"string"},
                "public": {"type" : "boolean"},
                "vendor": name_schema,
                "owners": {"type" : "array", "items": name_schema, "minItems":1},   # for KOB
                "license":vnfd_license_schema_v20,
                "web_url": {"type": "string"},
                "parameter": {"type":"array", "items":vnfd_parameter_schema_v20, "minItems":0},
                "vdu":{"type":"array", "items": vnfd_vdu_schema_v20, "minItems":1},
                "virtual_link":{"type":"array", "items": vnfd_vl_schema_v20, "minItems":0},
                "connection_point":{"type":"array", "items":vnfd_cp_schema_v20, "minItems":1},
                "dependency": {"type":"array", "items":vnfd_dependency_schema_v20},
                "lifecycle_event": {"type":"array", "items":vnfd_lifecycle_event_schema_v20, "minItems":0},
                "monitoring_parameter": {"type":"array", "items":vnfd_monitoring_parameter_schema_v20, "minItems":0},
                "deployment_flavour": {"type":"array", "items":vnfd_deployment_flavour_schema_v20, "minItems":0}
            },
            "required": ["id","name","descriptor_version"],
            "additionalProperties": True
        }
    },
    "required": ["vnf"],
    "additionalProperties": False
}

nsd_vnf_dependency_schema_v20 = {"type":"string"}
nsd_parameter_schema_v20 = vnfd_parameter_schema_v20

nsd_cp_schema_v20 = {
   "type": "object",
   "properties": {
        "id":name_schema,
        "name":name_schema,
        "graph":{"type":"string"},
        "type":{"type":"string"},
        "parameter":{"type":"array", "items":vnfd_parameter_schema_v20, "minItems":0}
    },
    "required": ["id"],
    "additionalProperties": True                     
}

vld_schema_v20 = {
    "type": "object",
    "properties": {
        "id":name_schema,
        "name":name_schema,
        "description":description_schema,
        "graph":{"type":"string"},
        "vendor":name_schema,
        "descriptor_version":{"type":"string"},
        "number_of_endpoints":{"type":"integer"},
        "connection": {"type":"array", "items":name_schema,"minItems":0},
        "connectivitity_type": {"type": "string", "enum":["e-lan","e-line","e-tree","kt-direct"]},
        "parameter":{"type":"array", "items":vnfd_parameter_schema_v20, "minItems":0},
        "meta_data":{"type":"string"}
    },
    "required": ["id", "descriptor_version"],
    "additionalProperties": True 
}

nsd_schema_v20 = {
    "title":"network scenario descriptor information schema v2.0 for KT One-Box Service",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "id":name_schema,
        "name":name_schema,
        "description": description_schema,
        "descriptor_version":{"type":"string"},
        "version":{"type":"string"},
        "public":{"type":"boolean"},
        "vendor":{"type":"string"},
        "graph":{"type":"string"},
        "vnfd":{"type":"array","items":name_schema,"minItems":1},
        "parameter":{"type":"array","items":nsd_parameter_schema_v20,"minItems":0},
        "vld": {"type":"array","items":vld_schema_v20,"minItems":0},
        "connection_point":{"type":"array","items":nsd_cp_schema_v20,"minItems":1},
        "lifecycle_event":{"type":"string"}, #TBD
        "monitoring_parameter":{"type":"string"}, #TBD
        "vnf_dependency":{"type":"array","items":nsd_vnf_dependency_schema_v20,"minItems":1}
    },
    "required": ["id","name","descriptor_version"],
    "additionalProperties": False
}


# HA Set schema
set_ha_schema = {
    "title":"HA setting information schema for KT One-Box Service",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "vip_w":{"type":"string"},    # virtual ip : wan
        "vip_o":{"type":"string"},    # virtual ip : ofiice
        "vip_s":{"type":"string"},    # virtual ip : server
        "cluster_list":{"type":"array","items":cluster_list_schema,"minItems":0}
    },
    "additionalProperties": True
}

# HA Clear schema
clear_ha_schema = {
    "title":"HA setting information schema for KT One-Box Service",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "cluster_list":{"type":"array","items":cluster_list_schema,"minItems":0}
    },
    "additionalProperties": True
}

vnf_add_schema = {
    "type": "object",
    "properties": {
        "vnfd_name":{"type":"string"},
        "vnfd_version":{"type":"string"},
        "service_number":{"type":"string"},
        "service_period":{"type":"string"},
        "parameters":parameter_schema
    },
    "required": ["vnfd_name", "vnfd_version"],
    "additionalProperties": True
}
vnf_del_schema = {
    "type": "object",
    "properties": {
        "vnfd_name":{"type":"string"},
        "vnfd_version":{"type":"string"}
    },
    "required": ["vnfd_name", "vnfd_version"],
    "additionalProperties": True
}
nsr_update_schema = {
    "title":"NSR action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "update":{
            "type": "object",
            "properties": {
                "add_vnf":{"type":"array","items":vnf_add_schema,"minItems":0},
                "del_vnf":{"type":"array","items":vnf_del_schema,"minItems":0}

            }
        }
    },
    "additionalProperties": True
}

vnf_account_schema={
    "title":"service order information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid": {"type":"string"},
        "tpath": {"type":"string"},
        "onebox_id" : {"type":"string"},
        "serverseq": {"type":"string"},
        "account_id": {"type":"string"},
        "account_pw": {"type":"string"},
        "force": {"type":"boolean"}
    },
    "additionalProperties": True
}

vnf_image_file_schema={
    "title":"service order information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid": {"type":"string"},
        "tpath": {"type":"string"},
        "name" : {"type":"string"},
        "location": {"type":"string"},
        "filesize": {"type":"string"},
        "checksum": {"type":"string"},
        "metadata": {"type":"string"},
        "description": {"type":"string"}
    },
    "required": ["name", "location", "filesize"],
    "additionalProperties": True
}

vnf_image_deploy_schema = {
    "type": "object",
    "properties": {
        "tid": {"type":"string"},
        "tpath": {"type":"string"},
        "release":{
            "type":"object",
            "properties":{
                "target_onebox": {"type":"array", "items":{"type":"string"}, "minItems":1}
            }
        }
    },
    "required": ["release"],
    "additionalProperties": True
}


vnf_image_check_schema = {
    "type": "object",
    "properties": {
        "name" : {"type":"string"},
        "location": {"type":"string"}
    },
    "required": ["name", "location"],
    "additionalProperties": True
}


vnf_image_id_schema = {
    "title":"NSR action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "vnfd_name":{"type":"string"},
        "image_id":{"type":"string"}
    },
    "additionalProperties": True
}

vnf_image_action_schema = {
    "type": "object",
    "properties": {
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "update":{
            "type": "object",
            "properties": {
                "image_id":{"type":"string"},
                "update_dt":{"type":"string"},
                "memo":{"type":"string"},
                "mode":{"type":"string"}
            }
        },
        "version":{
            "type": "object",
            "properties": {
                "serverseq":{"type":"string"}
            }
        }
    },
    "minProperties": 1,
    "additionalProperties": False
}

customer_delete_multi_schema = {
    "type": "object",
    "properties": {
        "customers": {"type":"array", "items":{"type":"string"}, "minItems":1}
    },
    "required": ["customers"],
    "additionalProperties": True
}


patch_save_schema={
    "title":"service order information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "location": {"type":"string"},
        "filesize": {"type":"string"},
        "description": {"type":"string"}
    },
    "required": ["location"],
    "additionalProperties": True
}


patch_deploy_schema={
    "title":"service order information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "onebox_id": {"type":"string"},
        "patch_id": {"type":"integer"}
    },
    "required": ["onebox_id", "patch_id"],
    "additionalProperties": True
}

# pnf server schema : bg.bong 2019.01.17
nic_schema = {
    "title":"onebox server nic information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "iface_name": {"type":"string"},
        "mac_addr": {"type":"string"},
        "zone": {"type":"string"},
        "ip_type": {"type":"string"},
        "ip_addr": {"type":"string"},
        "gw_ip_addr": {"type":"string"},
        "mgmt_boolean": {"type":"boolean"},
        "link_protocol": {"type":"string"},
        "link_status": {"type":"string"}
    },
    "required":["iface_name","zone", "ip_addr"],
    "additionalProperties":True
}

server_schema_pnf = {
    "title":"PNF : physical onebox server information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "onebox_id": {"type":"string"},
        "onebox_type": {"type":"string"},
        "web_url": {"type":"string"},
        "oba_baseurl": {"type":"string"},
        "vnfm_baseurl": {"type":"string"},
        "vim_baseurl": {"type":"string"},
        "wan_mode": {"type":"string"},
        "hardware": server_hardware_schema,
        "operating_system": {"type":"string"},
        "version": {"type":"string"},
        "nic": {"type" : "array", "items": nic_schema, "minItems":1},
        "oba_version": {"type":"string"},
        "first_notify": {"type":"boolean"}
    },
    "required":["onebox_type","oba_baseurl", "nic"],
    "additionalProperties": False
}

rlt_schema_pnf = {
    "title":"PNF : physical onebox server information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "onebox_type": {"type":"string"},
        "nsseq": {"type":"string"}
    },
    "required":["onebox_type", "nsseq"],
    "additionalProperties": False
}

server_action_schema_new = {
    "title":"One-Box server action information schema v4",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid":{"type":"string"},
        "tpath":{"type":"string"},
        "requester":{"type":"string"},
        "backup":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "trigger_type":{"type":"string"},
                "backup_server":{"type":"string"},
                "backup_location":{"type":"string"},
                "requester":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "restore":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "force_restore":{"type":"boolean"},
                "backup_id":{"type":"string"},
                "requester":{"type":"string"},
                "mgmt_ip":{"type":"string"},
                "wan_mac":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "reboot":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "freset":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "force_reset":{"type":"boolean"},
                "meta_data":{"type":"string"}
            }
        },
        "check":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "reset_mac":{
            "type": "object",
            "properties": {
                "user":{"type":"string"},
                "meta_data":{"type":"string"}
            }
        },
        "nic_mod":server_schema
        # "nic_mod":{
        #     "type": "object",
        #     "properties": {
        #         "wan_list" : {"type":"array", "items":wan_list_schema, "minItems":0}
        #     }
        # }
    },
    "additionalProperties": False
}


work_schema_base64 = {
    "title":"Work : work test base64 information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "backup_file": {"type":"string"},
    },
    "additionalProperties": True
}

work_schema_job = {
    "title":"Work : work test job information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
    },
    "additionalProperties": True
}

service_onebox_update_schema = {
    "title":"Work : work test job information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "org_name":{"type":"string"}
    },
    "additionalProperties": True
}

service_onebox_update_servicenum_schema = {
    "title":"Work : work test job information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "service_number":{"type":"string"}
    },
    "additionalProperties": True
}


server_schema_armbox = {
    "title":"physical arm-box server information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid": {"type":"string"},
        "tpath": {"type":"string"},
        "order_id": {"type":"string"},
        "servername": name_schema,
        "description": description_schema,
        "serveruuid": name_schema,
        "customerseq": integer1_schema,
        "customer_id": {"type":["string","null"]},
        "customer_name": name_schema,
        "mgmt_ip": {"type":["string","null"]},
        "public_ip": {"type":["string","null"]},
        "public_gw_ip": {"type":["string","null"]},
        "public_cidr_prefix": {"type":"integer"},
        "public_mac": {"type":["string","null"]},
        "public_ip_dhcp": {"type":"boolean"},
        "servercode": {"type":["string","null"]},
        "nfmaincategory": {"type":["string","null"]},
        "nfsubcategory": {"type":["string","null"]},
        "org_name": {"type":["string","null"]},
        "modify_dttm": {"type":["string","null"]},
        "stock_dttm": {"type":["string","null"]},
        "deliver_dttm": {"type":["string","null"]},
        "serial_no": {"type":["string","null"]},
        "onebox_flavor": {"type":["string","null"]},
        "vim": server_vim_schema,
        "vnfm": server_vnfm_schema,
        "obagent": server_obagent_schema,
        "software": server_software_schema,
        "hardware": server_hardware_schema,
        "network": {"type" : "array", "items": server_network_schema, "minItems":1},
        "wan": server_wan_schema,
        "lan_office1": server_lan_schema,
        "lan_office2": server_lan_schema,
        "lan_office": server_lan_schema,
        "lan_server": server_lan_schema,
        "vnet": {"type":"array", "items":server_vnet_schema, "minItems":0},
        "mgmt_nic" : {"type":["string","null"]},
        "public_nic" : {"type":["string","null"]},
        "wan_list" : {"type":"array", "items":wan_list_schema, "minItems":0},
        "extra_wan_list" : {"type":"array", "items":wan_list_schema, "minItems":0},
        "note": {"type":"array", "items":server_note_schema, "minItems":0},
        "default_ns_id" : {"type":["string","null"]},
        "first_notify" : {"type": "boolean"}
    },
    "additionalProperties": False
}

##### remote command control    #######################################################
# default schema
server_remote_control = {
    "title":"remote command control server information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "tid": {"type":["string","null"]},
        "tpath": {"type":["string","null"]},
        "userid": {"type":["string","null"]},
        "username": {"type":["string","null"]},
        "serverList": {"type":"string"},
        "cmdTxt": {"type":"string"},
        "connInfo": {"type":"string"},
        "cmdMode": {"type":"string"},
        "cmdType": {"type":"string"},
        "reserve": {"type":"string"},
        "reserve_date": {"type":["string","null"]},
        "reserve_hour": {"type":["string","null"]},
    },
    "additionalProperties": False
}

server_remote_control_reserve_delete = {
    "title":"remote command control server information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "sac_seq": {"type":"string"},
    },
    "additionalProperties": False
}

server_schema_change_ip = {
    "title":"remote command control server information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "public_ip": {"type":"string"},
        "mgmt_ip": {"type":"string"},
        "public_gw": {"type":"string"},
    },
    "additionalProperties": False
}

############    MMS     ##################################################################################
customer_list_schema={
    "type":"object",
    "properties":{
        "customerNm": {"type":["string", "null"]},
        "customerSeq": {"type":"integer"},
        "phone": {"type":["string", "null"]},
        "surveyUrl": {"type":["string", "null"]},
    },
    "required":["customerNm", "customerSeq", "phone", "surveyUrl"],
    "additionalProperties": True
}

server_mms_send = {
    "title":"MMS SEND information schema",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type":"object",
    "properties":{
        "surveyType": {"type":"string"},
        "customerList": {"type":"array", "items":customer_list_schema, "minItems":0},
        "mms_msg": {"type":"string"},
    },
    "additionalProperties": False
}