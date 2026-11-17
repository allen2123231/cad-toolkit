param(
 [Parameter(Mandatory=$true)][string]$Inventory,
 [Parameter(Mandatory=$true)][string]$Output,
 [switch]$RequireTrusted
)
$ErrorActionPreference='Stop'
$inputData=Get-Content -LiteralPath $Inventory -Raw | ConvertFrom-Json
$cache=@{}
$files=@(foreach($entry in $inputData.files){
 $actual=(Get-FileHash -LiteralPath $entry.path -Algorithm SHA256).Hash.ToLowerInvariant()
 if($actual -ne $entry.sha256){throw 'Signature-audit staging file changed'}
 if(-not $cache.ContainsKey($entry.sha256)){
  $signature=Get-AuthenticodeSignature -LiteralPath $entry.path
  $cache[$entry.sha256]=@{status=$signature.Status.ToString();signer=if($signature.SignerCertificate){$signature.SignerCertificate.Subject}else{$null};thumbprint=if($signature.SignerCertificate){$signature.SignerCertificate.Thumbprint}else{$null}}
 }
 $result=$cache[$entry.sha256]
 [ordered]@{source=$entry.source;sha256=$entry.sha256;status=$result.status;signer=$result.signer;thumbprint=$result.thumbprint}
})
$invalid=@($files | Where-Object {$_.status -ne 'Valid'})
$report=[ordered]@{schema=1;all_signatures_valid=($invalid.Count -eq 0);entries=$files.Count;distinct_bytes=$cache.Count;unsigned_or_untrusted=$invalid.Count;installer_sha256=$inputData.installer_sha256;payload_sha256=$inputData.payload_sha256;files=$files;scope='Authenticode trust on the audit machine; a separate installation/update/uninstall test on SAC-enforced Windows is still required.'}
$parent=Split-Path -Parent ([IO.Path]::GetFullPath($Output));New-Item -ItemType Directory -Force -Path $parent | Out-Null
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding UTF8
Write-Output "Signature audit: $($files.Count) executable entries; $($invalid.Count) unsigned or untrusted."
if($RequireTrusted -and $invalid.Count -gt 0){throw 'Release blocked: executable content is unsigned or untrusted. See the signature audit report.'}
