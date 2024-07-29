import array
from ast import Raise
import os
from typing import Any


#from pytorch_lightning import seed_everything

#for fastapi
from fastapi import FastAPI , Response, Request
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

from config import *
from abc import ABC, abstractmethod

import facefusion.globals
import facefusion.config
from facefusion.filesystem import get_temp_frame_paths, get_temp_file_path, create_temp, move_temp, clear_temp, is_image, is_video, filter_audio_paths, resolve_relative_path, list_directory
from facefusion.ffmpeg import extract_frames, merge_video, copy_image, finalize_image, restore_audio, replace_audio
from facefusion.vision import read_image, read_static_images, detect_image_resolution, restrict_video_fps, create_image_resolutions, get_video_frame, detect_video_resolution, detect_video_fps, restrict_video_resolution, restrict_image_resolution, create_video_resolutions, pack_resolution, unpack_resolution
from facefusion.processors.frame.core import get_frame_processors_modules, load_frame_processor_module
from facefusion.processors.frame import globals as frame_processors_globals
from facefusion import core

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)

#reset params
def resetFacefusionGlobals(sourcePath:str, targetPath:str):
    facefusion.globals.config_path = 'facefusion.ini' 
	# general
    facefusion.globals.source_paths = [sourcePath]
    facefusion.globals.target_path = targetPath
    facefusion.globals.output_path = config.config['api']['output'] #the same as actor web path
	# misc
    facefusion.globals.force_download = False
    facefusion.globals.skip_download = True
    facefusion.globals.headless = True
    facefusion.globals.log_level = 'info'
	# execution
    facefusion.globals.execution_device_id = '0'
    facefusion.globals.execution_providers = ["CUDAExecutionProvider"]#["CPUExecutionProvider"] #"", 
    facefusion.globals.execution_thread_count = 4
    facefusion.globals.execution_queue_count = 1
	# memory
    facefusion.globals.video_memory_strategy = 'strict'
    facefusion.globals.system_memory_limit = 0
	# face analyser
    facefusion.globals.face_analyser_order = 'left-right'
    facefusion.globals.face_analyser_age = None
    facefusion.globals.face_analyser_gender = None
    facefusion.globals.face_detector_model = 'yoloface'
    facefusion.globals.face_detector_size = '640x640'
    facefusion.globals.face_detector_score = 0.5
    facefusion.globals.face_landmarker_score = 0.5
	# face selector
    facefusion.globals.face_selector_mode = 'reference'
    facefusion.globals.reference_face_position =  0
    facefusion.globals.reference_face_distance =  0.6
    facefusion.globals.reference_frame_number = 0
	# face mask
    facefusion.globals.face_mask_types = [ 'box', 'occlusion', 'region' ]
    facefusion.globals.face_mask_blur = 0.3
    facefusion.globals.face_mask_padding = (0,0,0,0)
    facefusion.globals.face_mask_regions = facefusion.config.get_str_list('face_mask.face_mask_regions', ' '.join(facefusion.choices.face_mask_regions))
	# frame extraction
    facefusion.globals.trim_frame_start = None
    facefusion.globals.trim_frame_end = None
    facefusion.globals.temp_frame_format = 'png'
    facefusion.globals.keep_temp = False
	# output creation
    facefusion.globals.output_image_quality = 95
    if is_image(targetPath):
        output_image_resolution = detect_image_resolution(targetPath)
        output_image_resolutions = create_image_resolutions(output_image_resolution)
        facefusion.globals.output_image_resolution = pack_resolution(output_image_resolution)
    facefusion.globals.output_video_encoder = 'libx264'
    facefusion.globals.output_video_preset = 'medium'
    facefusion.globals.output_video_quality = 95
    if is_video(targetPath):
        output_video_resolution = detect_video_resolution(targetPath)
        output_video_resolutions = create_video_resolutions(output_video_resolution)
        facefusion.globals.output_video_resolution = pack_resolution(output_video_resolution)
        facefusion.globals.output_video_fps = detect_video_fps(targetPath)
    facefusion.globals.skip_audio = False
	# frame processors
    #face_debugger
    frame_processors_globals.face_debugger_items = ['face-landmark-5/68','face-mask']
    #face_enhancer
    frame_processors_globals.face_enhancer_model = 'gfpgan_1.4'
    frame_processors_globals.face_enhancer_blend = 80
    #face_swapper
    frame_processors_globals.face_swapper_model = 'inswapper_128'
    #frame_enhancer
    frame_processors_globals.frame_enhancer_model = 'span_kendata_x4'
    frame_processors_globals.frame_enhancer_blend = 80
    #lip_syncer
    frame_processors_globals.lip_syncer_model = 'wav2lip_gan'
    #frame_colorizer
    frame_processors_globals.frame_colorizer_model = 'ddcolor'
    frame_processors_globals.frame_colorizer_blend = 80
    frame_processors_globals.frame_colorizer_size = '256x256'
    
	# uis
    facefusion.globals.open_browser = None
    facefusion.globals.ui_layouts = None
    #clear processor list
    facefusion.globals.frame_processors = None

	#missing
    facefusion.globals.face_recognizer_model = 'arcface_inswapper'
    return

