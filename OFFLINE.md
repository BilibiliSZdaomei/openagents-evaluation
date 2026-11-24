# 离线安装所需的容器镜像

在可访问 GitHub 的电脑登录仓库账号，从[此版本的依赖下载页](https://github.com/BilibiliSZdaomei/openagents-evaluation/releases/tag/runtime-linux-amd64-20261124)下载 `SHA256SUMS` 和全部镜像附件。把附件放在同一目录，另将仓库源码下载或克隆到公司电脑。

镜像适用于 Linux x86_64，也可在 Windows x64 的 Docker Desktop（Linux 容器）中使用。安装 Docker 和 Docker Compose v2 后，在镜像下载目录执行下面的命令，然后按仓库首页启动。DeepSeek 在线对话需要从部署机访问模型服务，并使用你自己的 API Key。

**Windows PowerShell**

```powershell
$ErrorActionPreference = "Stop"
foreach ($line in Get-Content -LiteralPath .\SHA256SUMS) {
    if ($line -notmatch '^([a-fA-F0-9]{64})  ([A-Za-z0-9._-]+)$') { throw "校验清单格式有误" }
    $expected = $matches[1]
    $file = Join-Path (Get-Location) $matches[2]
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $expected) { throw "校验失败 $file" }
    docker image load -i $file
    if ($LASTEXITCODE -ne 0) { throw "镜像导入失败 $file" }
}
```

**Linux / WSL**

```bash
sha256sum -c SHA256SUMS && (
  set -e
  while read -r digest image; do
    docker image load -i "$image"
  done < SHA256SUMS
)
```
