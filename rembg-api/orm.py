#from asyncio.windows_events import NULL
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging
import datetime
import threading

#from https://github.com/TwinSync/docs/blob/main/iPollo/api-photoacting.md
'''
Error Code	Description
200	Request parameter error or incomplete
201	Invalid or missing access key
202	Invalid or missing cloud address of audio or video file
203	Internal server error (such as video conversion failure, storage failure)
'''
'''
Status Code

Status Code	Description
100	The task is in a successful state
101	The task is in a waiting state
102	The task is in a running state
104	The task is in a failed state.
200	taskID field is missing or the field is not in the service queue.
'''

Base = declarative_base()

#for rembg for video and photo
class Task(Base):
    __tablename__ = "task"
    id = Column(Integer, primary_key=True)
    task_id = Column(String(256), default = "")
    result = Column(Integer, default = 0) #0, unknown; -1, failed; 1: success
    status = Column(Integer, default = 0) #0, queue; 1, doing, 2, finished 
    msg = Column(String(512), default = "")
    result_code = Column(Integer, default = 100) 
    result_url = Column(String(512), default = "")
    result_file = Column(String(512), default = "")
    result_length = Column(Float, default = 0.0) 
    width =  Column(Integer, default = 1)
    height = Column(Integer, default = 1)
    start_time = Column(DateTime, default = datetime.datetime.now)
    end_time = Column(DateTime , default = datetime.datetime.now)
    param = Column(String(1024), default = "")

    def assignWithoutId(self, other):
        self.task_id = other.task_id
        self.result = other.result
        self.status = other.status
        self.msg = other.msg
        self.result_code = other.result_code
        self.result_url = other.result_url
        self.result_file = other.result_file
        self.result_length = other.result_length
        self.width = other.width
        self.height = other.height
        self.start_time = other.start_time
        self.end_time = other.end_time
        self.param = other.param

    def assignAll(self, other):
        self.id = other.id
        self.task_id = other.task_id
        self.result = other.result
        self.status = other.status
        self.msg = other.msg
        self.result_code = other.result_code
        self.result_url = other.result_url
        self.result_file = other.result_file
        self.result_length = other.result_length
        self.width = other.width
        self.height = other.height
        self.start_time = other.start_time
        self.end_time = other.end_time
        self.param = other.param

#very simple client, no care for transaction/rollback. only single thread lock
class DbClient:
    def __init__(self):
        self.engine = create_engine('mysql+mysqlconnector://root:QmKuwq8kSQ8b@localhost:3306/ipollo', pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        
        #create table
        #Base.metadata.create_all(self.engine)
        # self.session = None
        #for session protection()
        self.lock = threading.Lock()

    def __del__(self):
        self.session.close()

    def add(self, task : Task):
        session = self.Session()
        with self.lock:
            session.add(task)
            session.commit()
            logging.info(f"add taskid={task.task_id}")
        session.close()
        
    #in theory, there should be only one
    def queryByTaskId(self, taskID:str):
        session = self.Session()
        with self.lock:
            results = session.query(Task).filter_by(task_id=taskID).all()
            logging.info(f"query for taskID={taskID}, {len(results)} objects returned.")
            session.close()
            return results
        session.close()
        
        
    def queryByStatus(self, status:int):
        session = self.Session()
        with self.lock:
            results = session.query(Task).filter_by(status=status).all()
            logging.info(f"query for status={status}, {len(results)} objects returned.")
            session.close()
            return results
        session.close()
        
    #in theory, there should be only one
    def deleteByTaskId(self, taskID:str):
        session = self.Session()
        with self.lock:
            obj_to_delete = session.query(Task).filter_by(task_id=taskID).all()
            logging.info(f"query for taskID={taskID}, {len(obj_to_delete)} objects to be deleted.")
            for obj in obj_to_delete:
                session.delete(obj)
                session.commit()
        session.close()
        
    def updateByTaskId(self, task: Task, taskID:str):
        session = self.Session()
        with self.lock:
            obj_to_update = session.query(Task).filter_by(task_id=taskID).first()
            if(obj_to_update == None):
                logging.error(f"cannot update item: cannot find item, taskid = {taskID}, ")

            obj_to_update.assignWithoutId(task)
            session.commit()
        session.close()    