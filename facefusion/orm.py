#from asyncio.windows_events import NULL
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging
import datetime
import threading

#from 
'''
errorCode: 
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
    output = Column(String(10240), default = "")
    start_time = Column(DateTime, default = datetime.datetime.now)
    end_time = Column(DateTime , default = datetime.datetime.now)
    param = Column(String(1024), default = "")

    def assignWithoutId(self, other):
        self.task_id = other.task_id
        self.result = other.result
        self.status = other.status
        self.msg = other.msg
        self.result_code = other.result_code
        self.output = other.output
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
        self.output = other.output
        self.start_time = other.start_time
        self.end_time = other.end_time
        self.param = other.param

#very simple client, no care for transaction/rollback. only single thread lock
class DbClient:
    def __init__(self):
        #self.engine = create_engine('mysql+mysqlconnector://root:QmKuwq8kSQ8b@localhost:3306/facefusion')
        self.engine = create_engine('mysql+mysqlconnector://root:zxw316@localhost:3306/facefusion')
        Session = sessionmaker(bind=self.engine)
        
        #create table
        Base.metadata.create_all(self.engine)
        self.session = Session()
        #for session protection
        self.lock = threading.Lock()

    def __del__(self):
        self.session.close()

    def add(self, task : Task):
        with self.lock:
            self.session.add(task)
            self.session.commit()
            logging.info(f"add taskid={task.task_id}")

    #in theory, there should be only one
    def queryByTaskId(self, taskID:str):
        with self.lock:
            results = self.session.query(Task).filter_by(task_id=taskID).all()
            logging.info(f"query for taskID={taskID}, {len(results)} objects returned.")
            return results

    def queryByStatus(self, status:int):
        with self.lock:
            results = self.session.query(Task).filter_by(status=status).all()
            logging.info(f"query for status={status}, {len(results)} objects returned.")
            return results

    #in theory, there should be only one
    def deleteByTaskId(self, taskID:str):
        with self.lock:
            obj_to_delete = self.session.query(Task).filter_by(task_id=taskID).all()
            logging.info(f"query for taskID={taskID}, {len(obj_to_delete)} objects to be deleted.")
            for obj in obj_to_delete:
                self.session.delete(obj)
                self.session.commit()

    def updateByTaskId(self, task: Task, taskID:str):
        with self.lock:
            obj_to_update = self.session.query(Task).filter_by(task_id=taskID).first()
            if(obj_to_update == None):
                logging.error(f"cannot update item: cannot find item, taskid = {taskID}, ")

            obj_to_update.assignWithoutId(task)
            self.session.commit()
