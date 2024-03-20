#from asyncio.windows_events import NULL
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import logging
import datetime
import threading

#from https://github.com/OpenTalker/video-retalking
'''
VideoReTalking, a new system to edit the faces of a real-world talking head video according to input audio, producing a high-quality and lip-syncing output video even with a different emotion. 
Our system disentangles this objective into three sequential tasks:

(1) face video generation with a canonical expression
(2) audio-driven lip-sync and
(3) face enhancement for improving photo-realism.
python3 inference.py \
  --face examples/face/1.mp4 \
  --audio examples/audio/1.wav \
  --outfile results/1_1.mp4
 others: 
  --exp_img: Pre-defined expression template. The default is "neutral". You can choose "smile" or an image path.
--up_face: You can choose "surprise" or "angry" to modify the expression of upper face with GANimation.
from inference_utils:
    parser.add_argument('--DNet_path', type=str, default='checkpoints/DNet.pt')
    parser.add_argument('--LNet_path', type=str, default='checkpoints/LNet.pth')
    parser.add_argument('--ENet_path', type=str, default='checkpoints/ENet.pth') 
    parser.add_argument('--face3d_net_path', type=str, default='checkpoints/face3d_pretrain_epoch_20.pth')                      
    parser.add_argument('--face', type=str, help='Filepath of video/image that contains faces to use', required=True)
    parser.add_argument('--audio', type=str, help='Filepath of video/audio file to use as raw audio source', required=True)
    parser.add_argument('--exp_img', type=str, help='Expression template. neutral, smile or image path', default='neutral')
    parser.add_argument('--outfile', type=str, help='Video path to save result')

    parser.add_argument('--fps', type=float, help='Can be specified only if input is a static image (default: 25)', default=25., required=False)
    parser.add_argument('--pads', nargs='+', type=int, default=[0, 20, 0, 0], help='Padding (top, bottom, left, right). Please adjust to include chin at least')
    parser.add_argument('--face_det_batch_size', type=int, help='Batch size for face detection', default=4)
    parser.add_argument('--LNet_batch_size', type=int, help='Batch size for LNet', default=16)
    parser.add_argument('--img_size', type=int, default=384)
    parser.add_argument('--crop', nargs='+', type=int, default=[0, -1, 0, -1], 
                        help='Crop video to a smaller region (top, bottom, left, right). Applied after resize_factor and rotate arg. ' 
                        'Useful if multiple face present. -1 implies the value will be auto-inferred based on height, width')
    parser.add_argument('--box', nargs='+', type=int, default=[-1, -1, -1, -1], 
                        help='Specify a constant bounding box for the face. Use only as a last resort if the face is not detected.'
                        'Also, might work only if the face is not moving around much. Syntax: (top, bottom, left, right).')
    parser.add_argument('--nosmooth', default=False, action='store_true', help='Prevent smoothing face detections over a short temporal window')
    parser.add_argument('--static', default=False, action='store_true')

    
    parser.add_argument('--up_face', default='original')  'sad', 'angry', 'surprise'
    parser.add_argument('--one_shot', action='store_true')
    parser.add_argument('--without_rl1', default=False, action='store_true', help='Do not use the relative l1')
    parser.add_argument('--tmp_dir', type=str, default='temp', help='Folder to save tmp results')
    parser.add_argument('--re_preprocess', action='store_true')
'''

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

#for videoRetalking for video and photo
class Task(Base):
    __tablename__ = "task"
    id = Column(Integer, primary_key=True)
    task_id = Column(String(256), default = "")
    result = Column(Integer, default = 0) #0, unknown; -1, failed; 1: success
    status = Column(Integer, default = 0) #0, queue; 1, doing, 2, finished 
    msg = Column(String(512), default = "")
    result_code = Column(Integer, default = 100) 
    result_url = Column(String(512), default = "")
    result_file = Column(String(512), default = "")
    result_length = Column(Float, default = 0.0) 
    width =  Column(Integer, default = 1)
    height = Column(Integer, default = 1)
    start_time = Column(DateTime, default = datetime.datetime.now)
    end_time = Column(DateTime , default = datetime.datetime.now)
    param = Column(String(1024), default = "")

    def assignWithoutId(self, other):
        self.task_id = other.task_id
        self.result = other.result
        self.status = other.status
        self.msg = other.msg
        self.result_code = other.result_code
        self.result_url = other.result_url
        self.result_file = other.result_file
        self.result_length = other.result_length
        self.width = other.width
        self.height = other.height
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
        self.result_url = other.result_url
        self.result_file = other.result_file
        self.result_length = other.result_length
        self.width = other.width
        self.height = other.height
        self.start_time = other.start_time
        self.end_time = other.end_time
        self.param = other.param

#very simple client, no care for transaction/rollback. only single thread lock
class DbClient:
    def __init__(self):
        self.engine = create_engine('mysql+mysqlconnector://root:QmKuwq8kSQ8b@localhost:3306/ipollo')
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