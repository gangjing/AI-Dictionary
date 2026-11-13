using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Automation;
using System.Windows.Forms;

/// <summary>
/// Native Windows capabilities used by the AI Dictionary tray shell:
/// UIA selection capture with secure-field guard and clipboard fallback,
/// clipboard monitoring, global hotkeys, and region screenshot capture.
/// Compiled at runtime with Add-Type; keep to C# 5 syntax for Windows PowerShell 5.1.
/// </summary>
public static class NativeWindowInfo
{
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")]
    public static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")]
    private static extern bool IsChild(IntPtr parent, IntPtr child);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hwnd, StringBuilder name, int count);

    public static bool IsOwnedBy(IntPtr hwnd, IntPtr parent)
    {
        if (hwnd == IntPtr.Zero || parent == IntPtr.Zero) return false;
        return hwnd == parent || IsChild(parent, hwnd);
    }

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hwnd, int command);
    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hwnd, IntPtr insertAfter, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")]
    private static extern IntPtr SetFocus(IntPtr hwnd);
    [DllImport("user32.dll")]
    private static extern bool AttachThreadInput(uint attach, uint attachTo, bool attachFlag);
    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    private static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOACTIVATE = 0x0010;
    private const uint SWP_SHOWWINDOW = 0x0040;

    public static void RaiseWithoutActivation(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return;
        // A topmost panel can still be ordered behind the active main window after Show();
        // SetWindowPos with NOACTIVATE puts it above without stealing keyboard focus.
        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
    }

    public static void Activate(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return;
        ShowWindow(hwnd, 5);
        SetForegroundWindow(hwnd);
    }

    public static void ForceForeground(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return;
        var foreground = GetForegroundWindow();
        uint foregroundPid;
        uint foregroundThread = GetWindowThreadProcessId(foreground, out foregroundPid);
        uint currentThread = GetCurrentThreadId();
        bool attached = false;
        try
        {
            if (foregroundThread != 0 && foregroundThread != currentThread)
            {
                attached = AttachThreadInput(currentThread, foregroundThread, true);
            }
            ShowWindow(hwnd, 5);
            SetForegroundWindow(hwnd);
            SetFocus(hwnd);
        }
        finally
        {
            if (attached) AttachThreadInput(currentThread, foregroundThread, false);
        }
    }

    public static IntPtr Foreground
    {
        get { return GetForegroundWindow(); }
    }

    public static string Title(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return "";
        var buffer = new StringBuilder(512);
        GetWindowText(hwnd, buffer, buffer.Capacity);
        return buffer.ToString();
    }

    public static string ProcessName(IntPtr hwnd)
    {
        try
        {
            uint pid;
            GetWindowThreadProcessId(hwnd, out pid);
            if (pid == 0) return "";
            using (var process = Process.GetProcessById((int)pid))
            {
                return process.ProcessName;
            }
        }
        catch
        {
            return "";
        }
    }

    public static string ClassName(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return "";
        var buffer = new StringBuilder(256);
        GetClassName(hwnd, buffer, buffer.Capacity);
        return buffer.ToString();
    }

    public static bool IsTerminalWindow(IntPtr hwnd)
    {
        var process = ProcessName(hwnd).ToLowerInvariant();
        var className = ClassName(hwnd).ToLowerInvariant();
        if (className.Contains("consolewindowclass") || className.Contains("cascadia_hosting_window")) return true;
        switch (process)
        {
            case "windowsterminal":
            case "conhost":
            case "cmd":
            case "powershell":
            case "pwsh":
            case "mintty":
            case "wt":
            case "alacritty":
            case "wezterm-gui":
                return true;
            default:
                return false;
        }
    }
}

public class SelectionResult
{
    public string Status = "";
    public string Text = "";
    public string AppName = "";
    public string ProcessName = "";
    public bool IsSecure = false;
    public string Method = "";
    public string Message = "";
    public int CursorX = 0;
    public int CursorY = 0;
}

public static class SelectionReader
{
    private const int MaxClipboardWaitMs = 450;

