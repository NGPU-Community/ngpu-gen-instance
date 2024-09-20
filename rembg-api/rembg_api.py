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
from moviepy.editor import VideoFileClip

from orm import *
import time

from Process import *
from PIL import Image

from types import SimpleNamespace

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)


class MyClass(BaseModel):
    task_id: str
    result_code: int
    msg: str

dbClient = DbClient()


class Request(BaseModel):
    kind: str = 'photo'  # photo, video
    obj: str = 'any' #any, human, cloth
    url: str = '' #
    bgColor: str = '0,255,0,100' #RGBA, Green in default

    def __json__(self):
        return {"kind":self.kind, "obj":self.obj, "url":self.url, "bgColor":self.bgColor}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.kind = json_data.get("kind")
        one.obj = json_data.get("obj")
        one.url = json_data.get("url")
        one.bgColor = json_data.get("bgColor")

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

        self.www_folder = "/data/rembg/results"
        public_ip = self.get_public_ip()
        logging.info(f"public ip for this module is {public_ip}")
        self.url_prefix = "http://" + public_ip + ":7741/"

        self.version = "rembg_v1"

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
        #dbClientThread = DbClient()
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
            self.do_sample(task, request, dbClientThread)
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
    def do_sample(self, task:Task, request:Request, dbClientThread:DbClient):
        #empty? checked before, no need
         try:
             logging.info(f"download source file:{request.url} to {self.tmp_folder}")
             photo_file = self.download(request.url, self.tmp_folder)
             logging.info(f"downloaded source")

             cmd = []
             #for cmd params
             #1, photo or video, 2, model, 3. bgColor
             #for photo, rembg i -m u2net_human_seg -bgc 0 255 0 100 ./source/z.png ./dest/z_output.png
             #for video, ffmpeg -i ./source/biden.mp4  -an -f rawvideo -pix_fmt rgb24 pipe:1 | rembg b 1920 1080 -m u2net_human_seg -bgc 0 255 0 100 -o dest/biden2/biden_%05u.png
             logging.info(f"bg input = {request.bgColor}")
             bgColor = request.bgColor.split(",");
             logging.info(f"bg input = {request.bgColor}, splitted into {bgColor}")
             if(request.kind == 'photo'):
                 task.result_file = self.www_folder + "/" + task.task_id + ".png"
                 cmd = "rembg i "
                 if(request.obj == "any"):
                     cmd = cmd + "-m u2net -bgc "  + ' '.join(str(x) for x in bgColor) + " " + photo_file + " " + task.result_file
                 elif(request.obj == "human"):
                     cmd = cmd + "-m u2net_human_seg -bgc " + ' '.join(str(x) for x in bgColor) + " " + photo_file + " " + task.result_file
                 elif(request.obj == "cloth"):
                     cmd = cmd + "-m u2ne_cloth_seg -bgc " + ' '.join(str(x) for x in bgColor) + " " + photo_file + " " + task.result_file
                 else:
                     raise ValueError(f"invalid param for obj = {request.obj}")
                 logging.info(f"photo cmd={cmd}")
                 logging.info(f"to launchProcess with cmd={cmd}")
                 if(Process.launchProcess(cmd) == 0):
                     logging.info(f"succeeded in launching, cmd = {cmd}")
                 else:
                     logging.error(f"failed to launching, cmd = {cmd}")
                     raise Exception(f"failed to launching, cmd = {cmd}")
             elif(request.kind == 'video'):
                 outputFolder = self.www_folder + "/" + task.task_id
                 outputFile = outputFolder + "/output_%05d.png"
                 task.result_file = outputFolder + "/" + task.task_id + ".mp4"
                 os.mkdir(outputFolder)

                 video = VideoFileClip(photo_file)

                 cmd = "ffmpeg -i " + photo_file + " -an -f rawvideo -pix_fmt rgb24 pipe:1 | rembg b "+ ' '.join(str(x) for x in video.size)
                 if(request.obj == "any"):
                     cmd = cmd + " -m u2net -bgc " + ' '.join(str(x) for x in bgColor) + " -o " + outputFile
                 elif(request.obj == "human"):
                     cmd = cmd + " -m u2net_human_seg -bgc " + ' '.join(str(x) for x in bgColor) + " -o " + outputFile
                 elif(request.obj == "cloth"):
                     cmd = cmd + " -m u2net_cloth_seg -bgc " + ' '.join(str(x) for x in bgColor) + " -o " + outputFile
                 else:
                     raise ValueError(f"invalid param for obj = {request.obj}")
                 #to combine the video, ffmpeg -framerate 25 -pattern_type glob -i '*.png' -c:v libx264 -pix_fmt yuv420p biden_output.mp4
                 cmd = cmd
                 logging.info(f"video step 1 cmd={cmd}")

                 logging.info(f"video step 1: to launchProcess with cmd={cmd}")
                 if(Process.launchProcess(cmd) == 0):
                     logging.info(f"video step 1: succeeded in launching, cmd = {cmd}")
                 else:
                     logging.error(f"video step 1: failed to launching, cmd = {cmd}")
                     raise Exception(f"video step 1: failed to launching, cmd = {cmd}")

                 cmd = "ffmpeg -framerate " + str(video.fps) +  " -f image2 -i '" + outputFile \
                    + "' -c:v libvpx-vp9 -pix_fmt yuva420p " + task.result_file
                 logging.info(f"video step 2 cmd={cmd}")

                 logging.info(f"video step 2: to launchProcess with cmd={cmd}")
                 if(Process.launchProcess(cmd) == 0):
                     logging.info(f"video step 2: succeeded in launching, cmd = {cmd}")
                 else:
                     logging.error(f"video step 2: failed to launching, cmd = {cmd}")
                     raise Exception(f"video step 2: failed to launching, cmd = {cmd}")
             else:
                 raise ValueError(f"invalid param for kind = {request.kind}")



             if(request.kind == 'photo'):
                 image = Image.open(task.result_file)
                 task.width,task.height= image.size
             else:
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
             dbClientThread.updateByTaskId(task, task.task_id)

         except Exception as e:
             logging.error(f"something wrong during task={task.task_id}, exception={repr(e)}")
             task.result_url = ""
             task.result = -1
             task.status = 2
             task.result_code = 104
             task.msg = "something wrong during task=" + task.task_id + ", please contact admin."
             task.result_file = ""
             task.end_time = datetime.datetime.now()
             dbClientThread.updateByTaskId(task, task.task_id)

         finally:
             task.status = 2

    def get_status(self, task_id: str):
        ret = SimpleNamespace()
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
Remove background is based on rembg opersource.

## Items

You can **read items**.

## Users

You will be able to:

* **Create users** (thornbird).
"""

app = FastAPI(title="RembgAPI",
        description = description,
        version = "1.0")
actor = Actor("rembg_node_100")


@app.get("/")
async def root():
    return {"message": "Hello World, rembg, May God Bless You."}

@app.post("/removeBG", response_model=MyClass)
async def post_t2tt(content : Request):
    """
    - kind: str = 'photo'  # photo, video
    - obj: str = 'any' #any, human, cloth
    - url: str = '' #
    - bgColor: str = '0,255,0,100' #RGBA, Green in default
    """
    logging.info(f"before infer, content= {content}")
    result = MyClass(task_id="0",result_code=0, msg="")


    result.task_id = actor.init_task(content)
    result.result_code = 100
    result.msg = "task_id=" + result.task_id + " has been queued."
      
    retJ = {"task_id":result.task_id, "result_code": result.result_code, "msg": result.msg}
    logging.info(f"url={content.url}, task_id={result.task_id}, return {retJ}")

    #return response
    return retJ

@app.get("/removeBG")
async def get_status(taskID:str):
    logging.info(f"before startTask, taskID= {taskID}")
    return actor.get_status(taskID)

