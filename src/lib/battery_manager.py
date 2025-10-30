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

# import standard modules
from machine import Pin, ADC
from utime import sleep_ms


ADC_IN = Pin(4)                     # GPIO1 reads battery voltage
V_REF = 3.3                         # ADC reference voltage (assuming ESP32 powered at 3.3V)
DIVIDER_RATIO = 2                   # voltage divider ratio:  (R2 + R41) / R41 = (100 + 100) / 100
VBAT_READINGS = 20                  # number of readings for averaging
CORRECTION = 0.984                  # correction of adc reading vs measured (multimeter)
HYSTERESIS_V = 0.03                 # 30 mV hysteresys for battery_level change
SAFE_VOLTAGE_THRESHOLD = 3.4        # stop high comsumption if battery voltage drops below this value (in volts)

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
        self.safe_voltage_threshold = SAFE_VOLTAGE_THRESHOLD
        self.voltage_levels = VOLTAGE_LEVELS
        self.percent_levels = PERCENT_LEVELS
        
        self.last_level = None
        self.batt_voltage_list = []
        self.batt_level = self.check_battery()
        

    def read_batt_voltage(self, adc_avg=0, bat_voltage=0):
        """Monitor the battery voltage"""
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
            print(f"Error reading battery voltage: {e}")
            return None



    def get_batt_percentage(self, voltage, last_level=None):
        """
        Simple closest+shift hysteresis:
          - pick closest nominal level (initial estimate)
          - to change level, require shifted threshold:
              higher level needs nominal + h
              lower  level needs nominal - h
          - allow at most one level change per call (towards estimate)
        Args:
            voltage (float): measured battery voltage
            last_level (int|None): last stable percentage (None for first call)
            h (float): hysteresis voltage (V)
        Returns:
            int: new stable battery level (percent)
        """

        
        # 1) find closest nominal index
        closest_index = min(range(len(self.voltage_levels)), key=lambda i: abs(voltage - self.voltage_levels[i]))
        estimated_level = self.percent_levels[closest_index]
        

        # if no previous level, accept estimate
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

        batt_voltage = round(self.read_batt_voltage(),3) # battery voltage is measured   
        self.batt_voltage_list.append(batt_voltage)
        
        if len(self.batt_voltage_list) > 1:
            batt_voltage = sum(self.batt_voltage_list) / len(self.batt_voltage_list)
        
        if len(self.batt_voltage_list) > 10:
            self.batt_voltage_list.pop(0)
            
        self.batt_level = self.get_batt_percentage(batt_voltage)
        self.last_batt_level = self.batt_level
        if self.debug:
            print(f"[DEBUG]    Battery voltage = {batt_voltage:.3f}V,  Battery level = {self.batt_level}\n")
        
        return self.batt_level

    
    
