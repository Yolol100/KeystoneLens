param(
    [Parameter(Mandatory=$true)][string]$Payload,
    [string]$SetupSource = '',
    [switch]$Silent,
    [switch]$Repair
)
$ErrorActionPreference = 'Stop'
$LocalAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$ProgramsDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
$StartupDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
$DesktopDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
$TempRoot = [System.IO.Path]::GetTempPath()
foreach ($requiredPath in @($LocalAppData, $ProgramsDir, $StartupDir, $DesktopDir, $TempRoot)) {
    if ([string]::IsNullOrWhiteSpace($requiredPath) -or -not [System.IO.Path]::IsPathRooted($requiredPath)) {
        throw 'Windows known-folder paths are unavailable or unsafe. Setup was stopped without making changes.'
    }
}
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName WindowsBase

$Version = '0.12.7'
$InstallDir = Join-Path $LocalAppData 'Programs\KeystoneLens'
$RuntimeRoot = Join-Path $LocalAppData 'Programs\KeystoneLensRuntime'
$PythonDir = Join-Path $RuntimeRoot 'Python313'
$PythonExe = Join-Path $PythonDir 'python.exe'
$PythonW = Join-Path $PythonDir 'pythonw.exe'
$PythonUrl = 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe'
$PythonSha = 'edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403'
$PythonInstallerCache = Join-Path $RuntimeRoot 'python-3.13.15-amd64.exe'
$InstallerCacheDir = Join-Path $LocalAppData 'Programs\KeystoneLensInstaller'
$RepairSetup = Join-Path $InstallerCacheDir 'KeystoneLens-Repair.exe'
$Work = Join-Path $TempRoot ('KeystoneLensInstall-' + [guid]::NewGuid().ToString('N'))
$PayloadDir = Join-Path $Work 'payload'
$PythonInstaller = Join-Path $Work 'python-runtime.exe'
$StageDir = $InstallDir + '.new'
$BackupDir = $InstallDir + '.old'
# Recover the last valid application tree after an interrupted atomic swap.
# Never delete the only rollback copy at startup: a power loss can happen after
# InstallDir -> BackupDir but before StageDir -> InstallDir.
if (-not (Test-Path $InstallDir) -and (Test-Path $BackupDir)) {
    try {
        Move-Item -LiteralPath $BackupDir -Destination $InstallDir -Force
    } catch {
        throw 'KeystoneLens found an interrupted update but could not restore the previous installation. No new installation work was started.'
    }
}
$ExistingInstall = Test-Path (Join-Path $InstallDir 'KeystoneLens.exe')
$ExistingState = Test-Path $InstallDir
$DesktopShortcut = Join-Path $DesktopDir 'KeystoneLens.lnk'
$StartupShortcut = Join-Path $StartupDir 'KeystoneLens.lnk'
$ModeLabel = if ($Repair) { 'Repair' } elseif ($ExistingInstall) { 'Update' } else { 'Setup' }