#download url to folder, keep the file name untouched
def download(url: str, directory:str):
    if not os.path.exists(directory):
        os.makedirs(directory)

    filename = datetime.datetime.now().strftime("%Y%m%d_%H_%M_%S_%f") + "_" + url.split("/")[-1]

    file_name = os.path.join(directory, filename)
    urllib.request.urlretrieve(url, file_name)
    return file_name

class StartRet(BaseModel):
    task_id: str = ""
    result_code: int = 0
    msg: str = ""

dbClient = DbClient()

class RequestBase(ABC):
    def __init__(self): 
        self.fun :str = "uninitialized func"
        self.result:str = ""
        
    @abstractmethod
    def __json__(self):
        pass

    @abstractmethod
    def from_json(cls, json_data):
        pass

    @abstractmethod
    def init_facefusionGlobal(self):
        pass
    def runApi(self):
        result = core.runApi()
        if result == None:
            logging.error(f"failed to handle facefusion fun={self.fun}")
            return None
        else:
            logging.info(f"succeeded in facefusion fun={self.fun}, result = {result}")
            return result
            

class LipSyncerRequest(RequestBase):
    # lip_syncer: videoRetalking; audio, video, enhancementOrNot ( 0/1), 
    # blackwhite2color: frame_colorizer; video/image, blendStrength(weak, 0-1 strong), 
    # imagevideo_enhancer:frame_enhancer + face_enhancer; image/video, enhanceStrength, faceOrNot, faceEnhanceStrength (weak, 0-1 strong)
    # face_swap: face_swapper;  faceReference, faceTarget, fusionStrength (weak, 0-1 strong)
    def __init__(self):
        self.fun:str = 'lip_syncer'
        self.audio:str ='http://audio.com/audio.mp3'
        self.video:str = "http://video.com/video.mp4"
        self.isEnhance:int = 0  # 0: no need, 1, needed
        self.localAudio:str = ""
        self.localVideo:str = ""
    
    def __json__(self):
        return {"fun":self.fun, "audio":self.audio, "video":self.video, "isEnhance": self.isEnhance}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.audio = json_data.get("audio")
        one.fun = json_data.get("fun")
        one.video = json_data.get("video")
        one.isEnhance = json_data.get("isEnhance")
        one.localAudio = download(one.audio, config.config['api']['temp'])
        one.localVideo = download(one.video, config.config['api']['temp'])
        return one
    

    def init_facefusionGlobal(self):
        resetFacefusionGlobals(self.localAudio, self.localVideo)
        facefusion.globals.frame_processors = ['lip_syncer']
        if self.isEnhance != 0:
            facefusion.globals.frame_processors.append("face_enhancer")
            #TODO, might from input params
            frame_processors_globals.face_enhancer_blend = 80
        return 



