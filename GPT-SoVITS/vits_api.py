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
from GPT_SoVITS.inference_webui_simple import get_tts_wav, i18n

from orm import *
import time

from Process import *
from PIL import Image
import soundfile as sf
from pydub import AudioSegment

import langid

logging.basicConfig(
    # format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    format='[%(asctime)s %(levelname)-7s (%(name)s) <%(process)d> %(filename)s:%(lineno)d] %(message)s',
    level=logging.INFO
)


class AddVoiceRt(BaseModel):
    voice_id: int
    result_code: int
    msg: str

class TTSRt(BaseModel):
    srt: str
    audio: str
    result_code: int
    msg: str

class CommonRt(BaseModel):
    result_code: int
    msg: str

dbClient = DbClient()


class TTSRequest(BaseModel):
    voiceId: int = '' #must, voice id from adding voice
    inferText: str = '' #must, content for tts
    inferLang: str = 'auto' #optional, auto, zh, jp, en, ko,

    def __json__(self):
        return {"voiceId":self.voiceId, "inferText":self.inferText, "inferLang":self.inferLang}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.voiceId = json_data.get("voiceId")
        one.inferText = json_data.get("inferText")
        one.inferLang = json_data.get("inferLang")

        return one

class AddRequest(BaseModel):
    refAudio: str = ''  #must, url for ref audio
    refText: str = '' #optional, ref audio content
    refLanguage: str = 'auto' #optional, auto, zh, jp, en, ko,

    def __json__(self):
        return {"refAudio":self.refAudio, "refText":self.refText, "refLanguage":self.refLanguage}

    @classmethod
    def from_json(cls, json_data):
        one = cls()
        one.refAudio = json_data.get("refAudio")
        one.refText = json_data.get("refText")
        one.refLanguage = json_data.get("refLanguage")

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

        self.www_folder = "/data/GPT-SoVITS/results"
        if not os.path.exists(self.www_folder):
            os.makedirs(self.www_folder)
            logging.info(f"created result folder {self.www_folder}")
        else:
            logging.info(f"result folder {self.www_folder} exists")

        self.voice_folder = "/data/GPT-SoVITS/voices"
        if not os.path.exists(self.voice_folder):
            os.makedirs(self.voice_folder)
            logging.info(f"created voices folder {self.voice_folder}")
        else:
            logging.info(f"voices folder {self.voice_folder} exists")

        public_ip = self.get_public_ip()
        logging.info(f"public ip for this module is {public_ip}")
        self.url_prefix = "http://" + public_ip + ":9000/"

        self.version = "gpt-soVits_v1"

        self.threadRunning = True

    def __del__(self):
        self.threadRunning = False

    def say_hello(self):
        logging.debug(f"Hello, {self.name}!")
    
    def get_public_ip(self):
        response = requests.get('https://ifconfig.me/ip')
        return response.text


    #download url to folder, keep the file name untouched
    def download(self, url: str, directory:str):
        if not os.path.exists(directory):
            os.makedirs(directory)

        filename = url.split("/")[-1]
        filename = datetime.datetime.now().strftime("%Y%m%d_%H_%M_%S_%f") + "_" + filename

        file_name = os.path.join(directory, filename)
        urllib.request.urlretrieve(url, file_name)
        return file_name

    #for voice action
    def addVoice(self, content : AddRequest) -> int:
        #dl file to voices
        try:
             logging.info(f"download refAudio file:{content.refAudio} to {self.tmp_folder}")
             refAudio_file = self.download(content.refAudio, self.tmp_folder)
             sourceAudio = AudioSegment.from_file(refAudio_file)
             audio_length = len(sourceAudio)
             logging.info(f"downloaded ref audio, name={refAudio_file}, length={audio_length}")

             #limit to 10000 >  > 3000, 
             refAudio_file_new = ""
             if(audio_length < 3100): #ms
                 logging.error(f"ref audio length ={audio_length}, less than 3100ms")
                 return -1
             #if(audio_length > 9500): #ms
             #    logging.error(f"ref audio length ={audio_length}, more than 9500ms")
             #    return -1
             if(audio_length > 8000): #ms
                 logging.info(f"audio length > 8000, should limit to 8000ms, dled audio sampleRate={sourceAudio.frame_rate}, channels={sourceAudio.channels}")
                 audio_8_sec_temp = sourceAudio[:8000]
                 audio_8_sec = audio_8_sec_temp.set_channels(sourceAudio.channels)
                 filename, ext = refAudio_file.rsplit(".",1)
                 refAudio_file_new = f"{filename}_8sec.{ext}"
                 #sf.write(refAudio_file_new, audio_8_sec.get_array_of_samples(), sourceAudio.frame_rate)
                 audio_8_sec.export(refAudio_file_new, format="mp3")
                 refAudio_file = refAudio_file_new

             newOne = Voice()
             newOne.ref_audio = refAudio_file
             newOne.ref_lang = content.refLanguage
             newOne.ref_text = content.refText
             newOne.create_time = datetime.datetime.now()
             newOne.addParam = json.dumps(content.__json__())
             dbClient.addVoice(newOne)
             return newOne.id

        except Exception as e:
            logging.error(f"something wrong during add voice, refAudioUrl={content.refAudio}, exception={repr(e)}")

        return -1

    def deleteVoice(self, voiceId: int) ->CommonRt :
        ret = CommonRt(result_code=-1, msg="")

        try:
             dbClient.deleteByVoiceId(voiceId)
             ret.msg = "succeeded in deleting voice {voiceId}"
             ret.result_code = 100

        except Exception as e:
            logging.error(f"something wrong during delete voice, voiceid={voiceId}, exception={repr(e)}")
            ret.msg(f"something wrong during delete voice, voiceid={voiceId}, exception={repr(e)}")
            ret.result_code = 104

        return ret

    def detect_language(self, text:str):
        lang, confidence = langid.classify(text)
        return lang, confidence

    #for real tts
    def tts(self, voice: TTSRequest) ->TTSRt :
        ret = TTSRt(srt = "", audio = "", result_code=-1, msg="")

        try:
            #find the voice
            voiceItems = dbClient.queryByVoiceId(voice.voiceId)
            voiceItem = voiceItems[0]
            if(voiceItem == None):
                logging.error(f"cannot find voice, id={voice.voiceId}")
                return None
            #tts
            #language, confidence = self.detect_language(voice.inferText)
            #logging.info(f"for text {voice.inferText}, detect_language returns {language}, {confidence}")
            language = voice.inferLang
            cut = i18n("按标点符号切")
            if(language == "en"):
                cut = i18n("按英文句号.切")
            if(language == "zh"):
                cut = i18n("按中文句号。切")
            
            synthesis_result = get_tts_wav(ref_wav_path=voiceItem.ref_audio, 
                                       prompt_text= voiceItem.ref_text,
                                       prompt_language=voiceItem.ref_lang, 
                                       text=voice.inferText,
                                       text_language=voice.inferLang, how_to_cut=cut)
            
            result_list = list(synthesis_result)
            
            if result_list:
                #here, it is data self, not file.
                timeNow = datetime.datetime.now().strftime("%Y%m%d_%H_%M_%S_%f")
                last_sampling_rate, last_audio_data, subs = result_list[-1]
                resultFile = "result_" + timeNow + "_" + str(voice.voiceId) + ".wav"
                output_wav_path = os.path.join(self.www_folder, resultFile) 
                sf.write(output_wav_path, last_audio_data, last_sampling_rate)
                #for mp3
                sound = AudioSegment.from_file(output_wav_path)
                mp3File = "result_" + timeNow + "_" + str(voice.voiceId) + ".mp3"
                output_mp3_path = os.path.join(self.www_folder, mp3File)
                sound.export(output_mp3_path, format="mp3")
                #for srt
                srtFile = "result_" + timeNow + "_" + str(voice.voiceId) + ".srt"
                output_srt_path = os.path.join(self.www_folder, srtFile)
                subs.save(output_srt_path, encoding='utf-8')

                #for output url 
                diff = os.path.relpath(output_mp3_path, self.www_folder)
                ret.audio = self.url_prefix + diff
                diffSrt = os.path.relpath(output_srt_path, self.www_folder)
                ret.srt = self.url_prefix + diffSrt

                logging.info(f"succeeded in tts, voiceid={voice.voiceId}, inferText={voice.inferText}, \
                   inferLang={voice.inferLang}, result={output_mp3_path}, outputUrl={ret.audio}")

                ret.msg = "succeeded in tts voice=" + str(voice.voiceId) + ", inferText=" + voice.inferText \
                    + ", output=" + ret.audio + ", srt=" + ret.srt
                ret.result_code = 100

        except Exception as e:
            logging.error(f"something wrong during tts voice, voiceid={voice.voiceId}, inferText={voice.inferText}, exception={repr(e)}")
            ret.msg = "something wrong during delete voice,  voiceid=" + str(voice.voiceId) + f", inferText={voice.inferText}, exception={repr(e)}"
            ret.result_code = 104

        return ret


