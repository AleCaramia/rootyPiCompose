import json
import requests
import time
import datetime
import paho.mqtt.client as pahoMQTT
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image
import paho.mqtt.client as mqtt
import base64
import threading
import cherrypy
from datetime import datetime, timedelta

def hourly_timestamps_unix(start_time, end_time):
    """
    Generate a list of timestamps at hourly intervals between two given Unix timestamps.

    Args:
    start_time (int): The starting timestamp in Unix format.
    end_time (int): The ending timestamp in Unix format.

    Returns:
    list: A list of Unix timestamps at hourly intervals.
    """
    start = datetime.fromtimestamp(start_time)
    end = datetime.fromtimestamp(end_time)
    
    # Ensure start is on the hour
    if start.minute != 0 or start.second != 0:
        start = (start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))

    current = start
    timestamps = []

    while current <= end:
        timestamps.append(int(current.timestamp()))
        current += timedelta(hours=1)

    return timestamps  

def convert_timestamps(timestamps, duration):
    """
    Converts a list of Unix timestamps into hours or days based on the duration.
    
    Parameters:
    timestamps (list of int): List of Unix timestamps.
    duration (int): The duration to determine the format of conversion.

    Returns:
    list of str: List of converted timestamps in the specified format.
    """
    converted_timestamps = []
    
    if duration > 6*24:
        # Convert to days format
        for ts in timestamps:
            dt = datetime.utcfromtimestamp(ts)
            converted_timestamps.append(dt.strftime('%Y-%m-%d'))
    elif duration > 25:
        # Convert to hours format
        for ts in timestamps:
            dt = datetime.utcfromtimestamp(ts)
            converted_timestamps.append(dt.strftime('%Y-%m-%d %H:%M:%S'))
    else:
        # Return timestamps as is (Unix format)
        converted_timestamps = timestamps
    
    return converted_timestamps

