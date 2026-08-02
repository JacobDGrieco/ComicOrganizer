<#
.SYNOPSIS
Recursively flattens CBZ archives so files live at the archive root.

.DESCRIPTION
Scans one or more files or folders for .cbz archives. By default, the script
only reports archives that would be rewritten. Pass -Apply to rewrite them.

When rewriting, every non-directory entry is copied to the root of a new CBZ.
Nested folders are removed because directory entries are not written back. If
multiple nested files have the same leaf filename, later files are renamed with
__2, __3, and so on before the extension.

Terminal output is mirrored to logs\flatten-cbz.log by default. Use -LogPath
to write the log somewhere else.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\flatten-cbz.ps1 "D:\Comics"

Dry-run scan of all CBZ files under D:\Comics.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\flatten-cbz.ps1 "D:\Comics" -Apply

Rewrite nested CBZ files under D:\Comics without creating backup files.
#>

[CmdletBinding()]
param(
	[Parameter(Position = 0, ValueFromPipeline = $true, ValueFromPipelineByPropertyName = $true)]
	[Alias("FullName")]
	[string[]]$Path = @(),

	[switch]$Apply,

	[switch]$NoBackup,

	[switch]$NoRecurse,

	[switch]$StopOnError,

	[switch]$IncludeJunkEntries,

	[string]$LogPath = ""
)

$script:TranscriptStarted = $false

function Get-DefaultLogPath {
	$scriptFolder = $PSScriptRoot
	if ([string]::IsNullOrWhiteSpace($scriptFolder)) {
		$scriptFolder = Split-Path -Parent $MyInvocation.MyCommand.Path
	}

	if ([string]::IsNullOrWhiteSpace($scriptFolder)) {
		return Join-Path (Get-Location) "logs\flatten-cbz.log"
	}

	return Join-Path (Split-Path -Parent $scriptFolder) "logs\flatten-cbz.log"
}

function Start-OutputLog {
	param([string]$Path)

	$resolvedPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
	$logFolder = Split-Path -Parent $resolvedPath
	if (-not (Test-Path -LiteralPath $logFolder)) {
		New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
	}

	Start-Transcript -Path $resolvedPath -Force | Out-Null
	$script:TranscriptStarted = $true
	Write-Host "Log: $resolvedPath"
}

function Stop-OutputLog {
	if ($script:TranscriptStarted) {
		Stop-Transcript | Out-Null
		$script:TranscriptStarted = $false
	}
}

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($LogPath)) {
	$LogPath = Get-DefaultLogPath
}

if ($Path.Count -eq 0) {
	$requestedPath = Read-Host "Path to flatten"
	if ([string]::IsNullOrWhiteSpace($requestedPath)) {
		throw "Path is required."
	}

	$Path = @($requestedPath)
}

