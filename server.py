import json
import socket
import crc
import threading
import time
import messages

CRC_CALCULATOR = crc.Calculator(crc.Crc32.CRC32)

LOCK = threading.Lock()

sensors = {
    "ThermoNode": None,
    "WindSense" : None,
    "RainDetect": None,
    "AirQualityBox": None
}

token_counter = 0
unix_time = 0

class Server:
    
    def __init__(self, server_ip, server_port) -> None:
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        
        self.sock.bind((server_ip, server_port)) 

    def receive(self):
        data = None
        while data == None:
            data, self.client= self.sock.recvfrom(1024) #buffer size is 1024 bytes
        
        return data, self.client

    def send_response(self, data):
        self.sock.sendto(data.encode("utf-8"),self.client)

    def quit(self):
        self.sock.close() # correctly closing socket
        print("Server closed")


def menu():
    
    print("\n --- Menu --- ")
    print(" 1: Set IP and port (configure) ")
    print(" 2: listen ")
    print(" 3: do not confirm message ")
    print(" q: quit ")
    print(" ------------")
    
    choice = input(" Input your choice: ")
    
    return choice

    
       
def process_message(data, server):
    dictionary = data.decode("utf-8")
    dictionary = json.loads(dictionary)
    
    header = dictionary.get("header", {})
    msg_type = header.get("msg_type")
    crc = header.get("crc")
    
    token = header.get("token")  
    sensor_id = header.get("sensor_id")
    battery = header.get("battery")
    
    data = data.decode("utf-8")
    data = json.loads(data)
    data["header"]["crc"] = ""
    
    data = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    
    checksum = CRC_CALCULATOR.checksum(data)
    
    
    if crc != checksum:
        handle_corrupted(dictionary, server, 0)
    
    elif msg_type == "registration":
        handle_registration(dictionary, server)
        
    elif msg_type == "data":
        handle_data(dictionary, server)
        
    elif msg_type == "error":
        handle_corrupted(dictionary, server, 1)
    
    elif msg_type == "activity":
        handle_reconnect(dictionary, server)
        

def handle_reconnect(dictionary, server):
    header = dictionary["header"]
    sensor = header["sensor_id"]
    handle_data(dictionary, server)
    print(f" \033[31m INFO: {sensor} RECONNECTED!  \033[0m")
    
       
        
def activity_check(server):
    
    while True:
        
        with LOCK:
            for sensor in sensors:
                dictionary = sensors[sensor]
            
                if dictionary == None:
                    continue
            
                data = dictionary["data"]
                last_message = data[len(data)-1]
                header = last_message["header"]
                sensor_id = header["sensor_id"]
                battery = header["battery"]
                token = header["token"]
                time_stamp = header["time_stamp"]
                active = dictionary["active"]
            
                if unix_time - time_stamp > 15 and active:
                    
                    threading.Thread(target=reconnect, args=(sensor_id, token, battery, 0, server,), daemon=True).start()
                
        time.sleep(1)
    
            
def reconnect(sensor_id, token, battery, time_stamp, server):
    time_count = int(time.time())
    send_count = 0
    flag = 1
    
    with LOCK:
        sensors[sensor_id]["active"] = 0
        
    while(not sensors[sensor_id]["active"]) and send_count < 10:
        if unix_time - time_count > 1 and flag:
            msg = messages.sensor_message(sensor_id, token, {"activity":1}, battery, "activity", 0)
            server.send_response(msg)  
            print(f" \033[31m WARNING: {sensor_id} DISCONNECTED! \n \033[0m")  
            flag = 0
            time_count = unix_time
            send_count += 1
        if unix_time - time_count >= 5 and not flag:
            msg = messages.sensor_message(sensor_id, token, {"activity":1}, battery, "activity", 0)
            server.send_response(msg)
            print(f" \033[31m WARNING: {sensor_id} DISCONNECTED! \n \033[0m")
            time_count = unix_time
        time.sleep(5)   
              
        
def handle_registration(dictionary, server):
    global token_counter
    
    with LOCK:
        timestamp = dictionary["header"]["time_stamp"]
        token = int(timestamp * 1000) + token_counter
        
        token_counter += 1
        
        sensor = dictionary["header"]["sensor_id"]
        sensors[sensor] = {"token":token, "battery":"high", "data":[dictionary], "log":[False], "active": 1, "response": [1,0]}
        print(f"INFO: {sensor} REGISTERED at {timestamp} \n ")
    
    response = messages.registration_message(sensor, token)
    
    server.send_response(response)
    
    return

