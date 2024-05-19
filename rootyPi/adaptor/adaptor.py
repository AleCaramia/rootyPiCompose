from datetime import datetime
import time
import os
from influxdb_client import InfluxDBClient, Point, WritePrecision, BucketRetentionRules
from influxdb_client.client.write_api import SYNCHRONOUS
import json
import cherrypy
import paho.mqtt.client as PahoMQTT
import time
import threading
from pathlib import Path
import os
import requests

P = Path(__file__).parent.absolute()
SETTINGS = P / "settings.json"


#load_dotenv()
# You can generate a Token from the "Tokens Tab" in the UI
#token = "I2WHZha1ZTc8b4aS0atqZyG4kS-FPbBBs_iLONjqmFOysTwUHrdy8GK5HrUIF7mPLpBTMJJ8aFGO9qDG8lUyWA==" token1
token = "56a2fc64e4b1ef0ee725f0e900a43eb511942d859dbbfa864e28adf029227938"
org = "rootyPi"
#url = "http://localhost:8086"
#bucket = "Test"
#client = InfluxDBClient(url="http://localhost:8086", token=token)
#write_api = client.write_api(write_options=SYNCHRONOUS)


#record = '{"measurement": "humidity","fields": { "humidity": 55.2, "temp": 23 }}'
#write_api.write(bucket=bucket, org="IOT", record=json.loads(record))
def senmlToInflux(senml):
    output = []   
    for e in senml["e"]:
        point = {
        "measurement":"",
        "tags":"",
        "fields": ""
        }
        point["measurement"] = senml["bn"].split("/")[2]
        print(type(e))
        ex = json.loads(e)
        point["tags"] = {"unit": ex["u"]}
        point["fields"] = {ex["n"]:ex["v"]}
        output.append(point)
    return output  
