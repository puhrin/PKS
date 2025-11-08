import json
import socket
import crc
import threading
import time
import messages
import random

import struct

CRC_CALCULATOR = crc.Calculator(crc.Crc32.CRC32)

unix_time = 0

LOCK = threading.Lock()

sensors = {
    "ThermoNode": None,
    "WindSense" : None,
    "RainDetect": None,
    "AirQualityBox": None
}

### binary
sensors_map = {
    "ThermoNode": 0,
    "WindSense" : 1,
    "RainDetect": 2,
    "AirQualityBox": 3
}

msg_type_mag = {
    "error": 0,
    "activity": 1,
    "ack": 2,
    "data": 3,
    "registration": 4
}

###binary

class Client:
    
    def __init__(self, client_ip, client_port, server_ip, server_port) -> None:
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP socket creation
        
        self.sock.settimeout(0.1) ##########
        
        self.client_ip = client_ip
        self.client_port = client_port
        
        self.server_ip = server_ip
        self.server_port = server_port
        
        self.sock.bind((self.client_ip, self.client_port))

    def receive(self):
        try:
            data = None
            data, self.server = self.sock.recvfrom(1024) # buffer size is 1024 bytes
            return data #1
        except socket.timeout:
            return None ############

    def send_message(self, message):
        self.sock.sendto(bytes(message,encoding="utf8"),(self.server_ip,self.server_port))

    def quit(self):
        self.sock.close() # correctly closing socket
        print("Client closed..")

def menu():
    
    print("\n --- Menu --- ")
    print(" 1: Set IPs and ports (configure) ")
    print(" 2: auto message generation ")
    print(" 3: send custom message ")
    print(" q: leave menu  ")
    print(" ------------")
    
    choice = input(" Input your choice: ")
    
    return choice

def configure():
    server_ip = input(" server 'ip.ip.ip.ip' = ")
    server_port = int(input( " server 'port' = "))
    client_ip = input(" client 'ip.ip.ip.ip' = ")
    client_port = int(input( " client 'port' = "))
            
    client = Client(client_ip, client_port, server_ip, server_port)
    print(f"{'\033[32m'} IPs and ports succesfully set!{'\033[0m'}")
    return client

def register(sensor_id, client):
    json_message = messages.registration_message(sensor_id, None)
    client.send_message(json_message)
    msg = client.receive()
    token = process_message(msg)["header"]["token"]
    sensors[sensor_id] = [token, "high", [], 1, []]
        
def process_message(data):
    data = data.decode("utf-8")
    return json.loads(data)

def create_data(sensor_id): #param1, param2, param3, param4
    if sensor_id == "ThermoNode":
        message = {
            "temperature": round(random.uniform(-50.0, 60.0), 1),
            "humidity": round(random.uniform(0.0, 100.0), 1),
            "dew_point": round(random.uniform(-50.0, 60.0), 1),
            "pressure": round(random.uniform(800.00, 1100.00), 2) 
        }
        
    elif sensor_id == "WindSense":
        message = {
            "wind_speed": round(random.uniform(0, 50), 1),
            "wind_gust": round(random.uniform(0, 70), 1),
            "wind_direction": random.randint(0,359),
            "turbulence": round(random.uniform(0, 1), 1)
        }
        
    elif sensor_id == "RainDetect":
        message = {
            "rainfall": round(random.uniform(0, 500), 1),
            "soil_moisture": round(random.uniform(0, 100), 1),
            "flood_risk": random.randint(0,3),
            "rain_duration": random.randint(0,60)
        }
        
    elif sensor_id == "AirQualityBox":
        message = {
            "co2": random.randint(300,5000),
            "ozone": round(random.uniform(0,500), 1),
            "air_quality_index": random.randint(0, 500)
        }
        
    return message
    
    

def auto_send_data(client):
    global unix_time
    time.sleep(10)
    
    while True:
        
        unix_time = int(time.time())
        
        for key, value in sensors.items():
            
            with LOCK:
        
                token, battery, last_msg, active, ack = value
                if token != None and active:
            
                    dataflow = create_data(key)
                    msg = messages.sensor_message(key, value[0], dataflow, battery, "data", 0)
                
                    sensors[key][2].append(json.loads(msg))
                    sensors[key][4].append(0)
                    client.send_message(msg)
                

                
        time.sleep(15)
        