class Report_generator(object):
            
    exposed = True

    def __init__(self,config_path,stop_event):
        config =  json.load(open(config_path,'r'))
        self.registry_url = config['url_registry']
        #self.registry_url = 'http://127.0.0.1:8080'
        self.headers = config['headers']
        self.ID = config['ID']
        self.broker = config['broker']
        self.port = config['port']
        self.stop_event = stop_event
        self.start_web_server( )

    def start_web_server(self):


        conf={
            '/':{
            'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on':True
            }
        }
        cherrypy.tree.mount(self,'/',conf)
        cherrypy.config.update({'server.socket_port': 8081})
        cherrypy.config.update({'server.socket_host':'0.0.0.0'})
        cherrypy.engine.start()
        #cherrypy.engine.block()
        
    def stop_server(self):
        pass


    def plot_lux_intensity(self, sunlight_timestamps, sunlight_lux, lamp_timestamps, lamp_lux):
        """
        Plots the lux intensity values over time for sunlight and lamp.
        
        :param sunlight_timestamps: List of timestamps for sunlight.
        :param sunlight_lux: List of lux values for sunlight.
        :param lamp_timestamps: List of timestamps for lamp.
        :param lamp_lux: List of lux values for lamp.
        :return: BytesIO object containing the plot image.
        """
        plt.figure(figsize=(10, 6))
        
        # Plot sunlight lux intensity
        plt.plot(sunlight_timestamps, sunlight_lux, label='Sunlight Lux', marker='o', linestyle='-')
        
        # Plot lamp lux intensity
        plt.plot(lamp_timestamps, lamp_lux, label='Lamp Lux', marker='x', linestyle='--')
        
        # Set the title and labels
        plt.title('Lux Intensity Over Time')
        plt.xlabel('Time')
        plt.ylabel('Lux Intensity')
        plt.legend()
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save the plot to a BytesIO object
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        
        # Display the plot
        #plt.show()
        
        return buffer

    def plot_soil_moisture(self, timestamps, moisture_values):
        """
        Plots the soil moisture values over time.
        
        :param timestamps: List of timestamps.
        :param moisture_values: List of soil moisture values.
        :return: BytesIO object containing the plot image.
        """
        plt.figure(figsize=(10, 6))
        plt.plot(timestamps, moisture_values, label='Soil Moisture', marker='o', linestyle='-')
        plt.title('Soil Moisture Over Time')
        plt.xlabel('Time')
        plt.ylabel('Soil Moisture')
        plt.legend()
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save the plot to a BytesIO object
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
    
        return buffer
    
    def concatenate_images_vertically(self, buffer1, buffer2):
        """
        Concatenates two images vertically from BytesIO buffers and returns a new BytesIO buffer containing the combined image.
        
        :param buffer1: BytesIO object containing the first image.
        :param buffer2: BytesIO object containing the second image.
        :return: BytesIO object containing the concatenated image.
        """
        # Load images from buffers
        image1 = Image.open(buffer1)
        image2 = Image.open(buffer2)
        
        # Get dimensions
        width1, height1 = image1.size
        width2, height2 = image2.size
        
        # Create a new image with combined height
        total_height = height1 + height2
        combined_image = Image.new('RGB', (max(width1, width2), total_height))
        
        # Paste images into the new image
        combined_image.paste(image1, (0, 0))
        combined_image.paste(image2, (0, height1))
        
        # Save the combined image to a new BytesIO buffer
        combined_buffer = BytesIO()
        combined_image.save(combined_buffer, format='png')
        combined_buffer.seek(0)
        
        return combined_buffer

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback function for when the client receives a CONNACK response from the server.
        
        :param client: The client instance for this callback.
        :param userdata: The private user data as set in Client() or userdata_set().
        :param flags: Response flags sent by the broker.
        :param rc: The connection result.
        """
        if rc == 0:
            print("Connected to MQTT Broker successfully")
        else:
            print(f"Failed to connect, return code {rc}\n")

    def calculate_dli(self,light_data):
        """
        Calculate the Daily Light Integral (DLI) from the light data vector.
        DLI is the total amount of light (in mol/m²/day) received over a 24-hour period.
        """
        total_light = sum(light_data)  # Sum of light intensity over 24 hours
        dli = total_light / len(light_data)  # Average light intensity per hour
        return dli

    def calculate_light_fluctuation(self,light_data):
        """
        Calculate the light fluctuation from the light data vector.
        Light fluctuation measures how much the light levels fluctuate throughout the day.
        """
        max_light = max(light_data)
        min_light = min(light_data)
        fluctuation = max_light - min_light
        return fluctuation

    def calculate_water_absorption(self,soil_moisture_data):
        """
        Calculate the water absorption rate from the soil moisture data.
        Water absorption rate indicates how quickly the plant uses the water administered.
        """
        initial_moisture = soil_moisture_data[0]
        final_moisture = soil_moisture_data[-1]
        water_absorption = initial_moisture - final_moisture
        return water_absorption

    def analyze_plant_conditions(self, DLI, light_fluctuation, soil_moisture_data, water_absorption):
        try:
            tips = []

            # Daily Light Integral (DLI) analysis
            if DLI < 35000:
                tips.append("Increase the amount of light your plant receives.")
            elif DLI > 60000:
                tips.append("Reduce the amount of light your plant receives.")

            # Light Fluctuation Analysis
            if light_fluctuation > 100:
                tips.append("Ensure more consistent lighting conditions for your plant.")

            flag_humidity = False
            # Check for narrow peaks in soil moisture
            peak_width_threshold = 50  # Threshold for narrow peaks
            for i in range(1, len(soil_moisture_data) - 1):
                if soil_moisture_data[i] > soil_moisture_data[i - 1] and soil_moisture_data[i] > soil_moisture_data[i + 1]:
                    peak_width = soil_moisture_data[i] - min(soil_moisture_data[i - 1], soil_moisture_data[i + 1])
                    if peak_width < peak_width_threshold:
                        flag_humidity = True
                        
            if flag_humidity:
                tips.append("Consider moving the plant to a more humid environment.")
            # Water Administration Efficiency
            if water_absorption < 0.5:
                tips.append("Check for root health or consider changing watering methods.")

            # Additional checks and tips
            if light_fluctuation < 20:
                tips.append("Check for potential shading or obstruction affecting light levels.")
            if max(soil_moisture_data) > 95:
                tips.append("Ensure proper drainage to prevent waterlogging and root rot.")
            if min(soil_moisture_data) < 10:
                tips.append("Water your plant more frequently to prevent dehydration.")
            if water_absorption > 90:
                tips.append("Monitor for signs of overwatering such as yellowing leaves or wilting.")
            if min(soil_moisture_data) > 80 and DLI < 20000:
                tips.append("During periods of low light and high soil moisture, reduce watering to avoid root suffocation.")
            if max(soil_moisture_data) < 20 and DLI > 40000:
                tips.append("In periods of high light and low soil moisture, increase watering to prevent wilting.")
            if DLI < 10000 and max(soil_moisture_data) < 40:
                tips.append("During periods of very low light and moderate soil moisture, increase the received light to prevent fungal diseases.")
            if light_fluctuation > 40000 and min(soil_moisture_data) > 10:
                tips.append("In cases of high light fluctuation and consistently high soil moisture, ensure proper ventilation to prevent mold growth.")

            if DLI > 40000 and water_absorption < 20:
                tips.append("In periods of high light and low water absorption, consider fertilizing to support plant growth.")
            if DLI < 10000 and water_absorption > 60:
                tips.append("During periods of low light and high water absorption, reduce fertilization to prevent nutrient buildup.")

            string_of_tips = ''
            for tip in tips:
                string_of_tips = string_of_tips + '\n' + tip

            return string_of_tips
        except Exception as e:
            print(f"Error analyzing plant conditions: {e}")

    def publish_image_via_mqtt(self, combined_buffer,message, mqtt_broker, mqtt_port, mqtt_topic):
        """
        Publishes an image and a message via MQTT.
        
        :param combined_buffer: BytesIO object containing the combined image.
        :param mqtt_broker: MQTT broker address.
        :param mqtt_port: MQTT broker port.
        :param mqtt_topic: MQTT topic to publish to.
        :param message: Message to include with the image.
        """
        client = mqtt.Client()

        # Assign the on_connect callback function
        client.on_connect = self.on_connect

        client.connect(mqtt_broker, mqtt_port, 60)

        # Start the loop
        client.loop_start()

        # Convert image to base64 string
        combined_buffer.seek(0)
        image_base64 = base64.b64encode(combined_buffer.read()).decode('utf-8')

        # Create payload dictionary
        payload = {
            'image': image_base64,
            'message': message
        }

        # Serialize payload to JSON
        payload_json = json.dumps(payload)

        # Publish the JSON string
        client.publish(mqtt_topic, payload_json, qos=2)

        print(f'Message sent to {mqtt_topic}')
        
        # Stop the loop
        time.sleep(2)  # Wait for the message to be sent
        client.loop_stop()
        client.disconnect()

    def create_image(self,sunlight_timestamps, sunlight_lux, lamp_timestamps, lamp_lux, moisture_timestamps, moisture_values):
        lux_plot = self.plot_lux_intensity(self.lux_absorbed_timestamps, self.lux_absorbed_values, self.lux_emitted_timestamps, self.lux_emitted_values)
        moisture_plot = self.plot_soil_moisture(self.moisture_timestamps, self.moisture_values)
        combined_plot = self.concatenate_images_vertically(lux_plot,moisture_plot)

        return combined_plot
        

    def schedule_and_send_messages(self):
        plants = requests.get(self.registry_url+'/plants')
        plants = json.loads(plants.text)
        print(f'GET request sent at {self.registry_url+'/plants'}')
        try:
            while True:
                now = datetime.datetime.now()
                current_time = now.time()
                current_day = now.weekday()  # Monday is 0 and Sunday is 6
                # Check if it's 5 PM
                if current_time.hour == 23 and current_time.minute == 24:
                    for plant in plants:
                        user = plant['userId']
                        chatID = self.get_chatID_from_user(user) 
                        if chatID == None:
                            pass
                        else:
                            time_setting = plant['report_frequency']
                            send_message = False
                            if time_setting == "daily":
                                duration = 24
                                send_message = True
                            elif time_setting == "weekly" and current_day == 6:  # Sunday
                                send_message = True
                                duration = 7*24
                            elif time_setting == "two weeks" and current_day == 6:  # Handle two-week logic
                                week_num = now.isocalendar()[1]
                                duration = 14*24
                                if week_num % 2 == 0:
                                    send_message = True
                            elif time_setting == "monthly":
                                duration = 30*24
                                last_day_of_month = (now.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
                                if now.date() == last_day_of_month:
                                    send_message = True

                            if send_message:
                                self.generate_report(user,plant,duration = duration)
                
                    time.sleep(60)  # Check every minute
        except Exception as e:
            print('Report generator stopped working')
            self.stop_event.set()

    def generate_report(self,user,plant,duration = 24,instant = False):
        lux_sensor =  {"Time": [1717691400, 1717695000, 1717698600, 1717702200, 1717705800, 1717709400, 1717713000, 1717716600, 1717720200, 1717723800], "Value": [753.28, 423.11, 598.56, 729.18, 444.72, 385.96, 301.67, 529.88, 676.92, 773.53]}
        lux_emitted = {"Time": [1717691400, 1717695000, 1717698600, 1717702200, 1717705800, 1717709400, 1717713000, 1717716600, 1717720200, 1717723800], "Value": [459.45, 142.22, 361.34, 233.16, 389.65, 421.54, 283.64, 119.98, 249.29, 391.77]}
        moisture = {"Time": [1717691400, 1717695000, 1717698600, 1717702200, 1717705800, 1717709400, 1717713000, 1717716600, 1717720200, 1717723800], "Value": [15.28, 45.34, 23.12, 54.87, 31.94, 41.07, 57.23, 11.75, 29.66, 37.14]}
        
        #lux_sensor =  json.loads(requests.get(f'{self.url_adaptor}/getData/{user}/{plant}',params={"measurement":'light',"duration":duration}).text)
        self.lux_absorbed_timestamps = lux_sensor['Time']
        lux_sensor = lux_sensor['Value']
        #lux_emitted =  json.loads(requests.get(f'{self.url_adaptor}/getData/{user}/{plant}',params={"measurement":'lamplight',"duration":duration}).text)
        self.lux_emitted_timestamps = lux_emitted['Time']
        self.lux_emitted_values = lux_emitted['Value']
        self.lux_absorbed_values = [a - b for a, b in zip(lux_sensor, self.lux_emitted_values)]
        #moisture =   json.loads(requests.get(f'{self.url_adaptor}/getData/{user}/{plant}',params={"measurement":'moisture',"duration":duration}).text)
        self.moisture_timestamps = moisture['Time']
        self.moisture_values = moisture['Value']
        
        self.lux_absorbed_timestamps = convert_timestamps(self.lux_absorbed_timestamps,duration)
        self.lux_emitted_timestamps = convert_timestamps(self.lux_emitted_timestamps,duration)
        self.lux_moisture_timestamps = convert_timestamps(self.lux_moisture_timestamps,duration)

        combined_image = self.create_image(self.lux_absorbed_timestamps, self.lux_absorbed_values, self.lux_emitted_timestamps, self.lux_emitted_values, self.moisture_timestamps, self.moisture_values)
        dli = self.calculate_dli(self.lux_absorbed_values)
        light_fluctuation = self.calculate_light_fluctuation(self.lux_absorbed_values)
        water_absorption = self.calculate_water_absorption(self.moisture_values)
        tips = self.analyze_plant_conditions(dli, light_fluctuation, self.moisture_values, water_absorption)
        if not instant:
            self.publish_image_via_mqtt(combined_image, tips, self.broker, self.port, f'Rootypy/report_generator/{user}/{plant}')
        else:
            combined_image.seek(0)
            image_base64 = base64.b64encode(combined_image.read()).decode('utf-8')

            # Create payload dictionary
            body = {
                'image': image_base64,
                'message': tips
            }

            # Serialize payload to JSON
            return body
        print(f"Message sent to {user} for plant {plant} with instant: {instant}")

    def translate_uv_lamp_values(self,lux_emitted):
        uv_translated_timestamps = []
        uv_translated_values = []
        lux_emitted_timestamps = lux_emitted['Time']
        lux_emitted_values = lux_emitted['Value']
        for i in range(len(lux_emitted_timestamps)-1):
            translated_timestamp = hourly_timestamps_unix(lux_emitted_timestamps[i])
            translated_value = lux_emitted_values['e'][0]["v"]
            for element in translated_timestamp:
                uv_translated_timestamps.append(element)
            for element in translated_value:
                uv_translated_values.append(translated_value)
        
        return uv_translated_timestamps,uv_translated_values
      

    def get_chatID_from_user(self,user):

        r = requests.get(self.registry_url+'/users',headers = self.headers)
        print(f'GET request sent at \'{self.registry_url}/users')
        output = json.loads(r.text)
        for diz in output:
            if diz['userId'] == user:
                if diz['chatID'] != None:
                    chatID =diz['chatID']
                    return chatID
                else:
                    return None


    def GET(self,*uri,**params):
        print(f'get request received at {uri}')
        if uri[0] == 'getreport':
            print(f'get request  at {uri[0]}')
            r = requests.get(self.registry_url+'/plants',headers=self.headers)
            output = json.loads(r.text)
            found = False
            print('tutto a posto')
            for diz in output:
                if diz['plantCode'] == uri[1]:
                    print('trovato')
                    found = True
                    userid = diz['userId']
                    plantname = diz['plantId']
                    body =self.generate_report(userid,plantname,instant =True)
            if not found:   
                response = {"status": "NOT_OK", "code": 400, "message": "Invalid user"}
            else:
                response = body
            print(found)
            return json.dumps(response) 




class Iamalive(object):

    def __init__(self ,config_path,stop_event):

        json_config =  json.load(open(config_path,'r'))
        # mqtt attributes
        self.clientID = json_config["ID"]
        self.broker = json_config["broker"]
        self.port = json_config["port"]
        self.pub_topic = json_config["alive_topic"]
        self.paho_mqtt = pahoMQTT.Client(self.clientID,True)
        self.paho_mqtt.on_connect = self.myconnect_live
        self.myurl = json_config["myurl"]
        self.message = {"bn": "updateCatalogService","e":[{ "n": f"{self.clientID}", "u": "", "t": time.time(), "v":f"{self.myurl}" }]}
        self.starting_time = time.time()
        self.interval = json_config["update_time"]
        print('i am alive initialized')
        self.start_mqtt()
        self.stop_event = stop_event
        

    def start_mqtt(self):
        print('>starting i am alive')
        self.paho_mqtt.connect(self.broker,self.port)
        self.paho_mqtt.loop_start()

    def myconnect_live(self,paho_mqtt, userdata, flags, rc):
       print(f"report generator: Connected to {self.broker} with result code {rc}")

    def check_and_publish(self):
        while  not self.stop_event.is_set():
            actual_time = time.time()
            if actual_time > self.starting_time + self.interval:
                self.publish()
                print('sent alive message')
                self.starting_time = actual_time
            time.sleep(5)

    def publish(self):
        __message=json.dumps(self.message)
        #print(f'message sent at {time.time()} to {self.pub_topic}')
        self.paho_mqtt.publish(topic=self.pub_topic,payload=__message,qos=2)

class ThreadManager:

    def __init__(self, report_generator, iamalive):
        self.report_generator = report_generator
        self.iamalive = iamalive

    def start_threads(self):
        threading.Thread(target=self.iamalive.check_and_publish).start()
        threading.Thread(target=self.report_generator.schedule_and_send_messages).start()


if __name__ == '__main__':
    # Initialize the objects
    config_path = "config_report_generator.json"
    stop_event = threading.Event()
    report_generator = Report_generator(config_path,stop_event)
    iamalive = Iamalive(config_path,stop_event)  # Provide the actual path to your config file

    # Start the threads
    thread_manager = ThreadManager(report_generator, iamalive)
    thread_manager.start_threads()