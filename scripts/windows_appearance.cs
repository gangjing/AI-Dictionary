using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public static class DesktopAppearance {
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] public static extern IntPtr GetThreadDpiAwarenessContext();
    [DllImport("user32.dll")] public static extern bool AreDpiAwarenessContextsEqual(IntPtr a, IntPtr b);
    [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr window);
    [DllImport("dwmapi.dll")] private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr hwnd, int attribute, out int value, int size);

    public static void EnableDpi() {
        // The PowerShell host has its own manifest. Set the actual UI thread's context,
        // before constructing any WinForms or WebView2 HWND, not just the launcher.
        SetThreadDpiAwarenessContext(new IntPtr(-4)); // PER_MONITOR_AWARE_V2
    }
    public static void Theme(Form form, bool dark) {
        int enabled = dark ? 1 : 0;
        DwmSetWindowAttribute(form.Handle, 20, ref enabled, 4);
        int caption = dark ? 0x00201C19 : 0x00F9F8F6;
        int text = dark ? 0x00F4F2EF : 0x0027221D;
        DwmSetWindowAttribute(form.Handle, 35, ref caption, 4);
        DwmSetWindowAttribute(form.Handle, 36, ref text, 4);
        form.BackColor = dark ? Color.FromArgb(25,28,32) : Color.FromArgb(246,248,249);
    }
}

public class DictionaryWindow : Form {
    public Size LogicalSize = new Size(1120, 750);
    public Size LogicalMinimum = new Size(800, 520);
    public DictionaryWindow() { AutoScaleMode = AutoScaleMode.None; }
    protected override void OnHandleCreated(EventArgs e) {
        base.OnHandleCreated(e);
        float scale = DesktopAppearance.GetDpiForWindow(Handle) / 96f;
        MinimumSize = new Size((int)(LogicalMinimum.Width * scale), (int)(LogicalMinimum.Height * scale));
        var available = Screen.FromHandle(Handle).WorkingArea;
        ClientSize = new Size(Math.Min((int)(LogicalSize.Width * scale), available.Width - 40),
                              Math.Min((int)(LogicalSize.Height * scale), available.Height - 80));
    }
    [StructLayout(LayoutKind.Sequential)] private struct Rect { public int Left, Top, Right, Bottom; }
    protected override void WndProc(ref Message m) {
        if (m.Msg == 0x02E0) { // WM_DPICHANGED; WebView2 renders at the new native DPI.
            var bounds = (Rect)Marshal.PtrToStructure(m.LParam, typeof(Rect));
            float scale = (m.WParam.ToInt64() & 0xffff) / 96f;
            base.WndProc(ref m);
            MinimumSize = new Size((int)(LogicalMinimum.Width * scale), (int)(LogicalMinimum.Height * scale));
            Bounds = Rectangle.FromLTRB(bounds.Left, bounds.Top, bounds.Right, bounds.Bottom);
            return;
        }
        base.WndProc(ref m);
    }
}

public class DictionaryMenuColors : ProfessionalColorTable {
    private bool dark;
    public DictionaryMenuColors(bool darkMode) { dark = darkMode; UseSystemColors = false; }
    private Color Surface { get { return dark ? Color.FromArgb(31,35,41) : Color.White; } }
    public override Color ToolStripDropDownBackground { get { return Surface; } }
    public override Color ImageMarginGradientBegin { get { return Surface; } }
    public override Color ImageMarginGradientMiddle { get { return Surface; } }
    public override Color ImageMarginGradientEnd { get { return Surface; } }
    public override Color MenuItemSelected { get { return dark ? Color.FromArgb(48,57,71) : Color.FromArgb(232,239,249); } }
    public override Color MenuItemBorder { get { return MenuItemSelected; } }
    public override Color MenuBorder { get { return dark ? Color.FromArgb(61,67,77) : Color.FromArgb(218,223,230); } }
    public override Color SeparatorDark { get { return MenuBorder; } }
    public override Color SeparatorLight { get { return Surface; } }
    public override Color CheckBackground { get { return MenuItemSelected; } }
    public override Color CheckSelectedBackground { get { return MenuItemSelected; } }
}
