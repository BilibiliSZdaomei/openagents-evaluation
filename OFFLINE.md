# 离线安装容器镜像

在能访问 GitHub 的电脑下载本仓代码、`openagents-linux-amd64-images.tar.gz` 和 `SHA256SUMS`。后两个文件放在同一目录，再传到目标机。镜像适用于 Linux x86_64 和 Windows x64 的 Docker Desktop Linux 容器模式。[下载此版本的依赖](https://github.com/BilibiliSZdaomei/openagents-evaluation/releases/tag/runtime-linux-amd64-20261124)

## Ubuntu / WSL

在仓库根目录运行，最后一个参数指向镜像压缩包。使用同一个已获准操作 Docker 的普通 Linux 账号完成导入和启动。

```bash
python3 manage.py images /path/to/openagents-linux-amd64-images.tar.gz
python3 manage.py up
```

## Windows

将镜像压缩包和 SHA256SUMS 放在仓库根目录，启动 Docker Desktop，双击仓库里的 `Import-Images.cmd`。完成后双击 `Start.cmd`。镜像放在其他目录时可在 PowerShell 指定路径：

```powershell
.\Start.cmd images "D:\Downloads\openagents-linux-amd64-images.tar.gz"
```

## 共享 Docker 引擎上的镜像名称

导入时由 `manage.py` 校验压缩包的 SHA-256，并按[镜像锁](images.lock.json)逐个核对应用、数据库和 Nginx。原始压缩包内含通用的 PostgreSQL、Nginx 标签，因此公司服务器请始终用上面的项目导入命令，切勿用 `docker load -i` 直接加载该原包。

导入器仅将锁定的镜像配置与层交给 Docker，生成的运行标签均以 `openagents-evaluation/runtime-` 开头并带镜像 ID 前缀。已有共享镜像标签保持原样；若目标项目标签已指向其他 ID，导入会停止，请管理员核对该项目名称冲突。重新运行部署命令会复用当前引擎中 ID 匹配的镜像。Docker 29 使用 containerd 时，列表显示的 IMAGE ID 可能是清单的摘要。导入命令以 Linux/amd64 镜像配置的 SHA-256 为准。导入后可查看项目标签：

```bash
docker image ls --no-trunc --filter 'reference=openagents-evaluation/runtime-*'
```

离线包包括应用运行所需的四个容器镜像。首次启动需要自己准备评测登录密码与 DeepSeek API Key。真实对话需要后端容器可访问 DeepSeek；安装、停启、数据与 SSH 转发见[部署说明](README.md)。
