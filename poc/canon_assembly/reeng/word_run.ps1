# Word 2013 COM runner: executes steps from plan JSON (ASCII-escaped). Word PID -> pidfile; always Quit in finally.
param([string]$Plan)
$ErrorActionPreference = 'Stop'
$p = Get-Content -Raw -Encoding UTF8 $Plan | ConvertFrom-Json
$log = $p.log
function L($m) { Add-Content -Path $log -Value ((Get-Date -Format 'HH:mm:ss') + ' ' + $m) -Encoding UTF8 }
$before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
Start-Sleep -Milliseconds 500
$mine = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id } | ForEach-Object { $_.Id })
Set-Content -Path $p.pidfile -Value ($mine -join ',') -Encoding ASCII
L ("word pid " + ($mine -join ','))
$m = [Type]::Missing
function OpenDoc($path, $ro) { return $w.Documents.Open($path, $false, $ro, $false) }
try {
  foreach ($s in $p.steps) {
    L ("step " + $s.op)
    if ($s.op -eq 'convert') {
      try { $d = OpenDoc $s.src $true }
      catch {   # повреждённый .doc: повторное открытие с восстановлением (OpenAndRepair)
        L ("open failed, repair: " + $_.Exception.Message)
        $d = $w.Documents.Open($s.src, $false, $true, $false, $m, $m, $false, $m, $m, $m, $m, $false, $true)
      }
      try { $d.SaveAs2([ref]$s.dst, [ref]16); $d.Close([ref]0) }
      catch {   # Word не сохраняет этот .doc в docx («Ошибка файла»): через RTF (секции, колонтитулы сохраняются)
        L ("save docx failed, via rtf: " + $_.Exception.Message)
        $rtf = $s.dst + '.rtf'
        $d.SaveAs2([ref]$rtf, [ref]6); $d.Close([ref]0)
        $d = OpenDoc $rtf $true
        $d.SaveAs2([ref]$s.dst, [ref]16); $d.Close([ref]0)
        Remove-Item $rtf -ErrorAction SilentlyContinue
      }
    }
    elseif ($s.op -eq 'assemble') {
      $d = OpenDoc $s.base $false
      foreach ($ins in $s.inserts) {
        $frs = @($ins.frags)
        foreach ($fr in $frs) {
          $r = $d.Content
          $f = $r.Find
          $f.ClearFormatting()
          $ok = $f.Execute($ins.marker)
          if (-not $ok) { L ("marker not found " + $ins.marker); break }
          $r.Collapse(1)
          $r.InsertFile($fr, $m, $false, $false, $false)
          L ("inserted " + $fr)
        }
        $r = $d.Content
        $f = $r.Find
        if ($f.Execute($ins.marker)) {
          $pr = $r.Paragraphs.Item(1).Range
          try { $pr.Delete() | Out-Null }
          catch {   # абзац-маркер нельзя удалить целиком (последний абзац/ячейка): стираем только текст маркера
            L ("marker paragraph not deletable, text cleared: " + $ins.marker)
            $r.Text = ''
          }
        }
      }
      $d.SaveAs2([ref]$s.out, [ref]16)
      $d.Close([ref]0)
    }
    elseif ($s.op -eq 'concat') {   # склейка файлов-глав в один docx (порядок = порядок списка), между главами разрыв раздела
      $d = $w.Documents.Add()
      $first = $true
      foreach ($f in $s.files) {
        try {
          $r = $d.Content; $r.Collapse(0)
          if (-not $first) { $r.InsertBreak(2); $r = $d.Content; $r.Collapse(0) }
          $r.InsertFile($f, $m, $false, $false, $false)
          $first = $false
        } catch { L ("WARN insert failed " + $f + ": " + $_.Exception.Message) }
      }
      L ("concat files " + @($s.files).Count + " pages " + $d.ComputeStatistics(2))
      $d.SaveAs2([ref]$s.out, [ref]16)
      $d.Close([ref]0)
    }
    elseif ($s.op -eq 'compare') {
      $o = OpenDoc $s.orig $false
      $o.Compare($s.revised, 'reeng', 2, $false, $true, $false, $false, $false)
      $c = $w.ActiveDocument
      $c.SaveAs2([ref]$s.out, [ref]16)
      $c.Close([ref]0)
      $o.Close([ref]0)
    }
    elseif ($s.op -eq 'pdf') {
      $d = OpenDoc $s.src $true
      $d.ExportAsFixedFormat($s.out, 17)
      L ("pages " + $d.ComputeStatistics(2))
      $d.Close([ref]0)
    }
    elseif ($s.op -eq 'dump') {
      $d = OpenDoc $s.src $true
      $lines = New-Object System.Collections.Generic.List[string]
      $i = 0
      foreach ($pa in $d.Paragraphs) {
        $i++
        $rg = $pa.Range
        $ls = $rg.ListFormat.ListString
        $t = $rg.Text -replace "[\r\n\t\a\v]", ' '
        $tb = if ($rg.Information(12)) { 'T' } else { '-' }
        $lines.Add("$i`t$tb`t$ls`t$t`t$($rg.Start)")
      }
      function ShapeText($sh, $anc) {
        try {
          if ($sh.Type -eq 6) { foreach ($g in $sh.GroupItems) { ShapeText $g $anc } }
          elseif ($sh.Type -eq 20) { foreach ($g in $sh.CanvasItems) { ShapeText $g $anc } }
          elseif ($sh.TextFrame.HasText) { $tt = $sh.TextFrame.TextRange.Text -replace "[\r\n\t\a\v]", ' '; $script:i++; $lines.Add("$script:i`tS`t`t$tt`t$anc") }
        } catch {}
      }
      $script:i = $i
      foreach ($sh in $d.Shapes) { $anc = -1; try { $anc = $sh.Anchor.Start } catch {}; ShapeText $sh $anc }
      try { foreach ($fn in $d.Footnotes) { $tt = $fn.Range.Text -replace "[\r\n\t\a\v]", ' '; $script:i++; $lines.Add("$script:i`tF`t`t$tt") } } catch {}
      try { foreach ($fn in $d.Endnotes) { $tt = $fn.Range.Text -replace "[\r\n\t\a\v]", ' '; $script:i++; $lines.Add("$script:i`tF`t`t$tt") } } catch {}
      [IO.File]::WriteAllLines($s.out, $lines, (New-Object Text.UTF8Encoding($false)))
      $d.Close([ref]0)
    }
  }
  L 'done'
}
catch { L ("ERROR " + $_.Exception.Message + ' @ ' + $_.InvocationInfo.ScriptLineNumber) }
finally {
  try { $w.Quit([ref]0) } catch {}
  Start-Sleep -Seconds 1
  foreach ($i in $mine) { Stop-Process -Id $i -Force -ErrorAction SilentlyContinue }
}
