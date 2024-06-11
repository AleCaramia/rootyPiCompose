import threading
import paho.mqtt.client as mqtt
import json
import time
import requests

class water_pump(object):
    def __init__(self , config):
        threading.Thread.__init__(self)
        self.manual_init_hour = None
        self.manual_final_hour = None
        self.state = 0 # 0 automatic | 1 manual
        self.current_user = None
        self.current_plant = None
        self.list_of_manual_plant = [] 
        self.max_flow = None # 
        self.clientID = config["ID_water_pump"]
        self.broker = config["broker"]
        self.port = config["port"]
        self.sub_topic = config["sub_topics_water_pump"] 
        self.pub_topic = config["pub_topic_water_pump"]
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
        pump = { "bn": "None","e": [
        {
            "n": "Volume of water",
            "u": "l",
            "t": "None",
            "v": "None"
        }
    ]}
        topic = msg.topic
        topic_parts = topic.split("/")  
        last_part = topic_parts[-1]  
        self.current_user = topic_parts[1]
        self.current_plant = topic_parts[2]
        self.state = 0
        self.getpump = self.GetPump()
        if self.getpump == True:
            for user in self.list_of_manual_plant:
                if user["e"][1]['v'] == self.current_plant and user["e"][0]["v"] == self.current_user:
                    self.state = 1 
            self.flow = mess['e'][0]['v']
            if float(self.flow) > 0:
                self.flow = float(self.flow)
            else: 
                self.flow = 0
            if last_part == "automatic" and self.state == 0:
                self.pub_topic = "RootyPy/"+topic_parts[1]+"/"+topic_parts[2]+"/waterPump/automatic"
                pump["e"][0]["v"] = self.flow
                pump["e"][0]["t"] = time.time()
                pump["bn"] = "pump_state"
                print("\nState of the pump :" + str(pump) + "\nstate = " +str(self.state) +\
                    "\n" + str(self.pub_topic))
                self.publish(pump)
            elif last_part == "manual":
                self.manual_init_hour = mess["e"][1]["t"]
                self.manual_final_hour = mess["e"][1]["v"]
                pump["e"][0]["v"] = self.flow
                pump["e"][0]["t"] = time.time()
                pump["bn"] = "pump_state"
                self.check_manuals(pump)
                self.pub_topic = "RootyPy/"+topic_parts[1]+"/"+topic_parts[2]+"/waterPump/manual"
                print("\nState of the pump :" + str(pump) + "\nstate = " +str(self.state) +\
                    "\n" + str(self.pub_topic) )
                self.publish(pump)
                self.pub_topic = "RootyPy/waterPump/manual_list"
                self.publish(self.list_of_manual_plant)
        else: print(f"No pump found for the {self.current_user} and {self.current_plant}")

    def myconnect(self,paho_mqtt, userdata, flags, rc):
       print(f"water pump: Connected to {self.broker} with result code {rc} \n subtopic {self.sub_topic}, pubtopic {self.pub_topic}")

    def publish(self, pump):
       pump=json.dumps(pump)
       self.client.publish(self.pub_topic,pump,2)

    def CodeRequest(self):
        self.code_db=json.loads((requests.get(self.url_models)).text) 

        # with open("fake_catalogue.json",'r') as file:
        #         catalogue = json.loads(file.read())
        # self.code_db = catalogue['models']

    def GetPump(self):
        try:
            req_pump = requests.get(self.url_devices)
            req_pump.raise_for_status()  # Verifica lo stato della risposta
            self.pump = json.loads(req_pump.text)
            req_plants = requests.get(self.url_plants)
            req_plants.raise_for_status()  # Verifica lo stato della risposta
            self.plants = json.loads(req_plants.text)

            # with open("fake_catalogue.json",'r') as file:
            #     catalogue = json.loads(file.read())
            # self.pump = catalogue['devices']
            # self.plants = catalogue['plants']
            

            # self.pump = json.load(open("UV_light/devices.json",'r'))
            # self.plants = json.load(open("UV_light/temp_plants.json",'r'))
            for lamp in self.pump:
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
                        type == "tank":
                        print(f"Find a pump for user {self.current_user} and plant {plantcode}")
                        return True
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return False


    # def get_plant_jar(self):

    #     self.plants = json.loads(requests.get(self.url_plants).text) 
    #     # with open("fake_catalogue.json",'r') as file:
    #     #         catalogue = json.loads(file.read())
    #     # self.plants = catalogue['plants']

    #     for plant in self.plants:
    #         if plant['userId'] == self.current_user:
    #             if plant['plantCode'] == self.current_plant:
    #                 current_code = plant['plantCode']
    #                 current_model = current_code[0:2]
    #                 self.CodeRequest()
    #                 for code in self.code_db:
    #                     if code["model_code"] == current_model:
    #                         print(f"Find a pump for {current_model}")
    #                         return
    #                 print(f"No plant code found for {current_model}")
    #     print(f"\nNo plant found for {self.current_user}/{self.current_plant}")

    
    def check_manuals(self,pump):

        for j,user in enumerate(self.list_of_manual_plant):
            if self.current_user == user["e"][0]["v"] and self.current_plant == user["e"][1]["v"]:
                self.list_of_manual_plant[j] = {"bn": self.current_user + "/" + self.current_plant,\
                                            "e":\
                                            [{ "n": "user", "u": None, "t": time.time(), "v":self.current_user }, \
                                             { "n": "plant", "u": None, "t": time.time(), "v":self.current_plant }, \
                                             { "n": "state", "u": "boleean", "t": time.time(), "v": 1 }, \
                                             { "n": "init_hour", "u": "s", "t": time.time(), "v":self.manual_init_hour }, \
                                             { "n": "final_hour", "u": "s", "t": time.time(), "v":self.manual_final_hour }, \
                                             { "n": "mass flow rate", "u": "percentage", "t": time.time(), "v":pump["e"][0]["v"] }  \
                                             ]}
                return
            
        self.list_of_manual_plant.append({"bn": self.current_user + "/" + self.current_plant,\
                                        "e":\
                                        [{ "n": "user", "u": None, "t": time.time(), "v":self.current_user }, \
                                            { "n": "plant", "u": None, "t": time.time(), "v":self.current_plant }, \
                                            { "n": "state", "u": "boleean", "t": time.time(), "v": 1 }, \
                                            { "n": "init_hour", "u": "s", "t": time.time(), "v":self.manual_init_hour }, \
                                            { "n": "final_hour", "u": "s", "t": time.time(), "v":self.manual_final_hour }, \
                                            { "n": "mass flow rate", "u": "percentage", "t": time.time(), "v":pump["e"][0]["v"] }  \
                                            ]})
        
