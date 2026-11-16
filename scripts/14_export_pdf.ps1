# Export paper/report_apart.docx to PDF with Microsoft Word, and report page counts:
# total pages and the page on which "References" and each appendix start (the 8-page limit excludes them).
param([string]$Docx = "$PSScriptRoot\..\paper\report_apart.docx")
$Docx = (Resolve-Path $Docx).Path
$Pdf = [System.IO.Path]::ChangeExtension($Docx, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($Docx, $false, $true)
    $doc.Repaginate()
    "total pages: " + $doc.ComputeStatistics(2)
    foreach ($p in $doc.Paragraphs) {
        $t = $p.Range.Text.Trim()
        if ($t -match '^(References|Appendix [A-E]\.|LLM Usage Statement|\d\. )') {
            "{0,-60} starts on page {1}" -f $t.Substring(0, [Math]::Min(60, $t.Length)), $p.Range.Information(3)
        }
    }
    $doc.ExportAsFixedFormat($Pdf, 17)
    $doc.Close($false)
    "wrote $Pdf"
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
