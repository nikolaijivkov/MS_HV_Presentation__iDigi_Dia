"""\
This is a demonstration of how to write a (not so) simple device_driver using xbee_device_manager, capable of reading Xbee/ZigBee data.

Developed in March, 2013
@author: eng. Nikolay Jivkov, master student at Technical University of Sofia, branch Plovdiv
email: nikolaijivkov@gmail.com
"""

# imports
#import struct
from devices.device_base import DeviceBase
from devices.xbee.xbee_devices.xbee_base import XBeeBase
from settings.settings_base import SettingsBase, Setting
from channels.channel_source_device_property import *
from devices.xbee.xbee_config_blocks.xbee_config_block_ddo \
    import XBeeConfigBlockDDO
from devices.xbee.xbee_device_manager.xbee_device_manager_event_specs \
    import *
from devices.xbee.common.addressing import *
from devices.xbee.common.io_sample import parse_is
from devices.xbee.common.prodid import PROD_DIGI_UNSPECIFIED, \
    PROD_DIGI_XB_WALL_ROUTER, PROD_DIGI_XB_SENSOR_LT , PROD_DIGI_XB_SENSOR_LTH
import time
#import serial
import sys, os
from binascii import hexlify, unhexlify

class ZigBeeTransferDevice(XBeeBase, threading.Thread):

    # Define a set of endpoints that this device will send in on.
    ADDRESS_TABLE = [ [0xe8, 0xc105, 0x92], [0xe8, 0xc105, 0x11] ]

    # The list of supported products that this driver supports.
    SUPPORTED_PRODUCTS = [ PROD_DIGI_UNSPECIFIED, PROD_DIGI_XB_WALL_ROUTER, PROD_DIGI_XB_SENSOR_LT , PROD_DIGI_XB_SENSOR_LTH, ]

    def __init__(self, name, core_services):
        self.__name = name
        self.__core = core_services
        
        self.__xbee_manager = None
        
        from core.tracing import get_tracer
        self.__tracer = get_tracer(name)

        # Settings:
        #
        # xbee_device_manager:  must be set to the name of an XBeeDeviceManager
        #                       instance.
        # extended_address:     is the extended address of the XBee device you
        #                       would like to monitor.
        # sleep:                True/False setting which determines if we should put the
        #                       device to sleep between samples.  Default: True
        # sample_rate_ms:       the sample rate of the XBee adapter. Default:
        #                       20,000 ms or 20 sec.
        #
        # Advanced settings:
        #
        # awake_time_ms:        how long should the sensor stay awake after taking
        #                       a sample?  The default is 1000 ms.
        # sample_predelay:      how long should the sensor be awake for before taking
        #                       its sample reading?  This delay is used to allow the
        #                       device's sensoring components to warm up before
        #                       taking a sample.  The default is 125ms.

        settings_list = [
            Setting(
                name='xbee_device_manager', type=str, required=False,#actually this must be true
                default_value=''),
            Setting(
                name='extended_address', type=str, required=False,#actually this must be true
                default_value=''),
            Setting(
                name='sleep', type=bool, required=False,
                default_value=True),
            Setting(
                name='sample_rate_ms', type=int, required=False,
                default_value=20000),
            # These settings are provided for advanced users, they
            # are not required:
            Setting(
                name='awake_time_ms', type=int, required=False,
                default_value=1000,
                verify_function=lambda x: x >= 0 and x <= 0xffff),
            Setting(
                name='sample_predelay', type=int, required=False,
                default_value=125,
                verify_function=lambda x: x >= 0 and x <= 0xffff),
            
        ]
        ## Channel Properties Definition:
        property_list = [
            ChannelSourceDeviceProperty(name='data_channel', type=str,
                initial=Sample(timestamp=0, value="", unit='hex'),
                perms_mask=DPROP_PERM_GET,
                options=DPROP_OPT_AUTOTIMESTAMP,
            )
        ]
                                            
        ## Initialize the DeviceBase interface:
        XBeeBase.__init__(self, self.__name, self.__core,
                                settings_list, property_list)
        
    ## Functions which must be implemented to conform to the XBeeBase
    ## interface:

    @staticmethod
    def probe():
        #   Collect important information about the driver.
        #
        #   .. Note::
        #
        #       This method is a static method.  As such, all data returned
        #       must be accessible from the class without having a instance
        #       of the device created.
        #
        #   Returns a dictionary that must contain the following 2 keys:
        #           1) address_table:
        #              A list of XBee address tuples with the first part of the
        #              address removed that this device might send data to.
        #              For example: [ 0xe8, 0xc105, 0x95 ]
        #           2) supported_products:
        #              A list of product values that this driver supports.
        #              Generally, this will consist of Product Types that
        #              can be found in 'devices/xbee/common/prodid.py'

        probe_data = XBeeBase.probe()

        for address in ZigBeeTransferDevice.ADDRESS_TABLE:
            probe_data['address_table'].append(address)
        for product in ZigBeeTransferDevice.SUPPORTED_PRODUCTS:
            probe_data['supported_products'].append(product)

        return probe_data

    ## Functions which must be implemented to conform to the DeviceBase
    ## interface:
    def apply_settings(self):

        SettingsBase.merge_settings(self)
        accepted, rejected, not_found = SettingsBase.verify_settings(self)

        if len(rejected) or len(not_found):
            # there were problems with settings, terminate early:
            return (accepted, rejected, not_found)

        SettingsBase.commit_settings(self, accepted)

        return (accepted, rejected, not_found)

    
    def set_channel(self, channel_name, value):
        """
        #Set channel's value and timestamp with a new data.
        """
        try:
            cm = self.__core.get_service("channel_manager")
            cdb = cm.channel_database_get()
            channel = cdb.channel_get(channel_name)
            try:
                print "in set_channel" #if this is not displayed => this function is not called => it must be deleted...
                typing_value = channel.type()(value)#what is going on here?! I don't know...
            except:
                traceback.print_exc()
                return
            channel.consumer_set(Sample(time.time(), typing_value))
        except Exception:
            traceback.print_exc()
    
    def start(self):
        """Start the device driver.  Returns bool."""
        # Fetch the XBee Manager name from the Settings Manager:
        xbee_manager_name = SettingsBase.get_setting(self, "xbee_device_manager")
        dm = self.__core.get_service("device_driver_manager")
        self.__xbee_manager = dm.instance_get(xbee_manager_name)

        # Register ourselves with the XBee Device Manager instance:
        self.__xbee_manager.xbee_device_register(self)

        # Get the extended address of the device:
        extended_address = SettingsBase.get_setting(self, "extended_address")

        # Create a callback specification for our device address, endpoint
        # Digi XBee profile and sample cluster id:
        xbdm_rx_event_spec = XBeeDeviceManagerRxEventSpec()
        xbdm_rx_event_spec.cb_set(self._sample_indication)
        xbdm_rx_event_spec.match_spec_set(
            (extended_address, 0xe8, 0xc105, 0x92),
            (True, True, True, True))
        self.__xbee_manager.xbee_device_event_spec_add(self,
                                xbdm_rx_event_spec)

        # Create a DDO configuration block for this device:
        xbee_ddo_cfg = XBeeConfigBlockDDO(extended_address)

        # Get the gateway's extended address:
        gw_xbee_sh, gw_xbee_sl = gw_extended_address_tuple()

        # Set the destination for I/O samples to be the gateway:
        xbee_ddo_cfg.add_parameter('DH', gw_xbee_sh)
        xbee_ddo_cfg.add_parameter('DL', gw_xbee_sl)
        
        #""" IF YOUR XBEE DEVICE DON'N SLEEP AND YOU SEND DATA FROM XBEE DEVICE TO ConnectPort X manually then uncoment the start of that line.
        # Configure the IO Sample Rate:
        # Clip sample_rate_ms to the max value of IR:
        sample_rate_ms = SettingsBase.get_setting(self, "sample_rate_ms")
        sample_rate_ms = min(sample_rate_ms, 0xffff)
        xbee_ddo_cfg.add_parameter('IR', sample_rate_ms)

        # Register this configuration block with the XBee Device Manager:
        self.__xbee_manager.xbee_device_config_block_add(self, xbee_ddo_cfg)

        # Setup the sleep parameters on this device:
        will_sleep = SettingsBase.get_setting(self, "sleep")
        sample_predelay = SettingsBase.get_setting(self, "sample_predelay")
        awake_time_ms = (SettingsBase.get_setting(self, "awake_time_ms") +
                         sample_predelay)
        
        if will_sleep:
            # Sample time pre-delay, allow the circuitry to power up and
            # settle before we allow the XBee to send us a sample:            
            xbee_ddo_wh_block = XBeeConfigBlockDDO(extended_address)
            xbee_ddo_wh_block.apply_only_to_modules((MOD_XB_ZB, MOD_XB_S2C_ZB,))
            xbee_ddo_wh_block.add_parameter('WH', sample_predelay)
            self.__xbee_manager.xbee_device_config_block_add(self,
                                    xbee_ddo_wh_block)

        # The original sample rate is used as the sleep rate:
        sleep_rate_ms = SettingsBase.get_setting(self, "sample_rate_ms")
        xbee_sleep_cfg = XBeeConfigBlockSleep(extended_address)
        if will_sleep:
            xbee_sleep_cfg.sleep_cycle_set(awake_time_ms, sleep_rate_ms)
        else:
            xbee_sleep_cfg.sleep_mode_set(SM_DISABLED)
        self.__xbee_manager.xbee_device_config_block_add(self, xbee_sleep_cfg)
        #"""
        # Register this configuration block with the XBee Device Manager:
        self.__xbee_manager.xbee_device_config_block_add(self, xbee_ddo_cfg)

        # Indicate that we have no more configuration to add:
        self.__xbee_manager.xbee_device_configure(self)
        
        #threading.Thread.start(self)
        
        return True

    def stop(self):
        """Stop the device driver.  Returns bool."""
        # Unregister ourselves with the XBee Device Manager instance:
        self.__xbee_manager.xbee_device_unregister(self)
        return True
    
    """
    def run(self):
        "run when our device driver thread is started"
        #at some point of time...
        while True:
            T_sec=5*60 #5min
            time.sleep(T_sec)
            flag=self._write('Hello world!')
            if flag==False:
                print "Housten, we have a problem: Transmiting error!"
        return True
    """
    
    ## Locally defined functions:
    def _sample_indication(self, buf, addr):
        """\
        This is our data reader function.
        
        Called when data is received from our XBee device.
        Do not call it manually, it is called by xbee_device_manager.
        """
        #print 'Buffer, Address:', buf, addr
        try:
            #We may be (or may not be!) in need of translating our data with: hexlify or unhexlify. 
            data = hexlify(str(buf))
            print 'RAW data: ', buf
            print 'heXlify data: ', data
        except:
            traceback.print_exc()
        self.property_set('data_channel', Sample(0, str(data), 'hex'))
    
    def _write(self, data):
        """\
        Writes a buffer of data out the XBee device.

        Returns True if successful, False on failure.
        Call it manually when you want to send data to XBee device.
        """

        ret = False
        extended_address = SettingsBase.get_setting(self, "extended_address")
        addr = (extended_address, 0xe8, 0xc105, 0x11)#prey this works, I can't test it...
        try:
            self.__xbee_manager.xbee_device_xmit(0xe8, data, addr)
            ret = True
            print "success!" #
        except:
            print "(..., 0xc105, 0x11) faild, trying (..., 0, 0)" #
            try: #
                addr = (extended_address, 0xe8, 0, 0) #
                self.__xbee_manager.xbee_device_xmit(0xe8, data, addr) #
                ret = True #
                print "success!" #
            except: #
                print "(..., 0, 0) faild" #
                pass
        return ret
    
    def get_properties(self):
        cm = self.__core.get_service("channel_manager")
        cd = cm.channel_database_get()
        return cd.channel_list()
# internal functions & classes

def main():
    pass

if __name__ == '__main__':
    import sys
    status = main()
    sys.exit(status)
