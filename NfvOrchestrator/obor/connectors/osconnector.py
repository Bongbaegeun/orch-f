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
    osconnector implements all the methods to interact with openstack using the python-client.
"""
__author__="Alfonso Tierno, Gerardo Garcia"
__date__ ="$22-jun-2014 11:19:29$"

import time
import sys

from keystoneauth1 import loading #hjc
from keystoneauth1 import session #hjc

from novaclient import client as nClient, exceptions as nvExceptions
import keystoneclient.v2_0.client as ksClient
import keystoneclient.v3.client as ksClient_v3
import keystoneclient.exceptions as ksExceptions
import glanceclient.v2.client as glClient
import glanceclient.client as gl1Client
import glanceclient.exc as gl1Exceptions

from httplib import HTTPException
from neutronclient.neutron import client as neClient
from neutronclient.common import exceptions as neExceptions
from heatclient.client import Client as heatClient #hjc
import heatclient.exc as heatException #hjc
import copy

from db.orch_db import HTTP_Bad_Request, HTTP_Not_Found, HTTP_Unauthorized, HTTP_Conflict, HTTP_Internal_Server_Error
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

"""
contain the openstack virtual machine status to openmano status
"""
vmStatus2manoFormat={'ACTIVE':'ACTIVE',
                     'PAUSED':'PAUSED',
                     'SUSPENDED': 'SUSPENDED',
                     'SHUTOFF':'INACTIVE',
                     'BUILD':'CREATING',
                     'ERROR':'ERROR','DELETING':'DELETING'
                     }
netStatus2manoFormat = {'ACTIVE':'ACTIVE','PAUSED':'PAUSED','INACTIVE':'INACTIVE','CREATING':'CREATING','ERROR':'ERROR','DELETING':'DELETING'}


class osconnector():


    def __init__(self, uuid, name, tenant, url, url_admin=None, user=None, passwd=None, debug=True, config={}):
        """
        using common constructor parameters. In this case
        'url' is the keystone authorization url,
        'url_admin' is not use
        Throw keystoneclient.apiclient.exceptions.AuthorizationFailure
        """
 
        self.k_creds={}
        # self.n_creds={}
        self.id        = uuid
        self.name      = name
        self.url       = url
        if not url:
            raise TypeError, 'url param can not be NoneType'
        self.k_creds['auth_url'] = url
        # self.n_creds['auth_url'] = url
        self.url_admin = url_admin
        self.tenant    = tenant
        if tenant:
            self.k_creds['tenant_name'] = tenant
            # self.n_creds['project_id']  = tenant
        self.user      = user
        if user:
            self.k_creds['username'] = user
            # self.n_creds['username'] = user
        self.passwd    = passwd
        if passwd:
            self.k_creds['password'] = passwd
            # self.n_creds['api_key']  = passwd

        self.k_creds['insecure'] = True
        # self.n_creds['insecure'] = True

        self.config              = config
        self.debug               = debug
        self.reload_client       = True
        self.nova = None


    def __getitem__(self,index):

        if index=='tenant':
            return self.tenant
        elif index=='id':
            return self.id
        elif index=='name':
            return self.name
        elif index=='user':
            return self.user
        elif index=='passwd':
            return self.passwd
        elif index=='url':
            return self.url
        elif index=='url_admin':
            return self.url_admin
        elif index=='config':
            return self.config
        else:
            raise KeyError("Invalid key '%s'" %str(index))


    def __setitem__(self,index, value):
        """
        Set individuals parameters
        Throw keystoneclient.apiclient.exceptions.AuthorizationFailure
        """
        if index=='tenant':
            self.reload_client=True
            self.tenant = value
            if value:
                self.k_creds['tenant_name'] = value
                # self.n_creds['project_id']  = value
            else:
                del self.k_creds['tenant_name']
                # del self.n_creds['project_id']
        elif index=='id':
            self.id = value
        elif index=='name':
            self.name = value
        elif index=='user':
            self.reload_client=True
            self.user = value
            if value:
                self.k_creds['username'] = value
                # self.n_creds['username'] = value
            else:
                del self.k_creds['username']
                # del self.n_creds['username']
        elif index=='passwd':
            self.reload_client=True
            self.passwd = value
            if value:
                self.k_creds['password'] = value
                # self.n_creds['password'] = value
                # self.n_creds['api_key']  = value
            else:
                del self.k_creds['password']
                # del self.n_creds['api_key']
        elif index=='url':
            self.reload_client=True
            self.url = value
            if value:
                self.k_creds['auth_url'] = value
                # self.n_creds['auth_url'] = value
            else:
                raise TypeError, 'url param can not be NoneType'

        elif index=='url_admin':
            self.url_admin = value
        else:
            raise KeyError("Invalid key '%s'" %str(index))


    def reload_connection_novatest(self, timeout_value=30):

        # TODO control the timing and possible token timeout, but it seams that python client does this task for us :-)
        if self.reload_client:
            self.k_creds['timeout'] = timeout_value
            # self.n_creds['timeout'] = timeout_value

            nova_options = {"auth_url": self.k_creds['auth_url'], "username": self.k_creds['username'], "password": self.k_creds['password']}
            nova_options["project_name"] = self.k_creds['tenant_name']

            if self.k_creds['auth_url'].find("/v3") > 0:
                self.keystone = ksClient_v3.Client(**self.k_creds)
                log.debug("                   KEYSTONE v3: %s" % str(self.keystone))

                nova_options["user_domain_id"] = "default"
                nova_options["project_domain_name"] = "default"
            else:
                self.keystone = ksClient.Client(**self.k_creds)
                log.debug("                   KEYSTONE: %s" % str(self.keystone))

            hjc_loader = loading.get_plugin_loader('password')
            hjc_auth = hjc_loader.load_from_options(**nova_options)
            hjc_sess = session.Session(auth=hjc_auth, verify=False)
            self.nova = nClient.Client(2, session=hjc_sess)
            # self.nova = nClient.Client(2, **self.n_creds)
            log.debug("                   NOVA: %s" % str(self.nova))

            # log.debug("                     compute = %s" %str(self.keystone.service_catalog.url_for(service_type='compute', endpoint_type='publicURL')))

            self.glance_endpoint = self._private_ipcheck(self.keystone.service_catalog.url_for(service_type='image', endpoint_type='publicURL'), 'g')
            log.debug("                   GLANCE: endpoint = %s" % self.glance_endpoint)
            self.glance = glClient.Client(self.glance_endpoint, token=self.keystone.auth_token, **self.k_creds)

            self.ne_endpoint = self._private_ipcheck(self.keystone.service_catalog.url_for(service_type='network', endpoint_type='publicURL'), 'n')
            log.debug("                   NEUTRON: endpoint = %s" % self.ne_endpoint)
            self.neutron = neClient.Client('2.0', endpoint_url=self.ne_endpoint, token=self.keystone.auth_token, **self.k_creds)
            # hjc
            self.heat_endpoint = self._private_ipcheck(self.keystone.service_catalog.url_for(service_type='orchestration', endpoint_type='publicURL'), 'h')
            log.debug("                   HEAT: endpoint = %s" % self.heat_endpoint)
            self.heat = heatClient('1', endpoint=self.heat_endpoint, token=self.keystone.auth_token, **self.k_creds)
            self.reload_client = False


    def reload_connection(self, timeout_value=30):
        """
        called before any operation, it check if credentials has changed
        """

        # log.debug('[osconnector] self.k_creds = %s' %str(self.k_creds))
        # log.debug('[osconnector] self.id = %s' %str(self.id))
        # log.debug('[osconnector] self.name = %s' %str(self.name))
        # log.debug('[osconnector] self.url = %s' %str(self.url))
        # log.debug('[osconnector] self.url_admin = %s' %str(self.url_admin))
        # log.debug('[osconnector] self.tenant = %s' %str(self.tenant))
        # log.debug('[osconnector] self.user = %s' %str(self.user))
        # log.debug('[osconnector] self.passwd = %s' %str(self.passwd))
        # log.debug('[osconnector] self.config = %s' %str(self.config))
        # log.debug('[osconnector] self.debug = %s' %str(self.debug))
        # log.debug('[osconnector] self.reload_client = %s' %str(self.reload_client))
        # log.debug('[osconnector] self.nova = %s' %str(self.nova))

        #TODO control the timing and possible token timeout, but it seams that python client does this task for us :-)
        if self.reload_client:
            self.k_creds['timeout'] = timeout_value
            # self.n_creds['timeout'] = timeout_value

            nova_options = {"auth_url":self.k_creds['auth_url'], "username":self.k_creds['username'], "password":self.k_creds['password']}
            nova_options["project_name"] = self.k_creds['tenant_name']

            if self.k_creds['auth_url'].find("/v3") > 0:
                self.keystone = ksClient_v3.Client(**self.k_creds)
                log.debug("                   KEYSTONE v3: %s" %str(self.keystone))

                nova_options["user_domain_id"] = "default"
                nova_options["project_domain_name"] = "default"
            else:
                self.keystone = ksClient.Client(**self.k_creds)
                log.debug("                   KEYSTONE: %s" %str(self.keystone))

            hjc_loader = loading.get_plugin_loader('password')
            hjc_auth = hjc_loader.load_from_options(**nova_options)
            hjc_sess = session.Session(auth=hjc_auth, verify=False)
            self.nova = nClient.Client(2, session=hjc_sess)
            # self.nova = nClient.Client(2, **self.n_creds)
            log.debug("                   NOVA: %s" %str(self.nova))

            # log.debug("                     compute = %s" %str(self.keystone.service_catalog.url_for(service_type='compute', endpoint_type='publicURL')))

            self.glance_endpoint = self._private_ipcheck(self.keystone.service_catalog.url_for(service_type='image', endpoint_type='publicURL'), 'g')
            log.debug("                   GLANCE: endpoint = %s" %self.glance_endpoint)
            self.glance = glClient.Client(self.glance_endpoint, token=self.keystone.auth_token, **self.k_creds)

            self.ne_endpoint = self._private_ipcheck(self.keystone.service_catalog.url_for(service_type='network', endpoint_type='publicURL'), 'n')
            log.debug("                   NEUTRON: endpoint = %s" %self.ne_endpoint)
            self.neutron = neClient.Client('2.0', endpoint_url=self.ne_endpoint, token=self.keystone.auth_token, **self.k_creds)
            #hjc
            self.heat_endpoint = self._private_ipcheck(self.keystone.service_catalog.url_for(service_type='orchestration', endpoint_type='publicURL'), 'h')
            log.debug("                   HEAT: endpoint = %s" %self.heat_endpoint)
            self.heat = heatClient('1', endpoint=self.heat_endpoint, token=self.keystone.auth_token, **self.k_creds)
            self.reload_client = False

    def _private_ipcheck(self, url, type=None):
        # log.debug('url = %s' %str(url))

        url_dcp = str(copy.deepcopy(url))
        url_rp = url_dcp.replace('https://', '')

        if type == 'g':
            url_ip = url_rp.replace(':9292', '')
        elif type == 'n':
            url_ip = url_rp.replace(':9696', '')
        else:
            url_rp_dict = url_rp.split('/')
            url_ip = url_rp_dict[0].replace(':8004', '')

        # log.debug('url_ip = %s' %str(url_ip))

        a_url = url_ip.split('.')

        iparr = ['192', '172', '10']

        is_change_ip = False

        for ipa in iparr:
            if str(a_url[0]) != str(ipa):
                continue

            # log.debug('_private_ipcheck = %s' %str(ipa))
            is_change_ip = True
            break

        if is_change_ip:
            # log.debug('self.url = %s' % str(self.url))

            chg_url = copy.deepcopy(self.url)
            chg_url1 = chg_url.replace('https://', '').split('/')
            # log.debug('chg_url = %s' %str(chg_url1))

            chg_url2 = chg_url1[0].split(':')
            # log.debug('chg_url2 = %s' %str(chg_url2))

            url = url.replace(url_ip, chg_url2[0])

        # log.debug('url = %s' %str(url))

        return url


    def new_external_port(self, port_data):
        #TODO openstack if needed
        """
        Adds a external port to VIM
        Returns the port identifier
        """
        return -HTTP_Internal_Server_Error, "osconnector.new_external_port() not implemented" 


    def connect_port_network(self, port_id, network_id, admin=False):
        #TODO openstack if needed
        """
        Connects a external port to a network
        Returns status code of the VIM response
        """
        return -HTTP_Internal_Server_Error, "osconnector.connect_port_network() not implemented" 


    def new_user(self, user_name, user_passwd, tenant_id=None):
        """
        Adds a new user to openstack VIM
        Returns the user identifier
        """
        if self.debug:
            log.debug("osconnector: Adding a new user to VIM")
        try:
            self.reload_connection()
            user=self.keystone.users.create(user_name, user_passwd, tenant_id=tenant_id)
            #self.keystone.tenants.add_user(self.k_creds["username"], #role)
            return 1, user.id
        except ksExceptions.ConnectionError, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except ksExceptions.ClientException, e: #TODO remove
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("new_tenant %s" %error_text)
        return error_value, error_text


    def delete_user(self, user_id):
        """
        Delete a user from openstack VIM
        Returns the user identifier
        """
        if self.debug:
            log.debug("osconnector: Deleting  a  user from VIM")
        try:
            self.reload_connection()
            self.keystone.users.delete(user_id)
            return 1, user_id
        except ksExceptions.ConnectionError, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except ksExceptions.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except ksExceptions.ClientException, e: #TODO remove
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("delete_tenant %s" %error_text)
        return error_value, error_text

        
    def new_tenant(self,tenant_name,tenant_description):
        """
        Adds a new tenant to openstack VIM
        Returns the tenant identifier
        """
        if self.debug:
            log.debug("osconnector: Adding a new tenant to VIM")
        try:
            self.reload_connection()
            tenant=self.keystone.tenants.create(tenant_name, tenant_description)
            #self.keystone.tenants.add_user(self.k_creds["username"], #role)
            return 1, tenant.id
        except ksExceptions.ConnectionError, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except ksExceptions.ClientException, e: #TODO remove
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("new_tenant %s" %error_text)
        return error_value, error_text


    def delete_tenant(self,tenant_id):
        """
        Delete a tenant from openstack VIM
        Returns the tenant identifier
        """
        if self.debug:
            log.debug("osconnector: Deleting  a  tenant from VIM")
        try:
            self.reload_connection()
            self.keystone.tenants.delete(tenant_id)
            #self.keystone.tenants.add_user(self.k_creds["username"], #role)
            return 1, tenant_id
        except ksExceptions.ConnectionError, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except ksExceptions.ClientException, e: #TODO remove
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("delete_tenant %s" %error_text)
        return error_value, error_text


    def __net_os2mano(self, net_list_dict):
        """
        Transform the net openstack format to mano format
        net_list_dict can be a list of dict or a single dict
        """
        if type(net_list_dict) is dict:
            net_list_=(net_list_dict,)
        elif type(net_list_dict) is list:
            net_list_=net_list_dict
        else:
            raise TypeError("param net_list_dict must be a list or a dictionary")
        for net in net_list_:
            if net.get('provider:network_type') == "vlan":
                net['type']='data'
            else:
                net['type']='bridge'


    def new_tenant_network(self,net_name,net_type,public=False,cidr=None,vlan=None):
        """
        Adds a tenant network to VIM
        Returns the network identifier
        """
        if self.debug:
            log.debug("osconnector: Adding a new tenant network to VIM (tenant: %s, type: %s): %s" %(self.tenant, net_type, net_name))
        try:
            self.reload_connection()
            network_dict = {'name': net_name, 'admin_state_up': True}
            if net_type=="data" or net_type=="ptp":
                if self.config.get('network_vlan_ranges') is None:
                    return -HTTP_Bad_Request, "You must provide a 'network_vlan_ranges' at config value before creating sriov network "
                    
                network_dict["provider:physical_network"] = self.config['network_vlan_ranges'] #"physnet_sriov" #TODO physical
                network_dict["provider:network_type"]     = "vlan"
                if vlan is not None:
                    network_dict["provider:network_type"] = vlan
            network_dict["shared"]=public
            new_net=self.neutron.create_network({'network':network_dict})
            #create fake subnetwork
            if not cidr:
                cidr="192.168.111.0/24"
            subnet={"name":net_name+"-subnet",
                    "network_id": new_net["network"]["id"],
                    "ip_version": 4,
                    "cidr": cidr
                    }
            self.neutron.create_subnet({"subnet": subnet} )
            return 1, new_net["network"]["id"]
        #except neClient.exceptions.ConnectionFailed, e:
        except neExceptions.ConnectionFailed, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, neExceptions.NeutronException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("new_tenant_network %s" %error_text)
        return error_value, error_text


    def get_network_list(self, filter_dict={}):
        """
        Obtain tenant networks of VIM
        Filter_dict can be:
            name: network name
            id: network uuid
            shared: boolean
            tenant_id: tenant
            admin_state_up: boolean
            status: 'ACTIVE'
        Returns the network list of dictionaries
        """
        if self.debug:
            log.debug("osconnector.get_network_list(): Getting network from VIM (filter: %s)" %str(filter_dict))
        try:
            self.reload_connection()
            net_dict=self.neutron.list_networks(**filter_dict)
            net_list=net_dict["networks"]
            self.__net_os2mano(net_list)
            return 1, net_list
        except neExceptions.ConnectionFailed, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, neExceptions.NeutronException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("get_network_list %s" %error_text)
        return error_value, error_text


    def get_tenant_network(self, net_id, tenant_id=None):
        '''Obtain tenant networks of VIM'''
        '''Returns the network information from a network id'''
        if self.debug:
            log.debug("osconnector.get_tenant_network(): Getting tenant network %s from VIM" % net_id)
        filter_dict={"id": net_id}
        if tenant_id:
            filter_dict["tenant_id"] = tenant_id
        r, net_list = self.get_network_list(filter_dict)
        if r<0:
            return r, net_list
        if len(net_list)==0:
            return -HTTP_Not_Found, "Network '%s' not found" % net_id
        elif len(net_list)>1:
            return -HTTP_Conflict, "Found more than one network with this criteria"
        return 1, net_list[0]


    def delete_tenant_network(self, net_id):
        '''Deletes a tenant network from VIM'''
        '''Returns the network identifier'''
        if self.debug:
            log.debug("osconnector: Deleting a new tenant network from VIM tenant: %s, id: %s" %(self.tenant, net_id))
        try:
            self.reload_connection()
            #delete VM ports attached to this networks before the network
            ports = self.neutron.list_ports(network_id=net_id)
            for p in ports['ports']:
                try:
                    self.neutron.delete_port(p["id"])
                except Exception, e:
                    log.exception("Error deleting port: %s: %s" %(str(type(e))[6:-1], str(e)))
            self.neutron.delete_network(net_id)
            return 1, net_id
        except neExceptions.ConnectionFailed, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except neExceptions.NetworkNotFoundClient, e:
            error_value=-HTTP_Not_Found
            error_text= str(type(e))[6:-1] + ": "+  str(e.args[0])
        except (ksExceptions.ClientException, neExceptions.NeutronException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("delete_tenant_network %s" %error_text)
        return error_value, error_text


    def new_tenant_flavor(self, flavor_dict, change_name_if_used=True):
        """
        Adds a tenant flavor to openstack VIM
        if change_name_if_used is True, it will change name in case of conflict
        Returns the flavor identifier
        """
        retry=0
        name_suffix = 0
        name=flavor_dict['name']

        while retry < 2:
            retry += 1
            try:
                self.reload_connection()
                if change_name_if_used:
                    #get used names
                    fl_names=[]
                    fl=self.nova.flavors.list()
                    for f in fl:
                        fl_names.append(f.name)
                    while name in fl_names:
                        name_suffix += 1
                        name = flavor_dict['name']+"-" + str(name_suffix)
                        
                ram = flavor_dict.get('ram',64)
                vcpus = flavor_dict.get('vcpus',1)
                numa_properties=None

                extended=flavor_dict.get("extended")
                if extended:
                    numas=extended.get("numas")
                    if numas:
                        numa_nodes = len(numas)
                        if numa_nodes > 1:
                            return -1, "Can not add flavor with more than one numa"
                        numa_properties = {"hw:numa_nodes":str(numa_nodes)}
                        numa_properties["hw:mem_page_size"] = "large"
                        numa_properties["hw:cpu_policy"] = "dedicated"
                        numa_properties["hw:numa_mempolicy"] = "strict"
                        for numa in numas:
                            #overwrite ram and vcpus
                            ram = numa['memory']*1024
                            if 'paired-threads' in numa:
                                vcpus = numa['paired-threads']*2
                                numa_properties["hw:cpu_threads_policy"] = "prefer"
                            elif 'cores' in numa:
                                vcpus = numa['cores']
                                #numa_properties["hw:cpu_threads_policy"] = "prefer"
                            elif 'threads' in numa:
                                vcpus = numa['threads']
                                numa_properties["hw:cpu_policy"] = "isolated"
                #create flavor                 
                new_flavor=self.nova.flavors.create(name, 
                                ram, 
                                vcpus, 
                                flavor_dict.get('disk',1),
                                is_public=flavor_dict.get('is_public', True)
                            ) 
                #add metadata
                if numa_properties:
                    new_flavor.set_keys(numa_properties)
                return 1, new_flavor.id
            except nvExceptions.Conflict, e:
                error_value = -HTTP_Conflict
                error_text = str(e)
                if change_name_if_used:
                    continue
                break
            #except nvExceptions.BadRequest, e:
            except (ksExceptions.ClientException, nvExceptions.ClientException), e:
                error_value = -HTTP_Bad_Request
                error_text = str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                break
            except Exception, e:
                error_value = -HTTP_Internal_Server_Error
                error_text = "Unknown Error " + str(e)
                break
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("new_tenant_flavor %s" % error_text)
        return error_value, error_text


    def delete_tenant_flavor(self,flavor_id):
        """
            Deletes a tenant flavor from openstack VIM
            Returns >0,id if ok; or <0,error_text if error
        """
        retry = 0
        while retry < 2:
            retry += 1
            try:
                self.reload_connection()
                self.nova.flavors.delete(flavor_id)
                return 1, flavor_id
            except nvExceptions.NotFound, e:
                error_value = -HTTP_Not_Found
                error_text  = "flavor '%s' not found" % flavor_id
                break
            #except nvExceptions.BadRequest, e:
            except (ksExceptions.ClientException, nvExceptions.ClientException), e:
                error_value=-HTTP_Bad_Request
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                break
            except Exception, e:
                error_value = -HTTP_Internal_Server_Error
                error_text = "Unknown Error " + str(e)
                break
        if self.debug:
            log.debug("delete_tenant_flavor %s" %error_text)
        #if reaching here is because an exception
        return error_value, error_text


    def new_tenant_image(self,image_dict):
        """
        Adds a tenant image to VIM
        if change_name_if_used is True, it will change name in case of conflict
        Returns:
            >1, image-id        if the image is created
            <0, message          if there is an error
        """
        retry = 0
        #using version 1 of glance client
        glancev1 = gl1Client.Client('1',self.glance_endpoint, token=self.keystone.auth_token, **self.k_creds)  #TODO check k_creds vs n_creds

        while retry < 2:
            retry += 1
            try:
                self.reload_connection()
                #determine format  http://docs.openstack.org/developer/glance/formats.html
                if "disk_format" in image_dict:
                    disk_format=image_dict["disk_format"]
                else: #autodiscover base on extention
                    if image_dict['location'][-6:]==".qcow2":
                        disk_format="qcow2"
                    elif image_dict['location'][-4:]==".vhd":
                        disk_format="vhd"
                    elif image_dict['location'][-5:]==".vmdk":
                        disk_format="vmdk"
                    elif image_dict['location'][-4:]==".vdi":
                        disk_format="vdi"
                    elif image_dict['location'][-4:]==".iso":
                        disk_format="iso"
                    elif image_dict['location'][-4:]==".aki":
                        disk_format="aki"
                    elif image_dict['location'][-4:]==".ari":
                        disk_format="ari"
                    elif image_dict['location'][-4:]==".ami":
                        disk_format="ami"
                    else:
                        disk_format="raw"
                log.debug("new_tenant_image: '%s' loading from '%s'" % (image_dict['name'], image_dict['location']))
                if image_dict['location'][0:4]=="http":
                    new_image = glancev1.images.create(name=image_dict['name'], is_public=image_dict.get('public',"yes")=="yes",
                            container_format="bare", location=image_dict['location'], disk_format=disk_format)
                else: #local path
                    with open(image_dict['location']) as fimage:
                        new_image = glancev1.images.create(name=image_dict['name'], is_public=image_dict.get('public',"yes")=="yes",
                            container_format="bare", data=fimage, disk_format=disk_format)
                #insert metadata. We cannot use 'new_image.properties.setdefault' 
                #because nova and glance are "INDEPENDENT" and we are using nova for reading metadata
                new_image_nova=self.nova.images.find(id=new_image.id)
                new_image_nova.metadata.setdefault('location',image_dict['location'])
                metadata_to_load = image_dict.get('metadata')
                if metadata_to_load:
                    for k,v in metadata_to_load.iteritems():
                        new_image_nova.metadata.setdefault(k,v)
                return 1, new_image.id
            except nvExceptions.Conflict, e:
                error_value=-HTTP_Conflict
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                break
            except (HTTPException, gl1Exceptions.HTTPException, gl1Exceptions.CommunicationError), e:
                error_value=-HTTP_Bad_Request
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                continue
            except IOError, e:  #can not open the file
                error_value=-HTTP_Bad_Request
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                break
            except (ksExceptions.ClientException, nvExceptions.ClientException), e:
                error_value=-HTTP_Bad_Request
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                break
            except Exception, e:
                error_value = -HTTP_Internal_Server_Error
                error_text = "Unknown Error " + str(e)
                break
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("new_tenant_image %s" %error_text)
        return error_value, error_text

     
    def delete_tenant_image(self, image_id):
        """
        Deletes a tenant image from openstack VIM
        Returns >0,id if ok; or <0,error_text if error
        """
        retry = 0
        while retry < 2:

            retry += 1
            try:
                self.reload_connection()
                self.nova.images.delete(image_id)
                return 1, image_id
            except nvExceptions.NotFound, e:
                error_value = -HTTP_Not_Found
                error_text  = "flavor '%s' not found" % image_id
                break
            #except nvExceptions.BadRequest, e:
            except (ksExceptions.ClientException, nvExceptions.ClientException), e: #TODO remove
                error_value=-HTTP_Bad_Request
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                break
            except Exception, e:
                error_value = -HTTP_Internal_Server_Error
                error_text = "Unknown Error " + str(e)
                break
        if self.debug:
            log.debug("delete_tenant_image %s" % error_text)
        #if reaching here is because an exception
        return error_value, error_text


    def new_tenant_vminstance(self,name,description,start,image_id,flavor_id,net_list):
        """
        Adds a VM instance to VIM
        Params:
            start: indicates if VM must start or boot in pause mode. Ignored
            image_id,flavor_id: iamge and flavor uuid
            net_list: list of interfaces, each one is a dictionary with:
                name:
                net_id: network uuid to connect
                vpci: virtual vcpi to assign, ignored because openstack lack #TODO
                model: interface model, ignored #TODO
                mac_address: used for  SR-IOV ifaces #TODO for other types
                use: 'data', 'bridge',  'mgmt'
                type: 'virtio', 'PF', 'VF', 'VF not shared'
                vim_id: filled/added by this function
                #TODO ip, security groups
        Returns >=0, the instance identifier
                <0, error_text
        """
        if self.debug:
            log.debug("osconnector: Creating VM into VIM")
            log.debug("   image %s  flavor %s   nics=%s" %(image_id, flavor_id,net_list))
        try:
            net_list_vim=[]
            self.reload_connection()
            for net in net_list:
                if not net.get("net_id"): #skip non connected iface
                    continue
                if net["type"]=="virtio":
                    net_list_vim.append({'net-id': net["net_id"]})
                elif net["type"]=="PF":
                    log.debug("new_tenant_vminstance: Warning, can not connect a passthrough interface ")
                    #TODO insert this when openstack consider passthrough ports as openstack neutron ports
                else: #VF
                    port_dict={
                         "network_id": net["net_id"],
                         "name": net["name"],
                         "binding:vnic_type": "direct", 
                         "admin_state_up": True
                    }
                    if net.get("mac_address"):
                        port_dict["mac_address"]=net["mac_address"]
                    #TODO: manage having SRIOV without vlan tag
                    #if net["type"] == "VF not shared"
                    #    port_dict["vlan"]=0
                    new_port = self.neutron.create_port({"port": port_dict })
                    net["mac_adress"] = new_port["port"]["mac_address"]
                    net["vim_id"] = new_port["port"]["id"]
                    net["ip"] = new_port["port"].get("fixed_ips",[{}])[0].get("ip_address")
                    net_list_vim.append({"port-id": new_port["port"]["id"]})
            log.debug("name '%s' image_id '%s'flavor_id '%s' net_list_vim '%s' description '%s'"  % (name, image_id, flavor_id, str(net_list_vim), description))
            server = self.nova.servers.create(name, image_id, flavor_id, nics=net_list_vim) #, description=description)
            
            #TODO parse input and translate to VIM format (openmano_schemas.new_vminstance_response_schema)
            return 1, server.id
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        if self.debug:
            log.debug("get_tenant_vminstance Exception %s %s" %(str(e), error_text))
        return error_value, error_text    


    def get_tenant_vminstance(self,vm_id):
        """
        Returns the VM instance information from VIM
        """
        if self.debug:
            log.debug("osconnector: Getting VM from VIM")
        try:
            self.reload_connection()
            server = self.nova.servers.find(id=vm_id)
            #TODO parse input and translate to VIM format (openmano_schemas.new_vminstance_response_schema)
            return 1, {"server": server.to_dict()}
        except nvExceptions.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text= "vm instance %s not found" % vm_id
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("get_tenant_vminstance %s" %error_text)
        return error_value, error_text


    def delete_tenant_vminstance(self, vm_id):
        """
        Removes a VM instance from VIM
        Returns >0, the instance identifier
                <0, error_text
        """
        if self.debug:
            log.debug("osconnector: Getting VM from VIM")
        try:
            self.reload_connection()
            self.nova.servers.delete(vm_id)
            return 1, vm_id
        except nvExceptions.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text= (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("get_tenant_vminstance %s" %error_text)
        return error_value, error_text        


    def refresh_tenant_vms_and_nets(self, vmDict, netDict):
        """
        Refreshes the status of the dictionaries of VM instances and nets passed as arguments. It modifies the dictionaries
        Returns:
            - result: 0 if all elements could be refreshed (even if its status didn't change)
                      n>0, the number of elements that couldn't be refreshed,
                      <0 if error (foreseen)
            - error_msg: text with reference to possible errors
        """
        #vms_refreshed = []
        #nets_refreshed = []
        vms_unrefreshed = []
        nets_unrefreshed = []
        if self.debug:
            log.debug("osconnector refresh_tenant_vms and nets: Getting tenant VM instance information from VIM")
        for vm_id in vmDict:
            r,c = self.get_tenant_vminstance(vm_id)
            if r<0:
                log.error("osconnector refresh_tenant_vm. Error getting vm_id '%s' status: %s" % (vm_id, c))
                if r==-HTTP_Not_Found:
                    vmDict[vm_id] = "DELETED" #TODO check exit status
            else:
                try:
                    vmDict[vm_id] = vmStatus2manoFormat[ c['server']['status'] ]
                    #error message at server.fault["message"]
                except KeyError, e:
                    log.exception("osconnector refresh_tenant_elements KeyError %s getting vm_id '%s' status  %s" % (str(e), vm_id, c['server']['status']))
                    vms_unrefreshed.append(vm_id)
        
        for net_id in netDict:
            r,c = self.get_tenant_network(net_id)
            if r<0:
                log.error("osconnector refresh_tenant_network. Error getting net_id '%s' status: %s" % (net_id, c))
                if r==-HTTP_Not_Found:
                    netDict[net_id] = "DELETED" #TODO check exit status
                else:
                    nets_unrefreshed.append(net_id)
            else:
                try:
                    netDict[net_id] = netStatus2manoFormat[ c['status'] ]
                except KeyError, e:
                    log.exception("osconnector refresh_tenant_elements KeyError %s getting vm_id '%s' status  %s" % (str(e), vm_id, c['network']['status']))
                    nets_unrefreshed.append(net_id)
        
        error_msg=""
        if len(vms_unrefreshed)+len(nets_unrefreshed)>0:
            error_msg += "VMs unrefreshed: " + str(vms_unrefreshed) + "; nets unrefreshed: " + str(nets_unrefreshed)
            log.error(error_msg)

        return len(vms_unrefreshed)+len(nets_unrefreshed), error_msg


    def action_tenant_vminstance(self, vm_id, action_dict):
        """
        Send and action over a VM instance from VIM
        Returns the status
        """
        if self.debug:
            log.debug("osconnector: Action over VM instance from VIM %s" %str(vm_id))
        try:
            self.reload_connection()
            server = self.nova.servers.find(id=vm_id)
            if "start" in action_dict:
                if action_dict["start"]=="rebuild":  
                    server.rebuild()
                else:
                    if server.status=="PAUSED":
                        server.unpause()
                    elif server.status=="SUSPENDED":
                        server.resume()
                    elif server.status=="SHUTOFF":
                        server.start()
            elif "pause" in action_dict:
                server.pause()
            elif "resume" in action_dict:
                server.resume()
            elif "shutoff" in action_dict or "shutdown" in action_dict:
                server.stop()
            elif "forceOff" in action_dict:
                server.stop() #TODO
            elif "terminate" in action_dict:
                server.delete()
            elif "createImage" in action_dict:
                server.create_image()
                #"path":path_schema,
                #"description":description_schema,
                #"name":name_schema,
                #"metadata":metadata_schema,
                #"imageRef": id_schema,
                #"disk": {"oneOf":[{"type": "null"}, {"type":"string"}] },
            elif "rebuild" in action_dict:
                server.rebuild(server.image['id'])
            elif "reboot" in action_dict:
                server.reboot() #reboot_type='SOFT'
            return 1, vm_id
        except nvExceptions.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text= (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("action_tenant_vminstance %s" %error_text)
        return error_value, error_text        


    def get_hosts_info(self):
        """
        Get the information of deployed hosts
        Returns the hosts content
        """
        if self.debug:
            log.debug("osconnector: Getting Host info from VIM")
        try:
            h_list=[]
            self.reload_connection()
            hypervisors = self.nova.hypervisors.list()
            for hype in hypervisors:
                h_list.append( hype.to_dict() )
            return 1, {"hosts":h_list}
        except nvExceptions.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text= (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("get_hosts_info %s" %error_text)
        return error_value, error_text        


    def get_hosts(self, vim_tenant):
        """
        Get the hosts and deployed instances
        Returns the hosts content
        """
        r, hype_dict = self.get_hosts_info()
        if r<0:
            return r, hype_dict
        hypervisors = hype_dict["hosts"]
        try:
            servers = self.nova.servers.list()
            for hype in hypervisors:
                for server in servers:
                    if server.to_dict()['OS-EXT-SRV-ATTR:hypervisor_hostname']==hype['hypervisor_hostname']:
                        if 'vm' in hype:
                            hype['vm'].append(server.id)
                        else:
                            hype['vm'] = [server.id]
            return 1, hype_dict
        except nvExceptions.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text= (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("get_hosts %s" %error_text)
        return error_value, error_text        


    def get_image_id_from_path(self, path):
        """
        Get the image id from image path in the VIM database
        Returns:
             0,"Image not found"   if there are no images with that path
             1,image-id            if there is one image with that path
             <0,message            if there was an error (Image not found, error contacting VIM, more than 1 image with that path, etc.) 
        """
        try:
            self.reload_connection()
            images = self.nova.images.list()
            for image in images:
                if image.metadata.get("location")==path:
                    return 200, image.id
            return 0, "image with location '%s' not found" % path
        except (ksExceptions.ClientException, nvExceptions.ClientException), e: #TODO remove
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        if self.debug:
            log.debug("get_image_id_from_path %s" %error_text)
        #if reaching here is because an exception
        return error_value, error_text

    #hjc, v4 SBI
    def get_image_id_from_path_or_name(self, path, name):
        """
        Get the image id from image path in the VIM database
        Returns:
             0,"Image not found"   if there are no images with that path
             1,image-id            if there is one image with that path
             <0,message            if there was an error (Image not found, error contacting VIM, more than 1 image with that path, etc.) 
        """
        try:
            self.reload_connection()
            images = self.nova.images.list()
            for image in images:
                #log.debug("[HJC] image name = %s, image id = %s" %(image.name, image.id))
                if image.metadata.get("location")==path:
                    return 200, image.id
                elif image.name==name:
                    return 200, image.id
            return 0, "image with location '%s' not found" % path
        except (ksExceptions.ClientException, nvExceptions.ClientException), e: #TODO remove
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        if self.debug:
            log.debug("get_image_id_from_path_or_name %s" %error_text)
        #if reaching here is because an exception
        return error_value, error_text


    def new_virtual_provider_network_v4(self,net_name, net_type, physical_network_name, public=True, vlan=None, cidr=None, enable_dhcp=False):
        """
        Adds a virtual provider network to VIM
        Returns the network identifier
        """
        if self.debug:
            log.debug("osconnector: Adding a new virtual provider network to VIM (tenant: %s, type: %s): %s"  %(self.tenant, net_type, net_name))
        try:
            self.reload_connection()
            network_dict = {'name': net_name, 'admin_state_up': True}
            network_dict["provider:physical_network"] = physical_network_name
            network_dict["shared"]=public    
            if net_type=="vlan":
                network_dict["provider:network_type"]     = "vlan"
                if vlan is not None:
                    network_dict["provider:segmentation_id"] = vlan
            #log.debug("[HJC] new_virtual_provider_network_v4() arguments: %s" %str(network_dict))
            new_net=self.neutron.create_network({'network':network_dict})
            #create fake subnetwork
            try:
                if cidr:
                    subnet={"name":net_name+"-subnet",
                        "network_id": new_net["network"]["id"],
                        "ip_version": 4,
                        "cidr": cidr,
                        "enable_dhcp": enable_dhcp
                        }
                    self.neutron.create_subnet({"subnet": subnet} )
            except Exception, e:
                log.exception("Exception: [%s] %s" %(str(e), sys.exc_info()))
             
            return 200, new_net["network"]["id"]
        except neExceptions.ConnectionFailed, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, neExceptions.NeutronException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("new_virtual_provider_network_v4 %s" %error_text)
        return error_value, error_text


    def get_image_list_v4(self, filter_dict={}):
        """
        Gets image list from VIM
        Returns:
            1, ok signal        if the image is created
            <0, message          if there is an error
        """
        retry = 0
        while retry < 2:
            retry += 1
            try:
                self.reload_connection()
                #using version 1 of glance client
                #glancev1 = gl1Client.Client('1',self.glance_endpoint, token=self.keystone.auth_token, **self.k_creds)  #TODO check k_creds vs n_creds
                #image_list = glancev1.images.list()
                image_list = self.glance.images.list(**filter_dict)
                return 200, image_list
            except (HTTPException, gl1Exceptions.HTTPException, gl1Exceptions.CommunicationError), e:
                error_value=-HTTP_Bad_Request
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                continue
            except (ksExceptions.ClientException, nvExceptions.ClientException), e:
                error_value=-HTTP_Bad_Request
                error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
                break
            except Exception, e:
                error_value = -HTTP_Internal_Server_Error
                error_text = "Unknown Error " + str(e)
                break

        return error_value, error_text


    def get_network_list_v4(self, filter_dict={}):
        """
        Obtain tenant networks of VIM
        Filter_dict can be:
            name: network name
            id: network uuid
            shared: boolean
            tenant_id: tenant
            admin_state_up: boolean
            status: 'ACTIVE'
        Returns the network list of dictionaries
        """
        if self.debug:
            log.debug("osconnector.get_network_list(): Getting network from VIM (filter: %s)" %str(filter_dict))
        try:
            self.reload_connection()
            net_dict=self.neutron.list_networks(**filter_dict)
            
            net_list=net_dict["networks"]
            
            return 200, net_list
        except neExceptions.ConnectionFailed, e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except (ksExceptions.ClientException, neExceptions.NeutronException), e:
            error_value=-HTTP_Bad_Request
            error_text= str(type(e))[6:-1] + ": "+  (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        #TODO insert exception HTTP_Unauthorized
        #if reaching here is because an exception
        if self.debug:
            log.debug("get_network_list %s" %error_text)
        return error_value, error_text
    
    #hjc, heat SBI
    def check_connection(self):
        try:
            log.debug("[HJC] check a connection to VIM using Heat Get API")
            return self.get_heat_stacks()
        except Exception, e:
            return -HTTP_Internal_Server_Error, "Failed due to %s" %str(e)


    def get_heat_stacks(self):
        """
        Get the list of available HEAT stacks
        return stacks
        """
        if self.debug:
            log.debug("osconnector: Getting Stack List from VIM")
        try:
            stack_list=[]
            self.reload_connection()
            stacks = self.heat.stacks.list()
            for stack in stacks:
                stack_list.append(stack.to_dict())
            log.debug("Stack List: %s" %str(stack_list))
            return 200, {"stacks":stack_list}
        except heatException.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        if self.debug:
            log.debug("get_heat_stacks %s" %error_text)
        return error_value, error_text

    def new_heat_stack_v4(self, name, template_type, template, params=[]):
        """
        Create a new stack with name, template and parameters
        return stack id
        """
        try:
            template_data = template
            self.reload_connection()
            if template_type == 'hot_file':
                template_file = open(template, 'r')
                template_data = template_file.read()
            elif template_type == 'hot':
                template_data = template
            else:
                log.error("[Provisioning][NS]  HEAT: error invalid template type")
                #TODO: return ?
            
            param_dict={}
            for param in params:
                param_dict[param['name']]=param['value']

            # log.debug("stack_name = %s" % str(name))
            # log.debug("template_data = %s" % str(template_data))
            # log.debug("param_dict = %s" % str(param_dict))

            stack = self.heat.stacks.create(stack_name=name, template=template_data, parameters=param_dict)

            stack_uuid = stack['stack']['id']
            log.debug("[Provisioning][NS]  HEAT: stack uuid: %s" %stack_uuid)

            # wait for processing of heat
            stack = self.heat.stacks.get(stack_id=stack_uuid).to_dict()
            
            check_count = 0
            while stack['stack_status'] == 'CREATE_IN_PROGRESS':
                log.debug("[Provisioning][NS]  HEAT: Stack Status in Heat= %s" %str(stack['stack_status']))
                time.sleep(20)
                log.debug("[Provisioning][NS]  HEAT: new_heat_stack_v4() check %d th" %check_count)
                if check_count >= 60:
                    log.debug("[Provisioning][NS]  HEAT: new_heat_stack_v4() stop creating Heat Stack %d" %check_count)
                    break
                    
                try:
                    stack = self.heat.stacks.get(stack_id=stack_uuid).to_dict()
                except Exception, e:
                    log.exception("[Provisioning][NS]  HEAT: new_heat_stack_v4() failed to check heat stack status: %s" %str(e))
                
                check_count += 1
                
            if stack['stack_status'] == 'CREATE_COMPLETE':
                log.debug("[Provisioning][NS]  HEAT: Stack is successfully created.")
                return 200, stack_uuid
            else:
                log.error("[Provisioning][NS]  HEAT: Stack is under unknown status.")
                return -HTTP_Internal_Server_Error, stack['stack_status']
        except heatException.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except (heatException.BadRequest, heatException.CommandError), e:
            error_value=-HTTP_Internal_Server_Error
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except (heatException.HTTPInternalServerError, heatException.HTTPMethodNotAllowed), e:
            error_value=-HTTP_Internal_Server_Error
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except heatException.HTTPConflict, e:
            error_value=-HTTP_Conflict
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        if self.debug:
            log.error("[Provisioning][NS]  HEAT: new_heat_stack %s " %str(error_text))
        return error_value, error_text


    def get_heat_stack_statu_v4(self, stack_uuid):

        result, stack = self.get_heat_stack_id_v4(stack_uuid)
        if result < 0:
            return result, "Unknown"
        return 200, stack['stack_status']


    def delete_heat_stack_v4(self, stack_uuid, stack_name=None):
        """
        Delete the Stack identified by stack_uuid
        return deleted Stack's UUID
        """
        if self.debug:
            log.debug("[DELETE_HEAT_STACK_V4] HEAT: Deleting Stack from VIM")
        
        error_value = 200
        error_text = stack_uuid
        try:
            log.debug("[DELETE_HEAT_STACK_V4] stack_uuid = %s, stack_name =%s" %(stack_uuid, stack_name))
            self.reload_connection()
            
            if stack_name:
                log.debug("[DELETE_HEAT_STACK_V4] stack_name =%s" %(stack_name))
                self.heat.stacks.delete(stack_name)
            else:
                log.debug("[DELETE_HEAT_STACK_V4] stack_uuid =%s" %(stack_uuid))
                self.heat.stacks.delete(stack_uuid)
        except heatException.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value=-HTTP_Internal_Server_Error
            error_text="Unknown Error " + str(e)

        if error_value < 0 and stack_name:
            try:
                log.error("[DELETE_HEAT_STACK_V4] the first trial failed. Retry to delete Heat Stack: %d %s" %(error_value, error_text))
                time.sleep(10)
                self.reload_connection()
                self.heat.stacks.delete(stack_name)
            except heatException.NotFound, e:
                error_value=-HTTP_Not_Found
                error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
            except Exception, e:
                error_value=-HTTP_Internal_Server_Error
                error_text="Unknown Error " + str(e)
        
        if error_value < 0:
            log.error("[DELETE_HEAT_STACK_V4] failed to delete Heat Stack with name: %d %s" %(error_value, error_text))
            return error_value, error_text
        
        try:
            # wait for processing of heat
            stack = self.heat.stacks.get(stack_id=stack_uuid).to_dict()
            check_count = 0
            while True: 
                if type(stack) is str:
                    log.debug("[DELETE_HEAT_STACK_V4] heat stack get result type is not dict: %s" % str(stack))
                    break
                elif 'stack_status' not in stack:
                    log.debug("[DELETE_HEAT_STACK_V4] heat stack get result does not include stack_status: %s" % str(stack))
                    break
                elif stack['stack_status'] != 'DELETE_IN_PROGRESS':
                    log.debug("[DELETE_HEAT_STACK_V4] heat stack_status: %s" % str(stack['stack_status']))
                    break
                
                log.debug("[DELETE_HEAT_STACK_V4]  HEAT: Stack Status in Heat= %s" % str(stack['stack_status']))
                time.sleep(6)
                log.debug("[DELETE_HEAT_STACK_V4]  HEAT: check %d th" %check_count)
                if check_count >= 10:
                    log.debug("[DELETE_HEAT_STACK_V4]  HEAT: stop deleting Heat Stack %d" % check_count)
                    break
                    
                try:
                    stack = self.heat.stacks.get(stack_id=stack_uuid).to_dict()
                except Exception, e:
                    log.exception("[DELETE_HEAT_STACK_V4] : [%s] %s" %(str(e), sys.exc_info()))
                
                check_count += 1
                
            log.debug("[DELETE_HEAT_STACK_V4]  HEAT: Stack deleted.")
        
            return error_value, error_text
        
        except heatException.NotFound, e:
            error_value=200
            error_text=stack_uuid
        except Exception, e:
            error_value=-HTTP_Internal_Server_Error
            error_text="Unknown Error " + str(e)
            
        if self.debug:
            log.error("[DELETE_HEAT_STACK_V4] HEAT: delete_heat_stack error: %s" %str(error_text))
        return error_value, error_text


    def get_heat_resource_list_v4(self, stack_uuid):

        if self.debug:
            log.debug("                    HEAT: get stack resource info. from VIM")
        try:
            self.reload_connection()
            res_list = self.heat.resources.list(stack_uuid)
            
            return 200, res_list
        except heatException.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value=-HTTP_Internal_Server_Error
            error_text="Unknown Error " + str(e)
        if self.debug:
            log.error("                    HEAT: new_heat_stack error: %s"  %str(error_text))
        return error_value, error_text


    def get_heat_stack_id_v4(self, stack_uuid):

        if self.debug:
            log.debug("                    HEAT: get stack info. from VIM")

        try:
            self.reload_connection()
            stack_get = self.heat.stacks.get(stack_uuid).to_dict()
            return 200, stack_get
        except heatException.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value=-HTTP_Internal_Server_Error
            error_text="Unknown Error "+str(e)
        if self.debug:
            log.error("                    HEAT: error: %s" %str(error_text))
        return error_value, error_text


    def get_heat_stack_template_v4(self, stack_uuid):

        if self.debug:
            log.debug("                    HEAT: get stack template info. from VIM")

        try:
            self.reload_connection()

            stack_template = self.heat.stacks.template(stack_uuid)

            return 200, stack_template
        except heatException.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value=-HTTP_Internal_Server_Error
            error_text="Unknown Error "+str(e)
        if self.debug:
            log.error("                    HEAT: error: %s" %str(error_text))
        return error_value, error_text


    def get_server_vnc_url_v4(self, server_id, type='novnc'):

        try:
            self.reload_connection()
            server = self.nova.servers.get(server_id)
            r = server.get_vnc_console(type)
            log.debug("get_server_vnc_url() the result from VIM  = %s" %str(r))
            return 200, r
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value = -HTTP_Bad_Request
            error_text = str(e)
            log.error(str(e))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = str(e)
        
        return error_value, error_text


    def nova_test(self, server_id, type='SOFT'):
        try:
            log.debug('             nova_test >> server_id = %s' % str(server_id))

            self.reload_connection_novatest()
            server = self.nova.servers.get(server_id)
            log.debug('11111111111111111111')

            return 200, server

        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value = -HTTP_Bad_Request
            error_text = str(e)
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)

        return error_value, error_text


    def action_server_reboot(self, server_id, type='SOFT'):

        try:
            log.debug('             action_server_reboot >> server_id = %s' %str(server_id))

            self.reload_connection()
            server = self.nova.servers.get(server_id)
            log.debug('[action_server_reboot] server = %s' %str(server))
            
            r = server.reboot(type)
            log.debug("[ACTION_SERVER_REBOOT] the result from VIM = %s" %str(r))
            return 200, r
        
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value = -HTTP_Bad_Request
            error_text = str(e)
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)
        
        return error_value, error_text

    
    def action_server_stop(self, server_id):

        try:
            self.reload_connection()
            server = self.nova.servers.get(server_id)
            
            r = server.stop()
            log.debug("[ACTION_SERVER_STOP] the result from VIM = %s" %str(r))
            
            return 200, r
        
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value = -HTTP_Bad_Request
            error_text = str(e)
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)

        return error_value, error_text


    def action_server_start(self, server_id):

        try:
            self.reload_connection()
            server = self.nova.servers.get(server_id)
            r = server.start()
            log.debug("[ACTION_SERVER_START] the result from VIM = %s" % str(r))
            
            return 200, r
        
        except (ksExceptions.ClientException, nvExceptions.ClientException), e:
            error_value = -HTTP_Bad_Request
            error_text = str(e)
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Unknown Error " + str(e)

        return error_value, error_text


    def get_server_id(self, server_id):

        content = {}
        
        try:
            self.reload_connection()
            server = self.nova.servers.get(server_id)
            log.debug("[GET_SERVER_ID] the result from VIM = %s" % str(server))
            content['status'] = server.status
            content['updated'] = server.updated
            
            return 200, content
        except Exception, e:
            error_value = -HTTP_Bad_Request
            error_text = "Unknown Error " + str(e)
            return error_value, error_text


    def update_heat_stack_v4(self, name, stack_uuid, template_type, template, params=[]):
        """
        Update a stack with name, template and parameters
        return stack id
        """
        error_value, error_text = 0, None
        try:
            template_data = template
            self.reload_connection()

            if template_type == 'hot_file':
                template_file = open(template, 'r')
                template_data = template_file.read()
            elif template_type == 'hot':
                template_data = template
            else:
                log.error("[UPDATE_HEAT_STACK_V4]  HEAT: error invalid template type")
                #TODO: return ?

            param_dict={}
            for param in params:
                param_dict[param['name']]=param['value']

            log.debug('update_heat_stack_v4 > param_dict = %s' %str(param_dict))
            stack = self.heat.stacks.update(name, stack_name=name, template=template_data, parameters=param_dict)

            # wait for processing of heat
            time.sleep(2)

            check_count = 0
            while True:
                try:
                    stack = self.heat.stacks.get(stack_id=stack_uuid).to_dict()
                except Exception, e:
                    log.exception("[UPDATE_HEAT_STACK_V4]  HEAT: update_heat_stack_v4() failed to check heat stack status: %s" %str(e))

                log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: Stack Status in Heat= %s" %str(stack['stack_status']))
                if stack['stack_status'] == 'UPDATE_COMPLETE':
                    log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: Stack is successfully updated.")
                    return 200, stack_uuid
                elif stack['stack_status'] == 'UPDATE_FAILED':
                    log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: Stack is failed to update.")
                    return -500, stack_uuid
                else:
                    if check_count >= 30:
                        log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: update_heat_stack_v4() stop updating Heat Stack : limit count = %d" % check_count)
                        return -500, stack_uuid

                    time.sleep(30)
                    log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: update_heat_stack_v4() check %d th" % check_count)
                    check_count += 1

            # stack = self.heat.stacks.get(stack_id=stack_uuid).to_dict()
            # while stack['stack_status'] == 'UPDATE_IN_PROGRESS':
            #
            #     log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: Stack Status in Heat= %s" %str(stack['stack_status']))
            #     time.sleep(20)
            #     log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: update_heat_stack_v4() check %d th" %check_count)
            #     if check_count >= 20:
            #         log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: update_heat_stack_v4() stop updating Heat Stack %d" %check_count)
            #         break
            #
            #     try:
            #         stack = self.heat.stacks.get(stack_id=stack_uuid).to_dict()
            #     except Exception, e:
            #         log.exception("[UPDATE_HEAT_STACK_V4]  HEAT: update_heat_stack_v4() failed to check heat stack status: %s" %str(e))
            #
            #     check_count += 1
            # if stack['stack_status'] == 'UPDATE_COMPLETE':
            #     log.debug("[UPDATE_HEAT_STACK_V4]  HEAT: Stack is successfully updated.")
            #     return 200, stack_uuid
            # else:
            #     log.error("[UPDATE_HEAT_STACK_V4]  HEAT: Stack is under unknown status.")
            #     return -HTTP_Internal_Server_Error, stack['stack_status']

        except heatException.NotFound, e:
            error_value=-HTTP_Not_Found
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except (heatException.BadRequest, heatException.CommandError), e:
            error_value=-HTTP_Internal_Server_Error
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except (heatException.HTTPInternalServerError, heatException.HTTPMethodNotAllowed), e:
            error_value=-HTTP_Internal_Server_Error
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except heatException.HTTPConflict, e:
            error_value=-HTTP_Conflict
            error_text=str(type(e))[6:-1] + ": " + (str(e) if len(e.args)==0 else str(e.args[0]))
        except Exception, e:
            error_value = -HTTP_Internal_Server_Error
            error_text = "Exception : " + str(e)
        # if self.debug:
        #     log.error("[UPDATE_HEAT_STACK_V4]  HEAT: update_heat_stack %s " % str(error_text))
        return error_value, error_text


