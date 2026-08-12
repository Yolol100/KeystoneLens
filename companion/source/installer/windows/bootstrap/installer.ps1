param(
    [Parameter(Mandatory=$true)][string]$Payload,
    [string]$SetupSource = '',
    [string]$ResultFile = '',
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
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Net.Http

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
$DesktopShortcut = Join-Path $DesktopDir 'KeystoneLens.lnk'
$StartupShortcut = Join-Path $StartupDir 'KeystoneLens.lnk'
$WoWWatcherShortcut = Join-Path $StartupDir 'KeystoneLens-WoW-Watcher.lnk'
$InstallLogDir = Join-Path $LocalAppData 'KeystoneLens'
$InstallLog = Join-Path $InstallLogDir 'install.log'
$MaxInstallLogBytes = 1024 * 1024

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
$ModeLabel = if ($Repair) { 'Repair' } elseif ($ExistingInstall) { 'Update' } else { 'Setup' }
$PreviousLaunchMode = if (Test-Path $WoWWatcherShortcut) { 'wow' } elseif (Test-Path $StartupShortcut) { 'windows' } else { 'manual' }

function Initialize-InstallLog {
    New-Item -ItemType Directory -Force -Path $InstallLogDir | Out-Null
    if (Test-Path $InstallLog) {
        try {
            if ((Get-Item -LiteralPath $InstallLog).Length -gt $MaxInstallLogBytes) {
                Move-Item -LiteralPath $InstallLog -Destination ($InstallLog + '.previous') -Force
            }
        } catch { }
    }
}

function Write-InstallLog([string]$Message) {
    try {
        $stamp = [DateTimeOffset]::Now.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz')
        [System.IO.File]::AppendAllText($InstallLog, ('[' + $stamp + '] ' + $Message + [Environment]::NewLine), [System.Text.Encoding]::UTF8)
    } catch { }
}

Initialize-InstallLog
Write-InstallLog ('KeystoneLens ' + $ModeLabel + ' ' + $Version + ' started.')

[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="KeystoneLens Setup" Height="540" Width="690" WindowStartupLocation="CenterScreen" ResizeMode="NoResize" Background="#0D1016" Foreground="#F3F5F7" FontFamily="Segoe UI">
  <Grid Margin="28">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>
    <Grid Grid.Row="0">
      <Grid.ColumnDefinitions><ColumnDefinition Width="Auto"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
      <Image x:Name="BrandIcon" Width="46" Height="46" Margin="0,0,14,0" VerticalAlignment="Center"/>
      <StackPanel Grid.Column="1" VerticalAlignment="Center">
        <TextBlock Text="KeystoneLens" FontSize="25" FontWeight="SemiBold"/>
        <TextBlock x:Name="Mode" Text="Companion Setup" Foreground="#9099A8" Margin="0,4,0,0" FontSize="13"/>
      </StackPanel>
    </Grid>

    <Border Grid.Row="1" Background="#141923" CornerRadius="10" Padding="22" Margin="0,24,0,18">
      <Grid>
        <StackPanel x:Name="DecisionPanel">
          <TextBlock Text="Install KeystoneLens Companion" FontSize="17" FontWeight="SemiBold"/>
          <TextBlock Text="Choose how KeystoneLens should start. These options can be changed by running Setup again." Foreground="#AAB3C0" Margin="0,7,0,18" TextWrapping="Wrap"/>
          <TextBlock Text="START BEHAVIOR" Foreground="#9099A8" FontSize="11" FontWeight="SemiBold" Margin="0,0,0,8"/>
          <RadioButton x:Name="ManualRadio" Content="Start manually" GroupName="LaunchMode" IsChecked="True" Margin="0,4" Foreground="#F3F5F7"/>
          <TextBlock Text="Open KeystoneLens from the Start menu or desktop shortcut." Foreground="#9099A8" FontSize="11" Margin="22,0,0,7"/>
          <RadioButton x:Name="WindowsRadio" Content="Start with Windows" GroupName="LaunchMode" Margin="0,4" Foreground="#F3F5F7"/>
          <TextBlock Text="Start the Companion automatically after you sign in to Windows." Foreground="#9099A8" FontSize="11" Margin="22,0,0,7"/>
          <RadioButton x:Name="WowRadio" Content="Start when World of Warcraft Retail starts" GroupName="LaunchMode" Margin="0,4" Foreground="#F3F5F7"/>
          <TextBlock Text="A lightweight watcher waits for a real _retail_\Wow.exe process, then opens the Companion." Foreground="#9099A8" FontSize="11" Margin="22,0,0,14" TextWrapping="Wrap"/>
          <Separator Background="#2B3342" Margin="0,2,0,12"/>
          <CheckBox x:Name="Desktop" Content="Create desktop shortcut" IsChecked="False" Margin="0,5" Foreground="#F3F5F7"/>
          <CheckBox x:Name="LaunchAfter" Content="Launch KeystoneLens after installation" IsChecked="True" Margin="0,5" Foreground="#F3F5F7"/>
          <TextBlock Text="Setup installs the Companion, a private Python runtime, required libraries, Start menu entry, and repair/uninstall support." Foreground="#9099A8" FontSize="11" Margin="0,12,0,0" TextWrapping="Wrap"/>
        </StackPanel>

        <StackPanel x:Name="ProgressPanel" Visibility="Collapsed">
          <TextBlock x:Name="Step" Text="Preparing installation" FontSize="17" FontWeight="SemiBold"/>
          <TextBlock x:Name="Detail" Text="Checking required components…" Foreground="#AAB3C0" Margin="0,7,0,16" TextWrapping="Wrap" MinHeight="34"/>
          <ProgressBar x:Name="Progress" Height="9" Minimum="0" Maximum="100" Value="5" Foreground="#5DA8FF" Background="#2B3342" BorderThickness="0"/>
          <TextBlock x:Name="Percent" Text="5%" Foreground="#9099A8" HorizontalAlignment="Right" Margin="0,7,0,12"/>
          <Expander x:Name="DetailsExpander" Header="Details" Foreground="#AAB3C0" IsExpanded="False">
            <Border Background="#11161F" BorderBrush="#2B3342" BorderThickness="1" CornerRadius="6" Padding="8" Margin="0,7,0,0">
              <TextBox x:Name="DetailsText" Height="118" Background="#11161F" Foreground="#AAB3C0" BorderThickness="0" IsReadOnly="True" TextWrapping="Wrap" VerticalScrollBarVisibility="Auto" FontFamily="Consolas" FontSize="10.5"/>
            </Border>
          </Expander>
        </StackPanel>

        <StackPanel x:Name="FinishPanel" Visibility="Collapsed" VerticalAlignment="Center">
          <TextBlock Text="✓" Foreground="#52D273" FontSize="42" HorizontalAlignment="Center"/>
          <TextBlock Text="KeystoneLens is ready" FontSize="20" FontWeight="SemiBold" HorizontalAlignment="Center" Margin="0,8,0,0"/>
          <TextBlock x:Name="FinishDetail" Text="The Companion was installed successfully." Foreground="#AAB3C0" TextAlignment="Center" TextWrapping="Wrap" Margin="40,9,40,0"/>
          <TextBlock x:Name="FinishWarning" Text="" Foreground="#F1C75B" TextAlignment="Center" TextWrapping="Wrap" Margin="40,12,40,0"/>
        </StackPanel>

        <StackPanel x:Name="ErrorPanel" Visibility="Collapsed" VerticalAlignment="Center">
          <TextBlock Text="!" Foreground="#EF6B6B" FontSize="38" FontWeight="Bold" HorizontalAlignment="Center"/>
          <TextBlock x:Name="ErrorTitle" Text="Installation could not be completed" FontSize="19" FontWeight="SemiBold" HorizontalAlignment="Center" Margin="0,8,0,0"/>
          <TextBlock x:Name="ErrorDetail" Text="" Foreground="#AAB3C0" TextAlignment="Center" TextWrapping="Wrap" Margin="36,9,36,0"/>
          <Button x:Name="CopyDiagnostics" Content="Copy diagnostics" Width="126" Height="30" HorizontalAlignment="Center" Margin="0,16,0,0" Background="#2B3342" Foreground="#F3F5F7" BorderThickness="0"/>
        </StackPanel>
      </Grid>
    </Border>

    <TextBlock x:Name="Footer" Grid.Row="2" Text="Installs for this Windows account only. Administrator access is not required." Foreground="#9099A8" FontSize="11" Margin="0,0,0,12"/>
    <StackPanel Grid.Row="3" Orientation="Horizontal" HorizontalAlignment="Right">
      <Button x:Name="Cancel" Content="Cancel" Width="92" Height="34" Margin="0,0,10,0" Background="#2B3342" Foreground="#F3F5F7" BorderThickness="0"/>
      <Button x:Name="Install" Content="Install" Width="100" Height="34" Background="#5DA8FF" Foreground="#07101C" BorderThickness="0" FontWeight="SemiBold"/>
      <Button x:Name="Open" Content="Open KeystoneLens" Width="132" Height="34" Margin="0,0,10,0" Background="#5DA8FF" Foreground="#07101C" BorderThickness="0" FontWeight="SemiBold" Visibility="Collapsed"/>
      <Button x:Name="Done" Content="Done" Width="92" Height="34" Background="#2B3342" Foreground="#F3F5F7" BorderThickness="0" Visibility="Collapsed"/>
      <Button x:Name="Close" Content="Close" Width="92" Height="34" Background="#2B3342" Foreground="#F3F5F7" BorderThickness="0" Visibility="Collapsed"/>
    </StackPanel>
  </Grid>
</Window>
'@
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)
$window.Title = 'KeystoneLens ' + $ModeLabel
if ($Silent) { $window.ShowInTaskbar=$false; $window.WindowStyle='None'; $window.Opacity=0 }

$mode = $window.FindName('Mode'); $mode.Text = 'Companion ' + $ModeLabel + ' • ' + $Version
$brandIcon = $window.FindName('BrandIcon')
$decisionPanel = $window.FindName('DecisionPanel'); $progressPanel = $window.FindName('ProgressPanel'); $finishPanel = $window.FindName('FinishPanel'); $errorPanel = $window.FindName('ErrorPanel')
$manualRadio = $window.FindName('ManualRadio'); $windowsRadio = $window.FindName('WindowsRadio'); $wowRadio = $window.FindName('WowRadio')
$desktop = $window.FindName('Desktop'); $launchAfter = $window.FindName('LaunchAfter')
$step = $window.FindName('Step'); $detail = $window.FindName('Detail'); $progress = $window.FindName('Progress'); $percent = $window.FindName('Percent'); $detailsText = $window.FindName('DetailsText')
$finishDetail = $window.FindName('FinishDetail'); $finishWarning = $window.FindName('FinishWarning')
$errorTitle = $window.FindName('ErrorTitle'); $errorDetail = $window.FindName('ErrorDetail'); $copyDiagnostics = $window.FindName('CopyDiagnostics')
$footer = $window.FindName('Footer'); $cancel = $window.FindName('Cancel'); $install = $window.FindName('Install'); $open = $window.FindName('Open'); $done = $window.FindName('Done'); $close = $window.FindName('Close')
$script:DetailsControl = $detailsText

try {
    if ($SetupSource -and (Test-Path $SetupSource)) {
        Add-Type -AssemblyName System.Drawing
        $associatedIcon = [System.Drawing.Icon]::ExtractAssociatedIcon($SetupSource)
        if ($associatedIcon) {
            $iconSource = [System.Windows.Interop.Imaging]::CreateBitmapSourceFromHIcon($associatedIcon.Handle, [System.Windows.Int32Rect]::Empty, [System.Windows.Media.Imaging.BitmapSizeOptions]::FromEmptyOptions())
            $window.Icon = $iconSource
            $brandIcon.Source = $iconSource
            $associatedIcon.Dispose()
        }
    }
} catch { }

switch ($PreviousLaunchMode) {
    'windows' { $windowsRadio.IsChecked = $true }
    'wow' { $wowRadio.IsChecked = $true }
    default { $manualRadio.IsChecked = $true }
}
if ($ExistingState -or $Repair) { $desktop.IsChecked = Test-Path $DesktopShortcut }
if ($Silent) { $launchAfter.IsChecked = $false }

$script:InstallStarted = $false
$script:InstallSucceeded = $false
$script:InstallFailed = $false
$script:InstallCanceled = $false
$script:NewAppApplied = $false
$script:CancelRequested = $false
$script:SelectedLaunchMode = $PreviousLaunchMode
$script:SelectedDesktop = [bool]$desktop.IsChecked
$script:LaunchAfterInstall = [bool]$launchAfter.IsChecked
$script:ErrorText = ''
$script:FinishWarningText = ''

function Pump-UI {
    if (-not $Silent) {
        $window.Dispatcher.Invoke([action]{}, [System.Windows.Threading.DispatcherPriority]::Background)
    }
}

function Add-Detail([string]$Text) {
    Write-InstallLog $Text
    if (-not $Silent -and $script:DetailsControl) {
        $script:DetailsControl.AppendText($Text + [Environment]::NewLine)
        $script:DetailsControl.ScrollToEnd()
        Pump-UI
    }
}

function Update-Step([int]$Value, [string]$Title, [string]$Text) {
    $valueSafe = [Math]::Max(0, [Math]::Min(100, $Value))
    $progress.Value = $valueSafe
    $percent.Text = ($valueSafe.ToString() + '%')
    $step.Text = $Title
    $detail.Text = $Text
    Add-Detail ($valueSafe.ToString() + '% • ' + $Title + ' • ' + $Text)
    Pump-UI
}

function Assert-NotCanceled {
    if ($script:CancelRequested) {
        throw [System.OperationCanceledException]::new('Installation canceled by the user.')
    }
}

function Format-Bytes([long]$Value) {
    if ($Value -ge 1GB) { return ('{0:N1} GB' -f ($Value / 1GB)) }
    if ($Value -ge 1MB) { return ('{0:N1} MB' -f ($Value / 1MB)) }
    if ($Value -ge 1KB) { return ('{0:N1} KB' -f ($Value / 1KB)) }
    return ($Value.ToString() + ' B')
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
    # same filename. The launcher also owns its Python process through a Job Object.
    $targets = @(
        @{ Name = 'KeystoneLens'; Path = (Join-Path $InstallDir 'KeystoneLens.exe') },
        @{ Name = 'KeystoneLens-WoW-Watcher'; Path = (Join-Path $InstallDir 'KeystoneLens-WoW-Watcher.exe') },
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

function Invoke-DownloadWithProgress([string]$Uri, [string]$OutFile, [int]$Attempts = 3) {
    $last = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $client = $null; $response = $null; $stream = $null; $file = $null
        try {
            Assert-NotCanceled
            Remove-Item -LiteralPath $OutFile -Force -ErrorAction SilentlyContinue
            Add-Detail ('Downloading official Python runtime (attempt ' + $attempt + '/' + $Attempts + ').')
            $client = New-Object System.Net.Http.HttpClient
            $client.Timeout = [TimeSpan]::FromSeconds(60)
            $response = $client.GetAsync($Uri, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            $response.EnsureSuccessStatusCode() | Out-Null
            $total = $response.Content.Headers.ContentLength
            $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $file = [System.IO.File]::Open($OutFile, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
            $buffer = New-Object byte[] 65536
            [long]$received = 0
            while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                Assert-NotCanceled
                $file.Write($buffer, 0, $read)
                $received += $read
                if ($total -and $total -gt 0) {
                    $fraction = [Math]::Min(1.0, ($received / [double]$total))
                    $value = 22 + [int][Math]::Floor(20 * $fraction)
                    $detail.Text = ('Downloading Python runtime… ' + (Format-Bytes $received) + ' / ' + (Format-Bytes ([long]$total)))
                    $progress.Value = $value; $percent.Text = ($value.ToString() + '%')
                } else {
                    $detail.Text = ('Downloading Python runtime… ' + (Format-Bytes $received))
                }
                Pump-UI
            }
            if ($total -and $received -ne [long]$total) { throw 'Python runtime download ended before all expected bytes were received.' }
            Add-Detail ('Python runtime download complete: ' + (Format-Bytes $received) + '.')
            return
        } catch [System.OperationCanceledException] {
            throw
        } catch {
            $last = $_.Exception
            Add-Detail ('Download attempt failed: ' + $last.Message)
            if ($attempt -lt $Attempts) {
                for ($i = 0; $i -lt ($attempt * 10); $i++) { Assert-NotCanceled; Start-Sleep -Milliseconds 200; Pump-UI }
            }
        } finally {
            if ($file) { $file.Dispose() }
            if ($stream) { $stream.Dispose() }
            if ($response) { $response.Dispose() }
            if ($client) { $client.Dispose() }
        }
    }
    throw ('Download failed after ' + $Attempts + ' attempts: ' + $last.Message)
}

function Get-VerifiedPythonInstaller {
    if (Test-Path $PythonInstallerCache) {
        $cachedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonInstallerCache).Hash.ToLowerInvariant()
        if ($cachedHash -eq $PythonSha) {
            Add-Detail 'Using verified cached Python runtime.'
            return $PythonInstallerCache
        }
        Add-Detail 'Discarding cached Python runtime because its SHA-256 did not match.'
        Remove-Item -LiteralPath $PythonInstallerCache -Force -ErrorAction SilentlyContinue
    }
    Update-Step 22 'Downloading runtime' 'Downloading the official Python runtime from python.org…'
    Invoke-DownloadWithProgress $PythonUrl $PythonInstaller
    Update-Step 43 'Verifying runtime' 'Checking the Python runtime SHA-256 value…'
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonInstaller).Hash.ToLowerInvariant()
    if ($actual -ne $PythonSha) { throw 'Python runtime integrity check failed.' }
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    Copy-Item -LiteralPath $PythonInstaller -Destination $PythonInstallerCache -Force
    Add-Detail 'Python runtime SHA-256 verified.'
    return $PythonInstallerCache
}


function Log-LockedDependencies([string]$LockFile) {
    try {
        Get-Content -LiteralPath $LockFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -match '^([A-Za-z0-9_.-]+==[^\s\\]+)') { Add-Detail ('Required package: ' + $Matches[1]) }
        }
    } catch { Add-Detail 'Could not enumerate dependency names for the details view.' }
}

