import telepot
from telepot.loop import MessageLoop
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
import json
import requests
import time
import datetime
import paho.mqtt.client as pahoMQTT
import threading
import pandas as pd
import numpy as np
import base64
from PIL import Image
from io import BytesIO


class GreenHouseBot:
    def __init__(self, token,config_bot):
        # Local token
        self.watertanklevel = 100
        self.tokenBot = token
        json_config_bot =  json.load(open(config_bot,'r'))
        self.bot = telepot.Bot(self.tokenBot)
        self.interval = 1
        self.headers =  {'content-type': 'application/json; charset=UTF-8'}
        self.uservariables = {}
        self.registry_url = json_config_bot['url_registry']
        self.report_generator_url = json_config_bot['url_report_generator']
        self.adaptor_url = json_config_bot['url_adaptor']
        #self.registry_url = "http://127.0.0.1:8080"
        #self.report_generator_url = 'http://127.0.0.1:8081'
        self.ClientID =  json_config_bot['ID']
        self.broker = json_config_bot['broker']
        self.port = json_config_bot['port']
        self.notifier = self.myconnect
        self.paho_mqtt = pahoMQTT.Client(self.ClientID,True)
        self.countdown = json_config_bot['user_inactivity_timer']                            #Value untill the user status diz is deleted to reduce the weight on the server
        self.user_check_interval = json_config_bot['user_check_interval']
        self.iamalive_topic = json_config_bot["iamalive_topic"]
        self.update_time = json_config_bot["update_time"]
        #Dictionaries with the function to perform after a certain specification which will be written in query_list[1]
        diz_plant = {'inventory':self.choose_plant,'add':self.add_planttoken,'back':self.manage_plant,'create':self.choose_plant_type,'change':self.change_plant_name,'choose':self.remove_old_name_add_new}  #managing plants
        diz_actions = { 'water':self.water_plant, 'ledlight':self.led_management,'reportmenu':self.set_frequency_or_generate}   #actions to take care of the plant
        diz_led = {'setpercentage':self.set_led_percentage,'setmanualmodduration':self.set_led_manual_mode_duration,'switch':self.led_switch,'off':self.instant_switch_off,'change':self.led_change}      # control the led light
        diz_newuser = {'confirmname':self.add_passwd,'newname':self.add_user,'confirmpwd':self.confirm_pwd,'confirmtoken':self.add_plant,'newpsw':self.add_passwd,'newtkn':self.add_planttoken,'newplantname':self.add_plant,'sign_up':self.add_user,'transferaccount':self.transfer_usern,'back':self. new_user_management}
        diz_removeplant = {'choose':self.remove_plant,'plantname':self.confirmed_remove_plant}
        diz_report = {'generate':self.generate_instant_report,'settings':self.set_report_frequency}
        self.diz = { 'actions':diz_actions , 'led':diz_led,'plant':diz_plant,'removeplant':diz_removeplant,'newuser':diz_newuser,'report':diz_report}     #dictionary with dictionaries
        self.paho_mqtt.connect(self.broker, self.port)
        self.paho_mqtt.loop_start()

        MessageLoop(self.bot, {'chat': self.on_chat_message,'callback_query': self.on_callback_query}).run_as_thread() 
        iamalive = Iamalive(self.iamalive_topic,self.update_time,self.ClientID,self.port,self.broker)
        user_checker = Active_user_checker(self.user_check_interval)

        
        self.paho_mqtt.on_message = self.on_message

        self.paho_mqtt.subscribe('RootyPy/microservices/report_generator/#',2)
        self.paho_mqtt.subscribe('RootyPy/microservices/tank_alert/#',2)
        while True:
            time.sleep(5)
            iamalive.check_and_publish()
            self.uservariables = user_checker.updating_user_timer(self.uservariables)

        #messageloop manages the messages by using a certain function
        #specified in the dictionary on the basis of the flavour of the message.
        #Run_as_thread is crucial to allow the notification of the report otherwise run_forever does not allow it


