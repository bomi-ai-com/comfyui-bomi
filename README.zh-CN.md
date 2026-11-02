# comfy-bomi

[English](README.md)

Bomi AI 企业接口的四个 ComfyUI 节点。每个节点接一张图，内部走完整流程，直接返回成品图。

| 节点 | 产出 | 需要你选 |
|---|---|---|
| **Bomi 背景生成** | 1–4 张换好背景的商品图 | 背景风格、生成数量 |
| **Bomi AI 套图** | 一次出两批图：模特图和背景图 | 套图风格、两者各自的数量、画面比例、模特性别、首饰类型、镜头类型 |
| **Bomi 电商白底图** | 一张干净的白底商品图 | 品类预设 |
| **Bomi 戒指佩戴** | 一张手戴戒指的效果图 | 品类；人种、性别、角度可以不指定 |

四个节点都在节点菜单的 **Bomi** 分类下。

## 1. 安装

需要 ComfyUI 和 Python 3.9+。

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/bomi-ai-com/comfyui-bomi.git
pip install -r comfyui-bomi/requirements.txt
```

## 2. 获取 API Key

在 BomiAI 网站 https://bomi-ai.com/ 获取 API Key。
具体路径：个人中心 - API管理 - 创建 API Key。

## 3. 填入 API Key

```bash
cd ComfyUI/custom_nodes/comfyui-bomi
cp config.example.json config.json
```

打开 `config.json`，把你的 Key 填到 `enterpriseApiKey`。

```json
{ "enterpriseApiKey": "bmk...", "language": "zh" }
```

Key 填好之前什么都做不了 —— 风格下拉框也要靠它才能加载。
工作流样例在 `example_workflows/` 文件夹下


## 常见问题

| 现象 | 处理 |
|---|---|
| 菜单里没有 Bomi 节点 | 节点包没加载成功。在控制台找 `[Bomi] failed to load comfy-bomi`，通常是缺依赖：`pip install -r requirements.txt` |
| `未配置 API Key。` | `config.json` 里没有 Key，见第 2、3 步 |
| 下拉框显示 `— 请选择（列表未加载）—` | Key 缺失或不对。改好后刷新浏览器 |
| 运行时报 `未选择选项` | 该下拉框还停在占位项上，选一个真实值 |
| `企业未开通该功能` | 你的 Bomi 账号没开通这个功能，请联系 Bomi |
| `企业积分不足` | 积分不够。报错上面那行日志写了这次任务需要多少 |

## 许可

MIT，见 [LICENSE](LICENSE)。
