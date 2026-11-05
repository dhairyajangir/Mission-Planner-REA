from pathlib import Path
root = Path(__file__).resolve().parent.parent
source = (root/'research-tools/FenceAdvancedLegacyProbe.cs').read_text()
source = source.replace('FenceAdvancedLegacyProbe','FenceAdvancedWriteProbe')
start = source.index('            try {\n                var response = port.getFencePoint(0)')
end = source.index('            ushort count =',start)
replacement = '''            try {
                bool accepted = port.setFencePoint(0, new PointLatLngAlt(-35.3635,149.1655), 6);
                Console.WriteLine("LEGACY_WRITE_RESULT=" + accepted);
            } catch (Exception e) { Console.WriteLine("LEGACY_WRITE_ERROR=" + e.GetType().FullName + ":" + e.Message); }
            System.Threading.Thread.Sleep(1000);
'''
source = source[:start] + replacement + source[end:]
(root/'research-tools/FenceAdvancedWriteProbe.cs').write_text(source)
