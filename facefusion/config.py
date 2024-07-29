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


#definition for all result code and status.
#error code for return
#0  no error
ErrorInfo = {-10000: "unknown error", 
             -10001: "wrong product id",
             -10002: "wrong product config internally",
             -10003: "wrong task id",
             -10004: "http request failed",
             -10005: "wrong task status",
             -10006: "cannot find machine id",
             -10007: "cannot parse request params.",
             0: "done successfully"}

'''
result	code
0	unknown, like doing, inited
-1  failed
1   success
'''
Result_Unknown : int = 0
Result_Success: int = 1
Result_FailedCommon : int = -10000
Result_FailedProductId : int = -10001
Result_FailedProductConfig : int = -10002
Result_FailedTaskId : int = -10003
Result_FailedHttp : int = -10004
Result_FailedTaskStatus : int = -10005
Result_FailedMachineId : int = -10006
Result_FailedParams :int = -10007

'''
Status Code

Status Code	Description
0  queued
1  doing
2  finished
'''
Status_Queued : int = 0
Status_Doing : int = 1
Status_Finished : int = 2
''' 

'''