#---------------------------------------------------- Bot callbacks ----------------------------------------------------------------------

    

    def on_chat_message(self, msg):   
        content_type, chat_type, chat_ID = telepot.glance(msg)
        if chat_ID in self.uservariables.keys():
            self.restarting_user_timer(chat_ID,self.countdown)
        else:
            pass
        message = msg['text']
        msg_id = telepot.message_identifier(msg)
        self.bot.deleteMessage(msg_id)
        if message == "/start":
            self.start_user_status(chat_ID)
            if self.is_new_user(chat_ID):
                print('new user detected')
                self.new_user_management(chat_ID)
            else:
                self.choose_plant(chat_ID)
        elif  'listeningfortime' in self.uservariables[chat_ID]['chatstatus']:
            self.confirm_manual_mode_duration(message,chat_ID)
        elif "listeningforobswindow" in self.uservariables[chat_ID]['chatstatus'] :
            self.set_light_time(message,chat_ID,self.uservariables[chat_ID]['chatstatus'].split('&')[1],self.uservariables[chat_ID]['chatstatus'].split('&')[2])
        elif 'listeningforledpercentage' in self.uservariables[chat_ID]['chatstatus'] :
            self.check_light_percentage(message,chat_ID)
        elif self.uservariables[chat_ID]['chatstatus'].split('&')[0] == 'listeningforplantname':
            self.eval_plant_name(chat_ID,message,self.uservariables[chat_ID]['chatstatus'].split('&')[1],self.uservariables[chat_ID]['chatstatus'].split('&')[2])
        elif self.uservariables[chat_ID]['chatstatus'] == 'listeningforuser':
            self.eval_username(chat_ID,message)
        elif self.uservariables[chat_ID]['chatstatus'].split('&')[0]== 'listeningforpwd':
            self.eval_pwd(chat_ID,self.uservariables[chat_ID]['chatstatus'].split('&')[1],message)
        elif 'listeningforwaterpercentage' in  self.uservariables[chat_ID]['chatstatus']:
            self.eval_water_percentage(chat_ID,message)
        elif self.uservariables[chat_ID]['chatstatus'] == 'listeningfortoken':
            self.eval_token(chat_ID,message)
        elif self.uservariables[chat_ID]['chatstatus'] == 'listeningfortransfername':
            self.transfer_password(chat_ID,msg['text'])
        elif 'listeningfortransferpwd' == self.uservariables[chat_ID]['chatstatus'].split('&')[0]:            
            if self.confirm_transfer(chat_ID, self.uservariables[chat_ID]['chatstatus'].split('&')[1],msg['text']):
                msg_id = self.bot.sendMessage(chat_ID, text='Account migrated correctly')['message_id']
                self.uservariables[chat_ID]['chatstatus'] = 'start'
                self.remove_previous_messages(chat_ID)
                self.update_message_to_remove(msg_id,chat_ID)
                self.choose_plant(chat_ID)
            else:
                msg_id = self.bot.sendMessage(chat_ID, text='Wrong credentials')['message_id']
                self.remove_previous_messages(chat_ID)
                self.update_message_to_remove(msg_id,chat_ID)
                self.new_user_management(chat_ID)

    def on_callback_query(self,msg):

         #deals with the answers from the buttons
        query_ID , chat_ID , query_data = telepot.glance(msg,flavor='callback_query')
        if chat_ID in self.uservariables.keys():
            self.restarting_user_timer(chat_ID,self.countdown)     
            self.uservariables[chat_ID]['chatstatus'] = 'start'
            query_list = query_data.split('&')                             # splits the query from the callback_data, function_to_call is extracted from the dictionaries
            if query_list[0] == 'plant':
                print('chosen plant')
                if query_list[1] not in self.diz['plant'].keys():
                    #self.uservariables[chat_ID]['selected_plant'] = query_list[1]   CAMBIARE
                    self.manage_plant(chat_ID,query_list[1])
                else:
                    function_to_call = self.diz['plant'][query_list[1]]
                    if query_list[1] == 'create':
                        function_to_call(chat_ID,query_list[2],query_list[3])
                    elif query_list[1] == 'choose':
                        function_to_call(chat_ID,query_list[2],query_list[3])
                    else:
                        function_to_call(chat_ID)
            elif query_list[0] == 'command':
                print('chosen command')
                function_to_call = self.diz['actions'][query_list[1]]
                function_to_call(chat_ID,query_list[2])
            elif query_list[0] == 'led':
                print('chosen led')
                function_to_call = self.diz['led'][query_list[1]]
                function_to_call(chat_ID,query_list[2])
            elif query_list[0] == 'newuser':
                print('new user')
                function_to_call = self.diz['newuser'][query_list[1]]
                if query_list[1] == 'confirmname' or query_list[1] == 'confirmtoken':
                    function_to_call(chat_ID,query_list[2])
                elif query_list[1] == 'confirmpwd':
                    function_to_call(chat_ID,query_list[2],query_list[3])
                else:
                    function_to_call(chat_ID)
            elif query_list[0] == 'report':
                function_to_call = self.diz['report'][query_list[1]]
                function_to_call(chat_ID,query_list[2])
            elif query_list[0] == 'f_settings':
                self.send_new_report_frequency(chat_ID,query_list[1],query_list[2])
            elif query_list[0] == 'time':
                self.change_time(chat_ID,query_list[1],query_list[2])
            elif query_list[0] == 'inventory':
                self.choose_plant(chat_ID)
            elif query_list[0]== 'changeplantname':
                self.confirmed_change_name(chat_ID,query_list[1])
            elif query_list[0] == 'plant_type':
                self.create_plant(chat_ID,query_list[2],query_list[1],query_list[3])
            elif query_list[0] == 'removeplant':
                if query_list[1] not in self.diz['removeplant'].keys():
                    function_to_call = self.diz['removeplant']['plantname']
                    function_to_call(chat_ID,query_list[1])
                else:
                    function_to_call = self.diz['removeplant'][query_list[1]]
                    function_to_call(chat_ID)
        else:
            msg_id = self.bot.sendMessage(chat_ID, text='Too long since last interaction restart the bot with /start')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)


   #----------------------------------------------------- Managing user connected -------------------------------------------------


    # Initialize or update the status of a user identified by chat_ID.
    # If the chat_ID does not exist in the chatstatus dictionary, it creates a new entry with 'chatstatus' set to 'start'.
    def start_user_status(self, chat_ID):
        if chat_ID not in self.uservariables.keys():
            self.uservariables[chat_ID] = {}  # Initialize a new entry for the user
            self.uservariables[chat_ID]['chatstatus'] = 'start'  # Set the chatstatus for the user to 'start'
            self.uservariables[chat_ID]['timer'] = self.countdown    
            print(f'{chat_ID} connected ')


    # Update the timer for a user identified by chat_ID with a new countdown value.
    def restarting_user_timer(self, chat_ID, countdown):
        self.uservariables[chat_ID]['timer'] = countdown  # Set the timer for the user to the given countdown value
        print(f'restarting {chat_ID} of {countdown}')

    #-------------------------------------------------                             ---------------------------

    def choose_plant(self,chat_ID,keep_prev = False):                       #creates plants from the inventory of the user
        buttons = []
        user_plants = self.get_plant_for_chatID(chat_ID)
        userid = self.get_username_for_chat_ID(chat_ID)
        print(user_plants)
        for element in user_plants:
            element_code = self.get_plant_code_from_plant_name(userid,element)
            buttons.append(InlineKeyboardButton(text=f'{element}', callback_data='plant&'+element_code))
        buttons.append(InlineKeyboardButton(text=f'add plant', callback_data='plant&add'))
        buttons.append(InlineKeyboardButton(text=f'remove plant', callback_data='removeplant&choose'))
        buttons.append(InlineKeyboardButton(text=f'change plant name', callback_data='plant&change'))
        buttons = [buttons]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='Choose one of your plants', reply_markup=keyboard)['message_id']
        if keep_prev == False:
            self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def new_user_management(self,chat_ID):

        buttons = [[InlineKeyboardButton(text=f'new user', callback_data='newuser&sign_up'), InlineKeyboardButton(text=f'transfer account', callback_data='newuser&transferaccount')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='What do you want to do?', reply_markup=keyboard)['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def get_plant_for_chatID(self, chatID):

        plant_list = []     
        userid = self.get_username_for_chat_ID(chatID)
        r = requests.get(self.registry_url+'/plants',headers = self.headers)
        print(f'GET request sent at {self.registry_url}/plants')
        output =json.loads(r.text)
        for diz in output:
            if diz['userId'] == userid:
                plant_list.append(diz['plantId'])

        
        return plant_list

    def write_plants_for_chatID(self,path_archive, chatID,updated_list):

        df_users = pd.read_excel(path_archive)
        row_index = df_users.index[df_users['chatID'] == chatID].tolist()[0]
        print(f'updated plant list is {updated_list}')
        #updated_list.remove('')
        string_list = ''
        for plant in updated_list:
            string_list = string_list + ';' + plant
        print(f'string list is {string_list}')
        df_users.at[row_index, 'plants'] = string_list
        df_users.to_excel(path_archive,index=False)
        

    def manage_plant(self,chat_ID,plantcode):                       #generate a report on the status of the plant and allows you to perform change of the led or water

        userid = self.get_username_for_chat_ID(chat_ID)
        lux_sensor =  json.loads(requests.get(f'{self.adaptor_url}/getData/{userid}/{plantcode}',params={"measurament":'light',"duration":1}).text)
        lamp_emission =  json.loads(requests.get(f'{self.adaptor_url}/getData/{userid}/{plantcode}',params={"measurament":'current_intensity',"duration":1}).text)
        moisture =  json.loads(requests.get(f'{self.adaptor_url}/getData/{userid}/{plantcode}',params={"measurament":'moisture',"duration":1}).text)
        tank_level =  json.loads(requests.get(f'{self.adaptor_url}/getData/{userid}/{plantcode}',params={"measurament":'tankLevel',"duration":1}).text)
        if len(lux_sensor) > 0:
            actual_lux = lux_sensor[-1]['v']
            str_lux = f'light received: {actual_lux} lux'
        else:
            str_lux = 'no sensor data for light sensor'
        if len(lamp_emission) > 0:
            actual_emission = lamp_emission[-1]['v']
            str_lamp = f'current lamp intensity: {actual_emission} lux'
        else:
            str_lamp = f'no data on lamp intensity'
        if len(moisture) > 0:
            actual_moisture = moisture[-1]['v']
            str_moisture = f'moisture received: {actual_moisture} '
        else:
            str_moisture = f'no sensor data on moisture'
        if len(tank_level) > 0:
            actual_tank_level = tank_level[-1]['v']
            str_tank = f'actual tank level {actual_tank_level}'
        else:
            str_tank = 'no sensor data on tank level'
        msg_id = self.bot.sendMessage(chat_ID,text = str_lux+'\n'+str_lamp+'\n'+str_moisture+'\n'+str_tank)['message_id']

        self.update_message_to_remove(msg_id,chat_ID)
        buttons = [[InlineKeyboardButton(text=f'water 💦', callback_data=f'command&water&{plantcode}'), InlineKeyboardButton(text=f'led light 💥', callback_data=f'command&ledlight&{plantcode}'), InlineKeyboardButton(text=f'report', callback_data=f'command&reportmenu&{plantcode}'),InlineKeyboardButton(text=f'back ', callback_data='inventory&start')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='What do you want to do?', reply_markup=keyboard)['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def generate_instant_report(self,chat_ID,plantcode):
        print(f'{chat_ID} is asking for a report')

        #plantcode = self.uservariables[chat_ID]['chatstatus'].split('&')[1]
        r = requests.get(self.report_generator_url+f'/getreport/{plantcode}',headers = self.headers)
        print(f'GET request sent at \'{self.report_generator_url}/getreport/{plantcode}')
        output = json.loads(r.text)
            # Extract the base64-encoded image and decode it
        image_base64 = output['image']
        image_data = base64.b64decode(image_base64)
        
        # Extract the message
        message = output['message']
        print(f"Message: {message}")

        # Load the image into a BytesIO stream
        image = Image.open(BytesIO(image_data))
        bio = BytesIO()
        image.save(bio, format='PNG')
        bio.seek(0)

            # Send the image using the bot
        msg_id = self.bot.sendPhoto(chat_ID, bio, caption=message)
        self.update_message_to_remove(msg_id,chat_ID)
        self.choose_plant(chat_ID)

    def set_report_frequency(self,chat_ID,plantcode):
        print('choosing report frequency')
        userid = self.get_username_for_chat_ID(chat_ID)
        r = requests.get(self.registry_url+f'/plants')
        output = json.loads(r.text)
        for plant in output:
            if plant['userId'] == userid:
                oldsetting = plant['report_frequency']
                plantid = plant['plantId']
        self.remove_previous_messages(chat_ID)

        msg_id = self.bot.sendMessage(chat_ID,text = f'actual report frequency for {plantid} is {oldsetting}')['message_id']

        self.update_message_to_remove(msg_id,chat_ID)
        buttons = [[InlineKeyboardButton(text=f'daily', callback_data=f'f_settings&daily&{plantcode}'), InlineKeyboardButton(text=f'weekly', callback_data=f'f_settings&weekly&{plantcode}'), InlineKeyboardButton(text='biweekly', callback_data=f'f_settings&biweekly&{plantcode}'),InlineKeyboardButton(text=f'monthly', callback_data=f'f_settings&monthly&{plantcode}')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text=f'when do you want to receive a report for {plantcode}', reply_markup=keyboard)['message_id']
        self.update_message_to_remove(msg_id,chat_ID)


    def send_new_report_frequency(self,chat_ID,newfrequency,plantcode):

        print(f'updating {chat_ID} report frequency')
        body = {'plantCode':plantcode,'report_frequency':newfrequency}
        print(body)
        r = requests.put(self.registry_url+'/setreportfrequency',headers = self.headers,json = body)
        flag_keep_mex = self.manage_invalid_request(chat_ID,json.loads(r.text))
        self.choose_plant(chat_ID,flag_keep_mex)

    def add_plant(self,chat_ID,token):                         # allows self.on_chat_message() to stop listen to commands and listen for names
        msg_id = self.bot.sendMessage(chat_ID, text='Send new plant name in the chat')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        self.uservariables[chat_ID]['chatstatus'] = f'listeningforplantname&create&{token}'

    def eval_plant_name(self,chat_ID,mex,mode,plant = ''):              #Checks if the name is already used or other exceptions and makes you confirm

        user_plants = self.get_plant_for_chatID(chat_ID)
        name_set = set(user_plants)
        if mex.strip() in name_set:
            msg_id = self.bot.sendMessage(chat_ID,text =f'{mex} already exists')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
        elif any(char in mex.strip() for char in '&;:",/\'{}[]'):
            msg_id = self.bot.sendMessage(chat_ID,text =f'{mex} is a invalid name contains \'&,,,:,;,/,[,] ')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
        else:
            buttons = [[InlineKeyboardButton(text=f'confirm', callback_data='plant&'+ mode +'&'+mex+'&'+plant), InlineKeyboardButton(text=f'abort', callback_data='plant&inventory')]]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            msg_id = self.bot.sendMessage(chat_ID,text =f'{mex} it\'s a valid name \nwould you like to confirm?',reply_markup=keyboard)['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
            self.uservariables[chat_ID]['chatstatus'] = 'start'
    
    def create_plant(self,chat_ID,plantname,plant_type,plantcode):         #adds the name to the list associated to the user
        body = {'userId' : self.get_username_for_chat_ID(chat_ID),'plantId':plantname,'plantCode':plantcode,'type':plant_type}
        print(body)
        r = requests.post(self.registry_url+'/addp',headers=self.headers,json = body)
        print(f'post request sent at {self.registry_url}/addp')
        output = json.loads(r.text)
        flag_keep_messages = self.manage_invalid_request(chat_ID,output)
        self.choose_plant(chat_ID,keep_prev = flag_keep_messages)

    def manage_invalid_request(self,chat_ID,req_output):
        if req_output['code'] != 200:
            msg_id = self.bot.sendMessage(chat_ID,text = f'{req_output['message']}')['message_id']
            self.update_message_to_remove(msg_id,chat_ID)
            return True
        else:
            return False

    def add_user_first_time(self,chat_ID,userid,pwd):
        body = {'userId' : userid,'password':pwd,'chatID':chat_ID}
        print(body)
        r = requests.post(self.registry_url+'/addu',headers=self.headers,json = body)
        print(f'POST request sent at \'{self.registry_url}/addu')
        output = json.loads(r.text)
        self.remove_previous_messages(chat_ID)
        if self.manage_invalid_request(chat_ID,output):
            msg_id = self.bot.sendMessage(chat_ID,text = 'Something went wrong, try restarting the bot with /start')
            self.update_message_to_remove(msg_id,chat_ID)

    def get_username_for_chat_ID(self,chat_ID):

        r = requests.get(self.registry_url+'/users',headers = self.headers)
        print(f'GET request sent at \'{self.registry_url}/users')
        output = json.loads(r.text)
        for diz in output:

            if int(diz['chatID']) == chat_ID:

                usern =diz['userId']
        
        return usern


    def choose_plant_type(self,chat_ID,plantname,plantcode):
        available_plant_types = self.get_available_plant_types()
        buttons = []
        for pt in available_plant_types:
            button = [InlineKeyboardButton(text=f'{pt}', callback_data=f'plant_type&{pt}&{plantname}&{plantcode}')]
            buttons.append(button)
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID,text =f'choose plant type:',reply_markup=keyboard)['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def get_available_plant_types(self):
        r = requests.get(self.registry_url+'/valid_plant_types', headers = self.headers)
        print(f'GET request sent at {self.registry_url}/valid_plant_types')
        output = json.loads(r.text)
        plant_types =[]
        for diz in output:
            plant_types.append(diz['type'])
        return plant_types


#--------------------------------------------------------- New user ----------------------------------------------------

    def is_new_user(self,chat_ID):
        f = 0
        print('checking if the user is new')
        r = requests.get(self.registry_url+'/users',headers = self.headers)
        print(json.loads(r.text))
        print(f'GET request sent at {self.registry_url}/users')

        output = json.loads(r.text)
        
        for diz in output:
            if diz['chatID'] == None:
                pass
            elif int(diz['chatID']) == chat_ID:
                print(diz)
                f=1
        if f == 1:
            return False
        else:
            return True    

    def add_user(self,chat_ID):

        #self.uservariables[chat_ID]['first'] = True
        self.uservariables[chat_ID]['chatstatus'] = 'listeningforuser'
        buttons = [[InlineKeyboardButton(text=f'🔙', callback_data='newuser&back')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='Choose a username',reply_markup=keyboard)['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        print(f'waiting for name from {chat_ID}')

    def eval_username(self,chat_ID,message):
 
        if any(char in message.strip() for char in '&;:",/\'{}[]'):
            msg_id = self.bot.sendMessage(chat_ID,text =f'{message} is a invalid name contains \'&\' or \';\' ')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
        else:
            buttons = [[InlineKeyboardButton(text=f'confirm', callback_data=f'newuser&confirmname&{message.strip()}'), InlineKeyboardButton(text=f'abort', callback_data='newuser&newname')]]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            msg_id = self.bot.sendMessage(chat_ID,text =f'{message} it\'s a valid name \nwould you like to confirm?',reply_markup=keyboard)['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
            self.uservariables[chat_ID]['chatstatus'] = 'start'  
 


    def add_passwd(self,chat_ID,username):

        buttons = [[InlineKeyboardButton(text=f'🔙', callback_data='newuser&back')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='Choose a password',reply_markup=keyboard)['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        self.uservariables[chat_ID]['chatstatus'] = f'listeningforpwd&{username}'
        print(f'waiting for password from {chat_ID}')

    def eval_pwd(self,chat_ID,userid,message): 
        if any(char in message.strip() for char in '&;:",/\'{}[]'):
            msg_id = self.bot.sendMessage(chat_ID,text =f'{message} is a invalid name contains \'&\' or \';\' ')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
        else:
            buttons = [[InlineKeyboardButton(text=f'confirm', callback_data=f'newuser&confirmpwd&{userid}&{message}'), InlineKeyboardButton(text=f'abort', callback_data='newuser&newpsw')]]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            msg_id = self.bot.sendMessage(chat_ID,text =f'{message} it\'s a valid password \nwould you like to confirm?',reply_markup=keyboard)['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
            self.uservariables[chat_ID]['chatstatus'] = 'start'  


    def confirm_pwd(self,chat_ID,userid,pwd):
        self.add_user_first_time(chat_ID,userid,pwd)
        self.add_planttoken(chat_ID)

    def add_planttoken(self,chat_ID):
        msg_id = self.bot.sendMessage(chat_ID, text='Insert the token of your pot')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        self.uservariables[chat_ID]['chatstatus'] = 'listeningfortoken'
        print(f'waiting for  pot token from {chat_ID}')

    def eval_token(self,chat_ID,message):
        
        message= str(message)
        if not (message[0].isalpha() and message[1].isalpha()) and not all(char.isdigit() for char in message[2:]):

            msg_id = self.bot.sendMessage(chat_ID,text =f'{message} is a invalid token')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
        else:
            buttons = [[InlineKeyboardButton(text=f'confirm', callback_data=f'newuser&confirmtoken&{message.strip()}'), InlineKeyboardButton(text=f'abort', callback_data='newuser&newtkn')]]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            msg_id = self.bot.sendMessage(chat_ID,text =f'{message} it\'s a valid token \nwould you like to confirm?',reply_markup=keyboard)['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
            self.uservariables[chat_ID]['chatstatus'] = 'start'       

    def transfer_usern(self,chat_ID):
        msg_id = self.bot.sendMessage(chat_ID, text='insert you username')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        self.uservariables[chat_ID]['chatstatus'] = 'listeningfortransfername'
        print(f'waiting for username to transfer account for {chat_ID}')

    def transfer_password(self,chat_ID,userid):
        msg_id = self.bot.sendMessage(chat_ID, text='insert your password')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        self.uservariables[chat_ID]['chatstatus'] = f'listeningfortransferpwd&{userid}'
        print(f'waiting for username to transfer account for {chat_ID}')

    def confirm_transfer(self,chat_ID,username,pwd):
        r = requests.get(self.registry_url+'/users',headers = self.headers)
        print(f'GET request sent at {self.registry_url}/users')
        f = False
        output = json.loads(r.text)
        for user in output:
            if user['userId'] == username and user['password'] == pwd:
                f = True
                body = {"userId":username, 'chatID':chat_ID}
                r = requests.put(self.registry_url+'/transferuser',headers = self.headers,json = body)
                if self.manage_invalid_request(chat_ID,json.loads(r.text)):
                    msg_id = self.bot.sendMessage(chat_ID,'something went wrong try restarting the bot with /start')
                    self.update_message_to_remove(msg_id,chat_ID)
        return f


#--------------------------------------------------------- Plant watering --------------------------------------------------------------

    def water_plant(self, chat_ID,plantcode):                  # Activates the watering of the plant and prints tank level
        msg_id = self.bot.sendMessage(chat_ID, text="You chose to water the plant\nsend a percentange of the tank between 0 and 10")['message_id']
        self.uservariables[chat_ID]['chatstatus'] = f'listeningforwaterpercentage&{plantcode}'
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def eval_water_percentage(self,chat_ID,message):
        message = message.strip()
        try:
            perc_value = float(message)
            if perc_value <= 10 and perc_value > 0:
                plantcode = self.uservariables[chat_ID]['chatstatus'].split('&')[1]
                self.uservariables[chat_ID]['chatstatus'] = 'start'
                msg_id = self.bot.sendMessage(chat_ID,f'{perc_value} is a valid value')['message_id']
                self.remove_previous_messages(chat_ID)
                self.update_message_to_remove(msg_id,chat_ID)
                userid = self.get_username_for_chat_ID(chat_ID)
                payload =  {"bn": f'{self.ClientID}',"e":[{ "n": f"{self.ClientID}", "u": "", "t": time.time(), "v":f"{perc_value}" }]}
                self.paho_mqtt.publish(f'RootyPy/{userid}/{plantcode}/waterPump/manual',json.dumps(payload))
                self.manage_plant(chat_ID,plantcode)
            else:
                msg_id = self.bot.sendMessage(chat_ID,f'{perc_value} is a invalid value, senda a value between 0 and 10')['message_id']
                self.update_message_to_remove(msg_id,chat_ID)
        except:
            msg_id = self.bot.sendMessage(chat_ID,f'{message} is an invalid value,try again')['message_id']
            self.update_message_to_remove(msg_id,chat_ID)
        

#--------------------------------------- Plant Removal ------------------------------------------------------------------------------------

    def remove_plant(self,chat_ID):
        msg_id = self.bot.sendMessage(chat_ID,text = f"Be careful!\n You're trying to remove a plant")['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        buttons = []
        plant_list = self.get_plant_for_chatID(chat_ID)
        for element in plant_list:
            buttons.append(InlineKeyboardButton(text=f'{element}', callback_data='removeplant&'+element))
        buttons.append(InlineKeyboardButton(text=f'🔙', callback_data='plant&inventory'))
        buttons = [buttons]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='Choose the plant you\'d like to remove', reply_markup=keyboard)['message_id']
        self.update_message_to_remove(msg_id,chat_ID)


    def confirmed_remove_plant(self,chat_ID,plantname):#*
        print(f'removing from {chat_ID} plant formerly named {plantname}')
        userid = self.get_username_for_chat_ID(chat_ID)
        plantcode = self.get_plant_code_from_plant_name(userid,plantname)
        r = requests.delete(self.registry_url+f'/rmp/{userid}/{plantcode}',headers = self.headers)
        print(f'delete request sent at {self.registry_url}/rmp')
        output = json.dumps(r.text)
        msg_id = self.bot.sendMessage(chat_ID,text = f"You correctly removed {plantname}")['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        self.choose_plant(chat_ID)

#----------------------------------------------------------- Change plant name ---------------------------------------------------------------
    
    def change_plant_name(self,chat_ID):   
        buttons = []
        plant_list = self.get_plant_for_chatID(chat_ID)
        for element in plant_list:
            buttons.append(InlineKeyboardButton(text=f'{element}', callback_data='changeplantname&'+element))
        buttons.append(InlineKeyboardButton(text=f'🔙', callback_data='plant&inventory'))
        buttons = [buttons]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text="Chose the plant whose name you'd like to change", reply_markup=keyboard)['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def confirmed_change_name(self,chat_ID,plantname):                      
        msg_id = self.bot.sendMessage(chat_ID, text='Send plant name in the chat')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        self.uservariables[chat_ID]['chatstatus'] =f'listeningforplantname&choose&{plantname}'

    def remove_old_name_add_new(self,chat_ID,newname,oldname):
        print(f'changing plant name from {oldname} to  {newname}')
        userid = self.get_username_for_chat_ID(chat_ID)
        plant_code = self.get_plant_code_from_plant_name(userid,oldname)
        body = {"plantCode":plant_code,'new_name':newname}
        r = requests.put(self.registry_url+'/modifyPlant',headers=self.headers,json = body)
        print(f'PUT requesrt sent at {self.registry_url+'/modifyPlant'} with {body}')
        output = json.loads(r.text)
        flag_remove_mex = self.manage_invalid_request(chat_ID,output)
        self.choose_plant(chat_ID)
        msg_id = self.bot.sendMessage(chat_ID, text=f'You changed name to {oldname} into {newname}')['message_id']
        self.remove_previous_messages(chat_ID,flag_remove_mex)
        self.update_message_to_remove(msg_id,chat_ID)
        time.sleep(2)
        self.choose_plant(chat_ID)

    def get_plant_code_from_plant_name(self,userid,plantname):
        r = requests.get(self.registry_url+'/plants',headers=self.headers)
        output = json.loads(r.text)
        for diz in output:
            if diz['userId'] == userid and diz['plantId'] == plantname:
                return diz['plantCode']

#----------------------------------------------- removes messages from bot --------------------------------------

    def update_message_to_remove(self, msg_id, chat_ID):
        if msg_id is not None:
            if 'messages_to_remove' not in self.uservariables[chat_ID].keys():
                self.uservariables[chat_ID]['messages_to_remove'] = [msg_id]
            else:
                self.uservariables[chat_ID]['messages_to_remove'].append(msg_id)


    def remove_previous_messages(self, chat_ID):
        if 'messages_to_remove' in self.uservariables[chat_ID].keys():
            for msg_id in self.uservariables[chat_ID]['messages_to_remove']:
                if msg_id is not None:
                    try:
                        self.bot.deleteMessage((chat_ID, msg_id))
                    except telepot.exception.TelegramError as e:
                        print(f"Failed to delete message {msg_id}: {e}")
                else:
                    print(f"Invalid msg_id: {msg_id} for chat_ID: {chat_ID}, skipping deletion")
            
            self.uservariables[chat_ID]['messages_to_remove'] = []


    def set_frequency_or_generate(self,chat_ID,plantcode):

        buttons = [[ InlineKeyboardButton(text=f'generate report', callback_data=f'report&generate&{plantcode}'), InlineKeyboardButton(text=f'settings', callback_data=f'report&settings&{plantcode}'), InlineKeyboardButton(text=f'🔙', callback_data='plant&back')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='What do you want to do?', reply_markup=keyboard)['message_id']
        self.update_message_to_remove(msg_id,chat_ID)        

#----------------------------------------------------- Lamp management ---------------------------------------------------------------- 

    def led_management(self, chat_ID,plantcode):              # Gives you the possiblity to change light schedule of activation and to switch on and off
        msg_id = self.bot.sendMessage(chat_ID, text="You chose to manage the LED")['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        buttons = [[ InlineKeyboardButton(text=f'switch off 🔌', callback_data=f'led&off&{plantcode}'), InlineKeyboardButton(text=f'led manual 💡', callback_data=f'led&setpercentage&{plantcode}'),InlineKeyboardButton(text=f'daylight monitoring', callback_data=f'led&change&{plantcode}'),InlineKeyboardButton(text=f'🔙', callback_data='plant&back')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='What do you want to do?', reply_markup=keyboard)['message_id']
        self.update_message_to_remove(msg_id,chat_ID)

    def set_led_percentage(self,chat_ID,plantcode):
        self.uservariables[chat_ID]['chatstatus'] = f'listeningforledpercentage&{plantcode}'
        print(f'started listening for light percentage from {chat_ID}')
        msg_id = self.bot.sendMessage(chat_ID, text='Insert desired percentage of light as an integer number ')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def check_light_percentage(self, msg, chat_ID):
        clean_mex = msg.strip()
        
        try:
            # Attempt to convert the cleaned message to a float
            percentage = float(clean_mex)
            
            # Check if the percentage is within the valid range
            if 0 <= percentage <= 100:
                plantcode = self.uservariables[chat_ID]['chatstatus'].split('&')[1]
                self.uservariables[chat_ID]['chatstatus'] = 'start'
                self.set_led_manual_mode_duration(chat_ID,plantcode,percentage)
            else:
                msg_id = self.bot.sendMessage(chat_ID, text='Percentage must be between 0 and 100')['message_id']
                self.remove_previous_messages(chat_ID)
                self.update_message_to_remove(msg_id,chat_ID)
        except ValueError:
            # If conversion to float fails, send an error message
            msg_id = self.bot.sendMessage(chat_ID, text='Invalid percentage format')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)



    def set_led_manual_mode_duration(self,chat_ID,plantcode,percentage):
        self.uservariables[chat_ID]['chatstatus'] = f'listeningfortime&{plantcode}&{percentage}'
        print(f'started listening for time for {plantcode}')
        msg_id = self.bot.sendMessage(chat_ID, text='Insert when the light should switch off in format hh:mm')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def get_next_occurrence_unix_timestamp(self,time_str):
        # Parse the input time string into hours and minutes
        hours, minutes = map(int, time_str.split(":"))
        
        # Get the current time
        current_time = time.localtime()
        
        # Create a struct_time object for the target time today
        target_time_today = time.struct_time((
            current_time.tm_year,  # Year
            current_time.tm_mon,   # Month
            current_time.tm_mday,  # Day
            hours,                 # Hour
            minutes,               # Minute
            0,                     # Second
            current_time.tm_wday,  # Weekday
            current_time.tm_yday,  # Yearday
            current_time.tm_isdst  # Daylight saving time flag
        ))
        
        # Convert the struct_time to a Unix timestamp
        target_timestamp_today = time.mktime(target_time_today)
        
        # Get the current Unix timestamp
        current_timestamp = time.time()
        
        # If the target time has already passed today, compute the Unix timestamp for the same time tomorrow
        if target_timestamp_today <= current_timestamp:
            # Create a struct_time object for the target time tomorrow
            target_time_tomorrow = time.struct_time((
                current_time.tm_year,  # Year
                current_time.tm_mon,   # Month
                current_time.tm_mday + 1,  # Next day
                hours,                 # Hour
                minutes,               # Minute
                0,                     # Second
                (current_time.tm_wday + 1) % 7,  # Weekday (next day)
                current_time.tm_yday + 1,  # Yearday (next day)
                current_time.tm_isdst  # Daylight saving time flag
            ))
            target_timestamp_tomorrow = time.mktime(target_time_tomorrow)
            return target_timestamp_tomorrow
        
        return target_timestamp_today

    def confirm_manual_mode_duration(self,mex,chat_ID):
        mex=mex.strip()
        if len(mex) != 5 :
            self.bot.send_message(chat_ID,text = 'invalid message')
        else:
            if mex[2] == ':' and mex[0].isdigit() and mex[1].isdigit() and mex[3].isdigit() and mex[4].isdigit():
                print('extracting time')
                print(mex)
                hour = int(mex.split(':')[0])
                minute = int(mex.split(':')[1])
            else:
                msg_id = self.bot.sendMessage(chat_ID, text='Invalid message')['message_id']
                self.remove_previous_messages(chat_ID)
                self.update_message_to_remove(msg_id,chat_ID)
            if hour >= 0 and hour <= 24 and minute >= 0 and minute <= 59:
                m_mode_duration = self.get_next_occurrence_unix_timestamp(mex)
                print('stopped listening for time')
                plantcode = self.uservariables[chat_ID]['chatstatus'].split('&')[1]
                percentage = self.uservariables[chat_ID]['chatstatus'].split('&')[2]
                self.uservariables[chat_ID]['chatstatus'] = 'start'
                #self.uservariables[chat_ID]['manual_mode_duration'] = m_mode_duration
                msg_id = self.bot.sendMessage(chat_ID, text=f"light will be switched off at {mex}")['message_id']
                self.remove_previous_messages(chat_ID)
                self.update_message_to_remove(msg_id,chat_ID)
                self.led_switch(chat_ID,plantcode,percentage,m_mode_duration)
            else:
                msg_id = self.bot.sendMessage(chat_ID, text='Invalid message')['message_id']     
                self.remove_previous_messages(chat_ID)  
                self.update_message_to_remove(msg_id,chat_ID)


    def led_change(self,chat_ID,plantcode):                     # Makes you choose to change the start time or the stop time
        userid = self.get_username_for_chat_ID(chat_ID)
        time_start,time_end = self.get_time_start_and_time_end_from_chatId(userid)
        msg_id = self.bot.sendMessage(chat_ID, text=f"start time {time_start}'\nend time {time_end}")['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)
        buttons = [[InlineKeyboardButton(text=f'change start ⏰', callback_data=f'time&start&{plantcode}'), InlineKeyboardButton(text=f'change stop ⏰', callback_data=f'time&end&{plantcode}'),InlineKeyboardButton(text=f'🔙', callback_data='plant&back')]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        msg_id = self.bot.sendMessage(chat_ID, text='What do you want to change?', reply_markup=keyboard)['message_id']
        self.update_message_to_remove(msg_id,chat_ID)

    def get_time_start_and_time_end_from_chatId(self,userid):
        r = requests.get(self.registry_url+'/plants',headers = self.headers)
        print(f'GET request sent at \'{self.registry_url}/plants')
        output = json.loads(r.text)
        for plant in output:
            if plant['userId'] == userid:
                time_start = plant['auto_init']
                time_end = plant['auto_end']
        return time_start, time_end


    def change_time(self,chat_ID,timest,plantcode):         
        self.uservariables[chat_ID]['chatstatus'] = f'listeningforobswindow&{timest}&{plantcode}'
        print('started listening for time')
        msg_id = self.bot.sendMessage(chat_ID, text='Insert time in format hh:mm')['message_id']
        self.remove_previous_messages(chat_ID)
        self.update_message_to_remove(msg_id,chat_ID)

    def set_light_time(self,mex,chat_ID,checkp,plantcode):     # Extracts time and assigns it to the plant
        mex=mex.strip()
        if mex[2] == ':' and mex[0].isdigit() and mex[1].isdigit() and mex[3].isdigit() and mex[4].isdigit():
            print('extracting time')
            print(mex)
            hour = int(mex.split(':')[0])
            minute = int(mex.split(':')[1])
        else:
            msg_id = self.bot.sendMessage(chat_ID, text='Invalid message')['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
        userid = self.get_username_for_chat_ID(chat_ID)
        old_start,old_end = self.get_time_start_and_time_end_from_chatId(userid)
        if hour >= 0 and hour < 24 and minute >= 0 and minute <= 59:
            if checkp == 'start':
                time_start=mex
                time_end = old_end
            if checkp == 'end':
                time_end=mex
                time_start = old_start
        print('stopped listening for time')

        print('Changed observation window for automatic mode')
        state = "auto"
        init = time_start
        end =  time_end
        body = {"plantCode":plantcode,'state':state,'init':init,'end':end}
        out = json.loads(requests.put(self.registry_url+'/updateInterval',headers=self.headers,json = body).text)
        self.uservariables[chat_ID]['chatstatus'] = 'start'
        if self.manage_invalid_request(chat_ID,out):
            pass
        else:
            msg_id = self.bot.sendMessage(chat_ID, text=f"start time {time_start}\nend time {time_end}")['message_id']
            self.remove_previous_messages(chat_ID)
            self.update_message_to_remove(msg_id,chat_ID)
        self.manage_plant(chat_ID,plantcode)


    def led_switch(self,chat_ID,plantcode,percentage,m_mode_duration):                     # Switch remotely the led on and off

        userid = self.get_username_for_chat_ID(chat_ID)
        plantcode
        print('Light switched off manually')
        state = "manual"
        init = time.time()
        body = {"plantCode":plantcode,'state':state,'init':init,'end':m_mode_duration}
        r = requests.put(self.registry_url+'/updateInterval',headers=self.headers,json = body)
        output = json.loads(r.text)
        self.manage_invalid_request(chat_ID,output)
        mex_mqtt =  { 'bn': "manual_light_shift",'e': [{ "n": "percentage_of_light", "u": "percentage", "t": time.time(), "v":float(percentage) },{"n": "final_time", "u": "s", "t": time.time(), "v": m_mode_duration } ]}
        self.publish(f'RootyPy/{userid}/{plantcode}/lux_to_give/manual',json.dumps(mex_mqtt))
        print('SENT MESSAGE')
        self.manage_plant(chat_ID,plantcode)


    def instant_switch_off(self,chat_ID,plantcode):                     # Switch remotely the led on and off
        userid = self.get_username_for_chat_ID(chat_ID)
        print('Light switched off manually')
        state = "manual"
        init = time.time()
        end = time.time()+10
        body = {"plantCode":plantcode,'state':state,'init':init,'end':end}
        r = requests.put(self.registry_url+'/updateInterval',headers=self.headers,json = body)
        output = json.loads(r.text)
        self.manage_invalid_request(chat_ID,output)
        mex_mqtt =  { 'bn': "manual_light_shift",'e': [{ "n": "percentage_of_light", "u": "percentage", "t": time.time(), "v":0.0 },{"n": "final_time", "u": "s", "t": time.time(), "v":end} ]}
        self.publish(f'RootyPy/{userid}/{plantcode}/lux_to_give/manual',json.dumps(mex_mqtt))
        print(f'SENT MESSAGE to RootyPy/{userid}/{plantcode}/lux_to_give/manual')
        self.manage_plant(chat_ID,plantcode)

    
#----------------------------------------------------MQTT--------------------------------------------------------------------------------#

    def myconnect(self,paho_mqtt, userdata, flags, rc):
       print(f"ligth shift: Connected to {self.broker} with result code {rc} ")

    def publish(self,topic, diff):
        self.paho_mqtt.publish(topic,diff,2)


#------------------------------------------------ comunication to catalog -------------------------------------------
#------------------------------------------------- mqtt receiver ---------------------------------------

    def on_message(self, client, userdata, msg):
        payload = msg.payload
        print(f"Received message on topic {msg.topic}")
        if 'RootyPy/microservices/report_generator' in msg.topic:
            user = msg.topic.split('/')[2]
            plant = msg.topic.split('/')[3]
            # If the payload is an image, display it
            try:
                # Decode the JSON payload
                payload_dict = json.loads(payload.decode('utf-8'))
                if user == 'user1':
                    chat_ID = 6094158662
                else:
                    chat_ID = 6094158662
                
                # Extract the base64-encoded image and decode it
                image_base64 = payload_dict['image']
                image_data = base64.b64decode(image_base64)
                
                # Extract the message
                message = payload_dict['message']
                print(f"Message: {message}")

                # Load the image into a BytesIO stream
                image = Image.open(BytesIO(image_data))
                bio = BytesIO()
                image.save(bio, format='PNG')
                bio.seek(0)

                # Send the image using the bot
                self.bot.sendPhoto(chat_ID, bio, caption=message)

            except Exception as e:
                print(f"Error processing message: {e}")
        elif 'RootyPy/microservices/tank_alert' in msg.topic:
            user = msg.topic.split('/')[3]
            plant = msg.topic.split('/')[4]
            try:
                chat_ID = self.get_chatID_for_username(user)
                self.bot.sendMessage(chat_ID,text = f'watchout tank almost empty for {plant}')   
            except Exception as e:
                print(f"Error processing message: {e}")

    def get_chatID_for_username(self,userid):

        r = requests.get(self.registry_url+'/users',headers = self.headers)
        print(f'GET request sent at \'{self.registry_url}/users')
        output = json.loads(r.text)
        for diz in output:

            if int(diz['userId']) == userid:

                usern =diz['userId']

        return usern



class Iamalive():

    def __init__(self ,topic,update_time,id,port,broker):


        # mqtt attributes
        self.clientID = id
        self.port = port
        self.broker = broker
        self.pub_topic =topic
        self.paho_mqtt = pahoMQTT.Client(self.clientID,True)
        self.paho_mqtt.on_connect = self.myconnect_live
        self.message = {"bn": "updateCatalogService","e":[{ "n": f"{id}", "u": "", "t": time.time(), "v":f"{id}" }]}
        self.starting_time = time.time()
        self.interval = update_time
        print('i am alive initialized')
        self.start_mqtt()


    def start_mqtt(self):
        print('>starting i am alive')
        self.paho_mqtt.connect(self.broker,self.port)
        self.paho_mqtt.loop_start()

    def myconnect_live(self,paho_mqtt, userdata, flags, rc):
       print(f"telegrambot: Connected to {self.broker} with result code {rc}")

    def check_and_publish(self):

        actual_time = time.time()
        if actual_time > self.starting_time + self.interval:
            self.message["e"][0]["t"]= time.time()

            self.publish()
            #print(f'{self.interval} seconds passed sending i am alive message at {self.pub_topic}')
            self.starting_time = actual_time

    def publish(self):
        __message=json.dumps(self.message)
        # print(f'publishing {__message}, on topic {self.pub_topic}, {type(__message)}')
        self.paho_mqtt.publish(topic=self.pub_topic,payload=__message,qos=2)


#-------------------------------------------------- Disconnect silent users -------------------------
class Active_user_checker():

    def __init__(self,interval):

        #self.diz = diz
        self.interval = interval

    # Decrement the timer for each user in the chatstatus dictionary by the given interval.
    # Remove the user's status if the timer reaches or passes 0.
    def updating_user_timer(self,diz):

        keys_to_remove = []
        for key in diz.keys():
            diz[key]['timer'] = diz[key]['timer'] - self.interval  # Decrement the timer by the interval
            if diz[key]['timer'] <= 0:
                # If the timer reaches or passes 0, remove the user's status
                keys_to_remove.append(key)
        for key in keys_to_remove:
            self.delete_user_status(diz,key)
        return diz

    # Remove the status of a user identified by chat_ID from the chatstatus dictionary.
    def delete_user_status(self,diz, chat_ID):
        del diz[chat_ID]  # Remove the entry for the user from the chatstatus dictionary
        print(f'{chat_ID} disconnected ')


if __name__ == "__main__":

    token = '6395900412:AAHo8suUwcEqRP1-onAvlhkoK-OaB1X7Tew'

    config_bot = "telegram_bot_config.json"

    sb=GreenHouseBot(token,config_bot)