description = """
vitsAPI is based on vits opersource.

## Items

You can **read items**.

## Users

You will be able to:

* **Create users** (thornbird).
"""

appVits = FastAPI(title="vitsAPI",
        description = description,
        version = "1.0")
actor = Actor("vits_node_100")


@appVits.get("/")
async def root():
    return {"message": "Hello World, Vits comes, May God Bless You."}

@appVits.post("/addVoice", response_model=AddVoiceRt)
async def addVoice(content : AddRequest):
    """
    - refAudio: str = ''  #must, url for ref audio
    - refText: str = '' #optional, ref audio content
    - refLanguage: str = 'auto' #optional, auto, zh, jp, en, ko,
    """
    logging.info(f"before addVoice, content= {content}")
    result = AddVoiceRt(voice_id=0, result_code=0, msg="")


    result.voice_id = actor.addVoice(content)
    if(result.voice_id == -1):
        result.result_code = 104
        result.msg = "cannot add voice, please contact admin"
    else:
        result.result_code = 100
        result.msg = "voice=" + str(result.voice_id) + " has been added."
      
    retJ = {"voice_id":result.voice_id, "result_code": result.result_code, "msg": result.msg}
    logging.info(f"refAudio={content.refAudio}, result.voiceId={result.voice_id}, return {retJ}")

    #return response
    return retJ

