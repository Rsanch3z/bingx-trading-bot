param([string]$ServiceName = "BingXBot")
nssm stop $ServiceName
nssm remove $ServiceName confirm
Write-Host "$ServiceName removed."
