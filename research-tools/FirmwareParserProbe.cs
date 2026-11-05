using System;
using System.IO;
using px4uploader;

public static class FirmwareParserProbe
{
    public static int Main(string[] paths)
    {
        foreach (string path in paths)
        {
            try
            {
                var firmware = Firmware.ProcessFirmware(path);
                string bytes = firmware.imagebyte == null ? "null" : BitConverter.ToString(firmware.imagebyte).Replace("-", "");
                Console.WriteLine("RESULT|" + Path.GetFileName(path) + "|OK|" + firmware.board_id + "|" +
                                  firmware.image_size + "|" + (firmware.imagebyte == null ? -1 : firmware.imagebyte.Length) + "|" + bytes);
            }
            catch (Exception ex)
            {
                Console.WriteLine("RESULT|" + Path.GetFileName(path) + "|ERROR|" + ex.GetType().FullName);
            }
        }
        return 0;
    }
}
