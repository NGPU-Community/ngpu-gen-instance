import configparser
import logging

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)

class Config:
    def __init__(self):
        # Read configuration file
        config_file='config.ini'
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        logging.info("succeeded in config init")
        
    #read the config
    def get(self, l1, l2):
        return self.config[l1][l2]


#for global
config = Config()    
