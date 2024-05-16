import array
from ast import Raise
import os


#from pytorch_lightning import seed_everything

#for fastapi
from fastapi import FastAPI , Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import threading
import logging
import urllib.request
import requests
import datetime

from orm import *
import time

from Process import *
from PIL import Image

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)


class MyClass(BaseModel):
    task_id: str = ""
    result_code: int = 0
    msg: str = ""

dbClient = DbClient()


class Request(BaseModel):
    prompt: str = 'why is the sky blue?'  # photo, video

    def __json__(self):
        return {"prompt":self.prompt}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.prompt = json_data.get("prompt")

        return one

class GetRequest(BaseModel):
    taskId: str = 'xxx'  #

    def __json__(self):
        return {"taskId":self.taskId}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.taskId = json_data.get("taskId")

        return one

class Actor:
    def __init__(self, name: str):
        self.name = name
        #better in config, need modification for every node
        self.tmp_folder = "./tmp"
        if not os.path.exists(self.tmp_folder):
            os.makedirs(self.tmp_folder)
            logging.info(f"created tmp folder {self.tmp_folder}")
        else:
            logging.info(f"tmp folder {self.tmp_folder} exists")

        self.www_folder = "/data/ollama/results"
        public_ip = self.get_public_ip()
        logging.info(f"public ip for this module is {public_ip}")
        self.url_prefix = "http://" + public_ip + ":7741/"

        self.version = "ollama_v1"
        self.ollamaUrl = "http://localhost:11434/api/generate"

        #for worker thread
        self.thread = threading.Thread(target = self.check_task)
        self.thread.daemon = True
        self.thread.start()
        self.threadRunning = True

    def __del__(self):
        self.threadRunning = False

    def say_hello(self):
        logging.debug(f"Hello, {self.name}!")
    
    def get_public_ip(self):
        response = requests.get('https://ifconfig.me/ip')
        return response.text

    def init_task(self, content: Request):
        task = Task()
        task.status = 0 #queued
        task.task_id = datetime.datetime.now().strftime("%Y%m%d_%H_%M_%S_%f")
        task.result = 0
        task.msg = ""
        task.result_code = 100
        task.result_url = ""
        task.param = json.dumps(content.__json__())
        task.start_time = datetime.datetime.now()
        task.end_time = datetime.datetime.now()

        logging.info("after init_task")

        #add item to db
        dbClient.add(task)
        return task.task_id

    def check_task(self):
        logging.info("check_task, internal thread")
        #check db items 
        dbClientThread = dbClient
        while(self.threadRunning):
            #check 
            tasks = dbClientThread.queryByStatus(0)
            taskRunning = len(dbClientThread.queryByStatus(1))
            taskFinished = len(dbClientThread.queryByStatus(2))
            logging.info(f"waiting={len(tasks)}, running={taskRunning}, finished={taskFinished}")
            if(len(tasks) == 0):
                logging.info(f"no waiting task.")
                time.sleep(5)
                continue

            tasks[0].status = 1
            dbClientThread.updateByTaskId(tasks[0], tasks[0].task_id)
            logging.info(f"start handling task={tasks[0].task_id}")
            request= Request()
            request = Request.from_json(json.loads(tasks[0].param))
            task = Task()
            task.assignAll(tasks[0])
            self.do_sample(task, request)
            logging.info(f"finish handling task={tasks[0].task_id}")


        logging.info("finishing internal thread.")
        return

    #download url to folder, keep the file name untouched
    def download(self, url: str, directory:str):
        if not os.path.exists(directory):
            os.makedirs(directory)

        filename = url.split("/")[-1]

        file_name = os.path.join(directory, filename)
        urllib.request.urlretrieve(url, file_name)
        return file_name

    #action function, url is the http photo
    def do_sample(self, task:Task, request:Request):
        #empty? checked before, no need
         try:
             logging.info(f"start to handle task={task.task_id}")
             data = {"model":"llama3","prompt":request.prompt, "stream":False}
             dataStr = json.dumps(data)
             logging.info(f"before ollama inference, task={task.task_id}, url={self.ollamaUrl}, data={dataStr}")
             response = requests.post(self.ollamaUrl, data = dataStr)
             logging.info(f"for task={task.task_id}, response = {response.text}, statuscode={response.status_code}") 
             if(response.status_code == 200) :
                 json_data = json.loads(response.text)
                 logging.info(f"reponse 200, response={json_data['response']}")
                 task.output = json_data['response']
                 task.result = 1
                 task.status = 2
                 task.result_code = 100
                 task.msg = "succeeded"
                 task.end_time = datetime.datetime.now()
                 #update item
                 dbClient.updateByTaskId(task, task.task_id)
             else:
                 logging.info(f"reponse = {response.status_code}, failed")
                 raise requests.exceptions.HTTPError(f'request ollama service error, status = {response.status_code}')        

         except Exception as e:
             logging.error(f"something wrong during task={task.task_id}, exception={repr(e)}")
             task.result_url = ""
             task.result = -1
             task.status = 2
             task.result_code = 104
             task.msg = "something wrong during task=" + task.task_id + ", please contact admin."
             task.result_file = ""
             task.end_time = datetime.datetime.now()
             dbClient.updateByTaskId(task, task.task_id)

         finally:
             task.status = 2


    #action function, in sync mode,no task 
    def do_sampleSync(self, request:Request):
        #empty? checked before, no need
         try:
             logging.info(f"start to handle prompt={request.prompt}")
             data = {"model":"llama3","prompt":request.prompt, "stream":False}
             dataStr = json.dumps(data)
             logging.info(f"before ollama inference, url={self.ollamaUrl}, data={dataStr}")
             response = requests.post(self.ollamaUrl, data = dataStr)
             logging.info(f"for response = {response.text}, statuscode={response.status_code}") 
             if(response.status_code == 200) :
                 json_data = json.loads(response.text)
                 logging.info(f"reponse 200, response={json_data['response']}")
                 return json_data['response']
             else:
                 logging.info(f"reponse = {response.status_code}, failed")
                 raise requests.exceptions.HTTPError(f'request ollama service error, status = {response.status_code}')        

         except Exception as e:
             logging.error(f"something wrong during prompt={request.prompt}, exception={repr(e)}")
             return f"failed to answer {request.prompt}, please contact admin."
         finally:
             logging.info(f"finished all for prompt = {request.prompt}")
          
             
    def get_status(self, task_id: str):
        ret = MyClass()
        ret.task_id = task_id
        output = ""
        tasks = dbClient.queryByTaskId(task_id)
        task = Task()
        if(len(tasks) == 0):
            logging.error(f"cannot found task_id={task_id}")
            ret.result_code = 200
            ret.msg = "cannot find task_id=" + task_id    
        else:
            if(len(tasks) >= 1):
                logging.error(f"found {len(tasks)} for task_id={task_id}, use the first one")
            
            task.assignAll(tasks[0])
            if(task.result == 0 and task.status == 0):
                ret.result_code = 101
                ret.msg = "task(" + task_id + ") is waiting."
            elif(task.result == 0 and task.status == 1):
                ret.result_code = 102
                ret.msg = "task(" + task_id + ") is running."
            elif(task.result == 1): 
                ret.result_code = 100
                ret.msg = "task(" + task_id + ") has succeeded."
                output = task.output

            elif(task.result == -1): 
                ret.result_code = 104
                ret.msg = "task(" + task_id + ") has failed."
            else:
                ret.result_code = 104
                ret.msg = "task(" + task_id + ") has failed for uncertainty."  
        
        retJ = {"data": output, "result_code": ret.result_code, "msg": ret.msg,"taskID":task_id}
        #retJson = json.dumps(retJ)
        logging.debug(f"get_status for task_id={task_id}, return {retJ}" )
        return retJ


