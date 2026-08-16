$dir104 = "C:\Program Files (x86)\pinduoduo\3.7.0.12\pddbrowser104"
$dir75  = "C:\Program Files (x86)\pinduoduo\3.7.0.12\pddbrowser"
foreach ($d in @($dir104,$dir75)) {
    Write-Host "=== $d ==="
    Get-ChildItem -LiteralPath $d -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "pddweb*" -or $_.Name -like "_wrapper*" -or $_.Name -like "*.cs" -or $_.Name -like "pddwebwork*" } |
        ForEach-Object { "{0,-32} {1,12}  {2}" -f $_.Name, $_.Length, $_.LastWriteTime }
    Write-Host ""
}
Write-Host "=== 全盘搜索 pddwebworkbench.exe (含备份) ==="
Get-ChildItem -Path "C:\Program Files (x86)\pinduoduo","C:\Users\Public\Documents\PDD","$env:LOCALAPPDATA\PDDworkbenchUpdate" -Recurse -Filter "pddwebworkbench*.exe" -ErrorAction SilentlyContinue |
    Select-Object FullName, Length, LastWriteTime | Format-Table -AutoSize
