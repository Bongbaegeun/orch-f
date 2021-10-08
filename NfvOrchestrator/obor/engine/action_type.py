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

class ActionType():

    PROVS = "P"     # Provision
    RESTO = "R"     # Restore
    BACUP = "B"     # Backup
    IMGUP = "G"     # VNF Image Upgrade
    DELNS = "D"     # NS Delete
    NSRUP = "U"     # NS Update
    FACRS = "F"     # Facotry Reset
    OBPAT = "O"     # One-Box Patch (OBA/VNFM)
    NICMD = "N"     # Port(NIC) ADD/DEL
    NICER = "M"     # Port(NIC) ADD/DEL Fail
    VDUAC = "V"     # VDU Action stop/start/reboot
    WANSW = "W"     # WAN Switch

    # PNF
    REBOT = "T"     # Reboot
