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

class SRVStatus():

    IDLE = "I__NONE"
    
    LWT = "I__LINE_WAIT"
    RIS = "N__READY_INSTALL"
    
    RDS = "N__READY_SERVICE"
    PVS = "N__PROVISIONING"
    INS = "N__IN_SIERVICE"
    LPV = "N__LOCAL_PROVISIONING"
    
    OOS = "A__OUT_OF_SERVICE__1__2"
    OOS_suspendingmonitor = "A__MONITOR__1__4"
    OOS_inprogress = "A__IN_PROGRESS__2__4"
    OOS_resumingmonitor = "A__MONITRO__3__4"
    
    HWE = "E__ERROR_HW"
    ERR = "E__ERROR"
    
    DSC = "I__DISCONNECTED"

    # One-Box Update Patch
    OBU = "A__OB_UPDATE"
    OBP = "A__OB_PATCH"