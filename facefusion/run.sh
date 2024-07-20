#!/bin/bash
echo 启动中，根据机器情况需要等待30几秒…… 
eval "$(conda shell.bash hook)"
lsof -i:6006
source /etc/network_turbo
source /etc/network_turbo && source activate facefusion
cd /root/facefusion
nohup python run.py --output /root/outputs --execution-providers cuda cpu --skip-download > face.log 2>&1 & 
