param(
  [Parameter(Mandatory=$false)][string]$ProjectId = $env:RAILWAY_PROJECT_ID,
  [Parameter(Mandatory=$false)][string]$EnvironmentId = $env:RAILWAY_ENV_ID
)

$ErrorActionPreference = 'Stop'

if (-not $env:RAILWAY_TOKEN) { Write-Output 'ERR:NO_TOKEN'; exit 1 }
if (-not $ProjectId) { Write-Output 'ERR:NO_PROJECT_ID'; exit 1 }
if (-not $EnvironmentId) { Write-Output 'ERR:NO_ENV_ID'; exit 1 }

$Headers = @{ Authorization = "Bearer $($env:RAILWAY_TOKEN)"; 'Content-Type'='application/json' }

function Invoke-Gql($Query, $Variables) {
  $payload = @{ query = $Query; variables = $Variables } | ConvertTo-Json -Compress -Depth 6
  return Invoke-RestMethod -Method Post -Uri 'https://backboard.railway.app/graphql/v2' -Headers $Headers -Body $payload
}

$mutation = @'
mutation up($input: VariableUpsertInput!) {
  variableUpsert(input: $input)
}
'@

# Read values only from env-vars (so you don't paste secrets inline here)
$batch = @(
  @{ name='EBAY_ENVIRONMENT';          value=$env:RV_EBAY_ENVIRONMENT },
  @{ name='EBAY_PRODUCTION_CLIENT_ID'; value=$env:RV_EBAY_PRODUCTION_CLIENT_ID },
  @{ name='EBAY_PRODUCTION_DEV_ID';    value=$env:RV_EBAY_PRODUCTION_DEV_ID },
  @{ name='EBAY_PRODUCTION_CERT_ID';   value=$env:RV_EBAY_PRODUCTION_CERT_ID },
  @{ name='EBAY_PRODUCTION_RUNAME';    value=$env:RV_EBAY_PRODUCTION_RUNAME },
  @{ name='ALLOWED_ORIGINS';           value=$env:RV_ALLOWED_ORIGINS },
  @{ name='FRONTEND_URL';              value=$env:RV_FRONTEND_URL },
  @{ name='DATABASE_URL';              value=$env:RV_DATABASE_URL } # optional; set only if you export it
) | Where-Object { $_.value -and $_.value.Trim().Length -gt 0 }

if ($batch.Count -eq 0) { Write-Output 'INFO:NO_VALUES_PROVIDED'; exit 0 }

foreach ($item in $batch) {
  try {
    $vars = @{ input = @{ projectId=$ProjectId; environmentId=$EnvironmentId; name=$item.name; value=$item.value } }
    $resp = Invoke-Gql -Query $mutation -Variables $vars
    if ($resp.errors) {
      Write-Output ("UPSERT: " + $item.name + " -> ERR")
    } else {
      Write-Output ("UPSERT: " + $item.name + " -> OK")
    }
  } catch {
    Write-Output ("UPSERT: " + $item.name + " -> EXC: " + $_.Exception.Message)
  }
}