class Blackwhite2colorRequest(RequestBase):
    # lip_syncer: videoRetalking; audio, video, enhancementOrNot ( 0/1), 
    # blackwhite2color: frame_colorizer; video/image, blendStrength(weak, 0-1 strong), 
    # imagevideo_enhancer:frame_enhancer + face_enhancer; image/video, enhanceStrength, faceOrNot, faceEnhanceStrength (weak, 0-1 strong)
    # face_swap: face_swapper;  faceReference, faceTarget, fusionStrength (weak, 0-1 strong)
    def __init__(self):
        self.fun :str= 'blackwhite2color'
        self.source:str = 'http://photo.com/photo.jpg' #video or image url
        self.strength:float = 0.5 #from 0.0 - 1.0
        self.localSource:str = ""
    
    def __json__(self):
        return {"fun":self.fun, "source":self.source, "strength":self.strength}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.source = json_data.get("source")
        one.fun = json_data.get("fun")
        one.strength = json_data.get("strength")
        one.localSource = download(one.source, config.config['api']['temp'])
        if one.strength > 1 or one.strength < 0:
            raise Exception("wrong param for blackwhite to color")
        return one

    def init_facefusionGlobal(self):
        resetFacefusionGlobals(None, self.localSource)
        facefusion.globals.frame_processors = ['frame_colorizer']
        frame_processors_globals.frame_colorizer_blend = int(self.strength*100)
    
class FrameEnhanceRequest(RequestBase):
    # lip_syncer: videoRetalking; audio, video, enhancementOrNot ( 0/1), 
    # blackwhite2color: frame_colorizer; video/image, blendStrength(weak, 0-1 strong), 
    # imagevideo_enhancer:frame_enhancer + face_enhancer; image/video, enhanceStrength, faceOrNot, faceEnhanceStrength (weak, 0-1 strong)
    # face_swap: face_swapper;  faceReference, faceTarget, fusionStrength (weak, 0-1 strong)
    def __init__(self):
        self.fun:str = 'frameEnhance'
        self.source: str = 'http://photo.com/photo.jpg' #video or image url
        self.strength: float = 0.5 #from 0.0 - 1.0
        self.isFaceEnhance: int = 0 #0, no need; 1, needed
        self.faceEnhanceStrength: float = 0.5 #from 0.0 - 1.0
        self.localSource: str = ""
    
    def __json__(self):
        return {"fun":self.fun, "source":self.source, "strength":self.strength, "isFaceEnhance": self.isFaceEnhance, "faceEnhanceStrength":self.faceEnhanceStrength}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.source = json_data.get("source")
        one.fun = json_data.get("fun")
        one.strength = json_data.get("strength")
        one.isFaceEnhance = json_data.get("isFaceEnhance")
        one.faceEnhanceStrength = json_data.get("faceEnhanceStrength")
        one.localSource = download(one.source, config.config['api']['temp'])
        if one.strength > 1 or one.strength < 0 or one.faceEnhanceStrength > 1 or one.faceEnhanceStrength < 0:
            raise Exception("wrong param for frame enhance")
        return one
    
    def init_facefusionGlobal(self):
        resetFacefusionGlobals(None, self.localSource)
        frame_processors_globals.frame_enhancer_blend = int(self.strength*100)
        facefusion.globals.frame_processors = ['frame_enhancer']
        if self.isFaceEnhance != 0:
            frame_processors_globals.face_enhancer_blend = int(self.faceEnhanceStrength * 100)
            facefusion.globals.frame_processors.append("face_enhancer")

