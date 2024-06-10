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
class EnvMonitoring(object):
    def __init__(self,settings):
        #load settings
        self.base_topic=settings['basetopic']
        self.port=settings['port']
        self.broker=settings['broker']
        self.clientID=settings['ID']
        self.goals=settings["DlI_goals"]
        self.default_time=settings['default_time']
        
        ###
        self.url_registry=settings['url_registry']
        self.url_adaptor=settings['url_adaptor']


        # self.envTime=env_time
        ###############################################à
        # self.temp_users=json.load(open("EnviromentMonitoring/temp_users.json",'r'))
        # self.temp_mesure=json.load(open("EnviromentMonitoring/temp_mesures.json",'r'))
        # self.temp_light_status=json.load(open("EnviromentMonitoring/temp_light_status.json",'r'))
        #################################################à
        
        self._paho_mqtt=PahoMQTT.Client(self.clientID, True)
        self._paho_mqtt.on_connect=self.MyOnConnect
        #"{'n': 'light_deficit', 'unit': 'lux', 't': 1715156806.582416, 'v': 1383.6867064141877}"
        self.__message={"bn":"", 'e':[{'n':'light_deficit','u':"lux",'t':'','v':None }
                                                 ]}
        self.dli_rec_message={"bn":"", 'e':[{'n':'DLI','u':"DLI",'t':'','v':None }
                                                 ]}

        # self.maxLuxLamp= 20 #place holder
        

    def start(self):
        self._paho_mqtt.connect(self.broker,self.port)
        self._paho_mqtt.loop_start()

    def stop(self):
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()

    def MyOnConnect(self,paho_mqtt,userdata,flags,rc):
        print(f"EnvMonitoring: Connected to {self.broker} with result code {rc} \n subtopic {None}, pubtopic PROVA")

    def MyPublish(self):

        # users_plant=json.loads(req.get("http://localhost:8080/getUsers")) #http://localhost:8080/getData/user1?measurament=humidity&duration=1
        plants,url_adptor,models=self.RequestsToRegistry() 
        
        for plant in plants:
                
                plant_type=plant['type']
                plantId=plant['plantId']
                #print(plantId)
                userId=plant['userId']
                plant_code=plant["plantCode"]

                max_lux_lamp=self.retriveMaxLuxLamp(plant_code,models)

                start_time=plant['auto_init']
                end_time=plant['auto_end']

                current_time = datetime.now().time()
                current_datetime = datetime.combine(datetime.today(), current_time)
                start_datetime = datetime.combine(datetime.today(),datetime.strptime(start_time, '%H:%M').time())
                time_difference = current_datetime - start_datetime
                hours_passed = max(round(time_difference.total_seconds() / 3600),1)

                end_datetime = datetime.combine(datetime.today(), datetime.strptime(end_time, '%H:%M').time())
                time_difference = end_datetime - start_datetime
                suncycle = round(time_difference.total_seconds() / 3600)

                lux_to_add,dli_recived_past_hour=self.PlantLuxEstimation(url_adptor,plant_code,plant_type,userId,hours_passed,suncycle,max_lux_lamp)
                current_msg=self.__message.copy()
                
                current_topic=f"{self.base_topic}/{userId}/{plant_code}/lux_to_give/automatic"

                current_msg['e'][0]['t']=time.time()
                current_msg['e'][0]['v']=lux_to_add
                current_msg['bn']=current_topic
                
                topicDLI=f"{self.base_topic}/{userId}/{plant_code}/DLI"
                dli_mess=self.dli_rec_message.copy()
                dli_mess['e'][0]['t']=time.time()
                dli_mess['e'][0]['v']=dli_recived_past_hour
                dli_mess['bn']=topicDLI
                dli_mess=json.dumps(dli_mess)
                self._paho_mqtt.publish(topic=topicDLI,payload=dli_mess,qos=2)
                #req.post("-------------",dli_recived_past_hour)
                print(dli_mess)

                #Rootypy/usern/plantn/lux_to_give/automatic
                

                __message=json.dumps(current_msg)
                if current_datetime>=start_datetime and current_datetime<=end_datetime:
                    print(__message)
                    self._paho_mqtt.publish(topic=current_topic,payload=__message,qos=2)
                    

        return 
    
    def RequestsToRegistry(self):
        #Devo farla al registry
        response=req.get(f"{self.url_registry}/plants")
  
        plants=json.loads(response.text)
        models=json.loads((req.get(f"{self.url_registry}/models")).text)
        active_services=json.loads(req.get(f"{self.url_registry}/services").text)
        # for service in active_services:
        #     if service['name']=="adaptor":
        #         url_adptor=service['url']
        url_adaptor=self.url_adaptor

        # users_plant= self.temp_users
        return plants,url_adaptor,models
        
    def retriveMaxLuxLamp(self,plant_code,models):
        vase_type=plant_code[:2]
        for model in models:
            if model['model_code']==vase_type:
                max_lux_lamp=model["max_lux"]
                break
        return max_lux_lamp

    def PlantLuxEstimation(self,url_adptor,plant_code,plant_type,userId,hours_passed,suncycle,max_lux_lamp):               
        

        # Devo fare una request per sapere la misurazione della pianta (nome misurazione place holder)
        # mesurements_past_hour,perc_intensity_lamp=self.PlantSpecificGetReq(userId,plantId)
        mesurements_past_hour,DLI_daily_record,lamp_intensity_past_hour=self.PlantSpecificGetReq(url_adptor,userId,plant_code,hours_passed)#aggiungo i dli dati fin ora
        #ipotizzando siano lux al secondo e siano in un vettore
        # lux_past_hour=self.LuxPastHour(mesurements_past_hour)
        lux_past_hour,mean_lamp_intensity,dli_given_today=self.LuxPastHour(mesurements_past_hour,lamp_intensity_past_hour,DLI_daily_record)  
        current_plant_goal=self.goals[plant_type]

        lux_to_add,dli_recived_past_hour=self.LuxDeficitCalculation(current_plant_goal,suncycle,lux_past_hour,mean_lamp_intensity,dli_given_today,hours_passed,max_lux_lamp)
    
        return lux_to_add,dli_recived_past_hour

    def PlantSpecificGetReq(self,url_adaptor,userId,plant_code,hours_passed):
        #print(req.get(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=light&duration=1").text)
        
        mesurements_past_hour=json.loads(req.get(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=light&duration=1").text)
        lamp_intensity_past_hour=json.loads(req.get(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=lightShift&duration=1").text)
        # mesurements_past_hour=self.temp_mesure['light']
        #me lo sono inventato io "http://localhost:8080/getStatus/{userId}/{plantId}?status=DI COSA RICHIEDO LO STATUS&duration=DI QUANDO"
        # perc_intensity_lamp=json.loads(req.get(f"http://localhost:8080/getStatus/{userId}/{plantId}?status=light_intensity&duration=1")) #da definire output
        # perc_intensity_lamp=self.temp_light_status['v']
        print(hours_passed)
    ################################################################################
        DLI_daily_record=json.loads(req.get(f"{url_adaptor}/getData/{userId}/{plant_code}?measurament=DLI&duration={hours_passed}").text)
        # DLI_daily_record=self.temp_mesure['DLI']
        #qua devo gestire il caso di inizio giornata-> no dli record
    ###################################################################################
        return mesurements_past_hour,DLI_daily_record,lamp_intensity_past_hour

    def LuxPastHour(self,mesurments_past_hour,lamp_intensity_past_hour,DLI_daily_record):
        lux_past_hour_v=[]
        lamp_past_hour_v=[]
        dli_given_today=0
        if len(mesurments_past_hour)>0:
            for mesure in mesurments_past_hour:
                lux_past_hour_v.append(mesure['v'])
            lux_past_hour=np.mean(lux_past_hour_v)
        else:
            lux_past_hour=0

        if len(lamp_intensity_past_hour)>0:
            for intensity in lamp_intensity_past_hour:
                lamp_past_hour_v.append(intensity['v'])
            mean_light_intensity=np.mean(lamp_past_hour_v)
        else:
            mean_light_intensity=0

        if len(DLI_daily_record)>0:
            for dli in DLI_daily_record:
                dli_given_today=dli_given_today+dli['v']

        return lux_past_hour,mean_light_intensity,dli_given_today
    
    def PlantGoal(self,plant_type):
        if plant_type in self.goals.keys():
            current_plant_goal=self.goals[plant_type]

        return current_plant_goal
    
  
    def LuxDeficitCalculation(self,DLI_goal,sun_cycle,registered_Lux_hour,mean_lamp_intensity,dli_given_today,hours_passed,max_lux_lamp):
    #perc_intensity_lamp: At wich percentage of the intensity has the lamp work, makes get request to SHIFT
    #registered_Lux_hour: in the past hour, how many lux have been recived from the sensor. Need get request of past hour to database
    #maxLuxLamp: How many lux can emit the SPECIFIC LAMP

        PPFDlamp=max_lux_lamp*(mean_lamp_intensity/100)*0.0135 #the factor depends on kind of lamp
        print(f'PPFDlamp:{PPFDlamp}')
        PPFDsun=(registered_Lux_hour-(max_lux_lamp*mean_lamp_intensity/100))*0.0185
        print(f"PPFDsun: {PPFDsun}")
        PPFDtot=PPFDsun+PPFDlamp
        DLIsun_hour=PPFDsun*0.0036
        DLIrecived_hour=PPFDtot*0.0036
        print(f"DLIrecived_hour: {DLIrecived_hour}")
#################################################################
        #NUOVA VERSIONE DEL CALCOLO: Adesso calcolo il deficit nella giornata fin ora       
        DLIhgoal=DLI_goal/sun_cycle
        DLI_current_goal=DLIhgoal*hours_passed
        print(f"DLI_current_goal: {DLI_current_goal}")
        if dli_given_today<DLI_current_goal:
            DLI_toAdd=DLI_current_goal-dli_given_today
            Lux_toAdd=DLI_toAdd/(0.0135*0.0036)
        else:
            Lux_toAdd = 0

        # Lux_recived=DLIrecived_hour/
        return Lux_toAdd,DLIrecived_hour
    
###################################################################################################################################################

            
#################################################################################################################################################à

class Iamalive(object):
    "I am alive"

    def __init__(self,settings):
    

        # mqtt attributes
        self.base_topic=settings['basetopic']
        self.port=settings['port']
        self.broker=settings['broker']
        self.clientID=settings['ID']+"alive"

        self.topic = f"{self.base_topic}/{self.clientID}"       
        # self.pub_topic = self.clientID

        self.client = PahoMQTT.Client(self.clientID, True)
        self.client.on_connect = self.myconnect
        #########################################################################################
        #Il message è da definire, vedere come preferisce ale
        self.message = {"bn":"updateCatalogService","e":[{"n": settings['ID'], "t": time.time(), "v":None,"u":"IP"}]}
        #########################################################################################à
        self.time = time.time()
    
    def start_mqtt(self):
        self.client.connect(self.broker,self.port)
        self.client.loop_start()
        # Avvia il metodo self.control_state() come thread
        # control_thread = threading.Thread(target=self.control_state)
        # control_thread.start()
        # self.publish()
    
    def myconnect(self,paho_mqtt, userdata, flags, rc):
       print(f"AlIVE: Connected to {self.broker} with result code {rc} \n subtopic {None}, pubtopic {self.topic}")

    def publish(self):           
        __message=json.dumps(self.message)
        print(__message)
        self.client.publish(topic=self.topic,payload=__message,qos=2)
    
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

################################################################################################################################################
class thredFunction(threading.Thread): 
    def __init__(self,ThreadID,name,settings):
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        self.settings=settings
        # self.env_time="EnviromentMonitoring\envTime.json"
        # DEVO METTERE CHE NON PARTE SE L'orario corrente NON VA BENE
    def run(self):
        self.function = EnvMonitoring(self.settings)
        self.function.start()
        # try:
        while True:
                # current_time = datetime.now().time()
                # if current_time>self.start_time:
            self.function.MyPublish()        
            time.sleep(15)
                # else:
                #     time.sleep(15)
                
        # except KeyboardInterrupt:
        #         self.function.stop()

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

def main():
    # try:
        time.sleep(5)
        # settings,response=start_env_monitoring()
        settings=json.load(open("configEnv.json",'r'))
        thread2 = AliveThread(2, "aliveThread", settings)
        thread2.start()
        # Alive = Iamalive(settings)
        # thread_Alive = threading.Thread(target=Alive.start_mqtt)
        print("> Starting I am alive...")
        # thread_Alive.start()
        
        # webserver= ThreadServer()
        # thread_server = threading.Thread(target=webserver.start())
        # print("> Starting thread_server...")
        # thread_server.start()

        thread1 = thredFunction(1,'Function',settings)
        #thread_function = threading.Thread(target=tFunction.RunThred())
        print("> Starting thread_function...")
        thread1.start()

        # while True:
        #     time.sleep(3)
    # except:
    #     pass

if __name__ == "__main__":
    main()
 

