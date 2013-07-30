"""\
Health Vault OFFline mode

Devepoled in January, 2013 
@author: eng. Nikolay Jivkov, master student at Technical University of Sofia, branch Plovdiv
email: nikolaijivkov@gmail.com
"""

# imports
import traceback
from devices.device_base import DeviceBase
from presentations.presentation_base import PresentationBase
from settings.settings_base import SettingsBase, Setting
from channels.channel_source_device_property import *
from channels.channel import \
    PERM_GET, PERM_SET, PERM_REFRESH, \
    OPT_AUTOTIMESTAMP, OPT_DONOTLOG, OPT_DONOTDUMPDATA
from samples.sample import Sample
import threading
import time, datetime
import urllib
from urllib import urlencode
from itty import *
import etree.ElementTree as ET
import sys
from xml.dom import minidom
import Queue
from healthvaultlib.settings import *
from healthvaultlib.healthvault import HealthVaultConn
import python_ccr_creator

if sys.platform.startswith('digi'):
    path = 'WEB/python/'
else:
    path = 'C:/'

class MSHealthVault(PresentationBase, threading.Thread):
    
    def __init__(self, name, core_services):
        self.__name = name
        self.__core = core_services
        ## Settings Table Definition:
        self.queue = Queue.Queue()
        settings_list = [
            Setting(
                name='server_ip', type=str, required=False,
                default_value="192.168.33.106"),
            Setting(
                name='server_port', type=int, required=False,
                default_value="8081"),
            Setting(
                name='tx_interval', type=int, required=False,
                default_value=30),
        ]
        
        ## Channel Properties Definition:
        property_list = [ ]
                                            
        ## Initialize the DeviceBase interface:
        PresentationBase.__init__(self, self.__name, settings_list)
        ## Thread initialization:
        self.__stopevent = threading.Event()
        threading.Thread.__init__(self, name=name)
        threading.Thread.setDaemon(self, True)
        
        ## HealthValut functions:
        http_path = "/hv/"
        
        APP_ADDR_PORT = 'http://' + SettingsBase.get_setting(self, "server_ip") + ':' + str(SettingsBase.get_setting(self, "server_port"))
        APP_ACTION_URL = APP_ADDR_PORT + http_path + 'back'
        html_path = APP_ADDR_PORT + http_path
        
        self.hvconn = None
        self.subscribed_channels = []
        self.tx_started = False
        self.hv_ccr_pump_runing = False
        self.hv_ccr_pump_stoped = False
        self.hv_ccr_pump_restart = False
        
        html_header = '\
                <!DOCTYPE html>\
                <html>\
                <head>\
                    <title>Digi HV Presentation</title>\
                    <style type="text/css">\
                        body {\
                            background: url("http://thecodelesscode.com/images/circuits-back.jpg") 0% 0% repeat;\
                            font-size:2.5em;\
                            margin: 0;\
                            padding: 0;\
                            text-align: center;\
                        }\
                        a:link {color:black; text-decoration:none;}\
                        a:visited {color:black; text-decoration:none;}\
                        a:hover {color:red; text-decoration:underline;}\
                        a:active {color:red; text-decoration:underline;}\
                        .centered {margin: 0 auto; text-align: left; display: table;}\
                    </style>\
                </head>\
                <body><div class="centered">'
        html_footer = '</div></body></html>'
        
        @get('')
        @get('index')
        @get(http_path)
        @get(http_path + 'index')
        def IndexPage(request):
            html = html_header + '\
                <a href="' + html_path + 'create" target="_self">Create new App</a>\
                <br><br>\
                <a href="' + html_path + 'login" target="_self">Login new User</a>\
                <br><br>\
                <a href="' + html_path + 'user_list" target="_self">List of Users</a>\
                <br><br>\
                <a href="' + html_path + 'selected" target="_self">Selected User</a>\
                <br><br>'
            if not self.tx_started:
                #html += '<a href="' + html_path + 'tx_start" target="_self">Start HV Data Tx</a>'
                html += '<a href="' + html_path + 'tx_control" target="_self">Start HV Data Tx</a>'
            else:
                #html += '<a href="' + html_path + 'tx_stop" target="_self">Stop HV Data Tx</a>'
                html += '<a href="' + html_path + 'tx_control" target="_self">Stop HV Data Tx</a>'
            html += '\
                <br><br>\
                <a href="' + html_path + 'channels" target="_self">Channel Explorer</a>'
            html += html_footer
            
            return Response(html, content_type='text/html')
        
        @get(http_path + 'create')
        def CreateAppInstance(request):
            self.hvconn = HealthVaultConn(path)
            
            d = {}
            d['appid'] = HV_APPID
            d['appCreationToken'] = self.hvconn.instance_creation_token
            d['instancename'] = 'iDigi Dia MS_HV presentation'
            d['redirect'] = APP_ACTION_URL
            
            targetqs = urlencode(d)
            url = "%s/redirect.aspx?%s" % (HV_SHELL_URL, urlencode({'target': "CREATEAPPLICATION", 'targetqs': targetqs}))
            raise Redirect(url)
        
        @get(http_path + 'login')
        def LoginNewUser(request):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            
            d = {}
            d['appid'] = self.hvconn.instance_app_id
            d['redirect'] = APP_ACTION_URL
            
            targetqs = urlencode(d)
            url = "%s/redirect.aspx?%s" % (HV_SHELL_URL, urlencode({'target': "APPAUTH", 'targetqs': targetqs}))
                
            raise Redirect(url)
        
        @get(http_path + 'back')
        def ShellRedirectionPoint(request):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            self.hvconn.createAuthenticatedSessionToken()
            html = html_header + '\
                Success\
                <br><br>\
                <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
            return Response(html, content_type='text/html')
        
        @get(http_path + 'user_list')
        def AuthorizedPeopleList(request):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            self.hvconn.getAuthorizedPeople()
            #users = ''
            html = html_header
            for i in self.hvconn.user_dict:
                name = self.hvconn.user_dict[i]["name"]
                html += '\
                <a href="' + html_path + 'select/' + name.replace(' ', '_') + '" target="_self">' + name + '</a>\
                <br><br>'
            html += '\
                <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
            return Response(html, content_type='text/html')
            
        @get(http_path + 'select/(?P<name>\w+)')
        def SelectUser(request, name=None):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            name = name.replace('_', ' ')
            if name == self.hvconn.selected_user:
                message = 'User already selected.'
            else:
                message = 'User not found.'
                for i in self.hvconn.user_dict:
                    if name == self.hvconn.user_dict[i]["name"]:
                        found = 1
                        self.hvconn.userSelect(name)
                        self.hv_ccr_pump_reset()
                        message = 'User selected.'
            html = html_header +'\
                ' + message + '\
                <br><br>\
                <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
            return Response(html, content_type='text/html')
        
        @get(http_path + 'selected')
        def SelectedUser(request):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            user = self.hvconn.selected_user#.replace(' ', '_')
            html = html_header + '\
                Selected User: ' + user + '\
                <br><br>\
                <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
            return Response(html, content_type='text/html')
        
        @get(http_path + 'tx_control')
        def TxControl(request):
            if(self.hvconn == None):
                raise Redirect(APP_ADDR_PORT + '/create')
            
            if not self.tx_started:
                self.tx_started = True
                self.hv_ccr_pump_start()
                html = html_header +'\
                    Auto Data Tx Started!\
                    <br><br>\
                    <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            else:
                self.tx_started = False
                self.hv_ccr_pump_stop()
                html = html_header +'\
                    Auto Data Tx Stopped!\
                    <br><br>\
                    <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
                
            return Response(html, content_type='text/html')
        
        
        @get(http_path + 'tx_start')
        def TxStart(request):
            if(self.hvconn == None):
                raise Redirect(APP_ADDR_PORT + '/create')
            if not self.tx_started:
                self.tx_started = True
            self.hv_ccr_pump_start()
            html = html_header +'\
                Auto Data Tx Started!\
                <br><br>\
                <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
            return Response(html, content_type='text/html')
        
        @get(http_path + 'tx_stop')
        def TxStop(request):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            if self.tx_started:
                self.tx_started = False
            self.hv_ccr_pump_stop()
            html = html_header +'\
                Auto Data Tx Stopped!\
                <br><br>\
                <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
            return Response(html, content_type='text/html')
        
        @get(http_path + 'channels')
        def ChannelExplorer(request):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            
            cm = self.__core.get_service("channel_manager")
            cd = cm.channel_database_get()
            channel_list = cd.channel_list()
            
            html = html_header +'\
                Existing Channels:\
                <br><br>'
            for channel_name in channel_list:
                if channel_name in self.subscribed_channels:
                    html += '<a href="' + html_path + 'subscriber/' + channel_name + '" target="_self">Unsubscribe from: '+channel_name+'</a>'
                else:
                    html += '<a href="' + html_path + 'subscriber/' + channel_name + '" target="_self">Subscribe to: '+channel_name+'</a>'
                html += '<br><br>'
            html += '\
                <a href="' + html_path + 'index" target="_self">Back to Index Page</a>'
            html += html_footer
            return Response(html, content_type='text/html')
        
        @get(http_path + 'subscriber/(?P<channel_name>[\w\-._%]+)')
        def ChannelSubscriber(request, channel_name=None):
            if(self.hvconn == None):
                raise Redirect(html_path + 'create')
            channel_name=channel_name.replace('%20', ' ')
            if channel_name in self.subscribed_channels:
                #unsubscribe:
                self.unsubscriber(channel_name)
                self.subscribed_channels.remove(channel_name)
            else:
                #subscribe:
                self.subscriber(channel_name)
                self.subscribed_channels.append(channel_name)
            raise Redirect(html_path + 'channels')
        
        @get(http_path + 'get')
        def GetThing(request):
            if(self.hvconn == None):
                raise Redirect(APP_ADDR_PORT + '/create')
            try:
                personaldemographic = "92ba621e-66b3-4a01-bd73-74844aed4f5b"
                
                response_str = self.hvconn.getBasicThing(personaldemographic)
                return Response(response_str, content_type='text/xml')
                
            except:
                traceback.print_exc()
                
            return Response(response_str, content_type='text/xml')
        ##############################################################################
        @get(http_path + 'put_ccr')
        def PutThing_CCR(request):
            if(self.hvconn == None):
                raise Redirect(APP_ADDR_PORT + '/create')
            
            try:
                personaldemographic = "92ba621e-66b3-4a01-bd73-74844aed4f5b"
                ccr = "1e1ccbfc-a55d-4d91-8940-fa2fbf73c195"
                
                response_str = self.hvconn.getBasicThing(personaldemographic)
                
                dom = minidom.parseString(response_str)
                
                node = dom.getElementsByTagName("first")
                first_name = node.pop().firstChild.nodeValue    
                
                node = dom.getElementsByTagName("last")
                family_name = node.pop().firstChild.nodeValue    
                
                node = dom.getElementsByTagName("y")
                year = node.pop().firstChild.nodeValue
                
                node = dom.getElementsByTagName("m")
                month = node.pop().firstChild.nodeValue
                
                node = dom.getElementsByTagName("d")
                day = node.pop().firstChild.nodeValue
                
                date_of_birth = year + '-' + month + '-' + day
        
            except:
                traceback.print_exc()
                
            ccr_xml = self.Channels_to_CCR(first_name, family_name, date_of_birth)
            response_str = self.hvconn.putBasicThing(ccr, ccr_xml)
            
            return Response(response_str, content_type='text/xml')
        
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

    def start(self):
        """Start the device driver.  Returns bool."""
        threading.Thread.start(self)
        return True

    def stop(self):
        """Stop the device driver.  Returns bool."""
        self.unsubscriber()
        #self.hv_ccr_pump_runing = False
        self.hv_ccr_pump_stoped = True
        self.__stopevent.set()
        return True
                
    ## HealthVault help functions:
    def subscriber(self, source_name=None):
        cm = self.__core.get_service("channel_manager")
        cp = cm.channel_publisher_get()
        try:
            if(source_name == None):
                print 'subscribe to all channels'
                cp.subscribe_to_all(self.prop_set_input)
            else:
                print 'subscribe to a specific channel: ', source_name
                cp.subscribe(source_name, self.prop_set_input)
            #cp.subscribe_new_channels(self.subscriber) #this is going to subscribe to all new channels!!!
        except:
            traceback.print_exc()
        return True
    
    def unsubscriber(self, source_name=None):
        cm = self.__core.get_service("channel_manager")
        cp = cm.channel_publisher_get()
        try:
            if(source_name == None):
                print 'unsubscribe from all channels'
                cp.unsubscribe_from_all(self.prop_set_input)
            else:
                print 'unsubscribe from a specific channel: ', source_name
                cp.unsubscribe(source_name, self.prop_set_input)
            #cp.unsubscribe_new_channels(self.prop_set_input)
        except:
            traceback.print_exc()
        return True
    
    def prop_set_input(self, sample):
        if(not isinstance(sample, Sample)):
            
            channel_name = sample.name().split('.')[1]
            sample = sample.get()
            if self.sd!= None:
                self.sd.write(sample.value)
            self.queue.put((sample, channel_name))
            
            #print 'New sample arived in channel: ', channel_name
        return True
    
    def Channels_to_CCR(self, name, date_of_birth):
        if self.queue.empty():
            return False
        x = {}
        size = self.queue.qsize()
        for i in range(0, size):
            x[i] = self.queue.get()
            #sample, sample_name = x[i]
            
        #print "Created CCR with %s samples." % size
        ccr_xml, ccr_id = python_ccr_creator.CCR_gen(name, date_of_birth, x)
        ccr_xml += '\n<common><note>ccr_' + ccr_id + '.xml</note></common>'
        return ccr_xml
    
    def hv_ccr_pump_start(self):
        if self.hv_ccr_pump_runing:
            print "Already running?! We will restart then..."
            self.hv_ccr_pump_reset()
        else:
            threading.Thread(target=self.hv_ccr_pump).start()
    
    def hv_ccr_pump_reset(self):
        #self.hv_ccr_pump_runing = False
        self.hv_ccr_pump_stoped = True
        self.hv_ccr_pump_restart = True
    
    def hv_ccr_pump_stop(self):
        #self.hv_ccr_pump_runing = False
        self.hv_ccr_pump_stoped = True
        self.hv_ccr_pump_restart = False
        
    # Threading related functions:
    def hv_ccr_pump(self):
        if(self.hv_ccr_pump_runing): 
            print "This should never happen!"
            return True
        else: print "Ccr_pump is starting..."
        if(self.hvconn == None):
            print "hvconn = None! we will try again later..."
            self.hv_ccr_pump_start()
            return False
        
        #initializing flags
        self.hv_ccr_pump_runing = True
        self.hv_ccr_pump_restart = False
        tx_interval = int(SettingsBase.get_setting(self, "tx_interval"))
        
        personaldemographic = "92ba621e-66b3-4a01-bd73-74844aed4f5b"
        ccr = "1e1ccbfc-a55d-4d91-8940-fa2fbf73c195"
        
        response_str = self.hvconn.getBasicThing(personaldemographic)
        
        dom = minidom.parseString(response_str)
        
        node = dom.getElementsByTagName("full")
        name = node.pop().firstChild.nodeValue    
        
        try:
            node = dom.getElementsByTagName("y")
            year = node.pop().firstChild.nodeValue
            
            node = dom.getElementsByTagName("m")
            month = node.pop().firstChild.nodeValue
            
            node = dom.getElementsByTagName("d")
            day = node.pop().firstChild.nodeValue
            
            date_of_birth = '%s-%s-%s' % (year, month, day)
        except:
            date_of_birth = 'unknown'
        
        self.hv_ccr_pump_stoped = False
        while self.hv_ccr_pump_stoped==False:#self.hv_ccr_pump_runing:
            time.sleep(tx_interval)
            
            ccr_res = self.Channels_to_CCR(name, date_of_birth)
            if ccr_res != False:
                ccr_xml = ccr_res
                response_str = self.hvconn.putBasicThing(ccr, ccr_xml)
                print response_str
        self.hv_ccr_pump_runing = False
        
        if self.hv_ccr_pump_restart:
            print 'ccr_pump is reseting...'
            self.hv_ccr_pump_start()
        else: print 'ccr_pump is stoping...'
        return True
    
    def run(self):
        """run when our device driver thread is started"""
        self.sd = None
        '''/
        import serial
        self.sd = serial.Serial(
           0,                            #port number
           baudrate=115200,              #baudrate
           bytesize=serial.EIGHTBITS,    #number of databits
           parity=serial.PARITY_NONE,    #enable parity checking
           stopbits=serial.STOPBITS_ONE, #number of stopbits
           timeout=3,                    #set a timeout value
           xonxoff=0,                    #enable software flow control
           rtscts=0,                     #enable RTS/CTS flow control
        )
        '''
        
        try:
            fd = None
            fd = open(path + 'id_secret_token.txt', 'r+')
            id = fd.readline()
            secret = fd.readline()
            token = fd.readline()
            fd.close()
            self.hvconn = HealthVaultConn(path, id, secret, token)
        except:
            traceback.print_exc()
            if fd != None: fd.close()
            self.hvconn = None
        
        ip = SettingsBase.get_setting(self, "server_ip")
        port = int(SettingsBase.get_setting(self, "server_port"))
        server = 'wsgiref'
        run_itty(server, ip, port)
             
# internal functions & classes
    def get_properties(self):
        cm = self.__core.get_service("channel_manager")
        cd = cm.channel_database_get()
        return cd.channel_list()
    
def main():
    pass

if __name__ == '__main__':
    import sys
    status = main()
    sys.exit(status)
