param(
  [Parameter(Mandatory=$false)][string]$ProjectId = $env:RAILWAY_PROJECT_ID,
  [Parameter(Mandatory=$false)][string]$EnvironmentId = $env:RAILWAY_ENV_ID
)

$ErrorActionPreference = 'Stop'

if (-not $env:RAILWAY_TOKEN) { Write-Output 'ERR:NO_TOKEN'; exit 1 }
if (-not $ProjectId) { Write-Output 'ERR:NO_PROJECT_ID'; exit 1 }

$Headers = @{ Authorization = "Bearer $($env:RAILWAY_TOKEN)"; 'Content-Type'='application/json' }

function Invoke-Gql($Query, $Variables) {
  $payload = @{ query = $Query; variables = $Variables } | ConvertTo-Json -Compress -Depth 6
  return Invoke-RestMethod -Method Post -Uri 'https://backboard.railway.app/graphql/v2' -Headers $Headers -Body $payload
}

# 1) Fetch environments for the project
$queryEnvs = @'
query getProject($id: String!) {
  project(id: $id) {
    id
    name
    environments { edges { node { id name } } }
  }
}
'@

$resp = Invoke-Gql -Query $queryEnvs -Variables @{ id = $ProjectId }
if ($resp.errors) { 'ERR:GQL_ENVS'; $resp.errors | ConvertTo-Json -Compress; exit 2 }

$envs = @()
if ($resp.data.project -and $resp.data.project.environments) {
  $envs = $resp.data.project.environments.edges | ForEach-Object { $_.node }
}

Write-Output 'ENVIRONMENTS:'
$envs | Select-Object id,name | ConvertTo-Json -Compress

if (-not $EnvironmentId) { Write-Output 'INFO:NO_ENV_ID_PROVIDED'; exit 0 }

# 2) Fetch variables for the environment
$queryVars = @'
query getVars($projectId: String!, $environmentId: String!) {
  variables(projectId: $projectId, environmentId: $environmentId) {
    edges { node { id name } }
  }
}
'@

$resp2 = Invoke-Gql -Query $queryVars -Variables @{ projectId = $ProjectId; environmentId = $EnvironmentId }
if ($resp2.errors) { 'ERR:GQL_VARS'; $resp2.errors | ConvertTo-Json -Compress; exit 3 }

$vars = @()
if ($resp2.data.variables) {
  $vars = $resp2.data.variables.edges | ForEach-Object { $_.node }
}

Write-Output 'VARIABLE_KEYS:'
$vars | Select-Object id,name | ConvertTo-Json -Compress
