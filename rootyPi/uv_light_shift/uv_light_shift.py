import paho.mqtt.client as mqtt
import json
import numpy as np
from requests.exceptions import HTTPError
import time
import datetime
import threading
import requests

class light_shift(object):

    def __init__(self , config):
        self.manual_init_hour = 0
        self.manual_final_hour = 0
        self.state = 0 # 0 automatic | 1 manual
        self.current_user = None
        self.current_plant = None
        self.list_of_manual_plant = [] 
        self.max_lux = None # 
        # mqtt attributes
        self.clientID = config["ID_light_shift"]
        self.broker = config["broker"]
        self.port = config["port"]
        self.sub_topic = config["sub_topics_light_shift"] # rooty_py/userX/plantX/function
        self.pub_topic = config["pub_topic_light_shift"]
        self.client = mqtt.Client(self.clientID, True)
        self.client.on_connect = self.myconnect
        self.client.on_message = self.mymessage
        self.plants = None
        self.code_db = None
        self.url_plants = config["url_plants"]
        self.url_models = config["url_models"]
        self.url_devices = config["url_devices"]
        

    def start_mqtt(self):
        self.client.connect(self.broker,self.port)
        self.client.loop_start()
        # Avvia il metodo self.control_state() come thread
        control_thread = threading.Thread(target=self.control_state)
        control_thread.start()
        for topic in self.sub_topic:
            self.client.subscribe(topic, 2)

    def control_state(self):

        while True:
            for j,user in enumerate(self.list_of_manual_plant):
                if time.time() >= int(user["e"][3]["v"]) and \
                time.time() <= int(user["e"][4]["v"]):
                    self.state = 1
                else:
                    self.state = 0
                    del self.list_of_manual_plant[j]
            print("\nDict:\n" + str(self.list_of_manual_plant) + "\n")
            time.sleep(2)
            

    def mymessage(self,paho_mqtt,userdata,msg):
        
        mess = json.loads(msg.payload)
        print(mess)
        lamp = { "bn": "None","e": [
        {
            "n": "current_intensity",
            "u": "percentage",
            "t": "None",
            "v": "None"
        },
        {
            "n": "init_hour",
            "u": "s",
            "t": "None",
            "v": "None"
        },
        {
            "n": "final_hour",
            "u": "s",
            "t": "None",
            "v": "None"
        }
    ]
}
        topic = msg.topic
        topic_parts = topic.split("/")  # Dividi il topic usando il carattere "/"
        last_part = topic_parts[-1]  # Ottieni l'ultima parte del topic
        self.current_user = topic_parts[1]
        self.current_plant = topic_parts[2]
        self.state = 0

        self.getlamp = self.GetLamp()
        if self.getlamp == True:
            self.get_plant_jar()

            for user in self.list_of_manual_plant:
                if user["e"][1]['v'] == self.current_plant and user["e"][0]["v"] == self.current_user:
                    self.state = 1 
            
            self.intensity = mess['e'][0]['v']
            # print(mess)
            if last_part == "automatic" and self.state == 0:

                if float(self.intensity) > 0:
                    if float(self.intensity) >= self.max_lux:
                        self.intensity = self.max_lux
                    else:
                        self.intensity = float(self.intensity)
                else: 
                    self.intensity = 0
                self.pub_topic = "RootyPy/"+topic_parts[1]+"/"+topic_parts[2]+"/lightShift/automatic"
                lamp["e"][0]["v"] = int(round(self.intensity*100/self.max_lux))
                lamp["e"][1]["v"] = 0
                lamp["e"][2]["v"] = 0
                lamp["e"][0]["t"] = time.time()
                lamp["e"][1]["t"] = time.time()
                lamp["e"][2]["t"] = time.time()
                lamp["bn"] = "lamp_state"
                print("\nState of the lamp :" + str(lamp) + "\nstate = " +str(self.state) +\
                    "\n" + str(self.pub_topic)+ "\nmax lux: " + str(self.max_lux)) # + "\ncode: "  + str(self.code_db)
                self.publish(lamp)
                

            elif last_part == "manual":

                self.manual_init_hour = mess["e"][1]["v"]
                self.manual_final_hour = mess["e"][2]["v"]
                lamp["e"][0]["v"] = self.intensity
                lamp["e"][1]["v"] = self.manual_init_hour
                lamp["e"][2]["v"] = self.manual_final_hour
                # lamp["e"][1]["v"] = datetime.datetime.fromtimestamp(self.manual_init_hour).strftime("%H:%M")
                # lamp["e"][2]["v"] = datetime.datetime.fromtimestamp(self.manual_final_hour).strftime("%H:%M")
                lamp["e"][0]["t"] = time.time()
                lamp["e"][1]["t"] = time.time()
                lamp["e"][2]["t"] = time.time()
                lamp["bn"] = "lamp_state"
                self.check_manuals(lamp)
                
                
                self.pub_topic = "RootyPy/"+topic_parts[1]+"/"+topic_parts[2]+"/lightShift/manual"
                print("\nState of the lamp :" + str(lamp) + "\nstate = " +str(self.state) +\
                    "\n" + str(self.pub_topic) + "\nmax lux: " + str(self.max_lux))#"\ncode: " + str(self.code_db)
                self.publish(lamp)
                # self.pub_topic = "RootyPy/lightShift/manual_list"
                # self.publish(self.list_of_manual_plant)

        else: print(f"No lamp found for the {self.current_user} and {self.current_plant}")

    def get_response(url):
        for i in range(15):
            try:
                response = requests.get(url)
                response.raise_for_status()
                return json.loads(response.content.text)
            except HTTPError as http_err:
                print(f"HTTP error occurred: {http_err}")
            except Exception as err:
                print(f"Other error occurred: {err}")
            time.sleep(1)
        return []

    def myconnect(self,paho_mqtt, userdata, flags, rc):
       print(f"light shift: Connected to {self.broker} with result code {rc} \n subtopic {self.sub_topic}, pubtopic {self.pub_topic}")

    def publish(self, lamp):
       lamp=json.dumps(lamp)
       self.client.publish(self.pub_topic,lamp,2)

    
    def CodeRequest(self):

        self.code_db = self.get_response(self.url_models)

        # self.code_db=json.loads((requests.get(self.url_models)).text) 

    def GetLamp(self):
        try:

            self.lamp = self.get_response(self.url_devices)
            self.plants = self.get_response(self.url_plants)


            # req_lamp = requests.get(self.url_devices)
            # req_lamp.raise_for_status()  # Verifica lo stato della risposta
            # self.lamp = json.loads(req_lamp.text)
            # req_plants = requests.get(self.url_plants)
            # req_plants.raise_for_status()  # Verifica lo stato della risposta
            # self.plants = json.loads(req_plants.text)

            # print("lamp: ",self.lamp)
            # print("Plants: ",self.plants)
            

            # self.lamp = json.load(open("UV_light/devices.json",'r'))
            # self.plants = json.load(open("UV_light/temp_plants.json",'r'))
            for lamp in self.lamp:
                ID = lamp["deviceID"]
                ID_split = ID.split("/")
                plantcode = ID_split[0]
                type = ID_split[1]
                # print(plant['plantCode'])
                # print("type: ", type,"plantcode: ", plantcode)
                # print("self.current_user: ", self.current_user,"self.current_plant: ", self.current_plant)

                for plant in self.plants:
                    # print("INplantcode: ",plant['plantCode'],"IN userID: ", plant['userId'])
                    # print(f"{plant['plantCode']} == {plantcode}\n{self.current_user} == {plant['userId']}\
                    #       \n{type} == {"lampLight"}\n")

                    
                    if plant['plantCode'] == plantcode and self.current_user == plant['userId'] and \
                        type == "lampLight":
                        print(f"Find a lamp for user {self.current_user} and plant {plantcode}")
                        return True
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return False


    def get_plant_jar(self):

        self.plants = self.get_response(self.url_plants)

        # self.plants = json.loads(requests.get(self.url_plants).text) 

        # self.plants = json.load(open("UV_light/temp_plants.json",'r'))
        for plant in self.plants:
            if plant['userId'] == self.current_user:
                if plant['plantCode'] == self.current_plant:
                    current_code = plant['plantCode']
                    current_model = current_code[0:2]
                    self.CodeRequest()
                    for code in self.code_db:
                        if code["model_code"] == current_model:
                            self.max_lux = code["max_lux"]
                            return
                    print(f"No plant code found for {current_model}")
        print(f"\nNo plant found for {self.current_user}/{self.current_plant}")

    
    def check_manuals(self,lamp):

        for j,user in enumerate(self.list_of_manual_plant):
            if self.current_user == user["e"][0]["v"] and self.current_plant == user["e"][1]["v"]:
                self.list_of_manual_plant[j] = {"bn": self.current_user + "/" + self.current_plant,\
                                            "e":\
                                            [{ "n": "user", "u": None, "t": time.time(), "v":self.current_user }, \
                                             { "n": "plant", "u": None, "t": time.time(), "v":self.current_plant }, \
                                             { "n": "state", "u": "boleean", "t": time.time(), "v": 1 }, \
                                             { "n": "init_hour", "u": "s", "t": time.time(), "v":self.manual_init_hour }, \
                                             { "n": "final_hour", "u": "s", "t": time.time(), "v":self.manual_final_hour }, \
                                             { "n": "current_intensity", "u": "percentage", "t": time.time(), "v":lamp["e"][0]["v"] }  \
                                             ]}

                return
            
        self.list_of_manual_plant.append({"bn": self.current_user + "/" + self.current_plant,\
                                        "e":\
                                        [{ "n": "user", "u": None, "t": time.time(), "v":self.current_user }, \
                                            { "n": "plant", "u": None, "t": time.time(), "v":self.current_plant }, \
                                            { "n": "state", "u": "boleean", "t": time.time(), "v": 1 }, \
                                            { "n": "init_hour", "u": "s", "t": time.time(), "v":self.manual_init_hour }, \
                                            { "n": "final_hour", "u": "s", "t": time.time(), "v":self.manual_final_hour }, \
                                            { "n": "current_intensity", "u": "percentage", "t": time.time(), "v":lamp["e"][0]["v"] }  \
                                            ]})


