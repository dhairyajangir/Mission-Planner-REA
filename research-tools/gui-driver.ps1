# Drive ONE window of a process that this session launched (the research copy of Mission Planner 1.3.83) with window messages, without moving the user's mouse or
# sending keystrokes to any other window:
#   shot  <out.png> [windowTitleContains]   capture the window (PrintWindow) to a PNG
#   click <x> <y> [windowTitleContains]     post mouse move / left button down / left button up to the child window under client point (x, y)
#   text  <string> [windowTitleContains]    post WM_CHAR for each character to the focused child of that window's thread
#   list                                     list the process's top-level windows (handle, title, size)
#   combo <x> <y> <item> [windowTitleContains]  select the item with that text in the combo box under (x, y) (CB_SELECTSTRING + notify parent)
# The target process is the one named by -ProcessName (default MissionPlanner). Simulator and the research copy only.
param([Parameter(Mandatory = $true, Position = 0)][string]$Command, [Parameter(Position = 1)][string]$A1, [Parameter(Position = 2)][string]$A2, [Parameter(Position = 3)][string]$A3, [Parameter(Position = 4)][string]$A4, [string]$ProcessName = 'MissionPlanner')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
public static class W32 {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc p, IntPtr l);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern IntPtr ChildWindowFromPointEx(IntPtr h, POINT p, uint flags);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool ScreenToClient(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, string l);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr h);
    [DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    public static List<IntPtr> Windows(uint pid) {
        var l = new List<IntPtr>();
        EnumWindows((h, p) => { uint q; GetWindowThreadProcessId(h, out q); if (q == pid && IsWindowVisible(h)) l.Add(h); return true; }, IntPtr.Zero);
        return l;
    }
    public static List<IntPtr> Descendants(IntPtr top) { var l = new List<IntPtr>(); EnumChildWindows(top, (h, p) => { l.Add(h); return true; }, IntPtr.Zero); return l; }
    public static string Title(IntPtr h) { var s = new StringBuilder(256); GetWindowText(h, s, 256); return s.ToString(); }
    public static string Class(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    public static IntPtr Deepest(IntPtr top, int x, int y) {
        IntPtr cur = top; var pt = new POINT { X = x, Y = y };
        for (int i = 0; i < 20; i++) {
            IntPtr c = ChildWindowFromPointEx(cur, pt, 0x0001 | 0x0002 | 0x0004);   // skip invisible, disabled, transparent
            if (c == IntPtr.Zero || c == cur) break;
            POINT s = pt; ClientToScreen(cur, ref s); ScreenToClient(c, ref s); pt = s; cur = c;
        }
        return cur;
    }
    public static POINT ClientPointIn(IntPtr top, IntPtr child, int x, int y) {
        var p = new POINT { X = x, Y = y }; ClientToScreen(top, ref p); ScreenToClient(child, ref p); return p;
    }
}
'@
$proc = Get-Process -Name $ProcessName -ErrorAction Stop | Select-Object -First 1
$wins = [W32]::Windows([uint32]$proc.Id)
function Pick([string]$contains) {
    if ($contains) { return $wins | Where-Object { [W32]::Title($_).Contains($contains) } | Select-Object -First 1 }
    # the main window is the one whose title starts with the product name; otherwise the last created
    $m = $wins | Where-Object { [W32]::Title($_).StartsWith('Mission Planner 1.3') } | Select-Object -First 1
    if ($m) { return $m }
    return $wins | Select-Object -Last 1
}
switch ($Command) {
    'list' {
        foreach ($w in $wins) { $r = New-Object W32+RECT; [void][W32]::GetWindowRect($w, [ref]$r); '{0} | {1} | {2} | {3}x{4}' -f $w, [W32]::Title($w), [W32]::Class($w), ($r.Right - $r.Left), ($r.Bottom - $r.Top) }
    }
    'shot' {
        $h = Pick $A2
        $r = New-Object W32+RECT; [void][W32]::GetWindowRect($h, [ref]$r)
        $bmp = New-Object System.Drawing.Bitmap(($r.Right - $r.Left), ($r.Bottom - $r.Top))
        $g = [System.Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
        [void][W32]::PrintWindow($h, $hdc, 2); $g.ReleaseHdc($hdc); $g.Dispose()
        if ($A1.ToLower().EndsWith('.jpg')) { $bmp.Save($A1, [System.Drawing.Imaging.ImageFormat]::Jpeg) } else { $bmp.Save($A1, [System.Drawing.Imaging.ImageFormat]::Png) }; $bmp.Dispose()
        'saved {0} ({1}x{2}) of window "{3}"' -f $A1, ($r.Right - $r.Left), ($r.Bottom - $r.Top), [W32]::Title($h)
    }
    'click' {
        $h = Pick $A3
        $x = [int]$A1; $y = [int]$A2
        $c = [W32]::Deepest($h, $x, $y)
        $p = [W32]::ClientPointIn($h, $c, $x, $y)
        $lp = [IntPtr](($p.Y -shl 16) -bor ($p.X -band 0xFFFF))
        [void][W32]::PostMessage($c, 0x0200, [IntPtr]::Zero, $lp)          # WM_MOUSEMOVE
        [void][W32]::PostMessage($c, 0x0201, [IntPtr]1, $lp)               # WM_LBUTTONDOWN
        Start-Sleep -Milliseconds 80
        [void][W32]::PostMessage($c, 0x0202, [IntPtr]::Zero, $lp)          # WM_LBUTTONUP
        'clicked window-client ({0},{1}) -> child {2} class {3} text "{4}" at ({5},{6})' -f $x, $y, $c, [W32]::Class($c), [W32]::Title($c), $p.X, $p.Y
    }
    'text' {
        $h = Pick $A2
        foreach ($ch in $A1.ToCharArray()) { [void][W32]::PostMessage($h, 0x0102, [IntPtr][int]$ch, [IntPtr]1); Start-Sleep -Milliseconds 20 }
        'posted {0} characters' -f $A1.Length
    }
    'tree' {
        $h = Pick $A1
        foreach ($d in [W32]::Descendants($h)) {
            $r = New-Object W32+RECT; [void][W32]::GetWindowRect($d, [ref]$r)
            $tl = New-Object W32+POINT; $tl.X = $r.Left; $tl.Y = $r.Top; [void][W32]::ScreenToClient($h, [ref]$tl)
            '{0} | {1} | "{2}" | client ({3},{4}) {5}x{6} | visible={7} | enabled={8}' -f $d, [W32]::Class($d), [W32]::Title($d), $tl.X, $tl.Y, ($r.Right - $r.Left), ($r.Bottom - $r.Top), [W32]::IsWindowVisible($d), [W32]::IsWindowEnabled($d)
        }
    }
    'activate' {
        $h = Pick $A1
        [void][W32]::SendMessage($h, 0x001C, [IntPtr]1, [IntPtr]0)       # WM_ACTIVATEAPP
        [void][W32]::SendMessage($h, 0x0006, [IntPtr]1, [IntPtr]0)       # WM_ACTIVATE, WA_ACTIVE
        'activation messages sent to {0}' -f $h
    }
    'hwndclick' {
        # click at client point (x, y) of a specific child window handle (decimal)
        $c = [IntPtr][int64]$A1; $x = [int]$A2; $y = [int]$A3
        $lp = [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF))
        [void][W32]::PostMessage($c, 0x0200, [IntPtr]::Zero, $lp); [void][W32]::PostMessage($c, 0x0201, [IntPtr]1, $lp); Start-Sleep -Milliseconds 80; [void][W32]::PostMessage($c, 0x0202, [IntPtr]::Zero, $lp)
        'clicked {0} class {1} at ({2},{3})' -f $c, [W32]::Class($c), $x, $y
    }
    'bmclick' {
        # BM_CLICK: the button's own click, independent of mouse state
        $c = [IntPtr][int64]$A1
        [void][W32]::SendMessage($c, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero)
        'BM_CLICK sent to {0} class {1} text "{2}"' -f $c, [W32]::Class($c), [W32]::Title($c)
    }
    'hwndcombo' {
        $combo = [IntPtr][int64]$A1
        $idx = [W32]::SendMessage($combo, 0x014D, [IntPtr](-1), $A2)
        $parent = [W32]::GetParent($combo); $id = [W32]::GetDlgCtrlID($combo)
        [void][W32]::SendMessage($parent, 0x0111, [IntPtr]($id -bor (1 -shl 16)), $combo)
        'combo {0} class {1}: selected index {2}' -f $combo, [W32]::Class($combo), $idx
    }
    'combo' {
        $h = Pick $A4
        $x = [int]$A1; $y = [int]$A2
        $c = [W32]::Deepest($h, $x, $y)
        $cls = [W32]::Class($c)
        $combo = $c
        if ($cls -eq 'Edit') { $combo = [W32]::GetParent($c) }
        $idx = [W32]::SendMessage($combo, 0x014D, [IntPtr](-1), $A3)       # CB_SELECTSTRING
        $parent = [W32]::GetParent($combo)
        $id = [W32]::GetDlgCtrlID($combo)
        [void][W32]::SendMessage($parent, 0x0111, [IntPtr](($id) -bor (1 -shl 16)), $combo)       # WM_COMMAND, CBN_SELCHANGE
        'combo {0} class {1}: selected index {2}' -f $combo, [W32]::Class($combo), $idx
    }
}
