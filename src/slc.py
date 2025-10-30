"""
Andrea Favero 20251112


Self-Learning Clock (MicroPython)

More info at:
  https://github.com/AndreaFavero71/Self_Learning_Clock
  https://www.instructables.com/Self-Learning-Clock-SLC/


NTP is used to periodically discipline the clock.
The MCU’s internal clock interval (ticks counting) is compared with the one obtained via NTP,
allowing the system to learn its own drift and self-correct between synchronizations.
The internal timing mechanism itself is not altered by these corrections; instead, the
displayed time is adjusted to minimize deviation. This approach reduces time drift while
lowering the NTP synchronization frequency, thereby minimizing energy consumption.

The display refresh cadence is adapted so that the new time is updated when the
interpreted seconds fall between 0 and 5 of each minute.
Light-sleep duration is maximized to reduce power consumption in battery-operated clocks.
The code has been developed on a LilyGO T8 development board (ESP32-S3 based, with 8 MB PSRAM)

The used display is a Waveshare 4.2-inch (400×300) 4-grayscale e-paper Pico version:
https://www.waveshare.com/wiki/Pico-ePaper-4.2

(Optional) If predefined SSID/passwords are not available, or fail to connect, the code automatically
searches for open networks, check settings at config.py.




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


# import standard modules
from utime import ticks_ms, gmtime, time, sleep_ms, ticks_diff
from esp32 import NVS, mcu_temperature
from machine import lightsleep
from collections import deque
import uasyncio as asyncio
import sys, gc, bluetooth

# import SLC custom modules
from lib.config import config
from lib.lib_display.display import Display
from network_manager import NetworkManager
from time_manager import TimeManager
from battery_manager import Battery
from wdt_manager import WDTManager





class SelfLearningClock:
    def __init__(self, logo_time_ms):
        
        print()
        print("#" * 41)
        print("#  Clock started. Press Ctrl+C to stop  #")
        print("#" * 41)
        print()
        
        
        # check / make a folder
        self._make_folder("log")
        
        # initialize the module for time management
        self.time_mgr = TimeManager(config)
        
        # initialize WDT manager, before the modules where it is passed
        self.wdt_manager = WDTManager()
        
        # initialize display module, by also passing the WDT manager
        self.display = Display(wdt_manager = self.wdt_manager,
                               lightsleep_active = config.LIGHTSLEEP_USAGE,
                               battery = config.BATTERY,
                               debug = config.DEBUG,
                               logo_time_ms = logo_time_ms
                               )
        
        # initialize the network manager module, by also passing the WDT manager
        self.network_mgr = NetworkManager(self.wdt_manager, try_open_networks=config.OPEN_NETWORKS)

        # check if error from initializing the network manager
        if not self.network_mgr.secrets:
            self.display.text_on_logo("ERROR: SECRETS.JSON", x=-1, y=-1, show_time_ms=2000)
            sys.exit(1)
        
        # initialize the battery manager module, if set at config file
        if config.BATTERY:
            self.battery = Battery(debug=config.DEBUG)
        
        # initialize WDT after all components are initialized
        self.wdt_manager.initialize() 
        
        # initialize global variables
        self.smoothed_drift_ppm = 0
        self.last_smoothed_drift_ppm = 0
        self.current_sync_interval_ms = config.NTP_SYNC_INTERVAL_MS
        self.display_interval_ms = max(60000, config.DISPLAY_REFRESH_MS)     # EPD refresh time is at least 60 secs (nominal)
        self.max_display_interval_ms = int(1.1 * self.display_interval_ms)   # adapted min EPD refresh time is 0.9 x
        self.min_display_interval_ms = int(0.9 * self.display_interval_ms)   # adapted max EPD refresh time is 1.1 x

        # timekeeping variables
        self.last_ntp_sync_ticks_ms = 0
        self.last_ntp_epoch_ms = 0
        self.last_ntp_epoch_s = 0
        self.ntp_total_delay_ms = 0
        self.ntp_offset_ms = 0
        self.time_tuple = (0,0,0,0,0,0)
        self.last_sync_day = -1
        self.next_sync = '99:99'
        
        # state variables
        self.first_cycle = True
        self.ntp_update = False
        self.upload_files = False
        self.cycle_counter = 0
        self.sync_count = 0
        self.display_update_count = 0 
        
        # time-based sync configuration
        self.sync_target_hour = 3       # 3 (not 03) for 3 AM
        self.sync_target_minute = 15    # 15 (not :15) for 03:15 AM
        self.last_sync_day = -1         # last day NTP synced at target hour (-1 forces first time)
        
        # temperature smoothing
        self.mcu_temp = deque([], 16)
        
        # lists for trend analysis
        if config.DEBUG or config.PUSH_FILE_ENABLED:
            datapoints = 50
            self.mcu_temp_list = deque([], datapoints)
            self.error_ms_list = deque([], datapoints)
            self.correction_ms_list = deque([], datapoints)
            self.measured_drift_ppm_list = deque([], datapoints)
            self.smoothed_drift_ppm_list = deque([], datapoints)
            self.ntp_offset_ms_list = deque([], datapoints)
            self.ntp_tot_delay_ms_list = deque([], datapoints)
            self.ntp_rnd_latency_ms_list = deque([], datapoints)
            self.display_interval_ms_list = deque([], datapoints)
    
    
    
    
    def get_reset_reason(self):
        """Checks the reason for the MCU boot"""
        from machine import reset_cause, PWRON_RESET, HARD_RESET, WDT_RESET, DEEPSLEEP_RESET, SOFT_RESET
        
        reset_reason, reset_message = None, None
        reset_reason = reset_cause()
        reset_message = {
            PWRON_RESET: "POWER-ON RESET",
            HARD_RESET: "HARD RESET",
            WDT_RESET: "WATCHDOG RESET",
            DEEPSLEEP_RESET: "DEEPSLEEP WAKE",
            SOFT_RESET: "SOFT RESET"
        }.get(reset_reason, f"???: {reset_reason}")
        
        del reset_cause, PWRON_RESET, HARD_RESET, WDT_RESET, DEEPSLEEP_RESET, SOFT_RESET
        return reset_reason, reset_message
    
    
    
    
    def write_reset_reason(self, reset_reason, reset_msg):
        """Writes the reset reason to a text file."""
        self.network_mgr.feed_wdt(label="write_reset_reason")
        try:
            with open(config.RESET_FILE_NAME, "a") as file:
                file.write(f"Time: {gmtime(time())},  RST_reason: {str(reset_reason)},  RST_msg: {str(reset_msg)}\n")
        except OSError as e:
            print(f"[ERROR]   Failed to write reset reason: {e}")
    
    
    
    
    def get_discipline(self, key=1):
        """Read discipline factor from NVS"""
        
        if config.QUICK_CHECK:
            print(f"[DEBUG]    Existing 'discipline factor' is not loaded when config.QUICK_CHECK")
            return None
        
        try:
            nvs = NVS("storage")
            buffer = bytearray(16)
            nvs.get_blob(str(key), buffer)
            value = buffer.decode().strip('\x00') 
            if config.DEBUG:
                print(f"[DEBUG]    A discipline factor was available: {value}")
            return self._convert_to_number(value)
        
        except Exception as e:
            if e.errno == -0x1102:
                print("[DEBUG]    Variable 'discipline factor' not found (not saved in esp32.NSV yet)")
            else:
                print(f"[ERROR]    Issue on reading from esp32.NSV: {e}")
            return None
    
    
    
    def save_discipline(self, discipline_factor, key=1):
        """Save discipline factor to NVS"""
        
        if config.QUICK_CHECK:
            print(f"[DEBUG]    Variable 'discipline factor' is not saved when config.QUICK_CHECK")
            return None
        
        try:
            nvs = NVS("storage")
            nvs.set_blob(str(key), str(discipline_factor).encode())
            nvs.commit()
        except Exception as e:
            print(f"[ERROR]   Issue on saving to esp32.NSV: {e}")
            raise
    
    
    
    def write_to_csv(self, epoch, temp, error_ms, ntp_offset_ms, rnd_latency_ms, tot_latency_ms):
        """Writes the stats on a tab separated file."""
        
        if config.DEBUG:
            print(f"[DEBUG]    Function write_to_csv called with epoch={epoch}, file={self.stats_file_name}")
        
        self.network_mgr.feed_wdt(label="write_to_csv")

        try:
            # if this is the first write since boot, create the file and write the header
            if not hasattr(self, "csv_header_written"):
                with open(self.stats_file_name, "w") as file:
                    header = ("epoch\ttemp\terror_ms\tcorrection_ms\tdrift_ppm\t"
                              "ntp_offset_ms\trnd_latency_ms\ttot_latency_ms\t"
                              "smoothed_ppm\tdisplay_interval_ms\tbatt_voltage\t"
                              "battery_level\n"
                              )
                    file.write(header)
                self.csv_header_written = True

            # now append data
            with open(self.stats_file_name, "a") as file:
                data = (
                    f"{epoch}\t{temp:.2f}\t{error_ms}\t{self.correction_ms}\t"
                    f"{self.measured_drift_ppm:.6f}\t{ntp_offset_ms}\t{rnd_latency_ms}\t"
                    f"{tot_latency_ms}\t{self.smoothed_drift_ppm:.6f}\t{self.display_interval_ms}\t"
                    f"{self.batt_voltage}\t{round(self.batt_level,3)}\n"
                )
                file.write(data)

        except Exception as e:
            raise
    

    
    
    def get_temperature(self):
        """Get temperature from MCU"""

        self.network_mgr.feed_wdt(label="get_temperature")
        
        t_warning_c = 50

        temperature_c = mcu_temperature()
        
        if config.TEMP_DEGREES == "C":
            temperature = temperature_c
            if temperature_c > t_warning_c:
                self.display.text_on_logo(f"PROCESSOR TEMP {round(temperature_c,0)} C", x=-1, y=-1, show_time_ms=20000)
            
        elif config.TEMP_DEGREES == "F":
            temperature = self._c_to_f(temperature_c)
            if temperature_c > t_warning_c:
                self.display.text_on_logo(f"PROCESSOR TEMP {round(temperature,0)} F", x=-1, y=-1, show_time_ms=20000)
        else:
            print("[ERROR]   TEMP_DEGREES at config must be 'C' or 'F' ")
            self.display.text_on_logo("ERROR: C or F DEG.", x=-1, y=-1, show_time_ms=20000)
            gc.collect()
        
        
        if len(self.mcu_temp) > 0:
            avg_temp = sum(self.mcu_temp)/len(self.mcu_temp)
        else:
            avg_temp = temperature
        
        self.mcu_temp.append(temperature)
        temp = 0.8 * avg_temp + 0.2 * temperature

        return round(temp, 2)
    
    
    
    
    def update_display(self, current_temp, epd_clear=False):
        """Update the display"""
        self.network_mgr.feed_wdt(label="update_display_1")
        try:    
            H1, H2, M1, M2 = self.time_mgr.get_time_digits(self.time_tuple)
            dd, day, d_string = self.time_mgr.get_date(self.time_tuple)

            gc.collect()

            battery_low = False
            if config.BATTERY and self.batt_voltage < config.BATTERY_WARNING:
                battery_low = True

            if epd_clear:
                plot_all = True
            else:
                plot_all = False
            
            self.display.show_data(H1, H2, M1, M2, dd, day, d_string, current_temp, self.batt_level,
                                   self.res_error_ppm, self.next_sync, self.network_mgr.wifi_bool,
                                   self.network_mgr.ntp_bool, battery_low=battery_low, plot_all=plot_all)

            self.network_mgr.feed_wdt(label="update_display_2")
        
        except Exception as e:
            print(f"[ERROR]   Display error: {e}")
            raise
    
    
    
    
    def goto_sleep(self, total_sleep_ms):
        """Function handling the needed steps to enter lightsleep"""
        
        self.network_mgr.feed_wdt(label="goto_sleep_1")
        
        total_sleep_ms = max(0, total_sleep_ms)
        
        if not config.LIGHTSLEEP_USAGE:
            if config.DEBUG:
                print(f"[DEBUG]    Going to sleep for {total_sleep_ms} ms")
            sleep_ms(total_sleep_ms)

        elif config.LIGHTSLEEP_USAGE:
            
            if self.network_mgr.wlan.active() or self.network_mgr.wlan.isconnected():
                wlan_disabling_t_ms = self.network_mgr.disable_wifi()
                if total_sleep_ms > wlan_disabling_t_ms:
                    total_sleep_ms -= wlan_disabling_t_ms
                else:
                    total_sleep_ms = 0
            
            try:
                bluetooth.disable()   # may raise AttributeError if not available
            except Exception:
                pass
            
            if config.DEBUG:
                t_enter_lightsleep_ms = ticks_ms()
                print(f"[DEBUG]    Entering lightsleep for {total_sleep_ms} ms")   
            
            self.network_mgr.feed_wdt(label="goto_sleep_2")
            
            lightsleep(total_sleep_ms)
            
            if config.DEBUG:
                print(f"[DEBUG]    Quitting lightsleep")
        
        self.network_mgr.feed_wdt(label="goto_sleep_3")
    
    
    
    
    def _epd_sync(self, current_ticks_ms, cycle_time_ms, epd_refreshing_ms, sleep_time_ms):
        """
        Synchronizing the display refreshing moment right after a minute change.
        In this way the display gets refreshed when a new minute got calculated.
        The display update suggests the minute change (seconds between 0 and 10)
        """
        
        max_shift = 5000
        correction = max_shift - 2000
        
        # calculate the shift_ms (exceeding milliseconds from minute change)
        shift_ms = (self.time_tuple[5] * 1000) % self.display_interval_ms
        
        # case shift_ms <= 5000 ms means display refreshes when 0 to 5 secs after minute change
        if shift_ms <= max_shift:  
            # last_display_update_ticks adaptation to keep display refreshing at ca 5 secs after minute change
            self.last_display_update_ticks += (correction - shift_ms)
            
            # sleep time slightly adapted to sleep as long as possible, yet in time for next display refresh
            sleep_time_ms = self.display_interval_ms - cycle_time_ms - shift_ms + correction
            if config.DEBUG:
                if correction - shift_ms == 0:
                    print(f"[DEBUG]    Display refreshed at seconds {self.time_tuple[5]} --> OK ")
                else:
                    print(f"[DEBUG]    Display refreshed at seconds {self.time_tuple[5]} --> OK "   
                          f"(tuning sleep: {shift_ms + correction} and last_display_update_ticks: {correction - shift_ms})")
        
        # case the display requires a large shift_ms to refresh at minute change
        else:
            # last_display_update_ticks adaptation to keep display refreshing at ca 5 secs after minute change
            self.last_display_update_ticks -= (self.display_interval_ms - sleep_time_ms)
            
            # sleep time slightly adapted to sleep as long as possible, yet in time for next display refresh
            sleep_time_ms = self.display_interval_ms - epd_refreshing_ms - shift_ms + correction
            if config.DEBUG:
                print(f"[DEBUG]    Display refreshed at seconds {self.time_tuple[5]} --> adapting the sleeping time")
        
        return sleep_time_ms
    
    
    
    
    async def run(self):
        """Main clock execution"""

        # load discipline factor
        discipline_factor = self.get_discipline()
        if discipline_factor is None:
            self.smoothed_drift_ppm = 0
            if config.DEBUG:
                print(f"[DEBUG]    Not available a prior discipline_factor, it will be saved in a few days from now")
        else:
            self.smoothed_drift_ppm = discipline_factor
            if config.DEBUG:
                print(f"[DEBUG]    Loaded the latest discipline_factor: {discipline_factor}")
        
        self.last_smoothed_drift_ppm = self.smoothed_drift_ppm

        reset_reason, reset_msg = self.get_reset_reason()
        self.write_reset_reason(reset_reason, reset_msg)
        print(f"\n[INFO]     Last reset reason: {reset_msg}\n")

        # plot the SLC logo with a custom text underneath
        self.display.text_on_logo("WIFI  CONNECTION  ...", x=-1, y=-1, show_time_ms=2000)
        gc.collect()
        
        self.network_mgr.feed_wdt(label="before making 1st wlan")
        
        # initialize WiFi
        self.network_mgr.connect_to_wifi(blocking=True)
        
        # check if error due to wifi connection
        if not self.network_mgr.wifi_bool:
            self.display.text_on_logo("ERROR: WIFI NETWORKS", x=-1, y=-1, show_time_ms=2000)
            sys.exit(1)
        
        # check if the wifi has internet connection
        ret = await self.network_mgr.is_internet_available(blocking=True)
        
        # check if error due to internet access
        if not ret:
            self.display.text_on_logo("ERROR: NO INTERNET", x=-1, y=-1, show_time_ms=2000)
            sys.exit(1)
        
            
        self.network_mgr.feed_wdt(label="after making 1st wlan")
        
        # check the IP addresses of the NTP server(s)
        ntp_servers_ip = await self.network_mgr.get_ntp_servers_ip(repeats=5)
        
        # check if error ar resolving the NTP servers addresses
        if len(ntp_servers_ip) == 0:
            self.display.text_on_logo("ERROR: NTP DNS", x=-1, y=-1, show_time_ms=0)
            sys.exit(1)
        
        # get the first tick (in ms) from the board powering moment
        tick = ticks_ms()
        
        self.last_display_update_ticks = tick
        self.last_ntp_server_ip_update = tick

        print("\n[INFO]     Performing first NTP sync ...")

        # plot the SLC logo with a custom text underneath
        self.display.text_on_logo("NTP  SYNCING ...", x=-1, y=-1, show_time_ms=500)
        
        # first NTP sync
        epoch_s, epoch_frac_ms, ntp_sync_ticks_ms, rnd_latency_ms, ntp_offset_ms = await self.network_mgr.get_ntp_time(ntp_servers_ip,
                                                                                                                       blocking=True
                                                                                                                       )
        # case the NTP sync is successfull
        if epoch_s is not None:

            # time reference for the next NTP sync
            self.next_sync, self.secs_to_next_sync = self.time_mgr.next_sync_time(epoch_s, self.current_sync_interval_ms,
                                                                                self.sync_target_hour, self.sync_target_minute)            
            
            # NTP time in milliseconds
            epoch_ms = epoch_s * 1000 + epoch_frac_ms
            self.stats_file_name = config.STATS_FILE_NAME[:-4] + "_" + str(epoch_s) + ".csv"
            print(f"\n[INFO]     File stats_file_name: {self.stats_file_name}\n")
            
            self.last_ntp_epoch_s = epoch_s
            self.last_ntp_epoch_ms = epoch_ms
            self.last_ntp_sync_ticks_ms = ntp_sync_ticks_ms
            self.sync_count += 1

        else:
            raise Exception('First NTP synchronization failed. Halting.')
        
        
        current_temp = self.get_temperature()
        
        
        if config.BATTERY:
            self.batt_voltage, self.batt_level = self.battery.check_battery()
        
        
        print()
        print("#" * 44)
        print("#  Clock is working. Press Ctrl+C to stop  #")
        print("#" * 44)
        print()
        
        
        # main loop variables
        if config.DEBUG:
            self.t_out_sleep = 0
        
        self.measured_drift_ppm = 0.0
        self.res_error_ppm = 0.0
        self.correction_ms = 0
        error_ms = 0
        ntp_failures = 0
        sleep_time_ms = 0
        epd_refreshing_ms = 0
        current_epoch_s = 0
        last_hourly_check_ms = tick
        




        ########################################
        # infinite loop of the main clock code #
        ########################################
        
        while True:
            self.network_mgr.feed_wdt(label="Infinite loop start")
            
            # this tick (in ms) is the only time reference for internal time keeping
            # It is passed in most of the time-related funtions (all of those being time critical)
            current_ticks_ms = ticks_ms()
            

            # check if it's time for NTP sync (used to force NTP sync at fix time of the day, every day)
            time_to_sync = self._is_it_time(current_ticks_ms)
            
            
            # check if it's tick for NTP sync
            tick_to_sync = ticks_diff(current_ticks_ms, self.last_ntp_sync_ticks_ms) >= self.current_sync_interval_ms * (1 + ntp_failures) - config.DISPLAY_REFRESH_MS
            
            
            # in case sync_interval_ms of at least 8 hours, and next_sync happening within 4 hours because of sync_target_hour/minute,
            # the NTP sync due to ticks is skipped, until the NTP sync due to target hour/minute will be executed.
            # This approach synchronizs long sync_interval_ms to the target hour/minute, and preventing NTP sync (due to tick) from
            # happening too close to the NTP sync done because of the sync_target_hour/minute.
            if self.current_sync_interval_ms >= 28_800_000 and self.secs_to_next_sync < 14_400:
                tick_to_sync = False
            
            # case it is tick or (fix) time for NTP sync, call the support function
            if time_to_sync or tick_to_sync:
                ntp_failures = await self._handle_ntp_sync(current_ticks_ms, ntp_servers_ip, current_temp, ntp_failures, epoch_s)

                
            # hourly checks
            if ticks_diff(current_ticks_ms, last_hourly_check_ms) > 3_600_000:
                
                last_hourly_check_ms = current_ticks_ms
                
                # measure the microprocessor temperature
                current_temp = self.get_temperature()
            
                # measure the battery voltage and related level 
                if config.BATTERY:
                    batt_voltage, batt_level = self.battery.check_battery()
                    if batt_voltage != self.batt_voltage or batt_level != self.batt_level:
                        self.batt_voltage = batt_voltage
                        self.batt_level = batt_level

                # re-calculate time reference for the next NTP sync
                # necessary when "alternating" time_to_sunc and tick_to_sinc
                elapsed_since_last_sync_ms = ticks_diff(current_ticks_ms, self.last_ntp_sync_ticks_ms)
                current_epoch_s = self.last_ntp_epoch_s + elapsed_since_last_sync_ms // 1000
                left_sync_interval_ms = self.current_sync_interval_ms - elapsed_since_last_sync_ms
                self.next_sync, self.secs_to_next_sync = self.time_mgr.next_sync_time(current_epoch_s,
                                                                                      left_sync_interval_ms,
                                                                                      self.sync_target_hour,
                                                                                      self.sync_target_minute)
            
            
            # case it is time for display refresh
            if self.first_cycle or ticks_diff(current_ticks_ms, self.last_display_update_ticks) >= self.display_interval_ms:
                
                epd_refreshing_ms = await self._handle_display_update(current_ticks_ms, current_temp)
                
                
                # handle file uploads, right after the display update
                if self.upload_files:
                    await self._handle_file_uploads(current_ticks_ms)
                
                
                # calculate the cycle time, necessary for optimizing the lighsleep time
                cycle_time_ms = ticks_diff(ticks_ms(), current_ticks_ms)
                
                
                # eventually adapts the sleep time to get the display synchronized with minute change
                sleep_time_ms = self._epd_sync(current_ticks_ms, cycle_time_ms, epd_refreshing_ms, sleep_time_ms )
                
                
                # prebenting negative sleeping time
                if sleep_time_ms < 0:
                    sleep_time_ms = self.display_interval_ms - cycle_time_ms
                
                
                # call the supporting function for sleep or lighsleep
                self.goto_sleep(sleep_time_ms)
                
                
                # get the tick (in ms) right after waking up
                if config.DEBUG:
                    self.t_out_sleep = ticks_ms()
                
                # increases the cycle counter
                self.cycle_counter += 1

            # sleep time in between the infine loops; Not sure if really needed
            sleep_ms(50)

    
    
    
    
    async def _handle_ntp_sync(self, current_ticks_ms, ntp_servers_ip, current_temp, ntp_failures, epoch_s) -> int:
        """Support function handling NTP synchronization"""
        
        gc.collect()
        self.network_mgr.feed_wdt(label="Start of NTP IP refresh")
        
        
        # update NTP servers IP addresses
        if ticks_diff(current_ticks_ms, self.last_ntp_server_ip_update) >= config.NTP_IP_REFRESH_PERIOD * (1 + ntp_failures):
            
            # plot the SLC logo with a custom text underneath
            self.display.text_on_logo("GET SERVERS IP ...", x=-1, y=-1, show_time_ms=500)
            ntp_servers_ip, self.last_ntp_server_ip_update = await self.network_mgr.refresh_ntp_ip(current_ticks_ms,
                                                                                                   self.last_ntp_server_ip_update,
                                                                                                   ntp_servers_ip,
                                                                                                   blocking=False
                                                                                                   )

        gc.collect()
        self.network_mgr.feed_wdt(label="Start of synchronizing the display")
               
        if config.DEBUG:
            print(f"{'\n'*4}[NTP]      NTP Sync Cycle #{self.sync_count} (Interval: {self.current_sync_interval_ms/1000}s) ---")
        
        # predict time based on internal ticks
        t_since_last_sync_ms, p_epoch_ms, p_epoch_s, p_epoch_frac, p_t_tuple, p_millis = self.time_mgr.predict_time(self.last_ntp_sync_ticks_ms,
                                                                                                                    current_ticks_ms,
                                                                                                                    self.last_ntp_epoch_ms,
                                                                                                                    self.time_mgr.UTC_TZ)
        
        # plot the SLC logo with a custom text underneath
        self.display.text_on_logo("NTP  SYNCING ...", x=-1, y=-1, show_time_ms=500)
        
        # perform NTP sync
        epoch_s, epoch_frac_ms, ntp_sync_ticks_ms, rnd_latency_ms, ntp_offset_ms = await self.network_mgr.get_ntp_time(ntp_servers_ip,
                                                                                                                       blocking=False
                                                                                                                       )
            
        if epoch_s is None:
            ntp_failures += 1
            self.next_sync, self.secs_to_next_sync = self.time_mgr.next_sync_time(self.last_ntp_epoch_s + config.NTP_IP_REFRESH_PERIOD,
                                                                                self.current_sync_interval_ms, self.sync_target_hour,
                                                                                self.sync_target_minute, ntp_failures=ntp_failures)
            
        elif epoch_s is not None:
            ntp_failures = 0
            await self._process_ntp_result(epoch_s, epoch_frac_ms, ntp_sync_ticks_ms, rnd_latency_ms, ntp_offset_ms,
                                           current_ticks_ms, p_epoch_frac, p_epoch_ms, p_epoch_s, p_t_tuple, p_millis,
                                           t_since_last_sync_ms, current_temp)
            
            
        return ntp_failures
        
        

    
    
    
    async def _process_ntp_result(self, epoch_s, epoch_frac_ms, ntp_sync_ticks_ms, rnd_latency_ms, ntp_offset_ms,
                                  current_ticks_ms, p_epoch_frac, p_epoch_ms, p_epoch_s, p_t_tuple, p_millis,
                                  t_since_last_sync_ms, current_temp):
        
        """Support function processing the NTP sync result"""
        
        self.ntp_update = True
        
        epoch_ms = epoch_s * 1000 + epoch_frac_ms
        ntp_total_delay_ms = ticks_diff(ntp_sync_ticks_ms, current_ticks_ms)
        actual_sync_interval_ms = ticks_diff(ntp_sync_ticks_ms, self.last_ntp_sync_ticks_ms)
        error_ms = (p_epoch_ms + ntp_total_delay_ms - rnd_latency_ms//2) - epoch_ms
        
        if config.DEBUG:
            print(f"[NTP]      Variable last_ntp_epoch_s: {self.last_ntp_epoch_s} s)")
            print(f"[NTP]      Variable t_since_last_sync_ms: {t_since_last_sync_ms} ms")
            print(f"[NTP]      Variable predicted_epoch: {p_epoch_s} + {p_epoch_frac:.3f} s")
            print(f"[NTP]      Expected time before NTP call:",
                  f"{p_t_tuple[3]:02d}:{p_t_tuple[4]:02d}:{p_t_tuple[5]:02d}.{p_millis:03d}")
            print(f"[NTP]      NTP overall latency {ntp_total_delay_ms} ms")
            print(f"[NTP]      NTP new time: {epoch_ms} ms")
            print(f"[NTP]      NTP actual interval: {actual_sync_interval_ms} ms")
            print(f"[NTP]      NTP based error: {error_ms} ms ")
        
        # calculate drift
        self.measured_drift_ppm = (error_ms / actual_sync_interval_ms) * 1000000
        if config.DEBUG:
            print(f"[NTP]      Measured drift: {round(self.measured_drift_ppm,1)} ppm")
        
        self.last_smoothed_drift_ppm = self.smoothed_drift_ppm
        
        if self.sync_count == 0:
            self.smoothed_drift_ppm = self.measured_drift_ppm
        elif self.sync_count > 0:
            if abs(self.measured_drift_ppm) < 50000:
                self.smoothed_drift_ppm = (config.DRIFT_ALPHA * self.measured_drift_ppm) + ((1 - config.DRIFT_ALPHA) * self.smoothed_drift_ppm)
                if config.DEBUG:
                    print(f"[NTP]      Smoothed drift: {round(self.smoothed_drift_ppm,1)} ppm")
            else:
                self.smoothed_drift_ppm = self.last_smoothed_drift_ppm
                print("[ERROR]   Assigned smoothed_drift_ppm to last_smoothed_drift_ppm due to excess of calculated drift.")
        
        self.res_error_ppm = self.measured_drift_ppm - self.smoothed_drift_ppm

        # correct display interval
        if self.sync_count >= 4:
            self.display_interval_ms = config.DISPLAY_REFRESH_MS - round(self.smoothed_drift_ppm * config.DISPLAY_REFRESH_MS / 1000000)
            self.display_interval_ms = min(self.max_display_interval_ms, max(self.min_display_interval_ms, self.display_interval_ms))
            if config.DEBUG:
                print(f"[DEBUG]    Variable display_interval_ms set to {self.display_interval_ms} vs DISPLAY_REFRESH_MS of {config.DISPLAY_REFRESH_MS}")
        
        # log data
        self.write_to_csv(epoch_s, current_temp, error_ms, ntp_offset_ms, rnd_latency_ms, ntp_total_delay_ms)
        
        # feed lists
        if config.DEBUG or config.PUSH_FILE_ENABLED:
            self.network_mgr.feed_wdt(label="Preparing for FEED_LISTS")
            self.mcu_temp_list.append(current_temp)
            self.error_ms_list.append(error_ms)
            self.correction_ms_list.append(self.correction_ms)
            self.measured_drift_ppm_list.append(round(self.measured_drift_ppm,3))
            self.smoothed_drift_ppm_list.append(round(self.smoothed_drift_ppm,3))
            self.ntp_tot_delay_ms_list.append(ntp_total_delay_ms)
            self.ntp_rnd_latency_ms_list.append(rnd_latency_ms)
            self.ntp_offset_ms_list.append(ntp_offset_ms)
            
            if config.DEBUG:
                print(f"[DEBUG]    List mcu_temp_list {list(self.mcu_temp_list)}")
                print(f"[DEBUG]    List error_ms_list {list(self.error_ms_list)}")
                # ... (other list debug prints)
        
        # adaptive NTP sync interval
        last_ntp_sync_interval_ms = self.current_sync_interval_ms
        
        # get the interval for the NTP sync based on the NTP sync cycles
        self.current_sync_interval_ms = self._get_sync_interval_ms(self.sync_count)
      
        self.next_sync, self.secs_to_next_sync = self.time_mgr.next_sync_time(epoch_s, self.current_sync_interval_ms,
                                                                              self.sync_target_hour, self.sync_target_minute)
        
        if config.DEBUG and self.current_sync_interval_ms > last_ntp_sync_interval_ms:
            print(f"[DEBUG]    Increasing sync interval to {self.current_sync_interval_ms/1000}s")
        
        if config.PUSH_FILE_ENABLED:
            self.upload_files = True
        
        # update sync benchmarks
        self.last_ntp_epoch_s = epoch_s
        self.last_ntp_epoch_ms = epoch_ms
        self.last_ntp_sync_ticks_ms = ntp_sync_ticks_ms
        
        # save discipline factor (every 5 days once the NTP sync interval reaches 12 hours)
        if self.sync_count % 10 == 0:
            self.save_discipline(self.smoothed_drift_ppm)
        
        self.sync_count += 1
        
        if config.DEBUG:
            print("\n"*2)
            

    
    
    async def _handle_display_update(self, current_ticks_ms, current_temp):
        """Support function handling display update"""
        
        if config.DEBUG:
            print(f"{'\n'*3}[DEBUG]    {'#'*46}     cycle_counter: {self.cycle_counter}")
            if not self.first_cycle:
                print(f"[DEBUG]    From quitting sleep (or lightleep) and ticking",
                      f"display_interval_ms: {ticks_diff(ticks_ms(), self.t_out_sleep)} ms")

        if self.first_cycle:
            self.first_cycle = False


        # calculate corrected time
        self.time_tuple, self.correction_ms, p_epoch_s = self.time_mgr.calculate_corrected_time(
            current_ticks_ms, self.last_ntp_sync_ticks_ms, self.last_ntp_epoch_s, self.smoothed_drift_ppm
        )

        # update display
        if self.ntp_update or self.display_update_count % config.MAX_PARTIAL_UPDATES == 0:
            epd_clear = True
            self.display_update_count = 0
        else:
            epd_clear = False
        
        t_edp_ref_ms = ticks_ms()

        self.update_display(current_temp, epd_clear=epd_clear)

        epd_refreshing_ms = ticks_diff(ticks_ms(), t_edp_ref_ms)
        self.last_display_update_ticks = current_ticks_ms
        self.display_update_count += 1
        self.ntp_update = False
        
        # print interpreted time and drift
        if config.DEBUG:
            print()
        else:
            print(f"[INFO]     Display: {self.time_tuple[3]}:{self.time_tuple[4]} \tTemp: {current_temp:.2f}°C",
                  f"\tDrift: {round(self.measured_drift_ppm)} ppm",
                  f"\tCorrection: {round(self.smoothed_drift_ppm)} ppm",
                  f"\tBattery: {self.batt_level} %")
        
        return epd_refreshing_ms

    
    
    async def _handle_file_uploads(self, current_ticks_ms):
        """Support function listing the files to be sent to the server"""
        
        self.upload_files = False
        
        try:
            files = [self.stats_file_name,
                     config.NETWORKS_LOG_FILE_NAME,
                     config.RESET_FILE_NAME,
                     config.WDT_LOG_FILE]
            
            self.network_mgr.feed_wdt(label="Preparing for files pushing")
            
            file_list = []
            dest_fname_list = []
            
            for file in files:
                if self._file_exists(file):

                    # adding '_' + 'current_ticks_ms' to the destination filename
                    pos = 0
                    if "/" in file:
                        pos = 1 + file.find("/")
                    dst_fname = f"{file[pos:-4]}_{str(current_ticks_ms)}.csv"
                    dest_fname_list.append(dst_fname)
                    file_list.append(file)
             
            if len(file_list) > 0 and len(dest_fname_list):    
                await self.network_mgr.upload_files(file_list, dest_fname_list, blocking=False)
            
        except Exception as e:
            print(f"Error at sending files out: {e}")
        print()

    
    
    
    def _get_sync_interval_ms(self, sync_count):
        """Support function to get the NTP sync interval based on the cycles already made"""
        if not config.QUICK_CHECK:
            if sync_count > 16:
                if self.res_error_ppm <= 50:  # case the residual error is <= 50 ppm
                    return        86_400_000  # 24 hours NTP_SYNC_INTERVAL_MS
                
                else:                         # case the residual error is > 50 ppm
                    return        43_200_000  # 12 hours NTP_SYNC_INTERVAL_MS
            
            elif sync_count > 12:
                return            28_800_000  #  8 hours NTP_SYNC_INTERVAL_MS (4 times)
            elif sync_count > 8:
                return            21_600_000  #  6 hours NTP_SYNC_INTERVAL_MS (4 times)
            elif sync_count > 4:
                return            14_400_000  #  4 hours NTP_SYNC_INTERVAL_MS (4 times)
            else:
                return             7_200_000  #  2 hours NTP_SYNC_INTERVAL_MS (5 times)
        
        elif config.QUICK_CHECK:
            if sync_count > 1:
                return               300_000  #  5 minutes NTP_SYNC_INTERVAL_MS
            elif sync_count == 3:
                return               240_000  #  4 minutes NTP_SYNC_INTERVAL_MS
            elif sync_count == 2:
                return               180_000  #  3 minutes NTP_SYNC_INTERVAL_MS
            elif sync_count <= 1:
                return               120_000  #  2 minutes NTP_SYNC_INTERVAL_MS
            elif sync_count < 0:
                print("[ERROR]   Negative sync_count is certainly an ERROR !")
                return               300_000  #  5 minutes NTP_SYNC_INTERVAL_MS
                
        
    
    
    
    def _is_it_time(self, current_ticks_ms):
        """Check if current time matches target time within tolerance"""
        
        # check if at least 3 hours from the last NTP sinc, otherwise skip
        if ticks_diff(current_ticks_ms, self.last_ntp_sync_ticks_ms) < 10_800_000:
            return False
        
        target_hour = max(0, min(23, int(self.sync_target_hour)))
        target_minute = max(0, min(59, int(self.sync_target_minute - 1)))
        
        current_hour, current_minute, current_day = self.time_tuple[3], self.time_tuple[4], self.time_tuple[2]
        
        # check if it's around the target time (with some tolerance)
        if (current_hour == target_hour and 
            target_minute <= current_minute < target_minute + 5):  # within 5 minutes of target
            
            # return True only once per day
            if current_day != self.last_sync_day:
                self.last_sync_day = current_day
                if config.DEBUG:
                    target_time_text = f"{target_hour:02d}:{target_minute + 1:02d}"
                    print(f"[DEBUG]    Sync triggered at target time {target_time_text} of day {current_day} ")
                return True
        
        return False
    
    
    
    def _convert_to_number(self, num_text):
        """Convert text to number"""
        if isinstance(num_text, (int, float)):
            return num_text
        
        try:
            return float(num_text)
        except ValueError as e:
            print(f"[ERROR]   The value in {config.DISCIPLINE_FILE_NAME} is not a number: {e}")
            return None
    
    
    
    def _c_to_f(self, temp_c):
        """Function to convert Celsius to Fahrenheit"""
        return temp_c * config.C_TO_F_COEFF + 32
    

    
    def _make_folder(self, folder):
        """Create folder if it doesn't exist."""
        from os import mkdir
        try:
            mkdir(folder)
        except OSError:
            pass        # if folder already exists, ignore
        del mkdir
    
    
    
    def _file_exists(self, path):
        """Checks if the file (path) exists."""
        from os import stat
        try:
            stat(path)
            return True
        except OSError:
            return False





async def main(logo_time_ms=0):
    """Main entry point"""
    clock = SelfLearningClock(logo_time_ms=logo_time_ms)
    await clock.run()




if __name__ == "__main__":
    asyncio.run(main(logo_time_ms=5000))