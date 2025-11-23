"""
Self-learning clock project
Class monitors the LiPo battery voltage and its level %



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

from machine import Pin, ADC
from utime import sleep_ms


ADC_IN = Pin(4)                     # GPIO reading battery voltage
V_REF = 3.3                         # ADC reference voltage (assuming ESP32 powered at 3.3V)
DIVIDER_RATIO = 2                   # voltage divider ratio:  (R2 + R41) / R41 = (100 + 100) / 100
VBAT_READINGS = 20                  # number of readings for averaging
CORRECTION = 1.0                    # adc correction vs real (set > 1 when intepreted value is smaller than real)
HYSTERESIS_V = 0.03                 # 30 mV hysteresys for battery_level change (prevent jumping up and down)

# tuples with the volatge thresholds and battery levels
VOLTAGE_LEVELS = (4.02, 3.95, 3.84, 3.725, 3.675, 3.64, 3.59)
PERCENT_LEVELS = (100, 80, 60, 40, 20, 10, 0)


class Battery():
    def __init__(self, debug=False):
        
        self.debug = debug
        
        self.adc_bat = ADC(ADC_IN)         # adc object
        self.adc_bat.atten(ADC.ATTN_11DB)  # 11dB attenuation (input range up to ~3.3V)
        self.v_ref = V_REF
        self.divider_ratio = DIVIDER_RATIO
        self.vbat_readings = VBAT_READINGS
        self.correction = CORRECTION
        self.hysteresys_v = HYSTERESIS_V
        self.voltage_levels = VOLTAGE_LEVELS
        self.percent_levels = PERCENT_LEVELS
        
        self.last_level = None
        self.batt_voltage_list = []
        self.batt_voltage, self.batt_level = self.check_battery()
        

    def _read_batt_voltage(self, adc_avg=0, bat_voltage=0):
        """Supporting function reading the battery voltage"""
        try:
            adc_avg = self.adc_bat.read()       # first ADC reading
            sleep_ms(5)                         # short sleep time

            for _ in range(self.vbat_readings): # iterating vbat_readings times
                adc_avg += self.adc_bat.read()  # adds raw ADC value (0-4095) for vbat_readings times
                sleep_ms(10)                    # short sleep time
            
            adc_avg /= (self.vbat_readings + 1) # average the vbat_readings readings
            
            # convertion to batt voltage and correction
            bat_voltage = self.correction * (adc_avg / 4095) * self.v_ref * self.divider_ratio
            return bat_voltage                  # returns the measured battery voltag

        except Exception as e:
            if config.DEBUG:
                print(f"[ERROR]    Error reading battery voltage: {e}")
            return None



    def _get_batt_percentage(self, voltage):
        """
        Supporting function returning the battery level, based on
        closest value and shift hysteresis:
          - pick closest nominal level (initial estimate)
          - to change level, require shifted threshold:
              higher level needs nominal + h
              lower  level needs nominal - h
          - allow at most one level change per call (towards estimate)
        
        Args:
            voltage (float): measured battery voltage
            h (float): hysteresis voltage (V)
        Returns:
            int: new stable battery level (percent)
        """

        
        # find closest nominal index
        closest_index = min(range(len(self.voltage_levels)), key=lambda i: abs(voltage - self.voltage_levels[i]))
        estimated_level = self.percent_levels[closest_index]
    
        # if no previous level, accept the first estimate battery level
        if self.last_level is None:
            if self.debug:
                print("[DEBUG]    First battery level detection:", estimated_level)
            return estimated_level

        # find last index in table (fallback if last_level not in list)
        try:
            last_index = self.percent_levels.index(self.last_level)
        except ValueError:
            last_index = closest_index

        # if estimated equals last, keep it
        if closest_index == last_index:
            return self.last_level

        # moving UP (towards higher percent) -> smaller index number
        if closest_index < last_index:
            
            # candidate index we want to move to:
            candidate_index = closest_index
            
            # but limit to only one-step change if estimate is >1 step away
            if last_index - candidate_index > 1:
                candidate_index = last_index - 1

            # require voltage >= nominal_of_candidate + h to accept moving up
            threshold = self.voltage_levels[candidate_index] + h
            
            if voltage >= threshold:
                return self.percent_levels[candidate_index]
            else:
                return self.last_level

        # moving DOWN (towards lower percent) -> larger index number
        else:  # closest_index > last_index
            candidate_index = closest_index
            if candidate_index - last_index > 1:
                candidate_index = last_index + 1

            # require voltage <= nominal_of_candidate - h to accept moving down
            threshold = self.voltage_levels[candidate_index] - h
            if voltage <= threshold:
                return self.percent_levels[candidate_index]
            else:
                return self.last_level



    def check_battery(self):
        """Hub function for battery voltage and battery level"""
        
        # get the battery voltage from the supporting function (average of n readings)
        batt_voltage = round(self._read_batt_voltage(),3) # battery voltage is measured   
        
        # append the battery voltage to the list
        self.batt_voltage_list.append(batt_voltage)
        
        # case there are more than one value in the list
        if len(self.batt_voltage_list) > 1:
            # average battery voltage is calculated 
            batt_voltage = sum(self.batt_voltage_list) / len(self.batt_voltage_list)
        
        # the average battery voltage is assigned to the instance variable
        self.batt_voltage = batt_voltage
        
        # case there are more than 10 elemnts in the list
        if len(self.batt_voltage_list) > 10:
            self.batt_voltage_list.pop(0)      # the older value gets removed
        
        # call the support function to get the battery level, based on the average battery voltage
        self.batt_level = self._get_batt_percentage(batt_voltage)
        
        # the battery level is assigned to the last_batt_level
        self.last_batt_level = self.batt_level
        
        if self.debug:
            print(f"[DEBUG]    Battery voltage = {batt_voltage:.3f}V,  Battery level = {self.batt_level}\n")
        
        # battery volatge and level are returned
        return self.batt_voltage ,self.batt_level