class FaceSwapRequest(RequestBase):
    # lip_syncer: videoRetalking; audio, video, enhancementOrNot ( 0/1), 
    # blackwhite2color: frame_colorizer; video/image, blendStrength(weak, 0-1 strong), 
    # imagevideo_enhancer:frame_enhancer + face_enhancer; image/video, enhanceStrength, faceOrNot, faceEnhanceStrength (weak, 0-1 strong)
    # face_swap: face_swapper;  faceReference, faceTarget, fusionStrength (weak, 0-1 strong)
    def __init__(self):
        self.fun: str = 'face_swap'
        self.faceReference: str = 'http://photo.com/photo.jpg' #image url for face reference
        self.faceTarget: str = "http://facevideo.video"  #image or video for face to be swapped.
        self.strength: float = 0.5 #from 0.0 - 1.0
        self.isFaceEnhance: int = 1 #0, no need; 1, needed
        self.faceEnhanceStrength: float = 0.8 #from 0.0 - 1.0
        self.localFaceReference:str = ""
        self.localFaceTarget:str = ""
    
    def __json__(self):
        return {"fun":self.fun, "faceReference":self.faceReference, "faceTarget":self.faceTarget, "strength": self.strength, "isFaceEnhance":self.isFaceEnhance, "faceEnhanceStrength":self.faceEnhanceStrength}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.faceReference = json_data.get("faceReference")
        one.fun = json_data.get("fun")
        one.faceTarget = json_data.get("faceTarget")
        one.strength = json_data.get("strength")
        one.isFaceEnhance = json_data.get("isFaceEnhance")
        one.faceEnhanceStrength = json_data.get("faceEnhanceStrength")
        one.localFaceReference = download(one.faceReference, config.config['api']['temp'])
        one.localFaceTarget = download(one.faceTarget, config.config['api']['temp'])
        if one.strength > 1 or one.strength < 0 or one.faceEnhanceStrength > 1 or one.faceEnhanceStrength < 0:
            raise Exception("wrong param for face swap")
        
        return one
    
    def init_facefusionGlobal(self):
        resetFacefusionGlobals(self.localFaceReference, self.localFaceTarget)
        frame_processors_globals.reference_face_distance = int(self.strength*100)
        facefusion.globals.frame_processors = ['face_swapper']
        if self.isFaceEnhance != 0:
            frame_processors_globals.face_enhancer_blend = int(self.faceEnhanceStrength * 100)
            facefusion.globals.frame_processors.append("face_enhancer")
            
