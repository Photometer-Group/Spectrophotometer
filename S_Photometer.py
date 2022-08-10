"""
-----------------------------------------------

    Spectrophotometer firmware 

    California Space Grant Consortium 2022

    Author:
    Date:07/14/2022
    Revisided:08/02/2022
    
    Revisions:
    1) version 1.0
    2) 7/18/2022 Corrected error in reading buttons
    3) 7/20/2022 added average of photodiode voltages
    4) 7/30/2022 used drive keyword to adjust LED brightness (Swtiched to Kingbright, common cathode LED)
    5) 07/31/2022 adapted for use with common cathode LED
    6) 08/04/2022 switch off all leds after measurements complete, include settling time nin turn_off_leds()
-----------------------------------------------
"""
VERSION='1.6'

"""
-----------------------------------------------

libraries

-----------------------------------------------
"""
from time import sleep_ms
from machine import Pin
from machine import I2C, Pin
from I2C_LCD import I2cLcd
from machine import ADC,Pin
import os
import json
from machine import RTC
import machine

"""
-----------------------------------------------

Global Constants 

-----------------------------------------------
"""

SWITCH_DEBOUNCE_PERIOD_MS=250 #switch debounce period in milli seconds
LCD_DEFAULT_I2C_ADDR = 0x27
MACHINE_DATA_FILENAME='machine_data.txt'    
CONFIG_PARAM_BLANK='blank_value'
LED_WARMUP_PERIOD_MS=500 #time to allow LED to stabilize in milliseconds
ADC_SETTLING_TIME_MS=50 #time to allow ADC input to settle due to filter
ADC_SAMPLE_COUNT=20 # the number of samples the ADC is read for calculating average and stdev


"""
-----------------------------------------------

Configure Hardware 

-----------------------------------------------
Pin summary:
0 : red led
1 : *serial TX
2 : blue led
3 : *serial RX
4 : button read sample
5 : button read blank
6 : *flash 
7 : *flash
8 : *flash
9 : 
10: 
11: *flash
12:
13: i2c sda
14: i2c scl
15: green led
16: *flash
17: *flash
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
---input only---
34: ADC input incident photodiode
35: ADC input transmission photodiode
36: 
37:
38:
39:
----------------
"""

#LEDS

#Pin.DRIVE_0: 5mA / 130 ohm
#Pin.DRIVE_1: 10mA / 60 ohm
#Pin.DRIVE_2: 20mA / 30 ohm (default strength if not configured)
#Pin.DRIVE_3: 40mA / 15 ohm

led_red=Pin(0,Pin.OUT,drive=Pin.DRIVE_3) 
led_green=Pin(15,Pin.OUT,drive=Pin.DRIVE_0)
led_blue=Pin(2,Pin.OUT,drive=Pin.DRIVE_3 )

#Buttons
button_read_sample = Pin(4, Pin.IN,Pin.PULL_UP) #voltage at pin low when button is pressed
button_read_blank=Pin(5, Pin.IN,Pin.PULL_UP)

#LCD
DEFAULT_I2C_ADDR = 0x27
i2c = machine.I2C(1,scl=machine.Pin(14), sda=machine.Pin(13), freq=400000)
lcd = I2cLcd(i2c, DEFAULT_I2C_ADDR, 4, 20)
    
#ADC channels
adc_trans=ADC(Pin(35))
adc_trans.atten(ADC.ATTN_11DB)
adc_trans.width(ADC.WIDTH_12BIT)
    
adc_incid=ADC(Pin(34))
adc_incid.atten(ADC.ATTN_11DB)  
adc_incid.width(ADC.WIDTH_12BIT)

#RTC
rtc=RTC()

"""
-----------------------------------------------

Global Variables 

-----------------------------------------------
"""

machine_data={'incid_dark_value':0,
              'trans_dark_value':0,
              'incid_empty_blue_value':0,
              'incid_empty_red_value':0,
              'incid_empty_green_value':0,
              'trans_empty_blue_value':0,
              'trans_empty_red_value':0,
              'trans_empty_green_value':0,
              'blank_value_red':0,
              'blank_value_green':0,
              'blank_value_blue':0,
              'last_blank_reading':'',
              'set_datetime':'N',
              'set_rtc_datetime_to':'2022,7,17,6,12,46,0,0', #date in format yyyy,mm,dd,weekday (0 is Mon),hh,mm,ss,0
              'last_error':'none'
              }              
"""
-----------------------------------------------

function definitions 

-----------------------------------------------
"""

def is_read_sample_button_pressed():
    """ Determines if the read sample button is pushed
        (debounces switch, input reads low when pushed)
    
    Returns
    -------
    True: if button held down for debouncing period
    False: in all other cases
    
    Unit Test Result
    ----------------
        
    """

    if button_read_sample.value():
        
        sleep_ms(SWITCH_DEBOUNCE_PERIOD_MS)
        
        if button_read_sample.value():
            return True
        else:
            return False
        
    else:
        return False
    


