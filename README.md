# comfy-bomi

[简体中文](README.zh-CN.md)

Four ComfyUI nodes for the Bomi AI enterprise API. Each one takes an image, does the whole
job by itself, and hands back the finished images.

| Node | What it makes | What you pick |
|---|---|---|
| **Bomi Background** | 1–4 shots of your product on a new background | a background style, how many |
| **Bomi AI Suite** | two batches at once: model shots and background shots | a suite style, how many of each, aspect ratios, model gender, jewelry type, shot type |
| **Bomi White Background** | one clean white-background product image | a category preset |
| **Bomi Ring Try-On** | one shot of a hand wearing your ring | a category; ethnicity, gender and angle are optional |

All four live under the **Bomi** category in the node menu.

## 1. Install

Needs ComfyUI and Python 3.9+.

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/bomi-ai-com/comfyui-bomi.git
pip install -r comfyui-bomi/requirements.txt
```

## 2. Obtain API key

Get your API key from BomiAI website (https://bomi-ai.com/).
Path: Personal Center - API Management - Create API Key.

## 3. Add your API key

```bash
cd ComfyUI/custom_nodes/comfyui-bomi
cp config.example.json config.json
```

Open `config.json` and put your key in `enterpriseApiKey`.

```json
{ "enterpriseApiKey": "bmk...", "language": "en" }
```

Nothing works before the key is in place — it is also what fills the style dropdowns.
Workflow examples can be found in the `example_workflows/` folder.


## Troubleshooting

| Problem | Fix |
|---|---|
| No Bomi nodes in the menu | The pack failed to load. Look for `[Bomi] failed to load comfy-bomi` in the console — usually a missing dependency: `pip install -r requirements.txt` |
| `No API Key configured.` | No key in `config.json`. See step 2 and 3 |
| A dropdown reads `— choose one (list not loaded) —` | The key is missing or wrong. Fix it, then refresh the browser |
| `no option is selected` | That dropdown is still on its placeholder. Pick a real value |
| `Feature not enabled for the enterprise` | The feature is not enabled on your Bomi account. Contact Bomi |
| `Insufficient enterprise credits` | Out of credits. The console line above the error shows how many the job needed |

## License

MIT. See [LICENSE](LICENSE).
