# InsureScope 运维命令
# 用法： make <target>

PY := python3

.PHONY: collect collect-dry deploy sync help

help:  ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

collect:  ## 运行采集管道，合并新资讯并写回 data.json
	$(PY) collect.py

collect-dry:  ## 仅预览将新增的条目，不写文件
	$(PY) collect.py --dry-run

deploy:  ## 提示：通过 WorkBuddy CloudStudio 部署当前目录（data.json 与 index.html 一同上传）
	@echo "请使用 WorkBuddy 的部署功能（CloudStudio）上传本目录。"
	@echo "日常更新只需重跑 collect 后重新部署，index.html 通常无需改动。"

sync:  ## 同步到 GitHub insurescope 分支（绕过本机 gh-proxy，使用 gh 凭证助手）
	@cp ~/.gitconfig .gitconfig.tmp && sed -i '' '/gh-proxy/d' .gitconfig.tmp && \
	GIT_CONFIG_GLOBAL=$(PWD)/.gitconfig.tmp git -c credential.helper= -c 'credential.https://github.com.helper=!gh auth git-credential' push -u https://github.com/vikings1984/insureai.git HEAD:insurescope && \
	rm -f .gitconfig.tmp
