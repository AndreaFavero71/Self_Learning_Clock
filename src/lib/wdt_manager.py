"""
Self-learning clock project
Class managing the WDT (all the other classes refer to this one)



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

from utime import ticks_ms, ticks_diff, gmtime, time
from machine import WDT
from lib.config import config

class WDTManager:
    def __init__(self):
        self.wdt = None
        self.last_feed_ticks_ms = ticks_ms()
        self.enabled = False
        
    def initialize(self):
        """Initialize WDT"""
        if not config.WDT_ENABLED:
            return
            
        try: 
            self.wdt = WDT(timeout=config.wdt_timeout_ms)
            self.enabled = True
            print(f"[WDT]      Initialized WDT with timeout: {config.wdt_timeout_ms}ms")
            
        except Exception as e:
            print(f"[WDT_ERROR] Failed to initialize WDT: {e}")
            self.enabled = False
    
    
    def feed(self, label=""):
        """Feed the watchdog timer with safety checks"""
        if not self.enabled or not self.wdt:
            return
            
        try:
            current_ticks = ticks_ms()
            time_since_last_feed = ticks_diff(current_ticks, self.last_feed_ticks_ms)
            
            # warn if we're getting close to timeout
            if (time_since_last_feed > config.wdt_timeout_ms * config.wdt_warn_fraction and 
                time_since_last_feed < config.wdt_timeout_ms):
                print(f"[WDT] {label}, fed after {time_since_last_feed} ms (timeout={config.wdt_timeout_ms} ms)")
                
                # log to file if needed
                try:
                    with open(config.WDT_LOG_FILE, "a") as f:
                        f.write(f"{gmtime(time())} [WDT] {label}, fed after {time_since_last_feed} ms\n")
                except:
                    pass
            
            self.wdt.feed()
            self.last_feed_ticks_ms = current_ticks
            
        except Exception as e:
            print(f"[WDT_FEED_ERROR] {e}")
