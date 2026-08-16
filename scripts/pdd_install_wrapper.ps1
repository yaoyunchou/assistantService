# pdd_install_wrapper.ps1
# Install/uninstall pddwebworkbench.exe debug wrapper (adds --remote-debugging-port=9222).
# Auto-detects current PDD version dir (PDD auto-updates, version number changes).
param(
    [ValidateSet("install","uninstall","status")]
    [string]$Action = "install"
)

$root = "C:\Program Files (x86)\pinduoduo"
$verDir = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if (-not $verDir) { Write-Error "PDD install dir not found: $root"; exit 1 }
$dir = Join-Path $verDir.FullName "pddbrowser104"
if (-not (Test-Path $dir)) { Write-Error "pddbrowser104 not found: $dir"; exit 1 }
$exe = Join-Path $dir "pddwebworkbench.exe"
$realExe = Join-Path $dir "pddwebworkbench_real.exe"
$cs = Join-Path $dir "_wrapper.cs"
$csc = "C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

Write-Host ("PDD version dir: {0}" -f $verDir.Name)

switch ($Action) {
    "status" {
        Write-Host ("pddwebworkbench.exe exists: {0}" -f (Test-Path $exe))
        Write-Host ("pddwebworkbench_real.exe exists: {0}" -f (Test-Path $realExe))
        if (Test-Path $realExe) { Write-Host "-> wrapper installed" } else { Write-Host "-> original (no wrapper)" }
    }
    "install" {
        $log = Join-Path $env:TEMP "pdd_wrapper_install.log"
        ("=== install start " + (Get-Date) + " ===") | Out-File $log -Encoding UTF8
        ("dir=" + $dir) | Out-File $log -Append -Encoding UTF8
        ("exe=" + $exe + " exists=" + (Test-Path $exe)) | Out-File $log -Append -Encoding UTF8
        if (-not (Test-Path $exe)) { ("ERROR: not found " + $exe) | Out-File $log -Append -Encoding UTF8; Write-Error "not found $exe"; exit 1 }
        if (Test-Path $realExe) {
            Write-Host "real backup already exists, skip rename"
            ("real backup already exists, skip rename") | Out-File $log -Append -Encoding UTF8
        } else {
            try { Copy-Item $exe $realExe -Force -ErrorAction Stop; Write-Host "backed up pddwebworkbench.exe -> pddwebworkbench_real.exe"; ("backed up") | Out-File $log -Append -Encoding UTF8 }
            catch { ("backup failed: " + $_.Exception.Message) | Out-File $log -Append -Encoding UTF8; Write-Error $_; exit 5 }
        }
        $csSrc = Join-Path $PSScriptRoot "pdd_webworkbench_wrapper.cs"
        ("csSrc=" + $csSrc + " exists=" + (Test-Path $csSrc)) | Out-File $log -Append -Encoding UTF8
        try { Copy-Item $csSrc $cs -Force -ErrorAction Stop; ("copied wrapper.cs") | Out-File $log -Append -Encoding UTF8 }
        catch { ("copy cs failed: " + $_.Exception.Message) | Out-File $log -Append -Encoding UTF8; Write-Error $_; exit 6 }
        $out = $exe
        ("csc=" + $csc + " out=" + $out + " cs=" + $cs) | Out-File $log -Append -Encoding UTF8
        & $csc /nologo /platform:anycpu /out:"$out" "$cs" 2>&1 | Out-File $log -Append -Encoding UTF8
        ("csc exit=" + $LASTEXITCODE) | Out-File $log -Append -Encoding UTF8
        if ($LASTEXITCODE -ne 0) { ("compile failed exit " + $LASTEXITCODE) | Out-File $log -Append -Encoding UTF8; Write-Error "compile failed"; exit $LASTEXITCODE }
        Remove-Item $cs -Force -ErrorAction SilentlyContinue
        ("installed wrapper size=" + (Get-Item $out).Length) | Out-File $log -Append -Encoding UTF8
        Write-Host ("OK wrapper installed: " + $out + " size=" + (Get-Item $out).Length)
        Write-Host "Now launching PddWorkbench will add --remote-debugging-port=9222 to child browser"
    }
    "uninstall" {
        if (Test-Path $realExe) {
            Stop-Process -Name pddwebworkbench -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
            Copy-Item $realExe $exe -Force
            Remove-Item $realExe -Force -ErrorAction SilentlyContinue
            Write-Host "OK uninstalled wrapper, restored original pddwebworkbench.exe"
        } else {
            Write-Host "wrapper not installed, nothing to uninstall"
        }
    }
}