function Quote-ProcessArgument([string]$Value) {
    if ($Value.Contains('"')) { throw 'Unsafe quote character in child-process argument.' }
    return ('"' + $Value + '"')
}

function Invoke-TrackedProcess([string]$FilePath, [string[]]$Arguments, [bool]$AllowTerminateOnCancel) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.Arguments = (($Arguments | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join ' ')
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    if (-not $p.Start()) { throw ('Could not start required process: ' + $FilePath) }
    $cancelNoticeShown = $false
    try {
        while (-not $p.HasExited) {
            Pump-UI
            if ($script:CancelRequested) {
                if ($AllowTerminateOnCancel) {
                    try { $p.Kill() } catch { }
                    try { $p.WaitForExit() } catch { }
                    throw [System.OperationCanceledException]::new('Installation canceled by the user.')
                }
                if (-not $cancelNoticeShown) {
                    $cancelNoticeShown = $true
                    $footer.Text = 'Cancel requested. Finishing the current Windows runtime operation safely…'
                    Add-Detail 'Cancel requested; waiting for the current Windows runtime operation to finish safely.'
                }
            }
            Start-Sleep -Milliseconds 150
        }
        if ($p.ExitCode -ne 0) { throw ('Required process failed with exit code ' + $p.ExitCode + '.') }
    } finally {
        $p.Dispose()
    }
    Assert-NotCanceled
}