Start-OutputLog -Path $LogPath
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archivePaths = New-Object System.Collections.Generic.List[string]
$summary = [ordered]@{
	ArchivesFound = 0
	AlreadyFlat = 0
	WouldFlatten = 0
	Flattened = 0
	Errors = 0
}

	function Normalize-ZipEntryName {
		param(
			[Parameter(Mandatory = $true)]
			[string]$EntryName
		)

		return ($EntryName -replace "\\", "/").TrimStart("/")
	}

	function Get-ZipLeafName {
		param(
			[Parameter(Mandatory = $true)]
			[string]$EntryName
		)

		$normalizedName = Normalize-ZipEntryName -EntryName $EntryName
		$segments = $normalizedName -split "/"
		return $segments[$segments.Count - 1]
	}

	function Test-JunkEntry {
		param(
			[Parameter(Mandatory = $true)]
			[string]$EntryName
		)

		$normalizedName = Normalize-ZipEntryName -EntryName $EntryName
		$leafName = Get-ZipLeafName -EntryName $normalizedName

		if ($normalizedName.StartsWith("__MACOSX/", [System.StringComparison]::OrdinalIgnoreCase)) {
			return $true
		}

		return @(".DS_Store", "Thumbs.db") -contains $leafName
	}

	function Get-UniqueArchiveName {
		param(
			[Parameter(Mandatory = $true)]
			[string]$LeafName,

			[System.Collections.Generic.HashSet[string]]$UsedNames
		)

		if ($UsedNames.Add($LeafName)) {
			return $LeafName
		}

		$baseName = [System.IO.Path]::GetFileNameWithoutExtension($LeafName)
		$extension = [System.IO.Path]::GetExtension($LeafName)
		$counter = 2

		while ($true) {
			$candidateName = "{0}__{1}{2}" -f $baseName, $counter, $extension
			if ($UsedNames.Add($candidateName)) {
				return $candidateName
			}

			$counter++
		}
	}

	function Get-CbzFiles {
		param(
			[Parameter(Mandatory = $true)]
			[string]$InputPath
		)

		if (-not (Test-Path -LiteralPath $InputPath)) {
			Write-Warning "Path does not exist: $InputPath"
			return
		}

		$resolvedItems = Resolve-Path -LiteralPath $InputPath
		foreach ($resolvedItem in $resolvedItems) {
			$item = Get-Item -LiteralPath $resolvedItem.ProviderPath

			if (-not $item.PSIsContainer) {
				if ($item.Extension -ieq ".cbz") {
					$item
				}

				continue
			}

			if ($NoRecurse) {
				Get-ChildItem -LiteralPath $item.FullName -Filter "*.cbz" -File -ErrorAction SilentlyContinue
			} else {
				Get-ChildItem -LiteralPath $item.FullName -Filter "*.cbz" -File -Recurse -ErrorAction SilentlyContinue
			}
		}
	}

	function New-FlattenPlan {
		param(
			[Parameter(Mandatory = $true)]
			[System.IO.Compression.ZipArchive]$Archive
		)

		$usedNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
		$plan = New-Object System.Collections.Generic.List[object]

		for ($entryIndex = 0; $entryIndex -lt $Archive.Entries.Count; $entryIndex++) {
			$entry = $Archive.Entries[$entryIndex]
			$normalizedName = Normalize-ZipEntryName -EntryName $entry.FullName
			if ([string]::IsNullOrWhiteSpace($normalizedName) -or $normalizedName.EndsWith("/")) {
				continue
			}

			if ((-not $IncludeJunkEntries) -and (Test-JunkEntry -EntryName $normalizedName)) {
				Write-Verbose "Skipping junk entry: $normalizedName"
				continue
			}

			$leafName = Get-ZipLeafName -EntryName $normalizedName
			if ([string]::IsNullOrWhiteSpace($leafName)) {
				Write-Verbose "Skipping entry without a filename: $normalizedName"
				continue
			}

			$targetName = Get-UniqueArchiveName -LeafName $leafName -UsedNames $usedNames
			$plan.Add([pscustomobject]@{
				SourceIndex = $entryIndex
				OriginalName = $normalizedName
				TargetName = $targetName
				IsNested = $normalizedName.Contains("/")
				IsRenamed = $leafName -cne $targetName
			}) | Out-Null
		}

		return $plan
	}

	function Save-FlattenedCbz {
		param(
			[Parameter(Mandatory = $true)]
			[System.IO.FileInfo]$CbzFile
		)

		$tempPath = Join-Path $CbzFile.DirectoryName (".{0}.flatten-{1}.tmp" -f $CbzFile.BaseName, [guid]::NewGuid().ToString("N"))

		try {
			$sourceArchive = [System.IO.Compression.ZipFile]::OpenRead($CbzFile.FullName)
			try {
				$plan = @(New-FlattenPlan -Archive $sourceArchive)
				$destinationArchive = [System.IO.Compression.ZipFile]::Open($tempPath, [System.IO.Compression.ZipArchiveMode]::Create)
				try {
					for ($index = 0; $index -lt $plan.Count; $index++) {
						$plannedEntry = $plan[$index]
						$sourceEntry = $sourceArchive.Entries[$plannedEntry.SourceIndex]
						$newEntry = $destinationArchive.CreateEntry($plannedEntry.TargetName, [System.IO.Compression.CompressionLevel]::Optimal)
						$sourceStream = $sourceEntry.Open()
						try {
							$destinationStream = $newEntry.Open()
							try {
								$sourceStream.CopyTo($destinationStream)
							} finally {
								$destinationStream.Dispose()
							}
						} finally {
							$sourceStream.Dispose()
						}
					}
				} finally {
					$destinationArchive.Dispose()
				}
			} finally {
				$sourceArchive.Dispose()
			}

			Remove-Item -LiteralPath $CbzFile.FullName -Force
			Move-Item -LiteralPath $tempPath -Destination $CbzFile.FullName
		} catch {
			if (Test-Path -LiteralPath $tempPath) {
				Remove-Item -LiteralPath $tempPath -Force
			}

			throw
		}
	}

