"""
Self-learning clock project
Class managing the time related calculations



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

from utime import gmtime, mktime, ticks_diff
import ujson as json


class TimeManager:
    def __init__(self, config):
        
        self.config = config
        self.dst_rules = self._load_dst_rules()
        self.region = getattr(config, "DST_REGION", "EU")
        self.is_dst_enabled = getattr(config, "DST", True)
        self.UTC_TZ = getattr(config, "UTC_TZ", 0)
    
    
    
    def get_UTC_TZ(self, utc_epoch_time):
        """
        Calculates current UTC offset including DST, based on region rules.
        Returns offset in hours.
        """
        if not self.is_dst_enabled:
            return self.UTC_TZ

        rule = self.dst_rules.get(self.region, self.dst_rules.get("NONE", {}))
        if not rule or not rule.get("start") or not rule.get("end"):
            return self.UTC_TZ

        t = gmtime(utc_epoch_time)
        year, month, day, hour = t[0], t[1], t[2], t[3]

        start_m, start_w, start_d, start_h = rule["start"]
        end_m, end_w, end_d, end_h = rule["end"]

        start_day = self._get_rule_day(year, start_m, start_w, start_d)
        end_day = self._get_rule_day(year, end_m, end_w, end_d)

        months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                  "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

        sm = months[start_m]
        em = months[end_m]

        in_dst = False
        if sm < em:  # northern hemisphere (e.g. EU, US)
            if (month > sm and month < em) or \
               (month == sm and (day > start_day or (day == start_day and hour >= start_h))) or \
               (month == em and (day < end_day or (day == end_day and hour < end_h))):
                in_dst = True
        else:  # southern hemisphere (e.g. AU)
            if not ((month > em and month < sm) or \
                    (month == em and (day > end_day or (day == end_day and hour >= end_h))) or \
                    (month == sm and (day < start_day or (day == start_day and hour < start_h)))):
                in_dst = True

        offset_hr = (rule.get("offset", 3600) // 3600) if in_dst else 0
        
        return self.UTC_TZ + offset_hr
    
    
    
    def _load_dst_rules(self):
        """Loads DST rules from dst_rules.json (once at init)."""
        try:
            with open("lib/config/dst_rules.json") as f:
                return json.load(f)
        
        except Exception as e:
            if config.DEBUG:
                print("[DST]     Warning: could not load dst_rules.json:", e)
            
            # fallback: only EU and NONE
            return {
                "EU": {
                    "start": ["MAR", "last", "sun", 2],
                    "end": ["OCT", "last", "sun", 3],
                    "offset": 3600
                },
                "NONE": {
                    "start": None,
                    "end": None,
                    "offset": 0
                }
            }
    
    
    
    def _get_rule_day(self, year, month_abbr, which, weekday_abbr):
        """Return the day number for nth/last weekday of a month."""
        months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                  "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        weekdays = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}

        month = months[month_abbr.upper()]
        target_wday = weekdays[weekday_abbr.lower()]

        # month length
        if month in [1,3,5,7,8,10,12]:
            last_day = 31
        elif month == 2:
            last_day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
        else:
            last_day = 30

        # find target weekday
        if which == "last":
            for d in range(last_day, last_day - 7, -1):
                if gmtime(mktime((year, month, d, 12, 0, 0, 0, 0)))[6] == target_wday:
                    return d
        else:
            nth = {"1st":0,"2nd":1,"3rd":2,"4th":3}.get(which,0)
            for d in range(1, 8):
                if gmtime(mktime((year, month, d, 12, 0, 0, 0, 0)))[6] == target_wday:
                    return d + nth * 7

        return 1  # fallback
    
    
    
    def ms_to_hms(self, ms):
        seconds = ms // 1000
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return "{:02d}:{:02d}:{:02d}".format(h, m, s)
    
    
    
    def get_time_digits(self, time_tuple):
        HH = "{:02d}".format(time_tuple[3])
        MM = "{:02d}".format(time_tuple[4])
        return HH[0], HH[1], MM[0], MM[1]
    
    
    
    def get_date(self, time_tuple):
        yyyy = time_tuple[0]
        mm   = time_tuple[1]
        dd   = time_tuple[2]
        day  = self.config.DAYS[time_tuple[6]]
        
        YYYY = "{:04d}".format(yyyy)
        M    = "{:02d}".format(mm)
        D    = "{:02d}".format(dd)
        
        if self.config.DATE_FORMAT == "DMY":
            d_string = f"{D}-{M}-{YYYY}"
        elif self.config.DATE_FORMAT == "MDY":
            d_string = f"{M}-{D}-{YYYY}"
        elif self.config.DATE_FORMAT == "YMD":
            d_string = f"{YYYY}-{M}-{D}"
        else:
            d_string = f"{D}-{M}-{YYYY}"
        
        return dd, day, d_string
    
    
    
    def predict_time(self, last_ntp_sync_ticks_ms, current_ticks_ms, last_ntp_epoch_ms, current_UTC_TZ):
        """
        Predict the time without applying any corrections: Elapsed time is added to the latest time reference
        The predicted time, including the time zone, is converted to epoch.
        """        
        
        # calculate everything in milliseconds for precision
        t_since_last_sync_ms = ticks_diff(current_ticks_ms, last_ntp_sync_ticks_ms)
        
        # calculate predicted time in milliseconds
        p_epoch_ms = last_ntp_epoch_ms + t_since_last_sync_ms
        p_epoch_s = p_epoch_ms // 1000  # Use integer division
        p_epoch_frac = (p_epoch_ms % 1000) / 1000.0  # Fractional part
        
        # convert to time tuple for human-readable format
        p_t_tuple = gmtime(p_epoch_s + 3600 * current_UTC_TZ)
        p_millis = p_epoch_ms % 1000
                        
        return t_since_last_sync_ms, p_epoch_ms, p_epoch_s, p_epoch_frac, p_t_tuple, p_millis
    
    
    
    def calculate_corrected_time(self, current_ticks_ms, last_ntp_sync_ticks_ms,
                                last_ntp_epoch_s, smoothed_drift_ppm):
        """
        Calculates the current time, by correcting it.
        It takes into account the drift (passed as argument), the time zone
        and the eventual DST
        """
        
        # time (ms) since previous NTP sync (according to the mcu oscillator)
        time_since_sync_ms = ticks_diff(current_ticks_ms, last_ntp_sync_ticks_ms)
        
        # calculate the correction (ms), based on the oscillator drift (ppm) and elapsed time (ms)
        correction_ms = -(smoothed_drift_ppm * time_since_sync_ms) / 1000000
        
        # estimate elapsed time, calculated in ms and converted in rounded seconds
        total_elapsed_s = round((time_since_sync_ms + correction_ms) / 1000)
        
        # calculate the utc_epoch_s (utc time) in seconds
        utc_epoch_s = int(last_ntp_epoch_s + total_elapsed_s)
        
        # retrieves the time shift due to time_zome and eventual DST
        current_UTC_TZ = self.get_UTC_TZ(utc_epoch_s) # DST CALCULATION
        
        # local epoch time in seconds
        local_epoch_s = utc_epoch_s + 3600 * current_UTC_TZ
        
        # local time in standard Micropython tuple format
        time_tuple_utc = gmtime(local_epoch_s)

        if self.config.DEBUG:
            print("[DEBUG]    current_ticks_ms:", current_ticks_ms)
            print("[DEBUG]    last_ntp_sync_ticks_ms:", last_ntp_sync_ticks_ms)
            print("[DEBUG]    last_ntp_epoch_s:", last_ntp_epoch_s)
            print("[DEBUG]    smoothed_drift_ppm:", smoothed_drift_ppm)
            print("[DEBUG]    time_since_sync_ms:", time_since_sync_ms)
            print("[DEBUG]    correction_ms:", round(correction_ms))
            print("[DEBUG]    total_elapsed_s:", total_elapsed_s)
            print("[DEBUG]    utc_epoch_s:", utc_epoch_s)
            print("[DEBUG]    time_tuple_utc:", time_tuple_utc)
            
        # check for integer overflow
        if last_ntp_epoch_s > 2147483647:  # 2^31 - 1
            if config.DEBUG:
                print("[WARNING]  Possible integer overflow!")
        
        # returns the time tuple elements, the sub-seconds remainder from epoch_s, and the epoch_s
        return (time_tuple_utc[0], time_tuple_utc[1], time_tuple_utc[2], time_tuple_utc[3],
                time_tuple_utc[4], time_tuple_utc[5], time_tuple_utc[6]), round(correction_ms), utc_epoch_s
    
    
    
    def next_sync_time(self, epoch_s, current_sync_interval_ms, sync_target_hour, sync_target_minute, ntp_failures=0):        
        
        
        # calulates the UTC time, eventually corrected by the DST
        utc_tz_dst = self.get_UTC_TZ(epoch_s)
        
        # seconds to next sync, based on the ticks period
        secs_to_target_tick = (ntp_failures + 1) * current_sync_interval_ms//1000
        
        # update the time_tuple
        local_epoch_s = epoch_s + 3600 * utc_tz_dst
        
        # local_time_tuple
        time_tuple = gmtime(local_epoch_s)
        
        # seconds to next sync, based on the "fix" syncing time
        secs_to_target_time = self.seconds_until_target_time(time_tuple, sync_target_hour, sync_target_minute)
        
        # In case sync_interval_ms of at least 8 hours, and next_sync happening within 4 hours of sync_target_hour/minute,
        # the NTP sync due to ticks is postponed until the NTP sync due to target hour/minute.
        # This approach to synchronize the long sync_interval_ms to the target hour/minute, by preventing it from
        # NTP sync after a relatively short period sunce the last NTP sync due to ticks.
        if current_sync_interval_ms >= 28_800_000 and secs_to_target_time < 14_400:
            secs_to_target_tick += 18_000     # +5 hours, instead of 4, to ensure next_sync_time will refer to target_time
        
        # seconds to the earlier sync
        seconds_to_sync = min(secs_to_target_tick, secs_to_target_time)
        
        # time tuple of the next sync
        next_sync_tuple = gmtime(local_epoch_s + seconds_to_sync)
        
        # next sync time in text format HH:MM
        next_sync_hhmm = "{:02d}".format(next_sync_tuple[3]) + ":" + "{:02d}".format(next_sync_tuple[4])
        
        if self.config.DEBUG:
            print("[DEBUG]    next_sync time:", next_sync_hhmm)
        
        return next_sync_hhmm, seconds_to_sync
    
    
    
    def seconds_until_target_time(self, time_tuple, sync_target_hour, sync_target_minute):
        """calculate seconds until target time today or tomorrow"""
        current_hour, current_minute, current_second = time_tuple[3], time_tuple[4], time_tuple[5]
        
        # calculate seconds until target time today
        seconds_today = (sync_target_hour - current_hour) * 3600 + \
                        (sync_target_minute - current_minute) * 60 - \
                        current_second
        
        if seconds_today > 0:
            return seconds_today
        else:
            # target time already passed today, use tomorrow
            return seconds_today + 86400  # add one day

