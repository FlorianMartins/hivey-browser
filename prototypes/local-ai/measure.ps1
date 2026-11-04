# What does the AI engine cost a real game on this PC? For each profile: the
# game's frame times (PresentMon), the AI's speed, and what the detection of a
# running game sees. Nothing leaves the PC: the report stays in -WorkDir.
#
#   Open a PowerShell as administrator (PresentMon needs it), then:
#     powershell -ExecutionPolicy Bypass -File measure.ps1
#   Start the game within the countdown and stay in one stable scene.
#
# -Simulated runs frame_sim instead of a game (CI, no GPU).
param(
  [string]$Model = 'qwen3-1.7b',
  [int]$Seconds = 60,
  [int]$Rounds = 2,
  [int]$Countdown = 30,
  [string]$WorkDir = (Join-Path $env:LOCALAPPDATA 'HiveyLocalAI'),
  [switch]$Simulated,
  [string]$FrameSim = ''
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Raw = 'https://raw.githubusercontent.com/FlorianMartins/hivey-browser/local-ai-prototype/prototypes/local-ai'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class HiveyWin {
  [StructLayout(LayoutKind.Sequential)]
  public struct PowerThrottling { public uint Version, ControlMask, StateMask; }
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool SetProcessInformation(IntPtr process, int infoClass, ref PowerThrottling info, int size);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool SetProcessInformation(IntPtr process, int infoClass, ref uint info, int size);
  [DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr process);
  [DllImport("ntdll.dll")] public static extern int NtResumeProcess(IntPtr process);
  [DllImport("shell32.dll")] static extern int SHQueryUserNotificationState(out int state);
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);

  // EcoQoS (ProcessPowerThrottling, execution speed): efficient cores first.
  public static bool EcoQos(IntPtr process) {
    var s = new PowerThrottling { Version = 1, ControlMask = 1, StateMask = 1 };
    return SetProcessInformation(process, 4, ref s, Marshal.SizeOf(s));
  }
  // ProcessMemoryPriority, MEMORY_PRIORITY_VERY_LOW: its pages leave RAM first.
  public static bool LowMemory(IntPtr process) { uint p = 1; return SetProcessInformation(process, 0, ref p, 4); }
  // 3 = a Direct3D application in exclusive full screen (QUNS_RUNNING_D3D_FULL_SCREEN).
  public static int NotificationState() { int s; return SHQueryUserNotificationState(out s) == 0 ? s : -1; }
  public static uint ForegroundProcess() { uint p; GetWindowThreadProcessId(GetForegroundWindow(), out p); return p; }
}
'@

function Say($text) { Write-Host "[hivey] $text" }
function Beep($hz, $ms) { try { [console]::Beep($hz, $ms) } catch { } }

# Files that sit next to this script, else the branch's (a lone downloaded script).
function Support($name) {
  $here = Join-Path $PSScriptRoot $name
  if (Test-Path $here) { return $here }
  $dest = Join-Path $WorkDir ($name -replace '/', '_')
  Invoke-WebRequest "$Raw/$name" -UseBasicParsing -OutFile $dest
  return $dest
}

function Fetch($url, $dest, $digest) {
  if ((Test-Path $dest) -and (Get-FileHash $dest -Algorithm SHA256).Hash -eq $digest.ToUpper()) { return }
  Say "Téléchargement de $(Split-Path $dest -Leaf)"
  Invoke-WebRequest $url -UseBasicParsing -OutFile "$dest.part"
  $got = (Get-FileHash "$dest.part" -Algorithm SHA256).Hash
  if ($got -ne $digest.ToUpper()) {
    Remove-Item "$dest.part"
    throw "$(Split-Path $dest -Leaf): empreinte $got au lieu de $digest"
  }
  Move-Item -Force "$dest.part" $dest
}

function Engine($key) {
  $e = $Manifest.engine.$key
  $dir = Join-Path $WorkDir "llama-$($Manifest.engine.version)-$key"
  $zip = "$dir.zip"
  Fetch $e.url $zip $e.sha256
  if (-not (Test-Path $dir)) { Expand-Archive $zip -DestinationPath $dir }
  return (Get-ChildItem $dir -Recurse -Filter llama-server.exe | Select-Object -First 1).FullName
}

