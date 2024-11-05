# Multiple tools for api-fast

import os
from configparser import ConfigParser

config = ConfigParser()
#HOME_DIR = '/var'
HOME_DIR = os.path.dirname(os.getcwd())
DIR = os.path.basename(os.getcwd())

def get_config():
    default_dir = os.path.join(HOME_DIR, DIR)
    #default_dir = os.path.join(HOME_DIR, 'api-fast_pos')
    config_file = os.path.join(default_dir, 'api-fast.ini')
    config = ConfigParser()
    config.read(config_file)
    return config
