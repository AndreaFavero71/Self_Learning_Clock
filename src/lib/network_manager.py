"""
Self-learning clock project
Class managing the networks related aspects



MIT License

Copyright (c) 2025 Andrea Favero

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from utime import ticks_ms, gmtime, time, time_ns, sleep_ms, ticks_diff
from socket import socket, getaddrinfo, AF_INET, SOCK_DGRAM
from struct import pack_into, unpack
from network import WLAN, STA_IF
from machine import RTC

import json, gc, aiodns
import uasyncio as asyncio
from lib.config import config

if config.PUSH_FILE_ENABLED:
    from urequests import post



class NetworkManager:
    def __init__(self, wdt_manager):
        
        # passed module for wdt management
        self.wdt_manager = wdt_manager
        
        # constants from the config file
        self.num_ntp_servers = len(config.NTP_SERVERS)
        self.try_open_networks = config.OPEN_NETWORKS
        self.ntp_delta = config.NTP_DELTA
        
        # flags recalled from outside the Class
        self.wifi_bool = False
        self.ntp_bool = False
        self.wlan = None
        
        # load the wifi data from the json file
        networks = self.load_wifi_config()
        
        # analyze the data from the json file
        self.secrets, self.ssid_list, self.passw_list, self.only_open_networks = self._evaluate_networks(networks)
        
        # intantiate the mcu RTC, for meaningfull offset info when NTP sync
        self.rtc = RTC()

    
    
    def feed_wdt(self, label=""):
        """use the WDT manager instead of global WDT"""
        if self.wdt_manager:
            self.wdt_manager.feed(label)

    
    
    def load_wifi_config(self, filename="lib/config/secrets.json"):
        """
        Loads the ssid and passwords from the json filename.
        It returns a dictionary with defined networks.
        It returns an empty list in case of no file or errors.
        """
        
        # feed the wdt
        self.feed_wdt(label="load_wifi_config")
        
        try:
            with open(filename, 'r') as f:
                config_data = json.load(f)
            return config_data["networks"]
        
        except Exception as e:
            
            # feedback is printed to the terminal
            if config.DEBUG:
                if self.try_open_networks:
                    print(f"\n[INFO]     Not found file {filename}, will search for open networks\n")
                elif not self.try_open_networks:
                    print(f"[ERROR]    error loading config: {e}")
            
            return []

    
    
    def _evaluate_networks(self, networks):
        """
        Evaluate the content of the networks lists.
        
        This function assumes the user's intention for open networks, if
        try_open_networks flag is True and below cases:
        - empty networks list (file was not founf, likely erased by the user)
        - ssid field being an empty string (fields erased by the user)
        - ssid field having 'YOUR_SSID' (file not edit by the)

        """
        
        # feed the wdt
        self.feed_wdt(label="evaluate_networks")
        
        try:
            secrets = True
            only_open_networks = False
            ssid_list, passw_list = [], []
            
            if self.try_open_networks:
                
                # case the ntwork list (of dicts) is empty
                if not networks:
                    
                    # assuming open netwroks is the intent (only_open_networks=True)
                    only_open_networks = True
                
                # case the networks list (list of dicts) is not empty
                elif networks:
                    try:
                        # analyse the first ssid/password of the list
                        netw = networks[0]
                        
                        # case the ssid/password fields are empty or not edited
                        if netw['ssid'] == '' or 'YOUR_SSID' in netw['ssid'] or netw['password'] == '':
                            
                            # assuming open netwroks is the user intent (only_open_networks=True)
                            only_open_networks = True
                            
                            # feedback is printed to the terminal
                            if config.DEBUG:
                                print("\n[INFO]     secrets.json has empty or not edit fields, will search for open networks\n") 

                    except Exception as e:
                        # feedback is printed to the terminal
                        if config.DEBUG:
                            print(f"[ERROR]    Something went wrong while evaluating Networks: {e}")

            # case there are defined netwrorks (at secrets.json)
            if not only_open_networks:
                
                # parse the defined networks
                ssid_list, passw_list = self._get_network_info(networks)
                
                # case of empty fields or mismatch between number of ssid and passwords
                if len(ssid_list)==0 or len(passw_list)==0 or len(ssid_list) != len(passw_list):
                    
                    # feedback is printed to the terminal
                    if config.DEBUG:
                        print("\n[ERROR]    No secrets.json or mismatch in number of SSID and Passwords")
                    
                    # flag segrets is set False
                    secrets = False
            
        except Exception as e:
            # feedback is printed to the terminal
            if config.DEBUG:
                print(f"[ERROR]    Something went wrong while evaluating Networks: {e}")
        
        return secrets, ssid_list, passw_list, only_open_networks
    
    
    
    def _get_network_info(self, networks):
        """
        Returns a list of ssid and a list of passwords, sorted by the priority values.
        Arg is a list of dicts.
        """       
        
        # feed the wdt
        self.feed_wdt(label="get_network_info")
        
        if not networks:
            # feedback is printed to the terminal
            if config.DEBUG:
                print("[ERROR]    no WiFi networks configured, check the file: secrets.json")
        
        ssid_list = []
        passw_list = []
        
        # sort networks by priority (lower number = higher priority)
        sorted_networks = sorted(networks, key=lambda x: x["priority"])

        for network_info in sorted_networks:
            ssid_list.append(network_info["ssid"])
            passw_list.append(network_info["password"])

        return ssid_list, passw_list

    
    
    def scan_open_networks(self):
        """scan for open WiFi networks and return them sorted by signal strength"""
        
        # feed the wdt
        self.feed_wdt(label="scan_open_networks")
        
        if config.DEBUG:
            print("[WiFi]     scanning for Wi-Fi networks...")
        
        # fix sleep time (in ms) while checking for the radio di disconnect and to deactivate
        sleep_for_ms = 10
        
        # ensure WLAN is active for scanning
        if self.wlan is None:
            # define wlan as station (client)
            self.wlan = WLAN(STA_IF)
        
        # ensure we start fresh
        self.disable_wifi(printout=False)
        sleep_ms(20)
        self.wlan.active(True)

        aps = self.wlan.scan()  # list of tuples: (ssid, bssid, channel, RSSI, authmode, hidden)
        open_aps = []
        for ap in aps:
            ssid_bytes = ap[0]
            ssid = ssid_bytes.decode() if isinstance(ssid_bytes, bytes) else str(ssid_bytes)
            authmode = ap[4]
            # in MicroPython: authmode==0 means open (no encryption)
            if authmode == 0:
                open_aps.append({'ssid': ssid, 'rssi': ap[3], 'channel': ap[2]})
        
        # sort by signal strength (strongest first)
        open_aps.sort(key=lambda x: x['rssi'], reverse=True)
        
        if config.DEBUG:
            print("[WiFi]     found {} open network(s).".format(len(open_aps)))
            for i, a in enumerate(open_aps):
                print("[WiFi]    {:2d}. SSID: {!r}, RSSI: {}, channel: {}".format(i+1, a['ssid'], a['rssi'], a['channel']))
        
        return open_aps

    
    
    async def is_internet_available(self, attempts=3, blocking=True):
        """Check internet connectivity using the DNS resolution functionality"""
        
        # iterate over the number of attemps
        for attempt in range(attempts):
            
            # feed the wdt
            self.feed_wdt(label="is_internet_available")
            
            try:
                # check if possible to resolve the IP one of the NTP servers
                ntp_servers_ip = await self.get_ntp_servers_ip(internet_check=True)
                
                # case the ntp_servers_ip list has at lest one element
                if ntp_servers_ip and len(ntp_servers_ip) > 0:
                    if config.DEBUG:
                        print("[INTERNET] internet connectivity detected")
                    
                    # return True to indicate success
                    return True
                    
            except Exception as e:
                # feedback is printed to the terminal
                if config.DEBUG:
                    print(f"[INTERNET] internet connectivity attempt {attempt + 1} failed: {e}")
            
            # in between attempts (last excluded)
            if attempt < attempts - 1:
                # sleep time of one second
                sleep_ms(1000)
        
        # feedback is printed to the terminal
        if config.DEBUG:
            print("[INTERNET] no internet connectivity detected")
        
        # return False to indicate failure
        return False

    
    
    def connect_to_open_wifi(self, ssid, max_attempts=3):
        """Attempt to connect to an open WiFi network"""
        
        # feed the wdt
        self.feed_wdt(label="connect_to_open_wifi")
        
        # caase the wlan object is None
        if self.wlan is None:
            # define wlan as station (client)
            self.wlan = WLAN(STA_IF)
        
        # feedback is printed to the terminal
        if config.DEBUG:
            print(f"[WIFI]     trying to connect to open network: {ssid} ...")
        
        # iterate over the attempts
        for attempt in range(max_attempts):
            
            # time reference
            t_ref_ms = ticks_ms()
            
            # ensure we start fresh for each attempt
            self.disable_wifi(printout=False)
            sleep_ms(20)
            self.wlan.active(True)
            
            # connect to open network (no password)
            self.wlan.connect(ssid, "")
            
            # wait for connection with 10 secs timeout
            timeout = 0
            
            # iterate until wlan connects or timeut (10 secs)
            while not self.wlan.isconnected() and timeout < 500:
                # feed the wdt
                self.feed_wdt(label="connect_to_open_wifi_wait")
                sleep_ms(20)
                timeout += 1
            
            # case of successfull connection
            if self.wlan.isconnected():
                
                # optimize the wlan transmition power, based on rssi (signal strenght)
                rssi, txpower = self._optimize_wlan_power()
                
                # feedback is printed to the terminal
                if config.DEBUG:
                    print(f"[WIFI]     connected to open network{ssid} in "
                          f"{ticks_diff(ticks_ms(), t_ref_ms)} ms")
                    print(f"[WIFI]     RSSI {rssi}, adjusted wlan tx power to {txpower} dB (20 is max)")
                    print(f"[WIFI]     IP address: {self.wlan.ifconfig()[0]}\n")
                
                # set the wifi_bool to True (success)
                self.wifi_bool = True
                
                # return True to indicate wlan connection success to open-network
                return True
            
            # feedback is printed to the terminal
            if config.DEBUG:
                print(f"[WIFI]     failed to connect to {ssid}, attempt {attempt + 1}")
            
            # case of a 1st failure, increases the wlan tx power to max
            if attempt == 1:
                # set the wlan tx power to 20dB (max)
                self._set_wlan_power(txpower=20) 
        
        # return False to indicate wlan connection failure to open-network
        return False

    
    
    def connect_to_wifi(self, blocking=True):
        """
        Attempt to connect to one of the SSIDs in ssid_list.
        Tries each SSID/password pair multiple times, with watchdog feeds.
        If open_networks is set True, those are scannes and tried too.
        Returns a WLAN object on success.
        """
        
        if config.DEBUG:
            print()
        
        # set the wifi_bool to False
        self.wifi_bool = False
        
        # define wlan as station (client)
        self.wlan = WLAN(STA_IF)
        
        # set the number of connections attempts
        attempts = 1 if not blocking else 5
        
        # iterate over the attempts
        for attempt in range(attempts):   # outer retry loop
            
            # case there are configured networks
            if not self.only_open_networks:
                
                # iterate over the configured networks
                for priority, ssid in enumerate(self.ssid_list):
                    
                    # time reference
                    if config.DEBUG:
                        t_ref_ms = ticks_ms()
                    
                    # feed the wdt
                    self.feed_wdt(label="connect_to_wifi_1")
                    
                    # retrieve the password for this ssid
                    password = self.passw_list[priority]
                    
                    # feedback is printed to the terminal
                    if config.DEBUG:
                        print(f"\n[WIFI]     trying to connect to: {ssid} ...")

                    # ensure we start fresh for each AP
                    self.disable_wifi(printout=False)
                    sleep_ms(20)
                    self.wlan.active(True)
                    
                    # attempt to connect to this ssid
                    self.wlan.connect(ssid, password)

                    # wait for connection with 10 secs timeout
                    timeout = 0
                    
                    # iterate until wlan connects or timeut (10 secs)
                    while not self.wlan.isconnected() and timeout < 500:
                        
                        # feed the wdt
                        self.feed_wdt(label="connect_to_wifi_2")
                        sleep_ms(20)
                        timeout += 1
                    
                    # case of successfull connection
                    if self.wlan.isconnected():
                        
                        # optimize the wlan transmition power, based on rssi (signal strenght)
                        rssi, txpower = self._optimize_wlan_power()
                        
                        # feedback is printed to the terminal
                        if config.DEBUG:
                            print(f"[WIFI]     connected to {ssid} in "
                                  f"{ticks_diff(ticks_ms(), t_ref_ms)} ms")
                            print(f"[WIFI]     RSSI {rssi}, adjusted wlan tx power to {txpower} dB (20 is max)")
                            print(f"[WIFI]     IP address: {self.wlan.ifconfig()[0]}\n")
                        
                        # set the wifi_bool to True (success)
                        self.wifi_bool = True
                        
                        # return the wlan object
                        return self.wlan
                    
                    # case of failed connection
                    else:
                        # feedback is printed to the terminal
                        if config.DEBUG:
                            print(f"[WIFI]     failed to connect to {ssid}, attempt {attempt}")

                # end for ssid_list
            
            # if configured networks failed, try open networks as fallback
            if self.try_open_networks and not self.wifi_bool:
                
                # case there are configured networks
                if not self.only_open_networks:
                    # feedback is printed to the terminal
                    if config.DEBUG:
                        print("\n[WIFI]     configured networks failed, trying open networks...")
                
                # call the function dealing with open networks
                open_networks = self.scan_open_networks()
                
                # case open networks are found, iterates over those with stronger signal
                for open_net in open_networks[:3]:  # try top 3 strongest open networks
                    
                    # attempt to connect to this open network ssid
                    if self.connect_to_open_wifi(open_net['ssid']):
                        
                        # set the wifi_bool to True (success) 
                        self.wifi_bool = True
                        
                        # return the wlan object
                        return self.wlan
            
            # it the iterator is not interrupted, attempt counter is increased
            attempt += 1
            
            # case the function has been called as non-blocking
            if not blocking:
                # iteration is interrupted
                break
            
            # case the function has been called as blocking
            else:
                # feed the wdt
                self.feed_wdt(label="connect_to_wifi_3")
                
                # case of a 1st failure, increases the wlan tx power to max
                if attempt == 1:
                    
                    # set the wlan tx power to 20dB (max)
                    self._set_wlan_power(txpower=20)
                    
        # all attempts are exhausted
        # feedback is printed to the terminal
        if config.DEBUG:
            # case function called as non-blocking
            if not blocking:
                print("[WIFI]     could not connect to any available network, ignored") 
            
            # case function called as blocking
            else:
                print("\n[ERROR]    could not connect to any available network, stopping the code")
        
        # return None instaed of a wlan object
        return None
    
    
    
    async def ensure_wlan(self, blocking=True):
        """Function checking is wlan is still up and running, using async internet check"""
        
        # case wlan exists yet not active
        if self.wlan is not None and not self.wlan.active():
            # activate the wifi: some routers need a full re-establish
            self.wlan.active(True)
        
        # case the wlan does not exist or is not active or is not connected 
        if self.wlan is None or not self.wlan.active() or not self.wlan.isconnected():
            
            # call the fuction to establish a wlan connection
            self.wlan = self.connect_to_wifi(blocking=blocking)
            
            # case the wlan object exists and is not active
            if self.wlan is not None and not self.wlan.active:
                
                # activate the wlan
                self.wlan.active(True)
        
        # case internet is not available
        if not await self.is_internet_available(blocking=blocking):
            
            # feedback is printed to the terminal
            if config.DEBUG:
                print("[ERROR]   internet is not available")
            
            # case the wlan is not connected to a modem or router
            if not self.wlan.isconnected() and blocking:
                # feedback is printed to the terminal
                if config.DEBUG:
                    print("[ERROR]   WiFi connection lost, attempting to reconnect ...")
                
                # call the function for wal connection
                self.wlan = self.connect_to_wifi(blocking=blocking)
        
        # return the wlan object
        return self.wlan

    
    
    
    def _optimize_wlan_power(self):
        """Optimize the wlan transmission power based on rssi (signal strenght)"""
        
        # case the wlan object is not None
        if self.wlan is not None:
            
            # iterates even times check, change, check ...
            for i in range(4):
                
                # check the rssi (signal strenght)
                rssi = self.wlan.status('rssi')   # returns the rssi (integer in dBm)
            
                # adjust the wlan power based on RSSI signal
                if rssi > -60:
                    txpower = 5     # ~5 dBm
                elif rssi > -70:
                    txpower = 10    # ~10 dBm
                elif rssi > -80:
                    txpower = 15    # ~15 dBm
                else:
                    txpower = 20    # ~20 dBm  (max)
                
                # set the flag printout False
                printout=False
                
                # set the wlan transmission power accordingly
                txpower = self._set_wlan_power(txpower=txpower, printout=printout)
                
                # small delay
                sleep_ms(20)
            
            # returns the rssi and txpower for feedback
            return rssi, txpower
        
        # case the wlan object is None
        else:
            return False, False
            
        
        
    
                        
    
    def _set_wlan_power(self, txpower=20, printout=True):
        """Set the wlan transmission power, default is max (20dB)."""
        try:
            if self.wlan is not None:
                self.wlan.config(txpower=txpower)
                if config.DEBUG and printout:
                    if txpower == 20:
                        print("[WIFI]     set wlan tx power to max (20dB)")
                    else:
                        print(f"[WIFI]     set wlan tx power to {txpower} dB)")
                return txpower
        
        except Exception as e:
            # feedback is printed to the terminal
            if config.DEBUG:
                print(f"[ERROR]    issue at wlan tx power setting: {e}")
            return False
    
    
    
    def _disconnect_wlan(self):
        """Disconnect the wlan from the modem or router."""
        
        # fix sleep time (in ms) while checking for the radio di disconnect and to deactivate
        sleep_for_ms = 10
        
        # counter, later used to escape the while-loop in case it gets stuck
        times = 0
        
        if self.wlan.isconnected():
            
            # send the disconnection comand to slan module
            self.wlan.disconnect()
        
            # while loop until wlan is connected
            while self.wlan.isconnected():
                
                # feed the wdt
                self.feed_wdt(label="disable_wifi_1")
                
                # sleep the fict amount of time
                sleep_ms(sleep_for_ms)
                
                # increase the counter
                times += 1
                
                # interrup the while loop in case of 200 (or more) iterations
                if times >= 200:
                    break
        return True
    
    
    
    def _deactivate_wlan(self):
        """Deactivate the wlan."""
        
        # reset the counter, later used to escape the while-loop in case it gets stuck
        times = 0
        
        # case the wlan is active
        if self.wlan.active():
            
            # send the disactivation comand to the wlam module
            self.wlan.active(False)
            
            # while loop until wlan is active
            while self.wlan.active():
                
                # feed the wdt
                self.feed_wdt(label="disable_wifi_2")
                
                # sleep the fict amount of time
                sleep_ms(sleep_for_ms)
                
                # increase the counter
                times += 1
                
                # interrup the while loop in case of 200 (or more) iterations
                if times >= 200:
                    break
        return True
    
    
    
    
    def disable_wifi(self, printout=True):
        """Function to disable the wlan module, to save energy and to enable lightsleep"""
        
        # time reference
        t_start_ms = ticks_ms()
        
        # disconnect the wlan from the modem/router
        ret = self._disconnect_wlan()
        
        # deactivate the wlan
        ret = self._deactivate_wlan()

        if config.DEBUG and printout:
            print("[DEBUG]    Disabled the WLAN")
        
        # return the time (in ms) needed to disable the wlan
        return ticks_diff(ticks_ms(), t_start_ms)

    
    
    
    async def get_ntp_servers_ip(self, repeats=1, blocking=True, internet_check=False):
        """Resolve NTP servers asynchronously using aiodns."""
        
        # force garbage collection
        gc.collect()
        
        if config.DEBUG:
            if internet_check:
                print("[DEBUG]    checking internet availability")
            else:
                print("\n[DEBUG]    DNS resolution for NTP servers")
            
        aiodns.timeout_ms = 5000      # timeout for the asyncio task (in ms)
        sleep_for_ms = 500            # sleeping time in between sequential attempts
        ntp_servers_ip = {}           # empty dictionary to store NTP servers and their IP
        
        # iterate for the repeats passed ar argument
        for repeat in range(repeats):
            
            # feed the wdt
            self.feed_wdt(label="repeat DNS resolution")
            
            # iterate over the NTP servers defined in the config.py
            for server in config.NTP_SERVERS:
                
                # force garbage collection
                gc.collect()
                
                if config.DEBUG:
                    t_ref_ms = ticks_ms()

                try:
                    # feed the wdt
                    self.feed_wdt(label="try DNS resolution")
                    
                    # calls the asynchronous DNS resolver function
                    addr_info = await aiodns.getaddrinfo(server, 123)  # non-blocking dns_timeout_s)  # timeout in seconds
                    
                    # case of DNS result
                    if addr_info:
                        
                        # IP of the server is gathered from the addr_info list and stored in the dict (key is the server)
                        ntp_servers_ip[server] = addr_info[0][-1]
                        
                        # case the passed argument internet_check is True
                        if internet_check:
                            # the first IP is returned (proving internet accessibility)
                            return ntp_servers_ip
                        
                        if config.DEBUG:
                            print(f"[DEBUG]    server {server} IP: {addr_info[0]}, resolved in {ticks_diff(ticks_ms(), t_ref_ms)} ms")
                
                except asyncio.TimeoutError:
                    # feedback is printed to the terminal
                    if config.DEBUG:
                        print(f"[TIMEOUT]    {server} on DNS resolution")
                
                except Exception as e:
                    # feedback is printed to the terminal
                    if config.DEBUG:
                        print(f"[ERROR]    {server} on DNS resolution: {e}")
                
                # case the function is called as non-blocking and at least one NTP server IP is resolved
                if not blocking and len(ntp_servers_ip) > 0:
                    # iteration over NTP servers is stopped
                    break
            
            # case all IP has bee resolved for all the NTP servers
            if len(ntp_servers_ip) == self.num_ntp_servers:
                # the dictionary of the servers and IPs is returned
                return ntp_servers_ip
            
            # case the function is called as non-blocking and at least one NTP server IP is resolved
            if not blocking and len(ntp_servers_ip) > 0:
                # iteration over repeats is stopped
                break
            # case function is called as blocking and not gathered still not one IP resolved
            else:
                # feed the wdt
                self.feed_wdt(label="get coro and task for DNS")
                
                # waiting time in between repeats (over the same servers)
                sleep_ms(sleep_for_ms) 
        
        # after all the iteration over NTP servers and repetitions
        
        # case the dict is still empty
        if len(ntp_servers_ip) == 0:
            # feedback is printed to the terminal
            if config.DEBUG:
                print("[ERROR]    All NTP servers failed to resolve DNS. Check your network connection.")
            # return None
            return None
        
        # case the dict is not empty it gets returned
        return ntp_servers_ip

    
    
    
    async def refresh_ntp_ip(self, current_ticks_ms, last_ntp_server_ip_update, ntp_servers_ip, blocking=False):
        """Function to get again the IP resolved."""
        
        # time reference
        t_start_ms = ticks_ms()

        # force garbage collection
        gc.collect()
        
        # feed the wdt
        self.feed_wdt(label="DNS resolution refresh")
        
        if config.DEBUG:
            print("[DEBUG]    refreshing the NTP servers IPs ...")
        
        # previous NTP servers dict {servers:IP} is stored for later comparison
        last_ntp_servers_ip = ntp_servers_ip
        
        # set the minimum number of servers (at least 1, or 60% of the previously found)
        min_num_servers = round(0.6 * self.num_ntp_servers) if self.num_ntp_servers > 1 else 1
        
        # call the function to get the NTP servers dict {servers:IP}
        ntp_servers_ip = await self.get_ntp_servers_ip(repeats=3, blocking=blocking)
        
        # case the function is called as non-blocking (typical case)
        if not blocking:
            if config.DEBUG:
                print(f"[DEBUG]    list of NTP servers IPs got updated, in {ticks_diff(ticks_ms(), t_start_ms)} ms")
            
            # return the NTP servers dict {servers:IP} and the time
            return ntp_servers_ip, ticks_ms()
        
        # case the function is called as blocking (no the typical case)
        elif blocking:
            
            # defines the number of attempts
            attempts = 3
            
            # iterate for the number of attempts
            for attempt in range(attempts):
                
                # force garbage collection
                gc.collect()
                
                # feed the wdt
                self.feed_wdt(label="iterates DNS resolution")
                
                # call the function to get the NTP servers dict {servers:IP}, by passing the number of attempts
                ntp_servers_ip = await self.get_ntp_servers_ip(repeats=3, blocking=blocking)
                
                # case of enough NTP servers IP resolved
                if len(ntp_servers_ip) >= min_num_servers:
                    if config.DEBUG:
                        print(f"[DEBUG]    list of NTP servers IPs got updated, in {ticks_diff(ticks_ms(), t_start_ms)} ms")
                    
                    # return the NTP servers dict {servers:IP} and the time
                    return ntp_servers_ip, ticks_ms()
                
                # case of not enough NTP servers IP resolved, sleep time in between attempts
                sleep_ms(500)
        
        if config.DEBUG:
            print(f"[ERROR]   could not resolve the DNS of NTP servers, out of {attempts+1} attempts")
            print("[ERROR]   the previous servers'IP will be used")
        
        # in case DNS resolution fails, return the previous list of NTP servers IPs and time reference
        # This is not necessarily a safe approach, in the case the NTP servers have changed their IPs
        return last_ntp_servers_ip, ticks_ms()

    
    
    async def get_ntp_time(self, ntp_servers_ip, attempts=config.NTP_SERVER_ATTEMPTS, max_ntp_offset_ms=config.MAX_NTP_OFFSET_MS, blocking=False):
        """
        NTP sync with timestamp calculations and Wi-Fi management.
        The returned time-related variables (epoch_s, epoch_ms) have a meaning when linked to tick_ms time reference,
        (sync_ticks_ms), being the tick of the internal oscillator at the NTP data receival, corrected by offset_ms.
        The NTP server is inquired NTP_SERVER_ATTEMPTS times, and the reply with smallest latency is used.
        In the case the NTP time offset is > MAX_NTP_OFFSET_MS then the internal mcu RTC gets updated
        The different NTP servers are inquired in the provided order.
        The first server replying to the inquiry will be used, the other servers are for backup.
        """
        
        # time reference
        t_start = ticks_ms()
        
        if config.DEBUG:
            print()
        
        # flag for NTP sync outcome is initially set False
        self.ntp_bool = False
        
        # feed the wdt
        self.feed_wdt(label="get_ntp_time_1")
        
        # force garbage collection
        gc.collect()
        
        # minimum number of NTP sync attempts
        MIN_NTP_SERVER_ATTEMPTS = 3
        
        # ensuring at least minimum number of NTP sync attempts as number of NTP sync
        attempts = MIN_NTP_SERVER_ATTEMPTS if attempts < MIN_NTP_SERVER_ATTEMPTS else attempts
        
        # relevant variab;es are initially set to None
        epoch_s, epoch_ms, sync_ticks_ms, offset_ms, rnd_latency_ms = None, None, None, None, None
        
        # min_latency_ms is set initially very hight, to later choose the NTP sync with the lowest latency
        min_latency_ms = 100000
        
        # 'best', initially set to 0, is the dict key holding info of the NTP with lowest latency
        best = 0
        
        # ensure wlan is active and connected
        await self.ensure_wlan(blocking=blocking)
        
        if self.wlan is None:
            if config.DEBUG:
                print("[ERROR]    NTP sync failed due to WiFi issues\n")
            return None, None, None, None, None

        # iteration over the listes NTp servers
        for server in config.NTP_SERVERS:
            
            # feed the wdt
            self.feed_wdt(label="get_ntp_time_2")
            
            # case no ip for that server (server not reached after booting)
            if server not in ntp_servers_ip.keys():
                continue
            
            # case ntp sync was successfull
            if self.ntp_bool:
                break
            
            # retrive the ntp server address (IP and PORT)
            addr = ntp_servers_ip[server]
            
            if config.DEBUG:
                print(f"[NTP]      connecting to server {server} at IP {addr[0]} PORT {addr[1]}")
            
            try:
                # create NTP packet
                NTP_QUERY = bytearray(48)
                NTP_QUERY[0] = 0x1B  # LI=0, VN=3, Mode=3 (client)
                
                # create UDP socket
                s = socket(AF_INET, SOCK_DGRAM)
                
                # timeout at ESP32-S3 (2 secs) to see actions on the socket
                s.settimeout(2)
                
                # list to store NTP relevant data (offset_ms, rnd_latency_ms, t4_ms, epoch_s, epoch_fract_ms)
                ntp_results = []  
                
                # index for the fastest NTP sync, initially set to zero.
                index = 0
                
                # iterating over the (passed) attempts
                for attempt in range(attempts):
                    
                    # feed the wdt
                    self.feed_wdt(label="get_ntp_time_2")
                    
                    try:
                        # get current epoch time with nanosecond precision for t1
                        t_ns = time_ns()
                        secs = t_ns // 1_000_000_000
                        nanos = t_ns % 1_000_000_000
                        
                        # convert t1 to NTP format
                        t1_ntp_secs = secs + self.ntp_delta
                        t1_ntp_frac = int((nanos * (1 << 32)) // 1_000_000_000)
                        t1_ms = t_ns // 1_000_000  # convert ns to ms
                        
                        # prepare packet for NTP query with included timestamp
                        pack_into("!II", NTP_QUERY, 40, t1_ntp_secs, t1_ntp_frac)
                        
                        # feed the wdt
                        self.feed_wdt(label="get_ntp_time_3")
                        
                        # send packet to NTP server
                        s.sendto(NTP_QUERY, addr)
                        
                        # feed the wdt
                        self.feed_wdt(label="get_ntp_time_4")
                        
                        try:
                            # receive packet from NTP server
                            msg = s.recv(48)
                            error = False
                        except Exception as e:
                            error = True
                            continue  # skip to next attempt
                        
                        # record the receive time of NTP packet (t4)
                        t4_ns = time_ns()            # t4 in nanoseconds
                        tick_ms = ticks_ms()         # time tick (in ms)
                        t4_ms = t4_ns // 1_000_000   # t4 in milliseconds
                        
                        # feed the wdt
                        self.feed_wdt(label="get_ntp_time_5")  # feed the wdt
                        
                        # extract NTP server timestamps
                        t2_secs, t2_frac = unpack("!II", msg[32:40])  # NTP server receive time
                        t3_secs, t3_frac = unpack("!II", msg[40:48])  # NTP server transmit time 
                        
                        # convert server timestamps to milliseconds (rounded for precision)
                        t2_ms_tot = (t2_secs - self.ntp_delta) * 1000 + round(t2_frac * 1000 / (1 << 32))
                        t3_ms_tot = (t3_secs - self.ntp_delta) * 1000 + round(t3_frac * 1000 / (1 << 32))
                        
                        # calculate offset_ms and rnd_latency_ms (see https://en.wikipedia.org/wiki/Network_Time_Protocol)
                        rnd_latency_ms = (t4_ms - t1_ms) - (t3_ms_tot - t2_ms_tot)
                        offset_ms = ((t2_ms_tot - t1_ms) + (t3_ms_tot - t4_ms)) / 2
                        
                        # get server's transmit time (ground truth)
                        server_time_s = t3_secs - self.ntp_delta
                        server_time_ms = round(t3_frac * 1000 / (1 << 32))
                        
                        # add half the network rnd_latency_ms for better accuracy
                        epoch_ms = server_time_ms + (rnd_latency_ms / 2)
                        epoch_s = server_time_s + int(epoch_ms // 1000)
                        epoch_fract_ms = epoch_ms % 1000
                        
                        # case of very large offset: This is always the case for the real first positive NTP
                        # This case is then used to set the mcu RTC.
                        # By doing so, the next NTP syncs will have a smaller offset being also meaninfull.
                        if abs(offset_ms) > max_ntp_offset_ms:
                            
                            # from epoch (secs) to UTC (time.struct_time obj)
                            time_tuple = gmtime(epoch_s)        
                            
                            # set the rtc with the just obtained UTC time 
                            # note: the time zone will only applied to the displayed time
                            self.rtc.datetime((time_tuple[0], time_tuple[1], time_tuple[2],
                                               time_tuple[6], time_tuple[3], time_tuple[4],
                                               time_tuple[5], int(epoch_fract_ms*1000)
                                               ))
                            
                            if config.DEBUG:
                                print(f"[NTP]      NTP absolute offset (ms): {abs(offset_ms)} vs max acceptable of {max_ntp_offset_ms}")
                                print( "[NTP]      necsssary to updated the mcu internal RTC ....")
                                print(f"[NTP]      mcu RTC reset to UTC time: {epoch_s}.{int(epoch_fract_ms):03d}")
                                print( "[NTP]      note the time zome will only be applied to the displayed time")
                        
                        # case of an acceptable offset
                        else:
                            # store result for later evaluation
                            ntp_results.append({
                                "latency_ms": rnd_latency_ms,
                                "offset_ms": offset_ms,
                                "epoch_s": epoch_s,
                                "epoch_fract_ms": epoch_fract_ms,
                                "sync_ticks_ms": tick_ms,
                                "t4_ms": t4_ms
                            })
                            
                            # track the NTP pool with lowest latency
                            if abs(rnd_latency_ms) < min_latency_ms:
                                min_latency_ms = abs(rnd_latency_ms)
                                best = index
                            index += 1
                        
                        # feed the wdt
                        self.feed_wdt(label="get_ntp_time_6")   # feed the wdt
                        
                        # case of error at the packet received
                        if error:
                            try:
                                # case of quick test, an error is saved to a text file
                                if config.QUICK_CHECK:
                                    with open(config.NETWORKS_LOG_FILE_NAME,"a") as f:
                                        f.write(f"NTP_RECV_ERROR,{time()},{repr(e)}\n")
                            except Exception as e:
                                # feedback is printed to the terminal
                                if config.DEBUG:
                                    print(f"[ERROR]    log error: {e}")
                                
                    # case the or error in the attempt to comunicate with NTP server 
                    except Exception as e:
                        if s:
                            # feed the wdt
                            self.feed_wdt(label="get_ntp_time_4")
                            
                            # the socket get closed
                            s.close()
                        
                        if config.DEBUG:
                            print(f"[NTP]      sync attempt {attempt+1} of {attempts} failed: {e}")
                
                # the socket get closed (in this case not because of an error)
                s.close()
                
                # case the lightsleep usage is set True, the radio must be set off
                # anyway, the sooner the better for energy
                if config.LIGHTSLEEP_USAGE:
                    if self.wlan.active():
                        self.disable_wifi()
                
                # feed the wdt
                self.feed_wdt(label="get_ntp_time_7")
                
                # case ntp_results got populated
                if ntp_results:
                    # epoch_s is the NTP time referred to the sync_ticks_ms moment
                    # defined as the internal ticks_ms when NTP was received
                    epoch_ms =  round(ntp_results[best]["t4_ms"] + offset_ms)
                    sync_ticks_ms =   ntp_results[best]["sync_ticks_ms"]
                    rnd_latency_ms =  ntp_results[best]["latency_ms"]
                    offset_ms =       ntp_results[best]["offset_ms"]
                    epoch_s =         ntp_results[best]["epoch_s"]
                    
                    # normalize offset to keep abs(offset_ms) ≤ 500 ms
                    if abs(offset_ms) >= 1000:
                        delta_s = int(offset_ms // 1000)
                        epoch_s += delta_s
                        offset_ms -= delta_s * 1000

                    # fractional part of offset_ms.
                    # It is convenient a sub half-second offset, by eventually altering the seconds (epoch_s)
                    # This will allow a more precise rounding of the seconds (epoch_s)
                    if offset_ms > 500:
                        epoch_s += 1
                        offset_ms -= 1000
                    elif offset_ms < -500:
                        epoch_s -= 1
                        offset_ms += 1000
                    
                    # the effective fractional part of offset_ms
                    epoch_fract_ms = epoch_ms % 1000
                    
                    # flag for NTP sync outcome is set True (succeess)
                    self.ntp_bool = True
            
            # cse of expection (this relates to all the interaction with server in the iterator)
            except Exception as e:
                if config.DEBUG:
                    print(f"[ERROR]   sync failure with server {server}")
        
        # feed the wdt
        self.feed_wdt(label="get_ntp_time_8")
        
        # overall time to get the NTP sync
        tot_time_ms = ticks_diff(ticks_ms(), t_start)
        
        # case of quick test, some NTP timing related data is saved
        if config.QUICK_CHECK:
            try:
                # write the NTP 
                with open(config.NETWORKS_LOG_FILE_NAME, "a") as f:
                    f.write(f"NTP,{time()},{tot_time_ms}\n")
            except Exception as e:
                # feedback is printed to the terminal
                if config.DEBUG:
                    print(f"[ERROR]    log error: {e}")
        
        # feed the wdt
        self.feed_wdt(label="get_ntp_time_9")
        
        # case of a successfull NTP sync
        if self.ntp_bool:
            if config.DEBUG:
                print(f"[NTP]      NTP sync success (best sample) taking overall {tot_time_ms} ms ")
                print(f"[NTP]      NTP latency round-trip time (ms) {rnd_latency_ms}")
                print(f"[NTP]      NTP offset (ms) {offset_ms}")
            
            # returns the relevant NTP data (note sync_ticks_ms = NTP t4)
            return epoch_s, int(epoch_fract_ms), sync_ticks_ms, rnd_latency_ms, offset_ms
        
        # case of a failed NTP sync
        else:
            if config.DEBUG:
                print("[ERROR]   NTP sync failed with all servers\n")
            
            # returns all None
            return None, None, None, None, None
    
    
    
    
    async def upload_files(self, file_list, dest_fname_list, blocking):
        
        if not config.PUSH_FILE_ENABLED:
            return

        # feed the wdt
        self.feed_wdt(label="upload_file_1")
        
        # ensure wlan active and connected
        await self.ensure_wlan(blocking=blocking)
        
        # iterate over the filename list
        for idx, filepath in enumerate(file_list):
            
            # retrieve the destination filename from the list (same element order)
            filename_on_server = dest_fname_list[idx]
            
            # label for the wdt
            label = f"Preparing to push file {filepath}"
            
            # feed the wdt
            self.feed_wdt(label=label)
            
            # get the text content from the file
            with open(filepath, 'rb') as f:
                data = f.read()
            
            # prepare the header dict for file transmition
            headers = {'Content-Type': 'text/csv', 'X-Filename': filename_on_server }
            
            if config.DEBUG:
                print(f"[DEBUG]    Uploading file {filepath} to server, with destination filename {filename_on_server}")
                
                # time reference, just informative for the transmition time
                t_start_ms = ticks_ms()
            
            # string variable to store the server reply
            server_text = ""
            
            # flag to track file_sent (success or failure)
            file_sent = False
            
            try:
                # feed the wdt
                self.feed_wdt(label="upload_file_3")
                
                # send the file to the server
                response = post(config.SERVER_URL, data=data, headers=headers, timeout=5)
                
                # string reply from the server
                server_text = response.text
                
                # feed the wdt
                self.feed_wdt(label="upload_file_4")
                
                if config.DEBUG:
                    print(f"[DEBUG]    Server response: {response.text}")
                
                # closes the connection with the server
                response.close()
                
                # set the file_sent as True (succees)
                file_sent = True
            
            except Exception as e:
                response = f"ERROR: {e}"
                
                # set the file_sent as False (failure)
                file_sent = False
            
            if config.DEBUG:
                duration_ms = ticks_diff(ticks_ms(), t_start_ms)
                print(f"[DEBUG]    Upload {'OK' if file_sent else 'FAILED'} in {duration_ms} ms –-> {server_text}")
            
            # case of quick test, some info is saved to a text file
            if config.QUICK_CHECK:
                try:
                    with open(config.NETWORKS_LOG_FILE_NAME, "a") as f:
                        f.write(f"UPLOAD,{time()},{duration_ms},{'OK' if file_sent else 'FAILED'}\n")
                except Exception as e:
                    # feedback is printed to the terminal
                    if config.DEBUG:
                        print(f"[ERROR]    Log error: {e}")
                
            # feed the wdt
            self.feed_wdt(label="upload_file_4")
            
            # sleep time in between files
            sleep_ms(200)
        
        # case the lightsleep is set True, the radio is set OFF (save energy, enable lighsleep)
        if config.LIGHTSLEEP_USAGE:
            if self.wlan.active():
                self.disable_wifi()