function Start-Ai($prof) {
  $port = Get-Random -Minimum 20000 -Maximum 60000
  $key = [guid]::NewGuid().ToString('N')
  $argv = @('-m', "`"$ModelPath`"", '--host', '127.0.0.1', '--port', $port, '--api-key', $key, '-np', '1', '-c', '4096',
            '--threads-http', '1', '--no-repack') + $prof.args
  $exe = if ($prof.gpu) { $VulkanExe } else { $CpuExe }
  $log = Join-Path $WorkDir 'engine.log'
  $p = Start-Process -FilePath $exe -ArgumentList $argv -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$log.out" -RedirectStandardError "$log.err"
  if ($prof.low) {
    $p.PriorityClass = 'Idle'
    $eco = [HiveyWin]::EcoQos($p.Handle)
    $mem = [HiveyWin]::LowMemory($p.Handle)
    Say "Priorité basse, EcoQoS : $eco, mémoire basse : $mem"
  }
  $deadline = (Get-Date).AddMinutes(3)
  while ($true) {
    if ($p.HasExited) { throw "le moteur s'est arrêté (voir $log.err)" }
    if ((Get-Date) -gt $deadline) { throw 'le moteur ne répond pas' }
    try { $null = Invoke-WebRequest "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 2; break }
    catch { Start-Sleep -Milliseconds 300 }
  }
  return @{ process = $p; port = $port; key = $key }
}

# Asks for answers in a loop, from another process; each result goes to a file.
function Start-Load($ai, $out) {
  $body = @{ prompt = $Prompt; n_predict = 150; ignore_eos = $true; cache_prompt = $false } | ConvertTo-Json -Compress
  return Start-Job -ArgumentList $ai.port, $ai.key, $body, $out -ScriptBlock {
    param($port, $key, $body, $out)
    $bytes = [Text.Encoding]::UTF8.GetBytes($body)
    while ($true) {
      # The raw text: Windows PowerShell's JSON reader refuses this response.
      $r = Invoke-WebRequest "http://127.0.0.1:$port/completion" -UseBasicParsing -Method Post -Body $bytes `
        -ContentType 'application/json' -Headers @{ Authorization = "Bearer $key" } -TimeoutSec 600
      if ($r.Content -match '"predicted_per_second"\s*:\s*([0-9.eE+-]+)') { Add-Content $out $Matches[1] }
    }
  }
}

function Percentile($sorted, $p) { return $sorted[[math]::Min($sorted.Count - 1, [math]::Floor($p / 100 * $sorted.Count))] }

function Read-Frames($csv) {
  $ms = Import-Csv $csv | ForEach-Object { [double]::Parse($_.MsBetweenPresents, [Globalization.CultureInfo]::InvariantCulture) } | Where-Object { $_ -gt 0 }
  if (-not $ms) { throw "PresentMon n'a vu aucune image de $GameName" }
  $sorted = @($ms | Sort-Object)
  $tail = [math]::Max(1, [math]::Floor($sorted.Count / 100))
  $slow = ($sorted | Select-Object -Last $tail | Measure-Object -Average).Average
  return @{
    frames = $sorted.Count
    fps = [math]::Round(1000 / ($sorted | Measure-Object -Average).Average, 1)
    one_pct_low_fps = [math]::Round(1000 / $slow, 1)
    p99_ms = [math]::Round((Percentile $sorted 99), 2)
  }
}

