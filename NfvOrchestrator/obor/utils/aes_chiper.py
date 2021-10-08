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

import base64
import hashlib
from Crypto import Random
from Crypto.Cipher import AES
from utils.config_manager import ConfigManager
# import utils.log_manager as log_manager
# log = log_manager.LogManager.get_instance()

class AESCipher(object):

    _instance = None

    def __init__(self):

        cfgManager = ConfigManager.get_instance()
        config = cfgManager.get_config()
        salt = config.get('passwd_salt', "")
        key = config.get('license_code', "")
        key = base64.b16decode(key)
        self.bs = 32
        self.key = hashlib.sha256((salt+key).encode()).digest()

    def encrypt(self, raw):
        raw = self._pad(raw)
        Random.atfork()
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw))

    def decrypt(self, enc):
        enc = base64.b64decode(enc)
        iv = enc[:AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[AES.block_size:])).decode('utf-8')

    def _pad(self, s):
        return s + (self.bs - len(s) % self.bs) * chr(self.bs - len(s) % self.bs)

    @staticmethod
    def _unpad(s):
        return s[:-ord(s[len(s)-1:])]

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = AESCipher()
        return cls._instance


if __name__ == "__main__":
    pass