class StatusRequest(BaseModel):
    task_id: str = ''  #

    def __json__(self):
        return {"task_id":self.task_id}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.task_id = json_data.get("task_id")

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

        #self.www_folder = "/root/facefusion/results"
        self.www_folder = config.config['api']['wwwFolder']    
        public_ip = self.get_public_ip()
        logging.info(f"public ip for this module is {public_ip}")
        self.url_prefix = "http://" + public_ip + ":" + config.config["api"]["webContentPort"] + "/"

        self.version = "facefusion_v1"

        #for worker thread
        self.thread = threading.Thread(target = self.check_task)
        self.thread.daemon = True
        self.threadRunning = True
        self.thread.start()


    def __del__(self):
        self.threadRunning = False

    def say_hello(self):
        logging.debug(f"Hello, {self.name}!")
    
    def get_public_ip(self):
        response = requests.get('https://ifconfig.me/ip')
        return response.text

    def init_task(self, content: Any):
        task = Task()
        task.status = 0 #queued
        task.task_id = datetime.datetime.now().strftime("%Y%m%d_%H_%M_%S_%f")
        task.result = 0
        task.msg = ""
        task.result_code = 100
        task.result_url = ""
        task.param = json.dumps(content)
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
            
            try:
                tasks[0].status = 1
                dbClientThread.updateByTaskId(tasks[0], tasks[0].task_id)
                logging.info(f"start handling task={tasks[0].task_id}")
                ### request need to be inited as different params
                requestJson = json.loads(tasks[0].param)
                request = None
                if(requestJson["fun"] == "lip_syncer"):
                    request = LipSyncerRequest.from_json(json.loads(tasks[0].param))
                elif(requestJson["fun"] == "blackwhite2color"):
                    request = Blackwhite2colorRequest.from_json(json.loads(tasks[0].param))
                elif(requestJson["fun"] == "frameEnhance"):
                    request = FrameEnhanceRequest.from_json(json.loads(tasks[0].param))
                elif(requestJson["fun"] == "face_swap"):
                    request = FaceSwapRequest.from_json(json.loads(tasks[0].param))
                else:
                    logging.error(f"param of {tasks[0].task_id} is {tasks[0].param}, func name is invalid, failed and continue.")
                    tasks[0].result_url = ""
                    tasks[0].result = -1
                    tasks[0].status = 2
                    tasks[0].result_code = 104
                    tasks[0].msg = "something wrong during task=" + task.task_id + ", please contact admin."
                    tasks[0].result_file = ""
                    tasks[0].end_time = datetime.datetime.now()
                    dbClient.updateByTaskId(tasks[0], tasks[0].task_id)
                    continue
                
                request.init_facefusionGlobal()
                task = Task()
                task.assignAll(tasks[0])
                #
                self.do_sample(task, request)
                logging.info(f"finish handling task={tasks[0].task_id}")
            except Exception as e:
                logging.error(f"param of {tasks[0].task_id} is {tasks[0].param}, exception={repr(e)}, failed and continue.")
                tasks[0].result_url = ""
                tasks[0].result = -1
                tasks[0].status = 2
                tasks[0].result_code = 104
                tasks[0].msg = "something wrong during task=" + tasks[0].task_id + ", please contact admin."
                tasks[0].result_file = ""
                tasks[0].end_time = datetime.datetime.now()
                dbClient.updateByTaskId(tasks[0], tasks[0].task_id)
                continue
            
        logging.info("finishing internal thread.")
        return



    #action function, do the real work. 
    def do_sample(self, task:Task, request:Request):
        #empty? checked before, no need
         
         try:
             logging.info(f"start to handle task={task.task_id}")
             #call inference
             resultFile = request.runApi()
             if(resultFile != None):
                 logging.info(f"for task={task.task_id}, succeeded in facefusion {request.fun}, output = {resultFile}")
                 diff = os.path.relpath(resultFile, self.www_folder)
                 #for windows.
                 diff = diff.replace("\\", "/")
                 task.output = self.url_prefix + diff
                 logging.info(f'save_path={resultFile}, www_folder={self.www_folder}, result_url={task.output}, diff={diff}')
                 task.result = 1
                 task.status = 2
                 task.result_code = 100
                 task.msg = "succeeded"
                 task.end_time = datetime.datetime.now()
                 #update item
                 dbClient.updateByTaskId(task, task.task_id)
             else:
                 logging.error(f"failed to handle task {task.task_id}")
                 task.output = ""
                 task.result = -1
                 task.status = 2
                 task.result_code = 104
                 task.msg = "something wrong during task=" + task.task_id + ", please contact admin."
                 task.end_time = datetime.datetime.now()
                 dbClient.updateByTaskId(task, task.task_id)       

         except Exception as e:
             logging.error(f"something wrong during task={task.task_id}, exception={repr(e)}")
             task.output = ""
             task.result = -1
             task.status = 2
             task.result_code = 104
             task.msg = "something wrong during task=" + task.task_id + ", please contact admin."
             task.end_time = datetime.datetime.now()
             dbClient.updateByTaskId(task, task.task_id)

         finally:
             task.status = 2


    # #action function, in sync mode,no task 
    # def do_sampleSync(self, request:Request):
    #     #empty? checked before, no need
    #      try:
    #          logging.info(f"start to handle prompt={request.prompt}")
    #          data = {"model":"llama3","prompt":request.prompt, "stream":False}
    #          dataStr = json.dumps(data)
    #          logging.info(f"before ollama inference, url={self.ollamaUrl}, data={dataStr}")
    #          response = requests.post(self.ollamaUrl, data = dataStr)
    #          logging.info(f"for response = {response.text}, statuscode={response.status_code}") 
    #          if(response.status_code == 200) :
    #              json_data = json.loads(response.text)
    #              logging.info(f"reponse 200, response={json_data['response']}")
    #              return json_data['response']
    #          else:
    #              logging.info(f"reponse = {response.status_code}, failed")
    #              raise requests.exceptions.HTTPError(f'request ollama service error, status = {response.status_code}')        

    #      except Exception as e:
    #          logging.error(f"something wrong during prompt={request.prompt}, exception={repr(e)}")
    #          return f"failed to answer {request.prompt}, please contact admin."
    #      finally:
    #          logging.info(f"finished all for prompt = {request.prompt}")
          
             
    def get_status(self, task_id: str):
        ret = StartRet()
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
        
        retJ = {"data": output, "result_code": ret.result_code, "msg": ret.msg,"task_id":task_id}
        #retJson = json.dumps(retJ)
        logging.debug(f"get_status for task_id={task_id}, return {retJ}" )
        return retJ


