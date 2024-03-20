kind: str = 'photo' # photo, video
obj: str = 'any' #any, human, cloth
url: str = '' #
bgColor: str = '0,255,0,100' #RGBA, Green in default

bgColor设置为0,255,0,100，为纯色的绿色；0,0,0,0背景透明，但是物体边缘采用了黑色（0，0，0）勾边。

对于视频，输出的mp4并不能支持透明底，而是相当于A = 100
换成webm，就可以支持A=0