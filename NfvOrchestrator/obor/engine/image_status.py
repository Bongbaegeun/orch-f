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

class ImageStatus(object):

    WAIT = "I__WAIT"

    FILETRAN = "A__FILETRAN"

    VIMREG_start = "A__VIMREG__0__1"
    VIMREG_end = "A__VIMREG__1__1"

    COMPLETE = "N__COMPLETE"

    ERROR = "E__ERROR"
    ERROR_VIM = "E__ERROR-VIM"
    ERROR_NOTSUPPORTED = "E__ERROR-NOTSUPPORTED"

    PROGRESS_STEP = 10

    @classmethod
    def get_filetran_progress(cls, size, sent):

        step = (sent * cls.PROGRESS_STEP) / size
        if step == 0:
            step = 1

        return "%s__%s__%s" % (cls.FILETRAN, step, cls.PROGRESS_STEP)

# if __name__ == "__main__":
#
#     print ImageStatus.get_filetran_progress(78003, 15838)
