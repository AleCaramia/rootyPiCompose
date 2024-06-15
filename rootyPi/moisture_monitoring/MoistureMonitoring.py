import cherrypy
import paho.mqtt.client as PahoMQTT
import cherrypy
import time
import json
import numpy as np
import requests as req
import threading
from datetime import datetime
from requests.exceptions import HTTPError


class MoistureMonitoring(object):
    def __init__(self,settings):
        #load settings
        self.base_topic=settings['pub_topic_moisturemonitoring']
        self.alive_topic = settings['pub_topic_Iamalive']
        self.port=settings['port']
        self.broker=settings['broker']
        self.clientID=settings['ID_moistureMonitoring']
        self.moisture_goals = None
        self.default_time=settings['default_time'] 
        self.url_registry=settings['url_registry']
        self.url_adaptor=settings['url_adaptor']


        ###############################################à

        
        self._paho_mqtt=PahoMQTT.Client(self.clientID, True)
        self._paho_mqtt.on_connect=self.MyOnConnect
        self.__message={"bn":"", 'e':[{'n':'water_deficit','unit':"percent",'t':'','v':None }]}

        

    def start(self):
        self._paho_mqtt.connect(self.broker,self.port)
        self._paho_mqtt.loop_start()

    def stop(self):
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()

    def MyOnConnect(self,paho_mqtt,userdata,flags,rc):
        print(f"MoistureMonitoring: Connected to {self.broker} with result code {rc} \n subtopic {None}, pubtopic PROVA")

    def get_response(url):
        for i in range(15):
            try:
                response = req.get(url)
                response.raise_for_status()
                return json.loads(response.content.text)
            except HTTPError as http_err:
                print(f"HTTP error occurred: {http_err}")
            except Exception as err:
                print(f"Other error occurred: {err}")
            time.sleep(1)
        return []

    def MyPublish(self, type):

        if type == "function":
            plants,url_adptor,models=self.RequestsToRegistry() 
            
            for plant in plants:
                    
                    plant_type=plant['type']
                    plantId=plant['plantId']
                    #print(plantId)
                    userId=plant['userId']
                    plant_code=plant["plantCode"]
                    

                    jar_volume=self.retriveMaxFlowPumpAndJarVolume(plant_code,models)
                    
                    # start_time=plant['auto_init']
                    # end_time=plant['auto_end']

                    # current_time = datetime.now().time()
                    # current_datetime = datetime.combine(datetime.today(), current_time)
                    # start_datetime = datetime.combine(datetime.today(),datetime.strptime(start_time, '%H:%M').time())
                    # time_difference = current_datetime - start_datetime
                    # hours_passed = round(time_difference.total_seconds() / 3600)

                    # end_datetime = datetime.combine(datetime.today(), datetime.strptime(end_time, '%H:%M').time())
                    # time_difference = end_datetime - start_datetime
                    # suncycle = round(time_difference.total_seconds() / 3600)

                    water_to_add = self.PlantWaterEstimation(url_adptor,plant_code,plant_type,userId,jar_volume)
                    if water_to_add>0:

                        current_msg=self.__message.copy()
                        
                        current_topic=f"{self.base_topic}/{userId}/{plant_code}/water_to_give/automatic"

                        current_msg['e'][0]['t']=time.time()
                        current_msg['e'][0]['v']=water_to_add
                        current_msg['bn']=current_topic
                        


                        __message=json.dumps(current_msg)
                        print(__message)
                        self._paho_mqtt.publish(topic=current_topic,payload=__message,qos=2)
                        

            return 
        else:
            message = {"bn":"updateCatalogService","e":[{"n":"MoistureMonitoring", "t": time.time(), "v":None,"u":"IP"}]}
            self._paho_mqtt.publish(topic=self.alive_topic,payload=json.dumps(message),qos=2)

    
    def RequestsToRegistry(self):
        #Devo farla al registry

        plants=self.get_response(f"{self.url_registry}/plants")
        models=self.get_response(f"{self.url_registry}/models")
        active_services=self.get_response(f"{self.url_registry}/services")

        # response=req.get(f"{self.url_registry}/plants")
        # plants=json.loads(response.text)
        # models=json.loads((req.get(f"{self.url_registry}/models")).text)
        # active_services=json.loads(req.get(f"{self.url_registry}/services").text)

        url_adaptor=self.url_adaptor
        return plants,url_adaptor,models
    
    def retriveMaxFlowPumpAndJarVolume(self,plant_code,models):
        vase_type=plant_code[:2]
        for model in models:
            if model['model_code']==vase_type:
                jar_volume=model["jar_volume"]
                break
        return jar_volume

    def PlantWaterEstimation(self,url_adptor,plant_code,plant_type,userId,jar_volume): 

        plants_type= self.get_response(f"{self.url_registry}/valid_plant_types")

        # plants_type=json.loads((req.get(f"{self.url_registry}/valid_plant_types")).text)

        for plant in plants_type:
            if plant_type == plant["type"]:
                self.moisture_goals=float(plant["moisture_goal"])
                break
        mesurements_past_hour=self.PlantSpecificGetReq(url_adptor,userId,plant_code)#aggiungo i dli dati fin ora
        mesurements_past_hour_moisture = []
        for mesure in mesurements_past_hour:
                mesurements_past_hour_moisture.append(mesure['v'])
        mean_moisture_past_hour= np.mean(mesurements_past_hour_moisture)

        ##################################################################
        ##################################################################
        # mean_moisture_past_hour = float(mesurements_past_hour_moisture[-1])
        ##################################################################
        ##################################################################
        
        if self.moisture_goals - mean_moisture_past_hour > 0:
            water_to_add = (self.moisture_goals - mean_moisture_past_hour)/100 * jar_volume
        else:
            water_to_add = 0
    
        return water_to_add

    def PlantSpecificGetReq(self,url_adaptor,userId,plant_code):

        mesurements_past_hour=self.get_response(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=moisture&duration=1")
        
        # mesurements_past_hour=json.loads(req.get(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=moisture&duration=1").text)

        if len(mesurements_past_hour)==0:
            mesurements_past_hour = [{"t": f"{datetime.now()}, {time.time()}", "v": self.moisture_goals + 1}]
            return mesurements_past_hour
        else: 
            return mesurements_past_hour

class run(object): 
    def __init__(self,settings):
        
        
        self.function = MoistureMonitoring(settings)
        self.function.start()
        
    def run(self):
        
        try:
            start = time.time()
            while True:

                    if time.time()-start > 60:
                        self.function.MyPublish("function")
                        start = time.time()
                    self.function.MyPublish("alive")     
                    time.sleep(15)

                
        except KeyboardInterrupt:
                self.function.stop()


if __name__ == "__main__":

    time.sleep(5)
    settings=json.load(open("configWat.json",'r'))
    tFunction = run(settings)
    print("> Starting thread_function...")
    tFunction.run()


