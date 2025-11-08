import json
import socket
import crc
import asyncio
import threading
import time
import random

CRC_CALCULATOR = crc.Calculator(crc.Crc32.CRC32)

def getTime():
    return int(time.time())


def registration_message(sensor_id, token):
    
    message = {
        "header": {
        "msg_type": "registration",
        "time_stamp": getTime(),
        "sensor_id": sensor_id,
        "battery": "high",
        "token": token,
        "crc": "",
        "data": {"registration": 1}
        }
    }
    
    return json_dump(message)

def sensor_message(sensor_id, token, data, battery, msg_type, timestamp):
    
    if timestamp == 0:
        time_stamp = getTime()
    else: time_stamp = timestamp
        
    message = {
        "header": {
        "msg_type": msg_type,
        "time_stamp": time_stamp,
        "sensor_id": sensor_id,
        "battery": battery,
        "token": token,
        "crc": "",
        "data": data
        }
    }
    
    return json_dump(message)

def json_dump(message):
    json_message = json.dumps(message, separators=(",", ":"), sort_keys=True)
    
    checksum = CRC_CALCULATOR.checksum(json_message.encode("utf-8"))
    
    message["header"]["crc"] = checksum
    
    return json.dumps(message, separators=(",", ":"), sort_keys=True)