description = """
GenAI wrapper for facefusion.

## Items

You can **read items**.

## Users

You will be able to:

* **Create users** (thornbird).
"""

app = FastAPI(title="facefusionAPI",
        description = description,
        version = "1.0")
actor = Actor("facefusion_" + config.config["api"]["nodeName"])


@app.get("/")
async def root():
    return {"message": "Hello World, facefusion, May God Bless You."}

@app.post("/start")
async def start(content : Request):
    """
    - fun: four choices
    -- lip_syncer
    -- blackwhite2color
    -- frameEnhance
    -- face_swap
    - other parameters for each choice, json format
    -- lip_syncer: audio (string, audio url for new audio), video (string, video url to be replaced with new audio), isEnhance (int, 0 no enhance; 1, enhance);
    -- blackwhite2color: source(string, image/video url), strength(float, from 0 to 1, 1 max, 0 no effect),
    -- frameEnhance: source(string, image/video url), strength(float, from 0 to 1, 1 max, 0 no effect), isFaceEnhance(bool, face enhanced or not), faceEnhanceStrength (float, from 0 to 1, 1 max, 0 no effect)
    -- face_swap: faceReference(string, image url for new face), faceTarget(string, image/video url to be relpaced), strength (float, from 0 to 1, 1 max, 0 no effect), isFaceEnhance(bool, face enhanced or not), faceEnhanceStrength (float, from 0 to 1, 1 max, 0 no effect) 
    """
    request_body_bytes = await content.body()
    request_body_string = request_body_bytes.decode("utf-8")
    logging.info(f"before infer, content= {request_body_string}")
    try:
        json_data = await content.json()
        #check the param, fun,
        if json_data['fun'] not in ["lip_syncer", "blackwhite2color", "frameEnhance", "face_swap"] :
            raise Exception("wrong params for facefusion.")
        result = StartRet()


        result.task_id = actor.init_task(json_data)
        result.result_code = 100
        result.msg = "task_id=" + result.task_id + " has been queued."
      
        retJ = {"task_id":result.task_id, "result_code": result.result_code, "msg": result.msg}
        logging.info(f"request content={request_body_string} task_id={result.task_id}, return {retJ}")

		#return response
        return retJ       

    except Exception as e:
        return JSONResponse(content={"task_id":"", "result_code": 104, "msg": "wrong param. Please check if it is json."}, status_code=200)


@app.get("/get")
async def get_status(taskID:str):
    if(taskID == None or taskID == ''):
        logging.error("cannot find taskID, please check the input param")
        return {"data": "", "result_code": 104, "msg": "cannot find param task_id, please check the input param","task_id":""}
    logging.info(f"before startTask, taskID= {taskID}")
    return actor.get_status(taskID)

@app.post("/get")
async def get_status(getRequest:StatusRequest):
    if(getRequest.task_id == None or getRequest.task_id == ''):
        logging.error("cannot find task_id, please check the input param")
        return {"data": "", "result_code": 104, "msg": "cannot find param task_id, please check the input param","task_id":""}
    taskID = getRequest.task_id
    logging.info(f"before startTask, taskID= {taskID}")
    return actor.get_status(taskID)

# @app.post("/startSync")
# async def startSync(content : Request):
#     """
#     - prompt: question sent to llama3
#     """
#     logging.info(f"before infer, content= {content}")
#     result = MyClass()
    
#     data = actor.do_sampleSync(content)
#     result.result_code = 100
#     result.msg = "Done successfully."
      
#     retJ = {"data":data, "result_code": result.result_code, "msg": result.msg}
#     logging.info(f"prompt={content.prompt}  return {retJ}")

#     #return response
#     return retJ

#########for python launch directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
