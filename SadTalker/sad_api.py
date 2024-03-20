import array
import os
from app_sadtalker import ref_video_fn

#from pytorch_lightning import seed_everything

#for fastapi
from fastapi import FastAPI , Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import asyncio
import threading
import logging
import urllib.request
import requests
import datetime
from moviepy.editor import VideoFileClip

from src.gradio_demo import SadTalker
from orm import *
import time

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)


class MyClass:
    pass

dbClient = DbClient()


class SadRequest(BaseModel):
    pose_style: int = 0  # 0- 45
    size_of_image: int = 512 # 256,512
    preprocess_type: str = 'full' #'crop', 'resize','full', 'extcrop', 'extfull'
    is_still_mode: bool = True
    enhancer: bool = True #quite slow,
    #use_idle_mode: bool #not sure its meaning
    #length_of_audio: int  #with use_idle_mode
    use_ref_video: bool = False #activate ref_video settings
    ref_video: str  = "" #local file path,
    ref_info: str = 'all' #pose, blink, pose+blink, all
    use_blink: bool = True #default
    exp_scale: float = 1.0 #expression scale
    image_url: str = ""
    audio_url: str = ""

    def __json__(self):
        return {"pose_style":self.pose_style, "size_of_image":self.size_of_image, "preprocess_type":self.preprocess_type, "is_still_mode":self.is_still_mode, "enhancer":self.enhancer,
                "use_ref_video":self.use_ref_video, "ref_video":self.ref_video, "ref_info":self.ref_info, "use_blink":self.use_blink, "exp_scale":self.exp_scale, "image_url":self.image_url, "audio_url":self.audio_url}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.audio_url = json_data.get("audio_url")
        one.enhancer = json_data.get("enhancer")
        one.exp_scale = json_data.get("exp_scale")
        one.image_url = json_data.get("image_url")

        one.is_still_mode = json_data.get("is_still_mode")
        one.pose_style = json_data.get("pose_style")
        one.preprocess_type = json_data.get("preprocess_type")
        one.ref_info = json_data.get("ref_info")

        one.ref_video = json_data.get("ref_video")
        one.size_of_image = json_data.get("size_of_image")
        one.use_blink = json_data.get("use_blink")
        one.use_ref_video = json_data.get("use_ref_video")
        return one

class SadActor:
    def __init__(self, name: str):
        self.name = name
        #better in config, need modification for every node
        self.tmp_folder = "./tmp"
        if not os.path.exists(self.tmp_folder):
            os.makedirs(self.tmp_folder)
            logging.info(f"created tmp folder {self.tmp_folder}")
        else:
            logging.info(f"tmp folder {self.tmp_folder} exists")

        self.www_folder = "/data/SadTalker/results"
        public_ip = self.get_public_ip()
        logging.info(f"public ip for this module is {public_ip}")
        self.url_prefix = "http://" + public_ip + ":8076/"

        self.version = "sad_v2"

        self.sad_talker = SadTalker('checkpoints', 'src/config', lazy_load=True)

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

    def init_task(self, content: SadRequest):
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
        dbClientThread = DbClient()
        #check db items 
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

            logging.info(f"start handling task={tasks[0].task_id}")
            sad_request= SadRequest()
            sad_request = SadRequest.from_json(json.loads(tasks[0].param))
            task = Task()
            task.assignAll(tasks[0])
            self.do_sample(task, sad_request)
            logging.info(f"finish handling task={tasks[0].task_id}")
            tasks[0].status = 1
            dbClientThread.updateByTaskId(tasks[0], tasks[0].task_id)

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
    def do_sample(self, task:Task, sad_request:SadRequest):
        #empty? checked before, no need
         try:
             logging.info(f"download photo file:{sad_request.image_url} to {self.tmp_folder}, {sad_request.audio_url} to {self.tmp_folder} ")
             photo_file = self.download(sad_request.image_url, self.tmp_folder)
             audio_file = self.download(sad_request.audio_url, self.tmp_folder)
             logging.info(f"downloaded photo and audio ")
             ref_video_file = ""
             if(sad_request.use_ref_video and sad_request.ref_video != "" ) :
                 ref_video_file = self.download(sad_request.ref_video, self.tmp_folder)
                 logging.info(f"downloaded ref video to {ref_video_file}")

             #start inference
             output_video = self.sad_talker.test(photo_file, audio_file, sad_request.preprocess_type, sad_request.is_still_mode, sad_request.enhancer,2, \
                                                 sad_request.size_of_image,sad_request.pose_style  \
                                                 ,sad_request.exp_scale, sad_request.use_ref_video, ref_video_file, sad_request.ref_info, \
                                                 use_blink=sad_request.use_blink, result_dir=self.www_folder)
             logging.info(f"finished inferencing, output={output_video}")
             new_output_video = output_video.replace("#", "")
             os.rename(output_video, new_output_video)
             output_video = new_output_video

             task.result_file = output_video
             video = VideoFileClip(task.result_file)
             task.result_length = video.duration
             task.width , task.height  = video.size
             logging.info(f"result video={task.result_file}, length = {task.result_length}, size = {task.width}x{task.height}")

             #for output url 
             diff = os.path.relpath(task.result_file, self.www_folder)
             task.result_url = self.url_prefix + diff
             logging.info(f'save_path={output_video}, www_folder={self.www_folder}, result_url={task.result_url}, diff={diff}')
             task.result = 1
             task.status = 2
             task.result_code = 100
             task.msg = "succeeded"
             task.end_time = datetime.datetime.now()
             #update item
             dbClient.updateByTaskId(task, task.task_id)

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

    def get_status(self, task_id: str):
        ret = MyClass()
        ret.result_url = ""
        tasks = dbClient.queryByTaskId(task_id)
        task = Task()
        if(len(tasks) == 0):
            logging.error(f"cannot found task_id={task_id}")
            ret.result_url = ""
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
                ret.result_url = task.result_url

            elif(task.result == -1): 
                ret.result_code = 104
                ret.msg = "task(" + task_id + ") has failed."
            else:
                ret.result_code = 104
                ret.msg = "task(" + task_id + ") has failed for uncertainty."  
        
        retJ = {"result_url": ret.result_url, "result_code": ret.result_code, "msg": ret.msg,"api_time_consume":task.result_length, "api_time_left":0, "video_w":task.width, "video_h":task.height, "gpu_type":"", "gpu_time_estimate":0, "gpu_time_use":0}
        #retJson = json.dumps(retJ)
        logging.debug(f"get_status for task_id={task_id}, return {retJ}" )
        return retJ



app = FastAPI()
sadActor = SadActor("sad_node_100")


@app.get("/")
async def root():
    return {"message": "Hello World, sad, May God Bless You."}

@app.post("/sadTalker")
async def post_t2tt(content : SadRequest):
    logging.info(f"before infer, content= {content}")
    result = MyClass()


    result.task_id = sadActor.init_task(content)
    result.result_code = 100
    result.msg = "task_id=" + result.task_id + " has been queued."
      
    retJ = {"task_id":result.task_id, "result_code": result.result_code, "msg": result.msg}
    #response = Response(content=retJ, media_type="application/json")
    #retJson = json.dumps(retJ)
    logging.info(f"url={content.image_url}, task_id={result.task_id}, return {retJ}")

    #return response
    return retJ

@app.get("/sadTalker")
async def get_status(taskID:str):
    logging.info(f"before startTask, taskID= {taskID}")
    return sadActor.get_status(taskID)
