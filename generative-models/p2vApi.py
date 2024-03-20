#from array import _FloatTypeCode
import array
import os

from pytorch_lightning import seed_everything

from scripts.demo.p2vApi_helper import *

#for fastapi
from fastapi import FastAPI , Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import asyncio
import threading
import logging
import requests

SAVE_PATH = "/data/generative-models/outputs/api/vid/"

VERSION2SPECS = {
    "svd": {
        "T": 14,
        "H": 576,
        "W": 1024,
        "C": 4,
        "f": 8,
        "config": "configs/inference/svd.yaml",
        "ckpt": "checkpoints/svd.safetensors",
        "options": {
            "discretization": 1,
            "cfg": 2.5,
            "sigma_min": 0.002,
            "sigma_max": 700.0,
            "rho": 7.0,
            "guider": 2,
            "force_uc_zero_embeddings": ["cond_frames", "cond_frames_without_noise"],
            "num_steps": 25,
        },
    },
    "svd_image_decoder": {
        "T": 14,
        "H": 576,
        "W": 1024,
        "C": 4,
        "f": 8,
        "config": "configs/inference/svd_image_decoder.yaml",
        "ckpt": "checkpoints/svd_image_decoder.safetensors",
        "options": {
            "discretization": 1,
            "cfg": 2.5,
            "sigma_min": 0.002,
            "sigma_max": 700.0,
            "rho": 7.0,
            "guider": 2,
            "force_uc_zero_embeddings": ["cond_frames", "cond_frames_without_noise"],
            "num_steps": 25,
        },
    },
    "svd_xt": {
        "T": 25,
        "H": 576,
        "W": 1024,
        "C": 4,
        "f": 8,
        "config": "configs/inference/svd.yaml",
        "ckpt": "checkpoints/svd_xt.safetensors",
        "options": {
            "discretization": 1,
            "cfg": 3.0,
            "min_cfg": 1.5,
            "sigma_min": 0.002,
            "sigma_max": 700.0,
            "rho": 7.0,
            "guider": 2,
            "force_uc_zero_embeddings": ["cond_frames", "cond_frames_without_noise"],
            "num_steps": 30,
            "decoding_t": 14,
        },
    },
    "svd_xt_image_decoder": {
        "T": 25,
        "H": 576,
        "W": 1024,
        "C": 4,
        "f": 8,
        "config": "configs/inference/svd_image_decoder.yaml",
        "ckpt": "checkpoints/svd_xt_image_decoder.safetensors",
        "options": {
            "discretization": 1,
            "cfg": 3.0,
            "min_cfg": 1.5,
            "sigma_min": 0.002,
            "sigma_max": 700.0,
            "rho": 7.0,
            "guider": 2,
            "force_uc_zero_embeddings": ["cond_frames", "cond_frames_without_noise"],
            "num_steps": 30,
            "decoding_t": 14,
        },
    },
}
logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)

class MyClass:
    pass

class P2VActor:
    def __init__(self, name: str):
        self.name = name
        #better in config, need modification for every node
        self.www_folder = "/data/generative-models/outputs/api/vid/svd_xt/samples"
        public_ip = self.get_public_ip()
        logging.info(f"public ip for this module is {public_ip}")
        self.url_prefix = "http://" + public_ip + ":8076/"
        #"http://192.168.15.51:7883/"


        self.version = "svd_xt"

        self.version_dict = VERSION2SPECS[self.version]
        self.mode = "img2vid"


        #self.H = self.version_dict["H"]
        #self.W = self.version_dict["W"]
        #self.T = self.version_dict["T"]
        #self.C = self.version_dict["C"]
        #self.F = self.version_dict["f"]
        self.options = self.version_dict["options"]

        #from request
        self.H = 576 #content.height
        self.W = 1024 #content.width
        self.T = 8 #content.frames
        self.F = 8 #content.fps
        self.C = self.version_dict["C"]

        self.state = init_st(self.version_dict, load_filter=True)
        self.model = self.state["model"]

        self.ukeys = set(
            get_unique_embedder_keys_from_conditioner(self.state["model"].conditioner)
        )

        self.value_dict = init_embedder_options(
            self.ukeys,
            {},
            self.F
        )

        self.value_dict["image_only_indicator"] = 0

        self.seed = 23
        seed_everything(self.seed)

        self.save_locally, self.save_path = init_save_locally(
            os.path.join(SAVE_PATH, self.version), init_value=True
        )
        logging.debug(f"save_locally={self.save_locally}, save_path={self.save_path}")
        self.options["num_frames"] = self.T
        logging.debug(f"options={self.options}")

        self.sampler, self.num_rows, self.num_cols = init_sampling(options=self.options)
        
        self.num_samples = self.num_rows * self.num_cols
        logging.debug(f"sample={self.sampler}, num_samples={self.num_samples}")

        self.decoding_t = 2

        self.saving_fps = self.value_dict["fps"]
    
        #print(f"model={self.model}, sample={self.sampler}, value_dict={self.value_dict}, num_samples={self.num_samples}, H={self.H}, \
        #W={self.W}, C={self.C}, F={self.F}, T={self.T}, decoding_t={self.decoding_t}")
    
        self.task_id = None
        self.result = 0 # 0, unknown; -1, failed; 1: success
        self.status = 0 #0, init/empty; 1, doing
        self.msg = "" #error msg
        self.result_code = 100 # based on xme. 
        self.result_url = ""
        self.source_url = ""

    def say_hello(self):
        logging.debug(f"Hello, {self.name}!")
    
    def get_public_ip(self):
        response = requests.get('https://ifconfig.me/ip')
        return response.text

    def init_task(self, url: str):
        self.status = 1  #locked
        self.task_id = self.name + datetime.now().strftime("%f")
        self.result = 0 # 0, unknown; -1, failed; 1: success
        self.msg = "" #error msg
        self.result_code = 100 # based on xme. 
        self.result_url = ""
        self.source_url = url

    def start_task(self, url: str):
        self.do_sample(url)
        return

    #action function, url is the http photo
    def do_sample(self, url: str):
        #empty? checked before, no need