    public static SelectionResult ReadElement(AutomationElement element, int maxChars)
    {
        var result = new SelectionResult();
        var hwnd = NativeWindowInfo.Foreground;
        result.AppName = NativeWindowInfo.Title(hwnd);
        result.ProcessName = NativeWindowInfo.ProcessName(hwnd);
        Point cursor;
        if (NativeWindowInfo.GetCursorPos(out cursor))
        {
            result.CursorX = cursor.X;
            result.CursorY = cursor.Y;
        }
        if (element == null)
        {
            result.Status = "no_selection";
            result.Message = "没有可读取的焦点元素。";
            return result;
        }
        if (IsSecureElement(element))
        {
            result.Status = "blocked_secure_input";
            result.IsSecure = true;
            result.Method = "uia_secure_guard";
            result.Message = "检测到密码输入框，已拒绝读取。";
            return result;
        }
        var text = ReadTextPattern(element, maxChars);
        if (!String.IsNullOrEmpty(text))
        {
            result.Status = "ok";
            result.Text = Trim(text, maxChars);
            result.Method = "uia_element";
            result.Message = "已读取控件选中文本（自检路径）。";
        }
        else
        {
            result.Status = "no_selection";
            result.Method = "uia_element";
            result.Message = "控件没有可读取的选中文本。";
        }
        return result;
    }

    public static SelectionResult Read(int maxChars, bool allowClipboardFallback, bool restoreClipboard)
    {        var result = new SelectionResult();
        var hwnd = NativeWindowInfo.Foreground;
        result.AppName = NativeWindowInfo.Title(hwnd);
        result.ProcessName = NativeWindowInfo.ProcessName(hwnd);
        Point cursor;
        if (NativeWindowInfo.GetCursorPos(out cursor))
        {
            result.CursorX = cursor.X;
            result.CursorY = cursor.Y;
        }

        var element = SafeFocusedElement();
        if (element != null)
        {
            if (IsSecureElement(element))
            {
                result.Status = "blocked_secure_input";
                result.IsSecure = true;
                result.Method = "uia_secure_guard";
                result.Message = "检测到密码/安全输入框，已拒绝读取，也不会触发剪贴板回退。";
                return result;
            }

            var text = ReadTextPattern(element, maxChars);
            if (!String.IsNullOrEmpty(text))
            {
                result.Status = "ok";
                result.Text = Trim(text, maxChars);
                result.Method = "uia";
                result.Message = "已通过 Windows UI Automation 读取选中文本。";
                return result;
            }
        }

        if (!allowClipboardFallback)
        {
            result.Status = "no_selection";
            result.Method = "uia";
            result.Message = "未读取到选中文本。请先在目标应用中选中文字，或在设置中开启剪贴板回退。";
            return result;
        }

        // Ctrl+C in a terminal interrupts the running command instead of copying.
        if (NativeWindowInfo.IsTerminalWindow(hwnd))
        {
            result.Status = "no_selection";
            result.Method = "uia";
            result.Message = "终端窗口不支持安全复制回退（Ctrl+C 会中断命令）。请手动复制后使用剪贴板取词。";
            return result;
        }

        var copied = CopySelectionWithClipboard(restoreClipboard);
        if (!String.IsNullOrEmpty(copied))
        {
            result.Status = "ok";
            result.Text = Trim(copied, maxChars);
            result.Method = "clipboard";
            result.Message = "已通过受控复制读取选中文本（剪贴板内容已恢复）。";
            return result;
        }

        result.Status = "no_selection";
        result.Method = "clipboard";
        result.Message = "未读取到选中文本。部分应用禁止自动复制，请手动复制后再使用剪贴板取词。";
        return result;
    }

    private static AutomationElement SafeFocusedElement()    {
        try
        {
            return AutomationElement.FocusedElement;
        }
        catch
        {
            return null;
        }
    }

