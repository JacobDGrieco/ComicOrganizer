# bulk_comic_converter.ps1
# Bulk conversion between folders, CBZ (ZIP), and CBR (RAR).
# Choose the directory containing the source folders/archives when prompted.
#
# Supported operations:
#   1. Folders -> CBZ
#   2. Folders -> CBR
#   3. CBR -> CBZ
#   4. CBZ -> CBR
#   5. CBZ -> folders
#   6. CBR -> folders
#
# CBR creation requires WinRAR's rar.exe.
# CBR extraction requires either 7-Zip (7z.exe) or WinRAR.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Show-SingleChoiceMenu {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string[]]$Choices
    )

    $selectedIndex = 0

    while ($true) {
        Clear-Host
        Write-Host $Title -ForegroundColor Cyan
        Write-Host 'Use Up/Down and press Enter. Press Esc to cancel.'
        Write-Host ''

        for ($i = 0; $i -lt $Choices.Count; $i++) {
            $prefix = if ($i -eq $selectedIndex) { '> ' } else { '  ' }
            if ($i -eq $selectedIndex) {
                Write-Host ($prefix + $Choices[$i]) -ForegroundColor Yellow
            }
            else {
                Write-Host ($prefix + $Choices[$i])
            }
        }

        $key = [Console]::ReadKey($true)
        switch ($key.Key) {
            'UpArrow'   { $selectedIndex = ($selectedIndex - 1 + $Choices.Count) % $Choices.Count }
            'DownArrow' { $selectedIndex = ($selectedIndex + 1) % $Choices.Count }
            'Enter'     { return $selectedIndex }
            'Escape'    { return -1 }
        }
    }
}

function Read-YesNo {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [bool]$Default = $false
    )

    $suffix = if ($Default) { ' [Y/n]' } else { ' [y/N]' }

    while ($true) {
        $answer = (Read-Host ($Prompt + $suffix)).Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
        if ($answer -in @('y', 'yes')) { return $true }
        if ($answer -in @('n', 'no')) { return $false }
        Write-Host 'Enter Y or N.' -ForegroundColor DarkYellow
    }
}

function Read-ExistingDirectory {
	param([Parameter(Mandatory)][string]$Prompt)

	while ($true) {
		$path = (Read-Host $Prompt).Trim().Trim('"')
		if ([string]::IsNullOrWhiteSpace($path)) {
			Write-Host 'Enter a folder path.' -ForegroundColor DarkYellow
			continue
		}

		if (Test-Path -LiteralPath $path -PathType Container) {
			return (Get-Item -LiteralPath $path).FullName
		}

		Write-Host "Folder not found: $path" -ForegroundColor DarkYellow
	}
}

function Find-Executable {
    param(
        [Parameter(Mandatory)][string[]]$Names,
        [string[]]$KnownPaths = @()
    )

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }

    foreach ($path in $KnownPaths) {
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            return $path
        }
    }

    return $null
}

function Get-7ZipPath {
    return Find-Executable -Names @('7z.exe', '7zz.exe', '7z', '7zz') -KnownPaths @(
        (Join-Path $env:ProgramFiles '7-Zip\7z.exe'),
        $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} '7-Zip\7z.exe' })
    )
}

function Get-RarPath {
    return Find-Executable -Names @('rar.exe', 'rar') -KnownPaths @(
        (Join-Path $env:ProgramFiles 'WinRAR\rar.exe'),
        $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'WinRAR\rar.exe' })
    )
}

function Get-UnrarPath {
    $rarPath = Get-RarPath
    if ($null -ne $rarPath) { return $rarPath }

    return Find-Executable -Names @('unrar.exe', 'unrar') -KnownPaths @(
        (Join-Path $env:ProgramFiles 'WinRAR\UnRAR.exe'),
        $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'WinRAR\UnRAR.exe' })
    )
}

