#Requires -Version 7
<#
.SYNOPSIS
Starts an always-on repository-level runner for this repository's configured release branches.

.DESCRIPTION
Run once from your clone on a Windows PC with Docker Desktop (Linux engine). The runner registers
to the repository named by `git remote get-url origin` with label imserverless-release and restarts with Docker.
It uses the host Docker engine, so run it only on a machine you control for your own repository.
Rerunning is safe: an existing registration and container are reused.
#>
param(
    [string]$Kubeconfig,               # optional; otherwise set the RANCHER_KUBECONFIG GitHub Secret
    [string]$Context = 'cn01-linux',
    [string]$Owner,                    # IMServerless owner; or set the IMSERVERLESS_OWNER GitHub variable
    [string]$Domain = 'GAR',
    [string]$BaseImage = 'amr-registry.caas.intel.com/soia/icmpcs-soims:base'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$runnerVersion = '2.338.2'
$downloads = @{
    'actions-runner.tar.gz' = @("https://github.com/actions/runner/releases/download/v$runnerVersion/actions-runner-linux-x64-$runnerVersion.tar.gz",
                                'baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40')
    'kubectl'               = @('https://dl.k8s.io/release/v1.26.15/bin/linux/amd64/kubectl',
                                'b75f359e6fad3cdbf05a0ee9d5872c43383683bb8527a9e078bb5b8a44350a41')
}
$origin = git -C $PSScriptRoot remote get-url origin
if ($origin -notmatch '^https://(?<host>[^/]+)/(?<repo>[^/]+/[^/]+?)(\.git)?$') { throw "Unsupported origin URL: $origin" }
$gitHubHost, $repository = $Matches.host, $Matches.repo
$name = 'imserverless-release-' + ($repository -replace '[^A-Za-z0-9]+', '-').ToLower()
if ($name.Length -gt 63) { $name = $name.Substring(0, 63).TrimEnd('-') }
$image = 'imserverless-release-runner:' + $runnerVersion

if (docker ps -aq --filter "name=^$name$") {
    docker start $name | Out-Null
    Write-Host "Runner container $name is running for $repository"
    return
}

$cache = Join-Path $PSScriptRoot 'cache'
New-Item -ItemType Directory -Force $cache | Out-Null
foreach ($file in $downloads.Keys) {
    $path = Join-Path $cache $file
    if (-not (Test-Path $path)) { Invoke-WebRequest -Uri $downloads[$file][0] -OutFile $path }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $downloads[$file][1]) {
        Remove-Item $path
        throw "Checksum mismatch for $file; download removed"
    }
}
# Pull the selected base before building the runner tools.
docker pull $BaseImage
docker build --build-arg "BASE_IMAGE=$BaseImage" -t $image $PSScriptRoot

if (-not (docker run --rm -v "${name}:/runner" $image bash -c 'test -f .runner && echo configured || true')) {
    $credential = "protocol=https`nhost=$gitHubHost`n`n" | git credential fill
    $password = ($credential | Where-Object { $_ -like 'password=*' }) -replace '^password=', ''
    $token = (Invoke-RestMethod -Method Post -NoProxy -Headers @{ Authorization = "Bearer $password"; Accept = 'application/vnd.github+json' } `
        -Uri "https://$gitHubHost/api/v3/repos/$repository/actions/runners/registration-token").token
    Remove-Variable credential, password
    $token | docker run --rm -i -v "${name}:/runner" $image bash -c "read -r token; ./config.sh --unattended --replace --disableupdate --url https://$gitHubHost/$repository --name $name --labels imserverless-release --token `"`$token`""
    Remove-Variable token
}

$arguments = @('run', '-d', '--name', $name, '--restart', 'unless-stopped',
    '-v', "${name}:/runner", '-v', '/var/run/docker.sock:/var/run/docker.sock',
    '-e', "NO_PROXY=$gitHubHost,localhost,127.0.0.1,amr-registry.caas.intel.com,imcloud-rancher-k8s.s33prod.mfg.intel.com",
    '-e', "RUNNER_RANCHER_CONTEXT=$Context", '-e', "RUNNER_IMSERVERLESS_DOMAIN=$Domain")
if ($Owner) { $arguments += @('-e', "RUNNER_IMSERVERLESS_OWNER=$Owner") }
if ($Kubeconfig) {
    $source = (Resolve-Path $Kubeconfig).Path -replace '\\', '/'
    $arguments += @('--mount', "type=bind,source=$source,target=/run/runner-rancher.kubeconfig,readonly",
                    '-e', 'RUNNER_KUBECONFIG=/run/runner-rancher.kubeconfig')
}
docker @arguments $image | Out-Null
Write-Host "Runner $name registered to $repository and running; pushes to configured branches now release automatically"
