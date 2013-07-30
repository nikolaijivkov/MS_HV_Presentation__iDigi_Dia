"""\
Devepoled in Octomber, 2012 
@author: eng. Nikolay Jivkov, master student at Technical University of Sofia, branch Plovdiv
email: nikolaijivkov@gmail.com
"""

# imports
from devices.device_base import DeviceBase
from settings.settings_base import SettingsBase, Setting
from channels.channel_source_device_property import *

import threading
import time

import serial
import sys, os
import binascii

class HrSpo2Device(DeviceBase, threading.Thread):

    def __init__(self, name, core_services):
        self.__name = name
        self.__core = core_services
        
        ## Settings Table Definition:
        settings_list = [
            Setting(
                name='sample_rate_ms', type=float, required=False,
                default_value=1000.0,
                verify_function=lambda x: x >= 0.0),
            Setting(
                name='channel_settings', type=str, required=False,
                default_value="name,unit"),
        ]

        ## Channel Properties Definition:
        property_list = []
                                            
        ## Initialize the DeviceBase interface:
        DeviceBase.__init__(self, self.__name, self.__core,
                                settings_list, property_list)

        ## Thread initialization:
        self.__stopevent = threading.Event()
        threading.Thread.__init__(self, name=name)
        threading.Thread.setDaemon(self, True)


    ## Functions which must be implemented to conform to the DeviceBase
    ## interface:

    def apply_settings(self):
        """\
            Called when new configuration settings are available.
       
            Must return tuple of three dictionaries: a dictionary of
            accepted settings, a dictionary of rejected settings,
            and a dictionary of required settings that were not
            found.
        """
        SettingsBase.merge_settings(self)
        accepted, rejected, not_found = SettingsBase.verify_settings(self)
        if len(rejected) or len(not_found):
            print "Settings rejected/not found: %s %s" % (rejected, not_found)
            
        SettingsBase.commit_settings(self, accepted)
        
        return (accepted, rejected, not_found)
    
    def set_channel(self, channel_name, value):
        """
        Set channel's value and timestamp with a new data.
        """
        try:
            cm = self.__core.get_service("channel_manager")
            cdb = cm.channel_database_get()
            channel = cdb.channel_get(channel_name)
            try:
                typing_value = channel.type()(value)
            except Exception:
                traceback.print_exc()
                return
            channel.consumer_set(Sample(time.time(), typing_value))
        except Exception:
            traceback.print_exc()
    
    def start(self):
        """Start the device driver.  Returns bool."""
        self.add_property(
            ChannelSourceDeviceProperty(name='Heart Rate', type=str,
                initial=Sample(timestamp=0, value="", unit='BPM'),
                perms_mask=(DPROP_PERM_GET | DPROP_PERM_SET),
                options=DPROP_OPT_AUTOTIMESTAMP,
                set_cb=lambda sample: self.property_set('Heart Rate', sample))
            )
        self.add_property(
            ChannelSourceDeviceProperty(name='Blood Oxygen Saturation', type=str,
                initial=Sample(timestamp=0, value="", unit='%'),
                perms_mask=(DPROP_PERM_GET | DPROP_PERM_SET),
                options=DPROP_OPT_AUTOTIMESTAMP,
                set_cb=lambda sample: self.property_set('Blood Oxygen Saturation', sample))
            )
        
        self.runing = 1
        threading.Thread.start(self)
        
        return True

    def stop(self):
        """Stop the device driver.  Returns bool."""
        self.__stopevent.set()
        self.runing = 0
        time.sleep(1)
        try:
            self.disconnect()
            self.s.close()
        except:
            pass
        return True

    ## Locally defined functions:
    
    # Property callback functions:
    
    def get_properties(self):
        cm = self.__core.get_service("channel_manager")
        cd = cm.channel_database_get()
        return cd.channel_list()
    
    # Threading related functions:
    
    def connect(self, reconnect=0):
        self.s.flushInput()
        if(reconnect):
            while True:
                self.s.write('ATD\r\n')
                time.sleep(4)
                data = self.s.read(30).strip('\r\n')
                print(data)
                
                if('CONNECT' in data):
                    abort = 0
                    print('Conected\r\n')
                    break
        else:
            self.s.write('+++\r\n')
            time.sleep(0.5)
            print(self.s.read(10).strip('\r\n'))
                
            self.s.write('AT&F\r\n')
            time.sleep(0.5)
            print(self.s.read(10).strip('\r\n'))
            
            self.s.write('AT+BTSEC,1,0\r\n')
            time.sleep(0.5)
            print(self.s.read(10).strip('\r\n'))
            
            self.s.write('AT+BTKEY="810657"\r\n')
            time.sleep(0.5)
            print(self.s.read(10).strip('\r\n'))
            
            while True:
                self.s.write('ATD001C050018EA\r\n')
                time.sleep(4)
                data = self.s.read(30).strip('\r\n')
                #print(data)
                
                if('CONNECT' in data):
                    abort = 0
                    print('Conected\r\n')
                    break
            
            if(not abort):
                data = binascii.unhexlify('027002020803')
                s.write(data)#+'\r\n')
                time.sleep(0.5)
                print(self.s.read(10))
    
    return abort

    def disconnect(self):
        self.s.write('ATH\r\n')
        time.sleep(0.5)
        print(self.s.read(10).strip('\r\n'))
        
        self.s.write('AT+BTMODE,1\r\n')
        time.sleep(0.5)
        print(self.s.read(10).strip('\r\n'))
        
        self.s.write('ATZ\r\n')
        time.sleep(0.5)
        print(self.s.read(10).strip('\r\n'))
        
    def run(self):
        """run when our device driver thread is started"""
        # Calculate Sleep time from update_rate
        try:
            SLEEP = SettingsBase.get_setting(self, "sample_rate_ms") / 1000.0
        except:
            SLEEP = 1.0
        
        #self.s = serial.Serial(port=0, baudrate=9600, parity='N', stopbits=1, timeout=1)
        self.s = serial.Serial(
           0, #port number
           baudrate=9600, #baudrate
           bytesize=serial.EIGHTBITS, #number of databits
           parity=serial.PARITY_NONE, #enable parity checking
           stopbits=serial.STOPBITS_ONE, #number of stopbits
           timeout=1, #set a timeout value
           xonxoff=0, #enable software flow control
           rtscts=0, #enable RTS/CTS flow control
        )
        
        abort = self.connect()
        
        while(self.runing):
            errcount = 0
            try:
                ########################################
                self.s.flushInput()#self.s.flushOutput()
                ########################################
                time.sleep(SLEEP)
                if(SLEEP < 1.0): time.sleep(1.0 - SLEEP)
                
                data = self.s.read(4)
                if(data == ''): raise Exception('no data')
                #print data
                xdata0 = int(binascii.hexlify(data[0]), 16)
                xdata1 = int(binascii.hexlify(data[1]), 16)
                xdata2 = int(binascii.hexlify(data[2]), 16)
                
                hr = ((xdata0 & 0x03) << 7) | (xdata1 & 0x7f)
                spo2 = xdata2
                
                print 'Heart Rate:' + str(hr)
                self.property_set('Heart Rate', Sample(0, str(hr), 'BPM'))
                print 'Blood Oxygen Saturation :' + str(spo2)
                self.property_set('Blood Oxygen Saturation', Sample(0, str(spo2), '%'))
            except Exception, e:
                print 'Exception: %s\n' % e
                if(errcount % 5 == 0):
                    time.sleep(10)
                if(errcount > 20):    
                    errcount = 0
                    sys.stderr.write('Connection Lost! Trying to reconect...\n')
                    if(self.connect(1)):
                        self.runing = 0
                #if(errcount > 1000):
                #    self.runing = 0
                else:
                    errcount += 1

            
        print 'Exiting'

# internal functions & classes

def main():
    pass

if __name__ == '__main__':
    import sys
    status = main()
    sys.exit(status)