class Adaptor(object):
    exposed=True
    possMeasures=["humidity", "temperature","moisture", "dli", "tankLvl", "sunlight"]
    connectorBaseUrl = "http://192.68.0.24:8081"
    #example where do we save this?
    def __init__(self):
        token = "56a2fc64e4b1ef0ee725f0e900a43eb511942d859dbbfa864e28adf029227938"
        self.org = "rootyPi"
        self.url = "http://192.68.0.25:8080"
        self.client = InfluxDBClient(url="http://192.68.0.21:8086", token=token)
        self.bucket_api = self.client.buckets_api()
        self.loadUsers()
        
    def loadUsers(self):
        url = self.connectorBaseUrl + "/users"
        input = requests.get(url)
        self.users = json.loads(input._content)
    def checkUserPresent(self, userId):
        for user in self.users:
            if user["userId"] == userId:
                return True
        return False
    def checkPlantPresent(self,userId, plantId):
        for user in self.users:
            if user["userId"] == userId:
                for plant in user["plants"]:
                    if plant["plantId"] == plantId:
                        return True
        return False
        
        
    def start(self):
        conf={
            '/':{
            'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on':True
            }
        }
        cherrypy.tree.mount(self,'/',conf)
        cherrypy.config.update({'server.socket_port': 8080})
        cherrypy.config.update({'server.socket_host':'0.0.0.0'})
        cherrypy.engine.start()
        #cherrypy.engine.block()
        
    def stop(self):
        pass
        
    def GET(self,*uri,**params):
        #http://localhost:8080/getData/user1?measurament=humidity&duration=1 
        if len(uri) == 0:
            return open("index.html")
        elif len(uri)!=0:
            if uri[0] == "getData":
                print(1)
                if self.checkUserPresent(uri[1]):
                    if self.checkPlantPresent(uri[1],uri[2]): 
                        #if params[0] in self.uri[1].getBuckets(): 
                        print(2)
                        if params["measurament"] in self.possMeasures:
                            try:
                                duration = int(params["duration"])
                            except:
                                raise cherrypy.HTTPError("400", "invalid duration")
                            bucket = uri[1]
                            org = "rootyPi"
                            #query = f'from(bucket:"{bucket}") |> range(start: -1h) |> filter(fn:(r) => r["_measurement"] == "plant1"))'#test query    
                            query = f'from(bucket: "{bucket}") \
                                |> range(start: -{duration}h) \
                                    |> filter(fn: (r) => r["_measurement"] == "{uri[2]}") \
                                        |> filter(fn: (r) => r["_field"] == "{params["measurament"]}")'
                            tables = self.client.query_api().query(org=org, query=query)
                            out = []
                            for table in tables:
                                for row in table.records:
                                    line = {"t": row.get_time().strftime("%m/%d/%Y, %H:%M:%S"), "v": row.get_value()}
                                    #print(line)
                                    print(type(row.get_time()))
                                    out.append(line)
                                    #out = out + (f"Time: {row.get_time().strftime("%m/%d/%Y, %H:%M:%S")}, Value: {row.get_value()}\n")
                            return json.dumps(out)
                    else:
                        raise cherrypy.HTTPError("400", "Invalid plantId")                    
                else:
                    raise cherrypy.HTTPError("400", "Invalid User")
            elif uri[0] == "getUsers":
                url = self.connectorBaseUrl + "/users"
                return requests.get(url)
            else:
                raise cherrypy.HTTPError("400", "Invalid operation")

    
    def PUT(self,*uri,**params):
        return  
    
    def POST(self,*uri,**params):
        if uri[0] == "addUser":
            body = json.loads(cherrypy.request.body.read())
            url = self.connectorBaseUrl + "/addu/" + body["input1"]
            data = { 'userId': body["input1"], 'password': body["input2"]}
            headers = {'content-type': 'application/json; charset=UTF-8'}
            response = requests.post(url, data=json.dumps(data), headers=headers)
            print(response.text)
            r = json.loads(response.text)
            if r["status"] == "OK":
                newUser = data = { 'userId': body["input1"], "plants": []}
                self.users.append(newUser)
                self.addUserBuckets(body["input1"])
            return response.text  
        elif uri[0] == "addPlant":
            body = json.loads(cherrypy.request.body.read())
            url = self.connectorBaseUrl + "/addp/" + body["input1"]
            data = { 'plantId': body["input2"],'code': "", 'ownerId': body["input1"],"plantType": "Evergreen"}
            headers = {'content-type': 'application/json; charset=UTF-8'}
            response = requests.post(url, data=json.dumps(data), headers=headers)
            print(response.text)
            r = json.loads(response.text)
            if r["status"] == "OK":
                index = 0
                plant = {"plantId": body["input2"], 'code': "", 'ownerId': body["input1"], "plantType": "Evergreen"}
                for user in self.users:
                    if user["userId"] == body["input1"]:
                        user["plants"].append(plant)
                    index += 1
                print(self.users)
                print(f"Added plant {body['input2']}to user: {body['input1']}")
            return response.text 
    def DELETE(self,*uri,**params):
        if uri[0] == "deleteUser":
            #body = json.loads(cherrypy.request.body.read())
            url = self.connectorBaseUrl + "/rmu/" + uri[1]
            #data = { 'userId': body["input1"]}
            headers = {'content-type': 'application/json; charset=UTF-8'}
            response = requests.delete(url)
            print(response.text)
            r = json.loads(response.text)
            if r["status"] == "OK":
                index = 0
                for user in self.users:
                    if user["userId"] == uri[1]:
                        del self.users[index]
                    index += 1
                self.deleteUserBuckets(uri[1])
                print(f"Deleted {uri[1]}'s buckets")
            return response.text  
        elif uri[0] == "deletePlant":
            #body = json.loads(cherrypy.request.body.read())
            url = self.connectorBaseUrl + "/rmp/" + uri[1] + "/" + uri[2]
            headers = {'content-type': 'application/json; charset=UTF-8'}
            response = requests.delete(url)
            print(response.text)
            r = json.loads(response.text)
            if r["status"] == "OK":
                index = 0
                for user in self.users:
                    if user["userId"] == uri[1]:
                        for plant in user["plants"]:
                            if plant["plantId"] == uri[2]:
                                user["plants"].remove(plant)
                    index += 1
                print(self.users)
                print(f"Deleted plant:{uri[2]} from {uri[1]}")
            return response.text  
            
        
            
        
    def addUserBuckets(self, userID):  
        retention_rules = BucketRetentionRules(type="expire", every_seconds=2592000)
        created_bucket = self.bucket_api.create_bucket(bucket_name=f"{userID}", retention_rules = retention_rules,org = self.org)
        print(created_bucket)
    def addPlant(self, userID, plantID):
        self.dictUserPlants[userID].append(plantID)
        self.write_usersPlants()
        print(f"Added plant: {plantID} to {userID}")
    def listBuckets(self):
        buckets = self.bucket_api.find_buckets().buckets
        return buckets
    def deleteUserBuckets(self, userID):
        buckets = self.listBuckets()
        for bucket in buckets:
            if bucket.name.startswith(userID):
                self.bucket_api.delete_bucket(bucket)
                print(f"Succesfully deleted bucket: {bucket.name}")
    def publish(self, data, destination):#data in json format
        converted = senmlToInflux(data)
        #bucket #decided by destination taken from mqtt topic
        #write_api.write(bucket=bucket, org="IOT", record=converted)

