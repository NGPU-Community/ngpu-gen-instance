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
#from datetime import datetime, timedelta


from orm import *
import time

from PIL import Image

import pytz
from moviepy.editor import VideoFileClip

from inference_api import action, ArgsInternal

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)


class MyClass(BaseModel):
    task_id: str
    result_code: int
    msg: str
    result_url:str


dbClient = DbClient()


class Request(BaseModel):
    video_url: str = ''  # Filepath of video/image that contains faces to use
    audio_url: str = '' #Filepath of video/audio file to use as raw audio source
    exp_img: str = 'neutral' #Expression template. neutral, smile or image path
    up_face: str = 'original' #'sad', 'angry', 'surprise', original
    fps: float = 25 #only valid for photo file of face


    def __json__(self):
        return {"video_url":self.video_url, "audio_url":self.audio_url, "exp_img":self.exp_img, "up_face":self.up_face, "fps":self.fps}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.video_url = json_data.get("video_url")
        if(one.video_url == None or one.video_url == ""):
            raise ValueError('video_url argument must be a valid path to video/image file')

        one.audio_url = json_data.get("audio_url")
        if(one.audio_url == None or one.audio_url == ""):
            raise ValueError('audio_url argument must be a valid path to voice file')

        one.exp_img = json_data.get("exp_img")
        if(one.exp_img == None or one.exp_img == ""):
            one.exp_img = 'neutral'
        one.up_face = json_data.get("up_face")

        if(one.up_face == None or one.up_face == ""):
            one.up_face = 'original'

        one.fps = json_data.get("fps")
        if (one.fps == None or one.fps < 0.1):
            one.fps = 25

        return one

class Actor:
    def __init__(self, name: str):
        self.name = name
        #better in config, need modification for every node
        self.tmp_folder = "./temp"
        if not os.path.exists(self.tmp_folder):
            os.makedirs(self.tmp_folder)
            logging.info(f"created tmp folder {self.tmp_folder}")
        else:
            logging.info(f"tmp folder {self.tmp_folder} exists")

        self.www_folder = "/data/video-retalking/results"
        public_ip = self.get_public_ip()
        public_ip = public_ip.replace(".", "-")
        logging.info(f"public ip for this module is {public_ip}")
        self.url_prefix = "https://" + public_ip + ".servicetest.ipolloverse.cn:7835/" #more work needed. 

        self.version = "videoRetalking_v1"

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
        #uniformed in UTC+8
        eastern = pytz.timezone('Asia/Shanghai')
        current_time = datetime.datetime.now()
        task.task_id = current_time.astimezone(eastern).strftime("%Y%m%d_%H_%M_%S_%f")
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
        logging.info("check_task, internal thread, set all doing to failed")
        doingTasks = dbClient.queryByStatus(1)
        for one in doingTasks:
            one.result_url = ""
            one.result = -1
            one.status = 2
            one.result_code = 104
            one.msg = "left doing task=" + one.task_id + ", set it to failure."
            logging.error(one.msg)
            one.result_file = ""
            one.end_time = datetime.datetime.now()
            dbClient.updateByTaskId(one, one.task_id)
        #check db items 
        while(self.threadRunning):
            #check 
            tasks = dbClient.queryByStatus(0)
            taskRunning = len(dbClient.queryByStatus(1))
            taskFinished = len(dbClient.queryByStatus(2))
            logging.info(f"waiting={len(tasks)}, running={taskRunning}, finished={taskFinished}")
            if(len(tasks) == 0):
                logging.info(f"no waiting task.")
                time.sleep(5)
                continue

            tasks[0].status = 1
            dbClient.updateByTaskId(tasks[0], tasks[0].task_id)
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

    def initArgs(self, request:Request, outputFile:str, tempFolder:str):
        args = ArgsInternal()
        args.DNet_path = 'checkpoints/DNet.pt'
        args.LNet_path = 'checkpoints/LNet.pth'
        args.ENet_path = 'checkpoints/ENet.pth'
        args.face3d_net_path = 'checkpoints/face3d_pretrain_epoch_20.pth'
        args.face = request.video_url
        args.audio = request.audio_url
        args.exp_img = request.exp_img
        args.outfile = outputFile
        args.fps = request.fps
        args.pads = [0, 20, 0, 0]
        args.face_det_batch_size = 4
        args.LNet_batch_size = 16
        args.img_size  = 384
        args.crop = [0, -1, 0, -1]
        args.box = [-1, -1, -1, -1]
        args.nosmooth = False
        args.static = False
        args.up_face = request.up_face
        args.one_shot = False #no default ? 
        args.without_rl1 = False
        args.tmp_dir = tempFolder
        args.re_preprocess = False #every time re-preprocess

        return args


    #action function, url is the http photo
    def do_sample(self, task:Task, request:Request):

        #empty? checked before, no need
        tempFolder = self.tmp_folder + "/" + task.task_id
        outputFolder = self.www_folder + "/" + task.task_id
        task.result_file = outputFolder + "/" + task.task_id + ".mp4"
        os.mkdir(outputFolder)
        
        #args variable
        args = self.initArgs(request, task.result_file, tempFolder)
        try:
            logging.info(f"download audio source file:{args.audio} to {tempFolder}")
            audio_file = self.download(args.audio, tempFolder)
            logging.info(f"downloaded audio source to {audio_file}")
            args.audio = audio_file

            logging.info(f"download face source file:{args.face} to {tempFolder}")
            face_file = self.download(args.face, tempFolder)
            logging.info(f"downloaded face_file source to {face_file}")
            args.face = face_file

            if(args.exp_img is not None and ('.png' in args.exp_img or '.jpg' in args.exp_img)):
                logging.info(f"download exp_img source file:{args.exp_img} to {tempFolder}")
                exp_img_file = self.download(args.exp_img, tempFolder)
                logging.info(f"downloaded exp_img source to {exp_img_file}")
                args.exp_img = exp_img_file
            
            logging.info("start to call action actually")

            action(args);


            videoR = VideoFileClip(task.result_file)
            task.result_length = videoR.duration
            task.width , task.height  = videoR.size

            logging.info(f"result file={task.result_file}, length = {task.result_length}, size = {task.width}x{task.height}")

            #for output url 
            diff = os.path.relpath(task.result_file, self.www_folder)
            task.result_url = self.url_prefix + diff
            logging.info(f'save_path={task.result_file}, www_folder={self.www_folder}, result_url={task.result_url}, diff={diff}')
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
        #ret = MyClass()
        ret = MyClass(task_id = "1", result_code=0, msg="Success", result_url="")
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


