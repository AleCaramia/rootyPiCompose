import paho.mqtt.client as mqtt
import json
import cherrypy
import numpy as np
import time
import datetime
import threading
import requests

class light_shift(object):

    def __init__(self , config):
        threading.Thread.__init__(self)
        # signal attributes
        # self.intensity = lamp["e"][0]["v"]
        self.manual_init_hour = None
        self.manual_final_hour = None
        self.state = 0 # 0 automatic | 1 manual
        # self.response = None
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
        #
        # self.users = json.load(open("EnviromentMonitoring/temp_users.json",'r'))
        # self.code_db = json.load(open("UV_ligth/code_db.json",'r'))
        # self.users = None
        self.plants = None
        self.code_db = None
        self.url_plants = config["url_plants"]
        self.url_models = config["url_models"]
        self.url_devices = config["url_devices"]
    
        
        # self.payload =  {
        #                 "bn": self.clientID,Add a new functionality that determite self.max_lux from a field of the message given by self.pub_topic (take into account that the message is smnl like)
        #                 "e": [{ "n":f"intensity of lux per hour per {1/sf} seconds" , \
        #                        "u": f"lux/({import requests

        # path per controllare funzionamento, da togliere
        # self.lamp_state_path = "EnviromentMonitoring/lamp.json"          # put the correct path
        # self.lamp_database_path = "EnviromentMonitoring/database.json"  # put the correct path
        

    def start_mqtt(self):
        self.client.connect(self.broker,self.port)
        self.client.loop_start()
        # Avvia il metodo self.control_state() come thread
        control_thread = threading.Thread(target=self.control_state)
        control_thread.start()
        for topic in self.sub_topic:
            self.client.subscribe(topic, 2)

    def control_state(self):
        # while True:
        #     for j,user in enumerate(self.list_of_manual_plant):
        #         if time.time() >= user["init_hour"] and \
        #         time.time() <= user["final_hour"]:
        #             self.state = 1
        #         else:
        #             self.state = 0
        #             del self.list_of_manual_plant[j]
        #     print("\nDict:\n" + str(self.list_of_manual_plant) + "\n")
        #     time.sleep(1)
            # print("here")
        while True:
            for j,user in enumerate(self.list_of_manual_plant):
                if time.time() >= user["e"][3]["v"] and \
                time.time() <= user["e"][4]["v"]:
                    self.state = 1
                else:
                    self.state = 0
                    del self.list_of_manual_plant[j]
            print("\nDict:\n" + str(self.list_of_manual_plant) + "\n")
            time.sleep(2)
            

    def mymessage(self,paho_mqtt,userdata,msg):
        
        mess = json.loads(msg.payload)
        # lamp = json.load(open(self.lamp_state_path,"r"))
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
        # db = json.load(open(self.lamp_database_path,"r"))
        topic = msg.topic
        # print(topic,str(type(topic)))
        topic_parts = topic.split("/")  # Dividi il topic usando il carattere "/"
        last_part = topic_parts[-1]  # Ottieni l'ultima parte del topic
        self.current_user = topic_parts[1]
        self.current_plant = topic_parts[2]
        self.state = 0
        # self.CatalogRequestRequest() 
        # self.CodeRequest()
        # code = self.get_plant_jar(self.users, self.current_user , self.current_plant)
        # self.max_lux = self.code_db[code]["max_lux"]
        self.getlamp = self.GetLamp()
        if self.getlamp == True:
            self.get_plant_jar()

            for user in self.list_of_manual_plant:
                if user["e"][1]['v'] == self.current_plant and user["e"][0]["v"] == self.current_user:
                    self.state = 1 
            
            self.intensity = mess['e'][0]['v']
            # print(mess)
            if float(self.intensity) > 0:
                if float(self.intensity) >= self.max_lux:
                    self.intensity = self.max_lux
                else:
                    self.intensity = float(self.intensity)
            else: 
                self.intensity = 0

            if last_part == "automatic" and self.state == 0:
                # print(mess)
                # self.max_lux = float(mess['max_lux'])
                self.pub_topic = "RootyPy/"+topic_parts[1]+"/"+topic_parts[2]+"/lightShift/automatic"
                lamp["e"][0]["v"] = self.intensity*100/self.max_lux
                lamp["e"][1]["v"] = 0
                lamp["e"][2]["v"] = 0
                lamp["e"][0]["t"] = time.time()
                lamp["e"][1]["t"] = time.time()
                lamp["e"][2]["t"] = time.time()
                lamp["bn"] = "lamp_state"
                # print(lamp["current_intensity"])
                # mess = json.dump(lamp,open(self.lamp_state_path,"w"))
                # mess = json.dumps(lamp)
                # r = requests.put("https://mako-keen-rarely.ngrok-free.app/put",data = mess)
                print("\nState of the lamp :" + str(lamp) + "\nstate = " +str(self.state) +\
                    "\n" + str(self.pub_topic)+ "\nmax lux: " + str(self.max_lux)) # + "\ncode: "  + str(self.code_db)
                self.publish(lamp)
                

            elif last_part == "manual":

                self.manual_init_hour = mess["e"][1]["t"]
                self.manual_final_hour = mess["e"][1]["v"]
                lamp["e"][0]["v"] = self.intensity
                lamp["e"][1]["v"] = self.manual_init_hour
                lamp["e"][2]["v"] = self.manual_final_hour
                lamp["e"][0]["t"] = time.time()
                lamp["e"][1]["t"] = time.time()
                lamp["e"][2]["t"] = time.time()
                lamp["bn"] = "lamp_state"
                # self.state = 1
                self.check_manuals(lamp)
                
                # self.list_of_manual_plant.append({  "user": self.current_user ,\
                #                                     "plant": self.current_plant ,\
                #                                     "state": 1,\
                #                                     "init_hour": self.manual_init_hour,\
                #                                     "final_hour" : self.manual_final_hour,\
                #                                     "current_intensity": lamp["e"][0]["v"]})
                
                # mess = json.dump(lamp,open(self.lamp_state_path,"w"))
                # mess = json.dumps(lamp)
                # print(mess)
                # r = requests.put("https://mako-keen-rarely.ngrok-free.app/put", data = mess)
                
                self.pub_topic = "RootyPy/"+topic_parts[1]+"/"+topic_parts[2]+"/lightShift/manual"
                print("\nState of the lamp :" + str(lamp) + "\nstate = " +str(self.state) +\
                    "\n" + str(self.pub_topic) + "\nmax lux: " + str(self.max_lux))#"\ncode: " + str(self.code_db)
                self.publish(lamp)
                self.pub_topic = "RootyPy/lightShift/manual_list"
                self.publish(self.list_of_manual_plant)

        else: print(f"No lamp found for the {self.current_user} and {self.current_plant}")
        # print(mess)
        # time.sleep(0.05)
    
    #    self.publish(diff)

    def myconnect(self,paho_mqtt, userdata, flags, rc):
       print(f"ligth shift: Connected to {self.broker} with result code {rc} \n subtopic {self.sub_topic}, pubtopic {self.pub_topic}")

    def publish(self, lamp):
       lamp=json.dumps(lamp)
       self.client.publish(self.pub_topic,lamp,2)

    # def CatalogRequest(self):
    #     self.users=json.loads(req.get("http://localhost:8081/plants")) 
    #     # self.users= json.load(open("EnviromentMonitoring/temp_users.json",'r'))
    
    def CodeRequest(self):
        self.code_db=json.loads(requests.get(self.url_models)) 
        # self.code_db = json.load(open("UV_ligth/code_db.json",'r'))

    def GetLamp(self):
        self.lamp = json.loads(requests.get(self.url_devices)) 
        self.plants = json.loads(requests.get(self.url_plants))
        # self.lamp = json.load(open("UV_ligth/devices.json",'r'))
        # self.plants = json.load(open("UV_ligth/temp_plants.json",'r'))
        for lamp in self.lamp:
            ID = lamp["deviceID"]
            ID_split = ID.split("/")
            plantcode = ID_split[0]
            type = ID_split[1]
            for plant in self.plants:
                if plant['plantCode'] == plantcode and self.current_user == plant['userId'] and \
                    self.current_plant == plant['plantId'] and type == "lampLight":
                    return True


    def get_plant_jar(self):
        self.plants = json.loads(requests.get(self.url_plants)) 
        # self.plants = json.load(open("UV_ligth/temp_plants.json",'r'))
        for plant in self.plants:
            if plant['userId'] == self.current_user:
                if plant['plantId'] == self.current_plant:
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
                # print("\n\n","user after",user)
                
                # print("\n\n","list",self.list_of_manual_plant)
                
                # print("CHANGE!!!!!!!!!!")
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
        # print("APPEND!!!!!!!!!!")