class Thread2(threading.Thread):
    """Thread to run mqtt."""

    def __init__(self, ThreadID, name,config):
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        self.shift = water_pump(config)
        self.shift.start_mqtt()

class Iamalive(object):
    "I am alive"

    def __init__(self , config):
        # threading.Thread.__init__(self)

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
                        [{ "n": "water_irrigator", "u": "", "t": self.time, "v":"water_irrigator" }]}
    
    def start_mqtt(self):
        self.client.connect(self.broker,self.port)
        self.client.loop_start()
        # Avvia il metodo self.control_state() come thread
        # control_thread = threading.Thread(target=self.control_state)
        # control_thread.start()


    def myconnect(self,paho_mqtt, userdata, flags, rc):
       print(f"Iamalive: Connected to {self.broker} with result code {rc} \n subtopic {self.sub_topic}, pubtopic {self.pub_topic}")

    def publish(self):
        self.message["e"][0]["t"]= time.time()
        __message=json.dumps(self.message)
        print(__message)
        print(self.pub_topic, self.broker, self.port)
        self.client.publish(topic=self.pub_topic,payload=__message,qos=2)
        # print("I am alive message sent")

class AliveThread(threading.Thread):
    def __init__(self, threadId, name, config):
        threading.Thread.__init__(self)
        self.threadId = threadId
        self.name = name
        self.alive = Iamalive(config)
        


    def run(self):
        self.alive.start_mqtt()
        while True:
            self.alive.publish()  
            time.sleep(5)  

if __name__=="__main__":


    
    config = json.load(open("config_water_irrigator.json","r"))
    # pump = json.load(open("EnviromentMonitoring/pump.json","r"))
    # configIamalive = json.load(open("water_irrigator/Iamalive.json","r"))
    

    # thread1 = Iamalive(1, "Iamalive",config)
    # print("> Starting I am alive...")
    # thread_Alive = threading.Thread(target=thread1.start_mqtt)
    # thread_Alive.start()
    # thread1.join()  # Wait for thread1 to finish
    
    # thread2 = Thread1(2, "CherryPy",pump)
    # print("> Starting CherryPy...")
    # thread2.start()

    thread3 = Thread2(3, "Mqtt",config)
    print("> Starting light shift...")
    thread3.start()

    thread1 = AliveThread(2, "aliveThread", config)
    thread1.run()

    