#        if self.status == 0 :
         try:
             img = load_img_for_prediction(self.W, self.H, url)
             #print(f"1 image={img}")
             cond_aug = 0.02
             self.value_dict["cond_frames_without_noise"] = img
             self.value_dict["cond_frames"] = img + cond_aug * torch.randn_like(img)
             self.value_dict["cond_aug"] = cond_aug
             logging.debug(f"2 image={img}")


             out = do_sample(
             self.model,
             self.sampler,
             self.value_dict,
             self.num_samples,
             self.H,
             self.W,
             self.C,
             self.F,
             T=self.T,
             batch2model_input=["num_video_frames", "image_only_indicator"],
             force_uc_zero_embeddings=self.options.get("force_uc_zero_embeddings", None),
             force_cond_zero_embeddings=self.options.get(
                 "force_cond_zero_embeddings", None
             ),
             return_latents=False,
             decoding_t=self.decoding_t,
             )

             samples = None
             samples_z=None
             if isinstance(out, (tuple, list)):
                 samples, samples_z = out
                 logging.debug(f"samples={samples}, samples_z={samples_z}")
             else:
                 samples = out
                 samples_z = None
                 logging.debug(f"samples={samples}")

             output_video = ""
             if self.save_locally:
                  output_video = save_video_as_grid_and_mp4(samples, self.save_path, self.T, fps=self.saving_fps)

             #for output url 
             listA = output_video.split('/')
             listB = self.www_folder.split('/')
             diff = list(set(listA) - set(listB))
             self.result_url = self.url_prefix + '/'.join(diff)
             logging.info(f'save_path={self.save_path}, www_folder={self.www_folder}, result_url={self.result_url}, diff={"/".join(diff)}')
             self.result = 1
             self.status = 0
             self.result_code = 100
             self.msg = "succeeded"

         except Exception as e:
             logging.debug(f"something wrong during task={self.task_id}, exception={repr(e)}")
             self.result_url = ""
             self.result = -1
             self.status = 0
             self.result_code = 103
             self.msg = "something wrong during task=" + self.task_id + ", please contact admin."
         finally:
             self.status = 0
#        elif(self.status == 1):
#            print(f"task={self.task_id} is doing. cannot accept more. no more work")
#        else:
#            print(f"status={self.status}, not 1 or 0, invalid. current task_id={self.task_id} is doing. cannot accept more. no more work")


    def get_status(self, task_id: str):
        ret = MyClass()

        if(task_id != self.task_id):
            #not the current task
            ret.result_url = ""
            ret.result_code = 200
            ret.msg = "cannot find task_id=" + task_id
        else:
            ret.result_url = self.result_url;
            if(self.result == 0):
                ret.result_code = 102
                ret.msg = "task(" + task_id + ") is running."
            elif(self.result == 1): 
                ret.result_code = 100
                ret.msg = "task(" + task_id + ") has succeeded."
            elif(self.result == -1): 
                ret.result_code = 103
                ret.msg = "task(" + task_id + ") has failed."
            else:
                ret.result_code = 103
                ret.msg = "task(" + task_id + ") has failed for uncertainly."     
        
        retJ = {"result_url": ret.result_url, "result_code": ret.result_code, "msg": ret.msg,"api_time_consume":self.T/self.F, "api_time_left":0, "video_w":0, "video_h":0, "gpu_type":"", "gpu_time_estimate":0, "gpu_time_use":0}
        #retJson = json.dumps(retJ)
        logging.debug(f"get_status for task_id={task_id}, return {retJ}" )
        return retJ



app = FastAPI()
p2vActor = P2VActor("node_100")



class Photo2VideoRequest(BaseModel):
    #height: int
    #width: int
    #fps: int
    #frames: int
    image_url: str

@app.get("/")
async def root():
    return {"message": "Hello World, May God Bless You."}

@app.post("/api/photo2Video/startTask")
async def post_t2tt(content : Photo2VideoRequest):
    logging.info(f"before infer, content= {content}")
    result = MyClass()

    if(p2vActor.status != 0):
        logging.warn(f"engine is busy with task={p2vActor.task_id}, cannot accept more.")
        result.task_id = ""
        result.result_code = 203
        result.msg = "engine is busy with task, cannot accept more."
    else:
        p2vActor.init_task(content.image_url)
        result.task_id = p2vActor.task_id
        result.result_code = 100
        result.msg = "task_id=" + p2vActor.task_id + " has started."
        loop = asyncio.get_event_loop()
        #task = loop.create_task(p2vActor.start_task(p2vActor.source_url))
        thread = threading.Thread(target = p2vActor.start_task, args=(p2vActor.source_url,))
        thread.daemon = True
        thread.start()
        

    retJ = {"task_id":result.task_id, "result_code": result.result_code, "msg": result.msg}
    #response = Response(content=retJ, media_type="application/json")
    #retJson = json.dumps(retJ)
    logging.info(f"url={content.image_url}, task_id={result.task_id}, return {retJ}")

    #return response
    return retJ

@app.get("/api/photo2Video/getStatus")
async def get_status(taskID:str):
    logging.info(f"before get_status, taskID= {taskID}")
    return p2vActor.get_status(taskID)
