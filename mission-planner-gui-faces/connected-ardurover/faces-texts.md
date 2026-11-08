## Antenna.TrackerUI
Acceleration
Speed
Center PWM
Find Trim Pan (Sik Radio)
0
Misusing this interface can cause servo damage, use with caution!!!
Angle
PWM Range
Rev
Tilt
Pan
Range
Trim
Connect
Interface

## ConfigAC_Fence
RTL Altitude[]
Enable
Type
Action
Max Alt[]
Min Alt[]
Max Radius[]
Geo Fence

## ConfigADSB
Flight Identification:
Save
Aircraft Registration
Find
Refresh Params
Write Params

## ConfigAccelerometerCalibration
Level your Autopilot to set default accelerometer scale factors for level flight (1 axis).
This requires you to place your autopilot flat and level.
Level your Autopilot to set default accelerometer offsets (1 axis/AHRS trims).
This requires you to place your autopilot flat and level.
Calibrate Level
Calibrate Accel
Level your Autopilot to set default accelerometer Min/Max (3 axis).
This will ask you to place your autopilot on each edge.
Accelerometer Calibration
Simple Accel Cal

## ConfigAdvanced
Share connection with support engineer
Support Proxy
Spectrogram
FFT
Output the MAV location as a NMEA string
Mavlink mirror to an external location. For Monitoring or control
Enable mavlink signing to secure communication with the MAV
View the data from a 360 lidar
Warning Manager
NMEA
MAVLink Inspector
Mavlink Mirror
Proximity
Mavlink Signing
Enable custom warnings based on a set of conditions
View decoded mavlink data being sent and received
Scramble lat/lng in bin or tlog
Follow Me
Use an external NMEA gps and send guided mode waypoints to the MAV based on that location
Regenerage the param info used inside mp
Param gen
Show an extra icon on the map of your current location.
Moving Base
Anon Log
Plot a FFT from a log
The following pages are for advanced configutation only. use with caution

## ConfigAntennaTracker
Altitude Source
Pitch Gain
Rate Max
D
IMAX
I
P
Yaw Gain
Pitch Range of Movement
Max (deg)
Min (deg)
Yaw Range of Movement
Range (deg)
Pitch Servo
1500
Type
Test
Reverse
Neutral
Max
Min
Board Orientation
Yaw Servo

