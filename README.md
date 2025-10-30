# Self-learning clock (SLC)

a DIY clock that learns its own internal drift to maintain high accuracy with minimal NTP synchronizations

It uses an ultra-low power development board, paired with a 4.2-inch, high-contrast e-paper display.
The clock is battery-operated, and one charge should last for months; I'll provide precise battery life data in due time.
<br><br>
![title image](/images/slc_picture_small.jpg)![title image](/images/SLC_small.jpg)

<br><br>
## Repo content
- all the Micropython files
- the Gerber files to make the Connections board


<br><br>
## For more information
More detailed informations at my [Instructables page](https://www.instructables.com/Self-Learning-Clock-SLC/)


<br><br>
## The Concept

Traditional NTP-based clocks frequently check in with time servers, which drains power and relies on a continuous network connection.
Their accuracy drifts until the next sync.

The Self-Learning Clock (SLC) takes a different approach: it observes its own timing errors and builds a software correction model for its internal oscillator's drift.

By applying this adaptive correction, it achieves excellent short-term accuracy and minimal long-term drift (the last gets fully compensated at NTP syncs).

After an initial learning period, the clock maintains an accuracy of approximately ±2 seconds over a 12-hour period, with just two NTP syncs per day.

The initial learning takes about two days, but the learning process never stops, allowing the SLC to continuously refine its corrections.

A high-level flowchart is attached, which better explains how the system works.

After researching online, I could not find any prior project with this specific approach. While there are many accurate timekeeping solutions available, I wanted to see how far I could push the accuracy of a microcontroller's own hardware, in a battery-operated device, and I'm quite pleased with the results.


<br><br>
## Why This Matters:
Microcontrollers like the ESP32 contain two types of oscillators:
- High-power mode: Uses a stable and precise crystal oscillator.
- Low-power mode (light sleep): Uses energy-efficient but imprecise RC oscillators that can accumulate minutes of error per day.

While external RTC modules with backup batteries can solve this problem, the SLC achieves similar precision using only the microcontroller itself.
This enables true, long-lasting battery operation without any additional hardware.




<br><br>
## Why "Self-Learning"?
In this context, "learning" refers to a deterministic self-calibration process.

The clock models and compensates for its own hardware characteristics. It's not artificial intelligence, but a straightforward mathematical analysis.

The system compares the internal clock deviation (in PPM) against a trusted source (NTP servers) and applies a filtered correction to the displayed time.


<br><br>
## Key features

#### Adaptive Drift Compensation:
- Learns and corrects the microcontroller's oscillator drift through periodic NTP synchronization, creating an increasingly accurate internal timing model.
- There is no need to manually calibrate the resonator; the code handles compensation automatically.
- Ultra-Low Power Consumption (<0.75 mAh average):
- Implements finely tuned light-sleep cycles with ultra-short wakeups (≈0.8 seconds active per minute).

#### Smart Time Management:
- Automatically handles time zones and Daylight Saving Time (DST) with configurable rules for different regions (e.g., EU, US, Australia).

#### High-Contrast 4.2" E-Paper Display:
- Features gigantic 110-point digits for excellent readability.
- It uses partial refreshes for efficiency and a full refresh every 60 updates to prevent ghosting.
- The display updates immediately after the minute changes (when seconds are between 0 and 5).
- #### The display also shows useful status information:
  - Battery level (displayed in place of the colon between hours and minutes)
  - Residual timing error (in PPM)
  - Microprocessor temperature (°C/°F)
  - Time of the next NTP sync
  - Status of the last WiFi connection
  - Status of the last NTP synchronization

#### WiFi Connectivity:
- The clock requires a WiFi network for NTP synchronization. While this is a limiting factor, WiFi is common in most modern homes.

#### Additional Notes:
The learning and correction process continuously adapts to variations that might arise from temperature changes or component aging.

The very small duty cycle (<1.5%) drastically limits the microprocessor's self-heating, allowing it to be 'sealed' in an enclosure.
This isolation protects the processor from sudden room temperature fluctuations, leading to a more stable drift characteristic.

Long-term accuracy validation is an ongoing process: The more precise the clock becomes, the longer the test period required to characterize its performance fully.

So far, the longest continuous test run has been one week, and I will provide more detailed long-term data as it becomes available.