class run():
    """Thread to run mqtt."""

    def __init__(self, ThreadID, name,config):
        self.ThreadID = ThreadID
        self.shift = light_shift(config)
        self.shift.start_mqtt()
        self.alive = Iamalive(config)

    def run(self):
        try:
            self.alive.start_mqtt()
            while True:
                self.alive.publish()  
                time.sleep(5)
        except KeyboardInterrupt:
                self.shift.stop()
                self.alive.stop()


class Iamalive(object):
    "I am alive"

    def __init__(self , config):

        # mqtt attributes
        self.clientID = config["ID_Iamalive"]
        self.broker = config["broker"]
        self.port = config["port"]
        self.sub_topic = config["sub_topic_Iamalive"] # rooty_py/userX/plantX/function
        self.pub_topic = config["pub_topic_Iamalive"]
        self.client = mqtt.Client(self.clientID, True)
        self.time = time.time()
        self.client.on_connect = self.myconnect
        self.message = {"bn": "updateCatalogService",\
                        "e":\
                        [{ "n": "UV_light_shift", "u": "", "t": self.time, "v":"light_shift" }]}
    
    def start_mqtt(self):
        self.client.connect(self.broker,self.port)
        self.client.loop_start()
        # Avvia il metodo self.control_state() come thread


    def myconnect(self,paho_mqtt, userdata, flags, rc):
       print(f"Iamalive: Connected to {self.broker} with result code {rc} \n subtopic {self.sub_topic}, pubtopic {self.pub_topic}")

    def publish(self):
        self.message["e"][0]["t"]= time.time()
        __message=json.dumps(self.message)
        print(__message)
        print(self.pub_topic, self.broker, self.port)
        self.client.publish(topic=self.pub_topic,payload=__message,qos=2)
        # print("I am alive message sent")

# class AliveThread(threading.Thread):
#     def __init__(self, threadId, name, config):
#         threading.Thread.__init__(self)
#         self.threadId = threadId
#         self.name = name
#         self.alive = Iamalive(config)
        


#     def run(self):
#         self.alive.start_mqtt()
#         while True:
#             self.alive.publish()  
#             time.sleep(5)  

if __name__=="__main__":

    config = json.load(open("config_UV_light.json","r"))
    
    print("> Starting light shift...")
    main = run(3, "Mqtt",config)
    main.run()

    # print("> Starting IamAlive...")
    # thread1 = AliveThread(2, "aliveThread", config)
    # thread1.run()

    