## ConfigArducopter
Static Notch Filter
Attenuation
BandWidth
Frequency
Enabled
Harmonic Notch Filter
Harmonics
Options
Bandwidth
Reference
Mode
RC6 Opt
Filter Logs
Mask
Basic Filters
Accel
Gyro
RC10 Opt
RC9 Opt
RC8 Opt
Refresh Screen
Throttle Accel (Accel to motor)
D
IMAX
I
P
Velocity XY (Vel to Accel)
Refresh Params
Write Params
Min
Tune
RC7 Opt
Throttle Rate (VSpd to accel)
Lock Pitch and Roll Values
WPNav (cm's)
Speed Up
Loiter Speed
Speed Dn
Radius
Speed
Altitude Hold (Alt to climbrate)
Position XY (Dist to Speed)
INPUT TC
Stabilize Yaw (Error to Rate)
ACCEL MAX
Stabilize Pitch (Error to Rate)
Stabilize Roll (Error to Rate)
Rate Yaw
FLTT
FLTD
FLTE
Rate Pitch
Rate Roll

## ConfigArduplane
Refresh Screen
TECS
Sink Max (m/s)
Time Const
Pitch Dampening
Sink Min (m/s)
Climb Max (m/s)
L1 Control - Turn Control
Damping
Period
Refresh Params
Write Params
Throttle 0-100%
SlewRate
Max
Min
Cruise
Airspeed m/s
Ratio
Navigation Angles
Pitch Min
Pitch Max
Bank Max
Other Mix's
P to T
Rudder Mix
Energy/Alt Pid
INT_MAX
D
I
P
Nav Pitch Alt Pid
Nav Pitch AS Pid
Servo Yaw
Intergrator Max
Dampening
Integral
Yaw 2 roll
Servo Pitch Pid
Servo Roll Pid

## ConfigArdurover
RC10 Opt
RC9 Opt
RC8 Opt
RC7 Opt
Refresh Screen
Steering Mode
Turn Radius
Avoidance
Sonar Debounce
Turn Time
Turn Angle
Trigger Dist (cm)
Steering Rate
FF
IMAX
D
I
P
Navigation
WP Speed
Lat Acc Cntl Damp
Lat Acc Cntl Period
WP Overshoot
WP Radius
Turn G Max
Refresh Params
Write Params
Throttle and Motors
Motor Type
Throttle Max (%)
Throttle Min (%)
Speed/Throttle
Brake
Accel Max (m/s/s)
Cruise Speed
Cruise Throttle

## ConfigAteryx
Read Flash
Write Flash
Roll to Elev
Airspeed m/s
Max Airspeed
Min Airspeed
Cruise
Take Off / Landing
Approach Speed
Min TO Pitch
Altimeter Settings
in Hg
Field Elev
Navigation Angles
Pitch Min
Pitch Max
Bank Min
Bank Max
Track and Orbit
Default Radius
Orbit Gain
Entry Angle
Track Gain
Servo Yaw Pid
Yaw Rate Limit
P
Airspeed to Pitch
Int Lim
Effort Lim
D
I
Heading to Roll
Energy Height
EH Range
Servo Pitch Pid
Refresh Params
Write Params
Throttle 0-100%
FS Value
Max
Min
Servo Roll Pid

## ConfigAteryxSensors
Zero Pressure
Zero Attitude

## ConfigBatteryMonitoring
MP Alert on Low Battery
mAh
HW Ver
Calibration
5. Current (Calced)
4. Measured current:
1. Measured battery voltage:
2. Battery voltage (Calced):
3. Voltage divider (Calced):
6. Amperes per volt:
Sensor
Battery Capacity
Monitor

## ConfigBatteryMonitoring2
MP Alert on Low Battery
mAh
Current Pin
Calibration
5. Current (Calced)
4. Measured current:
1. Measured battery voltage:
2. Battery voltage (Calced):
3. Voltage divider (Calced):
6. Amperes per volt:
Volt Pin
Battery Capacity
Monitor

## ConfigCompassMot
Compass Motor Calibration
Finish
Start

## ConfigCubeID
Upload Custom Firmware
Force 57600 baud
SERIAL_PASSTIMO
SERIAL_PASS2
To use this feature
Please enable serial passthough to the port the CubeID is connected to.
Set param SERIAL_PASSTIMO to 0
Set param SERIAL_PASS2 to the telem port
Upload Firmware
Select the ODID device from the dropdown in the top right corner
then click the Update Firmware button

## ConfigESCCalibration
maximum speed of motors while in flight (almost all escs have a deadzone at the top)
minimum speed of motors while in flight (slightly higher than "Spin when Armed")
speed when motors are armed but throttle is at zero (idle)
Leave as 0 to use RX input range
Spin Maximum
Spin minimum
Spin when Armed
Output PWM Max
Output PWM Min
ESC Type:
Calibrate ESCs
Remove Props!
After pushing this button:
-Disconnect USB and battery
-Plug in battery
-when LEDs flash, push Saftey Switch (if present)
-ESCs should beep as they are calibrated
- restart flight controller normally
ESC Calibration (AC3.3+)

## ConfigFFT
Please ensure IMU_RAW and IMU_FAST are turned off to use FFT
Bitmap of what log types to enable in on-board logger. This value is made up of the sum of each of the log types you want to be saved. On boards supporting microSD cards or other large block-storage devices it is usually best just to enable all basic log types by setting this to 65535.
Fast Attitude
Medium Attitude
GPS
System Performance
Throttle
Navigation Tuning
IMU
Mission Commands
Battery Monitor
Rangefinder
Compass
Camera
Steering
RC Input-Output
Raw IMU
Video Stabilization
Optical Flow
FFT
FFT Setup
4096
32
Bitmap of which IMUs to log batch data for. This option takes effect on the next reboot.
IMU1
IMU2
IMU3

## ConfigFailSafe
Battery
Low Timer
Low Battery
Reserved MAH
GCS
GCS FS Enable
GCS FailSafe
FailSafe Short (1 sec)
FailSafe Long (20 sec)
Radio
FS Pwm
Throttle FailSafe
Throttle Failsafe Action
Wiki
Manual
Servo/Motor OUT
Radio IN
Radio 3
1500
Radio 1
Radio 8
1800
Radio 7
1000
Radio 6
Radio 5
Radio 4
Radio 2

## ConfigFirmwareDisabled
Update the bootloader on your hardware to the newest available.
Bootloader Update
You cannot load new firmware while connected via MAVLink. 

Please press the Disconnect button at top right to end the current MAVLink session and enable the firmware loading screen.

## ConfigFlightModes
Flight Mode 1
Super Simple Mode
PWM 1750 +
PWM 1621 - 1749
PWM 1491 - 1620
PWM 1361 - 1490
PWM 0 - 1230
PWM 1231 - 1360
Simple Mode
Flight Mode 2
Flight Mode 3
Flight Mode 4
Flight Mode 5
Flight Mode 6
Save Modes
Simple and Super Simple description
Current PWM:
8: 1800
Current Mode:
Manual

## ConfigFrameClassType
Frame Class
OctaQuad
Tri
Heli
Y6
Octa
Hexa
Quad
Undefined
Frame Type
Other
'V Tail'
NOTE: This is the Y6B and prop rotation changes from the old Y6A
'Y6B'
'Plus'
'X' , 'Y6A'
NOTE: X and H are NOT interchangable the prop rotation changes
'H'
'V'

## ConfigFrameType
Frame Type
'V Tail'
NOTE: This is the Y6B and prop rotation changes from the old Y6A
'Y6B'
'Plus'
'X' , 'Y6A'
NOTE: X and H are NOT interchangable the prop rotation changes
'H'
'V'
Default Settings
Load Params

## ConfigFriendlyParams
Find
Refresh Params
Write Params
360
0
0.1745
-0.1745
Description: AIS receiver type
AIS receiver type (AIS_TYPE)
Description: Checks to skip prior to arming motor. This is a bitmask of checks before allowing 
arming that will be skipped. For most users it is recommended to leave this 
at the default of 0 (no checks skipped). In extreme circumstances, a value of 
-1 can be used to skip all non-mandatory current and future checks.
Barometer
Compass
GPS lock
INS
Parameters
RC Channels
Board voltage
Battery Level
Logging Available
Hardware safety switch
GPS Configuration
System
Mission
Rangefinder
Camera
AuxAuth
VisualOdometry
FFT
Description: Enable airspeed sensor support
Airspeed Enable (ARSPD_ENABLE)
10
0.1
0.5
100
2
1
5
Description: Speed control brake enable/disable. Allows sending a reversed output to the motors to slow the vehicle.
Speed control brake enable/disable (ATC_BRAKE)
0.4
0.010
1000
3
20
Description: pin number to use to enable the throttle in auto mode. If set to -1 then 
don't use a trigger, otherwise this is a pin number which if held low in 
auto mode will enable the motor to run. If the switch is released while in 
AUTO then the motor will stop again. This can be used in combination with INITIAL_MODE 
to give a 'press button to start' rover with no receiver.
Auto mode trigger pin (AUTO_TRIGGER_PIN)
Description: Avoidance behaviour (slide or stop)
Avoidance behaviour (AVOID_BEHAVE)
Description: Enabled/disable avoidance input sources
UseFence
UseProximitySensor
UseBeaconFence
15
-2
Description: Sets the analog input pin that should be used for current monitoring.
Battery Current sensing pin (BATT_CURR_PIN)
Description: What action the vehicle should perform if it hits a critical battery failsafe
Critical battery failsafe action (BATT_FS_CRT_ACT)
Description: What action the vehicle should perform if it hits a low battery failsafe
Low battery failsafe action (BATT_FS_LOW_ACT)
Description: Controls enabling monitoring of the battery's voltage and current
Battery monitoring (BATT_MONITOR)
Description: Sets the analog input pin that should be used for voltage monitoring.
Battery Voltage sensing pin (BATT_VOLT_PIN)
Battery monitoring (BATT2_MONITOR)
Battery monitoring (BATT3_MONITOR)
Battery monitoring (BATT4_MONITOR)
Battery monitoring (BATT5_MONITOR)
Battery monitoring (BATT6_MONITOR)
Battery monitoring (BATT7_MONITOR)
Battery monitoring (BATT8_MONITOR)
Battery monitoring (BATT9_MONITOR)
Description: This controls the default state of the safety switch at startup. When set to 1 the 
safety switch will start in the safe state (flashing) at boot. When set to zero 
the safety switch will start in the unsafe state (solid) at startup. Note that if 
a safety switch is fitted the user can still control the safety state after startup 
using the switch. The safety state can also be controlled in software using a MAVLink 
message.
Sets default state of the safety switch (BRD_SAFETY_DEFLT)
Description: This controls the activation of the safety button. It allows you to control if the 
safety button can be used for safety enable and/or disable, and whether the button 
is only active when disarmed
ActiveForSafetyDisable
ActiveForSafetyEnable
ActiveWhenArmed
Force safety on when the aircraft disarms
Description: When enabled, trigging by distance is done in AUTO mode only.

## ConfigFriendlyParamsAdv
Find
Refresh Params
Write Params
0.5
0.001
Description: This controls which NavEKF Kalman filter version is used for attitude and position estimation
Use NavEKF Kalman filter for attitude and position estimation (AHRS_EKF_TYPE)
1
0
10
Description: This controls whether to use dead-reckoning or GPS based navigation. If set to 0 then the 
GPS won't be used for navigation, and only dead reckoning will be used. A value 
of zero should never be used for normal flight. Currently this affects only the DCM-based 
AHRS: the EKF uses GPS according to its own parameters. A value of 2 means 
to use GPS for height as well as position - both in DCM estimation and 
when determining altitude-above-home.
AHRS use GPS for DCM navigation and position-down (AHRS_GPS_USE)
Description: This controls optional AHRS behaviour. Setting DisableDCMFallbackFW will change the AHRS behaviour for fixed wing 
aircraft in fly-forward flight to not fall back to DCM when the EKF stops 
navigating. Setting DisableDCMFallbackVTOL will change the AHRS behaviour for fixed wing aircraft in non 
fly-forward (VTOL) flight to not fall back to DCM when the EKF stops navigating. 
Setting DontDisableAirspeedUsingEKF disables the EKF based innovation check for airspeed consistency. Setting AutoRecordOrigin will 
auto-save the EKF origin to parameters when it becomes valid.
DisableDCMFallbackFW
DisableDCMFallbackVTOL
DontDisableAirspeedUsingEKF
RecordOrigin
UseRecordedOriginForNonGPS
Description: Overall board orientation relative to the standard orientation for the board type. This rotates the IMU 
and compass readings to allow the board to be oriented in your vehicle at any 
90 or 45 degree angle. The label for each option is specified in the order 
of rotations for that orientation. This option takes affect on next boot. After changing you 
will need to re-level your vehicle. Firmware versions 4.2 and prior can use a CUSTOM 
(100) rotation to set the AHRS_CUSTOM_ROLL/PIT/YAW angles for AHRS orientation. Later versions provide two general 
custom rotations which can be used, Custom 1 and Custom 2, with CUST_ROT1_ROLL/PIT/YAW or CUST_ROT2_ROLL/PIT/YAW 
angles.
Board Orientation (AHRS_ORIENTATION)
180
-180
0.4
0.1
0.1745
-0.1745
127
Description: Bitmask of mission items that are required to be planned in order to arm the 
aircraft
Land
VTOL Land
DO_LAND_START
Takeoff
VTOL Takeoff
Rallypoint
RTL
Description: Require that the vehicle have an absolute position before it arms.  This can help ensure 
that the vehicle can Return To Launch.
Require vehicle location (ARMING_NEED_LOC)
Description: Options that can be applied to change arming behaviour
Disable prearm display
Do not send status text on state change
Skip IMU consistency checks when ICE motor running
Description: Arming disabled until some requirements are met. If 0, there are no requirements (arm immediately).  
If 1, all checks not skipped by ARMING_SKIPCHK must pass before the vehicle can be 
armed (for example, via rudder stick or GCS command).  If 3, Arm immediately once 
pre-arm/arm checks are satisfied, but only one time per boot up.  Note that a 
reboot is NOT required when setting to 0 but IS require when setting to 3.
Require Arming Motors (ARMING_REQUIRE)
Description: Allow arm/disarm by rudder input. When enabled arming can be done with right rudder, disarming with 
left rudder. Rudder arming only works with throttle at zero +- deadzone (RCx_DZ). Depending on 
vehicle type, arming in certain modes is prevented. See the wiki for each vehicle. Caution 
is recommended when arming if it is allowed in an auto-throttle mode!
Arming with Rudder enable/disable (ARMING_RUDDER)
0.03
200
Description: This selects the bus number for looking for an I2C barometer. When set to -1 it 
will probe all external i2c buses based on the BARO_PROBE_EXT parameter.
External baro bus (BARO_EXT_BUS)
100
Description: This selects which barometer will be the primary if multiple barometers are found
Primary barometer (BARO_PRIMARY)
Description: This sets which types of external i2c barometer to look for. It is a bitmask 
of barometer types. The I2C buses to probe is based on BARO_EXT_BUS. If BARO_EXT_BUS 
is -1 then it will probe all external buses, otherwise it will probe just 
the bus number given in BARO_EXT_BUS.
BMP085
BMP280
MS5611
MS5607
MS5637
FBM320
DPS280
LPS25H
Keller
MS5837
BMP388
SPL06
MSP
BMP581
AUAV
Description: This enables the use of wind coefficients for barometer compensation
Wind coefficient enable (BARO1_WCF_ENABLE)
Wind coefficient enable (BARO2_WCF_ENABLE)
Wind coefficient enable (BARO3_WCF_ENABLE)
Description: Voltage type used for detection of low voltage event
Failsafe voltage source (BATT_FS_VOLTSRC)
120
Description: This sets options to change the behaviour of the battery monitor
Ignore DroneCAN SoC
MPPT reports input voltage and current
MPPT Powered off when disarmed
MPPT Powered on when armed

## ConfigGPSOrder
UAVCAN GPS Order
Set the GPS order if required

## ConfigHWAirspeed
Type
Pin
Use Airspeed
Enable
Airspeed

## ConfigHWBT
Pin
Baud
Name
Save Settings
Bluetooth

## ConfigHWCompass
Large Vehicle MagCal
APM and External Compass
APM2.5 (Internal Compass)
Pixhawk/PX4
Select device to quick-configure parameters:
Compass #3
MOT          X: 0,   Y: 0,   Z: 0
OFFSETS  X: 5,   Y: 13,   Z: -18
Externally mounted
Use this compass
Compass #2
Compass #1
General Compass Settings
Primary Compass:
Automatically learn offsets
Obtain declination automatically
Degrees
Minutes
Declination WebSite
OR
Mission Planner Mag Calibration
Live Calibration
Youtube Example
Onboard Mag Calibration
Relax fitness if calibration fails
Fitness
Mag 3
Mag 2
Mag 1
Accept
Cancel
Start
Compass

## ConfigHWCompass2
Remove Missing
A reboot is required to adjust the ordering.
Reboot
Use Compass 3
Use Compass 2
Automatically learn offsets
A mag calibration is required to remap the above changes.
Large Vehicle MagCal
Do you want to disable any of the first 3 compasses?
Onboard Mag Calibration
Relax fitness if calibration fails
Fitness
Mag 3
Mag 2
Mag 1
Accept
Cancel
Start
Compass Priority
Use Compass 1
Set the Compass Priority by reordering the compasses in the table below (Highest at the top)

## ConfigHWESP8266
SSID
Password
STA Mode
Gateway
Subnet
IP
Channel
Client Mode
...
Baud
Reset to Defaults
Save Settings
ESP8266

## ConfigHWIDs


## ConfigHWOSD
You only need to use this if you are having issue with your OSD not updating
Enable Telemetry
OSD

## ConfigHWOptFlow
metres from ground
Height Override
Scaling Factors
Position of Sensor, relative to IMU
metres down
metres right
metres foward
degrees, relative to vehicle
Position Z
Position Y
Position X
FY Scale
FX Scale
Yaw Orientation
Type
Enable
Optical Flow

## ConfigHWPX4Flow
Focus Mode
PX4 Flow

## ConfigHWParachute
Min Alt (m)
Deploy PWM
Resting PWM
Servo Num
Type
Enable (AC3.3+)
Parachute

## ConfigHWRangeFinder
0
Voltage:
Distance:
RangeFinder

## ConfigInitialParams
PLEASE READ IT !
You can find a detailed description of initial parameter settings and tuning here.
https://ardupilot.org/copter/docs/tuning-process-instructions.html
Add suggested settings for 4.0 and up (Battery failsafe and Fence) ?
Battery Chemistry
Calculate Initial Parameters
Using T-Motor Flame ESC?
Battery cell fully discharged voltage:
Battery cell fully charged voltage:
Battery cellcount:
Airscrew size in inch:

## ConfigMandatory
The following pages are required to be configured before your autopilot will work. Please work though them all.

## ConfigMotorTest
Motor Test
Type: unknown
Class: unknown
Set the min % that will be output when flying
Set Motor Spin Min
Set the min % that will be output when armed, but still on the ground
Set Motor Spin Arm
Throttle %
Duration (s)
NOTE: PLEASE HOLD DOWN YOUR UAV
This will test your motors are working.
Motors are tested in a clockwise rotation 
starting at the front right.
Please click here to see your motor numbers,
scroll to the bottom of the page
Test motor A
Test motor B
Test motor C
Test motor D
Test all motors
Stop all motors
Test all in Sequence

## ConfigMount
NOTE: the gimbal type takes effect on the next reboot of the fight controller
Type
Please set the Ch7 Option to Camera Trigger
Duration (1/10th sec)
Shutter
Servo Limits
Not Pushed
Pushed
Max
Min
Stabalise Roll
Stabalise Tilt
Neutral Angles
Z
Y
X
Retract Angles
Input Ch
Angle Limits
Reverse
Pan
Wiki
Roll
Tilt

## ConfigOSD
Settings
OSD_TYPE
OSD / Telmetry Slots Config
Refresh
Discard all changes
Auto write on leaving
Write customization

## ConfigOptional
The following pages are OPTIONAL configure them if you have aditional hardware, or other requirements.

## ConfigPlanner
Disable RTS reset on ESP32 SerialUSB
Aircraft Icon
Inactive Aircraft
NOTE: Set the low level of SEVERITY to speak
Only when Armed
Runing on a slow computer
Params Download in BackGround
GCS ID
Alt Units
No Fly
Auto Commit Params
Layout
No RC Receiver
Testing Screen
TFR's
ADSB
Show Airports
Low Speed
Display Target
Display Turn Radius
Display Nav Bearing
Display Heading
Display ToolTip
Display COG
Password Protect Config
Beta Updates
OptOut Anon Stats
Start/Stop Vario
Arm/Disarm
Custom
Theme
Browse
Log Path
Dist to Home
Display in Flightdata
Map Follow
Map is rotated to follow the plane
Sensor
Video Format
Line Length
HUD
GDI+ (old type/no HW acceleration)
Waypoints
Load Waypoints on connect?
Track Length
Alt Warning
Connect Reset
Reset on USB Connect (toggle DTR)
Mavlink Message Debug
RC
Mode/Status
Position
Attitude
Telemetry Rates
NOTE: The Configuration Tab will NOT display these units, as those are raw values.
Speed Units
Dist Units
Joystick
Speech
Battery Warning
30s Interval
Mode
Waypoint
OSD Color
UI Language
Enable Speech
Enable HUD Overlay
Video Device
Joystick Setup
Stop
Start
Map Access Mode
Open Map Cache

## ConfigREPL
Disconnect
Connect

## ConfigRadioInput
Spektrum Bind
Bind DSM2
Bind DSM8
Bind DSMX
Elevon Config
Elevons
Elevons CH2 Rev
Elevons Rev
Elevons CH1 Rev
Reverse
Calibrate Radio

## ConfigRadioOutput
#
Max
Trim
Min
Function
Reverse
Position
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16

## ConfigRawParams
<
Search
Refresh Table
None Default
Load from file
Save to file
Refresh Params
Commit Params
Write Params
Reset to Default
Compare Params
Load Presaved
All Units are in raw 
format with no scaling
Modified

## ConfigSecureAP
Do Only Once
Generate Key
Files
Private Key
BootLoader
Firmware

## ConfigSerial


## ConfigSerialInjectGPS
Send NTRIP protocol v1.0 ?
Send NTRIP GGA? (VRS/Smart)
Link Status
Input data rate
9999 bps
Output data rate
Messages Seen
2
rtcm0000
rtcm0000
RTCM
Galileo
Beidou
Glonass
Gps
RTCM Base
Base
-00.000000000 000.000000000 0000.000000000
Automatically Configure Receiver
Automatic Config Options
At connect the receiver  will start a “survey-in” to determine the GPS precision location.
The survey-in is finished when the RTCM Base location is no longer changing.
Based on the location and signal it could take a couple minutes

Once the survey is completed, you are ready to go.
RTCM Constellation Usage
BeiDou
GLONASS
GPS
Set Interval
RTCM Message Interval (s)
RTCM Message Amount
Fixed Position
Atitude (WGS84)
Longitude (WGS84)
Altitude (m)
Set Position
Restart
M8P fw 130+/F9P
Save Current Position
Time(s)
SurveyIn Acc(m)
Survey In
Inject MSG Type
Connect

## ConfigSimplePids


## ConfigTradHeli4
Servo Setup
2
1
Reversed
Trim
Max
Min
Servo
Function
3
4
5
6
7
8
Swashplate Setup
H_SV_MAN
H_SW_TYPE
H_SW_COL_DIR
H_SW_LIN_SVO
H_FLYBAR_MODE
H_CYC_MAX
H_COL_MAX
H_COL_MID
H_COL_MIN
H_COL_ANG_MIN
H_COL_ANG_MAX
H_COL_ZERO_THRST
H_COL_LAND_MIN
Throttle Settings
H_RSC_MODE
H_RSC_CRITICAL
H_RSC_RAMP_TIME
H_RSC_RUNUP_TIME
H_RSC_CLDWN_TIME
H_RSC_SETPOINT
H_RSC_IDLE
H_RSC_THRCRV_0
H_RSC_THRCRV_25
H_RSC_THRCRV_50
H_RSC_THRCRV_75
H_RSC_THRCRV_100
Governor Settings
H_RSC_GOV_COMP
H_RSC_GOV_SETPNT
H_RSC_GOV_DISGAG
H_RSC_GOV_DROOP
H_RSC_GOV_FF
H_RSC_GOV_TCGAIN
H_RSC_GOV_RANGE
H_RSC_GOV_RPM
H_RSC_GOV_TORQUE
Misc Settings
IM_STB_COL_1
IM_STB_COL_2
IM_STB_COL_3
IM_STB_COL_4
H_TAIL_TYPE
H_TAIL_SPEED
H_GYR_GAIN
H_GYR_GAIN_ACRO
H_COLYAW

## ConfigUserDefined
Modify
RC6_OPTION
RC7_OPTION
RC8_OPTION
RC9_OPTION
RC10_OPTION
RC11_OPTION
RC12_OPTION
RC13_OPTION
RC14_OPTION
RC15_OPTION
RC16_OPTION

## Joystick.JoystickSetup
Manual Control
Loaded Config for ArduRover
Elevons
Reverse
Controller Axis
Output
Expo
Joystick
Enable
Save
Auto Detect
RC 1
0
RC 2
RC 3
RC 4
RC 5
RC 6
RC 7
RC 8
RC 9
RC 10
RC 11
RC 12
RC 13
RC 14
RC 15
RC 16

## MavFTPUI


## Sikradio
Upload Firmware (custom)
Reset to Defaults
Status Leds
Remote
Load from File...
Save to File...
Failsafe Frame Loss
GPO1_3AUXOUT
GPI1_2AUXIN
GPIO1_1FUNC
GPO1_0TXEN485
GPO1_3STATLED
Set PPM Fail Safe
Country:
GPO1_3SBUSOUT:
GPO1_3SBUSIN
Rate/FreqBand
RXENCAP
TXENCAP
Dest ID
Node ID
GPO1_1R/COUT
GPI1_1R/CIN
Op Resend
Mavlink
ECC
Tx Power
Net ID
Baud
Air Speed
Format
Antenna Mode
Break Detection
Global Retries
Max Retries
Max Data
AES Key
AES Encryption
RTS CTS
Max Window (ms)
Min Freq
Max Freq
# of Channels
Duty Cycle
LBT Rssi
Version
Local
Random
Settings for Standard Mavlink
Settings for Low Latency
RSSI
Copy required to remote
Save Settings
Load Settings
NOTE: Always click "Copy required to remote" when modifying
this ensures you wont lose radio link
Upload Firmware (standard)

