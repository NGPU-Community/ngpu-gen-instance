
import edge_tts
import tempfile

#for fastapi
from fastapi import FastAPI , Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging
import time
from tts_voice import tts_order_voice
import shutil
import requests
import datetime
import json
import os

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)

class MyClass:
    pass

g_result_url = ""
g_result_code = 100

class Request(BaseModel):
    content: str = "普通话"  # input message
    voicer: str = "普通话 (中国大陆)-Yunxia-男" # 普通话 (中国大陆)-Xiaoxiao-女


    def __json__(self):
        return {"content":self.content, "voicer":self.voicer}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.content = json_data.get("content")
        one.voicer = json_data.get("voicer")
        return one

def get_public_ip():
    try:
        response = requests.get('https://ifconfig.me/ip')
        return response.text
    except Exception as e:
        logging.error(f"something wrong, get publicIp,exception={repr(e)}")
        return "112.17.252.163"


async def text_to_speech_edge(request:Request):
    logging.info("21")
    voice = tts_order_voice[request.voicer]
    logging.info("3")
    text = request.content
    communicate = edge_tts.Communicate(text, voice)
    logging.info("4")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        tmp_path = tmp_file.name
    logging.info(f"temp file = {tmp_path}")

    await communicate.save(tmp_path)
    #add check for audio file size, in case of result file zero
    logging.info("5")
    global g_result_code
    if os.path.getsize(tmp_path) == 0:
        logging.error(f"result file from edge is zero lenght, {tmp_path}")
        g_result_code = 200
        return
    www_folder = "/var/www/html/results"
    url_prefix = "http://" + get_public_ip() + ":7991/results"

    result_file = "/" + datetime.datetime.now().strftime("%Y%m%d_%H_%M_%S_%f") + ".mp3"
    result_full_file = www_folder + result_file
    logging.info(f"mv temp={tmp_path} to {result_full_file}")

    shutil.move(tmp_path, result_full_file)
    os.chmod(result_full_file, 0o755)

    global g_result_url
    g_result_url = url_prefix + result_file
    logging.info(f"finished edge tts, {g_result_url}")
    g_result_code = 100
    return


app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World, sad, May God Bless You."}

@app.post("/tts")
async def post_t2tt(request :Request):
    logging.info(f"before infer, content= {request}")
    result = MyClass()

    global g_result_url
    g_result_url = ""
    global g_result_code 
    g_result_code = 100

    try:

        if(tts_order_voice[request.voicer] == None):
            logging.error(f"cannot find the voicer, {request.voicer}")
            result.result_code = 202
            result.msg = f"cannot find the voicer, {request.voicer}"
            result.task_id = -1
            result.result_url = ""
        else:
            logging.info("2")
            await text_to_speech_edge(request)
            result.task_id = "this_one"
            result.result_code = g_result_code
            result.msg = "task_id=" + result.task_id + f" has been finished, url={g_result_url}."
            result.result_url = g_result_url
      
    except Exception as e:
        logging.error(f"something wrong, request: voicer={request.voicer}, content={request.content},exception={repr(e)}")
        result.result_code = 202
        result.msg = f"unknown error"
        result.task_id = -1
        result.result_url = ""

    retJ = {"task_id":result.task_id, "result_code": result.result_code, "msg": result.msg, "result_url": result.result_url}


    return retJ

@app.get("/ttsVoices")
async def get_ttsVoices():
    json_array= json.dumps(tts_order_voice, ensure_ascii=False).encode('utf8')

    return Response(content=json_array, media_type="application/text")