@appVits.get("/deleteVoice", response_model=CommonRt)
async def deleteVoice(voiceId : int):
    """
    - voiceId: int = ''  # must, return from addVoice
    """
    logging.info(f"before deleteVoice, voiceId= {voiceId}")
    result = CommonRt(result_code=0, msg="")


    result = actor.deleteVoice(voiceId)
      
    retJ = {"result_code": result.result_code, "msg": result.msg}
    logging.info(f"delete voice id={voiceId}, result_code={result.result_code}, return {retJ}")

    #return response
    return retJ

@appVits.post("/tts", response_model=TTSRt)
async def tts(content : TTSRequest): 
    """
    - voiceId: int = '' #must, voice id from adding voice
    - inferText: str = '' #must, content for tts
    - inferLang: str = 'auto' #optional, auto, zh, jp, en, ko,
    """
    logging.info(f"before infer, content= {content}")
    result = TTSRt(srt="", audio="", result_code=0, msg="")


    result = actor.tts(content)
    #result.result_code = 100
    #result.msg = "voiceId=" + str(content.voiceId) + " has finished. inferText=" + content.inferText;
    result.msg = "voiceId=" + str(content.voiceId) + " has finished"
    
    retJ = {"srt":result.srt, "audio": result.audio, "msg": result.msg, "result_code": result.result_code}
    logging.info(f"text={content.inferText}, voiceId={content.voiceId}, return {retJ}")

    #return response
    return retJ