function Install-AppRuntime {
    $runtimeInstaller = Get-VerifiedPythonInstaller
    Update-Step 52 'Installing dedicated runtime' 'Installing the KeystoneLens Python runtime in its private per-user location…'
    $arguments = @(
        '/quiet',
        'InstallAllUsers=0',
        ('TargetDir=' + $PythonDir),
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
    Invoke-TrackedProcess $runtimeInstaller $arguments $false
    Add-Detail 'Dedicated Python runtime installation completed.'
}

function Apply-LaunchPreferences {
    $target = Join-Path $InstallDir 'KeystoneLens.exe'
    $watcherTarget = Join-Path $InstallDir 'KeystoneLens-WoW-Watcher.exe'
    $icon = Join-Path $InstallDir 'KeystoneLens.ico'

    Remove-Item -LiteralPath $StartupShortcut -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $WoWWatcherShortcut -Force -ErrorAction SilentlyContinue
    if ($script:SelectedLaunchMode -eq 'windows') {
        New-Shortcut $StartupShortcut $target $icon
        Add-Detail 'Configured KeystoneLens to start with Windows.'
    } elseif ($script:SelectedLaunchMode -eq 'wow') {
        if (-not (Test-Path $watcherTarget)) { throw 'The WoW launch watcher is missing from the installed Companion.' }
        New-Shortcut $WoWWatcherShortcut $watcherTarget $icon
        Add-Detail 'Configured KeystoneLens to start when World of Warcraft Retail starts.'
    } else {
        Add-Detail 'Configured KeystoneLens for manual start.'
    }

    if ($script:SelectedDesktop) {
        New-Shortcut $DesktopShortcut $target $icon
        Add-Detail 'Created desktop shortcut.'
    } else {
        Remove-Item -LiteralPath $DesktopShortcut -Force -ErrorAction SilentlyContinue
        Add-Detail 'Desktop shortcut not requested.'
    }
}

function Show-FinishPage {
    $decisionPanel.Visibility = 'Collapsed'; $progressPanel.Visibility = 'Collapsed'; $errorPanel.Visibility = 'Collapsed'; $finishPanel.Visibility = 'Visible'
    $install.Visibility = 'Collapsed'; $cancel.Visibility = 'Collapsed'; $close.Visibility = 'Collapsed'; $done.Visibility = 'Visible'
    $open.Visibility = 'Visible'
    $footer.Text = 'Installation complete. You can close Setup or open the Companion.'
    if ($script:FinishWarningText) { $finishWarning.Text = $script:FinishWarningText }
    Pump-UI
}

function Show-ErrorPage([string]$Title, [string]$Message, [bool]$Canceled) {
    $decisionPanel.Visibility = 'Collapsed'; $progressPanel.Visibility = 'Collapsed'; $finishPanel.Visibility = 'Collapsed'; $errorPanel.Visibility = 'Visible'
    $install.Visibility = 'Collapsed'; $cancel.Visibility = 'Collapsed'; $open.Visibility = 'Collapsed'; $done.Visibility = 'Collapsed'; $close.Visibility = 'Visible'
    $errorTitle.Text = $Title; $errorDetail.Text = $Message
    if ($Canceled) {
        $footer.Text = 'No new Companion installation was committed. A previous installed release was kept when present.'
    } else {
        $footer.Text = 'The previous installed release was kept when rollback was possible.'
    }
    Pump-UI
}

function Start-WoWWatcherIfRequested {
    if ($script:SelectedLaunchMode -ne 'wow') { return }
    $watcherTarget = Join-Path $InstallDir 'KeystoneLens-WoW-Watcher.exe'
    if (Test-Path $watcherTarget) {
        try { Start-Process $watcherTarget; Add-Detail 'WoW launch watcher started.' } catch { $script:FinishWarningText = 'KeystoneLens installed, but the WoW launch watcher could not be started until your next Windows sign-in.' }
    }
}

function Start-Installation {
    if ($script:InstallStarted) { return }
    $script:InstallStarted = $true
    $script:CancelRequested = $false
    $script:SelectedLaunchMode = if ($wowRadio.IsChecked) { 'wow' } elseif ($windowsRadio.IsChecked) { 'windows' } else { 'manual' }
    $script:SelectedDesktop = [bool]$desktop.IsChecked
    $script:LaunchAfterInstall = [bool]$launchAfter.IsChecked
    if ($Silent) { $script:LaunchAfterInstall = $false }

    $decisionPanel.Visibility = 'Collapsed'; $progressPanel.Visibility = 'Visible'; $install.Visibility = 'Collapsed'; $cancel.Visibility = 'Visible'; $cancel.IsEnabled = $true
    $footer.Text = 'You can keep using your PC while KeystoneLens installs.'
    Update-Step 5 'Preparing installation' 'Checking the required components…'
    Add-Detail ('Selected launch mode: ' + $script:SelectedLaunchMode + '; desktop shortcut: ' + $script:SelectedDesktop + '.')

    try {
        Assert-NotCanceled
        Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $Work,$PayloadDir,$StageDir | Out-Null
        Update-Step 10 'Preparing' 'Unpacking and validating KeystoneLens components…'
        Expand-Archive -LiteralPath $Payload -DestinationPath $PayloadDir -Force
        Copy-Item -Path (Join-Path $PayloadDir '*') -Destination $StageDir -Recurse -Force
        if (-not (Test-Path (Join-Path $StageDir 'KeystoneLens.exe')) -or -not (Test-Path (Join-Path $StageDir 'KeystoneLens-WoW-Watcher.exe'))) {
            throw 'The embedded Companion payload is incomplete.'
        }

        Assert-NotCanceled
        Update-Step 18 'Checking runtime' 'Checking the dedicated KeystoneLens Python runtime…'
        $runtimeHealthy = (Test-Path $PythonExe) -and (Test-Path $PythonW)
        if ($runtimeHealthy) {
            & $PythonExe -I -c 'import sys, tkinter, pip; raise SystemExit(0 if sys.version_info[:3] == (3, 13, 15) else 3)' | Out-Null
            $runtimeHealthy = ($LASTEXITCODE -eq 0)
        }
        if (-not $runtimeHealthy) { Install-AppRuntime } else { Update-Step 52 'Runtime ready' 'Using the verified dedicated KeystoneLens Python runtime…'; Add-Detail 'Existing dedicated Python runtime passed version/Tk/pip checks.' }
        Assert-NotCanceled
        if (-not (Test-Path $PythonExe) -or -not (Test-Path $PythonW)) { throw 'KeystoneLens dedicated Python runtime could not be located.' }
        & $PythonExe -I -c 'import tkinter, pip' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'The KeystoneLens dedicated runtime failed its Tk/pip check.' }

        Update-Step 68 'Installing components' 'Installing hash-locked KeystoneLens dependencies…'
        $packages = Join-Path $StageDir 'packages'
        New-Item -ItemType Directory -Force -Path $packages | Out-Null
        $lockFile = Join-Path $StageDir 'requirements-runtime.lock'
        Log-LockedDependencies $lockFile
        $pipArgs = @('-m','pip','install','--isolated','--no-input','--disable-pip-version-check','--no-warn-script-location','--no-cache-dir','--timeout','30','--retries','3','--index-url','https://pypi.org/simple','--only-binary=:all:','--require-hashes','--no-deps','--target',$packages,'-r',$lockFile)
        Invoke-TrackedProcess $PythonExe $pipArgs $true
        Set-Content -LiteralPath (Join-Path $StageDir 'pythonw.path') -Value $PythonW -Encoding ASCII
        Add-Detail 'Hash-locked dependencies installed into the staged application.'

        Assert-NotCanceled
        Update-Step 78 'Verifying Companion' 'Starting the staged modules in an isolated runtime check…'
        & $PythonExe -I -c 'import os,sys; root=sys.argv[1]; sys.path[:0]=[os.path.join(root,"app"),os.path.join(root,"packages")]; import tkinter, requests, PIL, zxingcpp; import keystonelens_companion.__main__' $StageDir | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Staged runtime verification failed.' }
        Add-Detail 'Staged Companion runtime verification passed.'

        Assert-NotCanceled
        $cancel.IsEnabled = $false
        $footer.Text = 'Finishing the verified installation safely…'
        Update-Step 84 'Applying safely' 'Replacing the previous Companion only after verification…'
        Stop-KeystoneLensProcesses
        Remove-Item -LiteralPath $BackupDir -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $InstallDir) { Move-Item -LiteralPath $InstallDir -Destination $BackupDir -Force }
        Move-Item -LiteralPath $StageDir -Destination $InstallDir -Force
        $script:NewAppApplied = $true

        Get-ChildItem -LiteralPath $RuntimeRoot -Filter 'python-3.13.*-amd64.exe' -File -ErrorAction SilentlyContinue |
            Where-Object { -not [string]::Equals($_.FullName, $PythonInstallerCache, [System.StringComparison]::OrdinalIgnoreCase) } |
            Remove-Item -Force -ErrorAction SilentlyContinue

        Update-Step 91 'Configuring Windows' 'Registering Start menu, repair and uninstall support…'
        New-Item -ItemType Directory -Force -Path $InstallerCacheDir | Out-Null
        if ($SetupSource -and (Test-Path $SetupSource)) {
            $sourceFull = [System.IO.Path]::GetFullPath($SetupSource)
            $repairFull = [System.IO.Path]::GetFullPath($RepairSetup)
            if (-not [string]::Equals($sourceFull, $repairFull, [System.StringComparison]::OrdinalIgnoreCase)) {
                Copy-Item -LiteralPath $SetupSource -Destination $RepairSetup -Force
            }
        }
        New-Shortcut (Join-Path $ProgramsDir 'KeystoneLens.lnk') (Join-Path $InstallDir 'KeystoneLens.exe') (Join-Path $InstallDir 'KeystoneLens.ico')
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
        Add-Detail 'Registered Start menu shortcut plus Windows repair/uninstall metadata.'
        $script:InstallSucceeded = $true

        try { Apply-LaunchPreferences } catch { $script:FinishWarningText = 'KeystoneLens installed, but one or more shortcut/startup preferences could not be applied. Run Setup again to retry.'; Add-Detail ('Preference warning: ' + $_.Exception.Message) }
        Start-WoWWatcherIfRequested

        Update-Step 100 'Ready' ('KeystoneLens Companion ' + $Version + ' is ready.')
        if ($script:LaunchAfterInstall -and (Test-Path (Join-Path $InstallDir 'KeystoneLens.exe'))) {
            try { Start-Process (Join-Path $InstallDir 'KeystoneLens.exe'); $finishDetail.Text = 'The Companion was installed successfully and has been opened.'; Add-Detail 'Companion launched after installation.' } catch { $script:FinishWarningText = 'KeystoneLens installed successfully, but could not be opened automatically.' }
        }
        if ($Silent) { $window.Close(); return }
        Show-FinishPage
    } catch [System.OperationCanceledException] {
        $script:InstallCanceled = $true
        Add-Detail 'Installation canceled by the user.'
        Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
        if ($Silent) { $window.Close(); return }
        Show-ErrorPage 'Installation canceled' 'KeystoneLens Setup stopped before committing a new Companion installation.' $true
    } catch {
        $script:InstallFailed = $true
        $script:ErrorText = $_.Exception.Message
        Add-Detail ('Installation failed: ' + $script:ErrorText)
        if (Test-Path $BackupDir) {
            Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $BackupDir -Destination $InstallDir -Force -ErrorAction SilentlyContinue
        } elseif ($script:NewAppApplied -and -not $ExistingState) {
            Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
        if ($PreviousLaunchMode -eq 'wow' -and (Test-Path (Join-Path $InstallDir 'KeystoneLens-WoW-Watcher.exe'))) {
            try { Start-Process (Join-Path $InstallDir 'KeystoneLens-WoW-Watcher.exe') } catch { }
        }
        if ($Silent) { $window.Close(); return }
        Show-ErrorPage 'Installation could not be completed' $script:ErrorText $false
    } finally {
        Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$install.add_Click({ Start-Installation })
$cancel.add_Click({
    if (-not $script:InstallStarted) { $script:InstallCanceled = $true; $window.Close(); return }
    if ($cancel.IsEnabled) {
        $script:CancelRequested = $true
        $cancel.IsEnabled = $false
        $cancel.Content = 'Canceling…'
        $footer.Text = 'Cancel requested. KeystoneLens will stop at the next safe point.'
        Add-Detail 'Cancel requested by the user.'
    }
})
$open.add_Click({ try { Start-Process (Join-Path $InstallDir 'KeystoneLens.exe') } catch { [System.Windows.MessageBox]::Show($_.Exception.Message,'KeystoneLens','OK','Warning') | Out-Null } })
$done.add_Click({ $window.Close() })
$close.add_Click({ $window.Close() })
$copyDiagnostics.add_Click({
    try {
        $text = 'KeystoneLens Setup ' + $Version + [Environment]::NewLine + $script:ErrorText + [Environment]::NewLine + 'Install log: ' + $InstallLog
        [System.Windows.Clipboard]::SetText($text)
        $copyDiagnostics.Content = 'Copied'
    } catch { }
})
$window.add_Closing({
    param($s,$e)
    if (-not $script:InstallStarted -and -not $script:InstallSucceeded -and -not $script:InstallFailed -and -not $script:InstallCanceled) {
        # Closing the decision page is a user cancellation, not a successful setup.
        $script:InstallCanceled = $true
        return
    }
    if ($script:InstallStarted -and -not $script:InstallSucceeded -and -not $script:InstallFailed -and -not $script:InstallCanceled) {
        $e.Cancel = $true
        if ($cancel.IsEnabled) {
            $script:CancelRequested = $true; $cancel.IsEnabled = $false; $cancel.Content = 'Canceling…'; $footer.Text = 'Cancel requested. KeystoneLens will stop at the next safe point.'
        } else {
            $footer.Text = 'Setup is finishing a critical verified installation step and cannot close yet.'
        }
    }
})
$window.add_ContentRendered({ if ($Silent -and -not $script:InstallStarted) { Start-Installation } })

$null = $window.ShowDialog()
$status = if ($script:InstallSucceeded) { 'ok' } elseif ($script:InstallCanceled) { 'canceled' } else { 'failed' }
if ($ResultFile) {
    try { [System.IO.File]::WriteAllText($ResultFile, $status, [System.Text.Encoding]::ASCII) } catch { }
}
Write-InstallLog ('KeystoneLens Setup finished with status: ' + $status + '.')
if ($script:InstallFailed) { exit 1 }
if ($script:InstallCanceled) { exit 2 }
exit 0