    private static bool IsSecureElement(AutomationElement element)
    {
        try
        {
            object value = element.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty);
            if (value is bool && (bool)value) return true;
            var controlType = element.Current.ControlType;
            if (controlType == ControlType.Edit)
            {
                object password = element.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty);
                if (password is bool && (bool)password) return true;
            }
        }
        catch
        {
        }
        return false;
    }

    private static string ReadTextPattern(AutomationElement element, int maxChars)
    {
        var current = element;
        for (int depth = 0; current != null && depth < 4; depth++)
        {
            try
            {
                object patternObject;
                if (current.TryGetCurrentPattern(TextPattern.Pattern, out patternObject))
                {
                    var pattern = (TextPattern)patternObject;
                    var ranges = pattern.GetSelection();
                    if (ranges != null && ranges.Length > 0)
                    {
                        var builder = new StringBuilder();
                        foreach (var range in ranges)
                        {
                            builder.Append(range.GetText(maxChars));
                            if (builder.Length >= maxChars) break;
                        }
                        if (builder.Length > 0) return builder.ToString();
                    }
                }
            }
            catch
            {
            }

            try
            {
                var walker = TreeWalker.ControlViewWalker;
                current = walker.GetParent(current);
            }
            catch
            {
                break;
            }
        }
        return null;
    }

    private static string CopySelectionWithClipboard(bool restoreClipboard)
    {
        IDataObject backup = null;
        try
        {
            backup = CloneClipboard();
        }
        catch
        {
        }

        string before = SafeGetClipboardText();
        string copied = null;
        try
        {
            SendKeys.SendWait("^c");
            var deadline = Environment.TickCount + MaxClipboardWaitMs;
            while (Environment.TickCount < deadline)
            {
                Thread.Sleep(25);
                var current = SafeGetClipboardText();
                if (!String.IsNullOrEmpty(current) && current != before)
                {
                    copied = current;
                    break;
                }
                if (String.IsNullOrEmpty(before) && !String.IsNullOrEmpty(current))
                {
                    copied = current;
                    break;
                }
            }
        }
        catch
        {
        }
        finally
        {
            if (restoreClipboard && backup != null)
            {
                try
                {
                    Clipboard.SetDataObject(backup, true);
                }
                catch
                {
                }
            }
        }
        return copied;
    }

    public static SelectionResult ReadClipboard(int maxChars)
    {
        var result = new SelectionResult();
        var hwnd = NativeWindowInfo.Foreground;
        result.AppName = NativeWindowInfo.Title(hwnd);
        result.ProcessName = NativeWindowInfo.ProcessName(hwnd);
        Point cursor;
        if (NativeWindowInfo.GetCursorPos(out cursor))
        {
            result.CursorX = cursor.X;
            result.CursorY = cursor.Y;
        }
        var text = SafeGetClipboardText();
        if (!String.IsNullOrEmpty(text))
        {
            result.Status = "ok";
            result.Text = Trim(text, maxChars);
            result.Method = "clipboard";
            result.Message = "已读取剪贴板文本。";
        }
        else
        {
            result.Status = "empty";
            result.Method = "clipboard";
            result.Message = "剪贴板中没有可翻译的文本。";
        }
        return result;
    }

    private static IDataObject CloneClipboard()
    {
        var source = Clipboard.GetDataObject();
        if (source == null) return null;
        var copy = new DataObject();
        foreach (var format in source.GetFormats(false))
        {
            try
            {
                var data = source.GetData(format, false);
                if (data != null) copy.SetData(format, data);
            }
            catch
            {
            }
        }
        return copy;
    }

    private static string SafeGetClipboardText()
    {
        for (int attempt = 0; attempt < 4; attempt++)
        {
            try
            {
                return Clipboard.ContainsText() ? Clipboard.GetText() : "";
            }
            catch
            {
                Thread.Sleep(20);
            }
        }
        return "";
    }

    private static string Trim(string text, int maxChars)
    {
        if (String.IsNullOrEmpty(text)) return "";
        text = text.Trim();
        if (maxChars > 0 && text.Length > maxChars) return text.Substring(0, maxChars);
        return text;
    }
}

public class ClipboardTextEventArgs : EventArgs
{
    public string Text;
    public ClipboardTextEventArgs(string text) { Text = text; }
}

public class ClipboardWatcher : IDisposable
{
    private readonly System.Windows.Forms.Timer timer;
    private string lastText = "";
    private bool disposed;

    public bool Enabled = false;
    public int MaxChars = 5000;
    public event EventHandler<ClipboardTextEventArgs> TextChanged;

    public ClipboardWatcher()
    {
        timer = new System.Windows.Forms.Timer();
        timer.Interval = 450;
        timer.Tick += delegate { Poll(); };
        timer.Start();
        // Do not pop up whatever was already on the clipboard before the feature was enabled.
        try
        {
            if (Clipboard.ContainsText()) lastText = Clipboard.GetText();
        }
        catch
        {
        }
    }