# class Webserver(object):

#     def __init__(self,lamp):
#         self.lamp = lamp

#     """CherryPy webserver."""
#     exposed = True
#     def start(self):
#         conf={
#             '/':{
#             'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
#             'tools.sessions.on':True
#             }
#         }
#         cherrypy.tree.mount(self,'/',conf)
#         cherrypy.config.update({'server.socket_port':8080})
#         cherrypy.config.update({'server.socket_host':'0.0.0.0'})
#         cherrypy.engine.start()
#         #cherrypy.engine.block()

#     #@cherrypy.tools.json_out()
#     def GET(self, *uri, **params):
#         """Define GET HTTP method for RESTful webserver."""
#         pass

#     def PUT(self, *uri, **params):
#         """Define PUT HTTP method for RESTful webserver."""        
#         pass

#     def POST(self, *uri, **params):
#         """Define POST HTTP method for RESTful webserver."""        
#         pass
        
# class Thread1(threading.Thread):
#     """Thread to run CherryPy webserver."""
#     exposed=True
#     def __init__(self, ThreadID, name,lamp):
#         threading.Thread.__init__(self)
#         self.ThreadID = ThreadID
#         self.name = name
#         self.webserver = Webserver(lamp)
#         self.webserver.start()

class Thread2(threading.Thread):
    """Thread to run mqtt."""

    def __init__(self, ThreadID, name,config):
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        self.shift = light_shift(config)
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
                        [{ "n": "UV_ligth_shift", "u": "", "t": self.time, "v":"ligth_shift" }]}
    
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


    
    config = json.load(open("config_UV_ligth.json","r"))
    # lamp = json.load(open("EnviromentMonitoring/lamp.json","r"))
    # configIamalive = json.load(open("UV_ligth/Iamalive.json","r"))
    

    # thread1 = Iamalive(1, "Iamalive",config)
    # print("> Starting I am alive...")
    # thread_Alive = threading.Thread(target=thread1.start_mqtt)
    # thread_Alive.start()
    # thread1.join()  # Wait for thread1 to finish
    
    # thread2 = Thread1(2, "CherryPy",lamp)
    # print("> Starting CherryPy...")
    # thread2.start()

    thread3 = Thread2(3, "Mqtt",config)
    print("> Starting light shift...")
    thread3.start()

    thread1 = AliveThread(2, "aliveThread", config)
    thread1.run()

    

