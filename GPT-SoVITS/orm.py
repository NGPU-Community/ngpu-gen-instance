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

#for tts task, current no use for tts call in syncronization
class Task(Base):
    __tablename__ = "task"
    id = Column(Integer, primary_key=True)
    task_id = Column(String(256), default = "")
    result = Column(Integer, default = 0) #0, unknown; -1, failed; 1: success
    status = Column(Integer, default = 0) #0, queue; 1, doing, 2, finished 
    msg = Column(String(512), default = "")
    result_code = Column(Integer, default = 100) 
    audio_url = Column(String(512), default = "") #result
    srt_url = Column(String(512), default = "") #result
    audio_length = Column(Float, default = 0.0) 
    start_time = Column(DateTime, default = datetime.datetime.now)
    end_time = Column(DateTime , default = datetime.datetime.now)
    param = Column(String(1024), default = "")

    def assignWithoutId(self, other):
        self.task_id = other.task_id
        self.result = other.result
        self.status = other.status
        self.msg = other.msg
        self.result_code = other.result_code
        self.audio_url = other.audio_url
        self.srt_url = other.srt_url
        self.audio_length = other.audio_length
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
        self.audio_url = other.audio_url
        self.srt_url = other.srt_url
        self.audio_length = other.audio_length
        self.start_time = other.start_time
        self.end_time = other.end_time
        self.param = other.param

#for voice,
class Voice(Base):
    __tablename__ = "voice"
    id = Column(Integer, primary_key=True)
    ref_audio = Column(String(256), default = "")
    ref_text = Column(String(512), default = "") # maximum 10 sec
    ref_lang = Column(String(32), default = "auto") #auto, zh, jp, en, ko,
    create_time = Column(DateTime, default = datetime.datetime.now)
    addParam = Column(String(1024), default = "")

    def assignWithoutId(self, other):
        self.ref_audio = other.ref_audio
        self.ref_text = other.ref_text
        self.ref_lang = other.ref_lang
        self.create_time = other.create_time
        self.addParam = other.addParam

    def assignAll(self, other):
        self.id = other.id
        self.ref_audio = other.ref_audio
        self.ref_text = other.ref_text
        self.ref_lang = other.ref_lang
        self.create_time = other.create_time
        self.addParam = other.addParam

#very simple client, no care for transaction/rollback. only single thread lock
class DbClient:
    def __init__(self):
        self.engine = create_engine('mysql+mysqlconnector://root:QmKuwq8kSQ8b@localhost:3306/ipollo')
        Session = sessionmaker(bind=self.engine)
        
        #create table
        #Base.metadata.create_all(self.engine)
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
                logging.error(f"cannot update item: cannot find item, taskid = {taskID}")

            obj_to_update.assignWithoutId(task)
            self.session.commit()

    def addVoice(self, voice : Voice):
        with self.lock:
            self.session.add(voice)
            self.session.commit()
            logging.info(f"add voice={voice.id}")

    #in theory, there should be only one
    def queryByVoiceId(self, voiceID:str):
        with self.lock:
            results = self.session.query(Voice).filter_by(id=voiceID).all()
            logging.info(f"query for voice id={voiceID}, {len(results)} objects returned.")
            return results

    #in theory, there should be only one
    def deleteByVoiceId(self, voiceID:str):
        with self.lock:
            obj_to_delete = self.session.query(Voice).filter_by(id=voiceID).all()
            logging.info(f"query for voiceID={voiceID}, {len(obj_to_delete)} objects to be deleted.")
            for obj in obj_to_delete:
                self.session.delete(obj)
                self.session.commit()

    #get the total number of voices
    def getVoiceCount(self) -> int:
        with self.lock:
            total_entries = self.session.query(Voice).count()
            return total_entries