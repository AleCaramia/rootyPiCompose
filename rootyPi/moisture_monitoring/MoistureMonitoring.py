import cherrypy
import paho.mqtt.client as PahoMQTT
import cherrypy
import time
import json
import numpy as np
import requests as req
import threading
from datetime import datetime

#devo cambiare il modo in cui prendo la perc intensità
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
        
        ###
        self.url_registry=settings['url_registry']
        self.url_adaptor=settings['url_adaptor']


        ###############################################à

        
        self._paho_mqtt=PahoMQTT.Client(self.clientID, True)
        self._paho_mqtt.on_connect=self.MyOnConnect
        #"{'n': 'light_deficit', 'unit': 'lux', 't': 1715156806.582416, 'v': 1383.6867064141877}"
        self.__message={"bn":"", 'e':[{'n':'water_deficit','unit':"percent",'t':'','v':None }]}

        

    def start(self):
        self._paho_mqtt.connect(self.broker,self.port)
        self._paho_mqtt.loop_start()

    def stop(self):
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()

    def MyOnConnect(self,paho_mqtt,userdata,flags,rc):
        print(f"MoistureMonitoring: Connected to {self.broker} with result code {rc} \n subtopic {None}, pubtopic PROVA")

    def MyPublish(self, type):

        # users_plant=json.loads(req.get("http://localhost:8080/getUsers")) #http://localhost:8080/getData/user1?measurament=humidity&duration=1
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

        response=req.get(f"{self.url_registry}/plants")
        plants=json.loads(response.text)
        models=json.loads((req.get(f"{self.url_registry}/models")).text)
        active_services=json.loads(req.get(f"{self.url_registry}/services").text)
        # with open("fake_catalogue.json",'r') as file:
        #     catalogue = json.loads(file.read())
        # plants = catalogue['plants']
        # models=catalogue['models']
        # active_services=catalogue['services']


        # for service in active_services:
        #     if service['name']=="adaptor":
        #         url_adptor=service['url']
        url_adaptor=self.url_adaptor
        # users_plant= self.temp_users
        return plants,url_adaptor,models
    
    def retriveMaxFlowPumpAndJarVolume(self,plant_code,models):
        vase_type=plant_code[:2]
        for model in models:
            if model['model_code']==vase_type:
                # max_lux_lamp=model["max_flow"]
                jar_volume=model["jar_volume"]
                break
        return jar_volume

    def PlantWaterEstimation(self,url_adptor,plant_code,plant_type,userId,jar_volume):               
        

        # Devo fare una request per sapere la misurazione della pianta (nome misurazione place holder)
        # mesurements_past_hour,perc_intensity_lamp=self.PlantSpecificGetReq(userId,plantId)
        plants_type=json.loads((req.get(f"{self.url_registry}/valid_plant_types")).text)
        for plant in plants_type:
            if plant_type == plant["type"]:
                self.moisture_goals=float(plant["moisture_goal"])
                break
        mesurements_past_hour=self.PlantSpecificGetReq(url_adptor,userId,plant_code)#aggiungo i dli dati fin ora
        # print(type(mesurements_past_hour))
        # print(mesurements_past_hour)
        #ipotizzando siano lux al secondo e siano in un vettore
        # lux_past_hour=self.LuxPastHour(mesurements_past_hour)
        
        # with open("fake_catalogue.json",'r') as file:
        #     catalogue = json.loads(file.read())
        # plants_type = catalogue['valid_plant_types']
        # print(mesurements_past_hour)
        # print(type(mesurements_past_hour))
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
        #print(req.get(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=light&duration=1").text)
        
        mesurements_past_hour=json.loads(req.get(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=moisture&duration=1").text)
        # mesurements_past_hour = np.random.randint(0,100,1000)
        if len(mesurements_past_hour)==0:
            mesurements_past_hour = [{"t": f"{datetime.now()}, {time.time()}", "v": self.moisture_goals + 1}]
            return mesurements_past_hour
        else: 
            return mesurements_past_hour

    
    

    
###################################################################################################################################################

            
#################################################################################################################################################à

# class Iamalive(object):
#     "I am alive"

#     def __init__(self,settings):
    

#         # mqtt attributes
#         self.base_topic=settings['pub_topic_Iamalive']
#         self.port=settings['port']
#         self.broker=settings['broker']
#         self.clientID=settings['ID_Iamalive']

#         self.topic = f"{self.base_topic}/{self.clientID}"       
#         # self.pub_topic = self.clientID

#         self.client = PahoMQTT.Client(self.clientID, True)
#         self.client.on_connect = self.myconnect
#         #########################################################################################
#         #Il message è da definire, vedere come preferisce ale
#         self.message = {"bn":"updateCatalogService","e":[{"n":"MoistureMonitoring", "t": time.time(), "v":None,"u":"IP"}]}
#         #########################################################################################à
#         self.time = time.time()
    
#     def start_mqtt(self):
#         self.client.connect(self.broker,self.port)
#         self.client.loop_start()
#         # Avvia il metodo self.control_state() come thread
#         # control_thread = threading.Thread(target=self.control_state)
#         # control_thread.start()
#         # self.publish()
    
#     def myconnect(self,paho_mqtt, userdata, flags, rc):
#        print(f"AlIVE: Connected to {self.broker} with result code {rc} \n subtopic {None}, pubtopic {self.topic}")

#     def publish(self):           
#         __message=json.dumps(self.message)
#         print(__message)
#         self.client.publish(topic=self.topic,payload=__message,qos=2)

################################################################################################################################################
class run(object): 
    def __init__(self,settings):
        
        # self.env_time="EnviromentMonitoring\envTime.json"
        
        self.function = MoistureMonitoring(settings)
        self.function.start()
        
            # DEVO METTERE CHE NON PARTE SE L'orario corrente NON VA BENE
    def run(self):
        
        try:
            start = time.time()
            while True:
                # current_time = datetime.now().time()
                # if current_time>self.start_time:
                    if time.time()-start > 3600:
                        self.function.MyPublish("function")
                        start = time.time()
                    self.function.MyPublish("alive")     
                    time.sleep(15)
                # else:
                #     time.sleep(15)
                
        except KeyboardInterrupt:
                self.function.stop()


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

##############################################################################################################################################à
# class ThreadServer(object):
#     def __init__(self):
#         self.url="http://192.68.0.24:8081"
#         self.server=EnvMonitoringTime()

#     def start(self):
#         conf={
#             '/':{
#             'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
#             'tools.sessions.on':True
#             }
#         }
#         cherrypy.tree.mount(self.server,'/',conf)
#         cherrypy.config.update({'server.socket_port': 8085})
#         cherrypy.config.update({'server.socket_host':'0.0.0.0'})
#         cherrypy.engine.start()

# def start_env_monitoring():
#     settings=json.load(open("configEnv.json",'r'))
#     url_registry=settings["url_registry"]
#     registartion_payload={"serviceID":settings['ID']}
#     response=req.put(url_registry,data=json.dumps(registartion_payload))
    
#     # base_topic=settings['basetopic']
#     # port=settings['port']
#     # broker=settings['broker']
#     # clientID=settings['ID']
#     # DLi_goals=settings["DlI_goals"]
#     return settings,response


    
#########################################################################################################################################
if __name__ == "__main__":

    time.sleep(5)
    # settings,response=start_env_monitoring()
    settings=json.load(open("configWat.json",'r'))
    #thread2 = AliveThread(2, "aliveThread", settings)
    #thread2.start()
    # Alive = Iamalive(settings)
    # thread_Alive = threading.Thread(target=Alive.start_mqtt)
    #print("> Starting I am alive...")
    
    # webserver= ThreadServer()
    # thread_server = threading.Thread(target=webserver.start())
    # print("> Starting thread_server...")
    # thread_server.start()

    tFunction = run(settings)
    #thread_function = threading.Thread(target=tFunction.RunThred())
    print("> Starting thread_function...")
    tFunction.run()


