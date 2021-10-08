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
One-Box Orchestrator DB engine. It implements all the methods to interact with the Orchestrator Database
'''
__author__="Jechan Han"
__date__ ="$30-oct-2015 10:05:01$"

#import MySQLdb as mdb
import psycopg2, psycopg2.extras
import json
import sys
import uuid as myUuid

from utils import auxiliary_functions as af
import utils.log_manager as log_manager
log = log_manager.LogManager.get_instance()

from utils.aes_chiper import AESCipher

HTTP_Bad_Request = 400
HTTP_Unauthorized = 401 
HTTP_Not_Found = 404 
HTTP_Method_Not_Allowed = 405 
HTTP_Request_Timeout = 408
HTTP_Conflict = 409
HTTP_Service_Unavailable = 503 
HTTP_Internal_Server_Error = 500 

class orch_db(object):
    def __init__(self, host, user, passwd, database, port):
        #initialization
        self.host = host
        self.user = user
        self.passwd = passwd
        self.database = database
        self.port = port
        self.con = None

    def connect(self):#, host=None, user=None, passwd=None, database=None, port=None):
        """
        Connect to specific data base.
        The first time a valid host, user, passwd and database must be provided,
        Following calls can skip this parameters
        """
        try:
            # if host     is not None: self.host = host
            # if user     is not None: self.user = user
            # if passwd   is not None: self.passwd = passwd
            # if database is not None: self.database = database
            # if port     is not None: self.port = port

            self.con = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
            return 0
        except psycopg2.Error, e:
            log.exception("nfvo_db.connect Error connecting to DB %s@%s:%s -> %s Error %d: %s" % (self.user, self.host, self.port, self.database, e.args[0], e.args[1]))
            return -1
        except Exception, e:
            log.error("Failed to connect DB : %s" % str(e))
            return -1
        
    def get_db_version(self):
        ''' Obtain the database schema version.
        Return: (negative, text) if error or version 0.0 where schema_version table is missing
                (version_int, version_text) if ok
        '''
        cmd = "SELECT version_int,version,openmano_ver FROM schema_version"
        for retry_ in range(0,2):
            try:
                with self.con:
                    self.cur = self.con.cursor()
                    self.cur.execute(cmd)
                    rows = self.cur.fetchall()
                    highest_version_int=0
                    highest_version=""
                    for row in rows: #look for the latest version
                        if row[0]>highest_version_int:
                            highest_version_int, highest_version = row[0:2]
                    return highest_version_int, highest_version
            except (psycopg2.Error, AttributeError), e:
                log.exception("get_db_version DB Exception %d: %s" % (e.args[0], e.args[1]))
                r,c = self.format_error(e)
                if r!=-HTTP_Request_Timeout or retry_==1: return r,c

    def disconnect(self):
        '''disconnect from specific data base'''
        try:
            self.con.close()
            del self.con
        except psycopg2.Error, e:
            log.exception("Error disconnecting from DB: Error %d: %s" % (e.args[0], e.args[1]))
            return -1
        except AttributeError, e: #self.con not defined
            if e[0][-5:] == "'con'": return -1, "Database internal error, no connection."
            else: raise

    def format_error(self, e, command=None, extra=None):
        if type(e[0]) is str:
            if e[0][-5:] == "'con'": return -HTTP_Internal_Server_Error, "DB Exception, no connection."
            else: raise
        if e.args[0]==2006 or e.args[0]==2013 : #MySQL server has gone away (((or)))    Exception 2013: Lost connection to MySQL server during query
            #reconnect
            self.connect()
            return -HTTP_Request_Timeout,"Database reconnection. Try Again"

        fk=e.args[1].find("foreign key constraint fails")
        if fk>=0:
            if command=="update": return -HTTP_Bad_Request, "tenant_id %s not found." % extra
            elif command=="delete":  return -HTTP_Bad_Request, "Resource is not free. There are %s that prevent deleting it." % extra
        de = e.args[1].find("Duplicate entry")
        fk = e.args[1].find("for key")
        uk = e.args[1].find("Unknown column")
        wc = e.args[1].find("in 'where clause'")
        fl = e.args[1].find("in 'field list'")
        if de>=0:
            if fk>=0: #error 1062
                return -HTTP_Conflict, "Value %s already in use for %s" % (e.args[1][de+15:fk], e.args[1][fk+7:])
        if uk>=0:
            if wc>=0:
                return -HTTP_Bad_Request, "Field %s can not be used for filtering" % e.args[1][uk+14:wc]
            if fl>=0:
                return -HTTP_Bad_Request, "Field %s does not exist" % e.args[1][uk+14:wc]
        return -HTTP_Internal_Server_Error, "Database internal Error %d: %s" % (e.args[0], e.args[1])

    def __remove_quotes(self, data):
        '''remove single quotes ' of any string content of data dictionary'''
        for k,v in data.items():
            if type(v) == str:
                if "'" in v:
                    data[k] = data[k].replace("'","_")


    def __update_rows_free(self, cur, cmd, db_log=False):
        ''' Update one or several rows into a table.
        Atributes
            UPDATE: dictionary with the key: value to change
            table: table where to update
            WHERE: dictionary of elements to update
        Return: (result, descriptive text) where result indicates the number of updated files, negative if error
        '''
        # self.__remove_quotes(UPDATE)
        #         #gettting uuid
        # uuid = WHERE['uuid'] if 'uuid' in WHERE else None
        #
        # cmd= "UPDATE " + table +" SET " + \
        #     ",".join(map(lambda x: str(x)+ ('=Null' if UPDATE[x] is None else "='"+ str(UPDATE[x]) +"'"  ),   UPDATE.keys() )) + \
        #     " WHERE " + " and ".join(map(lambda x: str(x)+ (' is Null' if WHERE[x] is None else"='"+str(WHERE[x])+"'" ),  WHERE.keys() ))
        cur.execute(cmd)
        nb_rows = cur.rowcount
        if nb_rows > 0 and db_log:
            log.debug("__update_rows(): nb_rows = %d" %nb_rows)
        # return nb_rows, "%d updated from %s" % (nb_rows, table[:-1] )
        return nb_rows, "%d %s" % (nb_rows, cmd)


    def __update_rows_kt(self, cur, table, UPDATE, WHERE, db_log=False):
        ''' Update one or several rows into a table.
        Atributes
            UPDATE: dictionary with the key: value to change
            table: table where to update
            WHERE: dictionary of elements to update
        Return: (result, descriptive text) where result indicates the number of updated files, negative if error
        '''
        self.__remove_quotes(UPDATE)
                #gettting uuid
        uuid = WHERE['uuid'] if 'uuid' in WHERE else None

        cmd= "UPDATE " + table +" SET " + \
            ",".join(map(lambda x: str(x)+ ('=Null' if UPDATE[x] is None else "='"+ str(UPDATE[x]) +"'"  ),   UPDATE.keys() )) + \
            " WHERE " + " and ".join(map(lambda x: str(x)+ (' is Null' if WHERE[x] is None else"='"+str(WHERE[x])+"'" ),  WHERE.keys() ))
        cur.execute(cmd)
        nb_rows = cur.rowcount
        if nb_rows > 0 and db_log:
            log.debug("__update_rows(): nb_rows = %d" %nb_rows)
        return nb_rows, "%d updated from %s" % (nb_rows, table[:-1] )

    def __update_rows(self, table, UPDATE, WHERE, log=False):
        ''' Update one or several rows into a table.
        Atributes
            UPDATE: dictionary with the key: value to change
            table: table where to update
            WHERE: dictionary of elements to update
        Return: (result, descriptive text) where result indicates the number of updated files, negative if error
        '''
        self.__remove_quotes(UPDATE)
                #gettting uuid
        uuid = WHERE['uuid'] if 'uuid' in WHERE else None

        cmd= "UPDATE " + table +" SET " + \
            ",".join(map(lambda x: str(x)+ ('=Null' if UPDATE[x] is None else "='"+ str(UPDATE[x]) +"'"  ),   UPDATE.keys() )) + \
            " WHERE " + " and ".join(map(lambda x: str(x)+ (' is Null' if WHERE[x] is None else"='"+str(WHERE[x])+"'" ),  WHERE.keys() ))
        self.cur.execute(cmd)
        nb_rows = self.cur.rowcount
        if nb_rows > 0 and log:
            #inserting new log
            if uuid is None: uuid_k = uuid_v = ""
            else: uuid_k=",uuid"; uuid_v=",'" + str(uuid) + "'"
            cmd = "INSERT INTO logs (related,level%s,description) VALUES ('%s','debug'%s,\"updating %d entry %s\")" \
                % (uuid_k, table, uuid_v, nb_rows, (str(UPDATE)).replace('"','-')  )
            self.cur.execute(cmd)

        return nb_rows, "%d updated from %s" % (nb_rows, table[:-1] )

    def _new_row_internal_seq(self, cur, table, INSERT, db_log=False, last_val=True):
        ''' Add one row into a table. It DOES NOT begin or end the transaction, so self.con.cursor must be created
        Attribute
            INSERT: dictionary with the key: value to insert
            table: table where to insert
            tenant_id: only useful for logs. If provided, logs will use this tenant_id
            add_uuid: if True, it will create an uuid key entry at INSERT if not provided
        It checks presence of uuid and add one automatically otherwise
        Return: (result, uuid) where result can be 0 if error, or 1 if ok
        '''
        #insertion
        cmd= "INSERT INTO " + table +" (" + \
            ",".join(map(str, INSERT.keys() ))   + ") VALUES(" + \
            ",".join(map(lambda x: 'Null' if x is None else "'"+str(x)+"'", INSERT.values() )) + ")"
        if db_log:
            log.debug("_new_row_internal_seq(): %s" %cmd)
        cur.execute(cmd)
        nb_rows = cur.rowcount

        seq = 0

        if last_val and table != 'TB_VIMTypeCode':
            cur.execute('SELECT LASTVAL()')
            seq = cur.fetchone()[0]

        if db_log:
            log.debug("_new_row_internal_seq(): nb_rows = %d, seq = %d" %(nb_rows, seq))

        return nb_rows, seq

    def _new_row_internal_seq_wo(self, cur, table, INSERT, db_log=False):
        ''' Add one row into a table. It DOES NOT begin or end the transaction, so self.con.cursor must be created
        Attribute
            INSERT: dictionary with the key: value to insert
            table: table where to insert
            tenant_id: only useful for logs. If provided, logs will use this tenant_id
            add_uuid: if True, it will create an uuid key entry at INSERT if not provided
        It checks presence of uuid and add one automatically otherwise
        Return: (result, uuid) where result can be 0 if error, or 1 if ok
        '''
        #insertion
        cmd= "INSERT INTO " + table +" (" + \
            ",".join(map(str, INSERT.keys() ))   + ") VALUES(" + \
            ",".join(map(lambda x: 'Null' if x is None else "'"+str(x)+"'", INSERT.values() )) + ")"
        if db_log:
            log.debug("_new_row_internal_seq(): %s" %cmd)
        cur.execute(cmd)
        nb_rows = cur.rowcount

        seq = 0

        return nb_rows, seq

    def _new_row_internal_kt(self, cur, table, INSERT, tenant_id=None, add_uuid=False, root_uuid=None, log=False):
        ''' Add one row into a table. It DOES NOT begin or end the transaction, so self.con.cursor must be created
        Attribute
            INSERT: dictionary with the key: value to insert
            table: table where to insert
            tenant_id: only useful for logs. If provided, logs will use this tenant_id
            add_uuid: if True, it will create an uuid key entry at INSERT if not provided
        It checks presence of uuid and add one automatically otherwise
        Return: (result, uuid) where result can be 0 if error, or 1 if ok
        '''

        if add_uuid:
            #create uuid if not provided
            if 'uuid' not in INSERT:
                uuid = INSERT['uuid'] = str(myUuid.uuid1()) # create_uuid
            else:
                uuid = str(INSERT['uuid'])
        else:
            uuid=None
        if add_uuid:
            #defining root_uuid if not provided
            if root_uuid is None:
                root_uuid = uuid
            #inserting new uuid
            cmd = "INSERT INTO uuids (uuid, root_uuid, used_at) VALUES ('%s','%s','%s')" % (uuid, root_uuid, table)
            cur.execute(cmd)
        #insertion
        cmd= "INSERT INTO " + table +" (" + \
            ",".join(map(str, INSERT.keys() ))   + ") VALUES(" + \
            ",".join(map(lambda x: 'Null' if x is None else "'"+str(x)+"'", INSERT.values() )) + ")"
        cur.execute(cmd)
        nb_rows = cur.rowcount
        #inserting new log
        if nb_rows > 0 and log:
            if add_uuid: del INSERT['uuid']
            if uuid is None: uuid_k = uuid_v = ""
            else: uuid_k=",uuid"; uuid_v=",'" + str(uuid) + "'"
            if tenant_id is None: tenant_k = tenant_v = ""
            else: tenant_k=",nfvo_tenant_id"; tenant_v=",'" + str(tenant_id) + "'"
            cmd = "INSERT INTO logs (related,level%s%s,description) VALUES ('%s','debug'%s%s,\"new %s %s\")" \
                % (uuid_k, tenant_k, table, uuid_v, tenant_v, table[:-1], str(INSERT).replace('"','-'))
            cur.execute(cmd)
        return nb_rows, uuid

    def _new_row_internal(self, table, INSERT, tenant_id=None, add_uuid=False, root_uuid=None, log=False):
        ''' Add one row into a table. It DOES NOT begin or end the transaction, so self.con.cursor must be created
        Attribute
            INSERT: dictionary with the key: value to insert
            table: table where to insert
            tenant_id: only useful for logs. If provided, logs will use this tenant_id
            add_uuid: if True, it will create an uuid key entry at INSERT if not provided
        It checks presence of uuid and add one automatically otherwise
        Return: (result, uuid) where result can be 0 if error, or 1 if ok
        '''

        if add_uuid:
            #create uuid if not provided
            if 'uuid' not in INSERT:
                uuid = INSERT['uuid'] = str(myUuid.uuid1()) # create_uuid
            else:
                uuid = str(INSERT['uuid'])
        else:
            uuid=None
        if add_uuid:
            #defining root_uuid if not provided
            if root_uuid is None:
                root_uuid = uuid
            #inserting new uuid
            cmd = "INSERT INTO uuids (uuid, root_uuid, used_at) VALUES ('%s','%s','%s')" % (uuid, root_uuid, table)
            self.cur.execute(cmd)
        #insertion
        cmd= "INSERT INTO " + table +" (" + \
            ",".join(map(str, INSERT.keys() ))   + ") VALUES(" + \
            ",".join(map(lambda x: 'Null' if x is None else "'"+str(x)+"'", INSERT.values() )) + ")"
        self.cur.execute(cmd)
        nb_rows = self.cur.rowcount
        #inserting new log
        if nb_rows > 0 and log:
            if add_uuid: del INSERT['uuid']
            if uuid is None: uuid_k = uuid_v = ""
            else: uuid_k=",uuid"; uuid_v=",'" + str(uuid) + "'"
            if tenant_id is None: tenant_k = tenant_v = ""
            else: tenant_k=",nfvo_tenant_id"; tenant_v=",'" + str(tenant_id) + "'"
            cmd = "INSERT INTO logs (related,level%s%s,description) VALUES ('%s','debug'%s%s,\"new %s %s\")" \
                % (uuid_k, tenant_k, table, uuid_v, tenant_v, table[:-1], str(INSERT).replace('"','-'))
            self.cur.execute(cmd)
        return nb_rows, uuid

    def __get_rows(self,table,uuid):
        self.cur.execute("SELECT * FROM " + str(table) +" where uuid='" + str(uuid) + "'")
        rows = self.cur.fetchall()
        return self.cur.rowcount, rows

    def new_row(self, table, INSERT, tenant_id=None, add_uuid=False, log=False, last_val=True):
        ''' Add one row into a table.
        Attribute
            INSERT: dictionary with the key: value to insert
            table: table where to insert
            tenant_id: only useful for logs. If provided, logs will use this tenant_id
            add_uuid: if True, it will create an uuid key entry at INSERT if not provided
        It checks presence of uuid and add one automatically otherwise
        Return: (result, uuid) where result can be 0 if error, or 1 if ok
        '''

        self._encrypt_passwd(table, INSERT)

        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor()
                #return self._new_row_internal(table, INSERT, tenant_id, add_uuid, None, log)
                if add_uuid:
                    result, content = self._new_row_internal_kt(cur, table, INSERT, tenant_id, add_uuid, None, log)
                else:
                    if last_val:
                        result, content = self._new_row_internal_seq(cur, table, INSERT, log, last_val=last_val)
                    else:
                        result, content = self._new_row_internal_seq(cur, table, INSERT, log, last_val=last_val)

                return result, content

            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def new_row_seq(self, table, INSERT, tenant_id=None, add_uuid=False, log=False):
        ''' Add one row into a table.
        Attribute
            INSERT: dictionary with the key: value to insert
            table: table where to insert
            tenant_id: only useful for logs. If provided, logs will use this tenant_id
            add_uuid: if True, it will create an uuid key entry at INSERT if not provided
        It checks presence of uuid and add one automatically otherwise
        Return: (result, uuid) where result can be 0 if error, or 1 if ok
        '''
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor()

                result, content = self._new_row_internal_seq_wo(cur, table, INSERT, log)

                return result, content

            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def update_rows(self, table, UPDATE, WHERE, log=False, _free=False):
        ''' Update one or several rows into a table.
        Atributes
            UPDATE: dictionary with the key: value to change
            table: table where to update
            WHERE: dictionary of elements to update
        Return: (result, descriptive text) where result indicates the number of updated files
        '''

        self._encrypt_passwd(table, UPDATE)

        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor()
                #return self.__update_rows(table, UPDATE, WHERE, log)

                if _free:
                    # free query : table == sql
                    result, content = self.__update_rows_free(cur, cmd=table)
                else:
                    result, content = self.__update_rows_kt(cur, table, UPDATE, WHERE, log)
                return result, content

            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def delete_row_seq(self, table, seq_name, seq_value, tenant_id=None, db_log=False):
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                #delete host
                cur = conn.cursor()
                if type(seq_value) is not str:
                    seq_value = str(seq_value)

                cmd = "DELETE FROM %s WHERE %s = '%s'" % (table, seq_name, seq_value)
                cur.execute(cmd)
                deleted = cur.rowcount

                cur.close()
                conn.close()
                return deleted, (str(seq_value) if deleted==1 else "not found")
            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def delete_row(self, table, uuid, tenant_id=None, log=False):
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                #delete host
                cur = conn.cursor()
                cmd = "DELETE FROM %s WHERE uuid = '%s'" % (table, uuid)
                cur.execute(cmd)
                deleted = cur.rowcount

                cur.close()

                if deleted == 1:
                    #delete uuid
                    if table == 'tenants': tenant_str=uuid
                    elif tenant_id:
                        tenant_str = tenant_id
                    else:
                        tenant_str = 'Null'
                    cur = conn.cursor()
                    cmd = "DELETE FROM uuids WHERE root_uuid = '%s'" % uuid
                    cur.execute(cmd)
                    #inserting new log
                    if log:
                        cmd = "INSERT INTO logs (related,level,uuid,nfvo_tenant_id,description) VALUES ('%s','debug','%s','%s','delete %s')" % (table, uuid, tenant_str, table[:-1])
                        cur.execute(cmd)
                    cur.close()
                return deleted, table[:-1] + " '%s' %s" %(uuid, "deleted" if deleted==1 else "not found")
            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)

            finally:
                if cur: cur.close()
                if conn: conn.close()

    def delete_old_rows(self, table, interval_days, where_dict=None, tenant_id=None, log=False):
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                #delete host
                cur = conn.cursor()
                cmd = "DELETE FROM %s WHERE reg_dttm < now() - interval '%d days'" % (table, interval_days)
                #if where_dict is not None:
                #    cmd = cmd + " AND ".join(map( lambda x: str(x) + (" is Null" if where_dict[x] is None else "='"+str(where_dict[x])+"'"),  where_dict.keys()) )
                cur.execute(cmd)
                deleted = cur.rowcount

                return deleted, table[:-1] + " %s" %("deleted" if deleted==1 else "not found")
            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def delete_row_by_dict(self, **sql_dict):
        ''' Deletes rows from a table.
        Attribute sql_dir: dictionary with the following key: value
            'FROM': string of table name (Mandatory)
            'WHERE': dict of key:values, translated to key=value AND ... (Optional)
            'WHERE_NOT': dict of key:values, translated to key<>value AND ... (Optional)
            'WHERE_NOTNULL': (list or tuple of items that must not be null in a where ... (Optional)
            'LIMIT': limit of number of rows (Optional)
        Return: the (number of items deleted, descriptive test) if ok; (negative, descriptive text) if error
        '''
        from_  = "FROM " + str(sql_dict['FROM'])
        if 'WHERE' in sql_dict and len(sql_dict['WHERE']) > 0:
            w=sql_dict['WHERE']
            where_ = "WHERE " + " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else "='"+str(w[x])+"'"),  w.keys()) )
        else: where_ = ""

        if 'LIKE' in sql_dict and len(sql_dict['LIKE']) > 0:
            w=sql_dict['LIKE']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else " LIKE '"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2

        if 'WHERE_NOT' in sql_dict and len(sql_dict['WHERE_NOT']) > 0:
            w=sql_dict['WHERE_NOT']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is not Null" if w[x] is None else "<>'"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2
        if 'WHERE_NOTNULL' in sql_dict and len(sql_dict['WHERE_NOTNULL']) > 0:
            w=sql_dict['WHERE_NOTNULL']
            where_2 = " AND ".join(map( lambda x: str(x) + " is not Null",  w) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2
        limit_ = "LIMIT " + str(sql_dict['LIMIT']) if 'LIMIT' in sql_dict else ""
        cmd =  " ".join( ("DELETE", from_, where_, limit_) )
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                #delete host
                cur = conn.cursor()
                cur.execute(cmd)
                deleted = cur.rowcount
                return deleted, "%d deleted from %s" % (deleted, sql_dict['FROM'][:-1] )
            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                log.exception("nfvo_db.delete_row DB Exception %s" % str(e))
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)

            finally:
                if cur: cur.close()
                if conn: conn.close()

    def get_rows(self,table,uuid):
        '''get row from a table based on uuid'''
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("SELECT * FROM " + str(table) +" where uuid='" + str(uuid) + "'")
                rows = cur.fetchall()
                result = cur.rowcount
                return result, rows
            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                log.exception("nfvo_db.delete_row DB Exception %s" % str(e))
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def get_table(self, **sql_dict):
        ''' Obtain rows from a table.
        Attribute sql_dir: dictionary with the following key: value
            'SELECT': (list or tuple of fields to retrieve) (by default all)
            'FROM': string of table name (Mandatory)
            'WHERE': dict of key:values, translated to key=value AND ... (Optional)
            'WHERE_NOT': dict of key:values, translated to key<>value AND ... (Optional)
            'WHERE_NOTNULL': (list or tuple of items that must not be null in a where ... (Optional)
            'LIMIT': limit of number of rows (Optional)
        Return: a list with dictionaries at each row
        '''
        select_= "SELECT " + ("*" if 'SELECT' not in sql_dict else ",".join(map(str,sql_dict['SELECT'])) )
        from_  = "FROM " + str(sql_dict['FROM'])
        order_ = "ORDER BY " + str(sql_dict['ORDER']) if 'ORDER' in sql_dict else ""

        if 'WHERE' in sql_dict and len(sql_dict['WHERE']) > 0:
            w=sql_dict['WHERE']
            where_ = "WHERE " + " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else "='"+str(w[x])+"'"),  w.keys()) )
        else:
            where_ = ""

        if 'LIKE' in sql_dict and len(sql_dict['LIKE']) > 0:
            w=sql_dict['LIKE']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else " LIKE '"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2

        if 'WHERE_NOT' in sql_dict and len(sql_dict['WHERE_NOT']) > 0:
            w=sql_dict['WHERE_NOT']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is not Null" if w[x] is None else "<>'"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2

        if 'WHERE_NOTNULL' in sql_dict and len(sql_dict['WHERE_NOTNULL']) > 0:
            w=sql_dict['WHERE_NOTNULL']
            where_2 = " AND ".join(map( lambda x: str(x) + " is not Null",  w) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2
        limit_ = "LIMIT " + str(sql_dict['LIMIT']) if 'LIMIT' in sql_dict else ""
        cmd =  " ".join( (select_, from_, where_, order_, limit_) )

        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(cmd)
                rows = cur.fetchall()

                result = cur.rowcount
                if result > 0:
                    self._decrypt_passwd(sql_dict['FROM'], rows)

                return result, rows

            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                log.exception("nfvo_db.get_table DB Exception %s" % str(e))
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def get_table_free(self, **sql_dict):
        ''' Obtain rows from a table.
        Attribute sql_dir: dictionary with the following key: value
            'SELECT': (list or tuple of fields to retrieve) (by default all)
            'FROM': string of table name (Mandatory)
            'WHERE': dict of key:values, translated to key=value AND ... (Optional)
            'WHERE_NOT': dict of key:values, translated to key<>value AND ... (Optional)
            'WHERE_NOTNULL': (list or tuple of items that must not be null in a where ... (Optional)
            'LIMIT': limit of number of rows (Optional)
        Return: a list with dictionaries at each row
        '''
        select_= "SELECT " + ("*" if 'SELECT' not in sql_dict else ",".join(map(str,sql_dict['SELECT'])) )
        from_  = "FROM " + str(sql_dict['FROM'])
        order_ = "ORDER BY " + str(sql_dict['ORDER']) if 'ORDER' in sql_dict else ""
        if 'WHERE' in sql_dict and len(sql_dict['WHERE']) > 0:
            w=sql_dict['WHERE']
            where_ = "WHERE " + " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else "='"+str(w[x])+"'"),  w.keys()) )
        else:
            where_ = ""

        if 'WHERE_FREE' in sql_dict:
            if len(where_)==0:   where_ = "WHERE " + str(sql_dict['WHERE_FREE'])
            else:                where_ = where_ + " AND " + str(sql_dict['WHERE_FREE'])

        if 'LIKE' in sql_dict and len(sql_dict['LIKE']) > 0:
            w=sql_dict['LIKE']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else " LIKE '"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2

        if 'WHERE_NOT' in sql_dict and len(sql_dict['WHERE_NOT']) > 0:
            w=sql_dict['WHERE_NOT']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is not Null" if w[x] is None else "<>'"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2

        if 'WHERE_NOTNULL' in sql_dict and len(sql_dict['WHERE_NOTNULL']) > 0:
            w=sql_dict['WHERE_NOTNULL']
            where_2 = " AND ".join(map( lambda x: str(x) + " is not Null",  w) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2
        limit_ = "LIMIT " + str(sql_dict['LIMIT']) if 'LIMIT' in sql_dict else ""
        cmd =  " ".join( (select_, from_, where_, order_, limit_) )
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(cmd)
                rows = cur.fetchall()

                result = cur.rowcount
                if result > 0:
                    self._decrypt_passwd(sql_dict['FROM'], rows)

                return result, rows

            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                log.exception("nfvo_db.get_table DB Exception %s" % str(e))
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def get_table_group(self, **sql_dict):
        ''' Obtain rows from a table.
        Attribute sql_dir: dictionary with the following key: value
            'SELECT': (list or tuple of fields to retrieve) (by default all)
            'FROM': string of table name (Mandatory)
            'WHERE': dict of key:values, translated to key=value AND ... (Optional)
            'WHERE_NOT': dict of key:values, translated to key<>value AND ... (Optional)
            'WHERE_NOTNULL': (list or tuple of items that must not be null in a where ... (Optional)
            'LIMIT': limit of number of rows (Optional)
        Return: a list with dictionaries at each row
        '''
        select_= "SELECT " + ("*" if 'SELECT' not in sql_dict else ",".join(map(str,sql_dict['SELECT'])) )
        from_  = "FROM " + str(sql_dict['FROM'])

        # [BBG] group by 추가 : 20.02.18
        group_ = "GROUP BY " + str(sql_dict['GROUP']) if 'GROUP' in sql_dict else ""

        order_ = "ORDER BY " + str(sql_dict['ORDER']) if 'ORDER' in sql_dict else ""
        if 'WHERE' in sql_dict and len(sql_dict['WHERE']) > 0:
            w=sql_dict['WHERE']
            where_ = "WHERE " + " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else "='"+str(w[x])+"'"),  w.keys()) )
        else:
            where_ = ""

        if 'LIKE' in sql_dict and len(sql_dict['LIKE']) > 0:
            w=sql_dict['LIKE']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is Null" if w[x] is None else " LIKE '"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2

        if 'WHERE_NOT' in sql_dict and len(sql_dict['WHERE_NOT']) > 0:
            w=sql_dict['WHERE_NOT']
            where_2 = " AND ".join(map( lambda x: str(x) + (" is not Null" if w[x] is None else "<>'"+str(w[x])+"'"),  w.keys()) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2

        if 'WHERE_NOTNULL' in sql_dict and len(sql_dict['WHERE_NOTNULL']) > 0:
            w=sql_dict['WHERE_NOTNULL']
            where_2 = " AND ".join(map( lambda x: str(x) + " is not Null",  w) )
            if len(where_)==0:   where_ = "WHERE " + where_2
            else:                where_ = where_ + " AND " + where_2
        limit_ = "LIMIT " + str(sql_dict['LIMIT']) if 'LIMIT' in sql_dict else ""

        # 원본
        # cmd =  " ".join( (select_, from_, where_, order_, limit_) )

        # 수정 : group_ 추가
        cmd =  " ".join( (select_, from_, where_, group_, order_, limit_) )

        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(cmd)
                rows = cur.fetchall()

                result = cur.rowcount
                if result > 0:
                    self._decrypt_passwd(sql_dict['FROM'], rows)

                return result, rows

            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                log.exception("nfvo_db.get_table DB Exception %s" % str(e))
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def get_table_by_uuid_name(self, table, uuid_name, error_item_text=None, allow_serveral=False):
        ''' Obtain One row from a table based on name or uuid.
        Attribute:
            table: string of table name
            uuid_name: name or uuid. If not uuid format is found, it is considered a name
            allow_severeral: if False return ERROR if more than one row are founded
            error_item_text: in case of error it identifies the 'item' name for a proper output text
        Return: if allow_several==False, a dictionary with this row, or error if no item is found or more than one is found
                if allow_several==True, a list of dictionaries with the row or rows, error if no item is found
        '''

        if error_item_text==None:
            error_item_text = table
        what = 'uuid' if af.check_valid_uuid(uuid_name) else 'name'
        cmd =  " SELECT * FROM " + table + " WHERE " + what +" ='"+uuid_name+"'"
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(cmd)
                number = cur.rowcount
                if number==0:
                    return -HTTP_Not_Found, "No %s found with %s '%s'" %(error_item_text, what, uuid_name)
                elif number>1 and not allow_serveral:
                    return -HTTP_Bad_Request, "More than one %s found with %s '%s'" %(error_item_text, what, uuid_name)
                if allow_serveral:
                    rows = cur.fetchall()
                else:
                    rows = cur.fetchone()
                return number, rows
            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                log.exception("nfvo_db.get_table_by_uuid_name DB Exception %s" % str(e))
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()

    def get_uuid(self, uuid):
        '''check in the database if this uuid is already present'''
        for retry_ in range(0,2):
            conn = None
            cur = None
            try:
                #with self.con:
                conn = psycopg2.connect(host=self.host, port=self.port, user=self.user, password=self.passwd, database=self.database, application_name="Orch-F")
                conn.autocommit = True
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("SELECT * FROM uuids where uuid='" + str(uuid) + "'")
                rows = cur.fetchall()
                #return self.cur.rowcount, rows
                result = cur.rowcount
                return result, rows
            except (psycopg2.Error, psycopg2.IntegrityError, AttributeError), e:
                log.exception("nfvo_db.get_uuid DB Exception %s" % str(e))
                return -HTTP_Internal_Server_Error, str(e)
            except Exception, e:
                return -HTTP_Internal_Server_Error, str(e)
            finally:
                if cur: cur.close()
                if conn: conn.close()


    @staticmethod
    def _encrypt_passwd(table, dict):

        column = None

        if table == "tb_vim_tenant":
            if "password" in dict:
                column = "password"
        elif table == "tb_server_account":
            if "account_pw" in dict:
                column = "account_pw"
        elif table == "tb_server_account_use":
            if "use_account_pw" in dict:
                column = "use_account_pw"
        elif table == "tb_nfcatalog":
            if "app_passwd" in dict:
                column = "app_passwd"
        elif table == "tb_vdud":
            if "vm_access_passwd" in dict:
                column = "vm_access_passwd"
        elif table == "tb_vdu":
            if "vm_access_passwd" in dict:
                column = "vm_access_passwd"
        try:
            if column and dict[column] is not None:
                cipher = AESCipher.get_instance()
                dict[column] = cipher.encrypt(dict[column])
        except Exception, e:
            log.error("_encrypt_passwd: %s" % str(e))

    @staticmethod
    def _decrypt_passwd(str_table, rows):

        column = None

        if str_table.find('tb_vim_tenant') >= 0:
            column = "password"
        elif str_table.find('tb_server_account') >= 0:
            column = "account_pw"
        elif str_table.find('tb_server_account_use') >= 0:
            column = "use_account_pw"
        elif str_table.find('tb_nfcatalog') >= 0:
            column = "app_passwd"
        elif str_table.find('tb_vdud') >= 0:
            column = "vm_access_passwd"
        elif str_table.find('tb_vdu') >= 0:
            column = "vm_access_passwd"

        try:
            if column:
                cipher = AESCipher.get_instance()
                for row in rows:
                    if column in row and row[column] is not None and len(row[column]) == 64:
                        row[column] = cipher.decrypt(row[column])
        except Exception, e:
            log.error("_decrypt_passwd: %s" % str(e))