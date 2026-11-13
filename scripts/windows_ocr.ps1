# AI Dictionary - in-memory Windows OCR bridge using Windows.Media.Ocr.
# Dot-source from the tray shell: . "$PSScriptRoot\windows_ocr.ps1"
# Returns: [pscustomobject]@{ Status; Text; Lines; Language; ElapsedMs; Message }

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
Add-Type -AssemblyName System.Drawing | Out-Null

$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataWriter, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]

$script:AidictOcrTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Wait-AidictWinRt($Operation, $ResultType) {
    $asTask = $script:AidictOcrTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($Operation))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

function Get-AidictOcrEngine {
    foreach ($tag in @('zh-Hans-CN', 'zh-Hans', 'en-US')) {
        try {
            $language = [Windows.Globalization.Language]::new($tag)
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
            if ($null -ne $engine) { return $engine }
        } catch {
        }
    }
    try {
        return [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    } catch {
        return $null
    }
}

function Remove-AidictCjkSpacing([string]$Text) {
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $pattern = '(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff，。！？；：、（）《》“”‘’])'
    $Text = [regex]::Replace($Text, $pattern, '')
    $Text = [regex]::Replace($Text, '(?<=[，。！？；：、（）《》“”‘’])\s+(?=[\u4e00-\u9fff])', '')
    return $Text
}

function Invoke-AidictWindowsOcr {
    param(
        [Parameter(Mandatory = $true)][System.Drawing.Bitmap]$Bitmap,
        [int]$MaxLines = 200
    )

    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $engine = Get-AidictOcrEngine
    if ($null -eq $engine) {
        return [pscustomobject]@{
            Status   = 'unavailable'
            Text     = ''
            Lines    = @()
            Language = ''
            ElapsedMs = 0
            Message  = 'Windows OCR 引擎不可用，请安装系统语言包（设置 → 时间和语言 → 语言）。'
        }
    }

    try {
        $stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
        $writer = [Windows.Storage.Streams.DataWriter]::new($stream)
        $memory = [System.IO.MemoryStream]::new()
        $Bitmap.Save($memory, [System.Drawing.Imaging.ImageFormat]::Png)
        $bytes = $memory.ToArray()
        $memory.Dispose()
        $writer.WriteBytes($bytes)
        $null = Wait-AidictWinRt ($writer.StoreAsync()) ([UInt32])
        $null = Wait-AidictWinRt ($writer.FlushAsync()) ([Boolean])
        $null = $stream.Seek(0)
        $decoder = Wait-AidictWinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $softwareBitmap = Wait-AidictWinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Wait-AidictWinRt ($engine.RecognizeAsync($softwareBitmap)) ([Windows.Media.Ocr.OcrResult])

        $lines = New-Object System.Collections.ArrayList
        foreach ($line in $result.Lines) {
            if ($lines.Count -ge $MaxLines) { break }
            $text = Remove-AidictCjkSpacing $line.Text
            if ([string]::IsNullOrWhiteSpace($text)) { continue }
            $rects = @($line.Words | ForEach-Object { $_.BoundingRect })
            $left = 0.0; $top = 0.0; $right = 0.0; $bottom = 0.0
            if ($rects.Count -gt 0) {
                $left = ($rects | Measure-Object -Property X -Minimum).Minimum
                $top = ($rects | Measure-Object -Property Y -Minimum).Minimum
                $right = ($rects | ForEach-Object { $_.X + $_.Width } | Measure-Object -Maximum).Maximum
                $bottom = ($rects | ForEach-Object { $_.Y + $_.Height } | Measure-Object -Maximum).Maximum
            }
            [void]$lines.Add([pscustomobject]@{
                Text   = $text
                Left   = [math]::Round($left, 1)
                Top    = [math]::Round($top, 1)
                Width  = [math]::Round($right - $left, 1)
                Height = [math]::Round($bottom - $top, 1)
            })
        }

        $watch.Stop()
        $status = if ($lines.Count -gt 0) { 'ok' } else { 'empty' }
        $message = if ($lines.Count -gt 0) { "已识别 $($lines.Count) 行文本" } else { '未在选区中识别到文字，请放大选区或提高清晰度。' }
        return [pscustomobject]@{
            Status    = $status
            Text      = ($lines | ForEach-Object { $_.Text }) -join "`n"
            Lines     = @($lines)
            Language  = $engine.RecognizerLanguage.LanguageTag
            ElapsedMs = [math]::Round($watch.Elapsed.TotalMilliseconds, 1)
            Message   = $message
        }
    } catch {
        $watch.Stop()
        return [pscustomobject]@{
            Status    = 'error'
            Text      = ''
            Lines     = @()
            Language  = ''
            ElapsedMs = [math]::Round($watch.Elapsed.TotalMilliseconds, 1)
            Message   = "OCR 失败：$($_.Exception.Message)"
        }
    } finally {
        if ($null -ne $writer) { try { $writer.Dispose() } catch {} }
        if ($null -ne $stream) { try { $stream.Dispose() } catch {} }
    }
}
