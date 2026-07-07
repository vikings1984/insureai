# InsureAI 运维命令
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

deploy:  ## 提示：推送到 GitHub 即由 Pages 自动部署（make sync 触发）
	@echo "主站托管于 GitHub Pages，推送即自动部署：运行 make sync。"
	@echo "日常更新只需重跑 collect 后 make sync，无需手动部署。"

sync:  ## 同步到 GitHub insureai 分支（经 gh-proxy 透传 gh 令牌，令牌仅运行时获取不落盘）
	@TOKEN=$$(gh auth token); \
	REMOTE="https://$${TOKEN}@gh-proxy.com/https://github.com/vikings1984/insureai.git"; \
	git -c credential.helper= -c http.version=HTTP/1.1 push "$$REMOTE" HEAD:insureai