function Test-IsImageFile {
    param([Parameter(Mandatory)][string]$Path)

    $extensions = @('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif', '.tif', '.tiff', '.jxl')
    return $extensions -contains [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
}

function Test-IsPackableFile {
    param([Parameter(Mandatory)][System.IO.FileInfo]$File)

    return $File.Extension.ToLowerInvariant() -ne '.bak'
}

function Remove-BackupArtifacts {
    param([Parameter(Mandatory)][string]$Directory)

    Get-ChildItem -LiteralPath $Directory -File -Recurse -Filter '*.bak' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Get-CompatibleRelativePath {
    param(
        [Parameter(Mandatory)][string]$BasePath,
        [Parameter(Mandatory)][string]$FullPath
    )

    $normalizedBase = [System.IO.Path]::GetFullPath($BasePath)
    if (-not $normalizedBase.EndsWith([System.IO.Path]::DirectorySeparatorChar.ToString())) {
        $normalizedBase += [System.IO.Path]::DirectorySeparatorChar
    }

    $normalizedFull = [System.IO.Path]::GetFullPath($FullPath)
    if (-not $normalizedFull.StartsWith($normalizedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "File is not inside the source directory: $FullPath"
    }

    return $normalizedFull.Substring($normalizedBase.Length)
}

function Remove-ExistingDestination {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][bool]$Force,
        [switch]$Directory
    )

    if (-not (Test-Path -LiteralPath $Path)) { return $true }

    if (-not $Force) {
        Write-Host "Skip (exists): $Path" -ForegroundColor DarkYellow
        return $false
    }

    if ($Directory) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    else {
        Remove-Item -LiteralPath $Path -Force
    }

    return $true
}

function New-CbzFromDirectory {
    param(
        [Parameter(Mandatory)][System.IO.DirectoryInfo]$Directory,
        [Parameter(Mandatory)][string]$OutputPath,
        [Parameter(Mandatory)][bool]$Force,
        [Parameter(Mandatory)][bool]$MaximumCompression
    )

    if (-not (Remove-ExistingDestination -Path $OutputPath -Force $Force)) { return $false }

    Write-Host "Creating CBZ: $($Directory.Name) -> $OutputPath"
    $fileStream = $null
    $archive = $null

    try {
        $fileStream = [System.IO.File]::Open(
            $OutputPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
        $archive = [System.IO.Compression.ZipArchive]::new(
            $fileStream,
            [System.IO.Compression.ZipArchiveMode]::Create,
            $false
        )

        $files = @(Get-ChildItem -LiteralPath $Directory.FullName -File -Recurse | Where-Object { Test-IsPackableFile $_ } | Sort-Object FullName)
        if ($files.Count -eq 0) {
            throw "Source folder is empty: $($Directory.FullName)"
        }

        foreach ($file in $files) {
            $entryName = (Get-CompatibleRelativePath -BasePath $Directory.FullName -FullPath $file.FullName).Replace('\', '/')
            $level = if (Test-IsImageFile $file.FullName) {
                [System.IO.Compression.CompressionLevel]::NoCompression
            }
            elseif ($MaximumCompression) {
                [System.IO.Compression.CompressionLevel]::Optimal
            }
            else {
                [System.IO.Compression.CompressionLevel]::Fastest
            }

            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive, $file.FullName, $entryName, $level
            ) | Out-Null
        }

        return $true
    }
    catch {
        if (Test-Path -LiteralPath $OutputPath) {
            Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
    finally {
        if ($null -ne $archive) { $archive.Dispose() }
        if ($null -ne $fileStream) { $fileStream.Dispose() }
    }
}

function New-CbrFromDirectory {
    param(
        [Parameter(Mandatory)][System.IO.DirectoryInfo]$Directory,
        [Parameter(Mandatory)][string]$OutputPath,
        [Parameter(Mandatory)][string]$RarPath,
        [Parameter(Mandatory)][bool]$Force,
        [Parameter(Mandatory)][bool]$MaximumCompression
    )

    if (-not (Remove-ExistingDestination -Path $OutputPath -Force $Force)) { return $false }

    $files = @(Get-ChildItem -LiteralPath $Directory.FullName -File -Recurse | Where-Object { Test-IsPackableFile $_ })
    if ($files.Count -eq 0) { throw "Source folder is empty: $($Directory.FullName)" }

    Write-Host "Creating CBR: $($Directory.Name) -> $OutputPath"
    $compressionSwitch = if ($MaximumCompression) { '-m5' } else { '-m0' }
    $listFile = Join-Path ([System.IO.Path]::GetTempPath()) ('comic_convert_rar_list_' + [guid]::NewGuid().ToString('N') + '.txt')

    Push-Location $Directory.FullName
    try {
        $relativePaths = @(
            $files |
                Sort-Object FullName |
                ForEach-Object { Get-CompatibleRelativePath -BasePath $Directory.FullName -FullPath $_.FullName }
        )
        [System.IO.File]::WriteAllLines($listFile, $relativePaths, [System.Text.UTF8Encoding]::new($false))
        & $RarPath 'a' '-idq' '-ep1' '-ma4' $compressionSwitch '--' $OutputPath "@$listFile" | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $OutputPath)) {
            throw "WinRAR failed with exit code $LASTEXITCODE while creating: $OutputPath"
        }
        return $true
    }
    catch {
        if (Test-Path -LiteralPath $OutputPath) {
            Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
    finally {
        Pop-Location
        Remove-Item -LiteralPath $listFile -Force -ErrorAction SilentlyContinue
    }
}

function Expand-CbzArchive {
    param(
        [Parameter(Mandatory)][System.IO.FileInfo]$Archive,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][bool]$Force
    )

    if (-not (Remove-ExistingDestination -Path $Destination -Force $Force -Directory)) { return $false }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($Archive.FullName, $Destination)
        Remove-BackupArtifacts -Directory $Destination
        return $true
    }
    catch {
        Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

function Expand-CbrArchive {
    param(
        [Parameter(Mandatory)][System.IO.FileInfo]$Archive,
        [Parameter(Mandatory)][string]$Destination,
        [string]$SevenZipPath,
        [string]$UnrarPath,
        [Parameter(Mandatory)][bool]$Force
    )

    if (-not (Remove-ExistingDestination -Path $Destination -Force $Force -Directory)) { return $false }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    try {
        if ($null -ne $SevenZipPath) {
            & $SevenZipPath 'x' '-y' "-o$Destination" '--' $Archive.FullName | Out-Null
        }
        elseif ($null -ne $UnrarPath) {
            & $UnrarPath 'x' '-y' '-idq' '--' $Archive.FullName ($Destination + [System.IO.Path]::DirectorySeparatorChar) | Out-Null
        }
        else {
            throw 'CBR extraction requires 7-Zip or WinRAR/UnRAR.'
        }

        if ($LASTEXITCODE -ne 0) {
            throw "Archive extraction failed with exit code $LASTEXITCODE : $($Archive.FullName)"
        }

        Remove-BackupArtifacts -Directory $Destination
        return $true
    }
    catch {
        Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

function Get-SourceFolders {
    param([Parameter(Mandatory)][bool]$RecurseOneLevel)

    $root = (Get-Item -LiteralPath (Get-Location).Path).FullName
    if (-not $RecurseOneLevel) {
        return @(Get-ChildItem -LiteralPath $root -Directory)
    }

    $results = @()
    foreach ($parent in Get-ChildItem -LiteralPath $root -Directory) {
        $results += @(Get-ChildItem -LiteralPath $parent.FullName -Directory)
    }
    return $results
}

function Get-SourceArchives {
    param(
        [Parameter(Mandatory)][string]$Extension,
        [Parameter(Mandatory)][bool]$Recursive
    )

    return @(Get-ChildItem -LiteralPath (Get-Location).Path -File -Filter "*$Extension" -Recurse:$Recursive)
}

$operations = @(
    'Folders -> CBZ',
    'Folders -> CBR',
    'CBR -> CBZ',
    'CBZ -> CBR',
    'CBZ -> folders (export)',
    'CBR -> folders (export)'
)

$operation = Show-SingleChoiceMenu -Title 'Bulk Comic Converter' -Choices $operations
if ($operation -lt 0) {
    Write-Host 'Cancelled.' -ForegroundColor Yellow
    exit 0
}

Clear-Host
Write-Host ("Selected: " + $operations[$operation]) -ForegroundColor Cyan
Write-Host ''

$conversionRoot = Read-ExistingDirectory -Prompt 'Full path to the folder for converting'
Push-Location -LiteralPath $conversionRoot

try {
$force = Read-YesNo -Prompt 'Overwrite existing output files/folders?' -Default $false
$deleteSource = Read-YesNo -Prompt 'Delete each source after a successful conversion?' -Default $false
$recursive = Read-YesNo -Prompt 'Search one level deeper for folder input, or recursively for archive input?' -Default $false
$maximumCompression = $false

if ($operation -in @(0, 1, 2, 3)) {
    $maximumCompression = Read-YesNo -Prompt 'Use maximum compression for non-image data?' -Default $false
}

$sevenZipPath = $null
$rarPath = $null
$unrarPath = $null

if ($operation -in @(1, 3)) {
    $rarPath = Get-RarPath
    if ($null -eq $rarPath) {
        throw "Creating CBR files requires WinRAR's rar.exe. Install WinRAR or add rar.exe to PATH."
    }
}

if ($operation -in @(2, 5)) {
    $sevenZipPath = Get-7ZipPath
    $unrarPath = Get-UnrarPath
    if ($null -eq $sevenZipPath -and $null -eq $unrarPath) {
        throw 'Reading CBR files requires 7-Zip or WinRAR/UnRAR.'
    }
}

Write-Host ''
Write-Host 'Starting...' -ForegroundColor Cyan
$successCount = 0
$skipCount = 0
$failureCount = 0

try {
    switch ($operation) {
        0 {
            $sources = Get-SourceFolders -RecurseOneLevel $recursive
            foreach ($source in $sources) {
                try {
                    $output = Join-Path $source.Parent.FullName ($source.Name + '.cbz')
                    if (New-CbzFromDirectory -Directory $source -OutputPath $output -Force $force -MaximumCompression $maximumCompression) {
                        $successCount++
                        if ($deleteSource) { Remove-Item -LiteralPath $source.FullName -Recurse -Force }
                    }
                    else { $skipCount++ }
                }
                catch { $failureCount++; Write-Host "Failed: $($source.FullName)`n$($_.Exception.Message)" -ForegroundColor Red }
            }
        }
        1 {
            $sources = Get-SourceFolders -RecurseOneLevel $recursive
            foreach ($source in $sources) {
                try {
                    $output = Join-Path $source.Parent.FullName ($source.Name + '.cbr')
                    if (New-CbrFromDirectory -Directory $source -OutputPath $output -RarPath $rarPath -Force $force -MaximumCompression $maximumCompression) {
                        $successCount++
                        if ($deleteSource) { Remove-Item -LiteralPath $source.FullName -Recurse -Force }
                    }
                    else { $skipCount++ }
                }
                catch { $failureCount++; Write-Host "Failed: $($source.FullName)`n$($_.Exception.Message)" -ForegroundColor Red }
            }
        }
        2 {
            $sources = Get-SourceArchives -Extension '.cbr' -Recursive $recursive
            foreach ($source in $sources) {
                $temp = Join-Path ([System.IO.Path]::GetTempPath()) ('comic_convert_' + [guid]::NewGuid().ToString('N'))
                try {
                    if (-not (Expand-CbrArchive -Archive $source -Destination $temp -SevenZipPath $sevenZipPath -UnrarPath $unrarPath -Force $true)) { continue }
                    $tempDirectory = Get-Item -LiteralPath $temp
                    $output = [System.IO.Path]::ChangeExtension($source.FullName, '.cbz')
                    if (New-CbzFromDirectory -Directory $tempDirectory -OutputPath $output -Force $force -MaximumCompression $maximumCompression) {
                        $successCount++
                        if ($deleteSource) { Remove-Item -LiteralPath $source.FullName -Force }
                    }
                    else { $skipCount++ }
                }
                catch { $failureCount++; Write-Host "Failed: $($source.FullName)`n$($_.Exception.Message)" -ForegroundColor Red }
                finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
            }
        }
        3 {
            $sources = Get-SourceArchives -Extension '.cbz' -Recursive $recursive
            foreach ($source in $sources) {
                $temp = Join-Path ([System.IO.Path]::GetTempPath()) ('comic_convert_' + [guid]::NewGuid().ToString('N'))
                try {
                    if (-not (Expand-CbzArchive -Archive $source -Destination $temp -Force $true)) { continue }
                    $tempDirectory = Get-Item -LiteralPath $temp
                    $output = [System.IO.Path]::ChangeExtension($source.FullName, '.cbr')
                    if (New-CbrFromDirectory -Directory $tempDirectory -OutputPath $output -RarPath $rarPath -Force $force -MaximumCompression $maximumCompression) {
                        $successCount++
                        if ($deleteSource) { Remove-Item -LiteralPath $source.FullName -Force }
                    }
                    else { $skipCount++ }
                }
                catch { $failureCount++; Write-Host "Failed: $($source.FullName)`n$($_.Exception.Message)" -ForegroundColor Red }
                finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
            }
        }
        4 {
            $sources = Get-SourceArchives -Extension '.cbz' -Recursive $recursive
            foreach ($source in $sources) {
                try {
                    $output = Join-Path $source.DirectoryName $source.BaseName
                    if (Expand-CbzArchive -Archive $source -Destination $output -Force $force) {
                        $successCount++
                        if ($deleteSource) { Remove-Item -LiteralPath $source.FullName -Force }
                    }
                    else { $skipCount++ }
                }
                catch { $failureCount++; Write-Host "Failed: $($source.FullName)`n$($_.Exception.Message)" -ForegroundColor Red }
            }
        }
        5 {
            $sources = Get-SourceArchives -Extension '.cbr' -Recursive $recursive
            foreach ($source in $sources) {
                try {
                    $output = Join-Path $source.DirectoryName $source.BaseName
                    if (Expand-CbrArchive -Archive $source -Destination $output -SevenZipPath $sevenZipPath -UnrarPath $unrarPath -Force $force) {
                        $successCount++
                        if ($deleteSource) { Remove-Item -LiteralPath $source.FullName -Force }
                    }
                    else { $skipCount++ }
                }
                catch { $failureCount++; Write-Host "Failed: $($source.FullName)`n$($_.Exception.Message)" -ForegroundColor Red }
            }
        }
    }
}
finally {
    Write-Host ''
    Write-Host "Finished. Successful: $successCount | Skipped: $skipCount | Failed: $failureCount" -ForegroundColor Green
}
}
finally {
	Pop-Location
}
