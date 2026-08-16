// pddwebworkbench_wrapper.cs
// Wrapper: launched by PddWorkbench.exe as if it were pddwebworkbench.exe.
// Appends --remote-debugging-port=9222 to all args, then calls the real
// pddwebworkbench_real.exe. Purpose: attach DevTools to PDD's embedded Chromium
// to inspect login/auth flow. Targets .NET Framework 4.x (no ArgumentList).
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class PddWrapper
{
    static string QuoteArg(string a)
    {
        if (string.IsNullOrEmpty(a)) return "\"\"";
        if (!a.Contains(" ") && !a.Contains("\"")) return a;
        // Standard Windows arg quoting: wrap in quotes, double embedded quotes
        return "\"" + a.Replace("\"", "\"\"") + "\"";
    }

    static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string realExe = Path.Combine(dir, "pddwebworkbench_real.exe");
        if (!File.Exists(realExe))
        {
            Console.Error.WriteLine("Missing real browser: " + realExe);
            return 2;
        }

        var sb = new StringBuilder();
        bool hasDebug = false;
        for (int i = 0; i < args.Length; i++)
        {
            if (i > 0) sb.Append(' ');
            sb.Append(QuoteArg(args[i]));
            if (args[i] != null && args[i].IndexOf("remote-debugging-port", StringComparison.OrdinalIgnoreCase) >= 0)
                hasDebug = true;
        }
        if (!hasDebug)
        {
            if (sb.Length > 0) sb.Append(' ');
            sb.Append("--remote-debugging-port=9222");
            sb.Append(" --remote-allow-origins=*");
        }

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = realExe,
                Arguments = sb.ToString(),
                UseShellExecute = false,
                WorkingDirectory = dir
            };
            var p = Process.Start(psi);
            if (p == null) return 3;
            p.WaitForExit();
            return p.ExitCode;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("Failed to launch real browser: " + e.Message);
            return 4;
        }
    }
}