[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Title="KeystoneLens Setup" Height="430" Width="620" WindowStartupLocation="CenterScreen" ResizeMode="NoResize" Background="#0D1016" Foreground="#F3F5F7" FontFamily="Segoe UI">
  <Grid Margin="28">
    <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
    <StackPanel Grid.Row="0">
      <TextBlock Text="KeystoneLens" FontSize="24" FontWeight="SemiBold"/>
      <TextBlock x:Name="Mode" Text="Companion Setup" Foreground="#9099A8" Margin="0,4,0,0" FontSize="13"/>
    </StackPanel>
    <Border Grid.Row="1" Background="#141923" CornerRadius="10" Padding="22" Margin="0,24,0,20">
      <StackPanel>
        <TextBlock x:Name="Step" Text="Preparing installation" FontSize="15" FontWeight="SemiBold"/>
        <TextBlock x:Name="Detail" Text="Checking the required components…" Foreground="#AAB3C0" Margin="0,7,0,18" TextWrapping="Wrap"/>
        <ProgressBar x:Name="Progress" Height="8" Minimum="0" Maximum="100" Value="5" Foreground="#5DA8FF" Background="#2B3342" BorderThickness="0"/>
        <TextBlock x:Name="Percent" Text="5%" Foreground="#9099A8" HorizontalAlignment="Right" Margin="0,8,0,0"/>
        <StackPanel x:Name="FinishPanel" Visibility="Collapsed" Margin="0,18,0,0">
          <TextBlock Text="Installation complete" FontSize="14" FontWeight="SemiBold" Margin="0,0,0,8"/>
          <CheckBox x:Name="Launch" Content="Start KeystoneLens" IsChecked="True" Margin="0,5"/>
          <CheckBox x:Name="Desktop" Content="Create desktop shortcut" IsChecked="True" Margin="0,5"/>
          <CheckBox x:Name="Autostart" Content="Start KeystoneLens with Windows" IsChecked="False" Margin="0,5"/>
        </StackPanel>
      </StackPanel>
    </Border>
    <Grid Grid.Row="2">
      <TextBlock x:Name="Footer" Text="KeystoneLens installs per-user and does not require administrator access." Foreground="#9099A8" VerticalAlignment="Center" FontSize="11"/>
      <Button x:Name="Finish" Content="Finish" Width="96" Height="34" HorizontalAlignment="Right" Background="#5DA8FF" Foreground="#07101C" BorderThickness="0" FontWeight="SemiBold" Visibility="Collapsed"/>
    </Grid>
  </Grid>
</Window>
'@
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)
$window.Title = 'KeystoneLens ' + $ModeLabel
if ($Silent) { $window.ShowInTaskbar=$false; $window.WindowStyle='None'; $window.Opacity=0 }
$mode = $window.FindName('Mode'); $mode.Text = 'Companion ' + $ModeLabel
$step = $window.FindName('Step'); $detail = $window.FindName('Detail'); $progress = $window.FindName('Progress'); $percent = $window.FindName('Percent')
$finishPanel = $window.FindName('FinishPanel'); $finish = $window.FindName('Finish'); $launch = $window.FindName('Launch'); $desktop = $window.FindName('Desktop'); $autostart = $window.FindName('Autostart'); $footer = $window.FindName('Footer')
if ($ExistingState -or $Repair) {
    $desktop.IsChecked = Test-Path $DesktopShortcut
    $autostart.IsChecked = Test-Path $StartupShortcut
}

function New-Shortcut([string]$Path, [string]$Target, [string]$Icon) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.WorkingDirectory = Split-Path $Target
    $shortcut.IconLocation = $Icon
    $shortcut.Save()
}

function Stop-KeystoneLensProcesses {
    # Stop only processes that belong to this per-user KeystoneLens install.
    # A name-only process kill could terminate an unrelated executable with the
    # same filename. 0.12.6+ launchers also place Python in a kill-on-close Job
    # Object; the private-runtime fallback below cleanly upgrades older builds.
    $targets = @(
        @{ Name = 'KeystoneLens'; Path = (Join-Path $InstallDir 'KeystoneLens.exe') },
        @{ Name = 'pythonw'; Path = $PythonW }
    )
    foreach ($target in $targets) {
        $expected = [System.IO.Path]::GetFullPath([string]$target.Path)
        Get-Process -Name ([string]$target.Name) -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $actual = [System.IO.Path]::GetFullPath([string]$_.Path)
                if ([string]::Equals($actual, $expected, [System.StringComparison]::OrdinalIgnoreCase)) {
                    Stop-Process -Id $_.Id -Force -ErrorAction Stop
                }
            } catch {
                # Ignore inaccessible/stale processes rather than broadening the
                # kill scope. A still-running exact target will make the atomic
                # directory swap fail and trigger rollback instead.
            }
        }
    }
}

function Update-Step([int]$Value, [string]$Title, [string]$Text) {
    $progress.Value = $Value
    $percent.Text = ($Value.ToString() + '%')
    $step.Text = $Title
    $detail.Text = $Text
    $window.Dispatcher.Invoke([action]{}, [System.Windows.Threading.DispatcherPriority]::Background)
}

function Invoke-DownloadWithRetry([string]$Uri, [string]$OutFile, [int]$Attempts = 3) {
    $last = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
            Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -TimeoutSec 60
            return
        } catch {
            $last = $_.Exception
            if ($attempt -lt $Attempts) { Start-Sleep -Seconds ([Math]::Min(4, $attempt * 2)) }
        }
    }
    throw ('Download failed after ' + $Attempts + ' attempts: ' + $last.Message)
}

function Get-VerifiedPythonInstaller {
    if (Test-Path $PythonInstallerCache) {
        $cachedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonInstallerCache).Hash.ToLowerInvariant()
        if ($cachedHash -eq $PythonSha) { return $PythonInstallerCache }
        Remove-Item -LiteralPath $PythonInstallerCache -Force -ErrorAction SilentlyContinue
    }
    Update-Step 25 'Downloading runtime' 'Downloading the official Python runtime from python.org…'
    Invoke-DownloadWithRetry $PythonUrl $PythonInstaller
    Update-Step 42 'Verifying runtime' 'Checking the Python runtime SHA-256 value…'
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonInstaller).Hash.ToLowerInvariant()
    if ($actual -ne $PythonSha) { throw 'Python runtime integrity check failed.' }
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    Copy-Item -LiteralPath $PythonInstaller -Destination $PythonInstallerCache -Force
    return $PythonInstallerCache
}

