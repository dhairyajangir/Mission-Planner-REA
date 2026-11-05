# Startup script for modified, plugin-disabled application test copy.
import System
from MissionPlanner.Utilities import CaptureMJPEG
from MissionPlanner.GCSViews import FlightData

result = System.Environment.GetEnvironmentVariable('MP_MJPEG_HUD_RESULT')
stop = System.Environment.GetEnvironmentVariable('MP_MJPEG_HUD_STOP')
lines = ['scope=modified app, plugins disabled, synthetic localhost MJPEG']
try:
    CaptureMJPEG.URL = 'http://127.0.0.1:6691/video'
    CaptureMJPEG.runAsync()
    found = False
    for attempt in range(40):
        Script.Sleep(500)
        image = FlightData.myhud.bgimage
        if image is not None:
            lines.append('hud_image=' + str(image.Width) + 'x' + str(image.Height))
            found = True
            break
    lines.append('image_found=' + str(found))
    System.IO.File.WriteAllText(result, '\n'.join(lines) + '\n')
    for attempt in range(300):
        if System.IO.File.Exists(stop):
            break
        Script.Sleep(500)
    CaptureMJPEG.Stop()
    Script.Sleep(2000)
    lines.append('stop_called=True')
    lines.append('hud_cleared=' + str(FlightData.myhud.bgimage is None))
except Exception as ex:
    lines.append('error=' + str(ex))
finally:
    System.IO.File.WriteAllText(result, '\n'.join(lines) + '\n')