def is_read_blank_ok_button_pressed():
    
    """ Determines if the read blank button is pushed
        (debounces switch, input reads low when pushed)
    
    Returns
    -------
    True: if button held down for debouncing period
    False: in all other cases 

    Unit Test Result
    ----------------

    """

    if button_read_blank.value():
        
        sleep_ms(SWITCH_DEBOUNCE_PERIOD_MS)
        
        if button_read_blank.value():
            return True
        else:
            return False
        
    else:
        return False

def turn_off_leds():
    led_red.value(0)
    led_green.value(0)
    led_blue.value(0)
    sleep_ms(ADC_SETTLING_TIME_MS)

def turn_on_red_led():
    turn_off_leds()
    led_red.value(1)
    sleep_ms(LED_WARMUP_PERIOD_MS)

def turn_on_blue_led():
    turn_off_leds()
    led_blue.value(1)
    sleep_ms(LED_WARMUP_PERIOD_MS)

def turn_on_green_led():
    turn_off_leds()
    led_green.value(1)
    sleep_ms(LED_WARMUP_PERIOD_MS)
    

def lcd_display(message_list):
    """ LCD Display
    Params
    -------
    message_list: one or two element list, first element is shown on top line
                second element (if any) is shown on bottom line
    
    Returns
    -------
    no return value

    Unit Test Result
    ----------------

    """
    
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr(message_list[0])
    
    if len(message_list)>1:
        lcd.move_to(0, 1)
        lcd.putstr(message_list[1]) 
    

def calculate_sample_statistics(sample_list):
    """ calculates the mean and standard deviation
        of a list of voltages from ADC readings
    
    Params
    -------
    sample_list: a list containting the numbers to be analyzed
    
    
    Returns
    -------
    mean
    
    
    Unit Test Result
    ----------------
    
    """
    total=sum(sample_list)
    n=len(sample_list)
   
    # the ADC is assumed to be no more precise than 1mV, therefore 3 decimal plaaces
    # is enough precision
    
    mean=round(total/n,3)
    print(mean)    
    return mean
    


def read_transmission_light_sensor():
    """ Read the photodiode sensor output. Average over multiple readings
    
    Returns
    -------
    mean value
    
    
    Unit Test Result
    ----------------
    """
    
    sample=[]
    
    for i in range(0,ADC_SAMPLE_COUNT):       
        adcVal=adc_trans.read()
        voltage = adcVal / 4095.0 * 3.3
        sample.append(voltage)
    
    mean=calculate_sample_statistics(sample)

    return mean

def read_incident_light_sensor():
    """ Read the photodiode sensor output. Average over multiple readings
    
    Returns
    -------
    mean value
    
    
    Unit Test Result
    ----------------
    """
    
    sample=[]
    
    for i in range(0,ADC_SAMPLE_COUNT):       
        adcVal=adc_incid.read()
        voltage = adcVal / 4095.0 * 3.3
        sample.append(voltage)
    
    mean=calculate_sample_statistics(sample)

    return mean

def self_test():
    """ Performs a self test to ensure sensors
        return values within specification
    
    Returns
    -------
    True: if all tests passed
    False: in all other cases 

    Unit Test Result
    ----------------

    """
    #load machine data
    #chekc machine data valid
    #turn off LEDs
    #read dark values
    #check dark values
    #read and check illuminated values for empty photometer
    

def write_machine_data():
    """ write the machine data dictionary to MACHINE_DATA_FILENAME
        in the form of a json form

    Returns
    -------
    True: if successful
    False: if not successful 

    Unit Test Result
    ----------------

    """
    global machine_data
    
    try:
        f=open(MACHINE_DATA_FILENAME,'w+') #w+ mode will overwrite existing file
        f.write(json.dumps(machine_data))
        f.close()
    except:
        return False
    else:
        return True


def read_machine_data():
    """ reads the data in MACHINE_DATA_FILENAME to the machine_data dictionary
        set the real time clock date if required

    Returns
    -------
    True: if successful
    False: if not successful 

    Unit Test Result
    ----------------

    """
    global machine_data
    try:
        f=open(MACHINE_DATA_FILENAME,'r') #read mode
        res=f.read()
        print(res)
        
        machine_data=json.loads(res)
        f.close()
        #set the date if required
        if (machine_data['set_datetime']=='Y'):
            d=[int(i) for i in machine_data['set_rtc_datetime_to'].split(',')] #convert setting to an a list of integers
            rtc.datetime(d)        
    except:
        return False
    else:
        return True

    
