"""
Self-learning clock project

EPD driver derived from the Waveshare repository:
https://github.com/waveshareteam/Pico_ePaper_Code/blob/main/python/Pico-ePaper-4.2_V2.py


Modified to use a LiLyGO TTGO T8-S3 board on the 4.2 inches Pico display

"""

from utime import sleep_ms
from machine import Pin
import framebuf

# display resolution
EPD_WIDTH  = 400
EPD_HEIGHT = 300

# LiLyGO TTGO T8-S3 pin used
DC_PIN   = 6
CS_PIN   = 7
CLK_PIN  = 8
MOSI_PIN = 9
RST_PIN  = 14
BUSY_PIN = 17
MISO_PIN = 21 # not phisically connected


LUT_ALL=[   0x01, 0x0A, 0x1B, 0x0F, 0x03, 0x01, 0x01, 
            0x05, 0x0A, 0x01, 0x0A, 0x01, 0x01, 0x01, 
            0x05, 0x08, 0x03, 0x02, 0x04, 0x01, 0x01, 
            0x01, 0x04, 0x04, 0x02, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x0A, 0x1B, 0x0F, 0x03, 0x01, 0x01, 
            0x05, 0x4A, 0x01, 0x8A, 0x01, 0x01, 0x01, 
            0x05, 0x48, 0x03, 0x82, 0x84, 0x01, 0x01, 
            0x01, 0x84, 0x84, 0x82, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x0A, 0x1B, 0x8F, 0x03, 0x01, 0x01, 
            0x05, 0x4A, 0x01, 0x8A, 0x01, 0x01, 0x01, 
            0x05, 0x48, 0x83, 0x82, 0x04, 0x01, 0x01, 
            0x01, 0x04, 0x04, 0x02, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x8A, 0x1B, 0x8F, 0x03, 0x01, 0x01, 
            0x05, 0x4A, 0x01, 0x8A, 0x01, 0x01, 0x01, 
            0x05, 0x48, 0x83, 0x02, 0x04, 0x01, 0x01, 
            0x01, 0x04, 0x04, 0x02, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x8A, 0x9B, 0x8F, 0x03, 0x01, 0x01, 
            0x05, 0x4A, 0x01, 0x8A, 0x01, 0x01, 0x01, 
            0x05, 0x48, 0x03, 0x42, 0x04, 0x01, 0x01, 
            0x01, 0x04, 0x04, 0x42, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
            0x02, 0x00, 0x00, 0x07, 0x17, 0x41, 0xA8, 
            0x32, 0x30 ]


