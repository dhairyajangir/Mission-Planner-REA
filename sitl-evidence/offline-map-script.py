# Test-copy startup script: select synthetic, cache-only map tiles.
import clr
import System
clr.AddReference('GMap.NET.Core')
from GMap.NET import GMaps, AccessMode, PointLatLng
from GMap.NET.MapProviders import GMapProviders
from MissionPlanner.GCSViews import FlightData

result_path = System.Environment.GetEnvironmentVariable('MP_OFFLINE_MAP_RESULT')
lines = ['scope=modified app, plugin-disabled, synthetic tiles, cache-only']
try:
    def apply_map():
        GMaps.Instance.Mode = AccessMode.CacheOnly
        FlightData.mymap.MapProvider = GMapProviders.OpenStreetMap
        FlightData.mymap.Position = PointLatLng(-35.363261, 149.165230)
        FlightData.mymap.Zoom = 3
    MainV2.instance.Invoke(System.Action(apply_map))
    lines.append('applied=True')
except Exception as ex:
    lines.append('error=' + str(ex))
finally:
    System.IO.File.WriteAllText(result_path, '\n'.join(lines) + '\n')