def read_blank():
    """ reads the blank sample
    
    Returns
    -------
    True: if successful
    False: if not successful 

    Unit Test Result
    ----------------

    """
    
    #Perform readings for each color of illumination
    lcd_display(['Reading Blank','Dark\n20%'])
    turn_off_leds()
    blank_dark_incid=read_incident_light_sensor()
    blank_dark_trans=read_transmission_light_sensor()
    turn_off_leds()
    
    lcd_display(['Reading Blank','Red\n40%\n****'])
    turn_on_red_led()
    blank_red_incid=read_incident_light_sensor()
    blank_red_trans=read_transmission_light_sensor()
    turn_off_leds()
    
    lcd_display(['Reading Blank','Green\n60%\n******'])
    turn_on_green_led()
    blank_green_incid=read_incident_light_sensor()
    blank_green_trans=read_transmission_light_sensor()
    turn_off_leds()
    
    lcd_display(['Reading Blank','Blue\n80%\n********'])
    turn_on_blue_led()
    blank_blue_incid=read_incident_light_sensor()
    blank_blue_trans=read_transmission_light_sensor()
    turn_off_leds()
    
    blank_value_red=(blank_red_trans-blank_dark_trans)/(blank_red_incid-blank_dark_incid)
    blank_value_green=(blank_green_trans-blank_dark_trans)/(blank_green_incid-blank_dark_incid)
    blank_value_blue=(blank_blue_trans-blank_dark_trans)/(blank_blue_incid-blank_dark_incid)
    
    #write values to machine_data dictionary and save
    machine_data['blank_value_red']=blank_value_red
    machine_data['blank_value_green']=blank_value_green
    machine_data['blank_value_blue']=blank_value_blue
    
    if write_machine_data():
        lcd_display(['Reading Blank','complete\n100%\n**********'])   
        return True
    
    else:
        lcd_display(['Reading Blank','failed'])   
        return False
    
    
def read_sample():
    """ reads the sample
    
    Returns
    -------
    True: if successful
    False: if not successful 

    Unit Test Result
    ----------------

    """
    #Perform readings for each color of illumination
    lcd_display(['Reading Sample','Dark'])
    turn_off_leds()
    samp_dark_incid=read_incident_light_sensor()
    samp_dark_trans=read_transmission_light_sensor()
    
    
    lcd_display(['Reading Sample','Red LED'])
    turn_on_red_led()
    samp_red_incid=read_incident_light_sensor()
    samp_red_trans=read_transmission_light_sensor()
    turn_off_leds()
    
    
    lcd_display(['Reading Sample','Green LED'])
    turn_on_green_led()
    samp_green_incid=read_incident_light_sensor()
    samp_green_trans=read_transmission_light_sensor()
    turn_off_leds()
    
    lcd_display(['Reading Sample','Blue LED'])
    turn_on_blue_led()
    samp_blue_incid=read_incident_light_sensor()
    samp_blue_trans=read_transmission_light_sensor()
    turn_off_leds()
    
    samp_value_red=(samp_red_trans-samp_dark_trans)/(samp_red_incid-samp_dark_incid)
    samp_value_green=(samp_green_trans-samp_dark_trans)/(samp_green_incid-samp_dark_incid)
    samp_value_blue=(samp_blue_trans-samp_dark_trans)/(samp_blue_incid-samp_dark_incid)
    
    samp_transmission_red=100*samp_value_red/(machine_data['blank_value_red'])
    samp_transmission_blue=100*samp_value_blue/(machine_data['blank_value_blue'])
    samp_transmission_green=100*samp_value_green/(machine_data['blank_value_green'])
    
    #display results on serial port
    print('Transmission Values')
    print('Red: ' +str('{:.2f}%'.format(abs(samp_transmission_red))))
    print('Green: '+str('{:.2f}%'.format(abs(samp_transmission_green))))
    print('Blue: '+str('{:.2f}%'.format(abs(samp_transmission_blue))))
    
    #format values to 1 decimal place
    result='Red:   ' +str('{:.2f}%'.format(abs(samp_transmission_red)))
    result=result+'\nGreen: '+str('{:.2f}%'.format(abs(samp_transmission_green)))
    result=result+'\nBlue:  '+str('{:.2f}%'.format(abs(samp_transmission_blue)))
    
    lcd_display(['Transmission Values',result])
    return True
    
"""    
def compare_number(a,b,tolerance):

def average(data):

def stdev(data):
"""    
    
#Main Loop
#self_test()
read_machine_data()
print(['Spectrophotometer','Version: '+VERSION])
lcd_display(['  Spectrophotometer','    Version: '+VERSION+"\n    NASA-CaSGC\n    Spring 2022"])
sleep_ms(1000)


while True:
    if is_read_blank_ok_button_pressed():
        print("read blank button is pressed")
        read_blank()
    
    if is_read_sample_button_pressed():
        print("read sample button is pressed")
        read_sample()
    
    sleep_ms(250)