description = """
videoRetalking is based on opensource.https://github.com/OpenTalker/video-retalking

## Items

You can **read items**.

## Users

You will be able to:

* **Create users** (thornbird).
"""

app = FastAPI(title="VideoRetalkingAPI",
        description = description,
        version = "1.0")
actor = Actor("videoRetalking_node_100")


@app.get("/")
async def root():
    return {"message": "Hello World, videoRetalking, May God Bless You."}

@app.post("/videoRetalking")
async def post_t2tt(content : Request):
    """
    - video_url: str = 'video/photo url'  #Must, Filepath of video/image that contains faces to use
    - audio_url: str = 'audio url' #Must, Filepath of video/audio file to use as raw audio source
    - exp_img: str = 'neutral' #optional, Expression template. neutral, smile or image path,
    - up_face: str = 'original' #optional,'sad', 'angry', 'surprise', original
    - fps: float = '25' #optional,only valid for photo file of face
    """
    logging.info(f"before infer, content= {content}")
    if(content.audio_url == None or content.audio_url == "" or content.video_url == None or content.video_url == ""):
        logging.error(f"audio_url={content.audio_url} and video_url={content.video_url} are must, please check them.")
        retJ = {"task_id":"", "result_code": 200, "msg": "wrong video_url or audio_url"}
        return retJ

    if(content.exp_img == None or content.exp_img == ""):
        content.exp_img = 'neutral'

    if(content.up_face == None or content.up_face == ""):
        content.up_face = 'original'

    if (content.fps == None or content.fps < 0.1):
        content.fps = 25
    logging.info(f"after correction, content= {content}")

    result = MyClass(task_id = "1", result_code=0, msg="Success", result_url="")


    result.task_id = actor.init_task(content)
    result.result_code = 100
    result.msg = "task_id=" + result.task_id + " has been queued."
      
    retJ = {"task_id":result.task_id, "result_code": result.result_code, "msg": result.msg}
    logging.info(f"video_url={content.video_url}, audio_url={content.audio_url}, task_id={result.task_id}, return {retJ}")

    #return response
    return retJ

@app.get("/videoRetalking")
async def get_status(taskID:str):
    logging.info(f"before startCheck, taskID= {taskID}")
    return actor.get_status(taskID)

