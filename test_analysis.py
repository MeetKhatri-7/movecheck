import sys
import os
import requests

url = "http://localhost:5001/process"
# create a dummy video file
os.system("ffmpeg -f lavfi -i color=c=blue:s=320x240:d=1 -vframes 30 dummy.mp4 2>/dev/null")

with open('dummy.mp4', 'rb') as f:
    files = {'side': ('dummy.mp4', f, 'video/mp4')}
    data = {
        'assessmentType': 'strength',
        'slug': 'back-squat',
        'weightMax': '100',
        'repsMax': '5',
        'targetReps': '5'
    }
    try:
        res = requests.post(url, files=files, data=data)
        print("Status:", res.status_code)
        print("Response:", res.json())
    except Exception as e:
        print("Error:", e)

os.system("rm dummy.mp4")
