#!/usr/bin/env python
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

class NSRStatus():
    IDLE = "I__NONE"
    
    CRT = "A__CREATING"
    CRT_parsing = "A__PARSING__1__8"
    CRT_creatingvr = "A__CREATING VM__2__8"
    CRT_checkingvr = "A__CREATING VM__3__8"
    CRT_processingdb = "A__RECORDING__4__8"
    CRT_configvnf = "A__CONFIG VNF__5__8"
    CRT_testing = "A__TESTING__6__8"
    CRT_startingmonitor = "A__MONITOR__7__8"
    
    UDT = "A__UPDATING"
    UDT_parsing = "A__PARSING__1__8"
    UDT_updatingvr = "A__UPDATING VM__2__8"
    UDT_checkingvr = "A__UPDATING VM__3__8"
    UDT_processingdb = "A__RECORDING__4__8"
    UDT_configvnf = "A__CONFIG VNF__5__8"
    UDT_testing = "A__TESTING__6__8"
    UDT_resumingmonitor = "A__MONITOR__7__8"
    
    RUN = "N__RUNNING"
    
    DEL = "A__DELETING"
    DEL_stoppingmonitor = "A__MONITOR__1__3"
    DEL_deletingvr = "A__DELETING__2__3"
        
    BAC = "A__BACKUP"
    BAC_backupnsr = "A__BACKUP NS__1__3"
    BAC_backupvnf = "A__BACKUP VNFs__2__3"
    
    RST = "A__RESTORE"
    RST_suspendingmonitor = "A__MONITOR__1__11"
    RST_deletingvr = "A__DELETING__2__11"
    RST_parsing = "A__PARSING__3__11"
    RST_creatingvr = "A__CREATING VM__4__11"
    RST_checkingvr = "A__CREATING VM__5__11"
    RST_processingdb = "A__RECORDING__6__11"
    RST_configvnf = "A__CONFIG VNF__7__11"
    RST_testing = "A__TESTING__8__11"
    RST_restoringvnf = "A__RESTORE VNFs__9__11"
    RST_resumingmonitor = "A__MONITOR__10__11"

    NIC = "A__NICMODIFY"
    NIC_updatingrlt = "A__UPDATING RLT__1__6"
    NIC_updatingvr = "A__UPDATING VM__2__6"
    NIC_processingdb = "A__RECORDING__3__6"
    NIC_configvnf = "A__CONFIG VNF__4__6"
    NIC_resumingmonitor = "A__MONITOR__5__6"

    VIU = "A__VNF IMAGE UPDATE"
    VIU_deploy = "A__DEPLOYING__1__8"
    VIU_suspendingmonitor = "A__MONITOR__2__8"
    VIU_creatingvr = "A__CREATING VM__3__8"
    VIU_configvnf = "A__CONFIG VNF__4__8"
    VIU_processingdb = "A__RECORDING__5__8"
    VIU_restoringvnf = "A__RESTORE VNFs__6__8"
    VIU_resumingmonitor = "A__MONITOR__7__8"

    ERR = "E__ERROR"