description = """
GenAI wrapper for ollama .

## Items

You can **read items**.

## Users

You will be able to:

* **Create users** (thornbird).
"""

app = FastAPI(title="ollamaAPI",
        description = description,
        version = "1.0")
actor = Actor("ollama_node_100")


@app.get("/")
async def root():
    return {"message": "Hello World, rembg, May God Bless You."}

@app.post("/start")
async def start(content : Request):
    """
    - prompt: question sent to llama3
    """
    logging.info(f"before infer, content= {content}")
    result = MyClass()


    result.task_id = actor.init_task(content)
    result.result_code = 100
    result.msg = "task_id=" + result.task_id + " has been queued."
      
    retJ = {"task_id":result.task_id, "result_code": result.result_code, "msg": result.msg}
    logging.info(f"prompt={content.prompt} task_id={result.task_id}, return {retJ}")

    #return response
    return retJ

@app.post("/get")
async def get_status(getRequest:GetRequest):
    taskID = getRequest.taskId
    logging.info(f"before startTask, taskID= {taskID}")
    return actor.get_status(taskID)

@app.post("/startSync")
async def startSync(content : Request):
    """
    - prompt: question sent to llama3
    """
    logging.info(f"before infer, content= {content}")
    result = MyClass()
    
    data = actor.do_sampleSync(content)
    result.result_code = 100
    result.msg = "Done successfully."
      
    retJ = {"data":data, "result_code": result.result_code, "msg": result.msg}
    logging.info(f"prompt={content.prompt}  return {retJ}")

    #return response
    return retJ