function Capture($name) {
  if ($Simulated) {
    $json = & $FrameSim --iters $Iters --threads 2 --seconds $Seconds
    return $json | ConvertFrom-Json
  }
  $csv = Join-Path $WorkDir "frames-$name.csv"
  if (Test-Path $csv) { Remove-Item $csv }
  & $PresentMon --process_name $GameName --output_file $csv --timed $Seconds --terminate_after_timed `
    --no_console_stats --stop_existing_session --session_name HiveyMeasure | Out-Null
  return [pscustomobject](Read-Frames $csv)
}

# What a governor would see: exclusive full screen, and the GPU's 3D load.
function Sample-Signals {
  $gpu = $null
  try {
    $c = Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -ErrorAction Stop
    $gpu = [math]::Round(($c.CounterSamples | Measure-Object CookedValue -Sum).Sum, 0)
  } catch { }
  return @{ quns = [HiveyWin]::NotificationState(); gpu_3d = $gpu }
}

New-Item -ItemType Directory -Force $WorkDir | Out-Null
$Manifest = Get-Content (Support 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$Prompt = Get-Content (Support 'corpus/page.txt') -Raw -Encoding UTF8
$m = $Manifest.models.$Model
if (-not $m) { throw "modèle inconnu : $Model" }
$ModelPath = Join-Path $WorkDir $m.file
Fetch "https://huggingface.co/$($m.repo)/resolve/$($m.revision)/$($m.file)" $ModelPath $m.sha256
$CpuExe = Engine 'windows-cpu'
$Physical = (Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum

$Profiles = [ordered]@{
  'baseline'   = $null
  'normal-all' = @{ args = @('-t', "$Physical"); low = $false }
  'bride-4t'   = @{ args = @('-t', '4', '--poll', '0'); low = $true }
  'bride-2t'   = @{ args = @('-t', '2', '--poll', '0'); low = $true }
  'pause'      = @{ args = @('-t', '2', '--poll', '0'); low = $true; paused = $true }
}

if ($Simulated) {
  if (-not $FrameSim) { throw '-Simulated demande -FrameSim' }
  $Iters = [int](& $FrameSim --calibrate --work-ms 3)
  $GameName = 'frame_sim'
} else {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  if (-not (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Lance PowerShell en administrateur : PresentMon en a besoin.'
  }
  $pm = $Manifest.presentmon
  $PresentMon = Join-Path $WorkDir 'PresentMon.exe'
  Fetch $pm.url $PresentMon $pm.sha256
  $VulkanExe = Engine 'windows-vulkan'
  $Profiles['gpu-vulkan'] = @{ args = @('-ngl', '99'); low = $false; gpu = $true }
  Say "Lance ton jeu maintenant et mets-toi dans une scène stable. Mesure dans $Countdown s."
  Start-Sleep $Countdown
  $fg = [HiveyWin]::ForegroundProcess()
  $GameName = "$((Get-Process -Id $fg).ProcessName).exe"
  if ($GameName -match '^(powershell|pwsh|WindowsTerminal|explorer)') { throw "Le jeu n'est pas au premier plan ($GameName)." }
  Say "Jeu détecté : $GameName. Reste dans le jeu, 2 bips marquent la fin."
}

$Rows = @()
for ($round = 0; $round -lt $Rounds; $round++) {
  foreach ($name in ($Profiles.Keys | Get-Random -Count $Profiles.Count)) {
    $prof = $Profiles[$name]
    $ai = $null; $load = $null
    $speeds = Join-Path $WorkDir "speed-$name-$round.txt"
    if (Test-Path $speeds) { Remove-Item $speeds }
    Beep 660 120
    try {
      if ($prof) {
        $ai = Start-Ai $prof
        if ($prof.paused) { $null = [HiveyWin]::NtSuspendProcess($ai.process.Handle) }
        else { $load = Start-Load $ai $speeds; Start-Sleep 5 }
      }
      $signals = Sample-Signals
      $row = Capture "$name-$round"
      $tps = if (Test-Path $speeds) { Get-Content $speeds | ForEach-Object { [double]::Parse($_, [Globalization.CultureInfo]::InvariantCulture) } } else { $null }
      $out = [ordered]@{
        profile = $name; round = $round; fps = $row.fps; one_pct_low_fps = $row.one_pct_low_fps
        ai_tok_s = if ($tps) { [math]::Round(($tps | Measure-Object -Average).Average, 1) } else { $null }
        quns = $signals.quns; gpu_3d_pct = $signals.gpu_3d
      }
      $Rows += [pscustomobject]$out
      Say "$name : 1 % low $($row.one_pct_low_fps), IA $($out.ai_tok_s) tokens/s"
    } finally {
      if ($load) { Stop-Job $load; Remove-Job $load -Force }
      if ($ai) {
        if ($prof.paused) { $null = [HiveyWin]::NtResumeProcess($ai.process.Handle) }
        Stop-Process -Id $ai.process.Id -Force -ErrorAction SilentlyContinue
      }
    }
  }
}

$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$gpus = (Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) -join ' + '
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$report = [ordered]@{ game = $GameName; model = $Model; seconds = $Seconds; cpu = $cpu; gpu = $gpus; ram_gb = $ram; rows = $Rows }
$path = Join-Path $WorkDir 'rapport.json'
$report | ConvertTo-Json -Depth 4 | Set-Content $path -Encoding UTF8
$Rows | Sort-Object profile, round | Format-Table -AutoSize | Out-String | Write-Host
Beep 880 200; Beep 880 200
Say "Terminé. Rapport à m'envoyer : $path (il ne part nulle part tout seul)."