def handle_data(dictionary, server):
    
    sensor = dictionary["header"]["sensor_id"]
    token = dictionary["header"]["token"]
    ack_response = 0
    
    with LOCK:
        if sensors[sensor]["token"] == token: 
            
            if dictionary["header"]["battery"] == "low":
                sensors[sensor]["battery"] = "low"
            
            sensors[sensor]["active"] = 1
            
            if sensors[sensor]["response"][0] == 1:
                ack_response = 1
                sensors[sensor]["data"].append(dictionary)
                sensors[sensor]["log"].append(False)
            elif sensors[sensor]["response"][0] == 0 and sensors[sensor]["response"][1] < 3:
                sensors[sensor]["response"][1] += 1
            else:
                sensors[sensor]["response"][0] = 1
                sensors[sensor]["response"][1] = 0
                ack_response = 1
                sensors[sensor]["data"].append(dictionary)
                sensors[sensor]["log"].append(False)
    
    if ack_response:
        ack = messages.sensor_message(dictionary["header"]["sensor_id"], token, {"ack":1}, dictionary["header"]["battery"], "ack", dictionary["header"]["time_stamp"])
        server.send_response(ack)

def handle_corrupted(dictionary, server, error):
    
    ack_response = 0
    
    sensor = dictionary["header"]["sensor_id"]
    time_stamp = dictionary["header"]["time_stamp"]
    token = dictionary["header"]["token"]
    battery = dictionary["header"]["battery"]
        
    if error == 0 and sensors[sensor]["token"] == token:
    
        print(f"{'\033[32m'} INFO: {sensor} CORRUTPED DATA at {time_stamp}. REQUESTING DATA {'\033[0m'} \n")
        
        msg = messages.sensor_message(sensor, token, {"error":1}, battery, "error", time_stamp)
        server.send_response(msg)
    
    elif error == 1 and sensors[sensor]["token"] == token:
        if battery == "high":
            print(f" {time_stamp} - {sensor}  ")
        else:
            print(f" \033[31m{time_stamp} - WARNING: LOW BATTERY {sensor}  \033[0m")
        for key, value in dictionary["header"]["data"].items():
            print(f"{'\033[32m'} {key}: {value},{'\033[0m'} ")
        print("\n ")
        ack = messages.sensor_message(dictionary["header"]["sensor_id"], token, {"ack":1}, dictionary["header"]["time_stamp"], "ack", 0)
        server.send_response(ack) 
        
                                    

def listen(server):
    global unix_time
    
    while (True):
        unix_time = int(time.time())
        
        data, client_ip = server.receive()
        process_message(data, server)
        
                            
def logger():
    
    while True:
        time.sleep(10)
        
        with LOCK:
            for sensor_id, value1 in sensors.items():
                    if value1 != None:
                        for i in range (len(value1["log"])):
                            
                            header = value1["data"][i]["header"]
                            time_stamp = header["time_stamp"]
                            sensor_id = header["sensor_id"]
                            
                            if value1["log"][i] != True:
                                
                                if value1["battery"] == "high":
                                    print(f" {time_stamp} - {sensor_id}  ")
                                else:
                                    print(f" \033[31m{time_stamp} - WARNING: LOW BATTERY {sensor_id}  \033[0m")
                                for key, value in header["data"].items():
                                    print(f" {key}: {value},")
                                print("\n ") 
                                value1["log"][i] = True     
                        
                        
                                  
        
        

    
if __name__=="__main__":
    
    possibilities = ["1", "2", "q"]
    server = None
    
    while (True):
        
        choice = menu()
        
        if choice == "1":
            
            server_ip = input(" ip.ip.ip.ip = ")
            server_port = int(input( " port = "))
            print(f"{'\033[32m'} server ip and port succesfully set!{'\033[0m'} \n")
            server = Server(server_ip, server_port)
            
        elif choice == "2":
            
            if server != None:
                print(f"{'\033[32m'} Starting server at {server_ip}:{server_port} {'\033[0m'} \n ")
            
                threading.Thread(target=listen, args=(server,), daemon=True).start()
                threading.Thread(target=logger, daemon=True).start()
                threading.Thread(target=activity_check, args=(server,),daemon=True).start()
            
            
        elif choice == "3":
            print(" --- Select sensor --- \n")
            i = 1
            
            with LOCK:    
                for key, value in sensors.items():
                        
                    token = value["token"]
                        
                    if token != None:
                            
                        print(f" {i}. {key} \n") 
                        i += 1
                    
                if i == 1:
                    print(" sensors do not have tokens yet! \n ")
                    continue
                
            sensorchoice = "none"
                
            while sensorchoice not in sensors:       
                sensorchoice = input(" Input your choice: (string name) ")
                
            with LOCK:
                sensors[sensorchoice]["response"][0] = 0
                
                
        
        elif choice == "q" and server != None:
            server.quit()
            break
        
        else:
            print(" wrong input! \n")
        