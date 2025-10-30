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
    def __init__(self, wdt_manager, try_open_networks):
        self.wdt_manager = wdt_manager
        self.try_open_networks = try_open_networks
        
        self.num_ntp_servers = len(config.NTP_SERVERS)
        self.ntp_delta = config.NTP_DELTA
        
        self.wifi_bool = False
        self.ntp_bool = False
        self.wlan = None
        
        networks = self.load_wifi_config()
        self.ssid_list, self.passw_list = self.get_network_info(networks)
        
        self.secrets = True
        if len(self.ssid_list)==0 or len(self.passw_list)==0 or len(self.ssid_list) != len(self.passw_list):
            print("\n[ERROR]     no secrets.json or empty file")
            self.secrets = False
            

    
    
    def feed_wdt(self, label=""):
        """use the WDT manager instead of global WDT"""
        self.wdt_manager.feed(label)

    
    
    def load_wifi_config(self, filename="lib/config/secrets.json"):
        self.feed_wdt(label="load_wifi_config")
        
        try:
            with open(filename, 'r') as f:
                config_data = json.load(f)
            return config_data["networks"]
        except Exception as e:
            print(f"error loading config: {e}")
            return []

    
    
    def get_network_info(self, networks):
        self.feed_wdt(label="get_network_info")
        
        if not networks:
            print("no WiFi networks configured, check the file: secrets.json")
        
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
        self.feed_wdt(label="scan_open_networks")
        print("[WiFi]     scanning for Wi-Fi networks...")
        
        # ensure WLAN is active for scanning
        if self.wlan is None:
            self.wlan = WLAN(STA_IF)
        if not self.wlan.active():
            self.wlan.active(True)
            sleep_ms(500)
        
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
        print("[WiFi]     found {} open network(s).".format(len(open_aps)))
        for i, a in enumerate(open_aps):
            print("[WiFi]   {:2d}. SSID: {!r}, RSSI: {}, channel: {}".format(i+1, a['ssid'], a['rssi'], a['channel']))
        
        return open_aps

    
    
    async def is_internet_available(self, attempts=3, blocking=True):
        """check internet connectivity using the DNS resolution functionality"""
        
        for attempt in range(attempts):
            self.feed_wdt(label="is_internet_available")
            
            try:
                ntp_servers_ip = await self.get_ntp_servers_ip(internet_check=True)
                
                if ntp_servers_ip and len(ntp_servers_ip) > 0:
                    print(f"[INTERNET] internet connectivity detected")
                    return True
                    
            except Exception as e:
                print(f"[INTERNET] internet connectivity attempt {attempt + 1} failed: {e}")
            
            if attempt < attempts - 1:
                sleep_ms(1000)
        
        print("[INTERNET] no internet connectivity detected")
        return False

    
    
    def connect_to_open_wifi(self, ssid, max_attempts=2):
        """attempt to connect to an open WiFi network"""
        self.feed_wdt(label="connect_to_open_wifi")
        
        if self.wlan is None:
            self.wlan = WLAN(STA_IF)
        
        print(f"[WIFI]     trying to connect to open network: {ssid} ...")
        
        for attempt in range(max_attempts):
            t_ref_ms = ticks_ms()
            
            # ensure we start fresh for each attempt
            if self.wlan.isconnected():
                self.wlan.disconnect()
                sleep_ms(200)
            
            self.wlan.active(False)
            sleep_ms(500)
            self.wlan.active(True)
            
            # connect to open network (no password)
            self.wlan.connect(ssid, "")
            
            # wait for connection with 15 secs timeout
            timeout = 0
            while not self.wlan.isconnected() and timeout < 15:
                self.feed_wdt(label="connect_to_open_wifi_wait")
                sleep_ms(500)
                timeout += 1
            
            if self.wlan.isconnected():
                print(f"[WIFI]     connected to open network {ssid} in "
                      f"{ticks_diff(ticks_ms(), t_ref_ms)} ms")
                print(f"[WIFI]     IP address: {self.wlan.ifconfig()[0]}\n")
                self.wifi_bool = True
                return True
            
            print(f"[WIFI]     failed to connect to {ssid}, attempt {attempt + 1}")
        
        return False

    
    
    def connect_to_wifi(self, blocking=True):
        """
        attempt to connect to one of the SSIDs in ssid_list.
        tries each SSID/password pair multiple times, with watchdog feeds.
        returns a WLAN object on success.
        """
        self.wifi_bool = False
        self.wlan = WLAN(STA_IF)

        # always start from a known state
        self.wlan.active(False)
        sleep_ms(500)
        self.wlan.active(True)
        
        attempts = 1 if not blocking else 5
        for attempt in range(attempts):   # outer retry loop
            for priority, ssid in enumerate(self.ssid_list):
                t_ref_ms = ticks_ms()
                self.feed_wdt(label="connect_to_wifi_1")

                password = self.passw_list[priority]
                print(f"\n[WIFI]     trying to connect to: {ssid} ...")

                # ensure we start fresh for each AP
                if self.wlan.isconnected():
                    self.wlan.disconnect()
                    sleep_ms(200)

                self.wlan.active(False)
                sleep_ms(500)
                self.wlan.active(True)

                self.wlan.connect(ssid, password)

                # wait for connection with 15 secs timeout
                timeout = 0
                while not self.wlan.isconnected() and timeout < 15:
                    self.feed_wdt(label="connect_to_wifi_2")
                    sleep_ms(500)
                    timeout += 1

                if self.wlan.isconnected():
                    print(f"[WIFI]     connected to {ssid} in "
                          f"{ticks_diff(ticks_ms(), t_ref_ms)} ms")
                    print(f"[WIFI]     IP address: {self.wlan.ifconfig()[0]}\n")
                    self.wifi_bool = True
                    return self.wlan
                else:
                    print(f"[WIFI]     failed to connect to {ssid}, attempt {attempt}")

            # end for ssid_list
            
            # if configured networks failed, try open networks as fallback
            if self.try_open_networks and not self.wifi_bool:
                print("\n[WIFI]     configured networks failed, trying open networks...")
                open_networks = self.scan_open_networks()
                for open_net in open_networks[:3]:  # try top 3 strongest open networks
                    if self.connect_to_open_wifi(open_net['ssid']):
                        self.wifi_bool = True
                        return self.wlan
            
            attempt += 1

            if not blocking:
                break
            else:
                self.feed_wdt(label="connect_to_wifi_3")

        # if all attempts exhausted
        if not blocking:
            print("[WIFI]     could not connect to any available network, ignored")
            return None
        else:
            print("\n[ERROR]    could not connect to any available network, stopping the code")
            return None

    
    
    
    async def ensure_wlan(self, blocking=True):
        """async version that uses the async internet check"""
        
        # case wlan exists yet not active
        if self.wlan is not None and not self.wlan.active():
            # activate the wifi: some routers need a full re-establish
            self.wlan.active(True)
        
        # case the wlan does not exist or is not active or is not connected 
        if self.wlan is None or not self.wlan.active() or not self.wlan.isconnected():
            self.wlan = self.connect_to_wifi(blocking=blocking)
            if self.wlan is not None:
                self.wlan.active(True)
        
        # check if internet connection is ok using async method
        if not await self.is_internet_available(blocking=blocking):
            print("[ERROR]   internet is not available")
            if not self.wlan.isconnected() and blocking:
                print("[ERROR]   WiFi connection lost, attempting to reconnect ...")
                self.wlan = self.connect_to_wifi(blocking=blocking)
        
        return self.wlan

    
    
    
    def disable_wifi(self):
        sleep_for_ms = 50
        times = 0
        t_start_ms = ticks_ms()
        if self.wlan.isconnected():
            self.wlan.disconnect()
            while self.wlan.isconnected():
                self.feed_wdt(label="disable_wifi_1")
                sleep_ms(sleep_for_ms)
                times += 1
                if times >= 200:
                    break
        
        times = 0
        if self.wlan.active():
            self.wlan.active(False)
            while self.wlan.active():
                self.feed_wdt(label="disable_wifi_2")
                sleep_ms(sleep_for_ms)
                times += 1
                if times >= 200:
                    break
        
        if config.DEBUG:
            print(f"[DEBUG]    Disabled the WLAN")
            
        return ticks_diff(ticks_ms(), t_start_ms)

    
    
    
    async def get_ntp_servers_ip(self, repeats=1, blocking=True, internet_check=False):
        """resolve NTP servers asynchronously using aiodns."""
        gc.collect()
        
        if config.DEBUG:
            if internet_check:
                print(f"[DEBUG]    checking internet availability")
            else:
                print(f"[DEBUG]    DNS resolution for NTP servers")
            
        aiodns.timeout_ms = 5000      # timeout for the asyncio task (in ms)
        sleep_for_ms = 500            # sleeping time in between sequential attempts
        ntp_servers_ip = {}
        
        for repeat in range(repeats):
            self.feed_wdt(label="repeat DNS resolution")
            for server in config.NTP_SERVERS:
                gc.collect()
                if config.DEBUG:
                    t_ref_ms = ticks_ms()

                try:
                    self.feed_wdt(label="try DNS resolution")
                    
                    addr_info = await aiodns.getaddrinfo(server, 123)  # non-blocking dns_timeout_s)  # timeout in seconds
                    if addr_info:
                        ntp_servers_ip[server] = addr_info[0][-1]
                        
                        if internet_check:
                            return ntp_servers_ip
                        
                        if config.DEBUG:
                            print(f"[DEBUG]    server {server} IP: {addr_info[0]}, resolved in {ticks_diff(ticks_ms(), t_ref_ms)} ms")
                
                except asyncio.TimeoutError:
                    print(f"[TIMEOUT]    {server} on DNS resolution")
                
                except Exception as e:
                    print(f"[ERROR]    {server} on DNS resolution: {e}")
                
                if not blocking and len(ntp_servers_ip) > 0:
                    break
            
            if len(ntp_servers_ip) == self.num_ntp_servers:
                return ntp_servers_ip
  
            if not blocking and len(ntp_servers_ip) > 0:
                break
            else:
                self.feed_wdt(label="get coro and task for DNS")
                sleep_ms(sleep_for_ms) # waiting time in between repeats (over the same servers)
            
        if len(ntp_servers_ip) == 0:
            print("all NTP servers failed to resolve. check your network connection.")
            return None
        
        return ntp_servers_ip

    
    
    
    async def refresh_ntp_ip(self, current_ticks_ms, last_ntp_server_ip_update, ntp_servers_ip, blocking=True):
        t_start_ms = ticks_ms()

        gc.collect()
        self.feed_wdt(label="DNS resolution refresh")
        
        if config.DEBUG:
            print(f"[DEBUG]    refreshing the NTP servers IPs ...")
        
        last_ntp_servers_ip = ntp_servers_ip
        min_num_servers = round(0.6 * self.num_ntp_servers) if self.num_ntp_servers > 1 else 1
        ntp_servers_ip = await self.get_ntp_servers_ip(repeats=3, blocking=blocking)

        if not blocking:
            if config.DEBUG:
                print(f"[DEBUG]    list of NTP servers IPs got updated, in {ticks_diff(ticks_ms(), t_start_ms)} ms")
            return ntp_servers_ip, ticks_ms()
        
        elif blocking:
            attempts = 3

            for attempt in range(attempts):
                gc.collect()
                self.feed_wdt(label="iterates DNS resolution")
                ntp_servers_ip = await self.get_ntp_servers_ip(repeats=3, blocking=blocking)
                if len(ntp_servers_ip) >= min_num_servers:
                    if config.DEBUG:
                        print(f"[DEBUG]    list of NTP servers IPs got updated, in {ticks_diff(ticks_ms(), t_start_ms)} ms")
                    return ntp_servers_ip, ticks_ms()
                sleep_ms(500)
        
        if config.DEBUG:
            print(f"[ERROR]   could not resolve the DNS of NTP servers, out of {attempts+1} attempts")
            print(f"[ERROR]   the previous servers'IP will be used")
        
        # in case DNS resolution fails, return the previous list of NTP servers IPs and time reference
        return last_ntp_servers_ip, ticks_ms()

    
    
    async def get_ntp_time(self, ntp_servers_ip, attempts=config.NTP_SERVER_ATTEMPTS, max_ntp_offset_ms=config.MAX_NTP_OFFSET_MS, blocking=False):
        """
        NTP sync with timestamp calculations and Wi-Fi management
        the returned time-related variables (epoch_s, epoch_ms) have a meaning when linked to tick_ms time reference,
        (sync_ticks_ms) being the tick of the internal oscillator at the NTP data receival corrected by offset_ms.
        the NTP server is inquired NTP_SERVER_ATTEMPTS times, and the reply with smallest latency is used.
        in the case the NTP time offset is > MAX_NTP_OFFSET_MS then the internal RTC gets updated
        the different NTP servers are inquired in the provided order.
        the first server replying to the inquiry will be used, the other servers are for back up.
        """
        
        t_start = ticks_ms()
        
        self.ntp_bool = False
        
        self.feed_wdt(label="get_ntp_time_1")
        gc.collect()
        
        MIN_NTP_SERVER_ATTEMPTS = 3 # minimum number of NTP sync attempts
        
        # ensuring at least minimum number of NTP sync attempts as number of NTP sync
        attempts = MIN_NTP_SERVER_ATTEMPTS if attempts < MIN_NTP_SERVER_ATTEMPTS else attempts
        
        epoch_s, epoch_ms, sync_ticks_ms, offset_ms, rnd_latency_ms = None, None, None, None, None

        min_latency_ms = 100000
        best = 0
        
        # ensure wlan is active and connected
        await self.ensure_wlan(blocking=blocking)
        
        if self.wlan is None:
            if config.DEBUG:
                print("[ERROR]    NTP sync failed due to WiFi issues\n")
            return None, None, None, None, None

        
        for server in config.NTP_SERVERS:
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
                s.settimeout(2)
                
                # --- new section: collect all results for later selection ---
                ntp_results = []  # store (offset_ms, rnd_latency_ms, t4_ms, epoch_s, epoch_fract_ms)
                
                index = 0
                for attempt in range(attempts):
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
                        
                        # record receive time of NTP packet
                        t4_ns = time_ns()            # t4 in nanoseconds
                        tick_ms = ticks_ms()         # time tick (in ms)
                        t4_ms = t4_ns // 1_000_000   # t4 in milliseconds
                        
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
                        
                        # the first positive NTP sync is used to set a first RTC value.
                        # the following NTP syncs will have a more meaninfull offset
                        if abs(offset_ms) > max_ntp_offset_ms:  # case time offset_ms from NTP not acceptable
                            # from epoch (secs) to UTC (time.struct_time obj)
                            time_tuple = gmtime(epoch_s)        
                            
                            # set the rtc with the just obtained UTC time 
                            # note: the time zone will only applied to the displayed time
                            rtc = RTC()
                            rtc.datetime((time_tuple[0], time_tuple[1], time_tuple[2],
                                          time_tuple[6], time_tuple[3], time_tuple[4],
                                          time_tuple[5], int(epoch_fract_ms*1000)))
                            
                            if config.DEBUG:
                                print(f"[NTP]      NTP absolute offset (ms): {abs(offset_ms)} vs max acceptable of {max_ntp_offset_ms}")
                                print(f"[NTP]      necsssary to updated the internal RTC ....")
                                print(f"[NTP]      full RTC reset to UTC time: {epoch_s}.{int(epoch_fract_ms):03d}")
                                print(f"[NTP]      note the time zome will only be applied to the displayed time")
                        
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
                        
                        self.feed_wdt(label="get_ntp_time_6")   # feed the wdt
                        
                        if error:
                            with open(config.NETWORKS_LOG_FILE_NAME,"a") as f:
                                f.write(f"NTP_RECV_ERROR,{time()},{repr(e)}\n")
                    
                    except Exception as e:
                        if s:
                            self.feed_wdt(label="get_ntp_time_4")
                            s.close()
                        if config.DEBUG:
                            print(f"[NTP]      sync attempt {attempt+1} of {attempts} failed: {e}")
                
                s.close()    # closing the socket
                
                if config.LIGHTSLEEP_USAGE:
                    if self.wlan.active():
                        self.disable_wifi()
                
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

                    # fractional part of offset_ms
                    if offset_ms > 500:
                        epoch_s += 1
                        offset_ms -= 1000
                    elif offset_ms < -500:
                        epoch_s -= 1
                        offset_ms += 1000

                    epoch_fract_ms =   epoch_ms % 1000
                    self.ntp_bool = True
                    
            except Exception as e:
                if config.DEBUG:
                    print(f"[ERROR]   sync failure with server {server}")
        
        self.feed_wdt(label="get_ntp_time_8")
        
        tot_time_ms = ticks_diff(ticks_ms(), t_start)
        try:
            with open(config.NETWORKS_LOG_FILE_NAME, "a") as f:
                f.write(f"NTP,{time()},{tot_time_ms}\n")
        except Exception as e:
            print(f"log error: {e}")
        
        self.feed_wdt(label="get_ntp_time_9")
        
        if self.ntp_bool:
            if config.DEBUG:
                print(f"[NTP]      NTP sync success (best sample) taking overall {tot_time_ms} ms ")
                print(f"[NTP]      NTP latency round-trip time (ms) {rnd_latency_ms}")
                print(f"[NTP]      NTP offset (ms) {offset_ms}")
            
            if config.DEBUG:
                print()
            return epoch_s, int(epoch_fract_ms), sync_ticks_ms, rnd_latency_ms, offset_ms
        
        else:
            if config.DEBUG:
                print("[ERROR]   NTP sync failed with all servers\n")
            return None, None, None, None, None
    
    
    
    async def upload_files(self, file_list, dest_fname_list, blocking):
        
        if not config.PUSH_FILE_ENABLED:
            return

        self.feed_wdt(label="upload_file_1")
        
        # ensure wlan active and connected
        await self.ensure_wlan(blocking=blocking)
        
        for idx, filepath in enumerate(file_list):
            filename_on_server = dest_fname_list[idx]
            
            label = f"Preparing to push file {filepath}"
            self.feed_wdt(label=label)

            with open(filepath, 'rb') as f:
                data = f.read()
            
            headers = {
                'Content-Type': 'text/csv',
                'X-Filename': filename_on_server
                }
            
            if config.DEBUG:
                print(f"[DEBUG]    Uploading file {filepath} to server, with destination filename {filename_on_server}")
            
            server_text = ""
            success = False
            t_start_ms = ticks_ms()
            
            try:
                self.feed_wdt(label="upload_file_3")
                response = post(config.SERVER_URL, data=data, headers=headers, timeout=5)
                self.feed_wdt(label="upload_file_4")
                server_text = response.text
                if config.DEBUG:
                    print(f"[DEBUG]    Server response: {response.text}")
                response.close()
                success = True
            
            except Exception as e:
                response = f"ERROR: {e}"
                success = False
            
            duration_ms = ticks_diff(ticks_ms(), t_start_ms)
            print(f"[DEBUG]    Upload {'OK' if success else 'FAILED'} in {duration_ms} ms –-> {server_text}")
            
            try:
                with open(config.NETWORKS_LOG_FILE_NAME, "a") as f:
                    f.write(f"UPLOAD,{time()},{duration_ms},{'OK' if success else 'FAILED'}\n")
            except Exception as e:
                print(f"Log error: {e}")
                
            self.feed_wdt(label="upload_file_4")
        
            sleep_ms(200)

        if config.LIGHTSLEEP_USAGE:
            if self.wlan.active():
                self.disable_wifi()