function Install-AppRuntime {
    $runtimeInstaller = Get-VerifiedPythonInstaller
    Update-Step 52 'Installing dedicated runtime' 'Installing the KeystoneLens Python runtime in its dedicated per-user location…'
    $arguments = @(
        '/quiet',
        'InstallAllUsers=0',
        ('TargetDir="' + $PythonDir + '"'),
        'Include_launcher=0',
        'Include_test=0',
        'Include_doc=0',
        'Shortcuts=0',
        'PrependPath=0',
        'AppendPath=0',
        'AssociateFiles=0',
        'CompileAll=0',
        'Include_debug=0',
        'Include_symbols=0',
        'Include_tools=0',
        'Include_pip=1',
        'Include_tcltk=1'
    )
    $p = Start-Process -FilePath $runtimeInstaller -ArgumentList $arguments -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw ('Python runtime installation failed with code ' + $p.ExitCode) }
}

$script:InstallSucceeded = $false
$script:InstallFailed = $false
$script:NewAppApplied = $false
$window.add_ContentRendered({
    if ($script:InstallStarted) { return }
    $script:InstallStarted = $true
    try {
        Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $Work,$PayloadDir,$StageDir | Out-Null
        Update-Step 10 'Preparing' 'Unpacking and validating KeystoneLens components…'
        Expand-Archive -LiteralPath $Payload -DestinationPath $PayloadDir -Force
        Copy-Item -Path (Join-Path $PayloadDir '*') -Destination $StageDir -Recurse -Force

        $runtimeHealthy = (Test-Path $PythonExe) -and (Test-Path $PythonW)
        if ($runtimeHealthy) {
            & $PythonExe -I -c 'import sys, tkinter, pip; raise SystemExit(0 if sys.version_info[:3] == (3, 13, 15) else 3)' | Out-Null
            $runtimeHealthy = ($LASTEXITCODE -eq 0)
        }
        if (-not $runtimeHealthy) { Install-AppRuntime }
        if (-not (Test-Path $PythonExe) -or -not (Test-Path $PythonW)) { throw 'KeystoneLens dedicated Python runtime could not be located.' }
        & $PythonExe -I -c 'import tkinter, pip' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'The KeystoneLens dedicated runtime failed its Tk/pip check.' }

        Update-Step 68 'Installing components' 'Installing hash-locked KeystoneLens dependencies…'
        $packages = Join-Path $StageDir 'packages'
        New-Item -ItemType Directory -Force -Path $packages | Out-Null
        $lockFile = Join-Path $StageDir 'requirements-runtime.lock'
        & $PythonExe -m pip install --isolated --no-input --disable-pip-version-check --no-warn-script-location --no-cache-dir --timeout 30 --retries 3 --index-url https://pypi.org/simple --only-binary=:all: --require-hashes --no-deps --target $packages -r $lockFile
        if ($LASTEXITCODE -ne 0) { throw 'Hash-locked dependency installation failed.' }
        Set-Content -LiteralPath (Join-Path $StageDir 'pythonw.path') -Value $PythonW -Encoding ASCII
        & $PythonExe -I -c 'import os,sys; root=sys.argv[1]; sys.path[:0]=[os.path.join(root,"app"),os.path.join(root,"packages")]; import tkinter, requests, PIL, zxingcpp; import keystonelens_companion.__main__' $StageDir | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Staged runtime verification failed.' }

        Update-Step 84 'Applying safely' 'Replacing the previous Companion only after verification…'
        Stop-KeystoneLensProcesses
        # A stale .old can exist when a previous run lost power after the new
        # tree became active but before final cleanup. Only retire it here, after
        # the replacement tree has passed all staged runtime checks.
        Remove-Item -LiteralPath $BackupDir -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $InstallDir) { Move-Item -LiteralPath $InstallDir -Destination $BackupDir -Force }
        Move-Item -LiteralPath $StageDir -Destination $InstallDir -Force
        $script:NewAppApplied = $true

        # The new application/uninstaller is now live, so rollback no longer depends
        # on an older cached CPython maintenance installer. Keep only the pinned one.
        Get-ChildItem -LiteralPath $RuntimeRoot -Filter 'python-3.13.*-amd64.exe' -File -ErrorAction SilentlyContinue |
            Where-Object { -not [string]::Equals($_.FullName, $PythonInstallerCache, [System.StringComparison]::OrdinalIgnoreCase) } |
            Remove-Item -Force -ErrorAction SilentlyContinue

        Update-Step 91 'Configuring' 'Registering shortcuts, repair and uninstall support…'
        New-Item -ItemType Directory -Force -Path $InstallerCacheDir | Out-Null
        if ($SetupSource -and (Test-Path $SetupSource)) {
            $sourceFull = [System.IO.Path]::GetFullPath($SetupSource)
            $repairFull = [System.IO.Path]::GetFullPath($RepairSetup)
            if (-not [string]::Equals($sourceFull, $repairFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                Copy-Item -LiteralPath $SetupSource -Destination $RepairSetup -Force
            }
        }
        $programs = $ProgramsDir
        New-Shortcut (Join-Path $programs 'KeystoneLens.lnk') (Join-Path $InstallDir 'KeystoneLens.exe') (Join-Path $InstallDir 'KeystoneLens.ico')
        $reg = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\KeystoneLens'
        New-Item -Force -Path $reg | Out-Null
        New-ItemProperty -Path $reg -Name DisplayName -Value 'KeystoneLens Companion' -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $reg -Name DisplayVersion -Value $Version -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $reg -Name Publisher -Value 'KeystoneLens' -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $reg -Name InstallLocation -Value $InstallDir -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $reg -Name DisplayIcon -Value (Join-Path $InstallDir 'KeystoneLens.exe') -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $reg -Name UninstallString -Value ('"' + (Join-Path $InstallDir 'KeystoneLens-Uninstall.exe') + '"') -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $reg -Name QuietUninstallString -Value ('"' + (Join-Path $InstallDir 'KeystoneLens-Uninstall.exe') + '" --silent') -PropertyType String -Force | Out-Null
        if (Test-Path $RepairSetup) {
            New-ItemProperty -Path $reg -Name ModifyPath -Value ('"' + $RepairSetup + '" --repair') -PropertyType String -Force | Out-Null
            Remove-ItemProperty -Path $reg -Name NoModify -ErrorAction SilentlyContinue
            Remove-ItemProperty -Path $reg -Name NoRepair -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $BackupDir -Recurse -Force -ErrorAction SilentlyContinue

        Update-Step 100 'Ready' ('KeystoneLens Companion ' + $Version + ' is ready.')
        $script:InstallSucceeded = $true
        if ($Silent) { $window.Close(); return }
        $finishPanel.Visibility='Visible'; $finish.Visibility='Visible'; $footer.Text='Choose optional finishing actions, then click Finish.'
    } catch {
        $script:InstallFailed = $true
        if (Test-Path $BackupDir) {
            Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $BackupDir -Destination $InstallDir -Force -ErrorAction SilentlyContinue
        } elseif ($script:NewAppApplied -and -not $ExistingState) {
            # A first install has no previous tree to restore. Do not leave a
            # partially configured application directory behind if a later
            # registration/shortcut step fails after the staged swap.
            Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
        if ($Silent) { $window.Close(); return }
        $step.Text='Installation failed'; $detail.Text=$_.Exception.Message; $footer.Text='The previous installed release was kept when rollback was possible.'; $progress.Foreground='#EF6B6B'; $finish.Content='Close'; $finish.Visibility='Visible'
    } finally {
        Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
    }
})
$finish.add_Click({
    if ($script:InstallSucceeded) {
        try {
            $target = Join-Path $InstallDir 'KeystoneLens.exe'; $icon = Join-Path $InstallDir 'KeystoneLens.ico'
            if ($desktop.IsChecked) { New-Shortcut $DesktopShortcut $target $icon } else { Remove-Item $DesktopShortcut -Force -ErrorAction SilentlyContinue }
            if ($autostart.IsChecked) { New-Shortcut $StartupShortcut $target $icon } else { Remove-Item $StartupShortcut -Force -ErrorAction SilentlyContinue }
            if ($launch.IsChecked -and (Test-Path $target)) { Start-Process $target }
        } catch { [System.Windows.MessageBox]::Show($_.Exception.Message,'KeystoneLens','OK','Warning') | Out-Null }
    }
    $window.Close()
})
$window.add_Closing({ param($s,$e) if (-not $Silent -and $script:InstallStarted -and -not $finish.IsVisible) { $e.Cancel=$true } })
$null = $window.ShowDialog()
if ($script:InstallFailed) { exit 1 }
exit 0
