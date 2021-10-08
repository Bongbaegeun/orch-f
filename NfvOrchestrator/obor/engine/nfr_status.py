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

class NFRStatus():
    IDLE = "I__NONE"
    
    CRT = "A__CREATING"
    CRT_composingvnfm = "A__COMM. VNFM__1__5"
    CRT_requestingvnfm = "A__COMM. VNFM__2__5"
    CRT_watingvnfm = "A__WAIT VNFM__3__5"
    CRT_processingdb = "A__RECORDING__4__5"
    
    RUN = "N__RUNNING"
    
    DEL = "A__DELETING"
        
    BAC = "A__BACKUP"
    BAC_waiting = "A__WAITING__0__4"
    BAC_composingvnfm = "A__COMM. VNFM__1__4"
    BAC_requestingvnfm = "A__COMM. VNFM__2__4"
    BAC_processingdb = "A__RECORDING__3__4"
    
    RST = "A__RESTORE"
    RST_waiting = "A__WAITING__0__5"
    RST_parsing = "A__PARSING__1__5"
    RST_requestingvnfm = "A__COMM. VNFM__2__5"
    RST_waitingvnfm = "A__WAIT VNFM__3__5"
    RST_processingdb = "A__RECORDING__4__5"
    

    STOP = "I__STOP"
    STOP_ing = "A__STOP"
    REBOOT = "A__REBOOT"
    START_ing = "A__START"
    UNKNOWN = "I__UNKNOWN"


    ERR = "E__ERROR"