    /// <summary>Mark the current clipboard text as already seen (used after our own copy).</summary>
    public void SyncCurrent()
    {
        try
        {
            if (Clipboard.ContainsText()) lastText = Clipboard.GetText();
        }
        catch
        {
        }
    }

    /// <summary>Run one poll immediately (used by the native self-test).</summary>
    public void PollNow()
    {
        Poll();
    }

    public void Suppress(string text)
    {
        lastText = text ?? "";
    }

    private void Poll()
    {
        if (disposed || !Enabled) return;
        string text = "";
        try
        {
            if (!Clipboard.ContainsText()) return;
            text = Clipboard.GetText();
        }
        catch
        {
            return;
        }
        if (String.IsNullOrWhiteSpace(text)) return;
        if (text.Length > MaxChars) text = text.Substring(0, MaxChars);
        if (text == lastText) return;
        lastText = text;
        var handler = TextChanged;
        if (handler != null) handler(this, new ClipboardTextEventArgs(text));
    }

    public void Dispose()
    {
        disposed = true;
        if (timer != null) timer.Dispose();
    }
}

public class HotkeyEventArgs : EventArgs
{
    public int Id;
    public HotkeyEventArgs(int id) { Id = id; }
}

public class HotkeyWindow : NativeWindow, IDisposable
{
    private const int WM_HOTKEY = 0x0312;
    private const uint MOD_ALT = 0x0001;
    private const uint MOD_CONTROL = 0x0002;
    private const uint MOD_SHIFT = 0x0004;
    private const uint MOD_WIN = 0x0008;

    [DllImport("user32.dll")]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint modifiers, uint vk);
    [DllImport("user32.dll")]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    private readonly System.Collections.Generic.List<int> registered = new System.Collections.Generic.List<int>();
    public event EventHandler<HotkeyEventArgs> HotkeyPressed;

    public HotkeyWindow()
    {
        var parameters = new CreateParams();
        parameters.Caption = "AIDictHotkeySink";
        CreateHandle(parameters);
    }

    public bool Register(int id, string accelerator)
    {
        uint modifiers;
        uint key;
        if (!HotkeyParser.TryParse(accelerator, out modifiers, out key)) return false;
        if (!RegisterHotKey(Handle, id, modifiers, key)) return false;
        registered.Add(id);
        return true;
    }

    public void UnregisterAll()
    {
        foreach (var id in registered)
        {
            try { UnregisterHotKey(Handle, id); } catch { }
        }
        registered.Clear();
    }

    protected override void WndProc(ref Message message)
    {
        if (message.Msg == WM_HOTKEY)
        {
            var handler = HotkeyPressed;
            if (handler != null) handler(this, new HotkeyEventArgs(message.WParam.ToInt32()));
            return;
        }
        base.WndProc(ref message);
    }

    public void Dispose()
    {
        UnregisterAll();
        if (Handle != IntPtr.Zero) DestroyHandle();
    }
}

public static class HotkeyParser
{
    private const uint MOD_ALT = 0x0001;
    private const uint MOD_CONTROL = 0x0002;
    private const uint MOD_SHIFT = 0x0004;
    private const uint MOD_WIN = 0x0008;

    public static bool TryParse(string text, out uint modifiers, out uint key)
    {
        modifiers = 0;
        key = 0;
        if (String.IsNullOrWhiteSpace(text)) return false;
        var parts = text.Split(new[] { '+' }, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 2) return false;

        for (int i = 0; i < parts.Length - 1; i++)
        {
            var token = parts[i].Trim().ToLowerInvariant();
            if (token == "ctrl" || token == "control") modifiers |= MOD_CONTROL;
            else if (token == "alt" || token == "option") modifiers |= MOD_ALT;
            else if (token == "shift") modifiers |= MOD_SHIFT;
            else if (token == "win" || token == "meta" || token == "cmd" || token == "command") modifiers |= MOD_WIN;
            else return false;
        }

        var name = parts[parts.Length - 1].Trim();
        if (name.Length == 1)
        {
            char c = Char.ToUpperInvariant(name[0]);
            if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) { key = (uint)c; return true; }
        }
        var upper = name.ToUpperInvariant();
        if (upper.Length >= 2 && upper[0] == 'F')
        {
            int number;
            if (Int32.TryParse(upper.Substring(1), out number) && number >= 1 && number <= 24)
            {
                key = (uint)(0x70 + number - 1);
                return true;
            }
        }
        switch (upper)
        {
            case "SPACE": key = 0x20; return true;
            case "ENTER": case "RETURN": key = 0x0D; return true;
            case "TAB": key = 0x09; return true;
            case "ESC": case "ESCAPE": key = 0x1B; return true;
            case "BACKSPACE": key = 0x08; return true;
            case ",": key = 0xBC; return true;
            case ".": key = 0xBE; return true;
            case "/": key = 0xBF; return true;
            case ";": key = 0xBA; return true;
            case "'": key = 0xDE; return true;
            case "[": key = 0xDB; return true;
            case "]": key = 0xDD; return true;
            case "-": key = 0xBD; return true;
            case "=": key = 0xBB; return true;
            case "`": key = 0xC0; return true;
        }
        return false;
    }
}

