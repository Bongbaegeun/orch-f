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

# pip install enum
#from enum import Enum

class HTTPResponse():
    
    Bad_Request =          400
    Unauthorized =         401 
    Not_Found =            404 
    Forbidden =            403
    Method_Not_Allowed =   405 
    Not_Acceptable =       406
    Service_Unavailable =  503 
    Internal_Server_Error= 500 