class EPD(framebuf.FrameBuffer):
    def __init__(self):

        self.init_spi_esp32()
        self.init_buffer()
    
    
    def init_buffer(self):
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.Seconds_1_5S = 0
        self.Seconds_1S = 1
        self.LUT_ALL = LUT_ALL

        self.black = 0x00
        self.white = 0xff
        self.darkgray = 0xaa
        self.grayish = 0x55

        self.buffer = bytearray(self.height * self.width // 8)
        self.fb = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.MONO_HLSB)

        self.fb.fill(1)

        self.init()
        self.clear()
        sleep_ms(500)

        # EPD object based on self.fb
        super().__init__(self.fb, self.width, self.height, framebuf.MONO_HLSB)


            
    def init_spi_esp32(self):
        # configuration for LilyGo TTGO T8-S3
        from machine import SoftSPI
        
        self.reset_pin = Pin(RST_PIN, Pin.OUT)
        self.busy_pin = Pin(BUSY_PIN, Pin.IN, Pin.PULL_UP)
        self.cs_pin = Pin(CS_PIN, Pin.OUT)
        self.spi = SoftSPI(
            baudrate  = 4_000_000,
            polarity  = 0,
            phase     = 0, 
            sck       = Pin(CLK_PIN),
            mosi      = Pin(MOSI_PIN),
            miso      = Pin(MISO_PIN),
            firstbit  = SoftSPI.MSB
            )
        self.dc_pin = Pin(DC_PIN, Pin.OUT)

    
    def digital_write(self, pin, value):
        pin.value(value)

    
    def digital_read(self, pin):
        return pin.value()

    
    def delay_ms(self, delaytime):
        sleep_ms(delaytime)

    
    def spi_writebyte(self, data):
        self.spi.write(bytearray(data))

    
    def module_exit(self):
        self.digital_write(self.reset_pin, 0)

    
    # hardware reset
    def reset(self):
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(20) 
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(20)
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(20)
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(20)  

    
    def send_command(self, command):
        self.digital_write(self.dc_pin, 0)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([command])
        self.digital_write(self.cs_pin, 1)

    
    def send_data(self, data):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([data])
        self.digital_write(self.cs_pin, 1)
        
    
    def send_data1(self, buf):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray(buf))
        self.digital_write(self.cs_pin, 1)
        
    
    def ReadBusy(self):
        while(self.digital_read(self.busy_pin) == 1):      #  LOW: idle, HIGH: busy
            self.delay_ms(100) 
        
        
    def TurnOnDisplay(self):
        self.send_command(0x22) #Display Update Control
        self.send_data(0xF7)
        self.send_command(0x20) #Activate Display Update Sequence
        self.ReadBusy()
        
    
    def TurnOnDisplay_Fast(self):
        self.send_command(0x22) #Display Update Control
        self.send_data(0xC7)
        self.send_command(0x20) #Activate Display Update Sequence
        self.ReadBusy()
        
    
    def TurnOnDisplay_Partial(self):
        self.send_command(0x22) #Display Update Control
        self.send_data(0xFF)
        self.send_command(0x20) #Activate Display Update Sequence
        self.ReadBusy()
        
    
    def TurnOnDisplay_4GRAY(self):
        self.send_command(0x22) #Display Update Control
        self.send_data(0xCF)
        self.send_command(0x20) #Activate Display Update Sequence
        self.ReadBusy()
            
    
    def init(self):
        # EPD hardware init start
        self.reset()
        self.ReadBusy()

        self.send_command(0x12) #SWRESET
        self.ReadBusy()

        self.send_command(0x21)  # Display update control
        self.send_data(0x40)
        self.send_data(0x00)

        self.send_command(0x3C)  # BorderWavefrom
        self.send_data(0x05)

        self.send_command(0x11)  # data  entry  mode
        self.send_data(0x03)  # X-mode

        self.send_command(0x44) 
        self.send_data(0x00)
        self.send_data(0x31)  
        
        self.send_command(0x45) 
        self.send_data(0x00)
        self.send_data(0x00)  
        self.send_data(0x2B)
        self.send_data(0x01)

        self.send_command(0x4E) 
        self.send_data(0x00)

        self.send_command(0x4F) 
        self.send_data(0x00)
        self.send_data(0x00)  
        self.ReadBusy()

    
    def init_Fast(self, mode=None):
        self.reset()
        self.ReadBusy()

        self.send_command(0x12) #SWRESET
        self.ReadBusy()

        self.send_command(0x21)  # Display update control
        self.send_data(0x40)
        self.send_data(0x00)

        self.send_command(0x3C)  # BorderWavefrom
        self.send_data(0x05)
        
        if mode is None or mode == self.Seconds_1_5S:
            self.send_command(0x1A)
            self.send_data(0x6E)  
        else :
            self.send_command(0x1A)
            self.send_data(0x5A)  

        self.send_command(0x22)  # Load temperature value
        self.send_data(0x91)  
        self.send_command(0x20)  
        self.ReadBusy()

        self.send_command(0x11)  # data  entry  mode
        self.send_data(0x03)  # X-mode

        self.send_command(0x44) 
        self.send_data(0x00)
        self.send_data(0x31)  
        
        self.send_command(0x45) 
        self.send_data(0x00)
        self.send_data(0x00)  
        self.send_data(0x2B)
        self.send_data(0x01)

        self.send_command(0x4E) 
        self.send_data(0x00)

        self.send_command(0x4F) 
        self.send_data(0x00)
        self.send_data(0x00)  
        self.ReadBusy()

    
    def Lut(self):
        self.send_command(0x32)
        for i in range(227):
            self.send_data(self.LUT_ALL[i])

        self.send_command(0x3F)
        self.send_data(self.LUT_ALL[227])

        self.send_command(0x03)
        self.send_data(self.LUT_ALL[228])

        self.send_command(0x04)
        self.send_data(self.LUT_ALL[229])
        self.send_data(self.LUT_ALL[230])
        self.send_data(self.LUT_ALL[231])

        self.send_command(0x2c)
        self.send_data(self.LUT_ALL[232])
        
            
    
    def clear(self, color=0xff):
        high = self.height
        if( self.width % 8 == 0) :
            wide =  self.width // 8
        else :
            wide =  self.width // 8 + 1

        self.send_command(0x24)
        for i in range(0, wide):
            self.send_data1([color] * high)
                
        self.send_command(0x26)
        for i in range(0, wide):
            self.send_data1([color] * high)

        self.TurnOnDisplay()
        
    
    def display(self):                
        self.send_command(0x24)
        self.send_data1(self.buffer)

        self.send_command(0x26)
        self.send_data1(self.buffer)
            
        self.TurnOnDisplay()
        

    def display_Fast(self):
        self.send_command(0x24)
        self.send_data1(self.buffer)

        self.send_command(0x26)
        self.send_data1(self.buffer)

        self.TurnOnDisplay_Fast()
        
    
    def partialDisplay(self):
        self.send_command(0x3C)  # BorderWavefrom
        self.send_data(0x80)

        self.send_command(0x21)  # Display update control
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x3C)  # BorderWavefrom
        self.send_data(0x80)

        self.send_command(0x44) 
        self.send_data(0x00)
        self.send_data(0x31)  
        
        self.send_command(0x45) 
        self.send_data(0x00)
        self.send_data(0x00)  
        self.send_data(0x2B)
        self.send_data(0x01)

        self.send_command(0x4E) 
        self.send_data(0x00)

        self.send_command(0x4F) 
        self.send_data(0x00)
        self.send_data(0x00) 

        self.send_command(0x24) # WRITE_RAM
        self.send_data1(self.buffer)
        self.TurnOnDisplay_Partial()
        
    
    def sleep(self):
        self.send_command(0x10)  # DEEP_SLEEP
        self.send_data(0x01)
    