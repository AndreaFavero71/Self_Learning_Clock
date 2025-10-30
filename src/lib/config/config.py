"""
Self-Learning Clock (MicroPython)

More info at:
  https://github.com/AndreaFavero71/Self_Learning_Clock
  https://www.instructables.com/Self-Learning-Clock-SLC/
"""

###################################################################################################
# System controls #########################################################################

# features
QUICK_CHECK        = True#False          # set True only for code debugging
OPEN_NETWORKS      = False          # set True if open wify at reach
BATTERY            = True           # set True if battery operated
WDT_ENABLED        = True           # set True always
PUSH_FILE_ENABLED  = False          # set True only for study purpose

# Notes:
# When QUICK_CHECK then:
# 1) LIGHTSLEEP_USAGE gets set False, to prevent serial communication dropping
# 2) DEBUG sets set True



###################################################################################################
# Constants #######################################################################################

NTP_SERVERS = ['pool.ntp.org', 'nl.pool.ntp.org', 'europe.pool.ntp.org', 
               'time.nist.gov', 'time.google.com', 'time.windows.com']

# regional settings
UTC_TZ = 1                              # timezone UTC (1 is the one for Amsterdam, in The Netherland)
DST = True                              # True if the Country uses DST (Day Saving Time), like The Netherlands does
DST_REGION   = "EU"                     # or 'US'or 'AU', only needed if DST=True, see dst.json file for rules
TEMP_DEGREES = 'C'                      # 'C' for Celsius, 'F' for Farenheit
DATE_FORMAT  = 'DMY'                    # date format, options are DMY, MDY and YMD

DAYS = ('MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY')


# EPD display related settings
DISPLAY_REFRESH_MS    =     60_000      # display updates once a minute
MAX_PARTIAL_UPDATES   =         60      # max number of EPD partial updates, prior a full refresh


# NTP related settings
NTP_SERVER_ATTEMPTS   =         3       # number of times each NTP server will be querried
MAX_NTP_OFFSET_MS     =       1000      # max time offset from NTP to reset internal RTC
NTP_IP_REFRESH_PERIOD = 21_600_000      # (6 hours) interval to refresh NTP servers DNS (IP addresses)


if BATTERY:
    BATTERY_WARNING = 3.4               # min battery voltage to plot a warning


# Files names for diagnostic and study relate
RESET_FILE_NAME        = "log/reset_reason.txt"
STATS_FILE_NAME        = "log/log_data.csv"
NETWORKS_LOG_FILE_NAME = "log/network_log.csv"

if WDT_ENABLED:
    WDT_LOG_FILE       = "log/wdt_log.txt"

# coefficient for error smoothing
DRIFT_ALPHA = 0.25

# time delta in secs from 01/01/2000 (MicroPython system for ESp32)
NTP_DELTA = 3155673600

# fractional coefficient from Celsius to Fahrenheit conversion
C_TO_F_COEFF = 9/5



###################################################################################################
# Conditional settings ############################################################################

# NTP related settings
if QUICK_CHECK:                           # when quick test
    NTP_SYNC_INTERVAL_MS =   120_000      # NTP first sync after 2 minutes, increasing to 5 minutes
    LIGHTSLEEP_USAGE = False              # disable lightsleep
    DEBUG = True                          # enable DEBUG (verbose printing)
else:                                     # when normal operation
    NTP_SYNC_INTERVAL_MS = 7_200_000      # (2 hours) interval at the starts, increasing it later
    LIGHTSLEEP_USAGE = True               # enables lightsleep
    DEBUG = False                         # disable DEBUG


# WDT settings
if WDT_ENABLED:
    wdt_warn_fraction = 0.8
    wdt_timeout_ms = int(1.5 * DISPLAY_REFRESH_MS)


# server address for file sharing
# this must be set according to your networks
# firewall might block python, requiring adding exemption rules
if PUSH_FILE_ENABLED:
    SERVER_URL = 'http://192.168.2.4:8000/upload'
