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

class DescriptorStatus():
    IDLE = "I__NONE"
    
    CRT = "A__CREATING"
    CRT_checking = "A__CHECKING__1__4"
    CRT_parsing = "A__PARSING__2__4"
    CRT_processingdb = "A__RECORDING__3__4"
    
    RDY = "N__READY"
    
    DEL = "A__DELETING"
    DEL_deleting = "A__DELETING__1__2"
        
    ERR = "E__ERROR"