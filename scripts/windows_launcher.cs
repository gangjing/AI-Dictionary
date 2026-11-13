using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

internal static class Launcher {
    [STAThread]
    private static int Main() {
        bool created;
        using (var mutex = new Mutex(true, @"Local\AIDictionaryDesktop", out created)) {
            if (!created) {
                MessageBox.Show("AI Dictionary is already running. Open it from the system tray.", "AI Dictionary");
                return 0;
            }
            try {
                var root = AppDomain.CurrentDomain.BaseDirectory;
                var script = Path.Combine(root, @"app\scripts\windows_tray_shell.ps1");
                var start = new ProcessStartInfo {
                    FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe"),
                    Arguments = "-STA -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\"",
                    WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden, RedirectStandardError = true
                };
                using (var process = Process.Start(start)) {
                    var errors = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    if (process.ExitCode != 0) {
                        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AIDictionary");
                        Directory.CreateDirectory(dir);
                        var log = Path.Combine(dir, "startup-error.log");
                        File.WriteAllText(log, errors);
                        MessageBox.Show("Unable to start AI Dictionary. Details: " + log, "AI Dictionary");
                    }
                    return process.ExitCode;
                }
            } catch (Exception error) {
                MessageBox.Show(error.Message, "AI Dictionary");
                return 1;
            } finally { mutex.ReleaseMutex(); }
        }
    }
}