def receive_data(client):
    
    inactivity_counter = 0
    
    while True:
        
        msg = client.receive()
        
        if msg is None:
            continue
        
        json_msg = process_message(msg)
        
        with LOCK:
            if json_msg["header"]["msg_type"] == "error":
                
                sensor = json_msg["header"]["sensor_id"]
                time_stamp = json_msg["header"]["time_stamp"]
                
                for corrupted_message in sensors[sensor][2]:        # sent messages
                    if corrupted_message["header"]["time_stamp"] == time_stamp:
                        
                        corrupted_message["header"]["crc"] = ""
                        corrupted_message["header"]["msg_type"] = "error"
                        corrupted_string = json.dumps(corrupted_message,separators=(",", ":"), sort_keys=True)
                        checksum = CRC_CALCULATOR.checksum(corrupted_string.encode("utf-8"))
                        corrupted_message["header"]["crc"] = checksum
                        corrupted_message = json.dumps(corrupted_message, separators=(",", ":"), sort_keys=True)
                        client.send_message(corrupted_message)
            
            elif json_msg["header"]["msg_type"] == "activity":
                sensor_id = json_msg["header"]["sensor_id"]
                sensor = sensors[sensor_id]
                
                inactivity_counter += 1
                
                if not sensor[3] and inactivity_counter >= 2:
                    sensor[3] = 1
                    token = json_msg["header"]["token"]
                    battery = sensor[1]
                    msg = messages.sensor_message(sensor_id, token, {"active": 1}, battery, "activity", 0)
                    client.send_message(msg)
                    inactivity_counter = 0
            
            elif json_msg["header"]["msg_type"] == "ack":
                
                sensor_id = json_msg["header"]["sensor_id"]
                
                token, battery, last_msg, active, ack = sensors[sensor_id]
                
                for i in range(len(ack)):
                    if ack[i] == 0:
                        if last_msg[i]["header"]["time_stamp"] == json_msg["header"]["time_stamp"]:
                            ack[i] = 1
                        
                
                     
def ack_data(client):
    
    while True:
        
        for key, value in sensors.items():
            
            with LOCK:
                token, battery, last_msg, active, ack = value
                
                for i in range(len(ack)):
                    
                    time_stamp = last_msg[i]["header"]["time_stamp"]
                
                    if ack[i] == 0 and unix_time - time_stamp > 1:
                        
                        msg_string = json.dumps(last_msg[i], separators=(",", ":"), sort_keys=True)
                    
                        client.send_message(msg_string)
                    
        time.sleep(5)
                
                
                       
if __name__=="__main__":
    
    client = None
    corrupted_msg = None
    
    while (True):
        
        choice = menu()
        
        if choice == "1":
            
            client = configure()
        
        elif choice == "2":
            
            if client != None:
                
                for sensor_id in sensors:
                    register(sensor_id, client)
                
                threading.Thread(target=auto_send_data,args=(client,), daemon=True).start()
                threading.Thread(target=receive_data,args=(client,), daemon=True).start()
                threading.Thread(target=ack_data,args=(client,), daemon=True).start()####
            
            else:
                print(f"{'\033[32m'} IPs and ports not configured!{'\033[0m'} ")
        
        elif choice == "3":
            
            if client != None:
                print(" --- Select sensor --- \n")
                i = 1
                
                for key, value in sensors.items():
                    
                    token, battery, last_msg, active, ack = value
                    
                    if token != None:
                        
                        print(f" {i}. {key} \n")
                        i += 1
                    
                if i == 1:
                    print(" sensors do not have tokens yet! \n ")
                    continue
                
                sensorchoice = "none"
                
                while sensorchoice not in sensors:       
                    sensorchoice = input(" Input your choice: (string name) ")
                
                #token = sensors[sensorchoice]
                
                print("\n --- message type --- \n")
                print(" 1. low battery \n")
                print(" 2. error in message \n")
                print(" 3. sensor activity \n")
                
                options = ["1", "2", "3"]
                
                typechoice = -1
                while typechoice not in options:
                    typechoice = input(" Input your choice: ")
            
                if typechoice == "1":
                    sensors[sensorchoice][1] = "low"
                    
                elif typechoice == "2":
                    dataflow = create_data(sensorchoice)
                    token, battery, last_msg, active, ack = sensors[sensorchoice]
                    corrupted_msg = messages.sensor_message(sensorchoice, token, dataflow, battery, "data", 0)
                    json_msg = json.loads(corrupted_msg)
                    json_msg["header"]["crc"] = "0"
                    msg = json.dumps(json_msg, separators=(",", ":"))
                    sensors[sensorchoice][2].append(json.loads(msg))
                    client.send_message(msg)
                    
                elif typechoice == "3":
                    sensors[sensorchoice][3] = 0 # active = 0
                    
                    
                    
                    
                
                   
            else:
                print(f"{'\033[32m'} IPs and ports not configured!{'\033[0m'} ")
            
            
        elif choice == "q" and client != None:
            
            client.quit()
            break
        
        else:
            
            print(" wrong input! \n")
    
        
        
    
    
   