class MySubscriber:
        def __init__(self, clientID, topic, broker, port, write_api):
            self.clientID = clientID
			# create an instance of paho.mqtt.client
            self._paho_mqtt = PahoMQTT.Client(clientID, False) 
            
			# register the callback
            self._paho_mqtt.on_connect = self.myOnConnect
            self._paho_mqtt.on_message = self.myOnMessageReceived 
            self.write_api = write_api
            #self.client = client, self.write_api = client.write_api(write_options=SYNCHRONOUS)
            self.topic = topic
            self.messageBroker = broker
            self.port = port



        def start (self):
            #manage connection to broker
            self._paho_mqtt.connect(self.messageBroker, self.port)
            self._paho_mqtt.loop_start()
            # subscribe for a topic
            self._paho_mqtt.subscribe(self.topic, 2)

        def stop (self):
            self._paho_mqtt.unsubscribe(self.topic)
            self._paho_mqtt.loop_stop()
            self._paho_mqtt.disconnect()

        def myOnConnect (self, paho_mqtt, userdata, flags, rc):
            print ("Connected to %s with result code: %d" % (self.messageBroker, rc))

        def myOnMessageReceived (self, paho_mqtt , userdata, msg):
            # A new message is received
            #modify here
            #record = '{"measurement": "humidity","fields": { "humidity": 55.2, "temp": 23 }}'
            #write_api.write(bucket=bucket, org="IOT", record=json.loads(record))
            #print ("Topic:'" + msg.topic+"', QoS: '"+str(msg.qos)+"' Message: '"+str(msg.payload) + "'")
            userId = msg.topic.split("/")[1]
            plantId = msg.topic.split("/")[2]
            bucket = userId
            test = json.loads(str(msg.payload).replace("\\\\", "\\").split("'")[1])
            #print(json.loads(senmlToInflux(test)))
            converted = senmlToInflux(test)
            #print(senmlToInflux(test))
            for c in converted:
                pass
                print(c)                
                self.write_api.write(bucket=bucket, org="rootyPi", record= c)

# Threads
class MQTTreciver(threading.Thread):
    """ Data are collected for 15 seconds and then published.
    So we call the class MySubscriber and the methods
    """

    def __init__(self, ThreadID, name):
        """Initialise thread widh ID and name."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        with open(SETTINGS, 'r') as file:
            data = json.load(file)
        self.topic = data["base_topic"]
        self.broker = data["broker"]
        self.mqtt_port = int(data["port"])
        self.client = InfluxDBClient(url=data["url_db"], token=data["influx_token"])
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def run(self):
        """Run thread."""
        global time_flag
        print(self.topic)
        # Start subscriber.
        sub = MySubscriber("J", self.topic, self.broker, self.mqtt_port, self.write_api)
        sub.start()

        while True:
            time.sleep(1)

            #while time_flag == 0: 
            """# wait untill the time_flag becomes 1, so every 15 sec except the first cycle that we have
                global time_flag = 1"""
            #    time.sleep(0.1)

            # waiting for the connection. when the system is connected to the broker, loop_flag becomes false
            #while loop_flag:
                #print("Waiting for connection...")
                #time.sleep(0.1)

            # Collecting data for 15 seconds. it stops when the time_flag becomes 0 (so after 15 sec)
            # while time_flag == 1:
            #    time.sleep(0.1)

            # Publish json data on thingspeak. Different patient=different channel
            #print(self.ts_url)
            #data_publish(sub.send_data(), self.ts_url)
        
    
class Tunneling(threading.Thread):
    """Old device remover thread.
    Remove old devices which do not send alive messages anymore.
    Devices are removed every five minutes.
    """

    def __init__(self, ThreadID, name):
        """Initialise thread widh ID and name."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = self.name

    def run(self):
        """Run thread."""
        os.system("ngrok http --domain=mako-keen-rarely.ngrok-free.app 8080")    
        

if __name__ == '__main__':
    #Standard configuration to serve the url "localhost:8080"
    adaptor = Adaptor()
    adaptor.start()
    
    reciver = MQTTreciver(1, "mqttReciver")
    reciver.run()
    
    #tunneling = Tunneling(1, "Tunneling")
    #tunneling.run()
    
    #adaptor.deleteUserBuckets("User1")
    #print(adaptor.listBuckets())

    #query = f'from(bucket:"{bucket}") |> range(start: -1h)'#test query

    # Query data from the bucket
    #tables = client.query_api().query(org=org, query=query)

    # Print the results
    #for table in tables:
        #for row in table.records:
            #pass
            #print(row)
            #print(f"Time: {row.get_time()}, Value: {row.get_value()}")
    #end    
        
    


    
    

