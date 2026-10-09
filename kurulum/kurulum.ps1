# Memecoin Radar - Windows için tek adımda kurulum.
#
# Kullanım (ikisinden biri):
#   1) kurulum.bat dosyasına çift tıklayın (bu dosya ile aynı klasörde olmalı).
#   2) PowerShell'e tek satır:  irm <bu dosyanın herkese açık adresi> | iex
#
# Yaptıkları: eksikse Python ve Git'i kurar; hesap veya giriş gerekmez;
# programı %USERPROFILE%\MemecoinRadar klasörüne indirir; paketleri kurar; masaüstüne kısayol koyar; programı açar.
# Zaten kuruluysa sadece günceller ve açar. Bu dosyada gizli bilgi yoktur.
# NOT: Bu betik Windows'ta henüz denenmedi.

$ErrorActionPreference = "Stop"
$Repo = "dinjon4/MemecoinRadar"
$Dest = if ($env:MR_DEST) { $env:MR_DEST } else { Join-Path $env:USERPROFILE "MemecoinRadar" }
$PyVersion = "3.14.8"

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

# --- 3. Programı indir veya güncelle (depo herkese açık; hesap/giriş gerekmez) ---
if (Test-Path (Join-Path $Dest ".git")) {
    Say "Program zaten kurulu, güncelleniyor"
    git -C $Dest pull --ff-only
    if ($LASTEXITCODE -ne 0) { Warn "Güncelleme yapılamadı; mevcut sürümle devam ediliyor." }
} else {
    if (Test-Path $Dest) { Die "$Dest klasörü var ama bir kurulum değil. Adını değiştirip tekrar deneyin." }
    Say "Program indiriliyor -> $Dest"
    git clone --quiet "https://github.com/$Repo.git" $Dest
    if ($LASTEXITCODE -ne 0) { Die "Program indirilemedi. İnternet bağlantınızı kontrol edin." }
}

# --- 4. Paketler ---
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

# --- 5. Masaüstü kısayolu ---
if (-not $env:MR_NO_SHORTCUT) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    Set-Content -Path (Join-Path $desktop "Memecoin Radar.bat") -Encoding ASCII -Value "@call `"$Dest\start.bat`""
}

# --- 6. Başlat ---
$v = & $VenvPy -c "from radar import VERSION; print('v' + VERSION)"
Say "Kurulum tamam: $v"
Write-Host "Masaüstündeki 'Memecoin Radar' kısayoluyla açabilirsiniz."
Write-Host "İlk açılışta panelde Ayarlar -> Bağlantı anahtarları bölümünden kendi anahtarlarınızı girin."
if (-not $env:MR_NO_LAUNCH) { Start-Process (Join-Path $Dest "start.bat") -WorkingDirectory $Dest }
