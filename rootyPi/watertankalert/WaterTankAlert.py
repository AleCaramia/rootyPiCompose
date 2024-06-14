import numpy
import time
import datetime    
import json
import paho.mqtt.client as pahoMQTT
import cherrypy
import requests


class WaterTankAlert(object):

    def __init__(self,config_path):
        config =  json.load(open(config_path,'r'))
        self.registry_url = config['url_registry']
        self.adaptor_url = config['url_adaptor']
        #self.registry_url = 'http://127.0.0.1:8080'
        self.headers = config['headers']
        self.ID = config['ID']
        self.broker = config['broker']
        self.port = config['port']
        self.starting_time_tank = time.time()
        self.interval_tank = config['tank_interval']
        self.paho_mqtt = pahoMQTT.Client(self.ID,True)
        self.paho_mqtt.on_connect = self.myconnect_live

        self.start_mqtt()

    def check_water_level(self):
            pass
        
            actual_time = time.time()
            if actual_time > self.starting_time_tank + self.interval_tank:
                r = requests.get(self.registry_url+'/models')
                models = json.loads(r.text)
                r = requests.get(self.registry_url+'/users')
                users = json.loads(r.text)
                userwithchatid = []
                for user in users:
                    if user['chat_ID'] != None:
                        userwithchatid.append(user)
                r = requests.get(self.registry_url+'/plants')
                plants = json.loads(r.text)
                plantwithchatid = []
                for user in userwithchatid:
                    for plant_diz in plants:
                        if plant_diz['userId'] in userwithchatid:    
                            plantwithchatid.append((plant_diz['plantCode'],user['userId']))
                for plant_u_tuple in plantwithchatid:
                    tank_level_series=  json.loads(requests.get(f'{self.adaptor_url}/getData/{plant_u_tuple[1]}/{plant_u_tuple[0]}',params={"measurement":'tankLevel',"duration":1}).text)
                    actual_tank_level = tank_level_series[-1]["v"]
                    curr_model = plant_u_tuple[0][:2]
                    for model in models:
                        if model['model_code'] == curr_model:
                            tank_capacity = model['tank_capacity']
                    tank_level_th = 0.1 * tank_capacity
                    if actual_tank_level < tank_level_th:
                        topic = self.pub_topic+f'/{plant_u_tuple[1]}/{plant_u_tuple[0]}'
                        message = {"bn": self.ID,"e":[{ "n": f"{plant_diz['plantCode']}", "u": "", "t": time.time(), "v":f"{alert}" }]}
                        self.publish(topic,message)
                #print(f'{self.interval} seconds passed sending i am alive message at {self.pub_topic}')
                self.starting_time_tank = actual_time

    def start_mqtt(self):
        print('>starting i am alive')
        self.paho_mqtt.connect(self.broker,self.port)
        self.paho_mqtt.loop_start()

    def myconnect_live(self,paho_mqtt, userdata, flags, rc):
       print(f"report generator: Connected to {self.broker} with result code {rc}")

    def publish(self,message):
        __message=json.dumps(message)
        #print(f'message sent at {time.time()} to {self.pub_topic}')
        self.paho_mqtt.publish(topic=self.pub_topic,payload=__message,qos=2)

        