public class RegionSelector : Form
{
    private Point startPoint;
    private bool dragging;
    private Rectangle selection;

    public Rectangle SelectedRegion = Rectangle.Empty;

    public RegionSelector()
    {
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = SystemInformation.VirtualScreen;
        TopMost = true;
        ShowInTaskbar = false;
        BackColor = Color.Black;
        Opacity = 0.32;
        Cursor = Cursors.Cross;
        KeyPreview = true;
        DoubleBuffered = true;
        Text = "AI Dictionary 截图识别";
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        Activate();
        Focus();
    }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        if (e.Button == MouseButtons.Left)
        {
            startPoint = e.Location;
            dragging = true;
            selection = Rectangle.Empty;
            Invalidate();
        }
        base.OnMouseDown(e);
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        if (dragging)
        {
            selection = Normalize(startPoint, e.Location);
            Invalidate();
        }
        base.OnMouseMove(e);
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        if (dragging && e.Button == MouseButtons.Left)
        {
            dragging = false;
            selection = Normalize(startPoint, e.Location);
            if (selection.Width > 8 && selection.Height > 8)
            {
                var screenRectangle = RectangleToScreen(selection);
                SelectedRegion = screenRectangle;
                DialogResult = DialogResult.OK;
            }
            else
            {
                DialogResult = DialogResult.Cancel;
            }
            Close();
        }
        base.OnMouseUp(e);
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape)
        {
            DialogResult = DialogResult.Cancel;
            Close();
        }
        base.OnKeyDown(e);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        if (selection.Width > 0 && selection.Height > 0)
        {
            using (var pen = new Pen(Color.FromArgb(255, 59, 130, 246), 2))
            {
                e.Graphics.DrawRectangle(pen, selection);
            }
            var label = selection.Width + " x " + selection.Height;
            using (var font = new Font("Segoe UI", 10, FontStyle.Bold))
            using (var brush = new SolidBrush(Color.White))
            using (var back = new SolidBrush(Color.FromArgb(200, 15, 23, 42)))
            {
                var size = e.Graphics.MeasureString(label, font);
                var point = new PointF(selection.Left, Math.Max(0, selection.Top - size.Height - 8));
                e.Graphics.FillRectangle(back, point.X, point.Y, size.Width + 10, size.Height + 4);
                e.Graphics.DrawString(label, font, brush, point.X + 5, point.Y + 2);
            }
        }
    }

    private static Rectangle Normalize(Point a, Point b)
    {
        return new Rectangle(
            Math.Min(a.X, b.X),
            Math.Min(a.Y, b.Y),
            Math.Abs(a.X - b.X),
            Math.Abs(a.Y - b.Y));
    }

    public static Rectangle SelectRegion()
    {
        using (var selector = new RegionSelector())
        {
            var result = selector.ShowDialog();
            return result == DialogResult.OK ? selector.SelectedRegion : Rectangle.Empty;
        }
    }
}

public static class ScreenCapture
{
    public static Bitmap Capture(Rectangle region)
    {
        if (region.Width <= 0 || region.Height <= 0) return null;
        var bitmap = new Bitmap(region.Width, region.Height);
        using (var graphics = Graphics.FromImage(bitmap))
        {
            graphics.CopyFromScreen(region.Location, Point.Empty, region.Size);
        }
        return bitmap;
    }
}