foreach ($inputPath in $Path) {
	foreach ($cbzFile in Get-CbzFiles -InputPath $inputPath) {
		$archivePaths.Add($cbzFile.FullName) | Out-Null
	}
}

try {
		if ($archivePaths.Count -eq 0) {
			foreach ($inputPath in $Path) {
				foreach ($cbzFile in Get-CbzFiles -InputPath $inputPath) {
					$archivePaths.Add($cbzFile.FullName) | Out-Null
				}
			}
		}

		$uniqueArchivePaths = $archivePaths | Sort-Object -Unique
		$summary.ArchivesFound = @($uniqueArchivePaths).Count

		foreach ($archivePath in $uniqueArchivePaths) {
			$cbzFile = Get-Item -LiteralPath $archivePath

			try {
				$archive = [System.IO.Compression.ZipFile]::OpenRead($cbzFile.FullName)
				try {
					$plan = @(New-FlattenPlan -Archive $archive)
					$nestedCount = @($plan | Where-Object { $_.IsNested }).Count
					$renamedCount = @($plan | Where-Object { $_.IsRenamed }).Count
					$directoryEntryCount = @($archive.Entries | Where-Object {
						$normalizedName = Normalize-ZipEntryName -EntryName $_.FullName
						[string]::IsNullOrWhiteSpace($normalizedName) -or $normalizedName.EndsWith("/")
					}).Count
					$junkEntryCount = 0
					if (-not $IncludeJunkEntries) {
						$junkEntryCount = @($archive.Entries | Where-Object {
							$normalizedName = Normalize-ZipEntryName -EntryName $_.FullName
							(-not [string]::IsNullOrWhiteSpace($normalizedName)) -and
								(-not $normalizedName.EndsWith("/")) -and
								(Test-JunkEntry -EntryName $normalizedName)
						}).Count
					}
					$needsRewrite = ($nestedCount -gt 0) -or ($renamedCount -gt 0) -or ($directoryEntryCount -gt 0) -or ($junkEntryCount -gt 0)

					if (-not $needsRewrite) {
						$summary.AlreadyFlat++
						Write-Host "OK flat: $($cbzFile.FullName)"
						continue
					}

					foreach ($plannedEntry in $plan | Where-Object { $_.OriginalName -cne $_.TargetName }) {
						Write-Verbose ("{0} -> {1}" -f $plannedEntry.OriginalName, $plannedEntry.TargetName)
					}

					if (-not $Apply) {
						$summary.WouldFlatten++
						Write-Host ("WOULD flatten: {0} (files={1}, nested={2}, renamed={3}, folders={4}, junk={5})" -f $cbzFile.FullName, $plan.Count, $nestedCount, $renamedCount, $directoryEntryCount, $junkEntryCount)
						continue
					}
				} finally {
					$archive.Dispose()
				}

				Save-FlattenedCbz -CbzFile $cbzFile

				$summary.Flattened++
				Write-Host "FLATTENED: $($cbzFile.FullName)"
			} catch {
				$summary.Errors++
				Write-Warning "FAILED: $($cbzFile.FullName) - $($_.Exception.Message)"

				if ($StopOnError) {
					throw
				}
			}
		}

		Write-Host ""
		Write-Host "Summary"
		Write-Host "  Archives found: $($summary.ArchivesFound)"
		Write-Host "  Already flat:   $($summary.AlreadyFlat)"
		Write-Host "  Would flatten:  $($summary.WouldFlatten)"
		Write-Host "  Flattened:      $($summary.Flattened)"
		Write-Host "  Errors:         $($summary.Errors)"

		if (-not $Apply) {
			Write-Host ""
			Write-Host "Dry run only. Re-run with -Apply to rewrite CBZ files."
		}
} finally {
	Stop-OutputLog
}
