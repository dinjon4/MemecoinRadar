# Memecoin Radar - Windows için tek adımda kurulum.
#
# Kullanım (ikisinden biri):
#   1) kurulum.bat dosyasına çift tıklayın (bu dosya ile aynı klasörde olmalı).
#   2) PowerShell'e tek satır:  irm <bu dosyanın herkese açık adresi> | iex
#
# Yaptıkları: eksikse Python, Git ve GitHub aracını (gh) kurar; GitHub'a giriş ister (bir kez, tarayıcıda);
# programı %USERPROFILE%\MemecoinRadar klasörüne indirir; paketleri kurar; masaüstüne kısayol koyar; programı açar.
# Zaten kuruluysa sadece günceller ve açar. Bu dosyada gizli bilgi yoktur.
# NOT: Bu betik Windows'ta henüz denenmedi.

$ErrorActionPreference = "Stop"
$Repo = "dinjon4/MemecoinRadar"
$Dest = if ($env:MR_DEST) { $env:MR_DEST } else { Join-Path $env:USERPROFILE "MemecoinRadar" }
$Tools = Join-Path $env:LOCALAPPDATA "MemecoinRadar-araclar"
$PyVersion = "3.14.8"
$GhFallback = "2.102.0"

function Say($m)  { Write-Host "`n> $m" -ForegroundColor Green }
function Warn($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "`nX $m" -ForegroundColor Red; Read-Host "Kapatmak için Enter'a basın"; exit 1 }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Has-Winget { [bool](Get-Command winget -ErrorAction SilentlyContinue) }

# --- 1. Python (3.11 veya üstü) ---
function Find-Python {
    foreach ($cmd in @("py -3", "python")) {
        $exe, $arg = $cmd.Split(" ", 2)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $ok = & $exe @($arg | Where-Object { $_ }) -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
            if ($ok -eq "True") { return $cmd }
        } catch {}
    }
    return $null
}

Say "Python kontrol ediliyor"
$Py = Find-Python
if (-not $Py) {
    Say "Python $PyVersion indiriliyor (python.org)"
    $exe = Join-Path $env:TEMP "python-$PyVersion-amd64.exe"
    try { Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe" -OutFile $exe -UseBasicParsing }
    catch { Die "Python indirilemedi. İnternet bağlantınızı kontrol edin." }
    Start-Process $exe -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1" -Wait
    Refresh-Path
    $Py = Find-Python
    if (-not $Py) { Die "Python kurulumu tamamlanmadı. Bu dosyayı tekrar çalıştırın." }
}
$PyExe, $PyArg = $Py.Split(" ", 2)
$PyArgs = @($PyArg | Where-Object { $_ })
Write-Host "Python: $(& $PyExe @PyArgs --version)"

# --- 2. Git ---
Say "Git kontrol ediliyor"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (-not (Has-Winget)) { Die "Git bulunamadı. git-scm.com/download/win adresinden Git'i kurup tekrar deneyin." }
    winget install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    $env:Path += ";$env:ProgramFiles\Git\cmd"
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die "Git kurulamadı. git-scm.com/download/win adresinden kurun." }
}
Write-Host "git: $(git --version)"

# --- 3. GitHub aracı (gh) ---
Say "GitHub aracı (gh) kontrol ediliyor"
$Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $Gh -and (Test-Path "$Tools\gh\bin\gh.exe")) { $Gh = "$Tools\gh\bin\gh.exe" }
if (-not $Gh) {
    $ver = $GhFallback
    try { $ver = (Invoke-RestMethod "https://api.github.com/repos/cli/cli/releases/latest").tag_name.TrimStart("v") } catch {}
    Say "gh $ver indiriliyor"
    $zip = Join-Path $env:TEMP "gh.zip"
    try { Invoke-WebRequest "https://github.com/cli/cli/releases/download/v$ver/gh_${ver}_windows_amd64.zip" -OutFile $zip -UseBasicParsing }
    catch { Die "gh indirilemedi." }
    if (Test-Path "$Tools\gh") { Remove-Item "$Tools\gh" -Recurse -Force }
    Expand-Archive $zip -DestinationPath "$Tools\gh" -Force
    $Gh = "$Tools\gh\bin\gh.exe"
}
Write-Host "gh: $((& $Gh --version) | Select-Object -First 1)"

# --- 4. GitHub'a giriş (bir kez) ---
& $Gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Say "GitHub'a giriş"
    Warn "Birazdan bir kod ve tarayıcı açılacak. Sorulursa 'Authenticate Git with your GitHub credentials?' -> Y."
    Warn "Tarayıcıda GitHub hesabınızla giriş yapıp kodu girin ve 'Authorize' deyin."
    & $Gh auth login --web --git-protocol https --hostname github.com
    if ($LASTEXITCODE -ne 0) { Die "GitHub girişi tamamlanmadı." }
}
& $Gh auth setup-git *> $null   # güncelleme butonu (git pull) bu girişi kullansın
& $Gh repo view $Repo *> $null
if ($LASTEXITCODE -ne 0) { Die "GitHub hesabınızın '$Repo' deposuna erişimi yok. Depo sahibinin davetini e-postanızdan kabul edip tekrar deneyin." }

# --- 5. Programı indir veya güncelle ---
if (Test-Path (Join-Path $Dest ".git")) {
    Say "Program zaten kurulu, güncelleniyor"
    git -C $Dest pull --ff-only
    if ($LASTEXITCODE -ne 0) { Warn "Güncelleme yapılamadı; mevcut sürümle devam ediliyor." }
} else {
    if (Test-Path $Dest) { Die "$Dest klasörü var ama bir kurulum değil. Adını değiştirip tekrar deneyin." }
    Say "Program indiriliyor -> $Dest"
    & $Gh repo clone $Repo $Dest -- --quiet
    if ($LASTEXITCODE -ne 0) { Die "Program indirilemedi." }
}

# --- 6. Paketler ---
Say "Paketler kuruluyor (ilk seferde birkaç dakika sürebilir)"
Set-Location $Dest
$VenvPy = Join-Path $Dest ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    & $PyExe @PyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { Die "Sanal ortam oluşturulamadı." }
}
& $VenvPy -m pip install -q --upgrade pip *> $null
& $VenvPy -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Die "Paketler kurulamadı." }

# --- 7. Masaüstü kısayolu ---
if (-not $env:MR_NO_SHORTCUT) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    Set-Content -Path (Join-Path $desktop "Memecoin Radar.bat") -Encoding ASCII -Value "@call `"$Dest\start.bat`""
}

# --- 8. Başlat ---
$v = & $VenvPy -c "from radar import VERSION; print('v' + VERSION)"
Say "Kurulum tamam: $v"
Write-Host "Masaüstündeki 'Memecoin Radar' kısayoluyla açabilirsiniz."
Write-Host "İlk açılışta panelde Ayarlar -> Bağlantı anahtarları bölümünden kendi anahtarlarınızı girin."
if (-not $env:MR_NO_LAUNCH) { Start-Process (Join-Path $Dest "start.bat") -WorkingDirectory $Dest }
